import csv,gzip,io,json,tempfile,unittest,zipfile
from pathlib import Path
from pipeline.archive import make_packet,verify_packet,archive_snapshot,tail,sha

class ArchiveTests(unittest.TestCase):
    def fixture(self,root):
        raw=root/'sample.json.gz';raw.write_bytes(gzip.compress(json.dumps({'snapshot_at':'2026-10-26T16:00:00Z','minsk_mir_objects':[{'uuid':'a','price':100}]}).encode(),mtime=0))
        csvfile=root/'snapshots.csv'
        with csvfile.open('w',newline='',encoding='utf-8-sig') as f:
            w=csv.DictWriter(f,['snapshot_at','uuid','price']);w.writeheader()
            for hour in (14,15,16):w.writerow({'snapshot_at':f'2026-10-26T{hour}:00:00Z','uuid':'a','price':str(100+hour)})
        return raw,csvfile
    def test_lossless_raw_and_only_current_csv_rows_with_digest(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw,csvfile=self.fixture(root)
            packet,meta=make_packet([raw],csvfile,'2026-10-26T16:00:00Z')
            self.assertEqual(verify_packet(packet),meta)
            with zipfile.ZipFile(io.BytesIO(packet)) as z:
                self.assertEqual(z.read(raw.name),raw.read_bytes())
                rows=list(csv.DictReader(io.StringIO(gzip.decompress(z.read('rows.csv.gz')).decode('utf-8-sig'))))
            self.assertEqual(len(rows),1);self.assertEqual(rows[0]['price'],'116')
            self.assertEqual(make_packet([raw],csvfile,'2026-10-26T16:00:00Z')[0],packet)
    def test_failed_remote_upload_never_adds_reference_or_changes_cache(self):
        class Fail:
            def publish(self,*a):raise RuntimeError('unverified upload')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw,csvfile=self.fixture(root);before=csvfile.read_bytes()
            with self.assertRaises(RuntimeError):archive_snapshot(root,[raw],{'snapshot_at':'2026-10-26T16:00:00Z','completed_at':'2026-10-26T16:01:00Z','rows':1},Fail())
            self.assertFalse((root/'archive').exists());self.assertEqual(csvfile.read_bytes(),before);self.assertTrue(raw.exists())
    def test_verified_archive_reference_idempotence_and_cache_bound(self):
        class Verified:
            def publish(self,packet,stamp):return {'verified':True,'sha256':sha(packet),'url':'https://example.invalid/verified','bytes':len(packet)}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);raw,csvfile=self.fixture(root);marker={'snapshot_at':'2026-10-26T16:00:00Z','completed_at':'2026-10-26T16:01:00Z','rows':1}
            archive_snapshot(root,[raw],marker,Verified());archive_snapshot(root,[raw],marker,Verified())
            self.assertEqual(len(json.loads((root/'archive'/'2026-10.json').read_text())['snapshots']),1)
            self.assertEqual(tail(csvfile)['recent_snapshots'],2)
            self.assertTrue(raw.exists())
