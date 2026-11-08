"""Non-executing DEGIRO handoff for purchase, stop changes, and exits.

All returned values are informational. Never communicates with a broker,
modifies an account, marks an order filled or changes a broker stop.
"""
from datetime import datetime, timezone, timedelta
import math

from broker_bridge import validate_isin
from trade_execution_readiness import clock, number

QUOTE_MAX_AGE_SECONDS = 90
SIDES = ("LONG", "SHORT")


def _safe_time(value, now):
    try:
        at = clock(value)
    except (ValueError, TypeError, AttributeError):
        return None
    delta = (now - at).total_seconds()
    return at if 0 <= delta <= QUOTE_MAX_AGE_SECONDS else None


def _active_trade(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get("active") is not True or snapshot.get("recordOnly") is True:
        return None, "Keine bestätigte aktive Position"
    product = snapshot.get("product")
    purchase = snapshot.get("purchase")
    if not isinstance(product, dict) or not isinstance(purchase, dict):
        return None, "Produkt- oder Kaufbeleg fehlt"
    try:
        validate_isin(product.get("isin"))
    except ValueError:
        return None, "Produkt-ISIN nicht bestätigt"
    if snapshot.get("dir") not in SIDES:
        return None, "Produktrichtung nicht bestätigt"
    qty = product.get("quantity")
    if type(qty) not in (int, float) or not math.isfinite(qty) or qty <= 0 or not float(qty).is_integer():
        return None, "Bestätigte ganze Stückzahl fehlt"
    if not (purchase.get("transactionId") or purchase.get("orderIdDigest") or purchase.get("messageId")):
        return None, "Eindeutiger Kaufbeleg fehlt"
    if product.get("currency") != "EUR":
        return None, "CHF-Produkt benötigt gesonderte Währungs-/Gebührenprüfung"
    return product, None


def _base(state, snapshot, reasons):
    product = snapshot.get("product") if isinstance(snapshot, dict) else {}
    product = product if isinstance(product, dict) else {}
    return {
        "state": state,
        "broker": "degiro",
        "orderSubmitted": False,
        "brokerStopChanged": False,
        "executionConfirmed": False,
        "tradeId": snapshot.get("tradeId") if isinstance(snapshot, dict) else None,
        "isin": product.get("isin"),
        "currency": product.get("currency"),
        "quantity": product.get("quantity"),
        "reasons": reasons,
        "manualOnly": True,
    }


def buy_handoff(review, now=None):
    """Only return a manual buy worksheet for still-current evidence."""
    if not isinstance(review, dict):
        raise ValueError("Prüfbericht fehlt")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Prüfzeit ohne Zeitzone")
    reasons = []
    if review.get("broker") != "degiro" or review.get("state") != "MANUAL_REVIEW":
        reasons.append("Kein freigegebener manueller DEGIRO-Prüfbericht")
    if review.get("tradeApproved") is not False or review.get("orderSubmitted") is not False or review.get("manualBrokerConfirmationRequired") is not True:
        reasons.append("Orderstatus nicht eindeutig manuell")
    try:
        validate_isin(review.get("isin"))
    except ValueError:
        reasons.append("ISIN ungültig")
    if review.get("signalDirection") not in SIDES or review.get("orderSide") != "BUY" or review.get("orderType") != "LIMIT":
        reasons.append("Richtung oder Orderart fehlt")
    if type(review.get("quantity")) is not int or review["quantity"] <= 0:
        reasons.append("Stückzahl fehlt")
    if not number(review.get("limitPriceEUR")):
        reasons.append("Indikativer Briefkurs fehlt")
    quote_at = _safe_time(review.get("quoteAt"), now)
    if quote_at is None:
        reasons.append("Quellenzeit veraltet: Order neu prüfen")
    if not review.get("reviewFingerprint"):
        reasons.append("Unveränderlicher Prüfbezug fehlt")
    result = _base("BLOCKED" if reasons else "MANUAL_BUY_REVIEW", {}, reasons)
    if reasons:
        return result
    result.update(
        isin=review["isin"], currency="EUR", direction=review["signalDirection"], orderSide="BUY",
        orderType="LIMIT", quantity=review["quantity"],
        indicativeLimitEUR=review["limitPriceEUR"],
        quoteAt=quote_at.isoformat(),
        expiresAt=(quote_at + timedelta(seconds=QUOTE_MAX_AGE_SECONDS)).isoformat(),
        estimatedWorstCaseLossEUR=review.get("estimatedWorstCaseLossEUR"),
        reference=review["reviewFingerprint"],
        instructions=(
            "ISIN in DEGIRO selbst suchen; Turbo, Richtung, Handelsplatz, "
            "verfügbaren Ordertyp, echten Briefkurs und Gebühren prüfen; "
            "Limit und Menge selbst eingeben und Order selbst bestätigen. "
            "Danach bestätigten Ausführungsbeleg in Bob übernehmen."
        ),
    )
    return result


def stop_update_handoff(snapshot, *, proposed_stop_eur, broker_confirmed_stop_eur=None,
                        observed_bid_eur=None, bid_at=None, bid_source=None, now=None):
    """Never propose a looser stop; missing original quote/known broker stop block."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Prüfzeit ohne Zeitzone")
    if not isinstance(snapshot, dict):
        raise ValueError("Trade fehlt")
    product, error = _active_trade(snapshot)
    reasons = [error] if error else []
    if not number(proposed_stop_eur):
        reasons.append("Neuer Produkt-Stopp fehlt")
    if not number(observed_bid_eur) or not isinstance(bid_source, str) or not bid_source.strip() or _safe_time(bid_at, now) is None:
        reasons.append("Aktueller originaler Produkt-Geldkurs mit Quellenzeit fehlt")
    elif number(proposed_stop_eur) and proposed_stop_eur >= observed_bid_eur:
        reasons.append("Neuer Stopp nicht unter beobachtetem Geldkurs")
    if not number(broker_confirmed_stop_eur):
        reasons.append("Tatsächlich bestehender Broker-Stopp noch nicht bestätigt")
    elif number(proposed_stop_eur) and proposed_stop_eur <= broker_confirmed_stop_eur:
        reasons.append("Stopp würde nicht enger werden")
    result = _base("BLOCKED" if reasons else "MANUAL_STOP_REVIEW", snapshot, reasons)
    if not reasons:
        result.update(
            existingStopEUR=broker_confirmed_stop_eur,
            suggestedStopEUR=proposed_stop_eur,
            quoteAt=clock(bid_at).isoformat(), quoteSource=bid_source,
            instructions="Bestehenden DEGIRO-Stopp und offene Orders manuell prüfen. "
                "Nur einen höheren Verkaufs-Stopp setzen. Brokerbestätigung dokumentieren.",
        )
    return result


def sell_handoff(snapshot, quote, *, exit_reason, quantity=None, now=None):
    """Prepare a manual exit, never assume that an unexecuted order was filled."""
    if not isinstance(snapshot, dict) or not isinstance(quote, dict):
        raise ValueError("Trade oder Kurs fehlt")
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Prüfzeit ohne Zeitzone")
    product, error = _active_trade(snapshot)
    reasons = [error] if error else []
    if exit_reason not in ("stop", "target", "trend-reversal", "manual"):
        reasons.append("Ausstiegsgrund fehlt")
    held = int(product["quantity"]) if product else 0
    quantity = held if quantity is None else quantity
    if type(quantity) is not int or not 1 <= quantity <= held:
        reasons.append("Verkaufsmenge überschreitet bestätigten Bestand")
    elif quantity != held:
        reasons.append("Teilverkauf noch nicht durch das bestehende Ausführungsjournal abbildbar")
    if not product or quote.get("isin") != product.get("isin") or quote.get("currency") != "EUR":
        reasons.append("Kurs gehört nicht zum bestätigten Produkt")
    bid = quote.get("bidEUR")
    if not number(bid) or quote.get("quoteKind") != "ISSUER_BID_ASK" or not str(quote.get("source") or "").strip():
        reasons.append("Originaler EUR-Produkt-Geldkurs fehlt")
    at = _safe_time(quote.get("quoteAt"), now)
    if at is None:
        reasons.append("Originalzeit des Verkaufskurses fehlt oder ist veraltet")
    result = _base("BLOCKED" if reasons else "MANUAL_SELL_REVIEW", snapshot, reasons)
    if not reasons:
        result.update(
            quantity=quantity, side="SELL", indicativeBidEUR=bid,
            quoteAt=at.isoformat(),
            instructions="DEGIRO manuell öffnen; richtige ISIN, bestätigten Bestand, "
                "offene Stop-/Verkaufsorders und aktuell angebotenen Geldkurs prüfen. "
                "Verkaufsorder selbst eingeben und bestätigen. Erst danach den "
                "echten Ausführungsbeleg in Bob übernehmen.",
        )
    return result
