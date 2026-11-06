import copy
import unittest
from unittest.mock import patch
import collector


def response(ids, total=4):
    return {'data': {'searchObjects': {'body': {
        'pagination': {'totalCount': total},
        'results': [{'uuid': uid} for uid in ids],
    }}}}


class Session:
    def __init__(self):
        self.passes = 0
        self.pages = []

    def begin_source_scan(self, agency):
        self.passes += 1
        self.pages = []


class PaginationRecoveryTests(unittest.TestCase):
    def collect(self, replies):
        session = Session()
        def fetch(s, query, variables, op):
            if not getattr(s, 'source_pagination_probe', False):
                s.pages.append(copy.deepcopy(variables['data']['pagination']['page']))
            value = next(replies)
            if isinstance(value, BaseException):
                raise value
            return value
        with patch.object(collector.C, 'PAGE_SIZE', 2), patch.object(collector, 'gql', side_effect=fetch), patch.object(collector, 'sleep_between'):
            result = collector.fetch_agency_listings(session, 'agency')
        return result, session

    def test_duplicate_page_restarts_without_deduplicating_or_retaining_failed_pages(self):
        replies = iter([response(['a', 'b']), response(['a', 'b']),
                        response(['a', 'b']), response(['c', 'd']), response(['a', 'b'])])
        rows, session = self.collect(replies)
        self.assertEqual([r['uuid'] for r in rows], ['a', 'b', 'c', 'd'])
        self.assertEqual(session.passes, 2)
        self.assertEqual(session.pages, [1, 2])

    def test_boundary_duplicate_and_total_change_restart(self):
        rows, session = self.collect(iter([
            response(['a', 'b']), response(['b', 'c'], 5),
            response(['a', 'b']), response(['c', 'd']), response(['a', 'b'])]))
        self.assertEqual(len(rows), 4)
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
        with self.assertRaises(collector.SourcePaginationChanged):
            self.collect(iter([response(['a', 'b']), response(['a', 'b'])] * 3))

    def test_block_does_not_enter_pagination_retry(self):
        class Blocked(BaseException):
            pass
        with self.assertRaises(Blocked):
            self.collect(iter([Blocked('403')]))
