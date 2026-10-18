"""Offline Monday pipeline: real shared analysis, selector, paper ledger and reflection.
Synthetic inputs only; never contact a broker or generate a live trade.
"""
import copy,json,os,subprocess,unittest,uuid
from datetime import datetime,timezone
from unittest.mock import patch,Mock
import paper_simulation as sim
import paper_portfolios as portfolios
import paper_ledger_costs as costs
import paper_reflection
import test_paper_entry_pipeline as entry_fixture
ISIN=entry_fixture.ISIN

NOW=int(datetime(2026,10,19,9,12,tzinfo=timezone.utc).timestamp()*1000)
SCRIPT=r'''
const fs=require('fs'),input=JSON.parse(fs.readFileSync(0,'utf8')),now=input.now,Real=Date;
global.Date=class extends Real{constructor(...a){super(...(a.length?a:[now]))}static now(){return now}};
const bars={};for(const [tf,step] of Object.entries({'1m':60000,'5m':300000,'15m':900000,'30m':1800000,'1h':3600000,'4h':14400000})){
 const end=Math.floor(now/step)*step;bars[tf]=Array.from({length:240},(_,i)=>({openTime:end-(240-i)*step,
 open:4100-i*.1,high:4104-i*.1,low:4096-i*.1,close:4100-i*.1+Math.sin(i/8),isOpen:false,instrument:'XAU/USD'}));
}
[4076,4076.1,4075.5].forEach((p,j)=>Object.assign(bars['5m'][237+j],{open:p+2,close:p,high:p+4,low:p-4}));
const bundle={spots:{xaus:4075.5,is_genuine_xauusd_spot:true,spot_price_as_of:new Date(now-(input.stale?120000:0)).toISOString()},history:{bars_by_tf:bars}};
const market=require('./background_analysis').evaluate({bundle,timeframe:'15m',learningPolicy:{campaign:'entry-filter-v2-guarded',base:'intraday-trend-follow-v7',variant:'baseline',version:'baseline',issuedAt:now,expiresAt:now+120000}});
const q=input.quote;
const selection=require('./paper_selection').evaluate({products:[{isin:q.isin,name:'SG Gold BEST SHORT',productDirection:'SHORT'}],quotes:{[q.isin]:q},market,bundle},now);
process.stdout.write(JSON.stringify({market,selection,bundle}));
'''

def fixture(stale=False):
    q,_=entry_fixture.EntryPipelineTests().fixture()
    at=datetime.fromtimestamp(NOW/1000,timezone.utc).isoformat()
    for k in ('bidAt','askAt','quoteAt','checkedAt'):q[k]=at
    for cond in q['conditions'].values():cond.update(at=at,reviewedAt=at,dateText='19.10.2026')
    q['leverageCalculation']['inputs'].update(basisAt=at,fxDataAt=at,fxEffectiveAt=at,basisPriceUsd=4075.5)
    result=json.loads(subprocess.run(['node','-e',SCRIPT],input=json.dumps(dict(now=NOW,quote=q,stale=stale)),capture_output=True,text=True,check=True,timeout=30).stdout)
    return result,q

