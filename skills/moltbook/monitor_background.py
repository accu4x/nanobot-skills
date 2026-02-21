"""
Background monitor for Moltbook skill.
- Periodically calls MoltbookClient.monitor_replies() to detect replies and verification challenges.
- Watches data/pending_verifications.json for new entries and (if configured) sends Telegram notifications for new verification challenges.
- Runs indefinitely; intended to be launched as a detached/background process.
"""
import time
import os
import json
import sys
from skill_moltbook import MoltbookClient, DraftManager, TelegramNotifier, _log, DATA_DIR, EVENT_LOG, load_api_key

# Ensure pending file exists
pending_path = os.path.join(DATA_DIR, 'pending_verifications.json')
if not os.path.exists(pending_path):
    try:
        with open(pending_path, 'w', encoding='utf8') as f:
            json.dump([], f, ensure_ascii=False)
    except Exception as e:
        _log(f'monitor_background: failed to create pending_verifications.json: {e}')

# Create notifier
notifier = TelegramNotifier()
# Attempt to create client if API key available
api_key = load_api_key()
client = None
if api_key:
    try:
        client = MoltbookClient(api_key=api_key)
    except Exception as e:
        _log(f'monitor_background: failed to create MoltbookClient: {e}')
else:
    _log('monitor_background: no MOLTBOOK_API_KEY available; monitor_replies will be skipped')

# Track seen pending verification codes to avoid duplicate notifications
seen_codes = set()
try:
    with open(pending_path, 'r', encoding='utf8') as f:
        existing = json.load(f) or []
        for r in existing:
            code = r.get('verification_code') or json.dumps(r, ensure_ascii=False)
            seen_codes.add(str(code))
except Exception:
    seen_codes = set()

_log('monitor_background: starting monitor loop')

SLEEP = int(os.environ.get('MOLTBOOK_MONITOR_INTERVAL', '30'))

while True:
    try:
        # Run the client's monitor_replies which logs to EVENT_LOG and persists pending verifications
        if client:
            try:
                client.monitor_replies(notifier=notifier if notifier.available() else None)
            except Exception as e:
                _log(f'monitor_background: monitor_replies failed: {e}')
        else:
            _log('monitor_background: skipping monitor_replies (no API client)')

        # Check pending_verifications.json for new entries
        try:
            with open(pending_path, 'r', encoding='utf8') as f:
                items = json.load(f) or []
        except Exception as e:
            _log(f'monitor_background: failed to read pending_verifications.json: {e}')
            items = []

        for it in items:
            code = it.get('verification_code') or json.dumps(it, ensure_ascii=False)
            code_s = str(code)
            if code_s in seen_codes:
                continue
            seen_codes.add(code_s)
            # New pending verification detected
            post_id = it.get('post_id') or it.get('comment_id') or 'unknown'
            challenge = it.get('challenge_text') or it.get('instructions') or ''
            msg = f"Moltbook pending verification detected: code={code_s}, post/comment={post_id}, challenge={challenge}"
            # Log locally (will append to events.log via _log)
            _log(f'monitor_background: {msg}')
            # Notify via Telegram if configured
            if notifier.available():
                try:
                    notifier.notify(msg)
                except Exception as e:
                    _log(f'monitor_background: Telegram notify failed: {e}')
            else:
                _log('monitor_background: Telegram notifier not configured; skipping Telegram notify')

    except Exception as e:
        _log(f'monitor_background: unexpected error: {e}')
    # Sleep then loop
    time.sleep(SLEEP)
