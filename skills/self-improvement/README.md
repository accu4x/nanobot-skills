self-improvement skill

Purpose
- Ingests Moltbook posts via the Moltbook API, summarizes them, and optionally indexes them with FAISS for retrieval.
- Config-driven: submolts, cadence, autosave, indexing, and other behaviors are set in config.json.

Files
- ingest.py: main runner. Reads config.json and polls Moltbook for recent posts.
- summarizer.py: converts post dicts to concise summaries and extracts 2-3 highlights.
- indexer.py: optional FAISS indexer (requires faiss and sentence-transformers). Disabled if missing.
- config.json: defaults for submolts, cadence, and options.
- data/: runtime artifacts (saved_threads.md, startup_report.txt, pending_verifications.json)

Usage
1) Set environment variables:
   - MOLTBOOK_API_KEY (if you want to use authenticated endpoints)
   - MOLTBOOK_API_BASE (optional, defaults to https://www.moltbook.com/api/v1)
2) Edit config.json to add/remove submolts or toggle index_on.
3) Run once:
   python ingest.py
4) To run on a schedule, install cron/Task Scheduler pointing to ingest.py (cron_install.ps1 provided).

Notes
- This skill uses the Moltbook API only. It does not run headless browsers or scrape client-rendered pages.
- It respects rate limits (basic checks) and writes pending verification challenges to data/pending_verifications.json.
- Do not store secrets in saved threads; redact sensitive links via config.json redact_list.

Contribution
- Make changes, test locally, and create a repo when ready. If you provide a transient PAT as an env var I can prepare a local git commit and push, but by default the skill remains local.
