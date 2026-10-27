import ast
import pathlib
import unittest

source = pathlib.Path('collector.py').read_text(encoding='utf-8')
tree = ast.parse(source)
node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'map_view_batch')
ns = {}
exec(compile(ast.Module(body=[node], type_ignores=[]), 'collector.py', 'exec'), ns)
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

if __name__ == '__main__':
    unittest.main()
