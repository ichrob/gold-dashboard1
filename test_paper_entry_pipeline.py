import json
import subprocess
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock
import paper_simulation as sim
import paper_portfolios as profiles

NOW=int(datetime(2026,10,14,12,tzinfo=timezone.utc).timestamp()*1000)
ISIN='DE000FG7K275'


class EntryPipelineTests(unittest.TestCase):
    def fixture(self):
        at=datetime.fromtimestamp((NOW-30000)/1000,timezone.utc).isoformat()
        conditions={k:dict(value=v,source='https://issuer.test/'+ISIN,at=at,
                       reviewedAt=at,conditionVerified=True,dateText='14.10.2026')
                    for k,v in dict(underlying='XAU/USD',currency='EUR',ratio=.1,
                       type='BEST Turbo-Optionsscheine (Open-End)',maturity='Open End',ko=4400.,strike=4400.).items()}
        q=dict(isin=ISIN,productVerified=True,paperQuoteAccepted=True,found=True,eligible=False,
          marketOpen=True,source='comdirect · SG LiveTrading',venue='LT Societe Generale',currency='EUR',
          priceKind='market-observation',isExecutableQuote=False,degiroExecutable=False,
          bid=9.99,ask=10.,price=10.,bidAt=at,askAt=at,quoteAt=at,checkedAt=at,leverage=35.,conditions=conditions,
          metadata=dict(status=1,direction='SHORT',underlyingType='SPOT',underlying='XAU/USD',
            issuerExchangeCode='CBDE',currency='EUR',ratio=.1,ko=4400.,strike=4400.,termsDated=True),
          leverageCalculation=dict(available=True,inputsFresh=True,inputs=dict(basisPriceUsd=4000.,
            basisAt=at,usdEur=.9,ratio=.1,askEur=10.,fxDataAt=at,fxEffectiveAt=at)))
        m=dict(direction='SHORT',price=4000.,priceFresh=True,ready=True,dataAt=NOW,score=0,
          session=dict(entryAllowed=True),atr=10.,ruleVersion='intraday-trend-follow-v7',analysisBarAt=NOW-300000,
          trendContext=dict(available=True,intact=True,direction='SHORT'),
          plan=dict(kind='candidate',direction='SHORT',unit='USD/oz',entry=4000.,stop=4020.,target=3960.),
          context=dict(policy='intraday-trend-follow-v7',signalScore=0,trend='SHORT',trend2='NEUTRAL',
                       mtf='SHORT',hist=-1,momentum=-1,rsi=40,atr=10))
        return q,m

    def test_confirmed_short_reaches_all_four_main_ledgers_at_observed_ask(self):
        q,m=self.fixture()
        request=dict(products=[dict(isin=ISIN,name='SG Gold BEST SHORT',productDirection='SHORT')],quotes={ISIN:q},market=m,bundle={})
        result=subprocess.run(['node','-e',"const fs=require('fs');const x=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(require('./paper_selection').evaluate(x,"+str(NOW)+")));"],input=json.dumps(request),text=True,capture_output=True,check=True)
        selected=json.loads(result.stdout)
        self.assertTrue(selected['choices'][0]['paperOnly'])
        for profile in ('conservative','balanced','offensive','trend800'):
            control=dict(startAt=NOW-1,enabled=True)
            calls=[]
            def execute(sql,args=()):
                calls.append((sql,args));cursor=Mock()
                cursor.fetchone.return_value=(control,) if 'FROM bob_paper_control' in sql else ('inserted',) if 'INSERT INTO bob_paper_cases' in sql else None
                return cursor
            conn=Mock();conn.execute.side_effect=execute
            sim.run_once(conn,{},m,selected,{ISIN:q},NOW,profile_policy=profiles.POLICIES[profile])
            insert=next(args for sql,args in calls if 'INSERT INTO bob_paper_cases' in sql)
            case=json.loads(insert[3])
            self.assertEqual(case['engine']['trade']['dir'],'SHORT')
            self.assertEqual(case['entryAsk'],10.)
            self.assertGreater(case['quantity'],0)
            self.assertFalse(case['entryQuote']['degiroExecutable'])
            daily=next(args for sql,args in calls if 'INSERT INTO bob_paper_days' in sql)
            self.assertNotIn('entryBlocks',json.loads(daily[1]))

    def test_chf_sources_convert_and_select_without_broker_execution(self):
        import copy
        from unittest.mock import patch
        from swissquote_quotes import source_url
        for source in ('chart','swissquote'):
            q,m=self.fixture();at=q['askAt']
            q.update(found=False,paperQuoteAccepted=False,currency='CHF')
            q['metadata'].update(issuerExchangeCode='CBSW',currency='CHF')
            q['conditions']['currency']['value']='CHF'
            q['leverageCalculation']['inputs'].update(quoteCurrency='CHF',usdEur=.8,askNative=8.)
            q['nativeChartEvidence']=dict(bid=7.99,ask=8.,currency='CHF',pointAt=at)
            if source=='swissquote':
                q.pop('nativeChartEvidence')
                q['thirdQuote']=dict(isin=ISIN,direction='SHORT',source='Swissquote · Swiss DOTS',
                    sourceUrl=source_url(ISIN),venue='Swiss DOTS',currency='CHF',bid=7.99,ask=8.,
                    bidAt=at,askAt=at,quoteAt=at,priceKind='market-observation',delayed=False,
                    marketOpen=True,isExecutableQuote=False,degiroExecutable=False)
            fx=dict(result='success',base='USD',market_session='open',sources=dict(EUR='live',CHF='live'),
                    rates=dict(EUR=.9,CHF=.8),data_updated_at=at,effective_at=dict(EUR=at,CHF=at))
            original=copy.deepcopy(q)
            with patch('sg_quotes.market_input',return_value=fx):
                projected=sim.paper_quote(q,NOW,ISIN)
                saved=sim.fresh_quote(projected,NOW,ISIN)
            self.assertEqual(q,original)
            self.assertAlmostEqual(projected['ask'],9.)
            self.assertEqual(saved['paperNativeQuote']['ask'],8.)
            self.assertFalse(saved['degiroExecutable'])
            request=dict(products=[dict(isin=ISIN,name='SG Gold SHORT',productDirection='SHORT')],quotes={ISIN:projected},market=m,bundle={})
            script="const fs=require('fs'),x=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify(require('./paper_selection').evaluate(x,"+str(NOW)+")));"
            selected=json.loads(subprocess.run(['node','-e',script],input=json.dumps(request),text=True,capture_output=True,check=True).stdout)
            self.assertTrue(selected['choices'],selected)
            self.assertTrue(selected['choices'][0]['paperOnly'],selected)
            with patch('sg_quotes.market_input',return_value=fx):
                case=sim.new_case(m,selected['choices'][0],projected,NOW,cash=100.)
            self.assertEqual(case['entryQuote']['paperNativeQuote']['currency'],'CHF')
            self.assertEqual(case['entryAsk'],9.)
            for profile in ('conservative','balanced','offensive','trend800'):
                calls=[]
                def execute(sql,args=()):
                    calls.append((sql,args));cursor=Mock()
                    cursor.fetchone.return_value=({'startAt':NOW-1,'enabled':True},) if 'FROM bob_paper_control' in sql else ('inserted',) if 'INSERT INTO bob_paper_cases' in sql else None
                    return cursor
                conn=Mock();conn.execute.side_effect=execute
                with patch('sg_quotes.market_input',return_value=fx):
                    sim.run_once(conn,{},m,selected,{ISIN:projected},NOW,profile_policy=profiles.POLICIES[profile])
                saved_case=json.loads(next(args for sql,args in calls if 'INSERT INTO bob_paper_cases' in sql)[3])
                self.assertEqual(saved_case['entryAsk'],9.)
                self.assertEqual(saved_case['entryQuote']['paperNativeQuote']['currency'],'CHF')
            changed=copy.deepcopy(fx);changed['rates']['EUR']=1.
            with patch('sg_quotes.market_input',return_value=changed):
                exit_quote=sim.fresh_quote(q,NOW,ISIN)
            self.assertAlmostEqual(exit_quote['bid'],7.99*1.25)
            self.assertEqual(exit_quote['paperFxConversion']['rate'],1.25)
            with patch('sg_quotes.market_input',return_value=fx):
                self.assertIsNone(sim.fresh_quote(q,NOW+90001,ISIN))

            for bad in ({**fx,'sources':dict(EUR='live',CHF='cached')},
                        {**fx,'data_updated_at':'2026-10-14T00:00:00+00:00'}):
                with patch('sg_quotes.market_input',return_value=bad):
                    self.assertFalse(sim.paper_quote(q,NOW,ISIN).get('paperQuoteAccepted'))

    def test_bnp_backup_and_provider_leverage_reach_selector(self):
        import copy
        q,m=self.fixture()
        at=q['askAt']
        pair={k:q[k] for k in ('isin','currency','bid','ask','price','bidAt','askAt','quoteAt','priceKind','isExecutableQuote','degiroExecutable')}
        pair.update(source='comdirect · BNP LiveTrading',venue='LT BNP Paribas')
        q.update(source='BNP Paribas · Emittent OTC',sourceUrl='https://derivate.bnpparibas.com/product-details/'+ISIN+'/',
                 secondaryQuote=pair,found=True,isExecutableQuote=True,leverage=30.,leverageAt=at,leverageEstimated=False)
        q['metadata'].pop('issuerExchangeCode')
        q['bidAt']=q['askAt']='2026-10-14T11:40:00+00:00'
        projected=sim.paper_quote(q,NOW,ISIN)
        self.assertTrue(projected['paperQuoteAccepted'])
        self.assertEqual(projected['source'],pair['source'])
        request=dict(products=[dict(isin=ISIN,name='Gold SHORT',productDirection='SHORT')],quotes={ISIN:projected},market=m,bundle={})
        script="const fs=require('fs'),x=JSON.parse(fs.readFileSync(0,'utf8')),p=require('./paper_selection');process.stdout.write(JSON.stringify({q:p.selectionQuote(x.quotes['"+ISIN+"'],"+str(NOW)+"),selection:p.evaluate(x,"+str(NOW)+")}));"
        out=json.loads(subprocess.run(['node','-e',script],input=json.dumps(request),text=True,capture_output=True,check=True).stdout)
        self.assertEqual(out['q']['leverage'],30.)
        self.assertEqual(out['q']['paperLeverage']['kind'],'provider')
        self.assertTrue(out['selection']['choices'][0]['paperOnly'])
        bad=copy.deepcopy(q);bad['secondaryQuote']['venue']='LT Societe Generale'
        self.assertNotEqual(sim.paper_quote(bad,NOW,ISIN)['source'],pair['source'])

    def test_block_history_counts_checks_and_retains_changed_direction(self):
        data={'waitChecks':0};conn=Mock()
        conn.execute.return_value.fetchone.return_value=(data,)
        for direction in ('SHORT','SHORT','LONG'):
            sim.day_update(conn,'2026-10-14',wait='Beleg fehlt',now=NOW,entry=dict(direction=direction,isin=ISIN))
            data=json.loads(conn.execute.call_args.args[1][1])
            conn.execute.return_value.fetchone.return_value=(data,)
        self.assertEqual(data['entryBlockCounts']['Beleg fehlt'],3)
        self.assertEqual(len(data['entryBlocks']),2)
        self.assertEqual(data['entryBlocks'][0]['checks'],2)
        self.assertEqual(data['entryBlocks'][1]['direction'],'LONG')


if __name__=='__main__':unittest.main()
