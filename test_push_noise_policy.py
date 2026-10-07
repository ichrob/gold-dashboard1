import ast
import json
import unittest
from unittest.mock import Mock
from pathlib import Path
import background_push as push


class NoisePolicyTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000000
        self.settings = {'trade': None}
        self.market = {'ready': True, 'priceFresh': True, 'direction': 'LONG',
                       'mtf': 'LONG', 'price': 110, 'atr': 4, 'dataAt': self.now}

    def tick(self, state=None, seconds=0, trade=False, **values):
        market = dict(self.market, dataAt=self.now+seconds*1000, **values)
        return push.advance(state, self.settings, market, True, trade, self.now+seconds*1000)

    @staticmethod
    def kinds(events):
        return [e['data']['eventKind'] for e in events]

    def trade(self):
        self.settings['trade'] = {'tradeId': 'test', 'dir': 'LONG', 'entry': 100,
                                 'stop': 90, 'initialRisk': 10, 'target': 140}

    def test_short_data_flap_is_silent(self):
        state, _ = self.tick()
        state, events = self.tick(state, 30, ready=False)
        self.assertEqual(events, [])
        state, events = self.tick(state, 60)
        self.assertNotIn('data-recovered', self.kinds(events))
        self.assertTrue(state['healthy'])

    def test_outage_and_recovery_need_spaced_confirmations(self):
        state, _ = self.tick()
        for seconds in (30, 31, 60):
            state, events = self.tick(state, seconds, ready=False)
            self.assertEqual(events, [])
        state, events = self.tick(state, 90, ready=False)
        self.assertIn('data-unavailable', self.kinds(events))
        state, events = self.tick(state, 120)
        self.assertNotIn('data-recovered', self.kinds(events))
        state, events = self.tick(state, 150)
        self.assertIn('data-recovered', self.kinds(events))

    def test_direction_confirmation_neutral_and_restart(self):
        state, events = self.tick()
        self.assertEqual(events, [])
        state, events = self.tick(state, 30)
        self.assertEqual(self.kinds(events), ['signal-change'])
        state = json.loads(json.dumps(state))  # durable reload after restart
        state, _ = self.tick(state, 60, direction='NEUTRAL')
        state, events = self.tick(state, 90)
        self.assertEqual(events, [])
        state, events = self.tick(state, 120, direction='SHORT', mtf='SHORT')
        self.assertEqual(events, [])
        state, events = self.tick(state, 150, direction='SHORT', mtf='SHORT')
        self.assertEqual(self.kinds(events), ['signal-change'])

    def test_same_quote_cannot_confirm_signal(self):
        state, _ = self.tick()
        state, events = push.advance(state, self.settings, self.market, True, False, self.now+30000)
        self.assertEqual(events, [])

    def test_bad_data_breaks_direction_confirmation(self):
        state, _ = self.tick()
        state, _ = self.tick(state, 30, ready=False)
        state, events = self.tick(state, 60)
        self.assertNotIn('signal-change', self.kinds(events))

    def test_stop_small_changes_accumulate_and_never_loosen(self):
        self.trade()
        state, events = self.tick(trade=True, price=105, suggestedStop=90.2)
        self.assertNotIn('trailing-stop', self.kinds(events))
        state, events = self.tick(state, 30, trade=True, price=105, suggestedStop=91.1)
        self.assertIn('trailing-stop', self.kinds(events))
        state, events = self.tick(state, 60, trade=True, price=105, suggestedStop=94)
        self.assertNotIn('trailing-stop', self.kinds(events))
        self.assertEqual(state['trade']['stop'], 94)
        state, events = self.tick(state, 330, trade=True, price=105, suggestedStop=92)
        self.assertEqual(state['trade']['stop'], 94)
        self.assertIn('trailing-stop', self.kinds(events))

    def test_stop_hit_is_immediate_once_even_with_bad_analysis(self):
        self.trade()
        state, events = self.tick(trade=True, ready=False, price=89)
        self.assertIn('stop-hit', self.kinds(events))
        state, _ = self.tick(state, 30, trade=True, ready=False, price=95)
        state, events = self.tick(state, 60, trade=True, ready=False, price=89)
        self.assertNotIn('stop-hit', self.kinds(events))

    def test_target_and_ko_are_immediate(self):
        self.trade()
        state, events = self.tick(trade=True, ready=False, price=141)
        self.assertIn('target', self.kinds(events))
        self.settings['trade']['product'] = {'ko': 85, 'isin': 'test', 'referenceAt': 'now',
            'direction': 'LONG', 'bid': 10, 'ratio': .1, 'strike': 80,
            'goldReference': 100, 'fxReference': 1, 'fxScenario': 1}
        state, events = self.tick(state, 30, trade=True, ready=False, price=84)
        self.assertIn('ko-hit', self.kinds(events))

    def test_short_trade_stop_tightens(self):
        self.trade()
        self.settings['trade'].update(dir='SHORT', stop=120, target=70)
        state, _ = self.tick(trade=True, price=100, direction='SHORT', suggestedStop=118)
        state, _ = self.tick(state, 30, trade=True, price=100, direction='SHORT', suggestedStop=119)
        self.assertEqual(state['trade']['stop'], 118)

    def test_history_is_bounded(self):
        state = None
        for seconds in range(0, 30000, 30):
            state, _ = self.tick(state, seconds, direction='LONG' if seconds % 60 else 'SHORT')
        self.assertLessEqual(len(state['pushHistory']), 50)

    def test_delivery_log_acceptance_and_failure(self):
        # Isolate the actual wrapper without loading database/network dependencies.
        tree = ast.parse(Path('push_server.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'webpush')
        class Failure(Exception):
            response = type('Response', (), {'status_code': 503})()
        provider = Mock(return_value=type('Response', (), {'status_code': 201})())
        log = Mock()
        env = dict(json=json, time=__import__('time'), _webpush=provider,
                   WebPushException=Failure, RequestException=ConnectionError, print=log)
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'push_server.py', 'exec'), env)
        env['webpush'](data=json.dumps({'data': {'eventKind': 'stop-hit'}}))
        self.assertIn('provider-accepted', log.call_args[0][0])
        self.assertEqual(provider.call_args.kwargs['timeout'], 8)
        provider.side_effect = Failure()
        with self.assertRaises(Failure):
            env['webpush'](data='{}')
        self.assertIn('failed', log.call_args[0][0])


if __name__ == '__main__':
    unittest.main()
