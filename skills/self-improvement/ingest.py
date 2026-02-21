"""
self-improvement/ingest.py
Moltbook-API-only polling/ingest runner. Reads config.json and polls Moltbook for new posts
in configured submolts. Produces summaries via summarizer.py, saves to data/saved_threads.md,
logs startup_report.txt, and records pending verification challenges.

Usage: set environment variable MOLTBOOK_API_KEY and run:
    python ingest.py

This script is intentionally dependency-light (requests only) and defensive about rate limits.
"""
from __future__ import annotations
import os
import time
import json
import requests
from datetime import datetime
from pathlib import Path
from summarizer import summarize_post

# Optional RSS parsing using feedparser
try:
    import feedparser
    HAS_FEEDPARSER = True
except Exception:
    HAS_FEEDPARSER = False

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = BASE_DIR / "config.json"
SAVED_THREADS = DATA_DIR / "saved_threads.md"
PENDING_VERIF = DATA_DIR / "pending_verifications.json"
STARTUP_REPORT = DATA_DIR / "startup_report.txt"

API_BASE = os.getenv("MOLTBOOK_API_BASE", "https://www.moltbook.com/api/v1")
API_KEY = os.getenv("MOLTBOOK_API_KEY")

HEADERS = {"Content-Type": "application/json"}
if API_KEY:
    HEADERS["Authorization"] = f"Bearer {API_KEY}"


def load_config():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing config: {CONFIG_PATH}")
    # handle files with BOM by using utf-8-sig
    return json.loads(CONFIG_PATH.read_text(encoding='utf-8-sig'))


def ensure_data():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SAVED_THREADS.exists():
        SAVED_THREADS.write_text("", encoding='utf-8')
    if not PENDING_VERIF.exists():
        PENDING_VERIF.write_text("[]", encoding='utf-8')


def fetch_posts_for_submolt(submolt: str, per_page: int = 20):
    """Fetch recent posts for a community/submolt. Returns list of post dicts or [] on error."""
    # Attempt common endpoints; some Moltbook installs use /posts?community=...
    try:
        url = f"{API_BASE}/posts?community={submolt}&limit={per_page}"
        r = requests.get(url, headers=HEADERS, timeout=15)
        if r.status_code == 429:
            retry = int(r.headers.get('Retry-After') or 60)
            return {"rate_limited": True, "retry": retry}
        r.raise_for_status()
        payload = r.json()
        # payload may be wrapped; try to find list under common keys
        if isinstance(payload, dict):
            for key in ("posts", "data", "result", "items"):
                if key in payload and isinstance(payload[key], list):
                    return payload[key]
            # sometimes API returns single post under 'post'
            if isinstance(payload.get('post'), dict):
                return [payload['post']]
        if isinstance(payload, list):
            return payload
    except Exception as e:
        return {"error": str(e)}
    return []


def fetch_rss_feed(url: str):
    if not HAS_FEEDPARSER:
        return {"error": "feedparser not installed"}
    try:
        parsed = feedparser.parse(url)
        if parsed.get('bozo'):
            # bozo indicates parse error but there may still be entries
            return {"error": str(parsed.get('bozo_exception', 'parse error'))}
        entries = []
        for e in parsed.entries:
            entries.append({
                'id': e.get('id') or e.get('link'),
                'title': e.get('title'),
                'body': e.get('summary') or e.get('content', [{'value': ''}])[0].get('value',''),
                'url': e.get('link')
            })
        return entries
    except Exception as ex:
        return {"error": str(ex)}


def save_summary_block(summary: dict):
    # append a structured block to saved_threads.md
    header = json.dumps({"id": summary.get('id'), "url": summary.get('url'), "community": summary.get('community'), "saved": datetime.utcnow().isoformat()})
    block = f"----\n{header}\nTitle: {summary.get('title')}\nHighlights:\n"
    for h in summary.get('highlights', []):
        block += f"- {h}\n"
    block += f"Sample: {summary.get('sample_quote','')}\n----\n\n"
    SAVED_THREADS.write_text(SAVED_THREADS.read_text(encoding='utf-8') + block, encoding='utf-8')


