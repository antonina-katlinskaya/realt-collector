"""Read-only bounded comparison of batch vs singleton Realt GraphQL view counts."""
import csv
import io
import requests
import collector
import config as C
import queries as Q

url = 'https://raw.githubusercontent.com/antonina-katlinskaya/realt-collector/main/data/snapshots.csv'
response = requests.get(url, timeout=30)
response.raise_for_status()
rows = list(csv.DictReader(io.StringIO(response.text)))
uuids = list(dict.fromkeys(r.get('uuid') for r in rows if r.get('uuid')))[:6]
assert len(uuids) == 6, 'Not enough objects for probe'
session = requests.Session()
session.headers.update({'content-type':'application/json','user-agent':C.USER_AGENT,'accept':'application/json'})

def read(batch):
    data = collector.gql(session,Q.VIEWS_QUERY,{'uuids':batch},'v')
    if data.get('errors'):
        raise RuntimeError('GraphQL returned errors')
    result = data['data']['objectsViewsCountsByUuids']
    return [item.get('views') if isinstance(item,dict) else None for item in result]

forward=read(uuids)
reverse=read(list(reversed(uuids)))
singles=[read([u])[0] for u in uuids]
print('sample_size',len(uuids))
print('forward_length',len(forward),'reverse_length',len(reverse))
print('forward_equals_singletons',forward==singles)
print('reverse_equals_reversed_singletons',reverse==list(reversed(singles)))
print('forward_values',forward)
print('single_values',singles)
if len(forward)!=len(uuids) or len(reverse)!=len(uuids) or forward!=singles or reverse!=list(reversed(singles)):
    raise RuntimeError('Batch mapping to UUID is not trustworthy')
