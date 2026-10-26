"""Immutable weekly GitHub Release assets for complete RAW and CSV observations.

Bulk snapshots never accumulate in the working Git tree. No LFS, paid storage,
Cloudflare or removal of existing files. Assets are read back and SHA-256 checked.
"""
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
import zipfile

REPO='antonina-katlinskaya/realt-collector'
MAX_ASSET=100_000_000

def sha(data):return hashlib.sha256(data).hexdigest()

def tail(path,keep=2):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames;rows=list(reader)
    times=sorted({r['snapshot_at'] for r in rows})[-keep:]
    out=[r for r in rows if r['snapshot_at'] in set(times)]
    temp=Path(path).with_suffix('.tmp')
    with temp.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fields);writer.writeheader();writer.writerows(out)
    temp.replace(path)
    return {'recent_snapshots':len(times),'recent_rows':len(out),'recent_csv_bytes':Path(path).stat().st_size}

def make_packet(raw_paths,csv_path,snapshot_at):
    files={Path(p).name:Path(p).read_bytes() for p in raw_paths}
    if not files:raise RuntimeError('Archive packet has no RAW snapshot')
    raw_ids=set()
    for name,data in files.items():
        document=json.loads(gzip.decompress(data))
        if document['snapshot_at']!=snapshot_at:raise RuntimeError('Archive RAW timestamp mismatch')
        ids=[str(x['uuid']) for x in document['minsk_mir_objects']]
        if len(ids)!=len(set(ids)) or not ids:raise RuntimeError('Archive RAW UUIDs are invalid')
        raw_ids.update(ids)
    with Path(csv_path).open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f);fields=reader.fieldnames
        rows=[r for r in reader if r['snapshot_at']==snapshot_at]
    if len(rows)!=len(raw_ids) or {r['uuid'] for r in rows}!=raw_ids:
        raise RuntimeError('RAW/CSV mismatch; archive not published')
    output=io.StringIO(newline='');writer=csv.DictWriter(output,fields);writer.writeheader();writer.writerows(rows)
    files['rows.csv.gz']=gzip.compress(output.getvalue().encode('utf-8-sig'),mtime=0)
    manifest={'schema':1,'snapshot_at':snapshot_at,'rows':len(rows),'raw_members':sorted(n for n in files if n!='rows.csv.gz'),
              'csv_member':'rows.csv.gz','sha256':{name:sha(data) for name,data in files.items()}}
    files['manifest.json']=json.dumps(manifest,ensure_ascii=False,sort_keys=True).encode()
    target=io.BytesIO()
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_STORED) as z:
        for name,data in sorted(files.items()):
            info=zipfile.ZipInfo(name,date_time=(2000,1,1,0,0,0));z.writestr(info,data)
    packet=target.getvalue()
    verify_packet(packet)
    if len(packet)>MAX_ASSET:raise RuntimeError('Archive packet exceeds 100 MB protective ceiling')
    return packet,manifest

def verify_packet(packet):
    with zipfile.ZipFile(io.BytesIO(packet)) as z:
        if z.testzip():raise RuntimeError('Archive CRC check failed')
        manifest=json.loads(z.read('manifest.json'))
        for name,digest in manifest['sha256'].items():
            if sha(z.read(name))!=digest:raise RuntimeError('Archive member checksum failed')
        return manifest

