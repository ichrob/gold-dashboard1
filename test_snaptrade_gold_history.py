"""Historical SnapTrade Gold KO research stays separate from trading decisions."""
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from unittest.mock import patch

import snaptrade_gold_history as research
import degiro_catalog

Z = ZoneInfo('Europe/Zurich')
A = 'DE000PJ8APE4'
B = 'DE000FG34XV8'
C = 'DE000FG4JXV7'


def trade(isin=A, name='BNP Gold Turbo Long', action='BUY', date='2026-10-22'):
    return dict(isin=isin, name=name, type=action, date=date,
                key='normalized-provider-hash', securityKind='other')


def account(rows, complete=False, code='READ_OK'):
    return {'journal':{'activities':{'rows': rows, 'complete':complete,'code':code}}}


class HistoricalGoldResearchTests(unittest.TestCase):
    def test_history_is_candidates_only_with_partial_coverage(self):
        result=research.discover([account([
            trade(),trade(action='SELL',date='2026-10-23'),
            trade(isin=B,name='SG Gold Mini Short'),
            trade(isin=C,name='SG Gold Faktor Long'),
            trade(isin=C,name='SG Gold Future Turbo Long')])])
        self.assertEqual(result['code'],'HISTORICAL_PARTIAL')
        self.assertEqual(result['candidateCount'],2)
        self.assertEqual([x['isin'] for x in result['items']], [A,B] if False else [A,B])
        self.assertEqual(next(x for x in result['items'] if x['isin']==A)['historicRecords'],2)
        self.assertFalse(result['completeDegiroCatalog'])
        self.assertFalse(result['tradeApproved'])
        self.assertFalse(result['historyComplete'])
        self.assertTrue(all(x['currentlyDegiroListed'] is None and
                            x['eligibleForTop3'] is False and
                            x['originalBidAskConfirmed'] is False
                            for x in result['items']))

    def test_reject_non_gold_factors_wrong_underlyings_and_ambiguous_direction(self):
        for name in ('SG Gold Future Turbo Long', 'SG Gold Faktor Long',
                     'Goldman Sachs Turbo Long', 'Barrick Gold Turbo Long',
                     'SG Gold ETF Turbo Long', 'Gold Mini Turbo',
                     'Gold Knock-Out Long Short', 'Silver Turbo Long'):
            with self.subTest(name=name):
                self.assertIsNone(research.classify(name))
        self.assertEqual(research.classify('BNP Gold Turbo Short'),'SHORT')
        self.assertEqual(research.classify('BNP XAU/USD Open End Long'),'LONG')

    def test_existing_filtered_trade_summaries_add_candidates_without_broker_calls(self):
        row=trade(isin=A,name='BNP Gold Turbo Long')
        hints={'items':[{'isin':B,'direction':'SHORT','name':'SG Gold Mini Short',
                         'historicRecords':3,'lastTradeDate':'2026-10-23',
                         'tradeApproved':False}],
               'scope':'historical-filtered-buy-sell-not-full-account'}
        acc=account([row])
        acc['journal']['tradeCoverage']={'code':'READ_OK','goldHistoryHints':hints}
        merged=research.discover([acc])
        self.assertEqual(merged['candidateCount'],2)
        self.assertEqual(merged['filteredHistorySources'],1)
        self.assertFalse(merged['historyComplete'])
        self.assertTrue(all(x['currentlyDegiroListed'] is None and
                            x['tradeApproved'] is False and x['eligibleForTop3'] is False
                            for x in merged['items']))
        self.assertEqual(next(x for x in merged['items'] if x['isin']==B)['historicRecords'],3)

    def test_filtered_overlap_does_not_double_count_and_conflicts_are_suppressed(self):
        acc=account([trade(), trade()])
        acc['journal']['tradeCoverage']={'code':'READ_OK','goldHistoryHints':{
            'items':[{'isin':A,'direction':'LONG','name':'BNP Gold Turbo Long',
                      'historicRecords':3,'lastTradeDate':'2026-10-23'}]}}
        observed=research.discover([acc])
        self.assertEqual(observed['candidateCount'],1)
        self.assertEqual(observed['items'][0]['historicRecords'],3)
        acc['journal']['tradeCoverage']['goldHistoryHints']['items'][0]['direction']='SHORT'
        acc['journal']['tradeCoverage']['goldHistoryHints']['items'][0]['name']='BNP Gold Turbo Short'
        conflicted=research.discover([acc])
        self.assertEqual(conflicted['candidateCount'],0)
        self.assertEqual(conflicted['suppressedConflicts'],1)

    def test_filtered_summary_ignores_untrusted_or_factor_labels(self):
        acc=account([])
        acc['journal']['tradeCoverage']={'code':'READ_OK','goldHistoryHints':{
            'items':[{'isin':B,'direction':'LONG','name':'SG Gold Faktor Long'},
                     {'isin':A,'direction':'LONG','name':'BNP Gold Turbo Short'},
                     {'isin':C,'direction':'SHORT','name':'SG Gold Future Turbo Short'}]}}
        out=research.discover([acc])
        self.assertEqual(out['candidateCount'],0)
        acc['journal']['tradeCoverage']['code']='UNAVAILABLE'
        out=research.discover([acc])
        self.assertEqual(out['filteredHistorySources'],0)

    def test_conflicting_sides_are_not_guessed(self):
        result=research.discover([account([
            trade(),trade(name='BNP Gold Turbo Short',action='SELL')])])
        self.assertEqual(result['candidateCount'],0)
        self.assertEqual(result['suppressedConflicts'],1)

    def test_all_forty_valid_candidates_eventually_receive_bounded_issuer_checks(self):
        from snaptrade_portfolio import isin as is_valid
        identifiers=[]
        for index in range(40):
            stem='DE'+str(index).zfill(9)
            identifiers.append(next(stem+str(n) for n in range(10)
                                    if is_valid(stem+str(n))))
        rows=[trade(isin=i,name='BNP Gold Turbo Long') for i in identifiers]
        history=research.discover([account(rows)])
        self.assertEqual(history['candidateCount'],40)
        self.assertEqual(len(history['items']),40)
        observed=[]
        def lookup(isin):
            observed.append(isin)
            return {'isin':isin, 'productVerified':False}
        for offset in range(0,40,2):
            batch=degiro_catalog.study_history(history,lookup,offset=offset)
            self.assertLessEqual(batch['sampled'],2)
            self.assertFalse(batch['tradeApproved'])
        self.assertEqual(set(observed),set(identifiers))
        self.assertEqual(len(observed),40)

    def test_no_history_has_no_candidates(self):
        result=research.discover([{}])
        self.assertEqual(result['code'],'NO_HISTORY')
        self.assertEqual(result['items'],[])
        self.assertFalse(result['historyComplete'])

    def test_issuer_checks_never_promote_historical_deals(self):
        history=research.discover([account([trade()])])
        def issuer(isin):
            return dict(isin=isin, productVerified=True, found=True, fresh=True,
                        eligible=True, metadata=dict(status=1,type='TURBO',
                            underlyingType='SPOT',underlying='Gold',
                            currency='EUR',direction='LONG'))
        with patch('degiro_catalog.valid_isin',side_effect=lambda isin: research.valid_isin(isin)):
            result=degiro_catalog.study_history(history,issuer)
        self.assertEqual(result['available'],1)
        self.assertEqual(result['sampled'],1)
        self.assertTrue(result['items'][0]['issuerIdentityMatched'])
        self.assertFalse(result['items'][0]['eligibleForTop3'])
        self.assertFalse(result['items'][0]['tradeApproved'])
        self.assertIsNone(result['items'][0]['currentlyDegiroListed'])

    def test_future_issuer_is_rejected_even_when_history_looks_valid(self):
        history=research.discover([account([trade()])])
        def issuer(isin):
            return dict(isin=isin,productVerified=True,
                metadata=dict(status=1,type='TURBO',
                              underlyingType='FUTURE',underlying='Gold',
                              currency='EUR',direction='LONG'))
        result=degiro_catalog.study_history(history,issuer)
        self.assertFalse(result['items'][0]['issuerIdentityMatched'])

    def test_current_session_cadence_observations_need_two_real_scans(self):
        now=datetime(2026,10,26,9,10,tzinfo=Z)
        report=dict(lastScanAt=(now-timedelta(seconds=50)).isoformat(),
                    scanHistory=[
                        dict(at=(now-timedelta(seconds=350)).isoformat(),
                             elapsedSeconds=None),
                        dict(at=(now-timedelta(seconds=50)).isoformat(),
                             elapsedSeconds=300)],status='ok',errors=0,
                    historyResearch={'available':2,'sampled':1})
        with patch.object(degiro_catalog,'snapshot',return_value=report):
            status=degiro_catalog.diagnostics(now)
        self.assertEqual(status['targetSeconds'],300)
        self.assertTrue(status['healthyCadenceProven'])
        self.assertEqual(status['recentIntervalsSeconds'],[300])
        with patch.object(degiro_catalog,'snapshot',return_value=report):
            weekend=degiro_catalog.diagnostics(datetime(2026,10,25,16,tzinfo=Z))
        self.assertFalse(weekend['healthyCadenceProven'])


if __name__=='__main__':
    unittest.main()
