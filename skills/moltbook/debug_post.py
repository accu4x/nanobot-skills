import os, json, requests, sys
HERE = os.path.dirname(__file__)
DATA_DIR = os.path.join(HERE, 'data')
DRAFTS_PATH = os.path.join(DATA_DIR, 'drafts.json')
DISCOVERED = os.path.join(DATA_DIR, 'discovered_endpoints.json')
API_BASE = 'https://www.moltbook.com/api/v1'

def load_draft(draft_id):
    with open(DRAFTS_PATH, 'r', encoding='utf8') as f:
        drafts = json.load(f)
    for d in drafts:
        if int(d.get('id')) == int(draft_id):
            return d
    return None


def load_discovered():
    try:
        with open(DISCOVERED, 'r', encoding='utf8') as f:
            return json.load(f)
    except Exception:
        return {}


def do_post(path, payload, headers):
    url = API_BASE + path
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        print(f"POST {path} -> {r.status_code}")
        try:
            print(r.text)
        except Exception:
            print('<non-text response>')
        print('\n' + ('-'*60) + '\n')
    except Exception as e:
        print(f"POST {path} -> Exception: {e}")


def main():
    draft = load_draft(2)
    if not draft:
        print('Draft 2 not found')
        sys.exit(2)
    title = draft.get('title')
    body = draft.get('body')
    payload = {'title': title, 'body': body, 'tags': draft.get('tags', []), 'visibility': draft.get('visibility', 'private')}

    api_key = os.environ.get('MOLTBOOK_API_KEY')
    if not api_key:
        print('No MOLTBOOK_API_KEY in environment')
        sys.exit(1)
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

    discovered = load_discovered()
    agent_id = None
    agent_info = discovered.get('agent_info')
    if isinstance(agent_info, dict):
        # try nested shapes
        agent_id = agent_info.get('id') or agent_info.get('agent_id')
        if not agent_id and 'agent' in agent_info and isinstance(agent_info['agent'], dict):
            agent_id = agent_info['agent'].get('id') or agent_info['agent'].get('agent_id')

    tried = []
    if agent_id:
        path = f"/agents/{agent_id}/posts"
        tried.append(path)
        do_post(path, payload, headers)

    path = '/posts'
    tried.append(path)
    do_post(path, payload, headers)

    print('Tried paths:', tried)

if __name__ == '__main__':
    main()
