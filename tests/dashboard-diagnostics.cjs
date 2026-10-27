'use strict';
const fs=require('node:fs');
const path=require('node:path');
const zlib=require('node:zlib');
const {parseCSV,buildIndex,intervals}=require('../docs/dashboard.js');
const raw=fs.readFileSync(process.argv[2]||'data/snapshots.csv','utf8');
const rows=parseCSV(raw);
if(process.argv.includes('--archive')){for(const filename of fs.readdirSync(process.env.ARCHIVE_DIR||'data/snapshots').filter(n=>n.endsWith('.csv.gz')&&n>='2026-10-20').sort()){const csv=zlib.gunzipSync(fs.readFileSync(path.join(process.env.ARCHIVE_DIR||'data/snapshots',filename))).toString('utf8');rows.push(...parseCSV(csv));}}
const idx=buildIndex(rows);
const from=idx.times.length?idx.times[0].slice(0,10):'2000-01-01';
const to=idx.times.length?idx.times.at(-1).slice(0,10):'2000-01-01';
const ev=intervals(idx,from,to);
const byCat={free:0,paid:0,unknown:0};
for(const e of ev)byCat[e.category]+=e.delta;
const byInterval=new Map();for(const e of ev){const key=e.start+' → '+e.end;byInterval.set(key,(byInterval.get(key)||0)+e.delta);}
const largest=ev.slice().sort((a,b)=>b.delta-a.delta).slice(0,20).map(e=>({id:e.id,code:e.row.code,start:e.start,end:e.end,delta:e.delta,status:e.row.paymentStatus,category:e.category}));
console.log(JSON.stringify({rows:rows.length,times:idx.times.length,first:idx.times[0],last:idx.times.at(-1),intervals:ev.length,total:ev.reduce((s,e)=>s+e.delta,0),byCat,byInterval:Object.fromEntries(byInterval),largest},null,2));
