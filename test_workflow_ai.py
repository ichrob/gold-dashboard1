import copy
import json
import os
import unittest
import uuid
from unittest.mock import patch, Mock, MagicMock
from contextlib import contextmanager
import workflow_ai as w
from test_android_telemetry import Handler
import android_telemetry_http as http

def request():
    return dict(version=1, requestId=uuid.uuid4().hex, consent=w.VERSION,
        app='org.example.notes', goal='Schreibe Gold in die Suche',
        nodes=[dict(label='', id='search', editable=True, clickable=True)])
def plan():
    return {'steps':[dict(action='WRITE',target='search',value='Gold',expected='')]}
ENV={'GEMINI_API_KEY':'test-only', 'BOB_GEMINI_FREE_PROJECT':'confirmed-no-billing'}

class Rules(unittest.TestCase):
    def test_plan_rejects_unrequested_input_unknown_targets_and_actions(self):
        self.assertEqual(w.validate_plan(plan(),request())[0]['value'],'Gold')
        for field,value in [('action','SHELL'),('target','unknown'),('value','Silver'),('expected','done')]:
            p=plan();p['steps'][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):w.validate_plan(p,request())
        for p in [dict(steps=[]),dict(steps=plan()['steps'],command='shell'),
                  dict(steps=[dict(action='CLICK',target='search',value='',expected='')]),
                  dict(steps=[dict(action='CLICK',target='search',value='',expected='Kaufen')])]:
            with self.assertRaises(ValueError):w.validate_plan(p,request())
    def test_request_rejects_images_field_content_missing_consent_and_private_text(self):
        for field,value in [('image','x'),('consent','old'),('version',True),('app','nl.degiro.trader.fake'),
                            ('goal','Schreibe mein Passwort'),('goal','IBAN CH12345678')]:
            r=request();r[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):w.validate_request(r)
        r=request();r['nodes'][0]['inputValue']='private'
        with self.assertRaises(ValueError):w.validate_request(r)
    def test_degiro_search_allowed_but_trading_and_login_remain_blocked(self):
        r=request(); r['app']='nl.degiro.trader'
        self.assertEqual(w.validate_request(r)['app'], 'nl.degiro.trader')
        for goal in ['Gold kaufen', 'Silber verkaufen', 'Anmelden', 'Schreibe Passwort']:
            r['goal']=goal
            with self.subTest(goal=goal), self.assertRaises(ValueError): w.validate_request(r)

    def test_free_account_gate_is_required_and_kill_switch_wins(self):
        with patch.dict(os.environ,{},clear=True): self.assertFalse(w.configured())
        with patch.dict(os.environ,{'GEMINI_API_KEY':'test-only'},clear=True): self.assertFalse(w.configured())
        with patch.dict(os.environ,ENV,clear=True): self.assertTrue(w.configured())
        with patch.dict(os.environ,dict(ENV,BOB_WORKFLOW_AI_DISABLED='1'),clear=True):self.assertFalse(w.configured())
    def test_http_needs_device_token_not_browser_cookie(self):
        h=Handler(request(),auth=True)
        http.route(h,'POST','/api/android-workflow/plan',lambda *a,**kw:self.fail('forwarded'))
        self.assertEqual(h.code,401)
        h=Handler(request(),headers={'Authorization':'Bearer '+'a'*64})
        seen=[]
        http.route(h,'POST','/api/android-workflow/plan',lambda p,**kw:seen.append(p) or {'ok':True})
        self.assertEqual(h.code,200);self.assertEqual(seen[0]['action'],'workflow-plan')
    def test_no_key_or_bad_device_never_calls_provider(self):
        conn=Mock();conn.execute.return_value.fetchone.return_value=('digest',)
        @contextmanager
        def connect(): yield conn
        provider=Mock()
        with patch.dict(os.environ,{},clear=True):
            result=w.handle(connect,dict(action='workflow-plan',token='a'*64,value=request()),provider)
            self.assertEqual(result['status'],'setup-required')
        conn.execute.return_value.fetchone.return_value=None
        with self.assertRaises(PermissionError):
            w.handle(connect,dict(action='workflow-plan',token='a'*64,value=request()),provider)
        provider.assert_not_called()
    def test_provider_is_called_once_without_retry_and_token_is_not_in_prompt(self):
        opener=MagicMock();response=Mock()
        response.read.return_value=json.dumps({'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'internal reasoning','thought':True},{'text':json.dumps(plan()),'thoughtSignature':'opaque'}]}}]}).encode()
        opener.open.return_value.__enter__.return_value=response
        with patch.dict(os.environ,ENV,clear=True),patch('urllib.request.build_opener',return_value=opener):
            self.assertEqual(w.generate(request()),plan())
        sent=opener.open.call_args.args[0]
        data=json.loads(sent.data)
        self.assertEqual(sent.full_url,w.URL);self.assertIn(w.MODEL,sent.full_url);self.assertEqual(data['generationConfig']['responseMimeType'],'application/json')
        self.assertNotIn('test-only',sent.data.decode());self.assertNotIn('requestId',sent.data.decode())
        self.assertNotIn('tools',data);opener.open.assert_called_once()
        with self.assertRaises(ValueError):w.NoRedirect().redirect_request(None,None,302,'',{},'https://other')
    def test_old_provider_consent_never_sends_data_to_new_provider(self):
        conn=Mock();conn.execute.return_value.fetchone.return_value=('digest',)
        @contextmanager
        def connect(): yield conn
        r=request();r['consent']='groq-reviewed-text-v1'
        provider=Mock()
        with patch.dict(os.environ,ENV,clear=True),self.assertRaisesRegex(ValueError,'consent-required'):
            w.handle(connect,dict(action='workflow-plan',token='a'*64,value=r),provider)
        provider.assert_not_called()
    def test_rejects_incomplete_tool_and_oversized_responses(self):
        for response_body in [
            {'candidates':[]},
            {'candidates':[{'finishReason':'MAX_TOKENS'}]},
            {'candidates':[{'finishReason':'STOP','content':{'parts':[{'functionCall':{}}]}}]},
            {'candidates':[{'finishReason':'STOP','content':{'parts':[]}}]},
            {'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'not json'}]}}]},
            'x'*32769]:
            opener=MagicMock()
            opener.open.return_value.__enter__.return_value.read.return_value=(
                response_body.encode() if isinstance(response_body,str) else json.dumps(response_body).encode())
            with self.subTest(response=response_body if isinstance(response_body,dict) else 'oversized'),patch.dict(os.environ,ENV,clear=True),patch('urllib.request.build_opener',return_value=opener),self.assertRaises(ValueError):
                w.generate(request())
            opener.open.assert_called_once()
    def test_invalid_provider_result_spends_reservation_but_never_retries(self):
        conn=Mock();conn.execute.return_value.fetchone.return_value=('digest',)
        @contextmanager
        def connect():yield conn
        provider=Mock(side_effect=RuntimeError('private provider detail'))
        with patch.dict(os.environ,ENV,clear=True),patch.object(w,'reserve',return_value='reserved'):
            result=w.handle(connect,dict(action='workflow-plan',token='a'*64,value=request()),provider)
        provider.assert_called_once();conn.commit.assert_called_once()
        self.assertEqual(result['status'],'no-valid-proposal');self.assertNotIn('private',json.dumps(result))

@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL CI integration')
class Database(unittest.TestCase):
    def test_persistent_dedup_daily_budget_restart_and_revocation(self):
        import psycopg
        schema='workflow_ai_'+uuid.uuid4().hex
        dsn=os.environ['BOB_TEST_DATABASE_URL']
        with psycopg.connect(dsn,autocommit=True) as c:c.execute('CREATE SCHEMA '+schema)
        def connect():return psycopg.connect(dsn,options='-c search_path='+schema)
        try:
            with connect() as c:
                import android_telemetry as telemetry
                telemetry.init(c)
                telemetry.handle(c,dict(action='register',tokenHash=w.token_hash('a'*64)))
                c.commit()
            provider=Mock(return_value=plan());r=request()
            payload=dict(action='workflow-plan',token='a'*64,value=r)
            with patch.dict(os.environ,ENV,clear=True),patch.object(w.time,'time',return_value=100000):
                self.assertEqual(w.handle(connect,payload,provider)['status'],'proposal')
                self.assertEqual(w.handle(connect,payload,provider)['status'],'already-requested')
                payload['value']=request()
                self.assertEqual(w.handle(connect,payload,provider)['status'],'wait-one-minute')
            provider.assert_called_once()
            with connect() as c:
                for n in range(1,10):
                    self.assertEqual(w.reserve(c,w.token_hash('a'*64),uuid.uuid4().hex,100000+61*n),'reserved')
                self.assertEqual(w.reserve(c,w.token_hash('a'*64),uuid.uuid4().hex,100700),'daily-limit')
                for n in range(10):
                    self.assertEqual(w.reserve(c,w.token_hash('b'*64),uuid.uuid4().hex,100800+61*n),'reserved')
                self.assertEqual(w.reserve(c,w.token_hash('c'*64),uuid.uuid4().hex,102000),'daily-limit')
                # Clock rollback cannot discard reservations and reopen spending.
                self.assertEqual(w.reserve(c,w.token_hash('c'*64),uuid.uuid4().hex,99000),'daily-limit')
                c.commit()
            # A new connection (worker/restart) still sees quota; no prompts stored.
            with connect() as c:
                rows=c.execute('SELECT recent FROM bob_workflow_ai_budget').fetchone()[0]
                self.assertEqual(len(rows),20);self.assertNotIn('Gold',json.dumps(rows))
                c.execute('UPDATE bob_android_diagnostic_devices SET revoked=true');c.commit()
            with patch.dict(os.environ,ENV,clear=True),self.assertRaises(PermissionError):
                w.handle(connect,payload,provider)
            provider.assert_called_once()
        finally:
            with psycopg.connect(dsn,autocommit=True) as c:c.execute('DROP SCHEMA '+schema+' CASCADE')
