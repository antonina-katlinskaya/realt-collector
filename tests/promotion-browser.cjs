
'use strict';
const {chromium}=require('playwright'),fs=require('node:fs'),assert=require('node:assert/strict');
const {parseCSV}=require('../docs/dashboard.js');
(async()=>{
 const ids=new Set(JSON.parse(fs.readFileSync('data/developer_manifest.json','utf8')).ids);
 const raw=parseCSV(fs.readFileSync('data/snapshots.csv','utf8')).filter(r=>ids.has(r.uuid));
 const agents=['ff985560-a80d-11f0-bfef-45b6701187ce','77ff7ab0-6e68-11ee-818e-0935d63487ea','cd9285f2-3506-4986-af06-7749b55924e7'];
 const rows=agents.map(id=>raw.find(r=>r.userUuid===id));assert.ok(rows.every(Boolean),'verified agent fixtures available');
 const keys=Object.keys(rows[0]),quote=x=>'"'+String(x??'').replaceAll('"','""')+'"',out=[];
 for(let d=27;d<=29;d++)for(let h=14;h<=17;h++)for(let i=0;i<rows.length;i++)out.push({...rows[i],snapshot_at:'2026-10-'+d+'T'+h+':00:00Z',views:String(10+(d-27)*20+(h-14)*(i+1)),paymentStatus:i===1?'3':'2',payment_label:i===1?'Поднятие':'Выделение'});
 const csv=[keys,...out.map(r=>keys.map(k=>r[k]))].map(r=>r.map(quote).join(',')).join('\n');
 const browser=await chromium.launch({headless:true});
 try{
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.clock.setFixedTime(new Date('2026-10-29T18:00:00Z'));
 await page.route('**/*',async route=>{
  const u=new URL(route.request().url()),name=u.pathname.split('/').at(-1)||'index.html';
  if(u.hostname==='antonina-katlinskaya.github.io'&&['index.html','dashboard.js','kufar-cards.css'].includes(name))return route.fulfill({path:'docs/'+name,contentType:name.endsWith('.js')?'application/javascript':name.endsWith('.css')?'text/css':'text/html'});
  const cors={'access-control-allow-origin':'*'};
  if(u.hostname==='raw.githubusercontent.com'){
   if(name==='snapshots.csv')return route.fulfill({body:csv,headers:cors});
   if(name==='developer_manifest.json')return route.fulfill({path:'data/'+name,headers:cors});
   if(name==='photo_manifest.json')return route.fulfill({body:'{"images":{}}',contentType:'application/json',headers:cors});
   return route.fulfill({status:404,body:'',headers:cors});
  }
  return route.abort();
 });
 await page.goto('https://antonina-katlinskaya.github.io/realt-collector/',{waitUntil:'domcontentloaded'});
 await page.waitForFunction(()=>document.querySelector('#promoOverviewKpi')?.children.length);
 const summary=page.locator('#employeeSummary'),open=()=>page.locator('#employeeDropdown').evaluate(e=>e.open);
 assert.equal(await page.locator('#multiAgents').getByText('Елена Довгун',{exact:true}).count(),1);
 await summary.click();assert.equal(await open(),true);await summary.click();assert.equal(await open(),false);
 await summary.click();await page.keyboard.press('Escape');assert.equal(await open(),false);
 await summary.click();await page.locator('h1').click();assert.equal(await open(),false);
 await summary.click();await page.locator('#closeEmployees').click();assert.equal(await open(),false);
 await summary.click();await page.locator('#employeeSearch').fill('Довгун');await page.locator('#multiAgents').getByText('Елена Довгун',{exact:true}).click();assert.equal(await summary.innerText(),'Выбрано: 1');
 await page.locator('#closeEmployees').click();await summary.click();await page.locator('#clearEmployees').click();await page.locator('#closeEmployees').click();assert.equal(await summary.innerText(),'Все сотрудники');
 await page.locator('[data-days="custom"]').click();assert.equal(await page.locator('#customDates').isVisible(),true);
 await page.locator('[data-days="7"]').click();assert.equal(await page.locator('#customDates').isVisible(),false);
 await page.locator('[data-rooms="4+"]').click();assert.equal(await page.locator('#rooms').inputValue(),'4+');await page.locator('[data-rooms="4+"]').click();assert.equal(await page.locator('#rooms').inputValue(),'');
 assert.equal(await page.locator('.promo-agent').count(),3);assert.equal(await page.locator('.promo-place').count(),3);
 const colors=await page.locator('[data-days="7"]').evaluate(e=>({background:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color}));
 assert.deepEqual(colors,{background:'rgb(31, 95, 74)',color:'rgb(255, 255, 255)'});
 const first=page.locator('#promoEmployeeChips button').nth(1);await first.click();const name=await first.innerText();
 assert.ok((await page.locator('#promoPeriods tbody tr td:first-child').allTextContents()).every(n=>n===name));
 await page.locator('#promoEmployeeChips button').first().click();
 const legend=page.locator('#promoChartLegend button').first();await legend.click();assert.equal(await legend.getAttribute('aria-pressed'),'false');await legend.click();assert.equal(await legend.getAttribute('aria-pressed'),'true');
 await page.locator('#promoPeriods [data-detail]').first().click();assert.equal(await page.locator('#drawer').isVisible(),true);await page.locator('#close').click();
 fs.mkdirSync('test-results',{recursive:true});await page.screenshot({path:'test-results/promotion-desktop.png',fullPage:true});
 for(const view of ['ads','employees','works','leaders','promotion']){await page.locator('[data-view="'+view+'"]').click();assert.equal(await page.locator('[data-section="'+view+'"]').first().isVisible(),true);}
 await page.setViewportSize({width:390,height:844});await summary.click();await page.keyboard.press('Escape');
 const dims=await page.evaluate(()=>({viewport:innerWidth,page:document.documentElement.scrollWidth}));assert.equal(dims.viewport,dims.page);
 await page.screenshot({path:'test-results/promotion-mobile.png',fullPage:true});assert.deepEqual(errors,[]);
 console.log('Verified employee identity; four close paths; search and selection; periods; rooms; cards; colors; ad filter; chart legend; history; five tabs; mobile layout.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
