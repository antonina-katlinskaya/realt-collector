import copy
import unittest
from unittest.mock import patch

import collector


# One immutable createdAt per test object, with x older than a.
ORDER = {key: offset for offset, key in enumerate('xabcdef')}
def response(ids, total=4):
    return {'data': {'searchObjects': {'body': {
        'pagination': {'totalCount': total},
        'results': [{'uuid': uid,
                     'createdAt': f'2026-01-01T00:00:{ORDER[uid]:02d}+03:00'}
                    for uid in ids],
    }}}}


class Session:
    def __init__(self):
        self.passes = 0
        self.pages = []
        self.variables = []

    def begin_source_scan(self, agency):
        self.passes += 1
        self.pages = []


class PaginationRecoveryTests(unittest.TestCase):
    def collect(self, replies):
        session = Session()

        def fetch(s, query, variables, op):
            s.variables.append(copy.deepcopy(variables))
            if not getattr(s, 'source_pagination_probe', False):
                s.pages.append(variables['data']['pagination']['page'])
            value = next(replies)
            if isinstance(value, BaseException):
                raise value
            return value

        with patch.object(collector.C, 'PAGE_SIZE', 2), \
             patch.object(collector, 'gql', side_effect=fetch), \
             patch.object(collector, 'sleep_between'):
            result = collector.fetch_agency_listings(session, 'agency')
        return result, session

    def test_stable_created_at_sort_preserves_original_filter_and_page_size(self):
        rows, session = self.collect(iter([
            response(['a', 'b']), response(['c', 'd']), response(['a', 'b'])]))
        self.assertEqual([r['uuid'] for r in rows], ['a', 'b', 'c', 'd'])
        first = session.variables[0]['data']
        self.assertEqual(first['sort'], [{'by': 'createdAt', 'order': 'ASC'}])
        self.assertEqual(first['pagination'], {'page': 1, 'pageSize': 2})
        self.assertEqual(first['where']['agencyUuids'], ['agency'])
        self.assertEqual(first['where']['category'], collector.C.CATEGORY)

    def test_duplicate_page_restarts_without_retaining_failed_pages(self):
        replies = iter([response(['a', 'b']), response(['a', 'b']),
                        response(['a', 'b']), response(['c', 'd']), response(['a', 'b'])])
        rows, session = self.collect(replies)
        self.assertEqual([r['uuid'] for r in rows], ['a', 'b', 'c', 'd'])
        self.assertEqual(session.passes, 2)
        self.assertEqual(session.pages, [1, 2])

    def test_append_only_growth_adds_tail_page_without_restart(self):
        rows, session = self.collect(iter([
            response(['a', 'b'], 4),
            response(['c', 'd'], 5),
            response(['e'], 5),
            response(['a', 'b'], 5),
        ]))
        self.assertEqual([r['uuid'] for r in rows], ['a', 'b', 'c', 'd', 'e'])
        self.assertEqual(session.passes, 1)
        self.assertEqual(session.pages, [1, 2, 3])

    def test_shrinking_source_restarts_even_if_identifiers_are_unique(self):
        rows, session = self.collect(iter([
            response(['a', 'b'], 5), response(['c', 'd'], 4),
            response(['a', 'b'], 4), response(['c', 'd'], 4),
            response(['a', 'b'], 4),
        ]))
        self.assertEqual([r['uuid'] for r in rows], ['a', 'b', 'c', 'd'])
        self.assertEqual(session.passes, 2)

    def test_unique_but_missing_tail_is_rejected(self):
        with self.assertRaises(collector.SourcePaginationChanged):
            self.collect(iter([response(['a', 'b']), response(['c'])] * 3))

    def test_moving_head_restarts_even_without_duplicate_ids(self):
        rows, session = self.collect(iter([
            response(['a', 'b']), response(['c', 'd']), response(['x', 'a']),
            response(['x', 'a']), response(['b', 'c']), response(['x', 'a'])]))
        self.assertEqual([r['uuid'] for r in rows], ['x', 'a', 'b', 'c'])
        self.assertEqual(session.passes, 2)

    def test_persistent_duplicates_exhaust_bounded_budget(self):
        with self.assertRaisesRegex(collector.SourcePaginationChanged, 'repeated UUID'):
            self.collect(iter([response(['a', 'b']), response(['a', 'b'])] * 3))

    def test_created_at_reordering_cannot_be_saved(self):
        with self.assertRaisesRegex(collector.SourcePaginationChanged, 'order changed'):
            self.collect(iter([response(['a', 'b']), response(['d', 'c'])] * 3))

    def test_growth_without_complete_tail_cannot_be_saved(self):
        with self.assertRaises(collector.SourcePaginationChanged):
            self.collect(iter([response(['a', 'b'], 4),
                               response(['c', 'd'], 5),
                               response([], 5)] * 3))

    def test_block_does_not_enter_pagination_retry(self):
        class Blocked(BaseException):
            pass
        with self.assertRaises(Blocked):
            self.collect(iter([Blocked('403')]))


if __name__ == '__main__':
    unittest.main()
