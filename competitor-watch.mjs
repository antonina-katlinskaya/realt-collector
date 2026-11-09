const townUuid='4cb07174-7b00-11eb-8943-0cc47adabd66', streets=["abc8d575-0762-11ed-83a9-2a683d81eaa1","4a248232-7b00-11eb-8943-0cc47adabd66","4c3d1e02-7b00-11eb-8943-0cc47adabd66","4c333426-7b00-11eb-8943-0cc47adabd66","4a24df08-7b00-11eb-8943-0cc47adabd66","4a267cdb-7b00-11eb-8943-0cc47adabd66","4c3edd91-7b00-11eb-8943-0cc47adabd66","4c3edea8-7b00-11eb-8943-0cc47adabd66","4c3d1b2b-7b00-11eb-8943-0cc47adabd66","4c3ee0c2-7b00-11eb-8943-0cc47adabd66","4c3d68db-7b00-11eb-8943-0cc47adabd66","f324aece-55f2-11ee-a430-525305579d91","bbeb39f4-4a54-11ef-9a28-525305579d91"];
const query='query searchObjects($data:GetObjectsByAddressInput!){searchObjects(data:$data){success errors{code message} body{pagination{totalCount} results{uuid code createdAt title description agencyUuid streetUuid streetName townName townUuid address userUuid contactName agencyName companyName realEstateDevUuid availableAlready}}}}';
async function get(addressV2,page=1,pageSize=30){const data={where:{addressV2,category:5},pagination:{page,pageSize},sort:[{by:'createdAt',order:'DESC'}],extraFields:null,isReactAdaptiveUA:true};const r=await fetch('https://realt.by/bff/graphql',{method:'POST',headers:{'content-type':'application/json','user-agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'},body:JSON.stringify([{operationName:'searchObjects',variables:{data},query}]),signal:AbortSignal.timeout(12000)});const j=(await r.json())[0];const x=j.data?.searchObjects;if(!x?.body)throw Error(j.errors?.[0]?.message??'no body');return x.body;}
const {writeFileSync,readFileSync}=await import('node:fs');
const zg='4ca3486d-7b00-11eb-8943-0cc47adabd66';
const segments=[
 {name:'Минск Мир',filter:streets.map(streetUuid=>({townUuid,streetUuid})),match:o=>streets.includes(o.streetUuid)&&/минск[\s‑–—-]*мир|minsk[\s‑–—-]*world/iu.test((o.title??'')+' '+(o.description??'')),seeds:[['Альфа-Недвижимость',4272486],['Светлана · Мариэлт',4264789],['Арт Недвижимость',4272814],['Алькор',4269672],['Ольга · Бриллиантовый лев',4269755]]},
 {name:'Зелёная гавань',filter:[{townUuid:zg}],match:o=>o.townUuid===zg&&(/зел[её]н(?:ая|ой|ую)\s+гаван[ьи]/iu.test((o.title??'')+' '+(o.description??''))||/лавандовая|березовая аллея|лесные озера|зеленой гавани|серебряный лес|хвойная аллея|кленовая аллея|солнечные поля/iu.test((o.streetName??'').replaceAll('ё','е'))),seeds:[['Ольга · Этажи',4268074],['Светлана · Этажи',4261856],['ЭРА-Недвижимости',4268436],['АурумЭстейт',4265036],['Золотой ключ',4265776,true]]}
];
const output='docs/competitor-watch.json';
const previous=process.argv.includes('--print')?[]:JSON.parse(readFileSync(output,'utf8')).rows;
const now=Date.now(), cutoff=now-30*864e5;
const rows=[];
for(const {name,filter,match,seeds} of segments){
 const ads=[];const seen=new Set();let latest=Infinity, complete=false;
 for(let page=1;page<=100;page++){
  const {results}=await get(filter,page);
  for(const ad of results){
   const time=Date.parse(ad.createdAt);
   if(!Number.isFinite(time)||time>latest||seen.has(ad.uuid))throw Error('Unstable pagination for '+name);
   latest=time;seen.add(ad.uuid);
   if(time>=cutoff&&match(ad))ads.push(ad);
  }
  if(latest<cutoff||results.length<30){complete=true;break;}
  await new Promise(resolve=>setTimeout(resolve,1100));
 }
 if(!complete)throw Error('Incomplete window for '+name);
 for(const [label,seed,agency] of seeds){
  const field=agency?'agencyUuid':'userUuid';
  const prior=previous.find(r=>r.complex===name&&r.label===label);
  const id=prior?.id??ads.find(ad=>Number(ad.code)===seed)?.[field];
  if(!id)throw Error('Missing identity for '+label);
  const matched=ads.filter(ad=>ad[field]===id);
  rows.push({complex:name,label,id,agency:!!agency,count:matched.length,days:new Set(matched.map(ad=>ad.createdAt.slice(0,10))).size,last:matched[0]?.createdAt??null,code:matched[0]?.code??null});
 }
}
const json=JSON.stringify({updatedAt:new Date(now).toISOString(),rows},null,2)+'\n';
if(process.argv.includes('--print'))console.log(JSON.stringify({updatedAt:new Date(now).toISOString(),rows}));
else writeFileSync(output,json);
