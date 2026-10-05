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
const day=t=>new Intl.DateTimeFormat('en-CA',{timeZone:'Europe/Minsk',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(t));
function buildIndex(rows) {
  const byTime=new Map(),histories=new Map();
  for(const r of rows){if(!r.uuid||!r.snapshot_at||Number.isNaN(Date.parse(r.snapshot_at)))continue;if(!byTime.has(r.snapshot_at))byTime.set(r.snapshot_at,new Map());byTime.get(r.snapshot_at).set(r.uuid,r);}
  const times=[...byTime.keys()].sort();
  for(const t of times)for(const r of byTime.get(t).values()){if(!histories.has(r.uuid))histories.set(r.uuid,[]);histories.get(r.uuid).push(r);}
  return {times,byTime,histories};
}
function intervals(index,from,to) {
  const out=[];
  for(let i=1;i<index.times.length;i++){
    const a=index.times[i-1],b=index.times[i];
    if(day(a)<from||day(b)>to)continue;
    const prev=index.byTime.get(a),cur=index.byTime.get(b);
    for(const [id,r]of cur){const p=prev.get(id);if(!p)continue;const va=number(p.views),vb=number(r.views);if(va===null||vb===null||vb<va)continue;
      const category=p.paymentStatus===r.paymentStatus&&paid(p)?'paid':free(p)&&free(r)?'free':'unknown';
      out.push({id,row:r,start:a,end:b,delta:vb-va,category});
    }
  }
  return out;
}
function statusStart(index,r){const h=index.histories.get(r.uuid)||[];let i=h.findIndex(x=>x.snapshot_at===r.snapshot_at);if(i<0)return {time:r.snapshot_at,open:true};const startIndex=i;while(i>0&&h[i-1].paymentStatus===r.paymentStatus&&index.times.indexOf(h[i].snapshot_at)===index.times.indexOf(h[i-1].snapshot_at)+1)i--;return {time:h[i].snapshot_at,open:i===0,startIndex};}
if(typeof module!=='undefined')module.exports={parseCSV,buildIndex,intervals,statusStart,day};
if(typeof document!=='undefined'){
const ROOT='https://raw.githubusercontent.com/antonina-katlinskaya/realt-collector/main/data/';
const $=id=>document.getElementById(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const fmt=x=>x==null?'—':Number(x).toLocaleString('ru-RU');
const date=t=>new Intl.DateTimeFormat('ru-RU',{timeZone:'Europe/Minsk',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(t));
const price=r=>fmt(number(r.price))+' '+({'978':'€','840':'$','933':'BYN'}[r.priceCurrency]||esc(r.priceCurrency));
const label=r=>r.payment_label||({'0':'Бесплатно','2':'Выделение','3':'Поднятие','4':'Спецразмещение'}[r.paymentStatus]||'Статус '+r.paymentStatus);
const known={'i.s.barashenko':'Ирина Барашенко','e.v.boriskina':'Елена Борискина','v.n.khatkovskaya':'Вероника Хатковская'};
const knownById={'77ff7ab0-6e68-11ee-818e-0935d63487ea':'Ирина Барашенко','ff985560-a80d-11f0-bfef-45b6701187ce':'Елена Борискина','d6a0a26a-26a6-11ec-ae6c-dee111c4eff3':'Вероника Хатковская'};
function agentName(r){const email=(r.contactEmail||'').split('@')[0];return knownById[r.userUuid]||known[email]||(r.contactName||'Без имени');}
let index,rows=[],seen=null,seenPromise=null,selectedTab='current',page=0,currentModel=null,loadSeq=0;
const matches=r=> (!$('agent').value||r.userUuid===$('agent').value)&&(!$('quarter').value|| (r.quarter||'(не определён)')===$('quarter').value)&&(!$('search').value||[r.title,r.address,r.code,agentName(r)].join(' ').toLowerCase().includes($('search').value.toLowerCase()))&&promoMatch(r);
function promoMatch(r){const p=$('promo').value;return !p||(p==='paid'?paid(r):p==='other'?![0,2,3,4].includes(number(r.paymentStatus)):r.paymentStatus===p);}
function model(){
  const from=$('from').value,to=$('to').value;
  const available=index.times.filter(t=>day(t)>=from&&day(t)<=to),end=available.at(-1);
  const current=end?[...index.byTime.get(end).values()].filter(matches):[];
  const activeIds=new Set(current.map(r=>r.uuid));
  const events=intervals(index,from,to).filter(e=>matches(e.row));
  const growth=new Map();for(const e of events)growth.set(e.id,(growth.get(e.id)||0)+e.delta);
  const first=new Map([...index.histories].map(([id,h])=>[id,h[0].snapshot_at]));
  const newly=current.filter(r=>day(first.get(r.uuid))>=from&&day(first.get(r.uuid))<=to);
  const gone=[];
  for(let i=1;i<index.times.length;i++){const a=index.times[i-1],b=index.times[i];if(day(b)<from||day(b)>to)continue;for(const [id,r]of index.byTime.get(a)){if(!index.byTime.get(b).has(id)&&!activeIds.has(id)&&matches(r))gone.push({...r,goneAt:b});}}
  const goneUnique=[...new Map(gone.map(r=>[r.uuid,r])).values()];
  let listing=selectedTab==='paid'?current.filter(paid):selectedTab==='new'?newly:selectedTab==='gone'?goneUnique:current;
  const sort=$('sort').value;listing=listing.slice().sort((a,b)=>sort==='growth'?(growth.get(b.uuid)||0)-(growth.get(a.uuid)||0):sort==='views'?(number(b.views)||0)-(number(a.views)||0):sort==='price'?(number(a.price)||0)-(number(b.price)||0):String(b.createdAt).localeCompare(String(a.createdAt)));
  return {from,to,end,current,events,growth,listing,newly,gone:goneUnique};
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
function render(){if(!index)return;const m=model();currentModel=m;
  if(m.from>m.to){$('status').textContent='Дата начала должна быть раньше даты окончания.';return;}
  const comparable=m.events.length>0,delta=m.events.reduce((s,e)=>s+e.delta,0),advertised=m.current.filter(paid).length;
  $('cards').innerHTML=[['Объявлений',m.current.length,'На последнем обходе выбранного периода'],['В продвижении',advertised,'По статусу на последнем обходе'],['Прирост просмотров',comparable?delta:null,'Только сопоставимые интервалы'],['Просмотры всего',m.current.reduce((s,r)=>s+(number(r.views)||0),0),'Общий счётчик выбранных объявлений']].map(([title,value,note])=>`<div class="card"><div class="kpi-label">${title}</div><strong>${fmt(value)}</strong><span>${note}</span></div>`).join('');
  $('status').textContent=m.end?'Состояние объявлений на '+date(m.end)+' · '+index.times.length+' снимков в истории':'Нет снимков до выбранной даты';
  const countTimes=index.times.filter(t=>day(t)>=m.from&&day(t)<=m.to).length;
  $('coverage').textContent=countTimes<2?'Пока в выбранном периоде меньше двух снимков. Прирост, длительность продвижения и время активности начнут уточняться с новыми обходами.':`${countTimes} снимков в выбранном периоде. Прирост за полностью покрытые интервалы: ${fmt(delta)}. При продвижении: ${fmt(m.events.filter(e=>e.category==='paid').reduce((s,e)=>s+e.delta,0))}; без продвижения: ${fmt(m.events.filter(e=>e.category==='free').reduce((s,e)=>s+e.delta,0))}; при смене / неизвестном статусе: ${fmt(m.events.filter(e=>e.category==='unknown').reduce((s,e)=>s+e.delta,0))}.`;
  const groups=new Map();for(const e of m.events){const k=e.end;if(!groups.has(k))groups.set(k,{paid:0,free:0,unknown:0,title:date(e.start)+' → '+date(e.end),label:date(e.end).slice(0,5)+' '+date(e.end).slice(-5)});groups.get(k)[e.category]+=e.delta;}
  $('traffic').innerHTML=svgBars([...groups.values()]);renderRanking(m);renderTable(m);
}
function renderRanking(m){const agents=new Map();for(const r of m.current){const id=r.userUuid;if(!agents.has(id))agents.set(id,{id,name:agentName(r),phone:r.contactPhone,count:0,paid:0,views:0,growth:0});const a=agents.get(id);a.count++;a.paid+=paid(r)?1:0;a.views+=number(r.views)||0;}
  for(const e of m.events){if(agents.has(e.row.userUuid))agents.get(e.row.userUuid).growth+=e.delta;}
  const key=$('rank').value;if(key==='growth'&&!m.events.length){$('ranking').innerHTML='<div class="empty">Для сравнения прироста нужны два снимка.</div>';return;}
  const list=[...agents.values()].sort((a,b)=>b[key]-a[key]).slice(0,10),max=Math.max(1,...list.map(a=>a[key]));
  $('ranking').innerHTML=list.map(a=>`<div class="barrow"><button data-agent="${esc(a.id)}" title="${esc(a.phone)}">${esc(a.name)}</button><div class="bartrack"><div class="bar" style="width:${a[key]/max*100}%"></div></div><b>${fmt(a[key])}</b></div>`).join('')||'<div class="empty">Нет объявлений по выбранным фильтрам</div>';
}
function renderTable(m){const size=40;page=Math.min(page,Math.max(0,Math.ceil(m.listing.length/size)-1));const part=m.listing.slice(page*size,(page+1)*size);
  $('listings').innerHTML=part.map(r=>{const st=statusStart(index,r),dv=m.growth.get(r.uuid);return `<tr><td>${esc(agentName(r))}<br><small>${esc(r.contactPhone)}</small></td><td class="title"><a href="https://realt.by/sale-flats/object/${encodeURIComponent(r.code)}/" target="_blank" rel="noopener">${esc(r.address||r.title)} ↗</a><br><small>${esc(r.code)} · ${esc(r.areaTotal)} м² · ${esc(r.storey)}/${esc(r.storeys)} эт. · ${esc(r.quarter||'дом не распознан')}</small>${r.goneAt?'<br><small>Отсутствует с '+date(r.goneAt)+'</small>':''}</td><td>${price(r)}</td><td><span class="badge ${paid(r)?'promo':''}">${esc(label(r))}</span></td><td>${date(st.time)}<br><small>${st.open?'Начало неизвестно':'Смена замечена между обходами'}</small></td><td>${fmt(number(r.views))}</td><td>${fmt(dv)}</td><td><button data-detail="${esc(r.uuid)}">История</button></td></tr>`;}).join('')||'<tr><td colspan="8" class="empty">Нет объявлений по выбранным фильтрам</td></tr>';
  $('rowcount').textContent=`${m.listing.length? page*size+1:0}–${Math.min((page+1)*size,m.listing.length)} из ${fmt(m.listing.length)}`;$('prev').disabled=page===0;$('next').disabled=(page+1)*size>=m.listing.length;
}
async function load(){const seq=++loadSeq;$('refresh').disabled=true;$('status').textContent='Загружаем снимки…';try{const response=await fetch(ROOT+'snapshots.csv?refresh='+Date.now(),{cache:'no-store'});if(!response.ok)throw Error('HTTP '+response.status);const text=await response.text();if(seq!==loadSeq)return;rows=parseCSV(text);index=buildIndex(rows);if(!index.times.length)throw Error('Снимки пока отсутствуют');const last=index.times.at(-1);$('freshness').textContent='Последний снимок: '+date(last);
  const agents=new Map();for(const t of index.times)for(const r of index.byTime.get(t).values())agents.set(r.userUuid,r);
  const prevAgent=$('agent').value,prevQuarter=$('quarter').value;
  $('agent').innerHTML='<option value="">Все агенты</option>'+[...agents.values()].sort((a,b)=>agentName(a).localeCompare(agentName(b),'ru')).map(r=>`<option value="${esc(r.userUuid)}">${esc(agentName(r))} · ${esc(r.contactPhone||r.userUuid.slice(0,8))}</option>`).join('');$('agent').value=prevAgent;
  $('quarter').innerHTML='<option value="">Все</option>'+[...new Set(rows.map(r=>r.quarter||'(не определён)'))].sort().map(q=>`<option>${esc(q)}</option>`).join('');$('quarter').value=prevQuarter;
  if(!$('from').value)$('from').value=day(index.times[0]);if(!$('to').value)$('to').value=day(last);seen=null;seenPromise=null;render();
}catch(e){$('status').textContent='Не удалось загрузить данные: '+e.message+'. Нажми «Обновить данные», чтобы повторить.';}finally{$('refresh').disabled=false;}}
function detailChart(h){if(!h.length)return '';const vals=h.filter(r=>number(r.views)!==null);if(!vals.length)return '<div class="empty">Счётчики не получены</div>';const W=740,H=210,min=0,max=Math.max(1,...vals.map(r=>Number(r.views)));const x=i=>48+(W-75)*i/Math.max(1,vals.length-1),y=v=>170-v/max*140;let s=`<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Общий счётчик просмотров объявления"><line x1="48" y1="170" x2="${W-15}" y2="170" stroke="#dce4ed"/><text x="40" y="30" text-anchor="end" font-size="11">${fmt(max)}</text><polyline points="${vals.map((r,i)=>x(i)+','+y(Number(r.views))).join(' ')}" fill="none" stroke="#396cc1" stroke-width="3"/>`;
  vals.forEach((r,i)=>{s+=`<circle cx="${x(i)}" cy="${y(Number(r.views))}" r="5" fill="${paid(r)?'#147b73':'#396cc1'}"><title>${date(r.snapshot_at)} · ${r.views} просмотров · ${esc(label(r))}</title></circle>`;if(vals.length<12||i%Math.ceil(vals.length/10)===0)s+=`<text x="${x(i)}" y="195" text-anchor="middle" font-size="10">${date(r.snapshot_at).slice(0,5)}</text>`;});return s+'</svg>';}
let lastFocused=null,detailSeq=0;
async function showDetail(id){const token=++detailSeq,h=index.histories.get(id)||[],r=h.filter(x=>day(x.snapshot_at)<=currentModel.to).at(-1)||h.at(-1);if(!r)return;const st=statusStart(index,r),duration=(Date.parse(r.snapshot_at)-Date.parse(st.time))/3600000;
  lastFocused=document.activeElement;$('drawer').hidden=false;$('close').focus();
  $('detail').innerHTML=`<div class="eyebrow">ОБЪЯВЛЕНИЕ ${esc(r.code)}</div><h2 id="detailtitle">${esc(r.title)}</h2><p>${esc(agentName(r))} · ${esc(r.address)} · ${esc(r.areaTotal)} м²</p><a href="https://realt.by/sale-flats/object/${encodeURIComponent(r.code)}/" target="_blank" rel="noopener">Открыть объявление на Realt ↗</a><div class="detailgrid"><div class="card">Цена<strong>${price(r)}</strong></div><div class="card">Продвижение<strong>${esc(label(r))}</strong></div><div class="card">Общий счётчик<strong>${fmt(number(r.views))}</strong></div></div><div class="notice">Текущий статус наблюдается с ${date(st.time)}. ${st.open?'Дата его начала до первого наблюдения неизвестна.':'Переход замечен между двумя обходами.'} Покрытый наблюдениями промежуток: ${fmt(Math.round(duration*10)/10)} ч. Непрерывность между обходами не гарантирована.</div><section class="panel"><h3>История общего счётчика</h3>${detailChart(h.filter(x=>day(x.snapshot_at)<=currentModel.to))}</section><section class="panel"><h3>Наблюдения по объявлению</h3><div class="tablewrap"><table><thead><tr><th>Начало сбора</th><th>Продвижение</th><th>Цена</th><th>Просмотры</th><th>Прирост</th></tr></thead><tbody>${h.filter(x=>day(x.snapshot_at)<=currentModel.to).map((x,i)=>{const p=h[i-1],a=number(x.views),b=p?number(p.views):null;return `<tr><td>${date(x.snapshot_at)}</td><td>${esc(label(x))}</td><td>${price(x)}</td><td>${fmt(a)}</td><td>${p&&a!==null&&b!==null&&a>=b?fmt(a-b):'—'}</td></tr>`;}).join('')}</tbody></table></div></section><section class="panel"><h3>Исходные исторические значения API</h3><p class="muted">Опорная дата запроса и возвращённое значение. Это не точное время визита клиента и не подтверждённая разбивка по дням.</p><div id="historyraw">Загружаем…</div></section>`;
  try{if(!seenPromise)seenPromise=fetch(ROOT+'listings_seen.json?refresh='+Date.now(),{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json();});seen=await seenPromise;if(token!==detailSeq||$('drawer').hidden)return;const hist=seen[id]?.history_views||{};$('historyraw').innerHTML=Object.keys(hist).length?'<table><thead><tr><th>Опорная дата</th><th>Значение API</th></tr></thead><tbody>'+Object.entries(hist).sort().map(([d,v])=>`<tr><td>${esc(d)}</td><td>${fmt(v)}</td></tr>`).join('')+'</tbody></table>':'Исторические значения отсутствуют';}catch(e){seenPromise=null;if(token===detailSeq)$('historyraw').textContent='История пока недоступна: '+e.message;}
}
function closeDetail(){$('drawer').hidden=true;detailSeq++;lastFocused?.focus();}
for(const id of ['from','to','agent','promo','quarter','sort','rank'])$(id).addEventListener('change',()=>{page=0;render();});$('search').addEventListener('input',()=>{page=0;render();});
$('quick').addEventListener('click',e=>{const b=e.target.closest('[data-days]');if(!b||!index)return;const today=day(new Date()),n=b.dataset.days;if(n==='all'){$('from').value=day(index.times[0]);$('to').value=day(index.times.at(-1));}else{const start=new Date(today+'T12:00:00Z');start.setUTCDate(start.getUTCDate()-Number(n)+1);$('from').value=start.toISOString().slice(0,10);$('to').value=today;}for(const x of $('quick').querySelectorAll('button'))x.classList.toggle('active',x===b);page=0;render();});
$('tabs').addEventListener('click',e=>{const b=e.target.closest('[data-tab]');if(!b)return;selectedTab=b.dataset.tab;for(const x of $('tabs').querySelectorAll('button'))x.classList.toggle('active',x===b);page=0;render();});
$('ranking').addEventListener('click',e=>{const b=e.target.closest('[data-agent]');if(b){$('agent').value=b.dataset.agent;page=0;render();}});
$('listings').addEventListener('click',e=>{const b=e.target.closest('[data-detail]');if(b)showDetail(b.dataset.detail);});$('close').onclick=closeDetail;$('drawer').onclick=e=>{if(e.target===$('drawer'))closeDetail();};document.addEventListener('keydown',e=>{if(e.key==='Escape')closeDetail();if(e.key==='Tab'&&!$('drawer').hidden){const els=[...$('drawer').querySelectorAll('button,a[href],input,select,summary')];if(e.shiftKey&&document.activeElement===els[0]){e.preventDefault();els.at(-1).focus();}else if(!e.shiftKey&&document.activeElement===els.at(-1)){e.preventDefault();els[0].focus();}}});
$('prev').onclick=()=>{page--;render();};$('next').onclick=()=>{page++;render();};$('refresh').onclick=load;
$('export').onclick=()=>{if(!currentModel)return;const keys=['agent','code','address','price','currency','promotion','views','views_delta','url'];const quote=x=>'"'+String(x??'').replace(/"/g,'""')+'"';const csv='\uFEFF'+[keys,...currentModel.listing.map(r=>[agentName(r),r.code,r.address,r.price,r.priceCurrency,label(r),r.views,currentModel.growth.get(r.uuid)??'', 'https://realt.by/sale-flats/object/'+r.code+'/'])].map(r=>r.map(quote).join(',')).join('\r\n');const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='realt-'+currentModel.from+'_'+currentModel.to+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
load();
}
