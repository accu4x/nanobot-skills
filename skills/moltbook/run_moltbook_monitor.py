#!/usr/bin/env python3
"""
Run a continuous (configurable-duration) monitor loop for the Moltbook skill.
This script repeatedly calls client.monitor_replies and the lurk_api/lurk_public
helpers to pick up new posts, replies and verification challenges, persisting
records to data/pending_verifications.json and events.log. If Telegram env vars
are configured it will send notifications.

Usage: python run_moltbook_monitor.py [--duration SECONDS] [--interval SECONDS]

By default this runs for 120 seconds and polls every 15 seconds. Set duration=0 to run indefinitely.
"""
import os
import time
import argparse
from skill_moltbook import MoltbookClient, DraftManager, TelegramNotifier, lurk_api, lurk_public, _log

p = argparse.ArgumentParser()
p.add_argument('--duration', type=int, default=120, help='Total run time in seconds (0 = run forever)')
p.add_argument('--interval', type=int, default=15, help='Polling interval in seconds')
p.add_argument('--mode', choices=['public','api','hybrid'], default='api', help='lurk mode to run each iteration')
args = p.parse_args()

start = time.time()
end_time = None if args.duration == 0 else (start + args.duration)

# Prepare components
key = None
try:
    # Prefer env var
    key = os.environ.get('MOLTBOOK_API_KEY')
    if not key:
        # try credentials path used by skill
        from skill_moltbook import CRED_PATH
        if os.path.exists(CRED_PATH):
            try:
                import json
                j = json.load(open(CRED_PATH,'r',encoding='utf8'))
                key = j.get('api_key')
            except Exception:
                key = None
except Exception:
    key = None

if not key:
    _log('No Moltbook API key found in MOLTBOOK_API_KEY or credentials file; monitor cannot run')
    raise SystemExit(2)

try:
    client = MoltbookClient(api_key=key)
except Exception as e:
    _log(f'Failed to create Moltbook client: {e}')
    raise

notifier = TelegramNotifier()
if notifier.available():
    _log('Telegram notifier is configured and will be used')
else:
    _log('Telegram notifier not configured; notifications will be logged only')

# Ensure pending file exists
try:
    client._ensure_pending_file()
except Exception as e:
    _log(f'Failed to ensure pending file: {e}')

# Draft manager for lurk
from skill_moltbook import DraftManager

dm = DraftManager()

_loop_count = 0
try:
    while True:
        _loop_count += 1
        _log(f'Monitor loop iteration {_loop_count} start')
        try:
            # Check for replies to our comments (may create pending_verifications and send notifications)
            client.monitor_replies(notifier=notifier if notifier.available() else None)
        except Exception as e:
            _log(f'Error during monitor_replies: {e}')
        try:
            # Lurk depending on mode
            if args.mode in ('public','hybrid'):
                lurk_public(dm, notifier)
            if args.mode in ('api','hybrid'):
                lurk_api(dm, notifier, client)
        except Exception as e:
            _log(f'Error during lurk: {e}')

        # Check elapsed
        if end_time and time.time() >= end_time:
            _log('Duration reached; exiting monitor loop')
            break
        time.sleep(max(1, args.interval))
except KeyboardInterrupt:
    _log('Monitor interrupted by user')

_log('Monitor stopped')
