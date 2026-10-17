import copy
import json
import math
import os
import subprocess
import unittest
import uuid
import metric_quality as q

NOW=1800000000000


def bars(flat=False):
    out=[]
    for i in range(240):
        v=4200 if flat else 4200+10*math.sin(i/8)+i*.02
        out.append(dict(openTime=NOW-(240-i)*300000,open=v,close=v,
            high=v+(0 if flat else 2),low=v-(0 if flat else 1),instrument='XAU/USD',isOpen=False))
    return out


class MathTests(unittest.TestCase):
    def test_independent_decimal_reference_against_actual_javascript(self):
        script="""
const fs=require('fs'),vm=require('vm'),h=fs.readFileSync('Bob.html','utf8');
const env={};vm.createContext(env);
vm.runInContext(h.slice(h.indexOf('function ema('),h.indexOf('function analyze('))+
h.slice(h.indexOf('function dmiCalc('),h.indexOf('// Shadow-only DMI')),env);
const b=JSON.parse(fs.readFileSync(0,'utf8'));env.C=b;
process.stdout.write(JSON.stringify({...env.calc(),...env.dmiCalc(b)}));
"""
        for b in (bars(),bars(True),list(reversed([dict(x,openTime=NOW-(i+1)*300000) for i,x in enumerate(bars())]))):
            actual=json.loads(subprocess.check_output(['node','-e',script],input=json.dumps(b),text=True))
            result=q.compare(b,actual,'5m',NOW)
            self.assertEqual(result['status'],'matched',result)
            self.assertEqual(len(result['metrics']),11)
    def test_detects_real_error_and_refuses_gaps_open_future_and_foreign_inputs(self):
        b=bars();a=q.reference(b);a['R']+=.2
        self.assertEqual(q.compare(b,a,'5m',NOW)['status'],'mismatch')
        for change in (dict(isOpen=True),dict(instrument='GC=F'),dict(high=0),dict(openTime=NOW+300000),dict(estimated=True)):
            changed=copy.deepcopy(b);changed[-1].update(change)
            self.assertEqual(q.compare(changed,a,'5m',NOW)['status'],'unavailable')
        self.assertEqual(q.compare(b[:-2]+b[-1:],a,'5m',NOW)['status'],'unavailable')
        self.assertEqual(q.compare(b,a,'5m',NOW+600001)['status'],'unavailable')
    def test_flat_boundaries_and_exact_tr_definition(self):
        a=q.reference(bars(True))
        self.assertEqual(a['R'],50);self.assertEqual(a['at'],0);self.assertEqual(a['adx'],0)
        self.assertEqual(a['macd'],0);self.assertEqual(a['e200'],4200)
        self.assertGreater(q.reference(bars())['at'],0)


@unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),'PostgreSQL integration runs in CI')
class PersistenceTests(unittest.TestCase):
    def test_immutable_math_and_precision_evidence_survive_commit(self):
        import psycopg
        from psycopg import sql
        import product_precision as p
        import precision_learning as learning
        schema='metrics_'+uuid.uuid4().hex
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            conn.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
            try:
                conn.execute(sql.SQL('SET search_path TO {}').format(sql.Identifier(schema)))
                q.init(conn);p.init(conn);learning.init(conn)
                b=bars();market={'analysisSnapshot':dict(q.reference(b),timeframe='5m')}
                bundle={'history':{'bars_by_tf':{'5m':b}}}
                q.capture(conn,bundle,market,NOW);conn.commit()
                market['analysisSnapshot']['R']+=1
                q.capture(conn,bundle,market,NOW+1000);conn.commit()
                report=q.report(conn,NOW+1000)
                self.assertTrue(report['rows'])
                self.assertTrue(all(r['count']==1 and r['mismatches']==0 for r in report['rows']))
                from test_product_comparison_worker import QUOTE
                from test_product_trade_history import NOW as quote_now,SPOTS,PRODUCT
                for _ in range(2):p.observe(conn,QUOTE,SPOTS,quote_now.timestamp()*1000)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_precision_quotes').fetchone()[0],1)
                for i in range(90):
                    learning.observe(conn,PRODUCT,dict(source='fixture',at=NOW+i*60000,estimated=10,quoted=10.1))
                conn.commit()
                policy=learning.for_product(conn,PRODUCT,NOW+89*60000)
                self.assertTrue(policy['usable'],policy)
                self.assertEqual(conn.execute('SELECT count(*) FROM bob_precision_events').fetchone()[0],2)
                learning.control(conn,False,NOW+90*60000);conn.commit()
                self.assertFalse(learning.for_product(conn,PRODUCT,NOW+90*60000)['usable'])
                self.assertFalse(learning.report(conn,NOW+90*60000)['enabled'])
                learning.control(conn,True,NOW+91*60000);conn.commit()
                self.assertEqual(learning.for_product(conn,PRODUCT,NOW+91*60000)['phase'],'training')
                self.assertEqual(p.report(conn)['cases'],0)
                p.harvest(conn,NOW)
            finally:
                conn.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
