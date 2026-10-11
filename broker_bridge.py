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


def status():
    return {
        "mode": "CONNECTION_SCAFFOLD_ONLY",
        "executionEnabled": False,
        "liveOrders": False,
        "paperOrders": False,
        "credentialsConfigured": False,
        "brokers": [{
            "id": identifier, **spec,
            "connection": "not-connected",
            "swissAccount": "not-verified",
            "degiroIsinTradability": "not-verified",
            "apiOrderSupport": "not-verified",
        } for identifier, spec in BROKERS.items()],
        "notice": "Offizielle APIs dokumentiert, aber kein Konto verbunden. "
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
