import copy
import json
import unittest
import os
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import patch
import android_remote as remote
import handset_entry_request as entry
from test_android_remote import value, NOW

ISIN='DE000FD0S0G4'
LIST='b'*32
AT=datetime.fromtimestamp(NOW-30,timezone.utc).isoformat()


def planning():
    return dict(resultFresh=True,revision=3,contextFingerprint='context',result=dict(
        configRevision=3,listUploadedAt=AT,items=[dict(isin=ISIN,available=True,
        entrySuitable=True,reasons=[],modelReferenceAt=AT)]))


class Db:
    def __init__(self,state):self.state=state;self.saved=None;self.run=None;self.listAt=AT
    def execute(self,sql,args=()):
        if sql.startswith('SELECT batch_id'):self.answer=(LIST,[dict(isin=ISIN)],self.listAt)
        elif sql.startswith('SELECT state'):self.answer=(self.state,)
        elif sql.startswith('SELECT payload FROM bob_android_read_runs'):
            assert args[0].endswith(':1'), 'Receipt must read exact saved revision'
            self.answer=(self.run,)
        elif sql.startswith('UPDATE bob_android_remote'):self.saved=json.loads(args[0])
        else:raise AssertionError(sql)
        return self
    def fetchone(self):return self.answer


class EntryRequest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL integration')
    def test_postgres_owned_list_queue_and_exact_revision_receipt(self):
        import psycopg
        now=int(time.time())
        at=datetime.fromtimestamp(now-20,timezone.utc).isoformat()
        p=planning();p['result']['listUploadedAt']=at
        p['result']['items'][0]['modelReferenceAt']=at
        s=dict(sessionId='a'*32,purpose='entry_read',active=True,
               expiresAt=now+900,seenAt=now,commands=[])
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            schema='entry_'+uuid.uuid4().hex
            conn.execute('CREATE SCHEMA '+schema)
            conn.execute('SET LOCAL search_path TO '+schema)
            conn.execute('CREATE TABLE bob_android_remote(token_hash text primary key,state jsonb)')
            conn.execute('CREATE TABLE bob_android_list_images(batch_id text,token_hash text,parsed_items jsonb,payload jsonb,import_receipt jsonb,created_at timestamptz default now())')
            conn.execute('CREATE TABLE bob_android_read_runs(batch_id text,payload jsonb)')
            conn.execute('INSERT INTO bob_android_list_images(batch_id,token_hash,parsed_items,payload,import_receipt) VALUES(%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)',
                (LIST,'owner',json.dumps([dict(isin=ISIN)]),json.dumps(dict(images=[dict(at=at)])),json.dumps(dict(stage='synced'))))
            with patch('handset_planning.read',return_value=p):
                entry.prepare(conn,'wrong-owner',s,now)
                self.assertFalse(s['commands'])
                s.pop('entryCheckAt')
                entry.prepare(conn,'owner',s,now)
                request=s['entryRead']['requestId']
                conn.execute('INSERT INTO bob_android_remote VALUES(%s,%s::jsonb)',('owner',json.dumps(s)))
                original=dict(results=[dict(code='COMPLETE',observation=dict(observedAt=datetime.fromtimestamp(now+1,timezone.utc).isoformat()))])
                conn.execute('INSERT INTO bob_android_read_runs VALUES(%s,%s::jsonb)',(request+':2',json.dumps(original)))
                run=dict(batchId=request,revision=2,isins=[ISIN],requestedFields={ISIN:entry.FIELDS})
                entry.receipt(conn,'owner',LIST,run,now+2)
                saved=conn.execute('SELECT state FROM bob_android_remote').fetchone()[0]
                self.assertEqual(saved['entryRead']['status'],'read-received-source-time-unverified')
                self.assertFalse(saved['entryRead']['entryApproved'])
            conn.execute('DROP SCHEMA '+schema+' CASCADE')

    def state(self):
        v=value();v['purpose']='entry_read'
        return remote.exchange({},v,NOW)[0]

    def test_locked_owner_entry_read_wait_cannot_start_server_request(self):
        state=self.state()
        state['observation']['code']='WAITING_FOR_UNLOCK'
        with patch('handset_planning.read',side_effect=AssertionError('No market query behind Android keyguard')):
            entry.prepare(Db(state),'owner',state,NOW)
        self.assertEqual(state['entryReadStatus'],'WAITING_FOR_UNLOCK')
        self.assertFalse(state['commands'])
        self.assertNotIn('entryRead',state)

    def test_normal_session_never_queues_and_purpose_cannot_change(self):
        s,_=remote.exchange({},value(),NOW)
        with patch('handset_planning.read',side_effect=AssertionError('No query')):
            entry.prepare(Db(s),'owner',s,NOW)
        changed=value();changed['purpose']='entry_read'
        with self.assertRaises(ValueError):remote.exchange(s,changed,NOW)
        with self.assertRaises(ValueError):remote.arguments('bob_phone_command',dict(
            deviceId='a'*12,sessionId='a'*32,requestId='b'*32,action='entry_read',isin=ISIN))

    def test_one_owned_request_delivery_and_no_second_request(self):
        s=self.state();db=Db(s)
        with patch('handset_planning.read',return_value=planning()):
            entry.prepare(db,'owner',s,NOW)
            self.assertEqual(len(s['commands']),1)
            self.assertEqual(s['entryRead']['status'],'queued')
            entry.prepare(db,'owner',s,NOW+31)
            self.assertEqual(len(s['commands']),1)
        v=value();v['purpose']='entry_read'
        s,reply=remote.exchange(s,v,NOW+1)
        self.assertEqual(reply['command']['action'],'entry_read')
        self.assertLessEqual(reply['command']['expiresAt'],NOW+21)
        self.assertEqual(reply['command']['listBatchId'],LIST)

    def test_missing_signal_stale_plan_wrong_list_and_expiry_do_not_queue(self):
        variants=[]
        p=planning();p['resultFresh']=False;variants.append(p)
        p=planning();p['result']['items'][0]['entrySuitable']=False;variants.append(p)
        p=planning();p['result']['items'][0]['available']=False;variants.append(p)
        p=planning();p['result']['items'][0]['modelReferenceAt']='bad';variants.append(p)
        for p in variants:
            s=self.state()
            with patch('handset_planning.read',return_value=p):entry.prepare(Db(s),'owner',s,NOW)
            self.assertFalse(s['commands'])
        s=self.state();db=Db(s);db.listAt='other'
        with patch('handset_planning.read',return_value=planning()):entry.prepare(db,'owner',s,NOW)
        self.assertEqual(s['entryReadStatus'],'OWNED_CURRENT_LIST_REQUIRED')
        s=self.state();s['expiresAt']=NOW+59
        with patch('handset_planning.read',side_effect=AssertionError('No query')):
            entry.prepare(Db(s),'owner',s,NOW)

    def test_receipt_bound_to_request_and_never_approves_trade(self):
        s=self.state();db=Db(s)
        with patch('handset_planning.read',return_value=planning()):
            entry.prepare(db,'owner',s,NOW)
            request=s['entryRead']
            run=dict(batchId=request['requestId'],revision=1,isins=[ISIN],requestedFields={ISIN:entry.FIELDS})
            db.run=dict(results=[dict(code='COMPLETE',observation=dict(
                observedAt=datetime.fromtimestamp(NOW+10,timezone.utc).isoformat()))])
            entry.receipt(db,'owner',LIST,dict(run,batchId='old'),NOW+20)
            self.assertIsNone(db.saved)
            with self.assertRaises(ValueError):entry.receipt(db,'owner','wrong',run,NOW+20)
            entry.receipt(db,'owner',LIST,run,NOW+20)
            self.assertEqual(db.saved['entryRead']['status'],'read-received-source-time-unverified')
            self.assertFalse(db.saved['entryRead']['entryApproved'])
            db.run['results'][0]['observation']['observedAt']=AT
            entry.receipt(db,'owner',LIST,run,NOW+20)
            self.assertEqual(db.saved['entryRead']['status'],'capture-time-invalid')
            entry.receipt(db,'owner',LIST,run,NOW+181)
            self.assertEqual(db.saved['entryRead']['status'],'expired')
            p=planning();p['revision']=4
            with patch('handset_planning.read',return_value=p):
                entry.receipt(db,'owner',LIST,run,NOW+20)
            self.assertEqual(db.saved['entryRead']['status'],'signal-or-settings-changed')

    def test_acknowledgement_is_not_a_read_receipt_and_expiry_never_requeues(self):
        s=self.state();db=Db(s)
        with patch('handset_planning.read',return_value=planning()):entry.prepare(db,'owner',s,NOW)
        s['commands'][0].update(status='acknowledged',result='ENTRY_READ_STARTED')
        entry.prepare(db,'owner',s,NOW+20)
        self.assertEqual(s['entryRead']['status'],'awaiting-read-receipt')
        entry.prepare(db,'owner',s,NOW+181)
        self.assertEqual(s['entryRead']['status'],'expired')
        self.assertEqual(len(s['commands']),1)