class Releases:
    def __init__(self):
        self.token=os.environ.get('GITHUB_TOKEN')
        if not self.token:raise RuntimeError('Missing GitHub token; archive refuses local-only fallback')

    def request(self,method,path,body=None,binary=False):
        url=path if path.startswith('https://uploads.github.com/') else 'https://api.github.com/repos/'+REPO+path
        headers={'Authorization':'Bearer '+self.token,'Accept':'application/vnd.github+json','User-Agent':'realt-archive',
                 'Content-Type':'application/zip' if binary else 'application/json'}
        data=body if binary else json.dumps(body).encode() if body is not None else None
        try:
            with urlopen(Request(url,data=data,method=method,headers=headers),timeout=120) as r:return json.load(r)
        except HTTPError as e:
            if e.code==404 and method=='GET':return None
            raise RuntimeError(f'GitHub archive {method} failed: HTTP {e.code}') from None
        except (URLError,TimeoutError):
            raise RuntimeError('GitHub archive network failure; no blind mutation retry') from None

    def release(self,tag):
        found=self.request('GET','/releases/tags/'+tag)
        if found:return found
        try:
            return self.request('POST','/releases',{'tag_name':tag,'target_commitish':'main','name':'Realt data archive '+tag,
                'body':'Immutable collected dataset packets: complete RAW, CSV and SHA-256 manifest. Project archive; no notification recipients or credentials.',
                'draft':False,'prerelease':False,'make_latest':'false'})
        except RuntimeError:
            found=self.request('GET','/releases/tags/'+tag)
            if found:return found
            raise

    def read(self,url):
        if not url.startswith('https://github.com/'+REPO+'/releases/download/'):
            raise RuntimeError('Unexpected archive URL')
        for attempt in range(3):
            try:
                with urlopen(Request(url,headers={'User-Agent':'realt-archive-verify'}),timeout=120) as r:return r.read()
            except HTTPError as e:
                if e.code not in (404,429,500,502,503,504) or attempt==2:
                    raise RuntimeError(f'Archive readback failed: HTTP {e.code}') from None
            except (URLError,TimeoutError):
                if attempt==2:raise RuntimeError('Archive readback unavailable') from None
            time.sleep(attempt+1)

    def publish(self,packet,snapshot_at):
        when=dt.datetime.fromisoformat(snapshot_at.replace('Z','+00:00'));year,week,_=when.isocalendar()
        tag=f'realt-data-{year}-W{week:02d}';release=self.release(tag)
        assets=[]
        for page in range(1,11):
            batch=self.request('GET',f"/releases/{release['id']}/assets?per_page=100&page={page}") or []
            assets.extend(batch)
            if len(batch)<100:break
        name='snapshot-'+when.strftime('%Y-%m-%d_%H-%M-%S')+'-'+sha(packet)[:12]+'.zip'
        existing=next((a for a in assets if a['name']==name),None)
        if not existing:
            if len(assets)>=900:raise RuntimeError('Weekly archive asset safety ceiling reached (900)')
            upload=release['upload_url'].split('{',1)[0]+'?name='+quote(name)
            try:existing=self.request('POST',upload,packet,binary=True)
            except RuntimeError:
                batch=self.request('GET',f"/releases/{release['id']}/assets?per_page=100&page=1") or []
                existing=next((a for a in batch if a['name']==name),None)
                if not existing:raise
        if existing.get('state')!='uploaded' or existing.get('size')!=len(packet):
            raise RuntimeError('Archive upload is incomplete')
        readback=self.read(existing['browser_download_url'])
        if sha(readback)!=sha(packet):raise RuntimeError('Archive readback SHA-256 mismatch')
        verify_packet(readback)
        return {'tag':tag,'asset_id':existing['id'],'url':existing['browser_download_url'],
                'name':name,'bytes':len(packet),'sha256':sha(packet),'verified':True}

def archive_snapshot(data_dir,raw_paths,marker,backend=None):
    data=Path(data_dir);packet,manifest=make_packet(raw_paths,data/'snapshots.csv',marker['snapshot_at'])
    remote=(backend or Releases()).publish(packet,marker['snapshot_at'])
    if remote.get('verified') is not True or remote.get('sha256')!=sha(packet):
        raise RuntimeError('Archive backend did not confirm integrity')
    entry={**remote,**{k:marker[k] for k in ('snapshot_at','completed_at','rows')},
           'raw_members':manifest['raw_members'],'csv_member':manifest['csv_member']}
    folder=data/'archive';folder.mkdir(exist_ok=True)
    month=marker['snapshot_at'][:7];path=folder/(month+'.json')
    history=json.loads(path.read_text()) if path.exists() else {'schema':1,'snapshots':[]}
    prior=next((x for x in history['snapshots'] if x['snapshot_at']==marker['snapshot_at']),None)
    if prior and prior['sha256']!=entry['sha256']:raise RuntimeError('Snapshot archive conflict; immutable asset not replaced')
    if not prior:history['snapshots'].append(entry)
    history['snapshots'].sort(key=lambda x:x['snapshot_at'])
    path.write_text(json.dumps(history,ensure_ascii=False,indent=2))
    root=folder/'index.json';index=json.loads(root.read_text()) if root.exists() else {'schema':1,'months':[]}
    index['months']=sorted(set(index['months']+[month]));index['latest_snapshot_at']=marker['snapshot_at']
    root.write_text(json.dumps(index,ensure_ascii=False,indent=2))
    return entry

def bootstrap():
    data=Path('data');proof=data/'health'/'release_archive.json'
    if proof.exists():
        _output(False);return
    marker=json.loads((data/'collection_state.json').read_text())
    raw_paths=[data.parent/p for p in marker['raw_paths']]
    entry=archive_snapshot(data,raw_paths,marker)
    # The legacy daily archives already contain every row of this compatibility file.
    # Keep all existing archives and RAW; shrink only this derived rolling cache.
    metrics=tail(data/'snapshots.csv')
    proof.parent.mkdir(exist_ok=True)
    proof.write_text(json.dumps({'schema':1,'mode':'weekly-github-releases','verified':entry,
        'cache':metrics,'existing_legacy_files_preserved':True},ensure_ascii=False,indent=2))
    _output(True)
    print(json.dumps({'archive_bootstrap_verified':entry,'cache':metrics},ensure_ascii=False))

def _output(changed):
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('changed='+str(changed).lower()+'\n')

if __name__=='__main__':bootstrap()
