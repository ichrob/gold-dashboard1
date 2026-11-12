"""Read-only four-stage order-readiness review using original signal/product evidence.

This module never places or approves a broker order. A complete review is an
informational DEGIRO manual-order worksheet, NOT an executable broker quote.
Current trading/venue/identity evidence must come from trusted Bob producers,
not an external model, screenshot text or a client-side approval flag alone.
"""
from datetime import datetime, timezone
import hashlib
import json
import math

from broker_bridge import validate_isin

SIGNAL_MAX_AGE_SECONDS = 60
QUOTE_MAX_AGE_SECONDS = 90
MAX_RISK_EUR = 10_000
MAX_QUANTITY = 100_000


def clock(value):
    if not isinstance(value, str):
        raise ValueError("Quellenzeit mit Zeitzone fehlt")
    try:
        at = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Quellenzeit ungültig") from exc
    if at.tzinfo is None:
        raise ValueError("Quellenzeit ohne Zeitzone")
    return at.astimezone(timezone.utc)


def number(value, *, zero=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (value >= 0 if zero else value > 0))


def age_seconds(value, now):
    age = (now - clock(value)).total_seconds()
    return age if 0 <= age <= 365 * 86400 else None


def _reason(reasons, message):
    if message not in reasons:
        reasons.append(message)


