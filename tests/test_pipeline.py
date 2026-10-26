import csv
import datetime as dt
import gzip
from pathlib import Path
import tempfile
import unittest
from pipeline.schedule import slots,due,UTC
from pipeline.storage import rotate
from pipeline.cadence import choose
from pipeline.budget import evaluate


class ScheduleTests(unittest.TestCase):
    def test_daytime_slots(self):
        day=dt.date(2026,10,26)
        self.assertEqual(len(slots(day,60)),15)
        self.assertEqual(len(slots(day,30)),30)
        self.assertEqual(slots(day,30)[0].strftime("%H:%M"),"07:10")
        self.assertEqual(slots(day,30)[-1].strftime("%H:%M"),"21:40")
    def test_no_night_and_no_fresh_repeat(self):
        self.assertFalse(due("",dt.datetime(2026,10,26,20,tzinfo=UTC)))
        now=dt.datetime(2026,10,26,5,12,tzinfo=UTC)
        self.assertTrue(due("2026-10-26T04:10:00Z",now))
        self.assertFalse(due("2026-10-26T05:11:00Z",now))
    def test_unknown_or_high_budget_cannot_promote(self):
        now=dt.datetime(2026,10,27,12,tzinfo=UTC)
        h=[{"status":"ok","started_at":(now-dt.timedelta(hours=30-i)).isoformat(),"duration_seconds":600} for i in range(15)]
        self.assertEqual(choose(h,{"safe":False},now)[0],60)
        self.assertEqual(choose(h,{"safe":True},now)[0],30)
        h[-1]["http_429"]=1
        self.assertEqual(choose(h,{"safe":True},now)[0],60)
    def test_account_total_includes_all_databases(self):
        r=evaluate([{"sum":{"rowsRead":3500000,"rowsWritten":30000}},{"sum":{"rowsRead":600000,"rowsWritten":2000}}])
        self.assertFalse(r["safe"])
        self.assertEqual(r["rows_read"],4100000)


class StorageTests(unittest.TestCase):
    def test_lossless_idempotent_rotation_and_bounded_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);file=root/"snapshots.csv"
            rows=[{"snapshot_at":f"2026-10-{20+i//24:02d}T{i%24:02d}:00:00Z","uuid":"x","price":str(i)} for i in range(60)]
            with file.open("w",encoding="utf-8-sig",newline="") as f:
                w=csv.DictWriter(f,list(rows[0]));w.writeheader();w.writerows(rows)
            rotate(root)
            def history():
                out=[]
                for p in sorted((root/"snapshots").glob("*.gz")):
                    with gzip.open(p,"rt",encoding="utf-8-sig",newline="") as f:out.extend(csv.DictReader(f))
                return out
            self.assertEqual(history(),rows)
            rotate(root);self.assertEqual(history(),rows)
            with file.open(encoding="utf-8-sig") as f:self.assertEqual(len(list(csv.DictReader(f))),32)

class TransactionTests(unittest.TestCase):
    def test_failed_original_collector_preserves_source_and_restores_paths(self):
        from unittest.mock import patch
        import pipeline.collect as job
        import config
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);data=root/'data';data.mkdir()
            marker=data/'collection_state.json';marker.write_text('{"complete":true,"snapshot_at":"old"}')
            old_paths={k:getattr(config,k) for k in ('DATA_DIR','RAW_DIR','REPORTS_DIR','SNAPSHOTS_CSV','SEEN_JSON')}
            with patch.object(job,'DATA',data),patch.object(job,'HEALTH',data/'health'),patch.object(job.collector,'run',side_effect=RuntimeError('source incomplete')):
                with self.assertRaisesRegex(RuntimeError,'source incomplete'):job.run()
            self.assertEqual(marker.read_text(),'{"complete":true,"snapshot_at":"old"}')
            self.assertEqual(old_paths,{k:getattr(config,k) for k in old_paths})
            import json
            self.assertEqual(json.loads((data/'health'/'collection_runs.json').read_text())[-1]['status'],'failed')
