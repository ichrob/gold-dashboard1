"""KO guard regression: real source clocks, no synthetic liquidation or broker actions."""
import unittest
import json
from unittest.mock import Mock
from datetime import datetime
from zoneinfo import ZoneInfo

import paper_ko_guard as guard
import paper_simulation as sim

NOW = int(datetime(2026, 10, 12, 9, tzinfo=ZoneInfo('Europe/Zurich')).timestamp()*1000)
ISIN = 'DE000PJ9NCK0'


def market(price=4000., at=NOW, direction='LONG'):
    return dict(plan=dict(kind='candidate', direction=direction, entry=4000.,
                          stop=3800. if direction=='LONG' else 4200.,
                          target=4300. if direction=='LONG' else 3700., unit='USD/oz'),
                price=price, priceFresh=True, ready=True, dataAt=at, analysisBarAt=at,
                atr=20., direction=direction, score=80 if direction=='LONG' else 20,
                session={'entryAllowed': True}, ruleVersion='ko-regression-v1')


def choice(direction='LONG', scope='XAU/USD'):
    return dict(isin=ISIN, direction=direction, scope=scope,
                koGuardRequired=True, approval='Bob-Pflichtprüfung bestanden')


def quote(at=NOW, ko=3900., side='LONG', bid=10., status=1):
    return dict(isin=ISIN, productVerified=True, found=True, marketOpen=status==1,
                source='BNP Paribas · Test', currency='EUR',
                bid=bid, ask=bid+.1, bidAt=at, askAt=at,
                direction=side, ko=ko,
                metadata=dict(status=status, underlyingType='SPOT',
                              underlying='XAU/USD', direction=side),
                conditions=dict(ko=dict(value=ko, source='https://issuer.test/'+ISIN,
                    conditionVerified=True, dateText='12.10.2026')))


