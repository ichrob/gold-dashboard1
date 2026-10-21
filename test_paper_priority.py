import copy
import json
import os
import unittest
from unittest.mock import Mock,patch
import paper_entry_review as review
import paper_stop_study as study
import paper_simulation as sim
import test_paper_simulation as f

NOW=f.NOW

def bundle():
    end=NOW//300000*300000
    return dict(history=dict(bars_by_tf={'5m':[dict(openTime=end-(20-i)*300000,isOpen=False,instrument='XAU/USD',low=85.,high=115.,close=100.) for i in range(20)]}))

def case(direction='LONG'):
    c=sim.new_case(f.market(direction),dict(isin=f.ISIN,scope='XAU/USD',direction=direction),f.quote(),NOW,cash=100,bundle=bundle())
    c['profile']='balanced';return c

class PriorityTests(unittest.TestCase):
    def test_checklist_freezes_source_context_and_reason_without_approval(self):
        m=f.market();m['session']={'entryAllowed':True};m['analysisSnapshot']={'R':60,'at':10,'e20':101}
        before=copy.deepcopy(m)
        c=review.capture(m,dict(isin=f.ISIN),f.quote(),NOW,True,'Prüfungen bestanden')
        self.assertEqual(c['requiredFailures'],[])
        self.assertEqual(c['sourceAt'],NOW);self.assertEqual(c['context']['indicators']['rsi'],60)
        self.assertFalse(c['affectsApproval']);m['analysisSnapshot']['R']=0
        self.assertEqual(c['context']['indicators']['rsi'],60)
        blocked=review.capture({**before,'priceFresh':False},None,None,NOW,False,'Kurs fehlt')
        self.assertEqual(blocked['decision'],'wait');self.assertIn('fresh',blocked['requiredFailures'])
        self.assertIn('product',blocked['requiredFailures'])

    def test_direction_mismatch_is_blocked_before_a_new_virtual_entry(self):
        market=f.market();market['session']={'entryAllowed':True}
        market['plan']=f.market('SHORT')['plan']
        control={'startAt':NOW-1,'enabled':True};calls=[]
        def execute(sql,args=()):
            calls.append((sql,args));cur=Mock()
            cur.fetchone.return_value=(control,) if 'FROM bob_paper_control' in sql else None
            return cur
        conn=Mock();conn.execute.side_effect=execute
        sim.run_once(conn,bundle(),market,{'choices':[dict(isin=f.ISIN,scope='XAU/USD')]},{f.ISIN:f.quote()},NOW)
        self.assertFalse(any('INSERT INTO bob_paper_cases' in sql for sql,_ in calls))
        self.assertIn('plan',control['lastEntryChecklist']['requiredFailures'])
        self.assertEqual(control['lastEntryChecklist']['decision'],'wait')

    def test_daily_never_calls_legacy_unknown_or_loss_an_avoidable_error(self):
        c=case();c['entryChecklist']=review.capture(f.market(),dict(isin=f.ISIN),f.quote(),NOW,True,'bestanden')
        legacy=case();legacy.pop('entryChecklist',None)
        out=review.daily([c,legacy],{'waitChecks':3},c['day'])
        self.assertEqual(out['legacyEntries'],1)
        self.assertEqual(out['requiredViolations'],0)
        self.assertEqual(out['ruleConsistent'],0,'Missing session proof is not a passed checklist')
        self.assertIsNone(out['modelNetEur']);self.assertEqual(out['waitChecks'],3)

    def test_setup_uses_only_twenty_closed_contiguous_spot_bars_and_actual_atr(self):
        b=bundle();m=f.market();s=study.setup(m,b,NOW)
        self.assertEqual(s['stops'],dict(fixed=90,atr=85,structure=85))
        b['history']['bars_by_tf']['5m'].append(dict(openTime=NOW,isOpen=True,instrument='XAU/USD',low=1,high=999,close=100))
        self.assertEqual(study.setup(m,b,NOW)['stops'],s['stops'])
        b['history']['bars_by_tf']['5m'][0]['instrument']='GC'
        self.assertIsNone(study.setup(m,b,NOW)['stops']['structure'])
        self.assertIsNone(study.setup({**m,'atr':None},bundle(),NOW)['stops']['atr'])

    def test_variants_remain_independent_and_use_observed_bid_and_costs(self):
        for direction in ('LONG','SHORT'):
            c=case(direction);original=copy.deepcopy(c);s=study.create(c)
            sign=1 if direction=='LONG' else -1
            # Only the fixed stop exits. Other variants continue after real case closure.
            t=NOW+30000;m={**f.market(direction),'dataAt':t,'price':100-sign*11}
            s=study.advance(s,m,f.quote(t,bid=9.,ask=9.1),t)
            self.assertEqual(s['variants']['fixed']['status'],'observed-stop')
            self.assertEqual(s['variants']['atr']['status'],'open')
            self.assertFalse(s['complete']);self.assertEqual(c,original)
            t+=30000;m.update(dataAt=t,price=100-sign*16)
            s=study.advance(s,m,f.quote(t,bid=8.,ask=8.1),t)
            self.assertTrue(s['complete'])
            v=s['variants']['atr'];self.assertEqual(v['status'],'observed-stop')
            self.assertLess(v['modelNetEur'],(8-c['entryAsk'])*c['quantity'])
            self.assertEqual(study.advance(s,m,f.quote(t),t),s,'Replay cannot charge costs again')

    def test_missing_or_regressing_quotes_are_never_winning_pairs(self):
        c=case();s=study.create(c);t=NOW+120000
        s=study.advance(s,{**f.market(),'dataAt':t,'price':130},f.quote(t,bid=14,ask=14.1),t)
        self.assertTrue(s['complete']);self.assertTrue(s['gap'])
        self.assertTrue(all(v['modelNetEur'] is None for v in s['variants'].values()))
        s=study.create(c)
        s=study.advance(s,{**f.market(),'dataAt':t,'price':130},None,c['endsAt']+100000)
        self.assertTrue(s['complete']);self.assertTrue(all(v['status']=='inconclusive' for v in s['variants'].values()))

    def test_ko_guard_failure_or_crossing_never_produces_a_profit(self):
        c=case();c['koGuardRequired']=True;s=study.create(c);t=NOW+30000
        m={**f.market(),'dataAt':t,'price':130}
        with patch('paper_ko_guard.assess',return_value=(dict(danger=True,crossed=True),None)):
            s=study.advance(s,m,f.quote(t,bid=14,ask=14.1),t)
        self.assertTrue(all(v['status']=='inconclusive' for v in s['variants'].values()))
        self.assertTrue(all(v['modelNetEur'] is None for v in s['variants'].values()))

    def test_paired_report_excludes_missing_variant_or_gap_and_does_not_promote(self):
        c=case();s=study.create(c);t=NOW+30000
        s=study.advance(s,{**f.market(),'dataAt':t,'price':130},f.quote(t,bid=14,ask=14.1),t)
        bad=copy.deepcopy(s);bad['variants']['structure'].update(status='unavailable',modelNetEur=None)
        conn=Mock();conn.execute.return_value.fetchall.return_value=[(s,),(bad,)]
        r=study.report(conn,c['day']);self.assertEqual(r['paired'],1)
        self.assertEqual(r['unavailable'],1);self.assertFalse(r['promoted'])
        self.assertTrue(all(x['paired']==1 for x in r['variants']))

