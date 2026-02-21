import requests, json
r = requests.get('https://www.moltbook.com/api/v1/posts', timeout=15)
print('Status', r.status_code)
try:
    j = r.json()
    if isinstance(j, list) and j:
        print('List top-level')
        print('First item keys:', list(j[0].keys()))
        print('First item sample:', json.dumps(j[0], indent=2, ensure_ascii=False)[:2000])
    elif isinstance(j, dict):
        print('Dict top-level keys:', list(j.keys()))
        for k in ('posts','items'):
            if k in j and isinstance(j[k], list) and j[k]:
                print(k,'first keys:', list(j[k][0].keys()))
                print(k,'first sample:', json.dumps(j[k][0], indent=2, ensure_ascii=False)[:2000])
                break
except Exception as e:
    print('JSON parse failed', e)
