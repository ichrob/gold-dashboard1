"""Secure, read-only DEGIRO email-import staging.

A received email is NOT a broker execution proof or an executable order.
Everything remains pending user review; no active trades are created.
"""
import base64
import hashlib
import hmac
import json
import math
import os
import re
import time
from datetime import datetime, timezone
from email.utils import parseaddr
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

VERSION = "degiro-email-staging-v1"
MAX_BODY = 128 * 1024
ZURICH = ZoneInfo("Europe/Zurich")
ISIN_RE = re.compile(r"(?<![A-Z0-9])[A-Z]{2}[A-Z0-9]{9}[0-9](?![A-Z0-9])")
NUMBER = r"([0-9]+(?:[.'\u2019 ][0-9]{3})*(?:[,\.][0-9]{1,6})?)"


def verify_svix(body, headers, secret, now=None):
    """Verify AgentMail's Svix signature over ORIGINAL bytes, not parsed JSON."""
    if not isinstance(body, bytes) or not 0 < len(body) <= MAX_BODY:
        raise ValueError("invalid webhook size")
    if not secret or not secret.startswith("whsec_"):
        raise ValueError("webhook not configured")
    msg_id = headers.get("svix-id") or headers.get("webhook-id")
    when = headers.get("svix-timestamp") or headers.get("webhook-timestamp")
    sig = headers.get("svix-signature") or headers.get("webhook-signature")
    if not all(isinstance(x, str) and x for x in (msg_id, when, sig)):
        raise ValueError("missing signature")
    if len(msg_id) > 160 or len(sig) > 2048 or not when.isdecimal():
        raise ValueError("malformed signature")
    now = time.time() if now is None else now
    if abs(now - int(when)) > 300:
        raise ValueError("webhook timestamp expired")
    try:
        key = base64.b64decode(secret[6:] + "=" * (-len(secret[6:]) % 4), validate=True)
    except (ValueError, base64.binascii.Error):
        raise ValueError("invalid secret") from None
    if len(key) < 16:
        raise ValueError("invalid secret")
    expected = base64.b64encode(hmac.new(
        key, msg_id.encode() + b"." + when.encode() + b"." + body,
        hashlib.sha256).digest()).decode()
    signatures = [x[3:] for x in sig.split() if x.startswith("v1,")]
    if not signatures or not any(hmac.compare_digest(x, expected) for x in signatures):
        raise ValueError("webhook signature invalid")
    payload = json.loads(body)
    if not isinstance(payload, dict):
        raise ValueError("invalid webhook payload")
    return payload, msg_id


def isin_ok(value):
    if not isinstance(value, str) or not ISIN_RE.fullmatch(value):
        return False
    digits = "".join(str(ord(c) - 55) if c.isalpha() else c for c in value)
    acc = 0
    for idx, char in enumerate(reversed(digits)):
        n = int(char) * (2 if idx % 2 else 1)
        acc += n // 10 + n % 10
    return acc % 10 == 0


def number(raw):
    if not isinstance(raw, str):
        return None
    s = raw.strip().replace(" ", "").replace("'", "").replace("\u2019", "")
    if "," in s:
        if s.count(",") != 1:
            return None
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    try:
        v = float(s)
        return v if math.isfinite(v) and v > 0 else None
    except (ValueError, OverflowError):
        return None


def labelled_value(text, labels):
    matches = re.findall(r"(?:^|\n)\s*(?:" + labels + r")\s*[:=\-]?\s*(?:EUR|€\s*)?\s*" + NUMBER + r"\s*(?:€|EUR|Stk\.?|Stück)?\b", text, re.I)
    return matches[0] if len(matches) == 1 else None


def price_value(text):
    # One explicit fill price is mandatory; a market quote is not an execution.
    raw = labelled_value(text, r"Ausführungskurs|Ausführungspreis|Kaufkurs|Verkaufskurs|Executed Price|Execution Price|Fill Price")
    return number(raw) if raw else None


def execution_time(text):
    raw = re.findall(
        r"(?:^|\n)\s*(?:Ausführungsdatum|Ausführungszeit|Handelszeit|Execution time|Executed at)\s*[:=\-]?\s*([^\n]{10,60})",
        text, re.I)
    if len(raw) != 1:
        return None
    value = raw[0].strip()
    dt = None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        match = re.fullmatch(
            r"(\d\d)[./](\d\d)[./](\d{4})\s+(\d\d):(\d\d)(?::(\d\d))?\s*(CET|CEST|UTC|Z|[+-]\d\d:\d\d)?",
            value, re.I)
        if match:
            day, month, year, hour, minute, seconds, tzname = match.groups()
            # An undated timezone or missing seconds cannot prove a 90-second quote.
            if not tzname:
                return None
            from datetime import timedelta
            tz = {"CET":timezone(timedelta(hours=1)),
                  "CEST":timezone(timedelta(hours=2)),
                  "UTC":timezone.utc, "Z":timezone.utc}.get(tzname.upper())
            if tz is None:
                sign = 1 if tzname[0] == "+" else -1
                tz = timezone(sign * timedelta(hours=int(tzname[1:3]), minutes=int(tzname[4:6])))
            try:
                dt = datetime(int(year), int(month), int(day),
                              int(hour), int(minute), int(seconds or 0), tzinfo=tz)
            except ValueError:
                return None
    if dt is None or dt.tzinfo is None:
        return None
    return dt.astimezone(timezone.utc).isoformat()