def append_pending_verification(item: dict):
    arr = json.loads(PENDING_VERIF.read_text(encoding='utf-8') or "[]")
    arr.append(item)
    PENDING_VERIF.write_text(json.dumps(arr, indent=2), encoding='utf-8')


def run_once():
    cfg = load_config()
    ensure_data()
    submolts = cfg.get('submolts', [])
    per_submolt = cfg.get('per_submolt', 10)
    report = {"started": datetime.utcnow().isoformat(), "checked": []}

    # First, poll submolts via Moltbook API
    for sm in submolts:
        entry = {"submolt": sm, "fetched": 0, "errors": []}
        res = fetch_posts_for_submolt(sm, per_page=per_submolt)
        if isinstance(res, dict) and res.get('rate_limited'):
            entry['errors'].append(f"rate_limited_retry_after={res.get('retry')}")
            report['checked'].append(entry)
            # respect rate limit: stop this run
            break
        if isinstance(res, dict) and res.get('error'):
            entry['errors'].append(res.get('error'))
            report['checked'].append(entry)
            continue
        posts = res or []
        entry['fetched'] = len(posts)
        for p in posts:
            try:
                # some posts may be wrapped
                post = p
                # derive canonical url and id
                pid = post.get('id') or post.get('_id') or post.get('post_id')
                url = post.get('url') or post.get('permalink') or f"https://www.moltbook.com/posts/{pid}"
                summarized = summarize_post(post)
                summarized['id'] = pid
                summarized['url'] = url
                summarized['community'] = sm
                if cfg.get('auto_save', True):
                    save_summary_block(summarized)
                # check for verification challenges in post metadata (site-specific)
                if post.get('requires_verification') or post.get('verification_challenge'):
                    append_pending_verification({"post_id": pid, "community": sm, "found_at": datetime.utcnow().isoformat()})
                # Optional indexing handled by indexer if configured (import here to avoid heavy deps at module import)
                if cfg.get('index_on'):
                    try:
                        from indexer import add_documents
                        add_documents([{"id": pid, "text": summarized.get('body','') or post.get('body','') or post.get('content','')}])
                    except Exception:
                        pass
            except Exception as ex:
                entry['errors'].append(str(ex))
        report['checked'].append(entry)
        time.sleep(cfg.get('gap_seconds', 1))

    # Next, poll RSS feeds if configured
    rss_list = cfg.get('rss_feeds', [])
    if rss_list:
        rss_entry = {"rss_polled": len(rss_list), "processed": 0, "errors": []}
        for rurl in rss_list:
            try:
                res = fetch_rss_feed(rurl)
                if isinstance(res, dict) and res.get('error'):
                    rss_entry['errors'].append({rurl: res.get('error')})
                    continue
                entries = res or []
                for e in entries:
                    try:
                        eid = e.get('id') or e.get('url')
                        summarized = summarize_post({'title': e.get('title'), 'body': e.get('body')})
                        summarized['id'] = eid
                        summarized['url'] = e.get('url')
                        summarized['community'] = 'rss'
                        if cfg.get('auto_save', True):
                            save_summary_block(summarized)
                        if cfg.get('index_on'):
                            try:
                                from indexer import add_documents
                                add_documents([{"id": eid, "text": summarized.get('body','')}])
                            except Exception:
                                pass
                        rss_entry['processed'] += 1
                    except Exception as ex:
                        rss_entry['errors'].append({"entry_error": str(ex)})
            except Exception as ex:
                rss_entry['errors'].append({rurl: str(ex)})
            time.sleep(1)
        report['checked'].append(rss_entry)

    report['finished'] = datetime.utcnow().isoformat()
    STARTUP_REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    r = run_once()
    print(json.dumps(r, indent=2))
