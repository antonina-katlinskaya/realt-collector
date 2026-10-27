"""Read-only analysis of resale contamination in the last verified Realt source."""
import gzip, hashlib, io, json, zipfile
from pathlib import Path
import requests
s=json.loads(Path('data/collection_state.json').read_text())
a=s['archive_entry']; data=requests.get(a['url'],timeout=60).content
assert hashlib.sha256(data).hexdigest()==a['sha256']
objects=[]
with zipfile.ZipFile(io.BytesIO(data)) as z:
    for name in z.namelist():
        if name.endswith('.json.gz'):
            objects.extend(json.loads(gzip.decompress(z.read(name)))['minsk_mir_objects'])
def classify(o):
    text=(' '.join(str(o.get(k) or '') for k in ['title','description'])).lower()
    if o.get('realEstateDevUuid'): return 'developer_id'
    if 'от застройщика' in text or 'напрямую от застройщика' in text:return 'developer_text'
    if 'новострой' in text or 'строящ' in text:return 'newbuild_text'
    if 'ремонт' in text or 'вторич' in text or 'готовая квартира' in text:return 'likely_resale'
    return 'unverified'
from collections import Counter
print('total',len(objects),'categories',Counter(map(classify,objects)))
for group in ['developer_id','developer_text','newbuild_text','likely_resale','unverified']:
    sample=[o for o in objects if classify(o)==group][:8]
    print('\nGROUP',group,'examples:',json.dumps([{'code':o.get('code'),'title':o.get('title'),'realEstateDevUuid':o.get('realEstateDevUuid'),'objectType':o.get('objectType'),'buildingYear':o.get('buildingYear'),'availableYear':o.get('availableYear'),'availableAlready':o.get('availableAlready')} for o in sample],ensure_ascii=False))

from pipeline.developer_filter import developer_offer
selected=[o for o in objects if developer_offer(o)]
print('selected',len(selected))
for check,cond in [('old_building',lambda o:int(o.get('buildingYear') or 0) and int(o.get('buildingYear') or 0)<2022),('title_remont',lambda o:'ремонт' in str(o.get('title') or '').lower()),('title_resale',lambda o:'вторич' in str(o.get('title') or '').lower()),('realty_deal',lambda o:bool(o.get('isObjectInRealtyDeal'))),('not_newbuild_text',lambda o:not any(w in str(o.get('title') or '').lower() for w in ['застройщик','минск','дом','рассроч','новострой']))]:
 cand=[o for o in selected if cond(o)]
 print('accepted_'+check,len(cand),json.dumps([{'code':o.get('code'),'title':o.get('title'),'year':o.get('buildingYear')} for o in cand[:8]],ensure_ascii=False))
