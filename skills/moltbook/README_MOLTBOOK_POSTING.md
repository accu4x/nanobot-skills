Moltbook owner-mediated posting helpers

Files added:
- create_daily_summary.py  -- Create a draft post from the latest hockey news CSV and call skill_moltbook.py post
- notify_pending_drafts.py  -- Send a Telegram notification listing pending drafts and approve/deny commands

Usage notes:
- create_daily_summary.py will create a draft via skill_moltbook.py post. You must approve drafts using skill_moltbook.py approve --id <id> to publish.
- notify_pending_drafts.py requires NANOBOT_TELEGRAM_TOKEN and NANOBOT_TELEGRAM_CHAT_ID to be set in your environment to send notifications.

Scheduling examples (Windows scheduled task):
- Create daily draft at 08:00:
  schtasks /Create /SC DAILY /TN "HobbyHero Create Daily Draft" /TR "python C:\\Users\\hn2_f\\.nanobot\\workspace\\skills\\moltbook\\create_daily_summary.py" /ST 08:00

- Notify owner every hour about drafts (requires Telegram config):
  schtasks /Create /SC HOURLY /MO 1 /TN "HobbyHero Notify Drafts" /TR "python C:\\Users\\hn2_f\\.nanobot\\workspace\\skills\\moltbook\\notify_pending_drafts.py" /ST 09:00

Security & safety:
- Keep MOLTBOOK_API_KEY and NANOBOT_TELEGRAM_TOKEN local in %USERPROFILE%\\.config\\moltbook\\credentials.json or as env vars. Do not paste keys into chat.
- Posting is owner-mediated. Drafts are created automatically by create_daily_summary.py but the bot will only publish them after you run skill_moltbook.py approve --id <id>.

