import json, gzip, zipfile, io, hashlib, requests
from pathlib import Path
from pipeline.developer_filter import classification
state=json.loads(Path('data/collection_state.json').read_text())
entry=state['archive_entry'];resp=requests.get(entry['url'],timeout=60);resp.raise_for_status()
if hashlib.sha256(resp.content).hexdigest()!=entry['sha256']:raise RuntimeError('SHA mismatch')
rows=[]
with zipfile.ZipFile(io.BytesIO(resp.content)) as archive:
 for name in archive.namelist():
  if name.endswith('.json.gz'):rows+=json.loads(gzip.decompress(archive.read(name))).get('minsk_mir_objects',[])
positive=[x for x in rows if classification(x)=='developer']
negative=[x for x in rows if classification(x)!='developer']
print(json.dumps({'source':len(rows),'developer':len(positive),'excluded':len(negative),'developer_examples':[{'code':x.get('code'),'title':x.get('title')} for x in positive[:20]],'excluded_examples':[{'code':x.get('code'),'title':x.get('title'),'dev':x.get('realEstateDevUuid'),'description':str(x.get('description'))[:120]} for x in negative[:15]],'suspect_positives':[{'code':x.get('code'),'title':x.get('title'),'dev':x.get('realEstateDevUuid'),'description':str(x.get('description'))[:160]} for x in positive if any(word in str(x.get('title','')).lower() for word in ['ремонт','мебел','готовая','дизайнер'])][:15]},ensure_ascii=False,indent=2))
