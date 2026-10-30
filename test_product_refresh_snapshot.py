"""Exercise the source-cache handoff without database/network dependencies."""
import ast
import copy
import threading
import types
import unittest
import quote_updates
from pathlib import Path
from unittest.mock import patch


class ProductRefreshSnapshot(unittest.TestCase):
    def test_backup_clock_reaches_push_without_paper_projection(self):
        tree = ast.parse(Path(__file__).with_name('paper_simulation.py').read_text())
        functions = [n for n in tree.body if isinstance(n, ast.FunctionDef)
                     and n.name in ('quote_cache', 'observed_quotes')]
        ns = dict(copy=copy, quote_updates=types.SimpleNamespace(updates=quote_updates.QuoteUpdates()), _guard=threading.Lock(), _pool=object(),
                  _pending={}, _requested={}, _quotes={'TEST': {'isin': 'TEST', 'askAt': 'old'}},
                  _observed_snapshot={})
        exec(compile(ast.Module(body=functions, type_ignores=[]), '<cache>', 'exec'), ns)
        def backup(isin, raw):
            return dict(raw, askAt='original-backup-clock', ask=7.13)
        def projection(raw):
            raw.update(ask=99, priceKind='model')
            return raw
        modules = {
            'product_quotes': types.SimpleNamespace(get_quote=lambda isin: None),
            'product_repair_learning': types.SimpleNamespace(request_order=lambda *args: []),
            'product_source_recovery': types.SimpleNamespace(enrich=lambda name, isin, fn, raw, recovery: fn(isin, raw)),
            'comdirect_quotes': types.SimpleNamespace(apply=backup),
            'swissquote_quotes': types.SimpleNamespace(apply=lambda isin, raw: raw),
            'comdirect_fields': types.SimpleNamespace(apply=lambda isin, raw: raw),
            'leverage_backup': types.SimpleNamespace(apply=lambda raw: raw),
            'hybrid_product_price': types.SimpleNamespace(apply=projection),
        }
        products = [{'isin': 'TEST'}]
        with patch.dict('sys.modules', modules):
            paper = ns['quote_cache'](products, [], 123)
            observed = ns['observed_quotes'](products)
            self.assertEqual(paper['TEST']['ask'], 99)
            self.assertEqual(observed['TEST']['ask'], 7.13)
            self.assertEqual(observed['TEST']['askAt'], 'original-backup-clock')
            self.assertNotIn('priceKind', observed['TEST'])
            observed['TEST']['ask'] = -1
            self.assertEqual(ns['observed_quotes'](products)['TEST']['ask'], 7.13)
            ns['quote_cache']([], [], 124)
            self.assertEqual(ns['observed_quotes'](products), {})


if __name__ == '__main__':
    unittest.main()
