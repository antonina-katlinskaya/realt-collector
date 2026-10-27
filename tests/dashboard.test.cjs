'use strict';
const { test } = require('node:test');
const assert = require('node:assert/strict');
const {parseCSV,buildIndex,intervals,periodData,statusStart} = require('../docs/dashboard.js');
const t1='2026-10-25T09:00:00Z', t2='2026-10-25T10:00:00Z', t3='2026-10-25T11:00:00Z';
const row=(uuid,snapshot_at,views,paymentStatus='0')=>({uuid,snapshot_at,views:String(views),paymentStatus,userUuid:'agent',title:'Квартира',price:'50000'});
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
