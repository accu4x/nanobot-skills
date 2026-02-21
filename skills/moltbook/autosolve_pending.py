import os, json, re, requests, time
DATA_DIR = r"C:\Users\hn2_f\.nanobot\workspace\skills\moltbook\data"
PEND = os.path.join(DATA_DIR, 'pending_verifications.json')
API_BASE = 'https://www.moltbook.com/api/v1'
KEY = os.environ.get('MOLTBOOK_API_KEY')
if not KEY:
    print('No MOLTBOOK_API_KEY in environment')
    raise SystemExit(1)

with open(PEND, 'r', encoding='utf8') as f:
    items = json.load(f)

def words_to_number(s):
    words = re.findall(r"[a-z]+", s.lower())
    mapping = {'zero':0,'one':1,'two':2,'three':3,'four':4,'five':5,'six':6,'seven':7,'eight':8,'nine':9,'ten':10,'eleven':11,'twelve':12,'thirteen':13,'fourteen':14,'fifteen':15,'sixteen':16,'seventeen':17,'eighteen':18,'nineteen':19,'twenty':20,'thirty':30,'forty':40,'fifty':50,'sixty':60,'seventy':70,'eighty':80,'ninety':90}
    total = 0
    any_found = False
    for w in words:
        if w in mapping:
            total += mapping[w]
            any_found = True
        else:
            # if encounter unknown, skip
            pass
    return total if any_found else None


def extract_digits(s):
    nums = re.findall(r"[-+]?[0-9]*\.?[0-9]+", s)
    out = []
    for n in nums:
        try:
            out.append(float(n))
        except:
            pass
    return out

session = requests.Session()
session.headers.update({'Authorization': f'Bearer {KEY}', 'Content-Type': 'application/json'})

changed = False
for rec in items:
    if rec.get('status') == 'succeeded':
        print('Already succeeded:', rec.get('verification_code'))
        continue
    text = rec.get('challenge_text','')
    # heuristic: if contains 'total' or 'sum' or 'add' -> sum numbers
    ans = None
    if any(k in text.lower() for k in ('total','sum','add','how many','to total','to t a l','t o t a l')):
        nums = extract_digits(text)
        wnum = words_to_number(text)
        # if digits present and two of them, try sum
        if len(nums) >= 2:
            ans = sum(nums)
        elif wnum is not None and wnum>0:
            # try to find another spelled number
            # naive: sum spelled groups
            ans = wnum
        elif nums:
            ans = sum(nums)
    # handle 'loses' -> subtraction
    if ans is None and 'loses' in text.lower():
        nums = extract_digits(text)
        w = words_to_number(text)
        if len(nums) >= 2:
            ans = nums[0] - nums[1]
        elif len(nums) == 1 and w is not None:
            ans = w - nums[0]
        elif w is not None:
            # try find second spelled number
            # fallback: if text mentions one spelled and one spelled again
            ans = w
    # fallback: if single integer present, use it
    if ans is None:
        nums = extract_digits(text)
        if len(nums) == 1 and float(nums[0]).is_integer():
            ans = nums[0]
        else:
            w = words_to_number(text)
            if w is not None:
                ans = w
    if ans is None:
        print('Could not auto-solve:', rec.get('verification_code'), 'text:', text)
        rec['status'] = rec.get('status','pending')
        continue
    ans_f = f"{float(ans):.2f}"
    payload = {'verification_code': rec.get('verification_code'), 'answer': ans_f}
    try:
        r = session.post(f'{API_BASE}/verify', json=payload, timeout=15)
        print('POST', rec.get('verification_code'), '->', getattr(r,'status_code',None))
        rec['last_attempt'] = {'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'status': getattr(r,'status_code',None), 'text': r.text[:400] if r is not None else ''}
        if r and getattr(r,'status_code',None) in (200,201):
            rec['status'] = 'succeeded'
            rec['answer'] = ans_f
        else:
            rec['status'] = 'attempted'
    except Exception as e:
        rec['status'] = 'attempted'
        rec['last_attempt'] = {'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'error': str(e)}
    changed = True

if changed:
    with open(PEND, 'w', encoding='utf8') as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    print('Updated pending_verifications.json')
else:
    print('No changes')
