import copy
import json
import unittest
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
    def state(self):
        v=value();v['purpose']='entry_read'
        return remote.exchange({},v,NOW)[0]

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
