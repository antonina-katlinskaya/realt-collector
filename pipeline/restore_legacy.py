"""One-time exact restoration of pre-migration CSV occurrences from its pinned commit."""
import csv
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
from collections import Counter
import shutil
import tempfile
from urllib.request import urlopen
from pipeline.storage import rotate

SOURCE='https://raw.githubusercontent.com/antonina-katlinskaya/realt-collector/60e7890d73ce95dc5b772125a33fe7518eb39fac/data/snapshots.csv'
PROOF=Path('data/health/history_integrity.json')

def counts(partitions,fields):
    out=Counter()
    for path in partitions:
        with gzip.open(path,'rt',encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):out[digest(row,fields)]+=1
    return out

def digest(row,fields):
    return hashlib.sha256(json.dumps([row.get(k,'') for k in fields],ensure_ascii=False).encode()).hexdigest()

def main():
    output=os.environ.get('GITHUB_OUTPUT')
    if PROOF.exists() and json.loads(PROOF.read_text()).get('schema')==2:
        if output:
            with open(output,'a') as f:f.write('changed=false\n')
        print('Legacy exact-history proof already exists');return
    with urlopen(SOURCE,timeout=120) as response:original=response.read()
    reader=csv.DictReader(io.StringIO(original.decode('utf-8-sig')))
    fields=reader.fieldnames or []
    if not {'snapshot_at','uuid','price'}<=set(fields):raise RuntimeError('Invalid pinned legacy CSV')
    expected=Counter();keys=Counter();n=0
    for row in reader:
        expected[digest(row,fields)]+=1;keys[(row['snapshot_at'],row['uuid'])]+=1;n+=1
    if not n:raise RuntimeError('Empty legacy history')
    before=counts(Path('data/snapshots').glob('*.csv.gz'),fields)
    with tempfile.TemporaryDirectory(prefix='realt-legacy-restore-') as directory:
        temp=Path(directory)
        (temp/'snapshots.csv').write_bytes(original)
        shutil.copytree('data/snapshots',temp/'snapshots')
        rotate(temp)
        after=counts((temp/'snapshots').glob('*.csv.gz'),fields)
        missing=sum((expected-after).values())
        if missing:raise RuntimeError(f'Legacy history still missing {missing} rows')
        for file in (temp/'snapshots').glob('*.csv.gz'):
            target=Path('data/snapshots')/file.name
            if not target.exists() or target.read_bytes()!=file.read_bytes():shutil.copy2(file,target)
    proof={'schema':2,'source_commit':'60e7890d73ce95dc5b772125a33fe7518eb39fac',
           'source_sha256':hashlib.sha256(original).hexdigest(),'previous_csv_rows':n,
           'duplicate_listing_keys':sum(c-1 for c in keys.values()),
           'restored_missing_occurrences':sum((expected-before).values()),
           'missing_previous_rows':missing,'archive_rows':sum(after.values()),
           'merge_policy':'maximum occurrence count per complete row; conflicting versions retained'}
    PROOF.parent.mkdir(parents=True,exist_ok=True)
    PROOF.write_text(json.dumps(proof,ensure_ascii=False,indent=2))
    if output:
        with open(output,'a') as f:f.write('changed=true\n')
    print(json.dumps(proof,ensure_ascii=False))

if __name__=='__main__':main()
