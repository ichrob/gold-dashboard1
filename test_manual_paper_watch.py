"""Regression: preserve manual test, avoid stale/phantom outcomes, observe server-side."""
import datetime as dt
import os
import unittest
from unittest.mock import Mock

import manual_paper_watch as watch

ISIN='DE000FC1CHB7'


def position():
    return dict(mode='manual-paper-test',isin=ISIN,direction='LONG',
                entry=8.,quantity=100,
                createdAt=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=1)).isoformat())


def current_quote(at=None):
    at=at or dt.datetime.now(dt.timezone.utc)
    return dict(isin=ISIN, productVerified=True,found=True,marketOpen=True,
                currency='EUR',source='Anbieter-Muster',bid=8.5,ask=8.6,
                bidAt=at.isoformat(),isExecutableQuote=True)


class FakeConn:
    def __init__(self):
        self.state=None
        self.observations={}
        self.last=None

    def execute(self,sql,args=()):
        import json
        self.last=None
        if 'FROM bob_manual_paper_watch' in sql and sql.lstrip().startswith('SELECT'):
            if self.state is not None:self.last=(dict(self.state),)
        elif sql.startswith('INSERT INTO bob_manual_paper_watch'):
            if self.state is None:self.state=json.loads(args[0])
        elif sql.startswith('UPDATE bob_manual_paper_watch'):
            self.state=json.loads(args[0])
        elif 'INSERT INTO bob_manual_paper_observations' in sql:
            key=(args[1],args[0])
            if key not in self.observations:
                self.observations[key]=args
                self.last=(args[0],)
        elif 'FROM bob_manual_paper_observations' in sql:
            self._many=[(at,rec[2],rec[3],rec[4],rec[5])
                        for (isin,at),rec in self.observations.items() if isin==args[0]]
        return self

    def fetchone(self):return self.last
    def fetchall(self):return getattr(self,'_many',[])


