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
ids=sorted({str(x['uuid']) for x in rows if classification(x)=='developer'})
if not ids:raise RuntimeError('No developer offers; refuse to create manifest')
target=Path('data/developer_manifest.json')
target.write_text(json.dumps({'snapshot_at':state['snapshot_at'],'rule_version':1,'ids':ids,'current_ids':ids,'current_total':len(rows)},ensure_ascii=False,indent=2)+'\n')
print('Developer manifest IDs',len(ids),'excluded',len(rows)-len(ids))
