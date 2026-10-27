'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const {parseCSV,buildIndex,intervals,periodData,statusStart,promotionPeriods,promotionSummary} = require('../docs/dashboard.js');
const t1='2026-10-25T09:00:00Z', t2='2026-10-25T10:00:00Z', t3='2026-10-25T11:00:00Z';
const row=(uuid,snapshot_at,views,paymentStatus='0')=>({uuid,snapshot_at,views:String(views),paymentStatus,userUuid:'agent',title:'Квартира',price:'50000'});
test('promotion history splits when the listing is absent from an intervening snapshot',()=>{
 const idx=buildIndex([row('a',t1,10,'2'),row('other',t2,1),row('a',t3,15,'2')]);
 const spans=promotionPeriods(idx,'2026-10-25','2026-10-25');
 assert.equal(spans.length,2);
 assert.equal(spans[1].reason,'missing');
 assert.equal(spans[1].last,t1);
 assert.equal(spans[1].next,t2);
 assert.equal(spans[0].reason,'latest');
});
test('selected dates retain the original promotion start and last confirmed paid snapshot',()=>{
 const before='2026-10-24T09:00:00Z';
 const idx=buildIndex([row('a',before,5,'2'),row('a',t1,10,'2'),row('a',t2,11,'0')]);
 const [span]=promotionPeriods(idx,'2026-10-25','2026-10-25');
 assert.equal(span.start,before);
 assert.equal(span.last,t1);
 assert.equal(span.next,t2);
 assert.equal(span.reason,'changed');
});
test('promotion history obeys exact bounds and promotion filters without joining different statuses',()=>{
 const idx=buildIndex([row('a',t1,10,'2'),row('a',t2,13,'3'),row('a',t3,15,'2')]);
 const spans=promotionPeriods(idx,'2026-10-25','2026-10-25',r=>r.paymentStatus==='2',{start:Date.parse(t2),end:Date.parse(t3)});
 assert.equal(spans.length,1);
 assert.equal(spans[0].start,t3);
});
test('a paid period missing from the latest snapshot is not marked currently promoted',()=>{
 const idx=buildIndex([row('a',t1,10,'2'),row('a',t2,13,'2'),row('other',t3,1)]);
 const [span]=promotionPeriods(idx,'2026-10-25','2026-10-25');
 assert.equal(span.reason,'missing');
 assert.equal(span.last,t2);
});
test('a change of employee splits promotion attribution',()=>{
 const idx=buildIndex([row('a',t1,10,'2'),{...row('a',t2,13,'2'),userUuid:'second'}]);
 const spans=promotionPeriods(idx,'2026-10-25','2026-10-25');
 assert.equal(spans.length,2);
 assert.equal(spans[0].row.userUuid,'second');
 assert.equal(spans[1].row.userUuid,'agent');
});
test('CSV supports quoted commas and newlines',()=>{
  assert.deepEqual(parseCSV('a,b\n"hello, there","one\ntwo"\n'),[{a:'hello, there',b:'one\ntwo'}]);
});
test('view growth counts only comparable consecutive snapshots',()=>{
  const idx=buildIndex([row('a',t1,10),row('a',t2,15),row('a',t3,12)]);
  const events=intervals(idx,'2026-10-25','2026-10-25');
  assert.equal(events.length,1);
  assert.equal(events[0].delta,5);
});
test('promotion transitions are unknown rather than attributed to advertising',()=>{
  const idx=buildIndex([row('a',t1,10,'0'),row('a',t2,18,'2')]);
  assert.equal(intervals(idx,'2026-10-25','2026-10-25')[0].category,'unknown');
});
test('a baseline snapshot is not considered a new listing',()=>{
  const idx=buildIndex([row('a',t1,10),row('a',t2,15),row('b',t2,2)]);
  const m=periodData(idx,'2026-10-25','2026-10-25');
  assert.deepEqual(m.newly.map(x=>x.uuid),['b']);
});
test('unchanged promotion status starts at first available observation',()=>{
  const idx=buildIndex([row('a',t1,10,'2'),row('a',t2,15,'2')]);
  const st=statusStart(idx,idx.histories.get('a')[1]);
  assert.equal(st.time,t1);
  assert.equal(st.open,true);
});

