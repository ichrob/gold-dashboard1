"""Parse DEGIRO execution-PDF text as untrusted, read-only evidence.

Does not book, activate or execute a trade. Never exports postal addresses or
account details. A PDF doesn't authenticate its author or prove a timezone.
"""
import hashlib
import math
import re
from datetime import datetime

ISIN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}[A-Z0-9]{9}[0-9](?![A-Z0-9])")
ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)


def _isin_ok(isin):
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in isin)
    total = 0
    for i, ch in enumerate(reversed(digits)):
        digit = int(ch) * (2 if i % 2 else 1)
        total += digit // 10 + digit % 10
    return total % 10 == 0


def _unique_label(text, label, capture):
    # PDF text extractors split table columns with either a newline or spaces.
    # Never take financial amounts from another, differently labelled row.
    pattern = rf"(?im)^[ \t]*{label}[ \t]*:?[ \t]*(?:\n[ \t]*)?({capture})[ \t]*(?=\n|$)"
    matches = re.findall(pattern, text)
    return matches[0] if len(matches) == 1 else None


def parse_document_text(raw):
    """Extract only explicit, unique facts; never infer execution or market data."""
    def incomplete(reason):
        return {"status": "incomplete", "reason": reason}

    if not isinstance(raw, str) or len(raw) > 100000:
        return incomplete("Dokumenttext fehlt oder ist zu groß")
    text = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    if not re.search(r"\bDEGIRO\b", text, re.I):
        return {"status": "ignored", "reason": "Kein DEGIRO-Beleg"}
    if not re.search(r"\bDie folgende Order wurde ausgeführt\s*:", text, re.I):
        return incomplete("Ausgeführte Order nicht ausdrücklich bestätigt")
    if re.search(r"\b(storniert|abgelehnt|cancelled|rejected)\b", text, re.I):
        return incomplete("Abweichender Orderstatus")

    order_id = _unique_label(text, r"Order[ -]?ID", ID_RE.pattern)
    isin = _unique_label(text, "ISIN", r"[A-Z]{2}[A-Z0-9]{9}[0-9]")
    side = _unique_label(text, "Auftrag", r"Kauf|Verkauf")
    qty = _unique_label(text, "Anzahl", r"[0-9]{1,7}")
    price = _unique_label(text, "Kurs", r"EUR[ \t]+[0-9]+(?:[.,][0-9]{1,6})?")
    when = _unique_label(text, "Ausführungsdatum",
                         r"[0-9]{2}\.[0-9]{2}\.[0-9]{4},?[ \t]+[0-9]{2}:[0-9]{2}:[0-9]{2}")

    if not all((order_id, isin, side, qty, price, when)):
        return incomplete("Order-ID, ISIN, Auftrag, Stückzahl, Kurs oder Ausführungsdatum fehlen bzw. sind uneindeutig")
    if not ISIN_RE.fullmatch(isin) or not _isin_ok(isin):
        return incomplete("Ungültige ISIN-Prüfziffer")
    try:
        amount = int(qty)
        eur = float(price.split()[1].replace(",", "."))
        dt = datetime.strptime(when.replace(",", ""), "%d.%m.%Y %H:%M:%S")
        if not (0 < amount <= 1000000 and math.isfinite(eur) and eur > 0):
            return incomplete("Stückzahl oder EUR-Kurs ungültig")
    except (ValueError, OverflowError, IndexError):
        return incomplete("Handelsdaten ungültig")

    costs = _unique_label(text, "Gesamte Kosten",
                          r"CHF[ \t]+-?[0-9]+(?:[.,][0-9]{1,2})?")
    costs_chf = abs(float(costs.split()[1].replace(",", "."))) if costs else None
    gross = _unique_label(text, "Wert", r"CHF[ \t]+-?[0-9]+(?:[.,][0-9]{1,2})?")
    total = _unique_label(text, "Gesamt", r"CHF[ \t]+-?[0-9]+(?:[.,][0-9]{1,2})?")
    eur_total = _unique_label(text, "Wert in Lokalwährung",
                              r"EUR[ \t]+-?[0-9]+(?:[.,][0-9]{1,4})?")
    fx = _unique_label(text, "Wechselkurs", r"[0-9]+(?:[.,][0-9]{1,8})?")
    gross_chf = float(gross.split()[1].replace(",", ".")) if gross else None
    total_chf = float(total.split()[1].replace(",", ".")) if total else None
    eur_value = float(eur_total.split()[1].replace(",", ".")) if eur_total else None
    fx_rate = float(fx.replace(",", ".")) if fx else None
    expected_sign = -1 if side.lower() == "kauf" else 1
    if (gross_chf is not None and gross_chf * expected_sign <= 0
            or total_chf is not None and total_chf * expected_sign <= 0
            or eur_value is not None and eur_value * expected_sign <= 0
            or eur_value is not None and abs(abs(eur_value)-eur*amount)>0.015
            or gross_chf is not None and total_chf is not None and costs_chf is not None
                and abs(total_chf - (gross_chf - costs_chf)) > 0.025
            or fx_rate is not None and not (0.1 <= fx_rate <= 5)
            or fx_rate is not None and gross_chf is not None
                and abs(eur*amount/fx_rate-abs(gross_chf))>0.08):
        return incomplete("Beträge, Gebühren, Währung oder Wechselkurs widersprüchlich")
    # Only a complete, arithmetically consistent CHF triplet is net evidence.
    complete_chf = all(x is not None for x in (gross_chf, total_chf, costs_chf))
    # No explicit timezone is printed. Preserve the source clock verbatim;
    # never fabricate a UTC timestamp, an intraday quote or a current position.
    return {
        "status": "pending-review",
        "sourceKind": "DEGIRO-execution-PDF",
        "reason": "Historischer DEGIRO-PDF-Beleg erkannt. PDF-Authentizität und Zeitzone nicht unabhängig bestätigt.",
        "isin": isin, "side": "BUY" if side.lower() == "kauf" else "SELL",
        "quantity": amount, "priceEur": eur,
        "executedLocal": dt.strftime("%d.%m.%Y %H:%M:%S"),
        "timezoneConfirmed": False, "executedAt": None,
        "orderIdDigest": hashlib.sha256(order_id.lower().encode("ascii")).hexdigest(),
        "costsChf": costs_chf,
        "grossChf": round(abs(gross_chf),2) if complete_chf else None,
        "totalChf": round(abs(total_chf),2) if complete_chf else None,
        "fxEurPerChf": fx_rate, "activeTrade": False,
    }
