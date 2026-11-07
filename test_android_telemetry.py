import copy
import io
import json
import os
import unittest
import uuid
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import android_telemetry as a
import android_telemetry_http as http

NOW=datetime.now(timezone.utc)
def report(at=None):
    return dict(reportId=uuid.uuid4().hex,observedAt=(at or datetime.now(timezone.utc)).isoformat(),
        appVersionCode=10213,lastCode='UNRECOGNIZED_INPUT',lastEventAt=None,
        **{k:False for k in a.BOOLS})

class Boundary(unittest.TestCase):
    def test_workflow_report_contains_only_bounded_technical_result(self):
        valid={'state':'SUCCEEDED','source':'LOCAL','confirmed':2,'total':2,'at':NOW.isoformat()}
        p=report();p['workflow']=valid
        self.assertEqual(a.validate_report(p)['workflow'],valid)
        for bad in [dict(valid,goal='private goal'),dict(valid,app='private.app'),
                    dict(valid,state='raw error'),dict(valid,source='provider key'),
                    dict(valid,confirmed=True),dict(valid,confirmed=1),dict(valid,total=13),
                    dict(valid,confirmed=0,total=0),dict(valid,at=(NOW+timedelta(minutes=5)).isoformat())]:
            p['workflow']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):a.validate_report(p)
        # Old last-event timestamps are retained, while observedAt records report freshness.
        p['workflow']=dict(valid,at=(NOW-timedelta(days=3)).isoformat())
        a.validate_report(p)

    def test_search_diagnostics_use_fixed_codes_without_screen_content(self):
        for code in ('SEARCH_TREE_EMPTY','SEARCH_NOT_ACTIONABLE','SEARCH_NO_PROGRESS','SEARCH_TRANSITION_PENDING','SEARCH_RETRY_PARENT'):
            value=report();value['lastCode']=code
            self.assertEqual(a.validate_report(value)['lastCode'],code)
            value['screenText']='Mit Namen, ISIN oder Symbol suchen'
            with self.assertRaises(ValueError):a.validate_report(value)
    def test_report_rejects_extra_content_and_invalid_states(self):
        self.assertEqual(a.validate_report(report())['lastCode'],'UNRECOGNIZED_INPUT')
        for key,value in [('screenText','account'),('token','secret'),('appVersionCode',True),('lastCode','raw screen text'),('running',1),('observedAt',(NOW-timedelta(days=2)).isoformat()),('lastEventAt','bad')]:
            p=report();p[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):a.validate_report(p)
    def test_paired_detail_transfer_aggregate_is_read_only_and_bounded(self):
        for state in a.DETAIL_STATES:
            p=report()
            p['detailTransfer']={'state':state,'saved':0,'deferred':8,
                                  'at':datetime.now(timezone.utc).isoformat()}
            self.assertEqual(a.validate_report(p)['detailTransfer']['state'],state)
            self.assertFalse('listBatchId' in json.dumps(p))
        p=report()
        valid={'state':'DEFERRED','saved':0,'deferred':8,
               'at':datetime.now(timezone.utc).isoformat()}
        for bad in [
            dict(valid,screenText='account information'),
            dict(valid,state='Raw error: Token 123'),
            dict(valid,saved=True),
            dict(valid,deferred=121),
            dict(valid,deferred=-1),
            dict(valid,saved=1.5),
            dict(valid,at=(datetime.now(timezone.utc)-timedelta(days=2)).isoformat())
        ]:
            p['detailTransfer']=bad
            with self.subTest(bad=bad),self.assertRaises(ValueError):
                a.validate_report(p)
        p['detailTransfer']=valid
        p['detailTransfer']['batchId']='a'*32
        with self.assertRaises(ValueError):
            a.validate_report(p)
        p=report()
        p['pinProbe']='not a valid probe'
        p['detailTransfer']=valid
        with self.assertRaises(ValueError):
            a.validate_report(p)

    def test_token_must_be_high_entropy_shape(self):
        for token in ['',None,'password','a'*63,'A'*64]:
            with self.assertRaises(PermissionError):a.token_hash(token)
        self.assertNotEqual(a.token_hash('a'*64),'a'*64)

