'use strict';
// Presentation only: read the collector's files without altering them.
function parseCSV(text) {
  const records=[]; let row=[],field='',quoted=false;
  text=text.replace(/^\uFEFF/,'');
  for(let i=0;i<text.length;i++) {
    const c=text[i];
    if(c==='"') { if(quoted&&text[i+1]==='"'){field+='"';i++;}else quoted=!quoted; }
    else if(c===','&&!quoted){row.push(field);field='';}
    else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;row.push(field);if(row.some(x=>x!==''))records.push(row);row=[];field='';}
    else field+=c;
  }
  if(quoted)throw Error('Незавершённое поле CSV');
  if(field||row.length){row.push(field);records.push(row);}
  const headers=records.shift()||[];
  return records.map((r,i)=>{if(r.length!==headers.length)throw Error('Неверное число колонок CSV: строка '+(i+2));return Object.fromEntries(headers.map((h,j)=>[h,r[j]]));});
}
const number=x=>x===''||x==null||!Number.isFinite(Number(x))?null:Number(x);
const paid=r=>[2,3,4].includes(number(r.paymentStatus));
const free=r=>number(r.paymentStatus)===0;
const HOUR_FMT=new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Minsk',hour:'2-digit',hourCycle:'h23'}),DAY_FMT=new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Minsk',year:'numeric',month:'2-digit',day:'2-digit'}),DAY_CACHE=new Map();
const day=t=>{let v=DAY_CACHE.get(t);if(v===undefined){v=DAY_FMT.format(new Date(t));DAY_CACHE.set(t,v);}return v;};
function buildIndex(rows) {
  const byTime=new Map(),histories=new Map();
  for(const r of rows){if(!r.uuid||!r.snapshot_at||Number.isNaN(Date.parse(r.snapshot_at)))continue;if(!byTime.has(r.snapshot_at))byTime.set(r.snapshot_at,new Map());byTime.get(r.snapshot_at).set(r.uuid,r);}
  const times=[...byTime.keys()].sort();
  for(const t of times)for(const r of byTime.get(t).values()){if(!histories.has(r.uuid))histories.set(r.uuid,[]);histories.get(r.uuid).push(r);}
  return {times,byTime,histories};
}
function intervals(index,from,to) {
  const out=[],highs=new Map();
  if(!index.times.length)return out;
  for(const r of index.byTime.get(index.times[0]).values()){const v=number(r.views);if(v!==null)highs.set(r.uuid,v);}
  for(let i=1;i<index.times.length;i++){
    const a=index.times[i-1],b=index.times[i],inside=day(a)>=from&&day(b)<=to;
    const prev=index.byTime.get(a),cur=index.byTime.get(b);
    for(const [id,r] of cur){
      const vb=number(r.views),priorHigh=highs.get(id);
      if(vb!==null)highs.set(id,priorHigh===undefined?vb:Math.max(priorHigh,vb));
      const p=prev.get(id);if(!p||!inside)continue;
      const va=number(p.views);if(va===null||vb===null||vb<va)continue;
      // Previously observed visits must not be counted again after a counter reset.
      const delta=Math.max(0,vb-Math.max(va,priorHigh===undefined?va:priorHigh));
      const category=p.paymentStatus===r.paymentStatus&&paid(p)?'paid':free(p)&&free(r)?'free':'unknown';
      out.push({id,row:r,start:a,end:b,delta,category});
    }
  }
  return out;
}
function statusStart(index,r){const h=index.histories.get(r.uuid)||[];let i=h.findIndex(x=>x.snapshot_at===r.snapshot_at);if(i<0)return {time:r.snapshot_at,open:true};const startIndex=i;while(i>0&&h[i-1].paymentStatus===r.paymentStatus&&index.times.indexOf(h[i].snapshot_at)===index.times.indexOf(h[i-1].snapshot_at)+1)i--;return {time:h[i].snapshot_at,open:i===0,startIndex};}
function weekday(t){return (new Date(day(t)+'T12:00:00Z').getUTCDay()+6)%7;}
function changesBetween(index,from,to,accept=()=>true){
 const result=[],fields={price:'Цена',priceCurrency:'Валюта',title:'Заголовок',paymentStatus:'Продвижение',areaTotal:'Площадь',rooms:'Комнатность',storey:'Этаж',storeys:'Этажность',address:'Адрес',createdAt:'Дата публикации'};
 for(let i=1;i<index.times.length;i++){const a=index.times[i-1],b=index.times[i];if(day(b)<from||day(b)>to)continue;const prev=index.byTime.get(a),cur=index.byTime.get(b);for(const [id,r]of cur){const p=prev.get(id);if(!p||!accept(r,b))continue;const changes=Object.entries(fields).filter(([k])=>p[k]!==''&&p[k]!=null&&r[k]!==''&&r[k]!=null&&p[k]!==r[k]).map(([key,name])=>({key,name,old:p[key],new:r[key]}));if(changes.length)result.push({id,row:r,start:a,end:b,changes});}}
 return result;
}
function periodData(index,from,to,accept=()=>true,bounds=null,trustedFrom=null){
 const inside=t=>day(t)>=from&&day(t)<=to&&(!bounds||(Date.parse(t)>=bounds.start&&Date.parse(t)<=bounds.end));
 const available=index.times.filter(inside),end=available.at(-1),current=end?[...index.byTime.get(end).values()].filter(r=>accept(r,end)):[];
 const observed=new Map();for(const t of available)for(const [id,r] of index.byTime.get(t))if(accept(r,t))observed.set(id,r);
 const lastValues=new Map(),unstableIds=new Set();
 for(const t of available.filter(t=>!trustedFrom||t>=trustedFrom))for(const [id,r] of index.byTime.get(t)){const v=number(r.views),prev=lastValues.get(id);if(v!==null){if(prev!==undefined&&v<prev)unstableIds.add(id);lastValues.set(id,v);}}
 const allEvents=intervals(index,from,to).filter(e=>inside(e.start)&&inside(e.end)&&accept(e.row,e.end));
 const rawEvents=allEvents.filter(e=>!trustedFrom||e.start>=trustedFrom);
 const excludedLegacyEvents=allEvents.length-rawEvents.length;
 const events=rawEvents.filter(e=>!unstableIds.has(e.id));
 const excludedEvents=rawEvents.filter(e=>unstableIds.has(e.id));
 const growth=new Map();for(const e of events)growth.set(e.id,(growth.get(e.id)||0)+e.delta);
 const newly=[...observed.values()].filter(r=>{const h=index.histories.get(r.uuid);return h[0].snapshot_at!==index.times[0]&&inside(h[0].snapshot_at)&&accept(h[0],h[0].snapshot_at);});
 const currentIds=new Set(current.map(r=>r.uuid)),gone=new Map();
 for(let i=1;i<index.times.length;i++){const a=index.times[i-1],b=index.times[i];if(!inside(b))continue;for(const [id,r]of index.byTime.get(a))if(!index.byTime.get(b).has(id)&&!currentIds.has(id)&&accept(r,b))gone.set(id,{...r,goneAt:b});}
 for(const [id,r]of gone)if(!observed.has(id))observed.set(id,r);
 const changes=changesBetween(index,from,to,(r,t)=>inside(t)&&accept(r,t));
 return {from,to,end,current,observed:[...observed.values()],events,unstableIds,excludedEvents,excludedLegacyEvents,growth,newly,gone:[...gone.values()],changes};
}

