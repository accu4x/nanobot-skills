#!/usr/bin/env python3
"""
create_daily_summary.py

Create a draft post from the latest hockey news CSV and save it as a draft via skill_moltbook.py post.
This script is safe to run locally. It does not contain or require secrets.

Usage:
  python create_daily_summary.py --csv "path/to/Latest_Hockey_Card_News_*.csv" --top 5

Outputs:
  - Creates a draft via: python skill_moltbook.py post --title "..." --body "..."
  - Prints created draft info to stdout

Note:
  - Ensure you run this from the moltbook skill folder, or set the SKILL_DIR env var to the skill path.
  - This script only creates drafts (owner-mediated posting). You must approve drafts to publish.
"""

import os
import sys
import argparse
import glob
import pandas as pd
from datetime import datetime
import subprocess
import json

DEFAULT_MEDIA_DIR = r"C:\Users\hn2_f\.nanobot\workspace\media"
DEFAULT_SKILL_DIR = r"C:\Users\hn2_f\.nanobot\workspace\skills\moltbook"


def find_latest_csv(pattern=None, media_dir=DEFAULT_MEDIA_DIR):
    if pattern:
        paths = glob.glob(pattern)
    else:
        paths = glob.glob(os.path.join(media_dir, "Latest_Hockey_Card_News_*.csv"))
    if not paths:
        return None
    paths.sort(key=os.path.getmtime, reverse=True)
    return paths[0]


def build_summary_from_csv(csv_path, top=5):
    df = pd.read_csv(csv_path)
    if df.empty:
        return None
    # pick first 'top' rows as summary
    top_n = df.head(top)
    lines = []
    for i, row in top_n.iterrows():
        title = row.get('title') or row.get('headline') or ''
        source = row.get('source') or ''
        url = row.get('url') or row.get('link') or ''
        lines.append(f"- {title} ({source})\n  {url}")
    body = "\n".join(lines)
    return body


def run_post(skill_dir, title, body, tags=None, visibility="private"):
    # Build command to call skill_moltbook.py post
    skill_py = os.path.join(skill_dir, "skill_moltbook.py")
    if not os.path.exists(skill_py):
        raise FileNotFoundError(f"skill_moltbook.py not found at {skill_py}")

    cmd = [sys.executable, skill_py, "post", "--title", title, "--body", body, "--visibility", visibility]
    if tags:
        for t in tags:
            cmd.extend(["--tags", t])

    # Run the command and capture stdout/stderr
    print("Running:", " ".join(cmd[:6]), "... [body omitted]")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    out = proc.stdout.strip()
    err = proc.stderr.strip()
    if proc.returncode != 0:
        print("Error creating draft:\n", err)
        return None
    # skill_moltbook.py should print a JSON snippet or plain text with draft id; attempt to parse JSON
    try:
        j = json.loads(out)
        return j
    except Exception:
        return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', help='Path to news CSV (glob ok). If omitted, uses latest in media dir.')
    p.add_argument('--top', type=int, default=5, help='Number of top headlines to include')
    p.add_argument('--skill-dir', default=os.environ.get('SKILL_DIR', DEFAULT_SKILL_DIR))
    p.add_argument('--tags', nargs='*', default=['hockey','news'])
    args = p.parse_args()

    csv_path = find_latest_csv(args.csv)
    if not csv_path:
        print('No news CSV found. Give --csv or place files in media dir matching Latest_Hockey_Card_News_*.csv')
        sys.exit(1)

    print('Using CSV:', csv_path)
    body = build_summary_from_csv(csv_path, top=args.top)
    if not body:
        print('Failed to build summary from CSV')
        sys.exit(1)

    title = f"Daily Hockey Summary — {datetime.now().strftime('%Y-%m-%d')}"
    # Truncate body if too long for CLI args by saving temporarily to a file and passing via stdin isn't implemented in skill_moltbook.py
    # We'll call the post command with the body inline; if shells choke, consider modifying skill_moltbook.post to accept --body-file

    res = run_post(args.skill_dir, title, body, tags=args.tags, visibility='private')
    print('Draft creation result:', res)


if __name__ == '__main__':
    main()
