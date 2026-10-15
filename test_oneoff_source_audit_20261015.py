"""One-off read-only SG / comdirect diagnosis for two publicly identified Gold ISINs.

Diagnostic branch only: no changes to application code, no account sessions,
no orders, no persistent market-data claims. Output omits all quoted prices.
"""
import datetime
import json
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
import product_quotes
import comdirect_quotes

ISINS = ("DE000FC1CHB7", "DE000FG4JXV7")

def age(value):
    if not isinstance(value, str):
        return None
    try:
        at=datetime.datetime.fromisoformat(value.replace('Z','+00:00'))
        if at.tzinfo is None:return None
        return round((datetime.datetime.now(datetime.timezone.utc)-at).total_seconds())
    except ValueError:return None

def classify(isin, r, co):
    primary=r.get('issuerResearch') or r
    chart=primary.get('chartEvidence') or r.get('chartEvidence') or {}
    analysis=r.get('analysisQuote') or {}
    sc=(r.get('secondaryQuote') or {})
    metadata=r.get('metadata') or {}
    sg_ref=primary.get('issuerLeverageReference') or {}
    backup=r.get('comdirectQuoteBackup') or {}
    return dict(
        isin=isin,
        identified=r.get('productVerified') is True,
        direction=metadata.get('direction'),
        status=metadata.get('status'),
        currency=metadata.get('currency') or r.get('currency'),
        issuer_source_failure=bool(primary.get('sourceFailure')),
        issuer_quote_failure=primary.get('quoteFailureCode') or r.get('quoteFailureCode'),
        issuer_stage=primary.get('lastSourceFailureStage'),
        issuer_chart_present=bool(chart.get('pointAt')),
        issuer_chart_age_seconds=age(chart.get('pointAt')),
        issuer_shared_clock=bool(primary.get('sharedTimeContext')),
        issuer_leverage_present=sg_ref.get('value') is not None,
        issuer_leverage_source_time=sg_ref.get('sourceAt'),
        ko_dates_confirmed=metadata.get('termsDated') is True or metadata.get('termsFixed') is True,
        executable_issuer_pair=bool(r.get('found') and r.get('eligible')),
        comdirect_state=co.get('state'),
        comdirect_reason=co.get('reasonCode'),
        comdirect_pair_present=bool(co.get('quote')),
        comdirect_age_seconds=age((co.get('quote') or {}).get('bidAt')),
        comdirect_applied=bool(sc.get('source','').startswith('comdirect')),
        comdirect_status=backup.get('state'),
        analysis_type=analysis.get('priceKind'),
        chosen_type=r.get('priceKind'),
        swissquote_eligible=False,
        onvista_auto_enabled=False,
    )

class OneShotPublicSourceAudit(unittest.TestCase):
    def test_two_explicit_isins_readonly(self):
        # Only two permitted user-supplied ISINs; per-provider caches and rate
        # limits remain active. Never substitute request time for source time.
        for isin in ISINS:
            self.assertTrue(product_quotes.valid_isin(isin))
        def probe(isin):
            try:return product_quotes.get_quote(isin)
            except Exception as exc:return {'isin':isin,'sourceFailure':True,'quoteFailureCode':'PROBE_'+type(exc).__name__}
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs={isin:pool.submit(probe,isin) for isin in ISINS}
            results={isin:jobs[isin].result(timeout=65) for isin in ISINS}
        # The secondary cache refresh is deliberately asynchronous.
        time.sleep(4)
        for isin in ISINS:
            co=comdirect_quotes.get_observation(isin)
            record=classify(isin,results[isin],co)
            print("BOB_READONLY_SOURCE_AUDIT "+json.dumps(record,sort_keys=True),flush=True)
            self.assertEqual(record['isin'],isin)

if __name__=="__main__":
    unittest.main()
