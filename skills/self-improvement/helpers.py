import os
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)
LESSONS_FILE = os.path.join(BASE_DIR, 'LESSONS-LEARNED.md')
MEM_REF = os.path.join(BASE_DIR, 'data', 'lessons_refs.log')


def append_lesson(title: str, body: str):
    ts = datetime.utcnow().isoformat()
    entry = f"## {title} - {ts}\n\n{body}\n\n"
    with open(LESSONS_FILE, 'a', encoding='utf-8') as f:
        f.write(entry)
    with open(MEM_REF, 'a', encoding='utf-8') as mf:
        mf.write(f"{ts} | {title}\n")
    return ts
