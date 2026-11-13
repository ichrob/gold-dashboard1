"""Non-executing broker interface contracts for Bob Zukunft.

Official broker APIs can be implemented only after obtaining the account's
permissions and confirming actual ISIN/contract lookup with the broker.
No credentials, external requests, orders or automatic live activation here.
"""
import re

BROKERS = {
    "ibkr": {
        "name": "Interactive Brokers",
        "api": "IBKR Web API",
        "identifier": "conid",
        "docs": "https://www.interactivebrokers.com/docs/web-api/introduction",
        "paperRequirement": "Existing eligible IBKR account and enabled paper environment; verify entitlements.",
    },
    "ig": {
        "name": "IG Bank Schweiz",
        "api": "IG Labs REST / Streaming",
        "identifier": "epic",
        "docs": "https://www.ig.com/en-ch/trading-platforms/trading-apis/how-to-use-ig-api",
        "paperRequirement": "IG demo account and valid API credentials; confirm instrument and Swiss access.",
    },
}


class LiveTradingDisabled(RuntimeError):
    pass


class BrokerAdapter:
    """Future adapter contract. Fail closed until official paper API configured."""
    def __init__(self, provider):
        if provider not in BROKERS:
            raise ValueError("Unbekannter offizieller Broker")
        self.provider = provider

    def find_contract(self, isin):
        validate_isin(isin)
        raise LiveTradingDisabled("Brokervertrag noch nicht per offizieller API geprüft")

    def get_positions(self):
        raise LiveTradingDisabled("Kein API-Konto verbunden")

    def submit_order(self, *args, **kwargs):
        raise LiveTradingDisabled("Orderausführung dauerhaft gesperrt; kein Live-/Paper-Orderadapter aktiv")

    def cancel_order(self, *args, **kwargs):
        raise LiveTradingDisabled("Kein Orderadapter aktiv")


def validate_isin(isin):
    if not isinstance(isin, str) or not re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}[0-9]", isin):
        raise ValueError("ISIN-Format ungültig")
    # ISO 6166 / Luhn: convert letters to decimal 10..35 and verify check digit.
    digits = "".join(str(ord(c)-55) if c.isalpha() else c for c in isin)
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2:
            value *= 2
        total += value // 10 + value % 10
    if total % 10:
        raise ValueError("ISIN-Prüfziffer ungültig")
    return isin


def route_signal(broker, direction, isin=None):
    """Build a non-executing handoff, independent of market-signal generation.

    DEGIRO is permanently manual. A future API broker requires its own
    supported instrument, authenticated session and separately authorized
    paper/live risk gate; the same DEGIRO ISIN is never assumed tradable.
    This function performs no IO and never calls submit_order.
    """
    if broker != "degiro" and broker not in BROKERS:
        raise ValueError("Unbekannter Broker")
    if direction not in ("LONG", "SHORT", "ABWARTEN", "NEUTRAL"):
        raise ValueError("Ungültige Marktrichtung")
    if isin is not None:
        validate_isin(isin)
    idle = direction in ("ABWARTEN", "NEUTRAL")
    manual = broker == "degiro"
    return {
        "broker": broker,
        "direction": direction,
        "isin": isin,
        "route": "NO_ACTION" if idle else (
            "DEGIRO_MANUAL_SIGNAL" if manual else "API_ADAPTER_NOT_CONNECTED"
        ),
        "analysisCanContinue": True,
        "manualDecisionRequired": bool(manual and not idle),
        "brokerExecutionQuoteVerified": False,
        "instrumentMappingVerified": False,
        "paperOrderEnabled": False,
        "liveOrderEnabled": False,
        "orderSubmitted": False,
        "orderId": None,
        "reason": ("Kein Handelssignal; kein Auftrag." if idle else
                   "DEGIRO: Markt-/Produktsignal zur manuellen Prüfung. "
                   "Ausführbaren Preis im DEGIRO-Orderfenster selbst prüfen."
                   if manual else
                   "Broker-API als Zukunftsadapter vorbereitet: zuerst "
                   "separates Instrument, Broker-Berechtigung, Preise und "
                   "kontrollierten Demo-/Papierhandel nachweisen."),
    }


