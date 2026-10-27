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

    def test_fetch_views_uses_aliases_to_preserve_uuids(self):
        from types import SimpleNamespace
        ns['C'] = SimpleNamespace(VIEWS_BATCH_SIZE=3, PAUSE_BETWEEN_VIEW_BATCHES=0)
        ns['Q'] = SimpleNamespace(VIEWS_QUERY='obsolete-unsafe-query')
        responses=[]
        def fake_gql(session, query, variables, op):
            responses.append(query)
            return {'data': {'v0':[{'views': 44}], 'v1':[{'views':28}], 'v2':[{'views':18}]}}
        ns['gql'] = fake_gql
        ns['sleep_between'] = lambda _: None
        self.assertEqual(ns['fetch_views'](None, ['a','b','c']), {'a':44,'b':28,'c':18})
        self.assertIn('v0:objectsViewsCountsByUuids(uuids:["a"])', responses[0])
        self.assertIn('v1:objectsViewsCountsByUuids(uuids:["b"])', responses[0])
        self.assertIn('v2:objectsViewsCountsByUuids(uuids:["c"])', responses[0])

    def test_missing_alias_is_not_assigned_to_next_uuid(self):
        from types import SimpleNamespace
        ns['C'] = SimpleNamespace(VIEWS_BATCH_SIZE=3, PAUSE_BETWEEN_VIEW_BATCHES=0)
        ns['gql'] = lambda *a: {'data': {'v0':[{'views':15}], 'v2':[{'views':19}]}}
        ns['sleep_between'] = lambda _: None
        self.assertEqual(ns['fetch_views'](None, ['a','b','c']), {'a':15,'b':None,'c':19})

if __name__ == '__main__':
    unittest.main()