class Handler:
    def __init__(self,body,auth=False,headers=None):
        raw=json.dumps(body).encode();self.headers={'Content-Length':str(len(raw)),'Content-Type':'application/json',**(headers or {})}
        self.rfile=io.BytesIO(raw);self.wfile=io.BytesIO();self.auth=auth;self.code=None
    def authenticated(self):return self.auth
    def send_response(self,code):self.code=code
    def send_header(self,*args):pass
    def end_headers(self):pass

class HttpBoundary(unittest.TestCase):
    def test_pairing_needs_login_and_same_origin(self):
        for auth,origin,expected in [(False,True,401),(True,False,403)]:
            h=Handler({'action':'register','tokenHash':'a'*64},auth)
            with patch('bob_auth.same_origin',return_value=origin):
                http.route(h,'POST','/api/android-diagnostics/pair',lambda _:self.fail('forwarded'))
            self.assertEqual(h.code,expected)
    def test_report_credential_never_grants_pairing_or_read(self):
        h=Handler(report(),headers={'Authorization':'Bearer '+'a'*64})
        sent=[]
        http.route(h,'POST','/api/android-diagnostics/report',lambda p:sent.append(p) or {'ok':True})
        self.assertEqual(h.code,200);self.assertEqual(sent[0]['action'],'report')
        h=Handler({'action':'register'},headers={'Authorization':'Bearer '+'a'*64})
        http.route(h,'POST','/api/android-diagnostics/pair',lambda _:self.fail('paired'))
        self.assertEqual(h.code,401)
        h=Handler({})
        http.route(h,'GET','/api/android-diagnostics/report',lambda _:self.fail('read'))
        self.assertEqual(h.code,405)
    def test_cookie_alone_cannot_submit_phone_report(self):
        h=Handler(report(),auth=True)
        http.route(h,'POST','/api/android-diagnostics/report',lambda _:self.fail('forwarded'))
        self.assertEqual(h.code,401)
    def test_errors_do_not_expose_credentials(self):
        h=Handler(report(),headers={'Authorization':'Bearer '+'a'*64})
        def fail(_):raise RuntimeError('secret '+('a'*64))
        http.route(h,'POST','/api/android-diagnostics/report',fail)
        self.assertEqual(h.code,503);self.assertNotIn(b'a'*64,h.wfile.getvalue())

class Database(unittest.TestCase):
    def test_pair_report_retry_reorder_revoke_and_private_status(self):
        url=os.environ.get('BOB_TEST_DATABASE_URL')
        if not url:self.skipTest('CI PostgreSQL not configured')
        import psycopg
        with psycopg.connect(url) as conn:
            try:
                schema='android_diag_'+uuid.uuid4().hex
                conn.execute('CREATE SCHEMA '+schema);conn.execute('SET LOCAL search_path TO '+schema);a.init(conn)
                token='a'*64;digest=a.token_hash(token);p=report()
                with self.assertRaises(PermissionError):a.handle(conn,{'action':'report','token':token,'report':p})
                a.handle(conn,{'action':'register','tokenHash':digest})
                self.assertTrue(a.handle(conn,{'action':'report','token':token,'report':p})['saved'])
                self.assertTrue(a.handle(conn,{'action':'report','token':token,'report':p})['saved'])
                older=report(datetime.now(timezone.utc)-timedelta(minutes=5))
                a.handle(conn,{'action':'report','token':token,'report':older})
                state=a.status(conn);self.assertEqual(state['devices'][0]['report']['reportId'],p['reportId'])
                self.assertNotIn(digest,json.dumps(state));self.assertNotIn(token,json.dumps(state))
                self.assertTrue(state['devices'][0]['fresh'])
                with self.assertRaises(PermissionError):a.handle(conn,{'action':'report','token':'b'*64,'report':p})
                a.handle(conn,{'action':'revokeAll'})
                self.assertIsNone(a.status(conn)['devices'][0]['report'])
                with self.assertRaises(PermissionError):a.handle(conn,{'action':'report','token':token,'report':p})
                a.handle(conn,{'action':'register','tokenHash':a.token_hash('c'*64)})
                conn.execute("UPDATE bob_android_diagnostic_devices SET expires_at=now()-interval '1 minute'")
                with self.assertRaises(PermissionError):a.handle(conn,{'action':'report','token':'c'*64,'report':p})
            finally:conn.rollback()