class KoGuardTests(unittest.TestCase):
    def test_healthy_entry_and_spot_short_direction(self):
        result, reason = guard.assess(choice(), quote(), market(), NOW)
        self.assertIsNone(reason)
        self.assertAlmostEqual(result['distancePct'], 2.5)
        self.assertFalse(result['danger'])
        self.assertIsNone(guard.entry_reason(choice(), quote(), market(), NOW)[0])
        q = quote(ko=4100., side='SHORT')
        m = market(direction='SHORT')
        self.assertIsNone(guard.entry_reason(choice('SHORT'), q, m, NOW)[0])
        self.assertAlmostEqual(guard.assess(choice('SHORT'), q, m, NOW)[0]['distancePct'], 2.5)

    def test_unsafe_at_entry_and_missing_or_wrong_evidence_block(self):
        self.assertIn('KO-Abstand', guard.entry_reason(
            choice(), quote(ko=3950.), market(), NOW)[0])
        missing = quote()
        missing['conditions']['ko'].pop('dateText')
        self.assertIn('heutigen', guard.entry_reason(choice(), missing, market(), NOW)[0])
        wrong = quote()
        wrong['isin'] = 'DE0000000000'
        self.assertIn('identität', guard.entry_reason(choice(), wrong, market(), NOW)[0])
        unverified = quote()
        unverified['conditions']['ko']['conditionVerified'] = False
        self.assertIsNotNone(guard.entry_reason(choice(), unverified, market(), NOW)[0])
        future = choice(scope='FUTURE')
        self.assertIn('Basiswert', guard.entry_reason(future, quote(), market(), NOW)[0])
        self.assertIsNotNone(guard.entry_reason(
            choice(), quote(), market(price=4000.,at=NOW,direction='SHORT'), NOW)[0])
        yesterday=quote()
        yesterday['conditions']['ko']['dateText']='11.10.2026'
        self.assertIsNotNone(guard.entry_reason(choice(), yesterday, market(), NOW)[0])

    def test_near_ko_produces_observed_bid_sale_not_guaranteed_fill(self):
        c=sim.new_case(market(),choice(),quote(),NOW,cash=100.)
        q=quote(NOW+30000, bid=8.)
        out=sim.advance_case(c, market(price=3940.,at=NOW+30000), q, NOW+30000)
        self.assertEqual(out['exitReason'],'ko-safety-exit')
        self.assertEqual(out['status'],'closed')
        self.assertEqual(out['remainingUnits'],0)
        self.assertAlmostEqual(out['cashReleased'],out['quantity']*8.)
        self.assertEqual(out['koWatchStatus'],'proximity-exit')
        self.assertTrue(out['productReturnKnown'])
        self.assertFalse(c['status']=='closed')

    def test_crossed_barrier_is_not_reported_as_a_successful_exit(self):
        opened=sim.new_case(market(),choice(),quote(),NOW,cash=100.)
        # Even when a nominal EUR bid is observed, the model cannot know
        # whether that price was executable before a possible knock-out.
        out=sim.advance_case(opened,market(price=3890.,at=NOW+30000),
                             quote(NOW+30000,bid=7.5),NOW+30000)
        self.assertEqual(out['status'],'inconclusive')
        self.assertEqual(out['koWatchStatus'],'crossed-observed')
        self.assertEqual(out['cashReleased'],0)
        self.assertEqual(out['pendingUnits'],opened['quantity'])
        self.assertIsNone(out['productGrossPct'])
        self.assertTrue(any(e['kind']=='ko-barrier-crossed-observed'
                            for e in out['events']))

    def test_no_trusted_terms_never_fake_ko_sale(self):
        c=sim.new_case(market(),choice(),quote(),NOW,cash=100.)
        stale=quote(NOW+30000)
        stale['conditions']['ko']['dateText']=None
        out=sim.advance_case(c,market(price=3940.,at=NOW+30000),
                             stale,NOW+30000)
        self.assertEqual(out['status'],'open')
        self.assertEqual(out['koWatchStatus'],'unverified')
        self.assertFalse(any(e['kind']=='ko-safety-exit' for e in out['events']))

    def test_unsynchronized_bid_never_claims_protective_sale(self):
        opened=sim.new_case(market(),choice(),quote(),NOW,cash=100.)
        # EUR bid is still within the general 90-second freshness window,
        # but arrived eight seconds before the triggering Gold observation.
        bid=quote(NOW+22000,bid=8.)
        out=sim.advance_case(opened,market(price=3940.,at=NOW+30000),
                             bid,NOW+30000)
        self.assertEqual(out['status'],'open')
        self.assertEqual(out['koWatchStatus'],'unverified')
        self.assertIn('zeitlich nicht abgestimmt',out['koWatchReason'])
        self.assertEqual(out['cashReleased'],0)
        self.assertNotIn('exitReason',out)

    def test_terminal_waits_for_real_settlement_not_zero_or_new_cash(self):
        c=sim.new_case(market(),choice(),quote(),NOW,cash=100.)
        terminal=quote(NOW+30000,status=2)
        terminal['found']=False
        terminal['terminalEvidence']=dict(status='knocked_out')
        result=sim.advance_case(c,market(price=3800.,at=NOW+30000),
                                terminal,NOW+30000)
        self.assertEqual(result['status'],'inconclusive')
        self.assertEqual(result['koWatchStatus'],'knockout-confirmed')
        self.assertEqual(result['cashReleased'],0)
        self.assertEqual(result['pendingUnits'],c['quantity'])
        self.assertIsNone(result['productGrossPct'])
        self.assertFalse(result['productReturnKnown'])
        self.assertNotIn('exitReason',result)
        self.assertEqual(guard.terminal(quote(status=2),ISIN),'product-terminated')
        self.assertIsNone(guard.terminal(quote(),ISIN))

    def test_next_cycle_selects_different_isin_after_ko_exit(self):
        replacement='DE000PJ9NCK1'
        other=choice()
        other['isin']=replacement
        other_quote=quote()
        other_quote['isin']=replacement
        chosen=[]
        current=dict(startAt=NOW-1, enabled=True, initialCapital=100., cash=100.,
                     equity=100., realizedProfit=0.,
                     koExcluded={'day':'2026-10-12','isins':[ISIN]})
        conn=Mock()

        def sql(query, args=()):
            result=Mock()
            result.fetchone.return_value=None
            if query.startswith('SELECT payload FROM bob_paper_control'):
                result.fetchone.return_value=(current.copy(),)
            if query.startswith('INSERT INTO bob_paper_cases'):
                chosen.append(json.loads(args[3])['product']['isin'])
                result.fetchone.return_value=(args[0],)
            return result

        conn.execute.side_effect=sql
        sim.run_once(conn, {}, market(),
                     {'choices':[choice(),other]},
                     {ISIN:quote(),replacement:other_quote},NOW)
        self.assertEqual(chosen,[replacement])
        self.assertEqual(guard.entry_reason(other,other_quote,market(),NOW)[0],None)
        # Even with no explicit block, an unsafe top candidate must not hide
        # the next ranked, verified and sufficiently distant product.
        chosen.clear()
        current['koExcluded']={'day':'2026-10-12','isins':[]}
        sim.run_once(conn, {}, market(),
                     {'choices':[choice(),other]},
                     {ISIN:quote(ko=3970.),replacement:other_quote},NOW)
        self.assertEqual(chosen,[replacement])



if __name__ == '__main__':
    unittest.main()
