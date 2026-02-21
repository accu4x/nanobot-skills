"""
Moltbook skill for nanobot (extended)
- Read-only heartbeat and DM helpers (existing)
- Owner-mediated posting workflow (drafts -> approve/deny)
- Drafts stored locally in data/drafts.json
- Logs written to events.log
- Optional Telegram notify: set NANOBOT_TELEGRAM_TOKEN and NANOBOT_TELEGRAM_CHAT_ID locally to receive approval requests

This file was patched to add endpoint discovery and safer API fallbacks: it will prefer agent-scoped endpoints if available, then fall back to global /posts, and finally to public scraping.
"""

import os
import json
import time
import re
from typing import Optional, List, Dict
import requests

HERE = os.path.dirname(__file__)
CRED_PATH = os.path.join(os.environ.get('USERPROFILE', ''), '.config', 'moltbook', 'credentials.json')
API_BASE = 'https://www.moltbook.com/api/v1'
DATA_DIR = os.path.join(HERE, 'data')
DRAFTS_PATH = os.path.join(DATA_DIR, 'drafts.json')
EVENT_LOG = os.path.join(HERE, 'events.log')
DISCOVERED_PATH = os.path.join(DATA_DIR, 'discovered_endpoints.json')

os.makedirs(DATA_DIR, exist_ok=True)
# ensure drafts file exists
if not os.path.exists(DRAFTS_PATH):
    with open(DRAFTS_PATH, 'w', encoding='utf8') as f:
        json.dump([], f, ensure_ascii=False)


def _log(msg: str):
    ts = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    line = f"[{ts}] {msg}\n"
    try:
        with open(EVENT_LOG, 'a', encoding='utf8') as f:
            f.write(line)
    except Exception:
        pass
    try:
        print(line, end='')
    except Exception:
        # Console may not accept some unicode characters on Windows (cp1252). Fall back to stderr write and ignore failures.
        try:
            import sys
            sys.stderr.write(line)
        except Exception:
            pass


def load_api_key():
    api_key = os.environ.get('MOLTBOOK_API_KEY')
    if api_key:
        return api_key
    if os.path.exists(CRED_PATH):
        try:
            j = json.load(open(CRED_PATH, 'r', encoding='utf8'))
            return j.get('api_key')
        except Exception:
            return None
    return None