def parse_confirmation(subject, text):
    """Only structured, unambiguous, post-trade executions become proposals.

    Never infer execution from a pre-trade order, security name or total.
    A screenshot/PDF-only confirmation is left incomplete, not guessed.
    """
    if not isinstance(subject, str) or not isinstance(text, str):
        return {"status":"incomplete", "reason":"Mailtext fehlt"}
    # The real DEGIRO transaction PDF and some notification mail bodies use
    # table labels "Auftrag" and "Kurs", not "Transaktion"/"Ausführungskurs".
    # Use a dedicated fail-closed parser, never turn its historical clock into
    # a UTC market timestamp, and never activate positions from email alone.
    if "Die folgende Order wurde ausgeführt" in text and "Auftrag" in text:
        import trade_document_import
        return trade_document_import.parse_document_text(text)
    if len(text) > MAX_BODY:
        return {"status":"incomplete", "reason":"Mail zu groß"}
    if not re.search(r"\bDEGIRO\b", subject + "\n" + text, re.I):
        return {"status":"ignored", "reason":"Keine DEGIRO-Bestätigung"}
    # Ignore unsolicited account messages, transactions, deposits etc.
    if not re.search(r"\b(Ausführung|ausgeführt|executed|execution|fill|trade confirmation)\b", subject + "\n" + text, re.I):
        return {"status":"incomplete", "reason":"Ausführung nicht eindeutig bestätigt"}
    if re.search(r"\b(storniert|cancelled|abgelehnt|rejected|ausstehend|pending)\b", subject + "\n" + text, re.I):
        return {"status":"incomplete", "reason":"Order ist nicht eindeutig ausgeführt"}
    ids = set(ISIN_RE.findall(text.upper()))
    if len(ids) != 1 or not isin_ok(next(iter(ids))):
        return {"status":"incomplete", "reason":"ISIN fehlt, mehrfach oder ungültig"}
    # Require an explicitly labelled transaction side, not a product's Long/Short.
    direction = re.findall(r"(?:^|\n)\s*(?:Transaktion|Ordertyp|Geschäft|Order action|Transaction)\s*[:=\-]?\s*(Kauf|Verkauf|Buy|Sell)\b", text, re.I)
    if len(direction) != 1:
        return {"status":"incomplete", "reason":"Kauf/Verkauf unklar"}
    side = "BUY" if direction[0].lower() in ("kauf", "buy") else "SELL"
    count_raw = labelled_value(text, r"Anzahl|Stückzahl|Quantity|Executed Quantity")
    qty = number(count_raw) if count_raw else None
    price = price_value(text)
    timestamp = execution_time(text)
    currency_check = bool(re.search(r"(?:^|\n)\s*(?:Währung|Currency)\s*[:=\-]?\s*(EUR|€)\b", text, re.I)
                          or re.search(r"(?:(?:Ausführungskurs|Ausführungspreis|Kaufkurs|Verkaufskurs|Execution Price|Fill Price)[^\n]{0,40})\bEUR\b", text, re.I))
    if qty is None or not qty.is_integer() or not 0 < qty <= 1000000 or price is None or not timestamp or not currency_check:
        return {"status":"incomplete", "reason":"Stückzahl, EUR-Ausführungskurs oder Kurszeit nicht sicher belegt",
                "isin":next(iter(ids)), "side":side}
    return {"status":"pending-review", "reason":"E-Mail erkannt; Broker-Ausführung nicht unabhängig verifiziert",
            "isin":next(iter(ids)), "side":side, "quantity":int(qty),
            "priceEur":price, "executedAt":timestamp}


