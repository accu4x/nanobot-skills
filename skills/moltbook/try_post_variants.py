import os, json, requests
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
        print(r.text)
    except Exception as e:
        print(f"POST {path} -> Exception: {e}")
    print('\n' + ('-'*60) + '\n')


def main():
    draft = load_draft(2)
    if not draft:
        print('Draft 2 not found'); return
    title = draft.get('title')
    body = draft.get('body')

    discovered = load_discovered()
    agent_name = None
    ai = discovered.get('agent_info')
    if isinstance(ai, dict):
        if 'agent' in ai and isinstance(ai['agent'], dict):
            agent_name = ai['agent'].get('name')
        agent_name = agent_name or ai.get('name') or ai.get('id')

    api_key = os.environ.get('MOLTBOOK_API_KEY')
    if not api_key:
        print('No MOLTBOOK_API_KEY in environment'); return
    headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}

    payloads = []
    if agent_name:
        payloads.append({'submolt_name': agent_name, 'title': title, 'text': body})
        payloads.append({'submolt_name': agent_name, 'title': title, 'content': body})
    # Generic fallbacks
    payloads.append({'title': title, 'text': body})
    payloads.append({'title': title, 'content': body})

    for i,p in enumerate(payloads, start=1):
        print('Trying payload variant', i)
        do_post('/posts', p, headers)

if __name__ == '__main__':
    main()