class PipelineTests(unittest.TestCase):
    def test_analysis_selection_stop_costs_and_reflection(self):
        result,q=fixture();m=result['market'];choices=result['selection']['choices']
        self.assertTrue(m['ready']);self.assertEqual(m['direction'],'SHORT');self.assertTrue(m['entryTimingGate']['allowed'])
        self.assertTrue(choices,result['selection']);choice=choices[0]
        self.assertTrue(choice['paperOnly']);self.assertTrue(choice['koGuardRequired'])
        self.assertIsNone(sim.paper_ko_guard.entry_reason(choice,q,m,NOW)[0])
        c=sim.new_case(m,choice,q,NOW,cash=100,cost_model=costs.MODEL)
        control=dict(cash=100-c['allocated'],realizedProfit=0.)
        costs.apply(control,c)
        self.assertLess(control['cash'],100-c['allocated'])
        later=NOW+30000
        next_market={**m,'price':m['plan']['stop']+.1,'dataAt':later}
        exit_quote={**q,'bid':9.5,'ask':9.6,'quoteAt':later,'bidAt':later,'askAt':later}
        closed=sim.advance_case(c,next_market,exit_quote,later)
        self.assertEqual(closed['exitReason'],'stop');self.assertEqual(closed['pendingUnits'],0)
        control['cash']+=closed['cashReleased'];control['realizedProfit']+=closed['cashReleased']-closed['allocated']
        costs.apply(control,closed);paper_reflection.record(control,closed,later)
        net=closed['reflection']['costModel']['modelNetEur']
        self.assertAlmostEqual(control['cash'],100+net)
        self.assertAlmostEqual(control['realizedProfit'],net)
        old=copy.deepcopy(control);costs.apply(control,closed);paper_reflection.record(control,closed,later)
        self.assertEqual(control,old)

    def test_stale_source_cannot_produce_entry_plan(self):
        result,_=fixture(stale=True)
        self.assertFalse(result['market']['priceFresh']);self.assertIsNone(result['market']['plan'])
        conn=Mock();calls=[]
        def execute(sql,args=()):
            calls.append(sql);cur=Mock()
            cur.fetchone.return_value=None
            if 'FROM bob_paper_control' in sql:cur.fetchone.return_value=({'startAt':NOW-1,'enabled':True},)
            return cur
        conn.execute.side_effect=execute
        sim.run_once(conn,result['bundle'],result['market'],result['selection'],{},NOW)
        self.assertFalse(any('INSERT INTO bob_paper_cases' in sql for sql in calls))

@unittest.skipUnless(os.getenv('BOB_TEST_DATABASE_URL'),'CI PostgreSQL integration')
class PipelineDatabaseTests(unittest.TestCase):
    def test_persisted_full_pipeline_stop_and_target_then_protection(self):
        import psycopg
        result,q=fixture();m=result['market'];selection=result['selection']
        with psycopg.connect(os.environ['BOB_TEST_DATABASE_URL']) as conn:
            for route in ('stop','target'):
                schema='pipeline_'+uuid.uuid4().hex
                conn.execute('CREATE SCHEMA '+schema);conn.execute('SET search_path TO '+schema)
                try:
                    with patch('paper_portfolios.time.time',return_value=NOW/1000):sim.init(conn)
                    ledger=portfolios.Ledger(conn,'balanced');policy=portfolios.POLICIES['balanced']
                    sim.run_once(ledger,result['bundle'],m,selection,{ISIN:q},NOW,policy)
                    case=ledger.execute('SELECT payload FROM bob_paper_cases').fetchone()[0]
                    self.assertGreater(case['ledgerCostsDebited'],0)
                    for i in (1,2):
                        t=NOW+i*30000
                        price=(case['engine']['trade']['stop']+.1 if route=='stop' or i==2
                               else case['engine']['trade']['target']-1)
                        nq={**q,'bid':9.5 if route=='stop' else 11.+i,'ask':9.6 if route=='stop' else 11.1+i,'quoteAt':t,'bidAt':t,'askAt':t}
                        sim.run_once(ledger,result['bundle'],{**m,'price':price,'dataAt':t},selection,{ISIN:nq},t,policy)
                        case=ledger.execute('SELECT payload FROM bob_paper_cases').fetchone()[0]
                        if case['status']!='open':break
                    self.assertNotEqual(case['status'],'open');self.assertEqual(case['pendingUnits'],0)
                    if route=='target':self.assertIn('partial-profit',[e['kind'] for e in case['events']])
                    control=ledger.execute('SELECT payload FROM bob_paper_control').fetchone()[0]
                    self.assertEqual(control['reflection']['evaluated'],1)
                    self.assertAlmostEqual(control['cash'],100+case['reflection']['costModel']['modelNetEur'])
                    before=control['cash']
                    sim.run_once(ledger,result['bundle'],{**m,'price':price,'dataAt':t},selection,{ISIN:nq},t,policy)
                    self.assertEqual(ledger.execute('SELECT payload FROM bob_paper_control').fetchone()[0]['cash'],before)
                finally:
                    conn.rollback()