def confirmation_html_text(raw):
    """Read table text locally, without executing HTML or loading resources."""
    if not isinstance(raw, str) or len(raw) > MAX_BODY:
        return ""

    class TextReader(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.parts = []
            self.skip = 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.skip += 1
            if not self.skip and tag in ("td", "th", "tr", "p", "div", "br"):
                self.parts.append("\n")

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self.skip = max(0, self.skip - 1)
            if not self.skip and tag in ("td", "th", "tr", "p", "div"):
                self.parts.append("\n")

        def handle_data(self, data):
            if not self.skip:
                self.parts.append(re.sub(r"\s+", " ", data))

    reader = TextReader()
    reader.feed(raw)
    return "\n".join(line.strip() for line in "".join(reader.parts).splitlines() if line.strip())


def import_event(event, allowed_sender):
    if event.get("type", "event") != "event" or event.get("event_type") != "message.received":
        return {"status":"ignored", "reason":"Kein eingegangener E-Mail-Event"}
    message = event.get("message")
    if not isinstance(message, dict):
        raise ValueError("message missing")
    raw_from = message.get("from_") or message.get("from") or ""
    if isinstance(raw_from, list):
        if len(raw_from) != 1 or not isinstance(raw_from[0], str):
            return {"status":"sender-unconfirmed", "reason":"Absender mehrdeutig"}
        raw_from = raw_from[0]
    if not isinstance(raw_from, str):
        return {"status":"sender-unconfirmed", "reason":"Absender nicht lesbar"}
    sender = parseaddr(raw_from)[1].lower()
    recipients = message.get("to") or []
    if isinstance(recipients, str):
        recipients = [recipients]
    # AgentMail's signed inbox_id identifies delivery. Redirected mail retains
    # the original To header; that header does not identify the receiving inbox.
    # A contradictory inbox must never be rescued by a matching To header.
    inbox = message.get("inbox_id")
    if inbox is not None and inbox != "bob-degiro@agentmail.to":
        return {"status":"ignored", "reason":"Anderes AgentMail-Postfach"}
    if (inbox is None and (not isinstance(recipients, list) or
            not recipients or any(not isinstance(x, str) for x in recipients) or
            not any(parseaddr(x)[1].lower() == "bob-degiro@agentmail.to"
                    for x in recipients))):
        return {"status":"ignored", "reason":"Andere Empfängeradresse"}
    allowed = parseaddr(allowed_sender or "")[1].lower()
    # A sender address is not DKIM proof. Do not activate trades from it.
    if not sender or not allowed or not hmac.compare_digest(sender, allowed):
        return {"status":"sender-unconfirmed", "reason":"Weiterleitungs-Absender nicht verifiziert"}
    body = message.get("text") or message.get("extracted_text") or ""
    if not isinstance(body, str):
        body = ""
    # GMX Android forwards can be HTML-only. The extracted reply omits the
    # quoted broker confirmation, so use the full HTML when text is absent.
    html_source = not body.strip() and isinstance(message.get("html"), str)
    if html_source:
        body = confirmation_html_text(message["html"])
    result = parse_confirmation(message.get("subject",""), body)
    if html_source and result.get("status") == "pending-review":
        result["sourceKind"] = "DEGIRO-execution-email-HTML"
        result["reason"] = "DEGIRO-HTML-Bestätigung erkannt; Prüfung der Ausführung und Zeitzone erforderlich"
    return result


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_trade_email_import (
       message_id TEXT PRIMARY KEY,
       imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
       payload JSONB NOT NULL
    )""")


def receive(conn, event, signed_id, allowed_sender):
    result = import_event(event, allowed_sender)
    message = event.get("message") or {}
    if not isinstance(message, dict):
        message = {}
    msg_id = message.get("message_id")
    # Stable delivery id for retries; do not store raw financial emails.
    if not isinstance(msg_id, str) or not 1 <= len(msg_id) <= 200:
        msg_id = signed_id
    if not isinstance(msg_id, str) or len(msg_id) > 200:
        raise ValueError("invalid message id")
    record = dict(messageId=msg_id, version=VERSION, result=result, receivedAt=datetime.now(timezone.utc).isoformat())
    inserted = conn.execute("""INSERT INTO bob_trade_email_import(message_id,payload)
          VALUES(%s,%s::jsonb) ON CONFLICT DO NOTHING RETURNING message_id""",
          (msg_id,json.dumps(record))).fetchone()
    # Return no confidential data to the webhook caller.
    return {"ok":True, "new":bool(inserted)}


def report(conn):
    rows=conn.execute("""SELECT payload || jsonb_build_object('messageId',message_id) FROM bob_trade_email_import
       ORDER BY imported_at DESC LIMIT 30""").fetchall()
    return {"ok":True, "configured":bool(os.environ.get("BOB_AGENTMAIL_WEBHOOK_SECRET") and
                                     os.environ.get("BOB_EMAIL_ALLOWED_FROM")),
            "items":[r[0] for r in rows], "mode":"read-only-pending-review",
            "notice":"Keine Brokerorders. E-Mail-Daten sind noch kein bestätigter Trade."}