def build_review(signal, product, risk, broker="degiro", now=None):
    """Return a blocked or manually reviewable worksheet, never an order.

    All amounts are *native EUR product prices*, not gold spot prices.
    Costs are displayed; the conservative KO worst-case cash exposure is the
    whole purchase notional plus documented fee estimate.
    """
    if broker not in ("degiro", "ibkr", "ig"):
        raise ValueError("Broker nicht unterstützt")
    if not all(isinstance(value, dict) for value in (signal, product, risk)):
        raise ValueError("Eingaben müssen strukturierte Prüfwerte sein")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Prüfzeit ohne Zeitzone")
    now = now.astimezone(timezone.utc)
    reasons = []
    # The DEGIRO turbo cannot be blindly mapped to an IG/IBKR contract.
    if broker != "degiro":
        _reason(reasons, "Brokerspezifische Vertrags-ID, Kurs und Konto-Handelsrecht fehlen")

    direction = signal.get("direction")
    if direction not in ("LONG", "SHORT"):
        _reason(reasons, "Kein LONG-/SHORT-Hauptsignal")
    if signal.get("ready") is not True or signal.get("priceFresh") is not True:
        _reason(reasons, "Markt-/Signalprüfung nicht bestätigt")
    try:
        if age_seconds(signal.get("at"), now) is None or age_seconds(signal["at"], now) > SIGNAL_MAX_AGE_SECONDS:
            _reason(reasons, "Signalzeit fehlt oder ist veraltet")
    except (ValueError, KeyError):
        _reason(reasons, "Signalzeit fehlt oder ist veraltet")
    if signal.get("marketOpen") is not True:
        _reason(reasons, "Handelszeit nicht bestätigt")

    isin = product.get("isin")
    try:
        validate_isin(isin)
    except ValueError:
        _reason(reasons, "ISIN nicht unabhängig gültig")
        isin = None
    if product.get("direction") != direction or direction not in ("LONG", "SHORT"):
        _reason(reasons, "Produktrichtung passt nicht zum Hauptsignal")
    if product.get("underlying") != "XAU/USD" or product.get("underlyingType") != "SPOT":
        _reason(reasons, "Gold-Spot-Basiswert nicht bestätigt")
    if product.get("productType") != "TURBO" or product.get("factorProduct") is not False:
        _reason(reasons, "Einfaches Turbo-/KO-Produkt nicht bestätigt")
    if product.get("currency") != "EUR":
        _reason(reasons, "Nur belegte EUR-Produktkurse; CHF benötigt eigenen FX-Nachweis")
    if any(product.get(key) is not True for key in
           ("identityVerified", "venueVerified", "koVerified", "termsVerified", "tradingOpen")):
        _reason(reasons, "Produktidentität, DEGIRO-Handelsplatz, KO, Bedingungen oder Handelbarkeit ungeprüft")
    if not all(number(product.get(key)) for key in ("ko", "strike", "ratio", "leverage")):
        _reason(reasons, "KO-Schwelle, Basispreis, Bezugsverhältnis oder Hebel unvollständig")
    if not number(product.get("koDistancePct")) or product["koDistancePct"] < 8:
        _reason(reasons, "KO-Abstand nicht ausreichend bestätigt")

    bid = product.get("bidEUR")
    ask = product.get("askEUR")
    if not number(bid) or not number(ask) or bid > ask:
        _reason(reasons, "Belegtes Geld-/Briefpaar fehlt oder ist widersprüchlich")
    try:
        quote_age = age_seconds(product.get("quoteAt"), now)
        if quote_age is None or quote_age > QUOTE_MAX_AGE_SECONDS:
            _reason(reasons, "Originalzeit des Produktkurses fehlt oder ist veraltet")
    except ValueError:
        _reason(reasons, "Originalzeit des Produktkurses fehlt oder ist veraltet")
    # Quotes and signals must describe the same short decision window.
    try:
        if abs((clock(product["quoteAt"]) - clock(signal["at"])).total_seconds()) > 30:
            _reason(reasons, "Produktkurs und Handelssignal liegen zeitlich auseinander")
    except (KeyError, ValueError, TypeError):
        _reason(reasons, "Zeitliche Zuordnung von Signal und Produktkurs fehlt")
    if not isinstance(product.get("quoteSource"), str) or not product["quoteSource"].strip():
        _reason(reasons, "Originalkursquelle nicht benannt")
    if product.get("quoteKind") != "ISSUER_BID_ASK":
        _reason(reasons, "Chart-, Modell- und Schätzkurse sind keine Orderpreise")

    cash = risk.get("cashEUR")
    budget = risk.get("positionBudgetEUR")
    maxloss = risk.get("maxLossEUR")
    daily = risk.get("dailyLossEUR")
    daily_cap = risk.get("dailyLossLimitEUR")
    fees = risk.get("expectedFeesEUR")
    if not all(number(x) for x in (cash, budget, maxloss, daily_cap)) or not all(
            number(x, zero=True) for x in (daily, fees)):
        _reason(reasons, "Liquidität, Einsatz-, Verlust- oder Gebührennachweis fehlen")
    if number(maxloss) and maxloss > MAX_RISK_EUR:
        _reason(reasons, "Unzulässige Verlustobergrenze")
    if number(daily, zero=True) and number(daily_cap) and daily >= daily_cap:
        _reason(reasons, "Tagesverlustgrenze erreicht")
    if type(risk.get("openPositions")) is not int or type(risk.get("maxPositions")) is not int or (
            risk.get("maxPositions", 0) <= 0 or risk.get("openPositions", -1) < 0 or
            risk.get("openPositions", 0) >= risk.get("maxPositions", 0)):
        _reason(reasons, "Positionsgrenze erreicht oder nicht nachgewiesen")
    stop = risk.get("stopProductBidEUR")
    target = risk.get("targetProductBidEUR")
    if not number(stop) or not number(target) or not number(ask) or stop >= ask or target <= ask:
        _reason(reasons, "Produkt-Stop/Ziel ungültig oder fehlt")
    if risk.get("stopTargetVerified") is not True:
        _reason(reasons, "Produkt-Stop/Ziel nicht geprüft")

    qty = 0
    if not reasons:
        # Risk cap assumes a complete Knock-out loss, not a guaranteed stop fill.
        alloc = min(cash - fees, budget - fees, maxloss - fees, daily_cap - daily - fees)
        qty = min(MAX_QUANTITY, math.floor(alloc / ask))
        if qty < 1:
            _reason(reasons, "Budget reicht für keine ganze Stückzahl inklusive Risikogrenze")
    state = ("BROKER_API_NOT_CONNECTED" if broker != "degiro" else
             "BLOCKED" if reasons else "MANUAL_REVIEW")
    notional = round(qty * ask, 2) if qty else None
    worst_case = round(notional + fees, 2) if qty else None
    proposal = {
        "state": state, "broker": broker, "mode": "READ_ONLY_PREPARATION",
        "signalDirection": direction if direction in ("LONG", "SHORT") else None,
        "isin": isin, "reviewedAt": now.isoformat(), "reasons": reasons,
        "orderSide": "BUY" if qty else None, "orderType": "LIMIT" if qty else None,
        "quantity": qty, "limitPriceEUR": ask if qty else None,
        "indicativeBidEUR": bid if qty else None,
        "orderNotionalEUR": notional, "estimatedWorstCaseLossEUR": worst_case,
        "stopProductBidEUR": stop if qty else None,
        "targetProductBidEUR": target if qty else None,
        "quoteAt": product.get("quoteAt") if qty else None,
        "quoteSource": product.get("quoteSource") if qty else None,
        "executionPriceConfirmed": False, "brokerBuyPermissionVerified": False,
        "manualBrokerConfirmationRequired": True, "tradeApproved": False,
        "orderSubmitted": False, "orderId": None,
        "monitoring": "REQUIRES_INDEPENDENT_CONFIRMED_FILL",
        "note": ("Nur unverbindliche Ordervorbereitung. DEGIRO-Orderfenster, Stückzahl, "
                 "Handelskosten und finalen Ausführungskurs manuell prüfen. "
                 "Bei Knock-out oder Kurslücke kann der vollständige Einsatz verloren gehen."),
    }
    if qty:
        stable = json.dumps([broker, isin, direction, qty, ask, product["quoteAt"]],
                            separators=(",", ":"), ensure_ascii=True)
        proposal["reviewFingerprint"] = hashlib.sha256(stable.encode()).hexdigest()
    return proposal


def pipeline_status():
    """Expose verifiable scope, never claim live trade or order permission."""
    return {
        "version": "four-stage-readiness-v1",
        "signalDetection": "EXISTING_EVALUATOR_REQUIRES_FRESH_EVIDENCE",
        "productAndRisk": "EXISTING_RANKING_PLUS_STRICT_READ_ONLY_ORDER_PREVIEW",
        "execution": "DEGIRO_MANUAL_ONLY_OFFICIAL_API_UNAVAILABLE",
        "otherBroker": "OFFICIAL_BROKER_API_REQUIRES_ELIGIBLE_ACCOUNT_AND_INSTRUMENT",
        "positionMonitoring": "CONFIRMED_RECEIPT_ONLY_EXISTING_REAL_TRADE_JOURNAL",
        "realOrdersEnabled": False,
        "brokerAccountLinkedForTrading": False,
        "quoteIsExecutable": False,
        "canOpenOrders": False,
        "canSellOrders": False,
        "safety": "No trade calls, credential reads, account mutations or auto live activation.",
    }
