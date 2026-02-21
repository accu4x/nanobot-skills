"""
Cron helper for Moltbook skill
- Provides idempotent cron metadata persistence (cron_jobs.json) so scheduling is not duplicated
- Small CLI for listing/setting/removing cron meta entries

Usage (from the workspace):
  python cron_helper.py --list
  python cron_helper.py --set --name moltbook-lurker --expr "0 */4 * * *" --jobid 8b65df46 --cmd "python skill_moltbook.py monitor"
  python cron_helper.py --remove --name moltbook-lurker

This module does NOT itself call the gateway cron tool; it only persists and inspects cron metadata used by the Moltbook skill.
"""
import os
import json
import time
import argparse

HERE = os.path.dirname(__file__)
DATA_DIR = os.path.join(HERE, 'data')
CRON_META_PATH = os.path.join(DATA_DIR, 'cron_jobs.json')

os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.exists(CRON_META_PATH):
    try:
        with open(CRON_META_PATH, 'w', encoding='utf8') as f:
            json.dump({}, f, ensure_ascii=False)
    except Exception:
        pass


def _load_cron_meta():
    try:
        with open(CRON_META_PATH, 'r', encoding='utf8') as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cron_meta(meta: dict):
    try:
        with open(CRON_META_PATH, 'w', encoding='utf8') as f:
            json.dump(meta, f, indent=2)
        return True
    except Exception as e:
        print(f'Failed to save cron meta: {e}')
        return False


def ensure_cron_meta(name: str, cron_expr: str, job_id: str = None, command: str = None):
    """Ensure a canonical cron job record exists. Returns tuple (changed:bool, meta:dict)"""
    meta = _load_cron_meta()
    entry = meta.get(name)
    new_entry = {'cron_expr': cron_expr, 'job_id': job_id, 'command': command, 'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
    if entry == new_entry:
        return False, meta
    meta[name] = new_entry
    _save_cron_meta(meta)
    return True, meta


def remove_cron_meta(name: str):
    meta = _load_cron_meta()
    if name in meta:
        del meta[name]
        _save_cron_meta(meta)
        return True, meta
    return False, meta


def list_cron_meta():
    return _load_cron_meta()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--list', action='store_true', help='List cron meta entries')
    parser.add_argument('--set', action='store_true', help='Set/update a cron meta entry')
    parser.add_argument('--remove', action='store_true', help='Remove a cron meta entry')
    parser.add_argument('--name', help='Cron meta name')
    parser.add_argument('--expr', help='Cron expression')
    parser.add_argument('--jobid', help='External cron job id (optional)')
    parser.add_argument('--cmd', help='Command/description for the cron job (optional)')
    args = parser.parse_args()

    if args.list:
        meta = list_cron_meta()
        print(json.dumps(meta, indent=2))
    elif args.set:
        if not args.name or not args.expr:
            print('Must provide --name and --expr to set an entry')
            raise SystemExit(2)
        changed, meta = ensure_cron_meta(args.name, args.expr, job_id=args.jobid, command=args.cmd)
        print('updated' if changed else 'unchanged')
        print(json.dumps(meta.get(args.name), indent=2))
    elif args.remove:
        if not args.name:
            print('Must provide --name to remove')
            raise SystemExit(2)
        ok, meta = remove_cron_meta(args.name)
        print('removed' if ok else 'not found')
    else:
        parser.print_help()