@unittest.skipUnless(os.getenv('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class PersistenceTests(unittest.TestCase):
    def test_study_survives_case_closure_restart_and_never_changes_cash(self):
        import psycopg,uuid
        from psycopg import sql
        c=case();c.update(status='closed')
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            schema='priority_'+uuid.uuid4().hex
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
            study.init(conn)
            conn.execute('CREATE TABLE bob_paper_balanced_cases(id TEXT,payload JSONB,started_at TIMESTAMPTZ)')
            conn.execute('INSERT INTO bob_paper_balanced_cases VALUES(%s,%s::jsonb,now())',(c['id'],json.dumps(c)))
            t=NOW+30000;m={**f.market(),'dataAt':t,'price':89}
            study.tick(conn,m,{f.ISIN:f.quote(t,bid=9,ask=9.1)},t)
            self.assertEqual(study.active_isins(conn),[f.ISIN]);study.init(conn)
            t+=30000;m.update(dataAt=t,price=84)
            study.tick(conn,m,{f.ISIN:f.quote(t,bid=8,ask=8.1)},t)
            r=study.report(conn,c['day']);self.assertEqual(r['total'],1);self.assertEqual(r['paired'],1)
            study.tick(conn,m,{f.ISIN:f.quote(t)},t)
            self.assertEqual(study.report(conn,c['day']),r)
            self.assertEqual(conn.execute('SELECT payload FROM bob_paper_balanced_cases').fetchone()[0],c)
            conn.rollback()
