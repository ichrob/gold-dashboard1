import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import future_estimate as f
import product_quotes as q
import sg_quotes as sg
from test_sg_futures import future_fixture, ISIN

NOW = datetime(2026, 10, 1, 7, 40, 30, tzinfo=timezone.utc)


def tick(seconds, price):
    return dict(at=(NOW-timedelta(seconds=seconds)).isoformat(), price=price, contract='GCZ26')


def history():
    return [tick(s, 4100+(790-s)*.01) for s in range(800, -1, -20)]


def reference():
    return dict(contract='GCZ26', underlyingAt=(NOW-timedelta(seconds=790)).isoformat(), underlyingPriceUsd=4191.4)


def page():
    state = dict(instrumentId=8830, instrument=dict(
        base=dict(id='8830', path='/commodities/gold', isCfd=True, isOpen=True, isActive=True),
        price=dict(last=4205.47, currency='USD', isDelayed=False,
                   lastUpdateTime=str(int(NOW.timestamp()*1000))),
        commodityData=dict(unit='_instr_unit_troy_ounce')),
        keyMetrics=dict(month='Dec 26', settlement_day='2026-12-29T00:00:00Z',
                        last_rollover_day='2026-08-27T00:00:00Z'))
    return state


def html(state):
    return '<script id="__NEXT_DATA__" type="application/json">'+json.dumps(
        dict(props=dict(pageProps=dict(state=dict(commodityStore=state)))))+'</script>'


class EstimateTests(unittest.TestCase):
    def test_aligned_additive_formula_and_provenance(self):
        out = f.calculate(reference(), history(), NOW)
        self.assertTrue(out['available'])
        self.assertAlmostEqual(out['proxyReferencePriceUsd'], 4100)
        self.assertAlmostEqual(out['priceUsd'], 4199.30)
        self.assertEqual(out['proxyReferenceKind'], 'linear-interpolation')
        self.assertEqual(out['alignmentSeconds'], 10)
        self.assertEqual(out['priceAt'], NOW.isoformat())
        self.assertFalse(out['eligible']); self.assertFalse(out['isExchangeRealtime'])

    def test_reanchor_replaces_old_basis_and_no_change_equals_real_reference(self):
        r = reference(); r.update(underlyingAt=NOW.isoformat(), underlyingPriceUsd=4200.1)
        self.assertEqual(f.calculate(r, history(), NOW)['priceUsd'], 4200.1)
        flat = [dict(t, price=4100) for t in history()]
        self.assertEqual(f.calculate(reference(), flat, NOW)['priceUsd'], 4191.4)

    def test_rejects_stale_future_proxy_gaps_contract_and_missing_times(self):
        cases = [(reference(), []), (dict(reference(), contract='GCG27'), history()),
                 (dict(reference(), underlyingAt=(NOW-timedelta(seconds=1801)).isoformat()), history()),
                 (dict(reference(), underlyingAt=(NOW+timedelta(seconds=1)).isoformat()), history()),
                 (reference(), history()[:-4]),
                 (reference(), [history()[0], history()[1], history()[-1]]),
                 (reference(), history()[3:]),
                 (dict(reference(), underlyingPriceUsd=float('nan')), history()),
                 (dict(reference(), underlyingAt='2026-10-01T07:27:20'), history()),
                 (reference(), [dict(t, contract='GCG27') for t in history()]),
                 (reference(), history()+[tick(-1, 4100)])]
        for r, ticks in cases:
            out = f.calculate(r, ticks, NOW)
            self.assertFalse(out['available'], str(out)); self.assertNotIn('priceUsd', out)

    def test_page_schema_time_market_and_rollover(self):
        self.assertEqual(f.parse_page(html(page()), NOW)['price'], 4205.47)
        for area, key, value in [('base','id','other'),('base','isCfd',False),('base','isOpen',False),
                                 ('price','currency','EUR'),('price','last',float('nan')),
                                 ('price','lastUpdateTime','000'),('price','isDelayed',True),
                                 ('price','lastUpdateTime',str(int((NOW.timestamp()-61)*1000))),
                                 ('price','lastUpdateTime',str(int((NOW.timestamp()+1)*1000)))]:
            state=page(); state['instrument'][area][key]=value
            with self.assertRaises(ValueError): f.parse_page(html(state), NOW)
        for key,value in [('month','Feb 27'),('settlement_day','2027-02-28T00:00:00Z'),
                          ('last_rollover_day','2026-10-01T00:00:00Z')]:
            state=page();state['keyMetrics'][key]=value
            with self.assertRaises(ValueError):f.parse_page(html(state),NOW)

    def test_collection_reports_actual_coverage_even_when_reference_is_missing(self):
        with patch.object(f,'_ticks',[tick(30,4100),tick(0,4101)]),patch.object(f,'_source_error',None):
            out=f.current_estimate(reference(),NOW)
            self.assertFalse(out['available']);self.assertNotIn('priceUsd',out)
            self.assertEqual(out['collection']['sampleCount'],2)
            self.assertEqual(out['collection']['coveredSeconds'],30)
            self.assertTrue(out['collection']['currentFresh'])
            stale=f.current_estimate(reference(),NOW+timedelta(seconds=61))
            self.assertFalse(stale['collection']['currentFresh'])
            self.assertEqual(stale['collection']['lastAt'],out['collection']['lastAt'])

    def test_collection_distinguishes_total_span_from_contiguous_segment(self):
        with patch.object(f,'_ticks',[tick(300,4100),tick(270,4101),tick(90,4102),tick(0,4103)]):
            out=f.current_estimate(reference(),NOW)
            self.assertEqual(out['collection']['coveredSeconds'],300)
            self.assertEqual(out['collection']['largestGapSeconds'],180)
            self.assertEqual(out['collection']['continuousSeconds'],90)
            self.assertFalse(out['available'])
        with patch.object(f,'_ticks',[]):
            empty=f.current_estimate(reference(),NOW)['alternatives'][0]['collection']
            self.assertEqual(empty['largestGapSeconds'],0)
            self.assertEqual(empty['continuousSeconds'],0)

    def test_recording_never_refreshes_cached_timestamp(self):
        with patch.object(f, '_ticks', []):
            f.record_tick(tick(10,4100),NOW)
            f.record_tick(tick(10,4100),NOW)
            f.record_tick(tick(20,4099),NOW)
            self.assertEqual(len(f._ticks),1)
            with self.assertRaises(ValueError):f.record_tick(tick(10,4101),NOW)
            with self.assertRaises(ValueError):f.record_tick(tick(61,4100),NOW)

    def test_enrichment_cache_recomputes_and_expiry_cannot_authorize_trade(self):
        with patch.object(f,'_ticks',history()),patch.object(f,'_source_error',None):
            result=sg.parse_future_research(*future_fixture(),ISIN,NOW)
            self.assertTrue(result['futureResearch']['calculatedFuture']['available'])
            self.assertFalse(result['found']);self.assertFalse(result['eligible'])
            for k in ('price','leverage','quoteAt'):self.assertNotIn(k,result)
            cached=q.freshness(result,NOW+timedelta(seconds=61))
            calc=cached['futureResearch']['calculatedFuture']
            self.assertFalse(calc['available']);self.assertNotIn('priceUsd',calc)
            self.assertFalse(cached['eligible'])


if __name__ == '__main__':unittest.main()
