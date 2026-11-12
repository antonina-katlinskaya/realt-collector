'use strict';
const API='https://realt-blocked-private.katlinskaya-antonina.workers.dev';
const $=x=>document.getElementById(x);
const escapeHtml=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date=x=>x?new Date(x).toLocaleString('ru-RU',{timeZone:'Europe/Minsk',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}):'—';
const num=x=>Number.isFinite(x)?new Intl.NumberFormat('ru-RU').format(x):'—';
let token='',all=[];
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
   const photo=x.photoUrl&&/^https:\/\//.test(x.photoUrl)?'<img loading="lazy" referrerpolicy="no-referrer" src="'+escapeHtml(x.photoUrl)+'" alt="Объявление" onerror="this.remove();this.parentElement.insertAdjacentText(\'beforeend\',\'Фото недоступно\')">':'Фото недоступно';
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
  $('status').textContent=data.updatedAt?'Последнее получение данных: '+date(data.updatedAt)+' ·  проверок страниц: '+(data.lastScan?.pages||'—'):'Пока нет загруженных данных. Начальный архив остаётся в Opera.';
  $('authPanel').classList.add('hidden');$('content').classList.remove('hidden');render();
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