def prepare_order_review(signal, product, risk, broker="degiro", now=None):
    """Connect existing signal/ranking data to a strict non-executing worksheet.

    Never treat the result as a brokerage order or a source of live quotes.
    Real user/account execution permissions are not known here.
    """
    from trade_execution_readiness import build_review
    return build_review(signal, product, risk, broker=broker, now=now)


def manual_degiro_buy_handoff(review, now=None):
    """Read-only counterpart to the manual order worksheet."""
    from degiro_manual_trade_handoff import buy_handoff
    return buy_handoff(review, now=now)


def manual_degiro_stop_handoff(snapshot, **kwargs):
    """Prepare a stricter stop suggestion; never update a broker order."""
    from degiro_manual_trade_handoff import stop_update_handoff
    return stop_update_handoff(snapshot, **kwargs)


def manual_degiro_sell_handoff(snapshot, quote, **kwargs):
    """Prepare manual sale only for a confirmed active position."""
    from degiro_manual_trade_handoff import sell_handoff
    return sell_handoff(snapshot, quote, **kwargs)


def __readiness_status():
    from trade_execution_readiness import pipeline_status
    return pipeline_status()


def status():
    return {
        "mode": "CONNECTION_SCAFFOLD_ONLY",
        "analysisIndependentOfExecution": True,
        "defaultManualBroker": "degiro",
        "manualBroker": {"id": "degiro", "name": "DEGIRO",
                         "mode": "MANUAL_ONLY", "apiConnected": False,
                         "orderExecutionEnabled": False,
                         "signalDelivery": "ANALYSIS_AND_MANUAL_REVIEW"},
        "manualTradeHandoff": {
            "buy": "LOCAL_MANUAL_REVIEW_ONLY",
            "stopUpdate": "LOCAL_MANUAL_REVIEW_ONLY",
            "sell": "LOCAL_MANUAL_REVIEW_ONLY",
            "manualAppOpen": "OWNER_CLICK_ONLY",
            "confirmedFillMonitor": "EXISTING_REAL_TRADE_JOURNAL",
            "brokerOrdersPlaced": False,
            "brokerStopsChanged": False,
        },
        "futureBrokerMode": "PAPER_API_CONNECTION_REQUIRED",
        "executionEnabled": False,
        "liveOrders": False,
        "paperOrders": False,
        "fourStageReadiness": __readiness_status(),
        "credentialsConfigured": False,
        "brokers": [{
            "id": identifier, **spec,
            "connection": "not-connected",
            "route": "PAPER_FIRST_API_FUTURE",
            "liveOrdersRequireSeparateApproval": True,
            "swissAccount": "not-verified",
            "degiroIsinTradability": "not-verified",
            "apiOrderSupport": "not-verified",
        } for identifier, spec in BROKERS.items()],
        "notice": "DEGIRO-Handel bleibt manuell; Bob kann Analysesignale unabhängig davon liefern. "
                  "IBKR/IG sind nur vorbereitete Zukunftsadapter: kein API-Konto, keine Paper- oder Live-Orders. "
                  "DEGIRO-ISIN-Verfügbarkeit, Kosten, API-Orders und CH-Handelsberechtigung müssen "
                  "pro Broker und pro ISIN unabhängig nachgewiesen werden."
    }


def instrument_check(provider, isin):
    if provider not in BROKERS:
        raise ValueError("Unbekannter Broker")
    validate_isin(isin)
    return {
        "broker": provider,
        "isin": isin,
        "allowed": False,
        "reason": "Kein offizieller Kontrakt-/EPIC-Abruf und keine CH-/API-Handelsberechtigung bestätigt",
        "mappingKey": BROKERS[provider]["identifier"],
        "contractId": None,
        "paperOrderEnabled": False,
        "liveOrderEnabled": False,
    }
