import ast
import pathlib
import unittest

source = pathlib.Path('collector.py').read_text(encoding='utf-8')
tree = ast.parse(source)
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in {'map_view_batch', 'fetch_views'}]
ns = {}
exec(compile(ast.Module(body=nodes, type_ignores=[]), 'collector.py', 'exec'), ns)
map_view_batch = ns['map_view_batch']

class ViewBatchTests(unittest.TestCase):
    def test_correct_length(self):
        self.assertEqual(map_view_batch(['a','b'], [{'views':4},{'views':12}]), {'a':4,'b':12})
    def test_truncated_response(self):
        self.assertEqual(map_view_batch(['a','b'], [{'views':12}]), {'a':None,'b':None})
    def test_extra_result(self):
        self.assertEqual(map_view_batch(['a'], [{'views':2},{'views':3}]), {'a':None})
    def test_bad_values(self):
        self.assertEqual(map_view_batch(['a','b','c'], [{'views':-1},{'views':'n/a'},None]), {'a':None,'b':None,'c':None})

    def test_fetch_views_does_not_shift_on_missing_response_item(self):
        from types import SimpleNamespace
        ns['C'] = SimpleNamespace(VIEWS_BATCH_SIZE=3, PAUSE_BETWEEN_VIEW_BATCHES=0)
        ns['Q'] = SimpleNamespace(VIEWS_QUERY='query')
        ns['gql'] = lambda *a: {'data': {'objectsViewsCountsByUuids': [{'views': 100}, {'views': 300}]}}
        ns['sleep_between'] = lambda _: None
        self.assertEqual(ns['fetch_views'](None, ['a','b','c']), {'a':None,'b':None,'c':None})

if __name__ == '__main__':
    unittest.main()