const fs=require('node:fs');
test('five priority tabs exist and selected default is promotion',()=>{const html=fs.readFileSync(require('node:path').join(__dirname,'../docs/index.html'),'utf8');for(const label of ['Продвижение','Объявления за период','Сотрудники','Топ органика','Топ продвижение'])assert.ok(html.includes('>'+label+'</button>'),label);assert.match(html,/data-view="promotion" class="active"/);assert.match(html,/data-section="promotion"/);});

test('freshness uses the current Minsk hourly schedule',()=>{const {collectionFreshness}=require('../docs/dashboard.js');const now=Date.parse('2026-10-27T09:00:00Z');assert.equal(collectionFreshness('2026-10-27T08:30:00Z',now).stale,false);assert.equal(collectionFreshness('2026-10-26T16:32:00Z',now).stale,true);});

test('recovered counter values are not counted as new views',()=>{const idx=buildIndex([row('a',t1,100),row('a',t2,5),row('a',t3,101)]);const ev=intervals(idx,'2026-10-25','2026-10-25');assert.equal(ev.length,1);assert.equal(ev[0].delta,1);});

test('Kufar-style filters have one outer disclosure',()=>{const html=fs.readFileSync(require('node:path').join(__dirname,'../docs/index.html'),'utf8');assert.equal((html.match(/id="filterBox"/g)||[]).length,1);assert.equal((html.match(/class="panel filterbox"/g)||[]).length,0);assert.equal((html.match(/id="quick"/g)||[]).length,1);});

test('declining view counter excludes all of that listing from ranked growth without deleting raw data',()=>{
 const idx=buildIndex([row('stable',t1,10),row('stable',t2,14),row('stable',t3,17),row('unstable',t1,12),row('unstable',t2,33000),row('unstable',t3,9)]);
 const m=periodData(idx,'2026-10-25','2026-10-25');
 assert.equal(m.growth.get('stable'),7);
 assert.equal(m.growth.has('unstable'),false);
 assert.equal(m.unstableIds.has('unstable'),true);
 assert.ok(m.excludedEvents.some(e=>e.id==='unstable'&&e.delta===32988));
 assert.equal(idx.histories.get('unstable').length,3);
});

test('ranking excludes all pre-fix intervals but preserves raw history',()=>{
 const idx=buildIndex([row('a',t1,3),row('a',t2,30000),row('a',t3,4)]);
 const m=periodData(idx,'2026-10-25','2026-10-25',()=>true,null,'2026-10-25T10:30:00Z');
 assert.equal(m.events.length,0);
 assert.equal(m.excludedLegacyEvents,1);
 assert.equal(m.observed.length,1);
 assert.equal(idx.histories.get('a').length,3);
});

test('organic view renders gallery cards as well as table',()=>{
 const js=require('node:fs').readFileSync(require('node:path').join(__dirname,'../docs/dashboard.js'),'utf8');
 const body=js.split('function renderWorks(m){')[1].split('\nfunction renderPlacements(m)')[0];
 assert.match(body,/renderGallery\(m\);/);
});


test('promotion summary counts an ad once across two promotion types on the same day',()=>{
 const idx=buildIndex([row('a',t1,10,'2'),row('a',t2,12,'2'),row('a',t3,15,'3')]);
 const summary=promotionSummary(idx,periodData(idx,'2026-10-25','2026-10-25'));
 assert.equal(summary.ads.size,1);assert.equal(summary.adDays.size,1);
 assert.equal(summary.ads.get('a').views,2);assert.equal(summary.types.size,2);
 assert.equal(summary.agents.get('agent').days.size,1);
});
test('no comparable views remains missing rather than a measured zero',()=>{
 const idx=buildIndex([row('a',t1,10,'2')]);
 const summary=promotionSummary(idx,periodData(idx,'2026-10-25','2026-10-25'));
 assert.equal(summary.ads.get('a').measured,0);
 assert.equal(summary.events.length,0);assert.equal(summary.ads.size,1);
});
test('employee transfer does not credit the transfer interval as promotion performance',()=>{
 const idx=buildIndex([row('a',t1,10,'2'),{...row('a',t2,12,'2'),userUuid:'second'}]);
 const summary=promotionSummary(idx,periodData(idx,'2026-10-25','2026-10-25'));
 assert.equal(summary.events.length,0);assert.equal(summary.agents.get('second').measured,0);
});
