import ast
import io
from pathlib import Path
import unittest
import archive_public

class Handler:
    def __init__(self, path):
        self.path = path
        self.wfile = io.BytesIO()
        self.headers = {}
    def send_response(self, status): self.status = status
    def send_header(self, key, value): self.headers[key] = value
    def end_headers(self): pass

class PublicArchiveTests(unittest.TestCase):
    def test_public_html_and_head(self):
        for path in archive_public.PAGES:
            get, head = Handler(path + '?ignored=<script>'), Handler(path)
            self.assertTrue(archive_public.route(get))
            self.assertTrue(archive_public.route(head, head=True))
            self.assertEqual(get.status, 200)
            self.assertEqual(get.headers, head.headers)
            self.assertEqual(int(get.headers['Content-Length']), len(get.wfile.getvalue()))
            self.assertEqual(head.wfile.getvalue(), b'')
            self.assertNotIn(b'<script>', get.wfile.getvalue())
            self.assertIn(b'lang="de"', get.wfile.getvalue())
    def test_private_and_unknown_paths_not_handled(self):
        for path in ['/', '/archive/connect', '/archive/connect/callback', '/api/status', '/archive/privacy/../connect', '/archive/other']:
            self.assertFalse(archive_public.route(Handler(path)))
    def test_server_routes_public_pages_before_private_dispatch(self):
        tree = ast.parse(Path('server.py').read_text())
        for name in ('do_GET', 'do_HEAD'):
            method = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)
            self.assertIn('archive_public', ast.unparse(method.body[0]))
    def test_cross_links_and_consent_scope(self):
        self.assertIn('href="/archive/privacy"', archive_public.HOME)
        self.assertIn('href="/archive/about"', archive_public.PRIVACY)
        self.assertIn('drive.file', archive_public.PRIVACY)

if __name__ == '__main__': unittest.main()
