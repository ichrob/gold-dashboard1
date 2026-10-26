"""Unattended issuer catalogue safety: never claim verified DEGIRO availability."""
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import degiro_catalog as catalog

Z = ZoneInfo("Europe/Zurich")


def issuer(isin, side="LONG", *, spot=True, status=1, verified=True):
    return dict(isin=isin, productVerified=verified, found=True,
        fresh=True, eligible=True, quoteAt="2026-10-12T08:00:00+02:00",
        sourceUrl="https://www.sg-zertifikate.de/product-details/"+isin.lower(),
        metadata=dict(underlying="XAU/USD", underlyingType="SPOT" if spot else "FUTURE",
                      direction=side, currency="EUR", status=status))


class IssuerCatalogueTests(unittest.TestCase):
    def test_confirmed_terminal_bnp_is_excluded_without_quote_failure(self):
        ended = {"DE000PJ9NCK0", "DE000PJ9NB98"}
        calls = {}
        def lookup(isin):
            calls[isin] = calls.get(isin, 0) + 1
            side = next(d for known, d in catalog.SEEDS if known == isin)
            row = issuer(isin, side)
            if isin in ended:
                row.update(found=False, fresh=False, eligible=False,
                           source="BNP Paribas · offizielle Produktdaten",
                           quoteFailureCode="MISSING_FIELD")
                row["metadata"].update(status=2, tradingHalted=True)
            return row

        result = catalog.build(lookup, datetime(2026, 10, 26, 13, tzinfo=Z),
                               retry_limit=3, sleeper=lambda _: self.fail("No KO quote retry"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["bnpConfirmedEnded"], 2)
        self.assertEqual(result["sourceChecks"]["historicalBNP"]["sourceErrors"], 0)
        self.assertTrue(ended.issubset({row["isin"] for row in result["excluded"]}))
        self.assertFalse(ended.intersection({row["isin"] for row in result["candidates"]}))
        self.assertTrue(all(calls[isin] == 1 for isin in ended))
        self.assertFalse(result["automaticOrders"])

    def test_terminal_bnp_requires_verified_identity_and_no_provider_failure(self):
        isin = "DE000PJ9NB98"
        row = issuer(isin)
        row.update(found=False, eligible=False,
                   source="BNP Paribas · offizielle Produktdaten",
                   quoteFailureCode="MISSING_FIELD")
        row["metadata"].update(status=2, tradingHalted=True)
        self.assertTrue(catalog._confirmed_terminal_bnp(isin, row))
        for changed in ({"isin": "DE000PJ9NCK0"}, {"productVerified": False},
                        {"sourceFailure": True}, {"sourceDisabled": True},
                        {"source": "comdirect · BNP LiveTrading"},
                        {"found": True}, {"eligible": True}):
            with self.subTest(changed=changed):
                self.assertFalse(catalog._confirmed_terminal_bnp(isin, dict(row, **changed)))
        self.assertFalse(catalog._confirmed_terminal_bnp(isin, dict(row, metadata={
            **row["metadata"], "status": 1})))
        self.assertFalse(catalog._confirmed_terminal_bnp(isin, dict(row, metadata={
            **row["metadata"], "tradingHalted": False})))

    def test_unconfirmed_knockout_does_not_hide_issuer_error(self):
        isin = "DE000PJ9NB98"
        def lookup(candidate):
            side = next(d for known, d in catalog.SEEDS if known == candidate)
            row = issuer(candidate, side)
            if candidate == isin:
                row.update(found=False, fresh=False, eligible=False,
                           source="BNP Paribas · offizielle Produktdaten",
                           productVerified=False, sourceFailure=True,
                           quoteFailureCode="CONNECTION")
                row["metadata"].update(status=2, tradingHalted=True)
            return row
        result = catalog.build(lookup, datetime(2026, 10, 26, 13, tzinfo=Z))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["errors"], 1)
        self.assertEqual(result["bnpConfirmedEnded"], 0)
        self.assertEqual(result["sourceChecks"]["historicalBNP"]["sourceErrors"], 1)

    def test_slow_scan_start_times_do_not_accumulate_duration(self):
        from unittest.mock import patch
        import copy
        class StopWorker(BaseException):
            pass
        clock = [0]
        starts, delays = [], []
        original = copy.deepcopy(catalog._CURRENT)
        def fake_scan(*args, **kwargs):
            starts.append(clock[0])
            clock[0] += 26
            return dict(status="partial", errors=1, attempted=10,
                sourceChecks={"historicalBNP": dict(attempted=3, verified=3,
                    datedFreshQuote=1, sourceErrors=1),
                    "otherHistorical": dict(sourceErrors=0)},
                retryAttempts=1, retryRecovered=0, bnpStaleSourceClocks=0,
                bnpConfirmedEnded=2)
        def fake_sleep(seconds):
            delays.append(seconds)
            clock[0] += seconds
            if len(delays) == 3:
                raise StopWorker
        try:
            with patch.object(catalog, "session", return_value=("2026-10-26", "morning")), \
                 patch.object(catalog, "build", side_effect=fake_scan), \
                 patch.object(catalog, "study_history", return_value={"sampled": 0}), \
                 patch("snaptrade_bridge.historical_gold_candidates", return_value={"items": []}), \
                 patch.object(catalog.time, "monotonic", side_effect=lambda: clock[0]), \
                 patch.object(catalog.time, "sleep", side_effect=fake_sleep):
                with self.assertRaises(StopWorker):
                    catalog._loop()
            self.assertEqual(starts, [0, 300, 600])
            self.assertEqual(delays, [274, 274, 274])
        finally:
            catalog._CURRENT.clear()
            catalog._CURRENT.update(original)


    def test_worker_detects_relapse_and_recovery_after_success_without_restart(self):
        from unittest.mock import patch
        import copy

        class StopWorker(BaseException):
            pass

        clock = [0]
        states = []
        scan_times = []
        original = copy.deepcopy(catalog._CURRENT)
        def scan(*args, **kwargs):
            scan_times.append(clock[0])
            status = ["ok", "partial", "ok"][len(scan_times)-1]
            return dict(status=status, errors=int(status == "partial"),
                        lastDay="2026-10-16", lastSession="evening",
                        sourceChecks={"historicalBNP": dict(attempted=3, verified=3,
                            datedFreshQuote=0 if status == "partial" else 3,
                            sourceErrors=3 if status == "partial" else 0),
                            "otherHistorical": dict(sourceErrors=0)},
                        attempted=10, retryAttempts=0, retryRecovered=0,
                        bnpStaleSourceClocks=3 if status == "partial" else 0)
        def wait(seconds):
            states.append(catalog._CURRENT["status"])
            clock[0] += seconds
            if clock[0] > 600:
                raise StopWorker
        try:
            with patch.object(catalog, "session", return_value=("2026-10-16", "evening")), \
                 patch.object(catalog, "build", side_effect=scan), \
                 patch.object(catalog.time, "monotonic", side_effect=lambda: clock[0]), \
                 patch.object(catalog.time, "sleep", side_effect=wait):
                with self.assertRaises(StopWorker):
                    catalog._loop()
            self.assertEqual(scan_times, [0, 300, 600])
            self.assertEqual(states, ["ok", "partial", "ok"])
        finally:
            catalog._CURRENT.clear()
            catalog._CURRENT.update(original)

    def test_no_deferred_degirosession_or_account_connection(self):
        self.assertGreaterEqual(len(catalog.SEEDS),5)
        self.assertLessEqual(len(catalog.SEEDS),catalog.LIMIT)
        self.assertNotIn("DE000FE4UF01",[a for a,_ in catalog.SEEDS])
        self.assertNotIn("DE000FG5NMF2",[a for a,_ in catalog.SEEDS])
        data=catalog.build(lambda isin:issuer(isin, next(d for i,d in catalog.SEEDS if i==isin)),
                           datetime(2026,10,12,9,tzinfo=Z))
        self.assertFalse(data["completeDegiroCatalog"])
        self.assertFalse(data["canAutoImportVerifiedDegiroList"])
        self.assertFalse(data["degiroAccountConnected"])
        self.assertFalse(data["automaticOrders"])
        self.assertTrue(data["attempted"]<=12)
        for x in data["candidates"]:
            self.assertIsNone(x["degiroListed"])
            self.assertIsNone(x["degiroTradingEnabled"])
            self.assertFalse(x["eligibleForTop3"])
            self.assertFalse(x["liveApproved"])
            self.assertFalse(x["screenshotToday"])

    def test_all_historically_confirmed_bnp_gold_isins_are_researched_safely(self):
        expected = ("DE000PJ9NCK0", "DE000PJ9NB98", "DE000PG0XK25")
        self.assertEqual([side for isin, side in catalog.SEEDS if isin in expected],
                         ["LONG", "LONG", "LONG"])
        self.assertEqual(len({isin for isin, _ in catalog.SEEDS}), len(catalog.SEEDS))
        scanned = []
        def fetch(isin):
            scanned.append(isin)
            return issuer(isin, next(side for candidate, side in catalog.SEEDS if candidate == isin))
        result = catalog.build(fetch, datetime(2026, 10, 15, 16, tzinfo=Z))
        for isin in expected:
            self.assertEqual(scanned.count(isin), 1)
            item = next(x for x in result["candidates"] if x["isin"] == isin)
            self.assertTrue(item["issuerVerified"])
            self.assertFalse(item["eligibleForTop3"])
            self.assertFalse(item["liveApproved"])
            self.assertIsNone(item["degiroListed"])
            self.assertFalse(item["screenshotToday"])

    def test_bnp_source_health_separated_from_sg_and_never_promotes_execution(self):
        from datetime import timezone
        listed = {"DE000PJ9NCK0", "DE000PJ9NB98", "DE000PG0XK25"}
        def healthy(isin):
            side = next(side for known, side in catalog.SEEDS if known == isin)
            row = issuer(isin, side)
            if isin == "DE000PJ9NCK0":
                for key in ("bidAt", "askAt", "leverageAt", "snapshotAt"):
                    row[key] = "2026-10-15T16:00:00+02:00"
            return row
        at = datetime(2026, 10, 15, 16, tzinfo=Z)
        healthy_result = catalog.build(healthy, at)
        bn = healthy_result["sourceChecks"]["historicalBNP"]
        others = healthy_result["sourceChecks"]["otherHistorical"]
        self.assertEqual(bn, dict(attempted=3, verified=3, datedFreshQuote=1, sourceErrors=0))
        self.assertEqual(others["attempted"], len(catalog.SEEDS) - 3)
        self.assertEqual(others["sourceErrors"], 0)
        self.assertFalse(healthy_result["automaticOrders"])
        self.assertTrue(all(not item["liveApproved"] and item["degiroListed"] is None
                            for item in healthy_result["candidates"]))

        # One provider failure must be attributed to the correct historical group,
        # without rewriting response quotes, source times, or approval gates.
        def bnp_failure(isin):
            row = healthy(isin)
            if isin == "DE000PJ9NB98":
                row["sourceFailure"] = True
                row["quoteFailureCode"] = "CONNECTION"
            return row
        failed = catalog.build(bnp_failure, at)
        self.assertEqual(failed["status"], "partial")
        self.assertEqual(failed["sourceChecks"]["historicalBNP"]["sourceErrors"], 1)
        self.assertEqual(failed["sourceChecks"]["otherHistorical"]["sourceErrors"], 0)
        self.assertEqual(failed["sourceChecks"]["historicalBNP"]["datedFreshQuote"], 1)

        def sg_failure(isin):
            row = healthy(isin)
            if isin not in listed and isin == "DE000FG4JXV7":
                row["sourceFailure"] = True
            return row
        failed_sg = catalog.build(sg_failure, at)
        self.assertEqual(failed_sg["sourceChecks"]["historicalBNP"]["sourceErrors"], 0)
        self.assertEqual(failed_sg["sourceChecks"]["otherHistorical"]["sourceErrors"], 1)

        # A model/chart pair, however recent, does not count as independently
        # dated issuer bid/ask/leverage/snapshot evidence.
        def model_only(isin):
            row = healthy(isin)
            if isin == "DE000PJ9NCK0":
                row["leverageAt"] = None
            return row
        self.assertEqual(catalog.build(model_only, at)["sourceChecks"]["historicalBNP"]["datedFreshQuote"], 0)

    def test_future_invalid_status_and_mismatch_excluded(self):
        isin="DE000FG309G0"
        item, bad=catalog.normalize(isin,"SHORT",issuer(isin,"SHORT",spot=False))
        self.assertIsNone(item);self.assertIn("Gold-Spot",bad["reason"])
        item, bad=catalog.normalize(isin,"SHORT",issuer(isin,"SHORT",status=2))
        self.assertIsNone(item);self.assertIn("beendet",bad["reason"])
        item, bad=catalog.normalize(isin,"SHORT",issuer(isin,"LONG"))
        self.assertIsNone(item);self.assertIn("weicht",bad["reason"])
        item, bad=catalog.normalize(isin,"SHORT",{**issuer(isin,"SHORT"),"isin":"DE000FG4JXV7"})
        self.assertIsNone(bad);self.assertFalse(item["issuerVerified"])
        self.assertFalse(item["issuerQuoteFresh"])

    def test_no_source_time_fabrication_on_missing_data(self):
        item, bad=catalog.normalize("DE000FC1CHB7","LONG",{})
        self.assertIsNone(bad)
        self.assertIsNone(item["quoteSourceAt"])
        self.assertFalse(item["issuerVerified"])
        self.assertFalse(item["issuerQuoteFresh"])

    def test_soft_provider_failures_trigger_retries(self):
        def lookup(isin):
            return dict(isin=isin,found=False,sourceFailure=True,
                        quoteFailureCode="CONNECTION",
                        reason="Provider offline")
        result=catalog.build(lookup,datetime(2026,10,12,9,tzinfo=Z))
        self.assertEqual(result["status"],"partial")
        self.assertEqual(result["errors"],len(catalog.SEEDS))
        self.assertFalse(any(x["issuerVerified"] for x in result["candidates"]))

    def test_transient_bnp_failures_retry_after_cache_window_and_recover(self):
        failing = {"DE000PJ9NCK0", "DE000PJ9NB98"}
        calls, waits = {}, []
        def flaky(isin):
            calls[isin] = calls.get(isin, 0) + 1
            side = next(side for known, side in catalog.SEEDS if known == isin)
            row = issuer(isin, side)
            if isin in failing and calls[isin] == 1:
                row.update(sourceFailure=True, quoteFailureCode="CONNECTION")
            return row
        result = catalog.build(flaky, datetime(2026, 10, 16, 10, tzinfo=Z),
                               retry_limit=2, retry_wait_seconds=16,
                               sleeper=waits.append)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["errors"], 0)
        self.assertEqual(result["retryAttempts"], 2)
        self.assertEqual(result["retryRecovered"], 2)
        self.assertEqual(waits, [16, 16])
        self.assertTrue(all(calls[isin] == (2 if isin in failing else 1)
                            for isin, _ in catalog.SEEDS))

    def test_retry_budget_is_global_and_fail_closed(self):
        calls, waits = [], []
        def unavailable(isin):
            calls.append(isin)
            return dict(isin=isin, found=False, sourceFailure=True,
                        quoteFailureCode="HTTP_503", reason="Provider unavailable")
        result = catalog.build(unavailable, datetime(2026, 10, 16, 10, tzinfo=Z),
                               retry_limit=2, retry_wait_seconds=16,
                               sleeper=waits.append)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["errors"], len(catalog.SEEDS))
        self.assertEqual(result["retryAttempts"], 2)
        self.assertEqual(result["retryRecovered"], 0)
        self.assertEqual(waits, [16, 16])
        self.assertEqual(len(calls), len(catalog.SEEDS) + 2)
        self.assertFalse(any(row["liveApproved"] for row in result["candidates"]))

    def test_no_network_credential_or_delayed_adapter_fallback(self):
        attempts=[]
        def lookup(isin):
            attempts.append(isin)
            raise OSError("upstream unavailable")
        result=catalog.build(lookup,datetime(2026,10,12,9,tzinfo=Z))
        self.assertEqual(result["errors"],len(catalog.SEEDS))
        self.assertEqual(result["status"],"partial")
        self.assertEqual(len(attempts),len(catalog.SEEDS))
        self.assertFalse(any(c["issuerVerified"] for c in result["candidates"]))
        self.assertFalse(any(c["issuerQuoteFresh"] for c in result["candidates"]))

    def test_session_gates_weekends_nights_and_reviewed_22h_close(self):
        self.assertIsNone(catalog.session(datetime(2026,10,11,10,tzinfo=Z)))
        self.assertIsNone(catalog.session(datetime(2026,10,12,7,tzinfo=Z)))
        self.assertEqual(catalog.session(datetime(2026,10,12,8,tzinfo=Z))[1],"morning")
        self.assertEqual(catalog.session(datetime(2026,10,12,18,tzinfo=Z))[1],"evening")
        self.assertEqual(catalog.session(datetime(2026,10,12,21,59,tzinfo=Z))[1],"evening")
        self.assertIsNone(catalog.session(datetime(2026,10,12,22,tzinfo=Z)))

    def test_server_endpoint_requires_auth_and_ui_keeps_separate_list(self):
        from pathlib import Path
        py=Path("server.py").read_text()
        js=Path("degiro_assistant.js").read_text()
        self.assertIn('or path == "/api/degiro/candidates"',py)
        self.assertIn('if path == "/api/degiro/candidates":',py)
        self.assertIn('degiro_catalog.start()',py)
        code=Path("degiro_catalog.py").read_text()
        self.assertIn("build(product_quotes.get_issuer_quote, retry_limit=3",code)
        self.assertIn("retry_wait_seconds=16",code)
        self.assertIn("Automatische Gold-Produktrecherche · externe Kandidaten",js)
        self.assertIn('completeDegiroCatalog!==false',js)
        self.assertIn('p.eligibleForTop3!==false',js)
        self.assertIn("Keine automatische Top-3-Freigabe",js)
        self.assertNotIn('document.querySelector("#dgListUpload").files',js)


    def test_stale_original_bnp_clocks_trigger_bounded_authorised_retry(self):
        """Three BNP issuer clocks may recover without new feeds or false ages."""
        isins = catalog.HISTORICAL_BNP
        calls, waits = {}, []
        original = "2026-10-16T08:01:00+02:00"
        current = "2026-10-16T13:00:00+02:00"
        def lookup(isin):
            calls[isin] = calls.get(isin, 0) + 1
            side = next(side for known, side in catalog.SEEDS if known == isin)
            row = issuer(isin, side)
            if isin in isins:
                row.update(source="BNP Paribas · Emittent OTC", marketOpen=True)
                if calls[isin] == 1:
                    row.update(found=True, eligible=False, fresh=False,
                               quoteFailureCode="STALE_OR_INVALID_SOURCE_TIME",
                               quoteAt=original,
                               bidAt=original, askAt=original,
                               leverageAt=original, snapshotAt=original)
                else:
                    row.update(found=True, eligible=True, fresh=True,
                               quoteAt=current,
                               bidAt=current, askAt=current,
                               leverageAt=current, snapshotAt=current)
            return row
        result = catalog.build(lookup, datetime(2026, 10, 16, 13, tzinfo=Z),
                               retry_limit=3, retry_wait_seconds=16,
                               sleeper=waits.append)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["retryAttempts"], 3)
        self.assertEqual(result["retryRecovered"], 3)
        self.assertEqual(result["bnpStaleSourceClocks"], 0)
        self.assertEqual(result["sourceChecks"]["historicalBNP"]["datedFreshQuote"], 3)
        self.assertEqual(waits, [16, 16, 16])
        for isin in isins:
            self.assertEqual(calls[isin], 2)
            item = next(x for x in result["candidates"] if x["isin"] == isin)
            self.assertEqual(item["quoteSourceAt"], current)
            self.assertTrue(item["issuerQuoteFresh"])
            self.assertFalse(item["liveApproved"])
            self.assertFalse(item["eligibleForTop3"])

    def test_persistently_old_bnp_clock_stays_old_and_unapproved(self):
        one = "DE000PJ9NCK0"
        old = "2026-10-16T08:01:00+02:00"
        calls = []
        def lookup(isin):
            calls.append(isin)
            side = next(side for known, side in catalog.SEEDS if known == isin)
            row = issuer(isin, side)
            if isin == one:
                row.update(source="BNP Paribas · Emittent OTC", marketOpen=True,
                           found=True, eligible=False, fresh=False,
                           quoteFailureCode="STALE_OR_INVALID_SOURCE_TIME",
                           quoteAt=old, bidAt=old, askAt=old,
                           leverageAt=old, snapshotAt=old)
            return row
        result = catalog.build(lookup, datetime(2026, 10, 16, 13, tzinfo=Z),
                               retry_limit=3, retry_wait_seconds=16,
                               sleeper=lambda _: None)
        self.assertEqual(calls.count(one), 2)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["bnpStaleSourceClocks"], 1)
        self.assertEqual(result["retryAttempts"], 1)
        self.assertEqual(result["retryRecovered"], 0)
        item = next(x for x in result["candidates"] if x["isin"] == one)
        self.assertEqual(item["quoteSourceAt"], old)
        self.assertFalse(item["issuerQuoteFresh"])
        self.assertFalse(item["liveApproved"])

    def test_stale_research_or_closed_bnp_does_not_trigger_network_retry(self):
        isin = "DE000PJ9NCK0"
        for changed in ({"marketOpen": False},
                        {"productVerified": False},
                        {"source": "comdirect · BNP LiveTrading"},
                        {"isin": "DE000PJ9NB98"},
                        {"found": False}):
            row = issuer(isin)
            row.update(source="BNP Paribas · Emittent OTC", marketOpen=True,
                       quoteFailureCode="STALE_OR_INVALID_SOURCE_TIME",
                       found=True, eligible=False, fresh=False)
            row.update(changed)
            self.assertFalse(catalog._retryable_bnp_failure(isin, row))
        row = issuer(isin)
        row.update(source="BNP Paribas · Emittent OTC", marketOpen=True,
                   found=True, eligible=False, fresh=False,
                   quoteFailureCode="STALE_OR_INVALID_SOURCE_TIME")
        self.assertTrue(catalog._retryable_bnp_failure(isin, row))


if __name__=="__main__":
    unittest.main()