class MoltbookClient:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or load_api_key()
        if not self.api_key:
            raise RuntimeError('MOLTBOOK_API_KEY not set and no credentials file found')
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {self.api_key}', 'Content-Type': 'application/json'})
        self.agent_id = None
        self.discovered = self._load_discovered()

    def _load_discovered(self):
        try:
            with open(DISCOVERED_PATH, 'r', encoding='utf8') as f:
                return json.load(f)
        except Exception:
            return {}

    # persistent pending verifications file path
    def _pending_path(self):
        return os.path.join(DATA_DIR, 'pending_verifications.json')

    def _ensure_pending_file(self):
        p = self._pending_path()
        try:
            if not os.path.exists(p):
                with open(p, 'w', encoding='utf8') as f:
                    json.dump([], f, ensure_ascii=False)
        except Exception as e:
            _log(f'Failed to ensure pending_verifications.json: {e}')

    def _save_pending_verification(self, rec: dict):
        p = self._pending_path()
        try:
            existing = []
            if os.path.exists(p):
                try:
                    with open(p, 'r', encoding='utf8') as f:
                        existing = json.load(f)
                except Exception:
                    existing = []
            existing.append(rec)
            with open(p, 'w', encoding='utf8') as f:
                json.dump(existing, f, indent=2, ensure_ascii=False)
        except Exception as e:
            _log(f'Failed to save pending verification: {e}')

    def _autosolve_challenge(self, text: str) -> Optional[float]:
        # Conservative autosolver: extract digits and simple spelled numbers, handle simple sum/total wording
        if not text or not isinstance(text, str):
            return None
        t = text.lower()
        words_to_nums = {
            'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,
            'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,
            'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90
        }
        def words_to_number(s: str) -> Optional[int]:
            parts = re.findall(r"[a-z]+", s)
            total = 0
            for p in parts:
                if p in words_to_nums:
                    total += words_to_nums[p]
                else:
                    return None
            return total if total > 0 else None

        nums = re.findall(r"[-+]?[0-9]*\.?[0-9]+", t)
        nums_f = []
        for n in nums:
            try:
                nums_f.append(float(n))
            except Exception:
                pass
        spelled_matches = re.findall(r"([a-z\- ]+)[^a-z0-9\-]{1}", t + ' ')
        spelled_nums = []
        for sm in spelled_matches:
            n = words_to_number(sm)
            if n is not None:
                spelled_nums.append(float(n))

        if 'total' in t or 'sum' in t or 'add' in t:
            cand = sum(nums_f) + sum(spelled_nums)
            if cand != 0:
                return float(cand)
        if len(spelled_nums) >= 2:
            return sum(spelled_nums)
        if len(nums_f) == 2:
            return nums_f[0] + nums_f[1]
        if len(nums_f) == 1 and float(nums_f[0]).is_integer():
            return float(nums_f[0])
        return None

    def _save_discovered(self):
        try:
            with open(DISCOVERED_PATH, 'w', encoding='utf8') as f:
                json.dump(self.discovered, f, indent=2)
        except Exception as e:
            _log(f'Failed to save discovered endpoints: {e}')

    def heartbeat(self):
        url = f'{API_BASE}/agents/heartbeat'
        r = self.session.post(url)
        r.raise_for_status()
        return r.json()

    def _try_get(self, path: str, timeout: int = 10):
        url = API_BASE + path
        try:
            r = self.session.get(url, timeout=timeout)
            return r
        except Exception as e:
            _log(f'HTTP GET {url} failed: {e}')
            return None

    def _try_post(self, path: str, payload: dict, timeout: int = 10):
        url = API_BASE + path
        try:
            r = self.session.post(url, json=payload, timeout=timeout)
            return r
        except Exception as e:
            _log(f'HTTP POST {url} failed: {e}')
            return None

    def discover_endpoints(self):
        """Discover usable API endpoints and cache them to DISCOVERED_PATH."""
        # Honor a forced agent id stored in monitored_comments.json so reply-tracking can work even
        # if /agents/me doesn't return an id for the current API key.
        try:
            mon_path = os.path.join(DATA_DIR, 'monitored_comments.json')
            if os.path.exists(mon_path):
                try:
                    mj = json.load(open(mon_path, 'r', encoding='utf8'))
                    fid = mj.get('force_agent_id')
                    if fid:
                        self.agent_id = fid
                        self.discovered.setdefault('agent_info', {})
                        self.discovered['agent_info']['id'] = fid
                        _log(f'Using forced agent id from monitored_comments.json: {fid}')
                except Exception:
                    _log('Failed to parse monitored_comments.json for force_agent_id; continuing')
        except Exception:
            pass

        # Try /agents/me first to get agent id (if supported)
        try:
            r = self.session.get(f"{API_BASE}/agents/me", timeout=10)
            if r.status_code == 200:
                info = r.json()
                parsed_id = None
                # Common direct keys
                if isinstance(info, dict):
                    parsed_id = info.get('id') or info.get('agent_id') or info.get('name')
                    # Wrapped agent object (e.g. {"success":true, "agent": { ... }})
                    agent_wrapped = info.get('agent') if isinstance(info.get('agent'), dict) else None
                    if agent_wrapped:
                        parsed_id = parsed_id or agent_wrapped.get('id') or agent_wrapped.get('agent_id') or agent_wrapped.get('name')
                    # Other container patterns like data/result/payload
                    for container in ('data', 'result', 'payload'):
                        if not parsed_id and isinstance(info.get(container), dict):
                            parsed_id = info[container].get('id') or info[container].get('agent_id') or (info[container].get('agent') or {}).get('id')
                # Only overwrite a forced agent id if the API returned a usable id
                if parsed_id:
                    self.agent_id = parsed_id
                    # store the full response so discover_endpoints can reuse discovery info
                    self.discovered['agent_info'] = info
                    _log(f'Discovered agent info: id={self.agent_id}')
                else:
                    _log('/agents/me returned no agent id; keeping forced agent id if present')
            else:
                _log(f'/agents/me returned status {r.status_code}')
        except Exception as e:
            _log(f'Error calling /agents/me: {e}')

        # Probe candidate read endpoints in order of preference
        candidates = []
        if self.agent_id:
            candidates += [f"/agents/{self.agent_id}/dms", f"/agents/{self.agent_id}/posts", f"/agents/{self.agent_id}/inbox", f"/agents/{self.agent_id}/comments"]
        candidates += ["/posts", "/dms"]

        for p in candidates:
            r = self._try_get(p)
            if not r:
                continue
            if r.status_code == 200:
                try:
                    data = r.json()
                    # Determine type (posts vs dms) heuristically
                    if isinstance(data, list) or isinstance(data, dict):
                        self.discovered['read_endpoint'] = p
                        _log(f'Using discovered read endpoint: {p}')
                        self._save_discovered()
                        return p
                except Exception:
                    # non-json response
                    self.discovered['read_endpoint'] = p
                    _log(f'Using discovered read endpoint (non-json): {p}')
                    self._save_discovered()
                    return p
            else:
                # log body for debugging
                body = r.text if hasattr(r, 'text') else ''
                _log(f'Probe {p} -> {r.status_code} {body}')

        _log('No API read endpoint discovered; will fall back to public scraping')
        return None

    def fetch_posts(self):
        """Fetch recent items using discovered endpoints or by reprobing. Returns a list of items (may be posts or dms)."""
        # Use cached endpoint if present
        read_ep = self.discovered.get('read_endpoint')
        if not read_ep:
            read_ep = self.discover_endpoints()

        if not read_ep:
            return []

        r = self._try_get(read_ep)
        if not r:
            _log(f'Failed to GET discovered endpoint {read_ep}'); return []
        if r.status_code != 200:
            _log(f'Discovered endpoint {read_ep} returned {r.status_code}: {r.text}'); return []

        try:
            data = r.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # common shapes: {"posts": [...] } or {"dms": [...]}
                for k in ('posts', 'dms', 'items'):
                    if k in data and isinstance(data[k], list):
                        return data[k]
                # fallback: return dict wrapped
                return [data]
        except Exception:
            # non-json; wrap as single item
            return [{'body': r.text}]

    def list_dms(self):
        # Backwards-compatible: attempt to fetch posts/dms via discovery
        items = self.fetch_posts()
        return items

    def send_dm(self, user_id: str, message: str):
        url = f'{API_BASE}/agents/dm/send'
        payload = {'user_id': user_id, 'message': message}
        r = self.session.post(url, json=payload)
        r.raise_for_status()
        return r.json()

    def discover_submolts(self, force: bool = False):
        """Discover available submolts (communities) and cache them."""
        if 'submolts' in self.discovered and not force:
            return self.discovered.get('submolts', [])
        r = self._try_get('/submolts')
        if not r:
            return []
        if r.status_code != 200:
            _log(f'/submolts probe -> {r.status_code} {getattr(r, "text", "")[:200]}')
            return []
        try:
            data = r.json()
            # Expecting list or {"submolts": [...]}
            subs = data if isinstance(data, list) else (data.get('submolts') or [])
            self.discovered['submolts'] = subs
            self._save_discovered()
            return subs
        except Exception:
            _log('Failed to parse /submolts response')
            return []

    def suggest_submolts(self, interests: Optional[List[str]] = None, limit: int = 5):
        """Return a list of suggested submolt names ranked by keyword match to interests."""
        interests = interests or ['hockey', 'card', 'cards', 'comic', 'collector', 'marketing', 'sports', 'hobby', 'trading', 'pokemon', 'community']
        subs = self.discover_submolts()
        if not subs:
            return []
        scored = []
        for s in subs:
            # Each submolt item may be a string name or dict with name/description
            name = s if isinstance(s, str) else s.get('name') or s.get('slug') or ''
            desc = ''
            if isinstance(s, dict):
                desc = (s.get('description') or '')
            text = f"{name} {desc}".lower()
            score = 0
            for kw in interests:
                if kw.lower() in text:
                    score += 1
            scored.append((score, name, s))
        # sort descending by score, then return names
        scored.sort(key=lambda x: (-x[0], x[1]))
        results = [t[1] for t in scored if t[0] > 0]
        # if no matches, return top N available names
        if not results:
            results = [ (s if isinstance(s,str) else s.get('name') or s.get('slug') or '') for s in subs ]
        # filter out empty
        results = [r for r in results if r]
        return results[:limit]

    def join_submolt(self, submolt_name: str):
        """Attempt to join a submolt. Returns response object or None."""
        # Try common join endpoints
        candidates = [f"/submolts/{submolt_name}/join", f"/submolts/join"]
        for p in candidates:
            payload = { 'name': submolt_name } if p.endswith('/join') else { 'name': submolt_name }
            r = self._try_post(p, payload)
            if not r:
                continue
            if r.status_code in (200,201):
                _log(f'Joined submolt {submolt_name} via {p}')
                return r.json()
            else:
                _log(f'Join attempt {p} -> {r.status_code} {r.text[:200]}')
        return None

    def _choose_submolt(self, provided: Optional[str] = None) -> Optional[str]:
        """Return a submolt name: prefer provided, then cached default, then suggested by interests."""
        if provided:
            return provided
        if 'default_submolt' in self.discovered:
            return self.discovered.get('default_submolt')
        suggestions = self.suggest_submolts()
        if suggestions:
            chosen = suggestions[0]
            self.discovered['default_submolt'] = chosen
            self._save_discovered()
            return chosen
        return None

    def create_post(self, title: str, body: str, submolt_name: Optional[str] = None, type_: str = 'text', tags: Optional[List[str]] = None, visibility: str = 'private'):
        """Create a post using the Moltbook API. The server expects a submolt_name and a type (text/image/link).
        This method will attempt agent-scoped endpoints first, then fall back to /posts. It will discover submolts if needed.

        Additionally, if the server returns a verification challenge in the response, save it to pending verifications
        and attempt to auto-solve simple numeric challenges when enabled.
        """
        if type_ not in ('text', 'image', 'link'):
            raise ValueError('type must be one of text/image/link')

        # Determine submolt
        submolt = self._choose_submolt(submolt_name)
        if not submolt:
            # try discovering submolts now
            self.discover_submolts()
            submolt = self._choose_submolt(submolt_name)
        if not submolt:
            raise RuntimeError('submolt_name is required to create a post; discover submolts and set submolt_name')

        payload = {'title': title, 'content': body, 'type': type_, 'submolt_name': submolt}
        if tags:
            payload['tags'] = tags

        tried = []
        # attempt agent-scoped post if agent id is known
        agent_info = self.discovered.get('agent_info')
        agent_id = None
        if agent_info and isinstance(agent_info, dict):
            agent_id = agent_info.get('id') or agent_info.get('agent_id') or agent_info.get('name')
            if not agent_id and 'agent' in agent_info and isinstance(agent_info['agent'], dict):
                agent_id = agent_info['agent'].get('id') or agent_info['agent'].get('agent_id') or agent_info['agent'].get('name')

        # helper to persist pending verification records
        def _pending_path(self):
            return os.path.join(DATA_DIR, 'pending_verifications.json')

        def _save_pending_verification(self, rec: dict):
            try:
                p = _pending_path(self)
                try:
                    existing = json.load(open(p, 'r', encoding='utf8'))
                except Exception:
                    existing = []
                existing.append(rec)
                json.dump(existing, open(p, 'w', encoding='utf8'), indent=2, ensure_ascii=False)
            except Exception as e:
                _log(f'Failed to save pending verification: {e}')

        # simple autosolver for numeric challenges (spelled numbers + digits, sum/diff)
        def _autosolve_challenge(self, text: str) -> Optional[float]:
            # Normalize text
            if not text or not isinstance(text, str):
                return None
            t = text.lower()
            # Map spelled numbers (simple) to digits
            words_to_nums = {
                'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,
                'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,
                'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90
            }
            def words_to_number(s: str) -> Optional[int]:
                # Very simple parser for phrases like 'thirty two' or 'twenty four'
                parts = re.findall(r"[a-z]+", s)
                total = 0
                last = 0
                for p in parts:
                    if p in words_to_nums:
                        val = words_to_nums[p]
                        total += val
                        last = val
                    else:
                        # unknown word
                        return None
                return total if total>0 else None

            # Try to extract digit numbers
            nums = re.findall(r"[-+]?[0-9]*\.?[0-9]+", t)
            nums_f = []
            for n in nums:
                try:
                    nums_f.append(float(n))
                except Exception:
                    pass
            # Try to find spelled numbers groups
            spelled_matches = re.findall(r"([a-z\- ]+)[^a-z0-9\-]{1}", t + ' ')
            spelled_nums = []
            for sm in spelled_matches:
                n = words_to_number(sm)
                if n is not None:
                    spelled_nums.append(float(n))

            # If the challenge asks for a total/sum, try summing numbers found
            if 'total' in t or 'sum' in t or 'add' in t:
                cand = sum(nums_f) + sum(spelled_nums)
                if cand != 0:
                    return float(cand)
            # If text mentions two spelled numbers like 'thirty two' and 'twenty four', return sum
            if len(spelled_nums) >= 2:
                return sum(spelled_nums)
            # If exactly two digit numbers found, return sum
            if len(nums_f) == 2:
                return nums_f[0] + nums_f[1]
            # If single integer found, return it
            if len(nums_f) == 1 and float(nums_f[0]).is_integer():
                return float(nums_f[0])
            return None

        # helper to handle verification in responses
        def _handle_verification_resp(resp_json, post_id_hint=None):
            try:
                v = None
                # response may have top-level 'verification' or be nested under 'post'
                if isinstance(resp_json, dict):
                    if 'verification' in resp_json:
                        v = resp_json.get('verification')
                        post_id = resp_json.get('post', {}).get('id') or post_id_hint
                    elif 'post' in resp_json and isinstance(resp_json.get('post'), dict) and 'verification' in resp_json.get('post'):
                        v = resp_json['post'].get('verification')
                        post_id = resp_json['post'].get('id') or post_id_hint
                    else:
                        return
                else:
                    return
                if not v or not isinstance(v, dict):
                    return
                # Persist pending verification record
                rec = {
                    'verification_code': v.get('verification_code'),
                    'post_id': post_id,
                    'challenge_text': v.get('challenge_text'),
                    'instructions': v.get('instructions'),
                    'expires_at': v.get('expires_at'),
                    'status': 'pending',
                    'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                }
                self._save_pending_verification(rec)
                _log(f'Found verification challenge for post {post_id}; saved to pending_verifications.json')

                # Auto-solve if allowed
                auto = os.environ.get('MOLTBOOK_AUTO_SOLVE', '1')
                if auto == '1':
                    ans = self._autosolve_challenge(v.get('challenge_text') or '')
                    if ans is not None:
                        formatted = f"{ans:.2f}"
                        _log(f'Attempting auto-verify with answer {formatted} for code {v.get("verification_code")}')
                        subr = self._try_post('/verify', {'verification_code': v.get('verification_code'), 'answer': formatted}, timeout=15)
                        if subr and subr.status_code in (200,201):
                            _log(f'Auto-verify succeeded for code {v.get("verification_code")}')
                            rec['status'] = 'succeeded'
                            rec['answer'] = formatted
                            rec['response'] = subr.text
                            self._save_pending_verification(rec)
                            return
                        else:
                            _log(f'Auto-verify attempt failed: {getattr(subr, "status_code", None)} {getattr(subr, "text", "")}')
                            rec['status'] = 'attempted'
                            rec['attempt_response'] = getattr(subr, 'text', '')
                            self._save_pending_verification(rec)
                    else:
                        _log('Auto-solver could not derive a confident numeric answer; left pending')
                else:
                    _log('Auto-solve disabled by env var MOLTBOOK_AUTO_SOLVE=0; verification left pending')
            except Exception as e:
                _log(f'Error handling verification response: {e}')
        # try agent-scoped endpoint first
        if agent_id:
            path = f"/agents/{agent_id}/posts"
            tried.append(path)
            r = self._try_post(path, payload)
            if r and r.status_code in (200,201):
                try:
                    resp = r.json()
                except Exception:
                    resp = {}
                # save default submolt
                self.discovered['default_submolt'] = submolt
                self._save_discovered()
                # handle verification if present
                try:
                    _handle_verification_resp(resp, post_id_hint=None)
                except Exception:
                    pass
                return resp
            if r:
                _log(f'POST {path} -> {r.status_code} {r.text}')

        # fallback to global posts
        path = '/posts'
        tried.append(path)
        r = self._try_post(path, payload)
        if r and r.status_code in (200,201):
            try:
                resp = r.json()
            except Exception:
                resp = {}
            # Save chosen submolt as default
            self.discovered['default_submolt'] = submolt
            self._save_discovered()
            # handle verification
            try:
                _handle_verification_resp(resp, post_id_hint=resp.get('post', {}).get('id') if isinstance(resp, dict) else None)
            except Exception:
                pass
            return resp
        if r:
            _log(f'POST {path} -> {r.status_code} {r.text}')

        raise RuntimeError(f'Failed to create post. Tried: {tried}')


    def post_comment(self, post_id: str, content: str):
        """Post a comment to a post. Do NOT include a 'type' field. Handles verification challenges and autosolve similarly to create_post."""
        path = f"/posts/{post_id}/comments"
        payload = {'content': content}
        r = self._try_post(path, payload)
        if not r:
            _log(f'POST {path} failed: no response')
            return None
        try:
            resp = r.json()
        except Exception:
            resp = {}
        if r.status_code in (200,201):
            # Inspect for verification under top-level or under 'comment'
            v = None
            comment_id = None
            if isinstance(resp, dict):
                if 'verification' in resp:
                    v = resp.get('verification')
                    comment_id = resp.get('comment', {}).get('id')
                elif 'comment' in resp and isinstance(resp.get('comment'), dict) and 'verification' in resp.get('comment'):
                    v = resp['comment'].get('verification')
                    comment_id = resp['comment'].get('id')
            if v and isinstance(v, dict):
                rec = {
                    'verification_code': v.get('verification_code'),
                    'comment_id': comment_id,
                    'post_id': post_id,
                    'challenge_text': v.get('challenge_text'),
                    'instructions': v.get('instructions'),
                    'expires_at': v.get('expires_at'),
                    'status': 'pending',
                    'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                }
                try:
                    self._save_pending_verification(rec)
                except Exception:
                    _log('Failed to persist pending verification for comment')
                _log(f'Found verification challenge for comment on post {post_id}; saved to pending_verifications.json')
                auto = os.environ.get('MOLTBOOK_AUTO_SOLVE', '1')
                if auto == '1':
                    ans = self._autosolve_challenge(v.get('challenge_text') or '')
                    if ans is not None:
                        formatted = f"{ans:.2f}"
                        _log(f'Attempting auto-verify with answer {formatted} for code {v.get("verification_code")}')
                        subr = self._try_post('/verify', {'verification_code': v.get('verification_code'), 'answer': formatted}, timeout=15)
                        if subr and getattr(subr, 'status_code', None) in (200,201):
                            _log(f'Auto-verify succeeded for code {v.get("verification_code")}')
                            rec['status'] = 'succeeded'
                            rec['answer'] = formatted
                            rec['response'] = getattr(subr, 'text', '')
                            try:
                                self._save_pending_verification(rec)
                            except Exception:
                                _log('Failed to update pending verification record after success')
                        else:
                            _log(f'Auto-verify attempt failed: {getattr(subr, "status_code", None)} {getattr(subr, "text", "")[:300]}')
                            rec['status'] = 'attempted'
                            rec['attempt_response'] = getattr(subr, 'text', '')
                            try:
                                self._save_pending_verification(rec)
                            except Exception:
                                _log('Failed to update pending verification record after attempt')
                    else:
                        _log('Auto-solver could not derive a confident numeric answer for comment challenge; left pending')
                else:
                    _log('Auto-solve disabled by env var MOLTBOOK_AUTO_SOLVE=0; comment verification left pending')
            return resp
        else:
            _log(f'POST {path} -> {r.status_code} {getattr(r, "text", "")[:300]}')
            try:
                return r.json()
            except Exception:
                return {'status_code': r.status_code, 'text': getattr(r, 'text', '')}

    # monitored comments persistence
    def _monitored_path(self):
        return os.path.join(DATA_DIR, 'monitored_comments.json')

    def _ensure_monitored_file(self):
        p = self._monitored_path()
        try:
            if not os.path.exists(p):
                with open(p, 'w', encoding='utf8') as f:
                    json.dump({'comments': {}}, f, ensure_ascii=False)
        except Exception as e:
            _log(f'Failed to ensure monitored_comments.json: {e}')

    def _load_monitored(self) -> Dict:
        p = self._monitored_path()
        try:
            with open(p, 'r', encoding='utf8') as f:
                return json.load(f)
        except Exception:
            return {'comments': {}}

    def _save_monitored(self, data: Dict):
        p = self._monitored_path()
        try:
            with open(p, 'w', encoding='utf8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            _log(f'Failed to save monitored comments: {e}')

    def monitor_replies(self, notifier=None):
        """Check for new replies to comments authored by this agent and notify/log them. Persists seen-reply ids to monitored_comments.json.
        Notifier should implement notify(text) (TelegramNotifier does).
        """
        try:
            self._ensure_monitored_file()
            monitored = self._load_monitored()
            seen_map = monitored.get('comments', {})

            # Ensure we have agent id
            if not self.agent_id:
                try:
                    self.discover_endpoints()
                except Exception:
                    pass
            if not self.agent_id:
                _log('monitor_replies: cannot determine agent id; skipping')
                return

            # Attempt to list comments authored by agent
            path = f"/agents/{self.agent_id}/comments"
            r = self._try_get(path)
            authored_comments = []
            if r and r.status_code == 200:
                try:
                    authored_comments = r.json() or []
                except Exception:
                    authored_comments = []
            else:
                # Fallback: scan recent posts and find comments authored by this agent by fetching post comments
                _log(f'monitor_replies: fallback listing comments by scanning recent posts (probe returned {getattr(r, "status_code", None)})')
                posts = []
                try:
                    posts = self.fetch_posts()
                except Exception:
                    posts = []
                for p in posts:
                    # normalize post item to dict; skip unexpected shapes
                    try:
                        if isinstance(p, str):
                            try:
                                p = json.loads(p)
                            except Exception:
                                continue
                        if not isinstance(p, dict):
                            continue
                        pid = p.get('id') or p.get('post_id')
                        if not pid:
                            continue
                    except Exception:
                        continue
                    creq = self._try_get(f"/posts/{pid}/comments?limit=200&sort=recent&include=all")
                    if not creq or creq.status_code != 200:
                        continue
                    try:
                        comments = creq.json() or []
                        # normalize comments into a list of dicts if wrapped
                        if isinstance(comments, dict):
                            comments = comments.get('comments') or comments.get('items') or [comments]
                        if isinstance(comments, str):
                            try:
                                tmp = json.loads(comments)
                                if isinstance(tmp, list):
                                    comments = tmp
                                elif isinstance(tmp, dict):
                                    comments = [tmp]
                                else:
                                    comments = []
                            except Exception:
                                comments = []
                    except Exception:
                        comments = []
                    for c in comments:
                        if not isinstance(c, dict):
                            continue
                        author_id = c.get('author_id') or (c.get('author') or {}).get('id')
                        if author_id == self.agent_id:
                            authored_comments.append(c)

            new_alerts = []
            for c in authored_comments:
                cid = c.get('id') or c.get('comment_id')
                post_id = c.get('post_id') or c.get('post', {}).get('id')
                if not cid or not post_id:
                    continue
                seen_replies = set(seen_map.get(cid, []))
                # fetch replies to the comment via the post comments endpoint
                creq = self._try_get(f"/posts/{post_id}/comments?limit=200&sort=recent&include=all")
                if not creq or creq.status_code != 200:
                    continue
                try:
                    all_comments = creq.json() or []
                except Exception:
                    all_comments = []
                # replies are comments where depth>0 or that reference parent id (heuristic)
                for ac in all_comments:
                    # skip the original comment and any authored by us
                    aid = ac.get('id')
                    if not aid or aid == cid:
                        continue
                    # consider it a reply if parent points to cid or depth>0 or it's authored by someone else and created after our comment
                    is_reply = False
                    parent = ac.get('parent_id') or ac.get('reply_to') or ac.get('in_reply_to')
                    if parent and str(parent) == str(cid):
                        is_reply = True
                    if ac.get('depth') and int(ac.get('depth')) > 0:
                        is_reply = True
                    # else: author differs and timestamp after our comment
                    if not is_reply:
                        try:
                            our_created = c.get('created_at')
                            their_created = ac.get('created_at')
                            if our_created and their_created and their_created > our_created and ac.get('author_id') != self.agent_id:
                                is_reply = True
                        except Exception:
                            pass
                    if not is_reply:
                        continue
                    if aid in seen_replies:
                        continue
                    # New reply detected
                    seen_replies.add(aid)
                    excerpt = (ac.get('content') or '')[:240]
                    author = ac.get('author', {}).get('name') or ac.get('author_id') or 'unknown'
                    created = ac.get('created_at')
                    msg = f"New reply to comment {cid} on post {post_id} by {author} at {created}: {excerpt}"
                    _log(msg)
                    new_alerts.append(msg)
                    # If reply has verification challenge, handle it (similar to comment autosolve)
                    v = None
                    if isinstance(ac, dict) and 'verification' in ac:
                        v = ac.get('verification')
                    elif isinstance(ac, dict) and ac.get('comment') and isinstance(ac.get('comment'), dict) and 'verification' in ac.get('comment'):
                        v = ac.get('comment').get('verification')
                    if v:
                        rec = {
                            'verification_code': v.get('verification_code'),
                            'comment_id': aid,
                            'post_id': post_id,
                            'challenge_text': v.get('challenge_text'),
                            'instructions': v.get('instructions'),
                            'expires_at': v.get('expires_at'),
                            'status': 'pending',
                            'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
                        }
                        try:
                            self._save_pending_verification(rec)
                        except Exception:
                            _log('Failed to persist pending verification found in reply')
                        _log(f'Found verification challenge in reply {aid}; saved to pending_verifications.json')
                        # autosolve if allowed
                        auto = os.environ.get('MOLTBOOK_AUTO_SOLVE', '1')
                        if auto == '1':
                            ans = self._autosolve_challenge(v.get('challenge_text') or '')
                            if ans is not None:
                                formatted = f"{ans:.2f}"
                                _log(f'Attempting auto-verify for reply with answer {formatted} for code {v.get("verification_code")}')
                                subr = self._try_post('/verify', {'verification_code': v.get('verification_code'), 'answer': formatted}, timeout=15)
                                if subr and getattr(subr, 'status_code', None) in (200,201):
                                    _log(f'Auto-verify succeeded for reply code {v.get("verification_code")}')
                                    rec['status'] = 'succeeded'
                                    rec['answer'] = formatted
                                    rec['response'] = getattr(subr, 'text', '')
                                    try:
                                        self._save_pending_verification(rec)
                                    except Exception:
                                        _log('Failed to update pending_verification record after success for reply')
                                else:
                                    _log(f'Auto-verify attempt failed for reply: {getattr(subr, "status_code", None)} {getattr(subr, "text", "")[:300]}')
                                    rec['status'] = 'attempted'
                                    rec['attempt_response'] = getattr(subr, 'text', '')
                                    try:
                                        self._save_pending_verification(rec)
                                    except Exception:
                                        _log('Failed to update pending_verification record after attempt for reply')
                            else:
                                _log('Auto-solver could not derive a confident numeric answer for reply challenge; left pending')

                # persist seen replies for this comment
                seen_map[cid] = list(seen_replies)

            if new_alerts:
                monitored['comments'] = seen_map
                self._save_monitored(monitored)
                # notify via notifier if present
                if notifier:
                    for a in new_alerts:
                        try:
                            notifier.notify(a)
                        except Exception:
                            _log('Notifier failed for alert')
                else:
                    _log(f'monitor_replies: {len(new_alerts)} new replies detected')
            else:
                _log('monitor_replies: no new replies')
        except Exception as e:
            _log(f'monitor_replies failed: {e}')


class DraftManager:
    def __init__(self, path: str = DRAFTS_PATH):
        self.path = path
        self._load()

    def _load(self):
        try:
            with open(self.path, 'r', encoding='utf8') as f:
                self.drafts = json.load(f)
        except Exception:
            self.drafts = []

    def _save(self):
        with open(self.path, 'w', encoding='utf8') as f:
            json.dump(self.drafts, f, indent=2, ensure_ascii=False)

    def list(self) -> List[Dict]:
        self._load()
        return self.drafts

    def add(self, title: str, body: str, tags: Optional[List[str]] = None, visibility: str = 'private') -> int:
        self._load()
        new_id = (max([d.get('id', 0) for d in self.drafts]) + 1) if self.drafts else 1
        draft = {
            'id': new_id,
            'title': title,
            'body': body,
            'tags': tags or [],
            'visibility': visibility,
            'created_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }
        self.drafts.append(draft)
        self._save()
        _log(f"Draft {new_id} created: {title}")
        return new_id

    def get(self, draft_id: int) -> Optional[Dict]:
        self._load()
        for d in self.drafts:
            if int(d.get('id')) == int(draft_id):
                return d
        return None

    def remove(self, draft_id: int) -> bool:
        self._load()
        orig = len(self.drafts)
        self.drafts = [d for d in self.drafts if int(d.get('id')) != int(draft_id)]
        changed = len(self.drafts) != orig
        if changed:
            self._save()
            _log(f"Draft {draft_id} removed")
        return changed


class TelegramNotifier:
    def __init__(self):
        self.token = os.environ.get('NANOBOT_TELEGRAM_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID') or os.environ.get('NANOBOT_TELEGRAM_CHAT_ID')

    def available(self) -> bool:
        return bool(self.token and self.chat_id)

    def notify(self, text: str):
        if not self.available():
            _log('Telegram notifier not configured; skipping notify')
            return False
        url = f'https://api.telegram.org/bot{self.token}/sendMessage'
        payload = {'chat_id': self.chat_id, 'text': text}
        try:
            r = requests.post(url, json=payload, timeout=10)
            r.raise_for_status()
            _log('Sent Telegram notification')
            return True
        except Exception as e:
            _log(f'Failed to send Telegram notification: {e}')
            return False


def add_draft(title: str, body: str, tags: Optional[List[str]] = None, visibility: str = 'private') -> Dict:
    """Helper to add a draft programmatically and return the draft dict."""
    dm = DraftManager()
    new_id = dm.add(title=title, body=body, tags=tags, visibility=visibility)
    return dm.get(new_id)

# Simple CLI usage
LURK_STATE = os.path.join(DATA_DIR, 'lurk_state.json')


def _load_lurk_state():
    try:
        with open(LURK_STATE, 'r', encoding='utf8') as f:
            s = json.load(f)
            # Normalize to seen-id lists (supports numeric ids and UUIDs)
            s.setdefault('public_seen', [])
            s.setdefault('api_seen', [])
            return s
    except Exception:
        return {'public_seen': [], 'api_seen': []}


def _save_lurk_state(state: dict):
    try:
        with open(LURK_STATE, 'w', encoding='utf8') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        _log(f'Failed to save lurk state: {e}')


def _extract_item_id(item: dict) -> Optional[str]:
    """Heuristically extract an identifier from an item. Returns string or None."""
    if not item or not isinstance(item, dict):
        return None
    # common keys
    for k in ('id', 'post_id', 'message_id', 'postId', 'id_str', 'uuid', 'uid'):
        if k in item and item.get(k) is not None:
            return str(item.get(k))
    # fallback: any key that endswith 'id' or contains 'uuid'
    for k, v in item.items():
        lk = k.lower()
        if (lk.endswith('id') or 'uuid' in lk) and v is not None:
            return str(v)
    return None


def lurk_public(dm: DraftManager, notifier: TelegramNotifier):
    """Fetch public posts (best-effort) and create local drafts for new items. Handles numeric IDs and UUIDs.
    This version forces UTF-8-safe conversions to avoid Windows encoding errors when writing drafts.
    """
    state = _load_lurk_state()
    seen = set(state.get('public_seen', []))
    url = f"{API_BASE}/posts"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        try:
            data = r.json()
        except Exception:
            data = None
        # Expecting a list of posts; adapt as needed
        posts = data if isinstance(data, list) else (data.get('posts', []) if isinstance(data, dict) else [])
        added = 0
        for p in posts:
            pid = _extract_item_id(p) or ''
            if pid and pid in seen:
                continue
            title = p.get('title') or (p.get('body')[:80] + '...' if p.get('body') else (json.dumps(p, ensure_ascii=False)[:80] + '...'))
            body = p.get('body') or json.dumps(p, ensure_ascii=False)
            # Ensure string types and UTF-8-safe
            if isinstance(title, bytes):
                title = title.decode('utf8', errors='replace')
            if isinstance(body, bytes):
                body = body.decode('utf8', errors='replace')
            title = title.encode('utf8', errors='replace').decode('utf8')
            body = body.encode('utf8', errors='replace').decode('utf8')
            new_id = dm.add(title, body, tags=p.get('tags') or [], visibility=p.get('visibility', 'private'))
            _log(f'Public lurk: created draft {new_id} from post {pid}')
            added += 1
            if pid:
                seen.add(pid)
        if added:
            state['public_seen'] = list(seen)
            _save_lurk_state(state)
            notifier.notify(f'Lurk: added {added} new public drafts')
        else:
            _log('Lurk public: no new posts')
    except Exception as e:
        _log(f'Public lurk failed: {e}')


def lurk_api(dm: DraftManager, notifier: TelegramNotifier, client: MoltbookClient):
    """Poll API endpoints (DMs/mentions) and create drafts for new items. Requires valid API key. Handles numeric IDs and UUIDs."""
    state = _load_lurk_state()
    seen = set(state.get('api_seen', []))
    try:
        items = client.fetch_posts()
        if not items:
            _log('Lurk api: no items returned from API fetch')
            return
        added = 0
        for m in items:
            mid = _extract_item_id(m) or ''
            if mid and mid in seen:
                continue
            # Heuristic title/body extraction
            title = m.get('title') or m.get('subject') or (m.get('body')[:80] + '...' if m.get('body') else (json.dumps(m)[:80] + '...'))
            body = m.get('body') or m.get('message') or json.dumps(m)
            new_id = dm.add(title, body, tags=m.get('tags') or [], visibility=m.get('visibility', 'private'))
            _log(f'API lurk: created draft {new_id} from item {mid}')
            added += 1
            if mid:
                seen.add(mid)
        if added:
            state['api_seen'] = list(seen)
            _save_lurk_state(state)
            notifier.notify(f'Lurk: added {added} new API drafts')
        else:
            _log('Lurk api: no new items')
    except Exception as e:
        _log(f'API lurk failed: {e}')


if __name__ == '__main__':
    import argparse
    # lightweight cron helper is available in cron_helper.py
    try:
        from cron_helper import ensure_cron_meta, list_cron_meta, remove_cron_meta
    except Exception:
        ensure_cron_meta = None
        list_cron_meta = None
        remove_cron_meta = None

    p = argparse.ArgumentParser()
    p.add_argument('op', choices=['heartbeat', 'list', 'send', 'post', 'list-drafts', 'approve', 'deny', 'lurk', 'show-draft', 'monitor', 'cron-set', 'cron-list', 'cron-remove'])
    p.add_argument('--user', help='user id for send')
    p.add_argument('--msg', help='message body for send')
    p.add_argument('--title', help='post title')
    p.add_argument('--body', help='post body')
    p.add_argument('--tags', nargs='*', help='tags')
    p.add_argument('--visibility', default='private', help='post visibility')
    p.add_argument('--id', type=int, help='draft id for approve/deny')
    p.add_argument('--mode', choices=['public', 'api', 'hybrid'], default='public', help='lurk mode: public, api, or hybrid')
    p.add_argument('--cron-name', help='cron meta name')
    p.add_argument('--cron-expr', help='cron expression (e.g. "0 */4 * * *")')
    p.add_argument('--cron-jobid', help='external cron job id (optional)')
    p.add_argument('--cron-cmd', help='command or description for the cron job')
    args = p.parse_args()

    dm = DraftManager()
    notifier = TelegramNotifier()

    # existing ops that require API key
    key = load_api_key()
    if args.op in ('heartbeat', 'list', 'send', 'approve', 'monitor') and not key:
        print('No api key found. Run register_moltbook.ps1 or set MOLTBOOK_API_KEY in env before running this operation.')
        raise SystemExit(1)

    client = None
    if key:
        try:
            client = MoltbookClient(api_key=key)
        except Exception as e:
            _log(f'Failed to create Moltbook client: {e}')
            client = None

    if args.op == 'heartbeat':
        if not client:
            raise SystemExit(2)
        print(client.heartbeat())

    elif args.op == 'list':
        if not client:
            raise SystemExit(2)
        print(client.list_dms())

    elif args.op == 'send':
        if not client:
            raise SystemExit(2)
        if not args.user or not args.msg:
            print('send requires --user and --msg')
            raise SystemExit(2)
        print(client.send_dm(args.user, args.msg))

    elif args.op == 'post':
        if not args.title or not args.body:
            print('post requires --title and --body')
            raise SystemExit(2)
        new_id = dm.add(args.title, args.body, tags=args.tags, visibility=args.visibility)
        # Notify owner via Telegram (if configured) with approve instructions
        msg = f"Draft {new_id} created: {args.title}\nApprove: python skill_moltbook.py approve --id {new_id}"
        if notifier.available():
            notifier.notify(msg)
        else:
            _log('Telegram not configured; owner must run approve command manually')

    elif args.op == 'list-drafts':
        for d in dm.list():
            print(f"{d.get('id')}: {d.get('title')} ({d.get('visibility')}) created {d.get('created_at')}")

    elif args.op == 'show-draft':
        if not args.id:
            print('show-draft requires --id')
            raise SystemExit(2)
        d = dm.get(args.id)
        if not d:
            print('draft not found')
            raise SystemExit(3)
        print(json.dumps(d, indent=2, ensure_ascii=False))

    elif args.op == 'approve':
        if not args.id:
            print('approve requires --id')
            raise SystemExit(2)
        draft = dm.get(args.id)
        if not draft:
            print('draft not found')
            raise SystemExit(3)
        # create post via API
        try:
            resp = client.create_post(draft.get('title'), draft.get('body'), tags=draft.get('tags'), visibility=draft.get('visibility'))
            _log(f"Posted draft {args.id} to Moltbook: {resp}")
            dm.remove(args.id)
            # append memory note
            try:
                mem_path = os.path.join(os.path.dirname(HERE), 'memory', 'MEMORY.md')
                note = f"\n- Posted Moltbook draft {args.id} ({draft.get('title')}) on {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}\n"
                with open(mem_path, 'a', encoding='utf8') as m:
                    m.write(note)
                _log('Appended MEMORY.md note')
            except Exception as e:
                _log(f'Failed to append MEMORY.md: {e}')
            print('Post created successfully')
        except Exception as e:
            _log(f'Failed to create post: {e}')
            raise

    elif args.op == 'deny':
        if not args.id:
            print('deny requires --id')
            raise SystemExit(2)
        ok = dm.remove(args.id)
        if ok:
            _log(f'Draft {args.id} denied/removed')
        else:
            print('draft not found')

    elif args.op == 'lurk':
        mode = args.mode
        _log(f'Starting lurk in {mode} mode')
        if mode in ('public', 'hybrid'):
            lurk_public(dm, notifier)
        if mode in ('api', 'hybrid'):
            if not client:
                _log('No API client available; skipping API lurk')
            else:
                lurk_api(dm, notifier, client)

    elif args.op == 'cron-set':
        if not ensure_cron_meta:
            print('cron helper not available')
            raise SystemExit(2)
        if not args.cron_name or not args.cron_expr:
            print('cron-set requires --cron-name and --cron-expr')
            raise SystemExit(2)
        changed = ensure_cron_meta(args.cron_name, args.cron_expr, job_id=args.cron_jobid, command=args.cron_cmd)
        print('cron meta updated' if changed else 'cron meta unchanged')

    elif args.op == 'cron-list':
        if not list_cron_meta:
            print('cron helper not available')
            raise SystemExit(2)
        print(json.dumps(list_cron_meta(), indent=2))

    elif args.op == 'cron-remove':
        if not remove_cron_meta:
            print('cron helper not available')
            raise SystemExit(2)
        if not args.cron_name:
            print('cron-remove requires --cron-name')
            raise SystemExit(2)
        ok = remove_cron_meta(args.cron_name)
        print('removed' if ok else 'not found')

    elif args.op == 'monitor':
        # one-shot monitor invocation
        if not client:
            _log('No API client available; cannot run monitor')
            raise SystemExit(2)
        try:
            client.monitor_replies(notifier=notifier if notifier.available() else None)
        except Exception as e:
            _log(f'Monitor op failed: {e}')
            raise
