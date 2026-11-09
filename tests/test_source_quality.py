import datetime as dt
import unittest

from pipeline.source_quality import assess_drop, verify_pages, diagnose_uuid_integrity


class SourceQualityTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {"snapshot_at": "2026-10-28T16:50:00Z", "rows": 1424}
        self.first = "2026-11-03T11:00:00Z"
        self.second = "2026-11-03T11:40:00Z"

    def test_complete_pages(self):
        pages = [{"agency": "a", "page": 1, "total": 65, "returned": 30},
                 {"agency": "a", "page": 2, "total": 65, "returned": 30},
                 {"agency": "a", "page": 3, "total": 65, "returned": 5}]
        self.assertEqual(verify_pages(pages, ["a"], 30)["a"]["retrieved"], 65)
        with self.assertRaisesRegex(RuntimeError, "Incomplete"):
            verify_pages(pages[:2], ["a"], 30)
        with self.assertRaisesRegex(RuntimeError, "materially"):
            verify_pages([pages[0], {**pages[1], "returned": 18}, pages[2]], ["a"], 30)

    def test_bounded_tail_growth_is_complete(self):
        pages = [
            {"agency": "a", "page": 1, "total": 4, "returned": 2},
            {"agency": "a", "page": 2, "total": 5, "returned": 2},
            {"agency": "a", "page": 3, "total": 5, "returned": 1},
        ]
        self.assertEqual(verify_pages(pages, ["a"], 2)["a"],
                         {"reported": 5, "retrieved": 5, "pages": 3})

    def test_incomplete_growth_cannot_be_accepted(self):
        pages = [
            {"agency": "a", "page": 1, "total": 4, "returned": 2},
            {"agency": "a", "page": 2, "total": 5, "returned": 2},
        ]
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            verify_pages(pages, ["a"], 2)

    def test_shrinking_source_is_not_mistaken_for_growth(self):
        pages = [
            {"agency": "a", "page": 1, "total": 5, "returned": 2},
            {"agency": "a", "page": 2, "total": 4, "returned": 2},
        ]
        with self.assertRaisesRegex(RuntimeError, 'shrank'):
            verify_pages(pages, ["a"], 2)

    def test_never_accept_first_major_drop(self):
        ids = [f"uuid-{n}" for n in range(900)]
        ok, candidate, why = assess_drop(self.baseline, 900, ids, self.first)
        self.assertFalse(ok)
        self.assertEqual(candidate["rows"], 900)
        self.assertIn("first", why)

    def test_corroborated_drop_acceptance(self):
        ids = [f"uuid-{n}" for n in range(900)]
        _, candidate, _ = assess_drop(self.baseline, 900, ids, self.first)
        later_ids = ids[:860] + [f"other-{n}" for n in range(40)]
        ok, new_candidate, why = assess_drop(self.baseline, 900, later_ids, self.second, candidate)
        self.assertTrue(ok)
        self.assertIsNone(new_candidate)
        self.assertIn("corroborated", why)

    def test_frequent_full_scans_do_not_postpone_confirmation_forever(self):
        ids=[f'uuid-{n}' for n in range(900)]
        _,candidate,_=assess_drop(self.baseline,900,ids,self.first)
        for stamp in ['2026-11-03T11:10:00Z','2026-11-03T11:19:00Z']:
            accepted,candidate,_=assess_drop(self.baseline,900,ids,stamp,candidate)
            self.assertFalse(accepted)
            self.assertEqual(candidate['observed_at'],self.first)
        self.assertTrue(assess_drop(self.baseline,900,ids,'2026-11-03T11:21:00Z',candidate)[0])

    def test_inconsistent_or_repeated_snapshot_not_accepted(self):
        ids = [f"uuid-{n}" for n in range(900)]
        _, candidate, _ = assess_drop(self.baseline, 900, ids, self.first)
        self.assertFalse(assess_drop(self.baseline, 900, ids, self.first, candidate)[0])
        changed = [f"other-{n}" for n in range(900)]
        self.assertFalse(assess_drop(self.baseline, 900, changed, self.second, candidate)[0])
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            assess_drop(self.baseline, 900, ids[:-1] + [ids[0]], self.second, candidate)

    def test_uuid_anomaly_report_preserves_both_duplicate_pages(self):
        objects = [
            {"uuid": "same", "code": 11},
            {"uuid": "other", "code": 12},
            {"uuid": "same", "code": 11},
            {"uuid": "", "code": 13},
        ]
        pages = [
            {"agency": "x", "page": 1, "total": 4,
             "identifiers": [{"uuid": "same", "code": "11"}, {"uuid": "other", "code": "12"}]},
            {"agency": "x", "page": 2, "total": 4,
             "identifiers": [{"uuid": "same", "code": "11"}, {"uuid": "", "code": "13"}]},
        ]
        report = diagnose_uuid_integrity(objects, pages, "source.json")
        self.assertFalse(report["valid"])
        self.assertEqual(report["missing_uuid_count"], 1)
        self.assertEqual(report["duplicate_uuid_count"], 1)
        self.assertEqual(report["duplicate_extra_rows"], 1)
        self.assertEqual(report["duplicate_samples"], [{"uuid": "same", "occurrences": 2}])
        self.assertEqual([p["page"] for p in report["affected_pages"]], [1, 2])
        self.assertEqual(report["affected_pages"][1]["anomaly_count"], 2)

    def test_uuid_anomaly_report_does_not_normalize_or_ignore_duplicates(self):
        self.assertTrue(diagnose_uuid_integrity(
            [{"uuid": "a"}, {"uuid": "b"}], [], "source.json")["valid"])
        self.assertFalse(diagnose_uuid_integrity([], [], "source.json")["valid"])
        self.assertFalse(diagnose_uuid_integrity(
            [{"uuid": "x"}, {"uuid": "x"}], [], "source.json")["valid"])

    def test_normal_complete_count_does_not_need_corroboration(self):
        ids = [f"id-{i}" for i in range(1250)]
        self.assertTrue(assess_drop(self.baseline, 1250, ids, self.first)[0])


if __name__ == "__main__":
    unittest.main()

