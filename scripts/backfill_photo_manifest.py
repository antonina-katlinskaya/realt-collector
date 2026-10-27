"""Build photo_manifest.json from a verified already-published release; no new scrape."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import requests
import zipfile

data=Path('data')
state=json.loads((data/'collection_state.json').read_text(encoding='utf-8'))
entry=state['archive_entry']
assert entry and entry.get('verified') and entry.get('sha256') and entry.get('url')
response=requests.get(entry['url'],timeout=60)
response.raise_for_status()
packet=response.content
if hashlib.sha256(packet).hexdigest()!=entry['sha256']:
    raise RuntimeError('Release checksum mismatch; no manifest will be written')
images={}
with zipfile.ZipFile(io.BytesIO(packet)) as z:
    members=[name for name in z.namelist() if name.endswith('.json.gz')]
    if not members: raise RuntimeError('Archive has no raw snapshots')
    for name in members:
        raw=json.loads(gzip.decompress(z.read(name)))
        for obj in raw.get('minsk_mir_objects',[]):
            urls=[u for u in (obj.get('images') or []) if isinstance(u,str) and u.startswith('https://')]
            if urls: images[str(obj['uuid'])]=urls[:5]
if not images: raise RuntimeError('No image URLs; refuse to overwrite manifest')
target=data/'photo_manifest.json'
target.write_text(json.dumps({'snapshot_at':state['snapshot_at'],'images':images},ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
print('Photo manifest prepared:',len(images),'UUIDs',target.stat().st_size,'bytes')
