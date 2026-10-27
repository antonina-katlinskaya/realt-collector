"""Read-only schema discovery: is phone-reveal statistics exposed publicly by Realt?
Does not request or reveal contact phone numbers.
"""
import requests
import config as C
import collector

session=requests.Session()
session.headers.update({'content-type':'application/json','user-agent':C.USER_AGENT,'accept':'application/json'})
query='query introspection{__schema{queryType{fields{name}}}}'
try:
    resp=collector.gql(session,query,{},'introspection')
    names=[x['name'] for x in ((resp.get('data') or {}).get('__schema') or {}).get('queryType',{}).get('fields',[])]
    matches=[n for n in names if any(w in n.lower() for w in ('phone','contact','click','stat','view','lead','call'))]
    print('Public query fields matching statistics:',matches)
    if not names:print('Schema introspection returned no public query fields (may be restricted).')
except Exception as exc:
    print('Read-only schema introspection unavailable:',type(exc).__name__,str(exc)[:250])
