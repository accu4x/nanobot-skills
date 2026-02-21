import requests,os,sys  
api=os.environ.get('MOLTBOOK_API_KEY')  
if not api:  
    print('No API key in env'); sys.exit(0)  
s=requests.Session()  
s.headers.update({'Authorization':f'Bearer {api}'})  
try:  
    r=s.get('https://www.moltbook.com/api/v1/agents/me',timeout=10)  
    print('status',r.status_code)  
    try:  
        print(r.json())  
    except Exception:  
        print('body:', r.text[:400])  
except Exception as e:  
    print('error',e)  
