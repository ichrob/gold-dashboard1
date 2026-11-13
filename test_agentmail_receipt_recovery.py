"""Regression: recover stored DEGIRO email bodies without sending any mail."""
import unittest
from unittest.mock import patch

import agentmail_receipt_recovery as recovery
from test_trade_document_import import TEXT


class MailRecoveryTests(unittest.TestCase):
    def test_read_errors_report_limits_without_private_message_content(self):
        import io
        from contextlib import redirect_stdout
        from unittest.mock import MagicMock
        for body, cap, code in [(b'private-receipt-data', 8, 'response-size-limit'),
                                (b'private-receipt-data', 100, 'invalid-json'),
                                (b'[]', 100, 'invalid-json-shape')]:
            response=MagicMock()
            response.__enter__.return_value.read.side_effect=lambda n: body[:n]
            output=io.StringIO()
            with patch.object(recovery,'urlopen',return_value=response), redirect_stdout(output):
                with self.assertRaises(ValueError):
                    recovery.api_json(recovery.BASE+'/private-message-id', 'private-key', cap)
            self.assertIn('code='+code, output.getvalue())
            for private in ('private-receipt', 'private-message-id', 'private-key'):
                self.assertNotIn(private, output.getvalue())

    def test_authenticated_inbox_recovery_is_scoped_and_idempotent(self):
        mid="<test-confirmation@example.test>"
        def fake_get(url,key,cap):
            self.assertEqual(key,'test-token-secure')
            self.assertTrue(url.startswith(recovery.BASE))
            if "?" in url:
                return {"messages":[
                    {"inbox_id":recovery.INBOX,"message_id":mid,"labels":["received"],
                     "subject":"DEGIRO - Transaktionsbestätigung: Kauf"},
                    {"inbox_id":"other@agentmail.to","message_id":"other",
                     "labels":["received"],"subject":"DEGIRO"},
                    {"inbox_id":recovery.INBOX,"message_id":"sent",
                     "labels":["sent"],"subject":"DEGIRO"},
                    {"inbox_id":recovery.INBOX,"message_id":mid,"labels":["received"],
                     "subject":"DEGIRO"}]}
            return {"inbox_id":recovery.INBOX,"message_id":mid,
                "from":"DEGIRO <notifications@degiro.com>",
                "subject":"DEGIRO - Transaktionsbestätigung: Kauf",
                "html":'<div>DEGIRO</div><div>'+TEXT.replace('\n','<br>')+'</div>'}
        items=recovery.recover('test-token-secure','customer@example.test',fake_get)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['messageId'],mid)
        self.assertEqual(items[0]['record']['status'],'pending-review')
        self.assertEqual(items[0]['record']['totalChf'],6.04)
        self.assertEqual(items[0]['record']['senderKind'],'original-degiro-unverified')
        self.assertNotIn('html',str(items))

    def test_historical_window_is_explicit_bounded_and_keeps_default(self):
        import datetime as dt
        from urllib.parse import urlsplit, parse_qs
        now=dt.datetime(2026,11,13,tzinfo=dt.timezone.utc)
        urls=[]
        def empty(url,*args):
            urls.append(parse_qs(urlsplit(url).query))
            return {'messages': []}
        recovery.recover('test-token-secure','customer@example.test',empty,now)
        self.assertEqual(urls[-1]['after'],['2026-11-06T00:00:00Z'])
        recovery.recover('test-token-secure','customer@example.test',empty,now,lookback_days=45)
        self.assertEqual(urls[-1]['after'],['2026-09-29T00:00:00Z'])
        self.assertEqual(urls[-1]['limit'],['5'])
        for days in [0,46,True,1.5]:
            with self.assertRaises(ValueError):
                recovery.recover('test-token-secure','customer@example.test',empty,now,lookback_days=days)
        self.assertEqual(len(urls),2)

    def test_archive_poll_schedule_success_and_failure_are_bounded(self):
        import ast, os
        from pathlib import Path
        from types import SimpleNamespace
        source=ast.parse(Path('server.py').read_text())
        function=next(n for n in source.body if isinstance(n,ast.FunctionDef) and n.name=='_agentmail_recovery_loop')
        for fails, expected in [(False,[45,7,7]),(True,[45,7,45])]:
            clock=[0.0]; calls=[]; sleeps=[]
            def read(*args, **kwargs):
                calls.append(kwargs['lookback_days'])
                if fails and len(calls)==1: raise ValueError('synthetic failure')
                return []
            def sleep(seconds):
                sleeps.append(seconds)
                if len(sleeps)==3: raise StopIteration()
                clock[0]+=30 if len(sleeps)==1 else 300
            env={'os':os,'time':SimpleNamespace(monotonic=lambda:clock[0],sleep=sleep),
                 'PUSH_SERVICE_URL':'','PUSH_SERVICE_TOKEN':'','print':lambda *a,**k:None}
            exec(compile(ast.Module(body=[function],type_ignores=[]),'server-loop-test','exec'),env)
            with patch.object(recovery,'recover',side_effect=read),patch.object(recovery,'submit',return_value=0):
                with self.assertRaises(StopIteration): env['_agentmail_recovery_loop']()
            self.assertEqual(calls,expected)
            self.assertEqual(sleeps,[30,30,30])

    def test_unconfigured_skip_network(self):
        def fail(*args):
            raise AssertionError('No unconfigured external traffic')
        self.assertEqual(recovery.recover('', 'user@example.test',fail),[])
        self.assertEqual(recovery.recover('test-token-secure', '',fail),[])

    def test_header_heavy_archive_pages_preserve_late_receipts_and_caps(self):
        import json
        from urllib.parse import urlsplit, parse_qs, unquote
        messages=[dict(inbox_id=recovery.INBOX, message_id='mail-'+str(i),
                       labels=['received'], subject='DEGIRO', headers={'transport':'x'*6000})
                  for i in range(35)]
        self.assertGreater(len(json.dumps({'messages':messages[:14]}).encode()),70000)
        for count, expected in [(14,14),(35,30)]:
            calls=[]
            def fetch(url,key,cap):
                if '?' in url:
                    q=parse_qs(urlsplit(url).query)
                    offset=int(q.get('page_token',['0'])[0]); limit=int(q['limit'][0])
                    calls.append(offset)
                    page={'messages':messages[offset:min(offset+limit,count)]}
                    if offset+limit<count:page['next_page_token']=str(offset+limit)
                    self.assertLessEqual(len(json.dumps(page).encode()),cap)
                    return page
                mid=unquote(url.rsplit('/',1)[-1])
                return dict(inbox_id=recovery.INBOX, message_id=mid,
                            **{'from':'DEGIRO <notifications@degiro.com>'},
                            subject='DEGIRO - Transaktionsbestätigung: Kauf',text=TEXT)
            with patch('builtins.print'):
                records=recovery.recover('test-token-secure','customer@example.test',fetch)
            self.assertEqual(len(records),expected)
            self.assertEqual(records[-1]['messageId'],'mail-'+str(expected-1))
            self.assertLessEqual(len(calls),6)
            self.assertTrue(all('headers' not in str(record) for record in records))

    def test_pagination_rejects_repeating_tokens_without_unbounded_requests(self):
        calls=[]
        def fetch(*args):
            calls.append(1)
            return {'messages':[], 'next_page_token':'same-private-token'}
        with patch('builtins.print') as log:
            with self.assertRaises(ValueError):
                recovery.recover('test-token-secure','customer@example.test',fetch)
        self.assertEqual(len(calls),2)
        self.assertNotIn('same-private-token',str(log.call_args_list))

    def test_request_cannot_switch_to_another_inbox(self):
        with self.assertRaises(ValueError):
            recovery.api_json('https://other.example/v0/inboxes/other/messages',
                              'test-token-secure',1000)


if __name__=="__main__":
    unittest.main()