function collectionFreshness(last,now=Date.now()){
 const grace=45*60*1000,d=new Date(now),midnight=Date.UTC(d.getUTCFullYear(),d.getUTCMonth(),d.getUTCDate());
 const slots=[];for(const base of [midnight-86400000,midnight])for(let hour=4;hour<=18;hour++)slots.push(base+(hour*60+10)*60000);
 const due=slots.filter(t=>t+grace<=now),expected=due.length?Math.max(...due):midnight-86400000+18*3600000+10*60000;
 return {expected,stale:!Number.isFinite(Date.parse(last))||Date.parse(last)<expected};
}
if(typeof module!=='undefined')module.exports={parseCSV,buildIndex,intervals,statusStart,day,weekday,changesBetween,periodData,collectionFreshness};
if(typeof document!=='undefined'){
const ROOT='https://raw.githubusercontent.com/antonina-katlinskaya/realt-collector/main/data/';
const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>x==null?'—':Number(x).toLocaleString('ru-RU');
const date=t=>new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Minsk',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(t));
const price=r=>fmt(number(r.price))+' '+({'978':'€','840':'$','933':'BYN'}[r.priceCurrency]||esc(r.priceCurrency));
const label=r=>r.payment_label||({'0':'Бесплатно','2':'Выделение','3':'Поднятие','4':'Спецпредложение'}[r.paymentStatus]||'Статус '+r.paymentStatus);
const known={'i.s.barashenko':'Ирина Барашенко','e.v.boriskina':'Елена Борискина','v.n.khatkovskaya':'Вероника Хатковская'};
const knownById={'77ff7ab0-6e68-11ee-818e-0935d63487ea':'Ирина Барашенко','ff985560-a80d-11f0-bfef-45b6701187ce':'Елена Борискина','d6a0a26a-26a6-11ec-ae6c-dee111c4eff3':'Вероника Хатковская'};
function agentName(r){const email=(r.contactEmail||'').split('@')[0];return knownById[r.userUuid]||known[email]||(r.contactName||'Без имени');}
let index,rows=[],baseRows=[],seen=null,seenPromise=null,selectedTab='published',page=0,currentModel=null,loadSeq=0,developerIds=new Set();
const ARCHIVE_START='2026-10-05',archiveRows=new Map(),archiveMissing=new Set();let archiveRequestSeq=0;
let preciseBounds=null,activeView='promotion',hiddenAgents=new Set(),chosenInterval=null,photos=new Map(),photoLoaded=false,photoDate=null;
async function restoreArchiveRange(){
 if(!index)return;
 const seq=++archiveRequestSeq,from=$('from').value,to=$('to').value,last=day(index.times.at(-1));
 if(!from||!to||from>to)return;
 const dates=[];for(let t=Date.parse((from>ARCHIVE_START?from:ARCHIVE_START)+'T12:00:00Z'),end=Date.parse((to<last?to:last)+'T12:00:00Z');t<=end;t+=86400000){const d=new Date(t).toISOString().slice(0,10);if(!archiveRows.has(d)&&!archiveMissing.has(d))dates.push(d);}
 if(!dates.length){if(seq===archiveRequestSeq)render();return;}
 $('status').textContent='Загружаю сохранённую историю за '+dates.length+' дн. Без неё рейтинг за период неполный…';
 const failures=[];let next=0;
 async function worker(){while(next<dates.length){const d=dates[next++];try{
 const response=await fetch(ROOT+'snapshots/'+d+'.csv.gz',{cache:'force-cache'});
 if(response.status===404){archiveMissing.add(d);continue;}if(!response.ok)throw Error('HTTP '+response.status);
 if(typeof DecompressionStream==='undefined')throw Error('Нужен браузер с поддержкой gzip');
 const content=await new Response(response.body.pipeThrough(new DecompressionStream('gzip'))).text();
 archiveRows.set(d,parseCSV(content));
 }catch(e){failures.push(d+': '+e.message);}}}
 await Promise.all(Array.from({length:Math.min(3,dates.length)},()=>worker()));
 rows=baseRows.concat(...archiveRows.values());index=buildIndex(rows.filter(r=>developerIds.has(r.uuid)));
 if(seq===archiveRequestSeq){populateUnified(new Map([...index.histories.values()].filter(a=>a.length).map(a=>[a.at(-1).userUuid,a.at(-1)])));render();if(failures.length)$('status').textContent='Часть архива не загрузилась: '+failures.join('; ');}
}
function updateFreshness(){
  const last=index?.times.at(-1);if(!last)return;
  const state=collectionFreshness(last);$('freshness').textContent='Последний снимок: '+date(last);
  const warning=$('freshnessWarning');warning.hidden=!state.stale;
  warning.textContent=state.stale?'Данные не обновились по расписанию. Последний снимок: '+date(last)+'. Ожидался сбор от '+date(state.expected)+'. Показаны сохранённые данные.':'';
}
const checks=id=>new Set([...$(id).querySelectorAll('input:checked')].map(x=>x.value));
function matches(r,t=r.snapshot_at,ignorePromo=false){const multi=checks('multiAgents'),week=checks('weekdays'),area=number(r.areaTotal),lo=number($('areaMin').value),hi=number($('areaMax').value);
return (!$('agent').value||r.userUuid===$('agent').value)&&(!multi.size||multi.has(r.userUuid))&&(ignorePromo||!week.size||week.has(String(weekday(t))))&&(!$('quarter').value||(r.quarter||'(не определён)')===$('quarter').value)&&(!$('company').value||r.agencyName===$('company').value)&&(!$('rooms').value||r.rooms===$('rooms').value)&&(!$('house').value||r.address===$('house').value)&&(lo===null||(area!==null&&area>=lo))&&(hi===null||(area!==null&&area<=hi))&&(!$('search').value||[r.title,r.address,r.code,agentName(r)].join(' ').toLowerCase().includes($('search').value.toLowerCase()))&&(ignorePromo||promoMatch(r));}
function createMatcher(){
 const multi=checks('multiAgents'),week=checks('weekdays');
 const agent=$('agent').value,quarter=$('quarter').value,company=$('company').value,rooms=$('rooms').value,house=$('house').value;
 const lo=number($('areaMin').value),hi=number($('areaMax').value),search=$('search').value.toLowerCase(),promo=$('promo').value;
 return (r,t=r.snapshot_at,ignorePromo=false)=>{
  const area=number(r.areaTotal);
  if(agent&&r.userUuid!==agent||multi.size&&!multi.has(r.userUuid))return false;
  if(!ignorePromo&&week.size&&!week.has(String(weekday(t))))return false;
  if(quarter&&(r.quarter||'(не определён)')!==quarter||company&&r.agencyName!==company||rooms&&r.rooms!==rooms||house&&r.address!==house)return false;
  if(lo!==null&&(area===null||area<lo)||hi!==null&&(area===null||area>hi))return false;
  if(search&&![r.title,r.address,r.code,agentName(r)].join(' ').toLowerCase().includes(search))return false;
  return ignorePromo||!promo||(promo==='paid'?paid(r):promo==='other'?![0,2,3,4].includes(number(r.paymentStatus)):r.paymentStatus===promo);
 };
}
function promoMatch(r){const p=$('promo').value;return !p||(p==='paid'?paid(r):p==='other'?![0,2,3,4].includes(number(r.paymentStatus)):r.paymentStatus===p);}
let cachedModelIndex=null,cachedModelKey='',cachedModelValue=null;
function model(){
 const fields=['from','to','agent','promo','quarter','company','rooms','house','areaMin','areaMax','search','sort'];
 const key=JSON.stringify([fields.map(id=>$(id).value),[...checks('multiAgents')].sort(),[...checks('weekdays')].sort(),selectedTab,preciseBounds]);
 if(cachedModelIndex===index&&cachedModelKey===key&&cachedModelValue)return cachedModelValue;
 const m=periodData(index,$('from').value,$('to').value,createMatcher(),preciseBounds,'2026-10-27T11:41:00Z');
 let listing=selectedTab==='published'?m.observed.filter(r=>r.createdAt&&day(r.createdAt)>=m.from&&day(r.createdAt)<=m.to):selectedTab==='paid'?m.current.filter(paid):selectedTab==='new'?m.newly:selectedTab==='gone'?m.gone:selectedTab==='period'?m.observed:m.current;
 const sort=$('sort').value;listing=listing.slice().sort((a,b)=>sort==='growth'?(m.growth.get(b.uuid)||0)-(m.growth.get(a.uuid)||0):sort==='views'?(number(b.views)||0)-(number(a.views)||0):sort==='price'?String(a.priceCurrency).localeCompare(String(b.priceCurrency))||(number(a.price)||0)-(number(b.price)||0):String(b.createdAt).localeCompare(String(a.createdAt)));
 cachedModelIndex=index;cachedModelKey=key;cachedModelValue={...m,listing};return cachedModelValue;
}
function svgBars(groups){
  if(!groups.length)return '<div class="empty">Нужны хотя бы два обхода внутри выбранного периода.<br>Общий счётчик уже доступен в таблице.</div>';
  const W=760,H=280,left=52,bottom=235,top=15,palette={paid:'#147b73',free:'#396cc1',unknown:'#b67b25'};
  const max=Math.max(1,...groups.map(g=>g.paid+g.free+g.unknown)),step=(W-left-14)/groups.length;
  let s=`<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Прирост просмотров между обходами">`;
  for(let i=0;i<=4;i++){const y=bottom-(bottom-top)*i/4;s+=`<line x1="${left}" y1="${y}" x2="${W}" y2="${y}" stroke="#e3eaf1"/><text x="${left-8}" y="${y+4}" text-anchor="end" font-size="11" fill="#62758a">${fmt(Math.round(max*i/4))}</text>`;}
  groups.forEach((g,i)=>{let y=bottom;const x=left+i*step+step*.2;for(const cat of ['free','paid','unknown']){const h=g[cat]/max*(bottom-top);y-=h;s+=`<rect x="${x}" y="${y}" width="${Math.max(2,step*.6)}" height="${h}" rx="2" fill="${palette[cat]}"><title>${esc(g.title)} · ${cat==='paid'?'при продвижении':cat==='free'?'без продвижения':'неясный статус'}: ${g[cat]}</title></rect>`;}
    if(groups.length<16||i%Math.ceil(groups.length/12)===0)s+=`<text x="${x+step*.3}" y="${bottom+20}" text-anchor="middle" font-size="10" fill="#62758a">${esc(g.label)}</text>`;
  });return s+'</svg>';
}
function render(){if(!index)return;const m=model();currentModel=m;const quick=$('quick').querySelector('button.active');$('filtersSummaryPeriod').textContent=quick?quick.textContent.trim():'Свой период';
  if(m.from>m.to){$('status').textContent='Дата начала должна быть раньше даты окончания.';return;}
  const comparable=m.events.length>0,delta=m.events.reduce((s,e)=>s+e.delta,0),advertised=m.current.filter(paid).length;
  const activations=m.changes.filter(c=>c.changes.some(x=>x.key==='paymentStatus'&&![2,3,4].includes(number(x.old))&&[2,3,4].includes(number(x.new)))).length;
  const bumps=m.changes.filter(c=>c.changes.some(x=>x.key==='paymentStatus'&&number(x.new)===3&&number(x.old)!==3)).length;
  $('cards').innerHTML=[['Прирост просмотров',comparable?delta:null,'за сопоставимые интервалы'],['Объявлений сейчас',m.current.length,'на последнем снимке выбранного периода'],['В продвижении',advertised,'по последнему снимку периода'],['Новых замечено',m.newly.length,'с момента первого наблюдения'],['Включений продвижения',activations,'наблюдаемые смены статуса'],['Включений поднятия',bumps,'наблюдаемые переходы на статус'],['Открытия номера','—','Realt не предоставляет эти данные']].map(([title,value,note])=>`<div class="card"><strong>${value===null?'—':(typeof value==='number'?fmt(value):value)}</strong><div class="kpi-label">${title}</div><span>${note}</span></div>`).join('');
  $('status').textContent=m.end?'Состояние объявлений на '+date(m.end)+' · '+index.times.length+' снимков в истории':'Нет снимков до выбранной даты';
  const countTimes=index.times.filter(t=>day(t)>=m.from&&day(t)<=m.to).length;
  $('coverage').textContent=countTimes<2?'Пока в выбранном периоде меньше двух снимков. Прирост, длительность продвижения и время активности начнут уточняться с новыми обходами.':`${countTimes} снимков в выбранном периоде. Прирост за полностью покрытые интервалы: ${fmt(delta)}. При продвижении: ${fmt(m.events.filter(e=>e.category==='paid').reduce((s,e)=>s+e.delta,0))}; без продвижения: ${fmt(m.events.filter(e=>e.category==='free').reduce((s,e)=>s+e.delta,0))}; при смене / неизвестном статусе: ${fmt(m.events.filter(e=>e.category==='unknown').reduce((s,e)=>s+e.delta,0))}.`;
  if(m.excludedLegacyEvents){$('coverage').textContent+=` До исправления привязки просмотров к UUID исключено ${fmt(m.excludedLegacyEvents)} исторических интервалов. Для рейтингов нужны два новых достоверных обхода после 27.10.2026, 14:41 Минск.`;}
  if(m.unstableIds.size){const excludedTotal=m.excludedEvents.reduce((sum,e)=>sum+e.delta,0);$('coverage').textContent+=` ⚠ У ${fmt(m.unstableIds.size)} объявлений счётчик просмотров снижался между обходами; их положительные скачки (+${fmt(excludedTotal)}) исключены из рейтингов и итогового прироста. Исходные значения сохранены в истории.`;}
  const currentTotal=m.current.reduce((sum,r)=>sum+(number(r.views)||0),0);
  if(delta>currentTotal*2&&currentTotal>0){$('coverage').textContent+=' ⚠ Это сумма наблюдаемых приращений по историческим объявлениям, а не число уникальных покупателей. В архиве обнаружены аномально большие скачки счётчиков: источник и причина пока не подтверждены; нельзя трактовать их как доказанную эффективность рекламы.';}
  const groups=new Map();for(const e of m.events){const k=e.end;if(!groups.has(k))groups.set(k,{paid:0,free:0,unknown:0,title:date(e.start)+' → '+date(e.end),label:date(e.end).slice(0,5)+' '+date(e.end).slice(-5)});groups.get(k)[e.category]+=e.delta;}
  if(activeView==='overview'){$('traffic').innerHTML=svgBars([...groups.values()]);renderRanking(m);}
  if(activeView==='ads')renderTable(m);
  if(activeView!=='ads')renderUnified(m);
}
function renderRanking(m){const agents=new Map();for(const r of m.current){const id=r.userUuid;if(!agents.has(id))agents.set(id,{id,name:agentName(r),phone:r.contactPhone,count:0,paid:0,views:0,growth:0});const a=agents.get(id);a.count++;a.paid+=paid(r)?1:0;a.views+=number(r.views)||0;}
  for(const e of m.events){if(agents.has(e.row.userUuid))agents.get(e.row.userUuid).growth+=e.delta;}
  const key=$('rank').value;if(key==='growth'&&!m.events.length){$('ranking').innerHTML='<div class="empty">Для сравнения прироста нужны два снимка.</div>';return;}
  const list=[...agents.values()].sort((a,b)=>b[key]-a[key]).slice(0,10),max=Math.max(1,...list.map(a=>a[key]));
  $('ranking').innerHTML=list.map(a=>`<div class="barrow"><button data-agent="${esc(a.id)}" title="${esc(a.phone)}">${esc(a.name)}</button><div class="bartrack"><div class="bar" style="width:${a[key]/max*100}%"></div></div><b>${fmt(a[key])}</b></div>`).join('')||'<div class="empty">Нет объявлений по выбранным фильтрам</div>';
}
function renderTable(m){const size=40;page=Math.min(page,Math.max(0,Math.ceil(m.listing.length/size)-1));const part=m.listing.slice(page*size,(page+1)*size);
  $('listings').innerHTML=part.map(r=>{const st=statusStart(index,r),dv=m.growth.get(r.uuid);return `<tr><td>${esc(agentName(r))}<br><small>${esc(r.contactPhone)}</small></td><td class="title">${photos.has(r.uuid)?`<img loading="lazy" class="listing-thumb" src="${esc(photos.get(r.uuid)[0])}" alt="Фото объявления ${esc(r.code)}">`:''}<a href="https://realt.by/sale-flats/object/${encodeURIComponent(r.code)}/" target="_blank" rel="noopener">${esc(r.address||r.title)} ↗</a><br><small>${esc(r.code)} · ${esc(r.areaTotal)} м² · ${esc(r.storey)}/${esc(r.storeys)} эт. · ${esc(r.quarter||'дом не распознан')}</small>${r.goneAt?'<br><small>Отсутствует с '+date(r.goneAt)+'</small>':''}</td><td>${price(r)}</td><td><span class="badge ${paid(r)?'promo':''}">${esc(label(r))}</span></td><td>${date(st.time)}<br><small>${st.open?'Начало неизвестно':'Смена замечена между обходами'}</small></td><td>${fmt(number(r.views))}</td><td>${fmt(dv)}</td><td><button data-detail="${esc(r.uuid)}">История</button></td></tr>`;}).join('')||'<tr><td colspan="8" class="empty">Нет объявлений по выбранным фильтрам</td></tr>';
  $('adCards').innerHTML=part.map(r=>{
    const imgs=photos.get(r.uuid)||[];
    const photo=imgs.length?`<img loading="lazy" src="${esc(imgs[0])}" alt="Фото объявления ${esc(r.code)}">`:'<div class="photo-fallback">Фото из снимка отсутствует</div>';
    const dv=m.growth.get(r.uuid),growth=dv===undefined?'—':'+'+fmt(dv);
    const posted=r.createdAt?date(r.createdAt):'дата неизвестна';
    return `<article class="ad-tile" data-detail="${esc(r.uuid)}">${photo}<div class="tile-content"><div class="tile-title">${esc(r.title||r.address||'Объявление')}</div><div class="tile-address">${esc(r.address||'Адрес не указан')}</div><div class="tile-meta">${esc(agentName(r))} · ${esc(r.rooms||'?')}-комн. · ${esc(r.areaTotal||'?')} м² · ${price(r)}</div><div class="tile-meta">Размещено: ${posted} · ${esc(label(r))}</div><div class="tile-stats"><span>${fmt(number(r.views))} просм. всего</span><span>${growth} за период</span></div></div></article>`;
  }).join('')||empty('Объявления по выбранным фильтрам отсутствуют.');
  if($('publishedCount'))$('publishedCount').textContent='· '+fmt(m.listing.length);
  $('rowcount').textContent=`${m.listing.length? page*size+1:0}–${Math.min((page+1)*size,m.listing.length)} из ${fmt(m.listing.length)}`;$('prev').disabled=page===0;$('next').disabled=(page+1)*size>=m.listing.length;
}
async function load(){const seq=++loadSeq;$('refresh').disabled=true;$('status').textContent='Загружаем снимки…';try{const manifestResponse=await fetch(ROOT+'developer_manifest.json?refresh='+Date.now(),{cache:'no-store'});if(!manifestResponse.ok)throw Error('Нет проверенного списка объявлений от застройщика: HTTP '+manifestResponse.status);const developerManifest=await manifestResponse.json();if(developerManifest.rule_version!==1||!Array.isArray(developerManifest.ids))throw Error('Неизвестная версия отбора новостроек');developerIds=new Set(developerManifest.ids);const response=await fetch(ROOT+'snapshots.csv?refresh='+Date.now(),{cache:'no-store'});if(!response.ok)throw Error('HTTP '+response.status);const text=await response.text();if(seq!==loadSeq)return;baseRows=parseCSV(text);rows=baseRows.concat(...archiveRows.values());index=buildIndex(rows.filter(r=>developerIds.has(r.uuid)));if(!index.times.length)throw Error('Снимки пока отсутствуют');const last=index.times.at(-1);updateFreshness();
  const agents=new Map();for(const t of index.times)for(const r of index.byTime.get(t).values())agents.set(r.userUuid,r);
  const prevAgent=$('agent').value,prevQuarter=$('quarter').value;
  $('agent').innerHTML='<option value="">Все агенты</option>'+[...agents.values()].sort((a,b)=>agentName(a).localeCompare(agentName(b),'ru')).map(r=>`<option value="${esc(r.userUuid)}">${esc(agentName(r))} · ${esc(r.contactPhone||r.userUuid.slice(0,8))}</option>`).join('');$('agent').value=prevAgent;
  $('quarter').innerHTML='<option value="">Все</option>'+[...new Set(rows.map(r=>r.quarter||'(не определён)'))].sort().map(q=>`<option>${esc(q)}</option>`).join('');$('quarter').value=prevQuarter;
  if(!$('from').value)$('from').value=day(index.times[0]);if(!$('to').value)$('to').value=day(last);const quick=$('quick').querySelector('button.active');if(quick)applyQuickPeriod(quick.dataset.days);seen=null;seenPromise=null;populateUnified(agents);await restoreArchiveRange();render();
}catch(e){$('status').textContent='Не удалось загрузить данные: '+e.message+'. Нажми «Обновить данные», чтобы повторить.';}finally{$('refresh').disabled=false;}}
function detailChart(h){if(!h.length)return '';const vals=h.filter(r=>number(r.views)!==null);if(!vals.length)return '<div class="empty">Счётчики не получены</div>';const W=740,H=210,min=0,max=Math.max(1,...vals.map(r=>Number(r.views)));const x=i=>48+(W-75)*i/Math.max(1,vals.length-1),y=v=>170-v/max*140;let s=`<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Общий счётчик просмотров объявления"><line x1="48" y1="170" x2="${W-15}" y2="170" stroke="#dce4ed"/><text x="40" y="30" text-anchor="end" font-size="11">${fmt(max)}</text><polyline points="${vals.map((r,i)=>x(i)+','+y(Number(r.views))).join(' ')}" fill="none" stroke="#396cc1" stroke-width="3"/>`;
  vals.forEach((r,i)=>{s+=`<circle cx="${x(i)}" cy="${y(Number(r.views))}" r="5" fill="${paid(r)?'#147b73':'#396cc1'}"><title>${date(r.snapshot_at)} · ${r.views} просмотров · ${esc(label(r))}</title></circle>`;if(vals.length<12||i%Math.ceil(vals.length/10)===0)s+=`<text x="${x(i)}" y="195" text-anchor="middle" font-size="10">${date(r.snapshot_at).slice(0,5)}</text>`;});return s+'</svg>';}
let lastFocused=null,detailSeq=0;
async function showDetail(id){const token=++detailSeq,h=index.histories.get(id)||[],r=h.filter(x=>day(x.snapshot_at)<=currentModel.to).at(-1);if(!r)return;const st=statusStart(index,r),duration=(Date.parse(r.snapshot_at)-Date.parse(st.time))/3600000;
  lastFocused=document.activeElement;$('drawer').hidden=false;$('close').focus();
  $('detail').innerHTML=`<div class="eyebrow">ОБЪЯВЛЕНИЕ ${esc(r.code)}</div><h2 id="detailtitle">${esc(r.title)}</h2><p>${esc(agentName(r))} · ${esc(r.address)} · ${esc(r.areaTotal)} м²</p><a href="https://realt.by/sale-flats/object/${encodeURIComponent(r.code)}/" target="_blank" rel="noopener">Открыть объявление на Realt ↗</a><div class="detailgrid"><div class="card">Цена<strong>${price(r)}</strong></div><div class="card">Продвижение<strong>${esc(label(r))}</strong></div><div class="card">Общий счётчик<strong>${fmt(number(r.views))}</strong></div></div><div class="notice">Текущий статус наблюдается с ${date(st.time)}. ${st.open?'Дата его начала до первого наблюдения неизвестна.':'Переход замечен между двумя обходами.'} Покрытый наблюдениями промежуток: ${fmt(Math.round(duration*10)/10)} ч. Непрерывность между обходами не гарантирована.</div><section class="panel"><h3>История общего счётчика</h3>${detailChart(h.filter(x=>day(x.snapshot_at)<=currentModel.to))}</section><section class="panel"><h3>Наблюдения по объявлению</h3><div class="tablewrap"><table><thead><tr><th>Начало сбора</th><th>Продвижение</th><th>Цена</th><th>Просмотры</th><th>Прирост</th></tr></thead><tbody>${h.filter(x=>day(x.snapshot_at)<=currentModel.to).map((x,i)=>{const p=h[i-1],a=number(x.views),b=p?number(p.views):null;return `<tr><td>${date(x.snapshot_at)}</td><td>${esc(label(x))}</td><td>${price(x)}</td><td>${fmt(a)}</td><td>${p&&a!==null&&b!==null&&a>=b?fmt(a-b):'—'}</td></tr>`;}).join('')}</tbody></table></div></section><section class="panel"><h3>Исходные исторические значения API</h3><p class="muted">Опорная дата запроса и возвращённое значение. Это не точное время визита клиента и не подтверждённая разбивка по дням.</p><div id="historyraw">Загружаем…</div></section>`;
  detailExtras(id);
  try{if(!seenPromise)seenPromise=fetch(ROOT+'listings_seen.json?refresh='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json();});seen=await seenPromise;if(token!==detailSeq||$('drawer').hidden)return;const hist=seen[id]?.history_views||{};$('historyraw').innerHTML=Object.keys(hist).length?'<table><thead><tr><th>Опорная дата</th><th>Значение API</th></tr></thead><tbody>'+Object.entries(hist).sort().map(([d,v])=>`<tr><td>${esc(d)}</td><td>${fmt(v)}</td></tr>`).join('')+'</tbody></table>':'Исторические значения отсутствуют';}catch(e){seenPromise=null;if(token===detailSeq)$('historyraw').textContent='История пока недоступна: '+e.message;}
}
function closeDetail(){$('drawer').hidden=true;detailSeq++;lastFocused?.focus();}
for(const id of ['from','to','agent','promo','quarter','sort','rank','rooms','company','house','areaMin','areaMax'])$(id).addEventListener('change',()=>{if(id==='from'||id==='to'){preciseBounds=null;if($('filterPeriodLabel'))$('filterPeriodLabel').textContent='Свой период';for(const x of $('quick').querySelectorAll('button'))x.classList.remove('active');}if(id==='agent')for(const x of $('multiAgents').querySelectorAll('input'))x.checked=false;page=0;if(id==='from'||id==='to')restoreArchiveRange();else render();});let searchRenderTimer=null;
$('search').addEventListener('input',()=>{page=0;clearTimeout(searchRenderTimer);searchRenderTimer=setTimeout(()=>render(),180);});
function applyQuickPeriod(n){const today=day(new Date());preciseBounds=null;const labels={'1':'Сегодня','yesterday':'Вчера','24h':'24 часа','7':'7 дней','14':'14 дней','30':'30 дней','90':'90 дней','all':'Вся история'};if($('filterPeriodLabel'))$('filterPeriodLabel').textContent=labels[n]||'Свой период';
if(n==='all'){$('from').value=ARCHIVE_START;$('to').value=day(index.times.at(-1));}
else if(n==='24h'){preciseBounds={start:Date.now()-86400000,end:Date.now()};$('from').value=day(preciseBounds.start);$('to').value=day(preciseBounds.end);}
else if(n==='yesterday'){const d=new Date(today+'T12:00:00Z');d.setUTCDate(d.getUTCDate()-1);$('from').value=$('to').value=d.toISOString().slice(0,10);}
else{const start=new Date(today+'T12:00:00Z');start.setUTCDate(start.getUTCDate()-Number(n)+1);$('from').value=start.toISOString().slice(0,10);$('to').value=today;}
}
$('quick').addEventListener('click',e=>{const b=e.target.closest('[data-days]');if(!b||!index)return;applyQuickPeriod(b.dataset.days);for(const x of $('quick').querySelectorAll('button'))x.classList.toggle('active',x===b);page=0;restoreArchiveRange();});
$('tabs').addEventListener('click',e=>{const b=e.target.closest('[data-tab]');if(!b)return;selectedTab=b.dataset.tab;for(const x of $('tabs').querySelectorAll('button'))x.classList.toggle('active',x===b);page=0;render();});
$('ranking').addEventListener('click',e=>{const b=e.target.closest('[data-agent]');if(b){$('agent').value=b.dataset.agent;for(const x of $('multiAgents').querySelectorAll('input'))x.checked=false;page=0;render();}});
$('listings').addEventListener('click',e=>{const b=e.target.closest('[data-detail]');if(b)showDetail(b.dataset.detail);});$('close').onclick=closeDetail;$('drawer').onclick=e=>{if(e.target===$('drawer'))closeDetail();};document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDetail();if(e.key==='Tab'&&!$('drawer').hidden){const els=[...$('drawer').querySelectorAll('button,a[href],input,select,summary')];if(e.shiftKey&&document.activeElement===els[0]){e.preventDefault();els.at(-1).focus();}else if(!e.shiftKey&&document.activeElement===els.at(-1)){e.preventDefault();els[0].focus();}}});
$('prev').onclick=()=>{page--;render();};$('next').onclick=()=>{page++;render();};$('refresh').onclick=load;
$('export').onclick=()=>{if(!currentModel)return;const keys=['agent','code','address','price','currency','promotion','views','views_delta','url'];const quote=x=>'"'+String(x??'').replace(/"/g,'""')+'"';const csv='\uFEFF'+[keys,...currentModel.listing.map(r=>[agentName(r),r.code,r.address,r.price,r.priceCurrency,label(r),r.views,currentModel.growth.get(r.uuid)??'', 'https://realt.by/sale-flats/object/'+r.code+'/'])].map(r=>r.map(quote).join(',')).join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='realt-'+currentModel.from+'_'+currentModel.to+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
const urlFor=r=>'https://realt.by/sale-flats/object/'+encodeURIComponent(r.code)+'/';
const adLink=r=>`<a href="${urlFor(r)}" target="_blank" rel="noopener">${esc(r.address||r.title)} ↗</a><br><small>№ ${esc(r.code)} · ${esc(r.areaTotal)} м² · ${esc(r.rooms)} комн.</small>`;
const detailButton=r=>`<button data-detail="${esc(r.uuid)}">История</button>`;
const totalEvents=(events,category=null)=>events.filter(e=>!category||e.category===category).reduce((s,e)=>s+e.delta,0);
const categoryName={paid:'При продвижении',free:'Бесплатно на обоих обходах',unknown:'Смена / неизвестный статус'};
const empty=message=>`<div class="empty">${message}</div>`;
function makeTable(headers,body){return '<div class="tablewrap"><table><thead><tr>'+headers.map(h=>'<th>'+h+'</th>').join('')+'</tr></thead><tbody>'+ (body.length?body.join(''):`<tr><td colspan="${headers.length}" class="empty">Нет подходящих наблюдений</td></tr>` )+'</tbody></table></div>';}
function populateUnified(agents){
 const selected=checks('multiAgents');$('multiAgents').innerHTML=[...agents.values()].sort((a,b)=>agentName(a).localeCompare(agentName(b),'ru')).map(r=>`<label><input type="checkbox" value="${esc(r.userUuid)}" ${selected.has(r.userUuid)?'checked':''}>${esc(agentName(r))} · ${esc(r.contactPhone||r.userUuid.slice(0,8))}</label>`).join('');
 for(const [id,key]of [['rooms','rooms'],['company','agencyName'],['house','address']]){const old=$(id).value;$(id).innerHTML='<option value="">Все</option>'+[...new Set(rows.map(r=>r[key]).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'ru',{numeric:true})).map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('');$(id).value=old;}
}
function changesHTML(changes){return changes.slice().reverse().slice(0,120).map(c=>`<div class="changes"><div><b>${esc(agentName(c.row))}</b> · ${adLink(c.row)}</div><small>${date(c.start)} → ${date(c.end)}</small><ul>${c.changes.map(x=>`<li>${esc(x.name)}: ${esc(x.key==='paymentStatus'?label({paymentStatus:x.old}):x.old)} → ${esc(x.key==='paymentStatus'?label({paymentStatus:x.new}):x.new)}</li>`).join('')}</ul>${detailButton(c.row)}</div>`).join('')||empty('Нужны два соседних снимка с изменениями. Исходная загрузка не считается действием агента.');}
function renderDaily(m){
 const groups=new Map();for(const t of index.times.filter(t=>day(t)>=m.from&&day(t)<=m.to)){const d=day(t);if(!groups.has(d))groups.set(d,{snapshots:0,newly:0,views:null});groups.get(d).snapshots++;}
 for(const e of m.events){const g=groups.get(day(e.end));if(g)g.views=(g.views||0)+e.delta;}
 for(const r of m.newly){const d=day(index.histories.get(r.uuid)[0].snapshot_at);if(groups.has(d))groups.get(d).newly++;}
 $('dailyTable').innerHTML=makeTable(['Дата конца замера','Снимков','Впервые замечены после базового','Прирост'],[...groups].map(([d,g])=>`<tr><td>${d}</td><td>${g.snapshots}</td><td>${g.newly}</td><td>${fmt(g.views)}</td></tr>`));
}
function agentsFor(m){const out=new Map();const publication=r=>{if(!r.createdAt||Number.isNaN(Date.parse(r.createdAt)))return 'unknown';const d=day(r.createdAt);return d>=m.from&&d<=m.to?'new':'old';};const ensure=r=>{if(!out.has(r.userUuid))out.set(r.userUuid,{row:r,current:0,paid:0,observed:new Set(),delta:0,deltaNew:0,deltaOld:0,deltaUnknown:0,published:new Set(),changes:0,newly:0,total:0});return out.get(r.userUuid);};for(const r of m.current){const a=ensure(r);a.current++;a.paid+=paid(r)?1:0;a.total+=number(r.views)||0;}for(const r of m.observed){const a=ensure(r);a.observed.add(r.uuid);if(publication(r)==='new')a.published.add(r.uuid);}for(const e of m.events){const a=ensure(e.row);a.delta+=e.delta;const k=publication(e.row);if(k==='new')a.deltaNew+=e.delta;else if(k==='old')a.deltaOld+=e.delta;else a.deltaUnknown+=e.delta;}for(const c of m.changes)ensure(c.row).changes++;for(const r of m.newly)ensure(r).newly++;return [...out.values()].sort((a,b)=>b.delta-a.delta||b.current-a.current);}
function renderUnified(m){
 if(activeView==='overview'){renderDaily(m);$('changesFeed').innerHTML=changesHTML(m.changes);}
 if(activeView==='leaders'){
 const promoted=new Map();for(const e of m.events){if(e.category!=='paid')continue;const v=promoted.get(e.id)||{row:e.row,delta:0};v.delta+=e.delta;v.row=e.row;promoted.set(e.id,v);}const list=[...promoted.values()].sort((a,b)=>b.delta-a.delta);
 $('leadersTable').innerHTML=list.length?makeTable(['Место','Агент','Объявление','Прирост','Общий счётчик',''],list.slice(0,100).map((v,i)=>`<tr><td>${i+1}</td><td>${esc(agentName(v.row))}</td><td class="wrap">${adLink(v.row)}</td><td>+${fmt(v.delta)}</td><td>${fmt(number(v.row.views))}</td><td>${detailButton(v.row)}</td></tr>`)):empty('Нет сопоставимых интервалов с платным продвижением за выбранный период.');
 if(photoLoaded)renderPromotedGallery(m);
 }
 if(activeView==='employees'){
 $('employeeChanges').innerHTML=changesHTML(m.changes);
 const agents=agentsFor(m);const maxDelta=Math.max(1,...agents.map(a=>a.delta));$('employeeHighlights').innerHTML=agents.slice(0,18).map(a=>`<article class="employee-highlight"><button data-select-agent="${esc(a.row.userUuid)}">${esc(agentName(a.row))}</button><div class="big">${m.events.length?'+'+fmt(a.delta):'—'}</div><div class="track"><span style="width:${Math.max(0,a.delta)/maxDelta*100}%"></span></div><small>${fmt(a.current)} активных · ${fmt(a.paid)} с продвижением</small></article>`).join('');$('employeeTable').innerHTML=makeTable(['Сотрудник','Активных','Опубликовано за период','Просмотры новых: прирост','Просмотры старых: прирост','Без даты: прирост','С продвижением','Изменений'],agents.map(a=>`<tr><td><button data-select-agent="${esc(a.row.userUuid)}">${esc(agentName(a.row))}</button><br><small>${esc(a.row.contactPhone)}</small></td><td>${a.current}</td><td>${a.published.size}</td><td>${m.events.length?fmt(a.deltaNew):'—'}</td><td>${m.events.length?fmt(a.deltaOld):'—'}</td><td>${m.events.length?fmt(a.deltaUnknown):'—'}</td><td>${a.paid}</td><td>${a.changes}</td></tr>`));
 }
 if(activeView==='promotion')renderPromotions(m);
 if(activeView==='works')renderWorks(m);
 if(activeView==='placements')renderPlacements(m);
 if(activeView==='hours')renderInterval(m);
 const baseline=m.newly.length===0&&index.times.length===1?' Базовый снимок содержит уже существовавшие объявления; он не считается массовой новой публикацией.':'';
 if(activeView==='overview')$('coverage').textContent+=baseline;
}
function liveAgentCard(id,items){const r=items[0];return `<article class="agentcard"><h3>${esc(agentName(r))}</h3><span class="badge promo">${items.length} в продвижении</span>${items.map(r=>{const st=statusStart(index,r);return `<div class="adlink">${adLink(r)}<br><small>${price(r)} · ${esc(label(r))}<br>Наблюдается с ${date(st.time)}; ${st.open?'начало неизвестно':'смена между обходами'}</small> ${detailButton(r)}</div>`;}).join('')}</article>`;}
function renderPromotions(m){
 const paidEvents=m.events.filter(e=>e.category==='paid');
 const active=[...index.byTime.get(index.times.at(-1)).values()].filter(r=>matches(r,r.snapshot_at,true)&&paid(r));
 const promotedObserved=m.observed.filter(paid);
 const paidIds=new Set(promotedObserved.map(r=>r.uuid));
 const totalPaid=m.events.filter(e=>e.category==='paid').reduce((n,e)=>n+e.delta,0);
 const kpis=[
 ['Объявлений в продвижении',paidIds.size,'замечено за выбранный период'],
 ['Просмотры при продвижении',paidEvents.length?totalPaid:null,'только проверенные последовательные замеры'],
 ['Открытия телефона','—','Realt не предоставляет эти значения'],
 ['Сейчас в рекламе',active.length,'подтверждены последним обходом']
 ];
 $('promoOverviewKpi').innerHTML=kpis.map(([name,value,note])=>`<div class="card"><strong>${value===null?'—':typeof value==='number'?fmt(value):value}</strong><div class="kpi-label">${name}</div><span>${note}</span></div>`).join('');
 const groups=new Map();
 for(const r of active){const id=r.userUuid||'';if(!groups.has(id))groups.set(id,[]);groups.get(id).push(r);}
 $('livePromo').innerHTML=[...groups].sort((a,b)=>b[1].length-a[1].length).map(([id,ads])=>liveAgentCard(id,ads)).join('')||empty('Сейчас нет подтверждённых объявлений в продвижении.');
 const stats=new Map();
 for(const r of promotedObserved){const id=r.userUuid||'';if(!stats.has(id))stats.set(id,{row:r,ids:new Set(),views:0,intervals:0});stats.get(id).ids.add(r.uuid);}
 for(const e of paidEvents){const id=e.row.userUuid||'';if(!stats.has(id))stats.set(id,{row:e.row,ids:new Set(),views:0,intervals:0});const st=stats.get(id);st.ids.add(e.id);st.views+=e.delta;st.intervals++;}
 $('promoResults').innerHTML=makeTable(['Сотрудник','Объявлений в рекламе','Просмотры при рекламе','Открытия телефона'],[...stats.values()].sort((a,b)=>b.ids.size-a.ids.size).map(st=>`<tr><td>${esc(agentName(st.row))}</td><td>${st.ids.size}</td><td>${st.intervals?'+'+fmt(st.views):'—'}</td><td>—</td></tr>`))+'<p class="muted tiny">Просмотры — не уникальные клиенты и не доказанная отдача рекламы. Открытия телефона неизвестны.</p>';
 const spans=[];
 const promoFilter=createMatcher();
 for(const [id,h] of index.histories){
  let first=null,previous=null;
  for(const row of h){
   const t=row.snapshot_at;if(day(t)>m.to||day(t)<m.from||!promoFilter(row,t,true))continue;
   const isPaid=paid(row);
   if(isPaid){
    if(!first){first=row;previous=row;}
    else if(row.paymentStatus!==previous.paymentStatus){spans.push({id,row:previous,start:first.snapshot_at,end:t,status:first.paymentStatus,open:false});first=row;previous=row;}
    else previous=row;
   }else if(first){spans.push({id,row:first,start:first.snapshot_at,end:t,status:first.paymentStatus,open:false});first=null;previous=null;}
  }
  if(first){spans.push({id,row:first,start:first.snapshot_at,end:null,status:first.paymentStatus,open:true});}
 }
 spans.sort((x,y)=>String(y.start).localeCompare(String(x.start)));
 const allPromoted=new Set(spans.map(x=>x.id));
 $('promoOverviewKpi').querySelector('.card strong').textContent=fmt(allPromoted.size);

 const rows=spans.slice(0,150).map(x=>{
  const ev=paidEvents.filter(e=>e.id===x.id&&e.start>=x.start&&(!x.end||e.end<=x.end));
  const v=ev.length?'+'+fmt(totalEvents(ev)):'—';
  return `<tr><td>${esc(agentName(x.row))}</td><td class="wrap">${adLink(x.row)}</td><td>${esc(label({paymentStatus:x.status}))}</td><td>${date(x.start)}</td><td>${x.end?date(x.end):'На последнем наблюдении'}</td><td>${v}</td><td>${detailButton(x.row)}</td></tr>`;
 });
 const cards=spans.slice(0,150).map(x=>{
  const ev=paidEvents.filter(e=>e.id===x.id&&e.start>=x.start&&(!x.end||e.end<=x.end));
  const viewed=ev.length?'+'+fmt(totalEvents(ev)):'—';
  return `<article class="promo-history-card" data-detail="${esc(x.id)}">
    <div class="promo-history-title">${adLink(x.row)}</div>
    <div class="muted">${esc(agentName(x.row))} · ${esc(x.row.areaTotal||'')} м² · ${price(x.row)}</div>
    <div class="promo-history-stats"><div><small>Реклама</small><b>${esc(label({paymentStatus:x.status}))}</b></div><div><small>Зафиксирована с</small><b>${date(x.start)}</b></div><div><small>До</small><b>${x.end?date(x.end):'Конец неизвестен'}</b></div><div><small>Прирост просмотров</small><b>${viewed}</b></div><div><small>Открытия номера</small><b>Нет данных</b></div></div>
    <div class="muted tiny">Показаны моменты наблюдения, не точные часы оплаты и выключения.</div>
    ${detailButton(x.row)}
   </article>`;
 }).join('');
 $('promoPeriods').innerHTML=cards||empty('В выбранном периоде продвижение не обнаружено.');
 if(spans.length>150)$('promoPeriods').insertAdjacentHTML('beforeend','<p class="muted">Показаны первые 150 периодов, уточните даты или сотрудника для остальных.</p>');
}

const palette=['#396cc1','#d97558','#147b73','#885ac5','#b67b25','#ba4b86','#1a899e','#5e728a'];
function renderTrend(m){const ids=[...new Set(m.events.map(e=>e.row.userUuid))];const names=new Map(m.events.map(e=>[e.row.userUuid,agentName(e.row)]));
 $('agentLegend').innerHTML=ids.map((id,i)=>`<button data-line="${esc(id)}" aria-pressed="${!hiddenAgents.has(id)}" style="opacity:${hiddenAgents.has(id)?'.4':'1'}"><i class="dot" style="background:${palette[i%palette.length]}"></i>${esc(names.get(id))}</button>`).join('');
 if(!ids.length){$('agentTrend').innerHTML=empty('Для динамики нужны минимум два снимка внутри периода.');return;}
 const times=[...new Set(m.events.map(e=>e.end))],values=new Map();for(const id of ids)values.set(id,new Map());for(const e of m.events){const v=values.get(e.row.userUuid);v.set(e.end,(v.get(e.end)||0)+e.delta);}
 const visible=ids.filter(id=>!hiddenAgents.has(id)),W=1000,H=300,left=55,bottom=250,max=Math.max(1,...visible.flatMap(id=>[...values.get(id).values()])),x=i=>left+i*(W-left-30)/Math.max(1,times.length-1),y=v=>bottom-v/max*220;
 let svg=`<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Прирост просмотров по агентам">`;for(let i=0;i<=4;i++){const yy=y(max*i/4);svg+=`<line x1="${left}" y1="${yy}" x2="980" y2="${yy}" stroke="#e3eaf1"/><text x="45" y="${yy+4}" text-anchor="end" font-size="12">${fmt(Math.round(max*i/4))}</text>`;}
 for(const id of visible){const color=palette[ids.indexOf(id)%palette.length],v=values.get(id);let path='',connected=false;times.forEach((t,i)=>{if(!v.has(t)){connected=false;return;}path+=(connected?' L':' M')+x(i)+' '+y(v.get(t));connected=true;});svg+=`<path d="${path}" fill="none" stroke="${color}" stroke-width="2"/>`;times.forEach((t,i)=>{if(!v.has(t))return;svg+=`<circle cx="${x(i)}" cy="${y(v.get(t)||0)}" r="4" fill="${color}"><title>${esc(names.get(id))} · конец интервала ${date(t)} · +${v.get(t)||0}</title></circle>`;});}
 times.forEach((t,i)=>{if(times.length<12||i%Math.ceil(times.length/10)===0)svg+=`<text x="${x(i)}" y="280" text-anchor="middle" font-size="11">${date(t).slice(0,5)} ${date(t).slice(-5)}</text>`;});$('agentTrend').innerHTML=svg+'</svg>';
}
function renderWorks(m){
 const byId=new Map();
 for(const e of m.events.filter(e=>e.category==='free')){
  if(!byId.has(e.id))byId.set(e.id,{r:e.row,views:0,hours:0});
  const v=byId.get(e.id);v.views+=e.delta;v.hours+=(Date.parse(e.end)-Date.parse(e.start))/3600000;
 }
 const verified=byId.size>0;
 const list=(verified?[...byId.values()]:m.current.filter(free).map(r=>({r,views:number(r.views)||0,hours:null}))).sort((a,b)=>b.views-a.views).slice(0,30);
 $('organicTable').innerHTML=(verified?'<p class="muted">Рейтинг по проверенному приросту при бесплатном статусе на двух замерах.</p>':'<p class="notice">После исправления сборщика ещё нет сопоставимых проверенных интервалов. Ниже — объявления без продвижения на последнем обходе, по общему счётчику просмотров. Это временный список, а не доказанный органический прирост.</p>')+
 makeTable(['Сотрудник','Объявление',verified?'Прирост без рекламы':'Всего просмотров','Наблюдалось часов',''],list.map(v=>`<tr><td>${esc(agentName(v.r))}</td><td class="wrap">${adLink(v.r)}</td><td>${verified?'+'+fmt(v.views):fmt(v.views)}</td><td>${v.hours===null?'—':fmt(Math.round(v.hours*10)/10)}</td><td>${detailButton(v.r)}</td></tr>`));
 $('wordsTable').innerHTML='';
}

function renderPlacements(m){const items=m.observed.filter(r=>r.createdAt&&!Number.isNaN(Date.parse(r.createdAt))&&day(r.createdAt)>=m.from&&day(r.createdAt)<=m.to&&(!preciseBounds||(Date.parse(r.createdAt)>=preciseBounds.start&&Date.parse(r.createdAt)<=preciseBounds.end))&&(!checks('weekdays').size||checks('weekdays').has(String(weekday(r.createdAt))))),groups=new Map();for(const r of items){const key=r.rooms+'|'+r.areaTotal;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);}
 $('placementGroups').innerHTML=[...groups.values()].sort((a,b)=>b.length-a.length).map(a=>`<details class="notice"><summary><b>${esc(a[0].rooms)} комн. · ${esc(a[0].areaTotal)} м²</b> — ${a.length} объявлений</summary><div class="placeitems">${a.map(r=>`<div class="placeitem">${adLink(r)}<br>${esc(agentName(r))}<br><small>Размещено ${date(r.createdAt)} · ${price(r)}</small><br>${detailButton(r)}</div>`).join('')}</div></details>`).join('')||empty('В наблюдавшихся объявлениях нет дат публикации внутри этого периода.');
 const heat=Array.from({length:7},()=>Array(24).fill(0));for(const r of items){const h=Number(HOUR_FMT.format(new Date(r.createdAt)));heat[weekday(r.createdAt)][h]++;}const max=Math.max(1,...heat.flat());$('publicationHeat').innerHTML='<div class="tablewrap"><table class="heat"><thead><tr><th></th>'+Array.from({length:24},(_,h)=>'<th>'+h+'</th>').join('')+'</tr></thead><tbody>'+['Пн','Вт','Ср','Чт','Пт','Сб','Вс'].map((d,i)=>'<tr><th>'+d+'</th>'+heat[i].map(v=>`<td style="background:rgba(20,123,115,${.04+.5*v/max})">${v||'·'}</td>`).join('')+'</tr>').join('')+'</tbody></table></div>';
}
function renderInterval(m){const times=[...new Set(m.events.map(e=>e.end))];if(!times.length){$('intervalButtons').innerHTML='';$('intervalDetail').innerHTML=empty('Сейчас доступен один снимок. После следующего появятся интервалы и списки объявлений с приростом.');return;}
 if(!times.includes(chosenInterval))chosenInterval=times.at(-1);$('intervalButtons').innerHTML=times.map(t=>{const es=m.events.filter(e=>e.end===t);return `<button class="intervalpick ${t===chosenInterval?'active':''}" data-interval="${esc(t)}">${date(es[0].start)} → ${date(t)}<br><b>+${fmt(totalEvents(es))} просмотров</b></button>`;}).join('');
 const ev=m.events.filter(e=>e.end===chosenInterval).sort((a,b)=>b.delta-a.delta);$('intervalDetail').innerHTML=makeTable(['Агент','Объявление','Начало → конец','Прирост','Статус интервала',''],ev.slice(0,100).map(e=>`<tr><td>${esc(agentName(e.row))}</td><td class="wrap">${adLink(e.row)}</td><td>${date(e.start)}<br>${date(e.end)}</td><td>+${fmt(e.delta)}</td><td>${categoryName[e.category]}</td><td>${detailButton(e.row)}</td></tr>`));
}
function renderGallery(m){const organic=new Map();for(const e of m.events){if(e.category==='free')organic.set(e.id,(organic.get(e.id)||0)+e.delta);}const hasGrowth=organic.size>0;const items=(hasGrowth?m.observed.filter(r=>organic.has(r.uuid)):m.current.filter(free)).filter(r=>photos.has(r.uuid)).sort((a,b)=>hasGrowth?(organic.get(b.uuid)||0)-(organic.get(a.uuid)||0):(number(b.views)||0)-(number(a.views)||0)).slice(0,30);
 $('gallery').innerHTML=items.map(r=>`<article class="adcard-clickable" data-detail="${esc(r.uuid)}"><div class="photoStrip">${photos.get(r.uuid).slice(0,5).map(u=>`<img loading="lazy" src="${esc(u)}" alt="Фото объявления ${esc(r.code)}">`).join('')}</div><div class="gbody">${adLink(r)}<p>${esc(agentName(r))} · ${price(r)}</p><b>${hasGrowth?'+'+fmt(organic.get(r.uuid))+' при бесплатном статусе':fmt(number(r.views))+' общих просмотров'}</b><p class="tiny">Фотографии из снимка ${date(photoDate)}; могут отличаться от нынешних.</p>${detailButton(r)}</div></article>`).join('')||empty('В выбранной подборке нет фотографий из загруженного сырого снимка.');
}
function renderPromotedGallery(m){
 const promoted=new Map();
 for(const e of m.events){if(e.category!=='paid')continue;const v=promoted.get(e.id)||{row:e.row,delta:0};v.delta+=e.delta;v.row=e.row;promoted.set(e.id,v);}
 const confirmed=[...promoted.values()].filter(v=>v.delta>0).sort((a,b)=>b.delta-a.delta);
 const fallback=confirmed.length===0;
 const ranked=fallback?m.current.filter(paid).sort((a,b)=>(number(b.views)||0)-(number(a.views)||0)).map(r=>({row:r,delta:null})):confirmed;
 const items=ranked.filter(v=>photos.has(v.row.uuid)).slice(0,30);
 $('promotedGallery').innerHTML=(fallback?'<p class="muted">Пока нет двух достоверных обходов для расчёта прироста. Ниже — объявления в продвижении на последнем снимке, упорядоченные по общему счётчику, НЕ по эффективности рекламы.</p>':'')+
 items.map(v=>{const r=v.row;return `<article class="adcard-clickable" data-detail="${esc(r.uuid)}"><div class="photoStrip">${photos.get(r.uuid).slice(0,5).map(u=>`<img loading="lazy" src="${esc(u)}" alt="Фото объявления ${esc(r.code)}">`).join('')}</div><div class="gbody">${adLink(r)}<p>${esc(agentName(r))} · ${price(r)}</p><b>${v.delta===null?fmt(number(r.views))+' всего просмотров':('+'+fmt(v.delta)+' при платном статусе')}</b><p class="tiny">Фото из снимка ${date(photoDate)}. ${v.delta===null?'Прирост ещё не проверен.':'Источник просмотров не доказан.'}</p>${detailButton(r)}</div></article>`;}).join('')+(items.length?'':empty(photoLoaded?'Нет подходящих фотографий в источнике.':'Фотографии загружаются.'));
}

async function loadPhotos(){if(photoLoaded){if(activeView==='ads')renderTable(currentModel);else if(activeView==='leaders')renderPromotedGallery(currentModel);else renderGallery(currentModel);return;}$('photoStatus').textContent='Загружаем обложки объявлений…';try{
 const manifestResponse=await fetch(ROOT+'photo_manifest.json',{cache:'no-store'});
 if(manifestResponse.ok){
  const manifest=await manifestResponse.json();
  photos=new Map(Object.entries(manifest.images||{}).filter(([,images])=>Array.isArray(images)&&images.length&&images.every(u=>typeof u==='string'&&u.startsWith('https://'))));
  photoDate=manifest.snapshot_at;photoLoaded=true;
  if(activeView==='ads')renderTable(currentModel);
  if(activeView==='leaders')renderPromotedGallery(currentModel);
  if(activeView==='works')renderGallery(currentModel);
  $('photoStatus').textContent='Фотографии получены из компактного снимка '+date(photoDate)+'.';
  return;
 }
 const listResponse=await fetch('https://api.github.com/repos/antonina-katlinskaya/realt-collector/contents/data/raw');if(!listResponse.ok)throw Error('Список снимков: HTTP '+listResponse.status);const files=await listResponse.json();const end=currentModel.end||index.times.at(-1),stamp=new Date(end).toISOString().slice(0,16).replace('T','_').replace(':','-');const candidates=files.filter(f=>f.type==='file'&&/\.json(?:\.gz)?$/.test(f.name)&&f.name.slice(0,16)<=stamp).sort((a,b)=>b.name.localeCompare(a.name));if(!candidates.length)throw Error('Нет сырого снимка в выбранном периоде');const file=candidates[0];const response=await fetch(file.download_url);if(!response.ok)throw Error('Сырой снимок: HTTP '+response.status);let raw;if(file.name.endsWith('.gz')){if(typeof DecompressionStream==='undefined')throw Error('Браузер не поддерживает распаковку gzip');const decoded=response.body.pipeThrough(new DecompressionStream('gzip'));raw=await new Response(decoded).json();}else raw=await response.json();photos=new Map((raw.minsk_mir_objects||[]).map(o=>[o.uuid,(o.images||[]).filter(u=>typeof u==='string'&&/^https:\/\//.test(u))]).filter(([,images])=>images.length));photoDate=raw.snapshot_at;photoLoaded=true;if(activeView==='leaders')renderPromotedGallery(currentModel);if(activeView==='ads')renderTable(currentModel);$('photoStatus').textContent='Фотографии загружены из сохранённого снимка. В рейтинге учитываются только наблюдаемые бесплатные интервалы.';renderGallery(currentModel);
 }catch(e){$('photoStatus').textContent='Не удалось загрузить фотографии: '+e.message;}finally{}}
function detailExtras(id){
 const ev=currentModel.events.filter(e=>e.id===id),changes=currentModel.changes.filter(c=>c.id===id);
 const split=['paid','free','unknown'].map(cat=>{const es=ev.filter(e=>e.category===cat);return `<div class="card"><div>${categoryName[cat]}</div><strong>${es.length?'+'+fmt(totalEvents(es)):'—'}</strong><small>${es.length} сопоставимых интервалов</small></div>`;}).join('');
 const html=`<section class="panel"><h3>Прирост за выбранный период</h3><div class="detailgrid">${split}</div><p class="muted tiny">Пусто означает отсутствие сопоставимого интервала. Нули появляются только при двух полученных одинаковых счётчиках.</p>${makeTable(['Начало','Конец','Прирост','Статус'],ev.map(e=>`<tr><td>${date(e.start)}</td><td>${date(e.end)}</td><td>+${fmt(e.delta)}</td><td>${categoryName[e.category]}</td></tr>`))}<h3>Изменения за период</h3>${changesHTML(changes).replace(/<button data-detail="[^"]+">История<\/button>/g,'')}</section>`;
 $('detail').insertAdjacentHTML('beforeend',html);
}
function activateView(view){const changed=activeView!==view;activeView=view;for(const x of document.querySelectorAll('[data-section]'))x.hidden=x.dataset.section!==view;for(const b of $('views').querySelectorAll('button'))b.classList.toggle('active',b.dataset.view===view);if(changed&&index){render();if(['works','leaders','ads'].includes(view)&&!photoLoaded)loadPhotos();}}
$('views').onclick=e=>{const b=e.target.closest('[data-view]');if(b)activateView(b.dataset.view);};
for(const id of ['multiAgents','weekdays'])$(id).onchange=()=>{if(id==='multiAgents')$('agent').value='';page=0;render();};
$('reset').onclick=()=>{for(const id of ['agent','promo','quarter','company','rooms','house','areaMin','areaMax','search'])$(id).value='';for(const x of document.querySelectorAll('#multiAgents input,#weekdays input'))x.checked=false;page=0;render();};

$('intervalButtons').onclick=e=>{const b=e.target.closest('[data-interval]');if(b){chosenInterval=b.dataset.interval;renderInterval(currentModel);}};

for(const id of ['areaMin','areaMax'])$(id).addEventListener('input',()=>{page=0;render();});
document.addEventListener('click',e=>{const b=e.target.closest('[data-detail]');if(b&&!b.closest('#listings')&&!b.closest('#drawer')&&!e.target.closest('a[href]'))showDetail(b.dataset.detail);const a=e.target.closest('[data-select-agent]');if(a){$('agent').value=a.dataset.selectAgent;for(const x of $('multiAgents').querySelectorAll('input'))x.checked=false;page=0;render();activateView('ads');}});

load();
setInterval(updateFreshness,60000);
setInterval(()=>{if(!document.hidden&&!$('refresh').disabled)load();},300000);
}

