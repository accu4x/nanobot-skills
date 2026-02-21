#!/usr/bin/env python3
"""
notify_pending_drafts.py

Sends a Telegram notification summarizing pending drafts and includes approve/deny commands.
This updated version includes the full draft text (chunked to avoid Telegram message size limits).
Requires NANOBOT_TELEGRAM_TOKEN and NANOBOT_TELEGRAM_CHAT_ID to be set in the environment locally.

Usage:
  python notify_pending_drafts.py

Outputs:
  - Sends one or more Telegram messages to the configured chat with pending draft details and the full text.

Note: This script does not store or send any credentials. It reads drafts.json from the moltbook skill data folder.
"""

import os
import json
import requests
import textwrap

SKILL_DIR = r"C:\Users\hn2_f\.nanobot\workspace\skills\moltbook"
DRAFTS_PATH = os.path.join(SKILL_DIR, 'data', 'drafts.json')

TELEGRAM_TOKEN = os.environ.get('NANOBOT_TELEGRAM_TOKEN') or os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('NANOBOT_TELEGRAM_CHAT_ID') or os.environ.get('TELEGRAM_CHAT_ID')

# Max characters per Telegram message payload (keep a margin)
TELEGRAM_MAX_CHARS = 3800


def load_drafts():
    if not os.path.exists(DRAFTS_PATH):
        return []
    try:
        with open(DRAFTS_PATH, 'r', encoding='utf8') as f:
            return json.load(f)
    except Exception:
        return []


def chunk_text(s, size=TELEGRAM_MAX_CHARS):
    if not s:
        return [""]
    # Simple chunking on character boundaries
    return [s[i:i+size] for i in range(0, len(s), size)]


def build_messages(drafts):
    """
    Return a list of message strings to send to Telegram. Each draft may produce multiple messages if long.
    """
    if not drafts:
        return ['No pending drafts.']

    msgs = []
    header = 'Pending HobbyHeroBot drafts:'
    msgs.append(header)

    for d in drafts:
        draft_header = f"\nID {d['id']}: {d.get('title','(no title)')}"
        msgs.append(draft_header)
        # Include metadata line
        meta = []
        if d.get('tags'):
            meta.append('tags: ' + ','.join(d.get('tags')))
        meta.append(f"visibility: {d.get('visibility','private')}")
        meta_line = ' | '.join(meta)
        msgs.append(meta_line)

        # Approve/Deny instructions
        approve_line = f"Approve: python skill_moltbook.py approve --id {d['id']}"
        deny_line = f"Deny:    python skill_moltbook.py deny --id {d['id']}"
        msgs.append(approve_line)
        msgs.append(deny_line)

        # Draft body
        body = d.get('body','') or d.get('text','') or ''
        if body:
            chunks = chunk_text(body)
            for i, chunk in enumerate(chunks):
                # Prefix first chunk with a label
                prefix = 'Draft body:' if i == 0 else 'Continued:'
                msgs.append(f"{prefix}\n{chunk}")
        else:
            msgs.append('(no body)')

        # Separator
        msgs.append('-' * 40)

    # Now we may have many message pieces; combine small pieces to reduce number of API calls
    combined = []
    current = ''
    for part in msgs:
        if len(current) + len(part) + 1 < TELEGRAM_MAX_CHARS:
            if current:
                current += '\n' + part
            else:
                current = part
        else:
            combined.append(current)
            current = part
    if current:
        combined.append(current)

    return combined


def send_telegram_messages(messages):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print('Telegram creds not set. Set NANOBOT_TELEGRAM_TOKEN and NANOBOT_TELEGRAM_CHAT_ID to enable notifications.')
        return False
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'

    for msg in messages:
        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg}
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code != 200:
            print('Telegram send failed:', r.status_code, r.text)
            return False
    print('Telegram notification sent ({} messages)'.format(len(messages)))
    return True


def main():
    drafts = load_drafts()
    messages = build_messages(drafts)
    # Print a short summary locally
    print(f"Prepared {len(messages)} Telegram message(s) for {len(drafts)} draft(s).")
    # Optionally print the first message for quick inspection
    if messages:
        print('\n--- First message preview ---\n')
        print(messages[0][:1000])
        print('\n--- end preview ---\n')
    send_telegram_messages(messages)


if __name__ == '__main__':
    main()
