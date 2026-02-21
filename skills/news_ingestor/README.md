news_ingestor

Purpose
- Poll configured RSS feeds, extract article snippets, and write normalized raw JSON artifacts into data/raw_items/ for downstream consumers.

Files
- news_ingestor.py: main runner. Writes raw artifacts to data/raw_items/ and summary markdown to the workspace memory folder by default.
- data/raw_items/: contains raw per-item JSON files for other skills to consume. Files are named rss_{safe_id}.json.
- LOCAL_NOTES.md: local-only notes (do not push to GitHub).

Best practices
- Use LOCAL_NOTES.md for environment-specific paths or transient info; clear it before publishing.
- Ensure feed list in code or config is maintained and respects robots/terms.

Usage
- Run once: python news_ingestor.py
- The script will create data/raw_items/ if missing and write JSON files.

Output contract
- Raw JSON schema (minimal):
  {
    "id": "...",
    "source": "rss",
    "source_name": "thehockeywriters",
    "url": "...",
    "title": "...",
    "body": "...",
    "fetched_at": "ISO8601",
    "metadata": {...}
  }