class ManualWatchTests(unittest.TestCase):
    def test_original_800_eur_trade_identity(self):
        p=watch.validate_position(position())
        self.assertEqual(p['isin'],ISIN)
        self.assertEqual(p['quantity'],100)
        self.assertEqual(p['entry']*p['quantity'],800)
        with self.assertRaises(ValueError):
            watch.validate_position({**position(),'quantity':0})

    def test_connect_once_and_never_overwrite_local_trade(self):
        db=FakeConn()
        original=position()
        r=watch.sync(db,{'position':original})
        self.assertTrue(r['ok'])
        self.assertEqual(db.state['position']['entry'],8)
        self.assertIsNone(db.state['valuation'])
        r=watch.sync(db,{'position':original})
        self.assertTrue(r['ok'])
        self.assertTrue(r['existing'])
        rejected=watch.sync(db,{'position':{**original,'entry':9.}})
        self.assertFalse(rejected['ok'])
        self.assertEqual(db.state['position']['entry'],8.)

    def test_quote_freshness_and_source_gates(self):
        now=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
        self.assertIsNotNone(watch.quote_observation(current_quote(),ISIN,now)[0])
        stale=current_quote(dt.datetime.now(dt.timezone.utc)-dt.timedelta(minutes=3))
        self.assertIsNone(watch.quote_observation(stale,ISIN,now)[0])
        self.assertIsNone(watch.quote_observation({**current_quote(),'productVerified':False},ISIN,now)[0])
        self.assertIsNone(watch.quote_observation({**current_quote(),'priceKind':'issuer-chart'},ISIN,now)[0])
        self.assertIsNone(watch.quote_observation({**current_quote(),'currency':'CHF'},ISIN,now)[0])

    def test_background_observations_do_not_create_trades(self):
        db=FakeConn()
        watch.sync(db,{'position':position()})
        now=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
        observed_quote=current_quote()
        watch.observe(db,observed_quote,now)
        self.assertEqual(len(db.observations),1)
        self.assertEqual(db.state['eventsCount'],1)
        self.assertEqual(db.state['valuation']['pnlEur'],50)
        self.assertEqual(db.state['valuation']['valueEur'],850)
        watch.observe(db,observed_quote,now)
        self.assertEqual(db.state['eventsCount'],1)
        # An unavailable quote must never leave old equity labeled as current.
        watch.observe(db,None,now)
        self.assertEqual(db.state['status'],'waiting-quote')
        self.assertIsNone(db.state['valuation'])
        self.assertEqual(db.state['position']['entry'],8.)
        self.assertEqual(db.state['position']['quantity'],100)

    def test_stop_and_target_require_explicit_approved_levels(self):
        db=FakeConn()
        watch.sync(db,{'position':position()})
        self.assertEqual(db.state['alerts'],[])
        self.assertFalse(db.state['stopEur'])
        self.assertFalse(db.state['targetEur'])
        with self.assertRaises(ValueError):
            watch.set_levels(db,dict(stopEur=9.,targetEur=10.))
        watch.set_levels(db,dict(stopEur=7.5,targetEur=8.25))
        # Capture the quote before the observation clock; otherwise a
        # millisecond-later mock quote can appear "from the future".
        quote=current_quote()
        now=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
        watch.observe(db,quote,now)
        self.assertEqual(db.state['alerts'][-1]['kind'],'target-observed')
        self.assertEqual(db.state['position']['entry'],8.)

    def test_bought_short_certificate_uses_product_price_for_profit_stop_target(self):
        # SHORT is the gold exposure; the customer BOUGHT the certificate.
        db=FakeConn()
        watch.sync(db,{'position':{**position(),'direction':'SHORT'}})
        watch.set_levels(db,dict(stopEur=7.5,targetEur=8.25))
        one=current_quote(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=2))
        now=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
        watch.observe(db,one,now)
        self.assertEqual(db.state['valuation']['pnlEur'],50)
        self.assertEqual(db.state['alerts'][-1]['kind'],'target-observed')
        two=current_quote(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=1))
        two.update(bid=7,ask=7.02)
        watch.observe(db,two,now)
        self.assertEqual(db.state['valuation']['pnlEur'],-100)
        self.assertEqual(db.state['alerts'][-1]['kind'],'stop-observed')
        with self.assertRaises(ValueError):
            watch.set_levels(db,dict(stopEur=8.4,targetEur=7.2))

    def test_legacy_reversed_short_levels_never_generate_false_alert(self):
        db=FakeConn()
        watch.sync(db,{'position':{**position(),'direction':'SHORT'}})
        # Earlier server versions stored SHORT-product model levels inverted.
        db.state['stopEur']=9.5
        db.state['targetEur']=7.
        now=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
        watch.observe(db,current_quote(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=2)),now)
        self.assertEqual(db.state['valuation']['pnlEur'],50)
        self.assertEqual(db.state['status'],'levels-need-review')
        self.assertIn('Stopp muss unter',db.state['reason'])
        self.assertEqual(db.state['alerts'],[])
        self.assertEqual(db.state['stopEur'],9.5)
        self.assertEqual(db.state['targetEur'],7.)
        # An explicit corrected owner input restores ordinary monitoring.
        watch.set_levels(db,dict(stopEur=7.5,targetEur=8.25))
        q=current_quote(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=1))
        watch.observe(db,q,now)
        self.assertEqual(db.state['alerts'][-1]['kind'],'target-observed')

    def verified_comdirect_paper_research(self,age_seconds=2):
        at=(dt.datetime.now(dt.timezone.utc)-dt.timedelta(seconds=age_seconds)).isoformat()
        pair=dict(isin=ISIN,bid=8.5,ask=8.6,quoteAt=at,bidAt=at,askAt=at,
                  currency='EUR',source='comdirect · SG LiveTrading',
                  venue='LT Societe Generale',priceKind='market-observation',
                  isExecutableQuote=False,degiroExecutable=False)
        return dict(isin=ISIN,productVerified=True,found=False,eligible=False,
                    currency='EUR',source='Société Générale · Direktimport',
                    metadata=dict(status=1,direction='LONG',issuerExchangeCode='CBDE'),
                    secondaryQuote=pair)

    def test_researched_comdirect_pair_values_paper_only_without_stop_alert(self):
        db=FakeConn()
        watch.sync(db,{'position':position()})
        watch.set_levels(db,dict(stopEur=7.5,targetEur=8.25))
        now=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
        raw=self.verified_comdirect_paper_research()
        result=watch.observe(db,raw,now)
        self.assertEqual(result['watch']['status'],'model-observed')
        self.assertEqual(result['watch']['valuation']['pnlEur'],50)
        self.assertTrue(result['watch']['valuation']['referenceOnly'])
        self.assertFalse(result['watch']['valuation']['degiroExecutable'])
        self.assertIn('keine ausführbare DEGIRO-Quote',result['watch']['reason'])
        self.assertEqual(result['watch']['alerts'],[])
        self.assertFalse(raw.get('paperQuoteAccepted',False))
        self.assertFalse(raw['secondaryQuote']['isExecutableQuote'])

    def test_research_fallback_never_backfills_bad_or_undated_quotes(self):
        for change in ('old','mismatch','inactive','wrong-currency','wrong-upstream'):
            with self.subTest(change=change):
                db=FakeConn()
                watch.sync(db,{'position':position()})
                raw=self.verified_comdirect_paper_research(181 if change=='old' else 2)
                if change=='mismatch':raw['secondaryQuote']['isin']='DE000FG4JXV7'
                if change=='inactive':raw['metadata']['status']=2
                if change=='wrong-currency':raw['secondaryQuote']['currency']='CHF'
                if change=='wrong-upstream':raw['secondaryQuote']['source']='unknown'
                now=int(dt.datetime.now(dt.timezone.utc).timestamp()*1000)
                watch.observe(db,raw,now)
                self.assertEqual(db.state['status'],'waiting-quote')
                self.assertIsNone(db.state['valuation'])
                self.assertEqual(db.state['alerts'],[])

    def test_conflicting_issuer_direction_never_values_existing_test(self):
        db=FakeConn()
        watch.sync(db,{'position':position()})
        raw=current_quote()
        raw['metadata']=dict(status=1,direction='SHORT')
        watch.observe(db,raw)
        self.assertEqual(db.state['status'],'waiting-quote')
        self.assertIn('Produktrichtung',db.state['reason'])
        self.assertFalse(db.observations)

    @unittest.skipUnless(os.environ.get('BOB_TEST_DATABASE_URL'),
                         'Requires ephemeral CI database')
    def test_database_isolation_and_restart_resume(self):
        import psycopg
        con=psycopg.connect(os.environ['BOB_TEST_DATABASE_URL'])
        try:
            watch.init(con)
            p=position()
            self.assertTrue(watch.sync(con,{'position':p})['ok'])
            before=con.execute('SELECT count(*) FROM bob_paper_cases').fetchone()[0] if con.execute(
                "SELECT to_regclass('bob_paper_cases')").fetchone()[0] else None
            r=watch.observe(con,current_quote())
            self.assertEqual(r['watch']['eventsCount'],1)
            check=watch.report(con)
            self.assertTrue(check['connected'])
            self.assertEqual(check['watch']['position']['quantity'],100)
            self.assertEqual(len(check['observations']),1)
            con.commit()
            # Re-attach to existing durable record after a separate DB session.
            again=watch.report(con)
            self.assertEqual(again['watch']['eventsCount'],1)
            if before is not None:
                self.assertEqual(con.execute('SELECT count(*) FROM bob_paper_cases').fetchone()[0],before)
        finally:
            # CI database is discarded after tests.
            con.close()


if __name__=='__main__':
    unittest.main()
