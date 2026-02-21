"""
self-improvement/ingest.py
Aggregator: consume raw JSON artifacts from configured input directories (moltbook, news_ingestor, deadinternet), summarize, optionally index, and archive/delete processed files.

Usage: configure input_dirs in config.json and run:
    python ingest.py --once
or run worker mode:
    python ingest.py --worker

This script looks for JSON files in each input directory, processes them, and moves processed files to an archive/ subfolder.
"""
from __future__ import annotations
import os
import sys
import time
import json
import shutil
import argparse
from datetime import datetime
from pathlib import Path
from summarizer import summarize_post

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CONFIG_PATH = BASE_DIR / "config.json"
SAVED_THREADS = DATA_DIR / "saved_threads.md"
PENDING_VERIF = DATA_DIR / "pending_verifications.json"
STARTUP_REPORT = DATA_DIR / "startup_report.txt"
LESSONS = BASE_DIR / "LESSONS-LEARNED.md"


def load_config():
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing config: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding='utf-8-sig'))


def ensure_data():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SAVED_THREADS.exists():
        SAVED_THREADS.write_text("", encoding='utf-8')
    if not PENDING_VERIF.exists():
        PENDING_VERIF.write_text("[]", encoding='utf-8')
    if not LESSONS.exists():
        LESSONS.write_text("# Lessons Learned\n\n", encoding='utf-8')


def append_lesson(title: str, body: str):
    ts = datetime.utcnow().isoformat()
    entry = f"## {title} - {ts}\n\n{body}\n\n"
    # append to LESSONS-LEARNED.md
    with open(LESSONS, 'a', encoding='utf-8') as f:
        f.write(entry)
    # also write a tiny memory reference file for manual import into MEMORY.md by the human
    mem_ref = BASE_DIR / "data" / "lessons_refs.log"
    with open(mem_ref, 'a', encoding='utf-8') as mf:
        mf.write(f"{ts} | {title}\n")


def save_summary_block(summary: dict):
    header = json.dumps({"id": summary.get('id'), "url": summary.get('url'), "source": summary.get('source'), "saved": datetime.utcnow().isoformat()})
    block = f"----\n{header}\nTitle: {summary.get('title')}\nHighlights:\n"
    for h in summary.get('highlights', []):
        block += f"- {h}\n"
    block += f"Sample: {summary.get('sample_quote','')}\n----\n\n"
    SAVED_THREADS.write_text(SAVED_THREADS.read_text(encoding='utf-8') + block, encoding='utf-8')


def process_input_dir(dir_path: Path, cfg: dict, report: dict):
    dir_path = Path(dir_path)
    if not dir_path.exists():
        report['errors'].append(f"input_not_found:{dir_path}")
        return
    raw_files = sorted([p for p in dir_path.glob('*.json') if p.is_file()])
    archive_dir = dir_path / 'processed'
    archive_dir.mkdir(parents=True, exist_ok=True)
    processed = 0
    for f in raw_files[: cfg.get('per_source_limit', 50)]:
        try:
            obj = json.loads(f.read_text(encoding='utf-8'))
            # try common field names
            pid = obj.get('id') or obj.get('post_id') or obj.get('link') or obj.get('url') or obj.get('title')
            title = obj.get('title') or obj.get('headline') or ''
            body = obj.get('body') or obj.get('snippet') or obj.get('content') or ''
            source = obj.get('source') or obj.get('source_name') or dir_path.name
            summarized = summarize_post({'title': title, 'body': body})
            summarized['id'] = pid
            summarized['url'] = obj.get('url') or obj.get('link') or ''
            summarized['source'] = source
            if cfg.get('auto_save', True):
                save_summary_block(summarized)
            if cfg.get('index_on'):
                try:
                    from indexer import add_documents
                    add_documents([{'id': pid, 'text': body or title}])
                except Exception as e:
                    append_lesson('index_error', str(e))
            # move file to processed
            shutil.move(str(f), str(archive_dir / f.name))
            processed += 1
        except Exception as ex:
            append_lesson('processing_error', f"{f} => {ex}")
            report['errors'].append(f"{f.name}:{str(ex)}")
    report['processed'] = report.get('processed', 0) + processed


def run_once():
    cfg = load_config()
    ensure_data()
    input_dirs = cfg.get('input_dirs', [])
    report = {'started': datetime.utcnow().isoformat(), 'inputs': [], 'errors': [], 'processed': 0}
    for d in input_dirs:
        entry = {'dir': d, 'processed': 0, 'errors': []}
        try:
            process_input_dir(Path(d), cfg, entry)
        except Exception as ex:
            entry['errors'].append(str(ex))
        report['inputs'].append(entry)
    report['finished'] = datetime.utcnow().isoformat()
    STARTUP_REPORT.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def worker_loop(cadence: int):
    while True:
        r = run_once()
        print(json.dumps(r, indent=2))
        time.sleep(cadence)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', action='store_true', help='Run as a worker loop')
    parser.add_argument('--once', action='store_true', help='Run once and exit')
    args = parser.parse_args()
    if args.worker:
        cfg = load_config()
        cadence = cfg.get('cadence_seconds', 14400)  # default 4 hours
        worker_loop(cadence)
    else:
        r = run_once()
        print(json.dumps(r, indent=2))
