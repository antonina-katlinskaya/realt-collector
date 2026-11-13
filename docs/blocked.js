'use strict';
const API='https://realt-blocked-private.katlinskaya-antonina.workers.dev';
const $=x=>document.getElementById(x);
const escapeHtml=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=x=>x?new Date(x).toLocaleString('ru-RU',{timeZone:'Europe/Minsk',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}):'—';
const num=x=>Number.isFinite(x)?new Intl.NumberFormat('ru-RU').format(x):'—';
let token='',all=[];
const PUBLIC_DATA='https://raw.githubusercontent.com/antonina-katlinskaya/realt-collector/main/data/';
let photoLookupAttempted=false;
function csvCodesToUuids(text,wanted){
 const map=new Map();let row=[],field='',quoted=false,headers=null,codeCol=-1,uuidCol=-1;
 const finish=()=>{row.push(field);field='';if(!headers){headers=row;codeCol=headers.indexOf('code');uuidCol=headers.indexOf('uuid');}
  else if(codeCol>=0&&uuidCol>=0&&wanted.has(row[codeCol]))map.set(row[codeCol],row[uuidCol]);row=[];};
 for(let i=0;i<text.length;i++){const c=text[i];
  if(c==='"'){if(quoted&&text[i+1]==='"'){field+='"';i++;}else quoted=!quoted;}
  else if(c===','&&!quoted){row.push(field);field='';}
  else if((c==='\n'||c==='\r')&&!quoted){if(c==='\r'&&text[i+1]==='\n')i++;if(field||row.length)finish();}
  else field+=c;
 }
 if(field||row.length)finish();return map;
}
async function recoverArchivedPhotos(){
 if(photoLookupAttempted||!all.length)return;photoLookupAttempted=true;
 const missing=all.filter(x=>!x.photoUrl);if(!missing.length)return;
 try{
  const [r1,r2]=await Promise.all([fetch(PUBLIC_DATA+'photo_manifest.json?refresh='+Date.now(),{cache:'no-store'}),fetch(PUBLIC_DATA+'snapshots.csv?refresh='+Date.now(),{cache:'no-store'})]);
  if(!r1.ok||!r2.ok)throw Error('Фотоархив не опубликован');
  const manifest=await r1.json(),matches=csvCodesToUuids(await r2.text(),new Set(missing.map(x=>String(x.id))));
  let found=0;
  for(const x of missing){const urls=manifest.images?.[matches.get(String(x.id))];
   if(Array.isArray(urls)&&urls.length){x.photoCandidates=urls.filter(url=>typeof url==='string'&&/^https:\/\//.test(url)).slice(0,8);if(x.photoCandidates.length){x.photoUrl=x.photoCandidates[0];found++;}}
  }
  if(found)render();
  else if(!all.some(x=>x.photoUrl))$('status').textContent+=' В сохранённых публичных снимках фотографии этих объявлений пока не найдены.';
 }catch(e){$('status').textContent+=' Фотоархив временно недоступен; основные записи сохранены.';}
}
document.addEventListener('error',e=>{
 const img=e.target;if(!img.matches?.('img[data-block-photo]'))return;
 const code=img.dataset.blockPhoto,entry=all.find(x=>String(x.id)===code),urls=entry?.photoCandidates||[entry?.photoUrl].filter(Boolean);
 const next=Number(img.dataset.photoIndex||0)+1;
 if(next<urls.length){img.dataset.photoIndex=String(next);img.src=urls[next];return;}
 const fallback=document.createElement('span');fallback.textContent='Фото недоступно';img.replaceWith(fallback);
},true);

function readToken(){
 const param=new URLSearchParams(location.hash.slice(1)).get('access');
 if(param){localStorage.setItem('realt_blocked_read_token',param);history.replaceState(null,'',location.pathname+location.search);return param;}
 return localStorage.getItem('realt_blocked_read_token')||'';
}
function render(){
 const q=$('search').value.trim().toLocaleLowerCase('ru'),scope=$('scope').value,sort=$('sort').value;
 let data=all.filter(x=>(scope==='all'||x.detectionType===scope)&&(!q||[x.id,x.address,x.employeeEmail,x.description].some(v=>String(v||'').toLocaleLowerCase('ru').includes(q))));
 data.sort((a,b)=>sort==='views'?(b.views??-1)-(a.views??-1):sort==='old'?Date.parse(a.firstDetectedAt||0)-Date.parse(b.firstDetectedAt||0):Date.parse(b.firstDetectedAt||0)-Date.parse(a.firstDetectedAt||0));
 $('shown').textContent='Показано '+data.length+' из '+all.length;
 $('cards').innerHTML=data.map(x=>{
   const safeId=/^\d{4,12}$/.test(String(x.id))?String(x.id):'';
   const link='https://realt.by/sale-flats/object/'+safeId+'/';
   const photo=x.photoUrl&&/^https:\/\//.test(x.photoUrl)?'<img loading="lazy" decoding="async" data-block-photo="'+escapeHtml(x.id)+'" data-photo-index="0" referrerpolicy="no-referrer" src="'+escapeHtml(x.photoUrl)+'" alt="Объявление">':'Фото пока недоступно';
   const address=escapeHtml(x.address||x.description||'Адрес не указан');
   return '<article class="card"><div class="photo">'+photo+'<span class="blocked">Заблокировано</span></div><div class="details"><h3>'+address+'</h3><div class="muted">'+escapeHtml(x.description||'')+'</div><span class="badge">'+escapeHtml(x.employeeEmail||'Учётная запись Realt')+'</span><div><a href="'+link+'" target="_blank" rel="noopener noreferrer">Объявление №'+safeId+'</a></div><div class="stat"><span>Просмотры</span><strong>'+num(x.views)+'</strong></div><div class="stat"><span>Даты на Realt</span><strong>'+escapeHtml((x.datesObserved||[]).join(' / ')||'—')+'</strong></div><div class="stat"><span>Обнаружено</span><strong>'+date(x.firstDetectedAt)+'</strong></div><div class="info">'+(x.detectionType==='initial_baseline'?'Было заблокировано до первого сбора':'Впервые замечено после запуска')+'</div></div></article>';
 }).join('')||'<div class="muted">Записей по выбранным фильтрам нет.</div>';
}
async function load(){
 if(!token){$('authPanel').classList.remove('hidden');$('content').classList.add('hidden');return;}
 $('reload').disabled=true;
 try{
  const r=await fetch(API+'/data',{headers:{Authorization:'Bearer '+token},cache:'no-store'});
  if(r.status===401){$('authError').textContent='Неверный ключ доступа.'; $('authPanel').classList.remove('hidden');$('content').classList.add('hidden');return;}
  if(!r.ok)throw Error('Сервис вернул код '+r.status);
  const j=await r.json(),data=j.data||{};
  all=Object.values(data.items||{});$('total').textContent=num(all.length);
  $('latestCount').textContent=num(data.lastScan?.count);
  $('lastSync').textContent=date(data.updatedAt);
  $('status').textContent=data.updatedAt?'Последнее получение данных: '+date(data.updatedAt)+' · проверок страниц: '+(data.lastScan?.pages||'—'):'Общий журнал пуст: данные из Opera ещё не поступали на сервер. Вводить сюда пароль Realt не нужно — требуется ключ просмотра из защищённой ссылки. Местный архив остаётся в Opera.';
  $('authPanel').classList.add('hidden');$('content').classList.remove('hidden');render();recoverArchivedPhotos();
 }catch(e){$('status').textContent='Ошибка загрузки: '+e.message;$('authPanel').classList.add('hidden');$('content').classList.remove('hidden');}
 finally{$('reload').disabled=false;}
}
$('connect').addEventListener('click',()=>{token=$('token').value.trim();if(token)localStorage.setItem('realt_blocked_read_token',token);load();});
$('reload').addEventListener('click',load);
$('share').addEventListener('click',async()=>{if(!token){alert('Сначала откройте журнал с ключом доступа.');return;}const link=location.origin+location.pathname+'#access='+encodeURIComponent(token);try{await navigator.clipboard.writeText(link);$('share').textContent='Ссылка скопирована';setTimeout(()=>$('share').textContent='Скопировать ссылку для сестры',2800);}catch(e){prompt('Скопируйте защищённую ссылку:',link);}});
for(const id of ['sort','scope'])$(id).addEventListener('change',render);
$('search').addEventListener('input',render);
token=readToken();load();
setInterval(()=>{if(token)load();},5*60*1000);
