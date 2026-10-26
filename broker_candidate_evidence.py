"""Private user-uploaded DEGIRO detail screenshot observations.

Client-side OCR reads the original image locally. This service receives only
bounded structured fields and a SHA-256 image fingerprint, never image bytes,
raw OCR text, account identifiers, credentials, orders or holdings. It verifies
consistency and expiry, NOT an independent live DEGIRO account connection.
Does not write the active screenshot list, Top-3, risk rules or trade status.
"""
import json
import math
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from product_quotes import valid_isin

ZONE = ZoneInfo("Europe/Zurich")
MAX_ITEMS = 120
VALID_MIME = frozenset(("image/jpeg", "image/png", "image/webp"))
KIND = "user-uploaded-detail-ocr"
ORIGIN = "user-uploaded-degiro-detail-image"


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_degiro_candidate_proofs (
        isin TEXT PRIMARY KEY,
        payload JSONB NOT NULL,
        observed_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""")


def _local_time(source, now):
    if not isinstance(source, str) or not re.fullmatch(
        r"\d{2}[./]\d{2}[./]\d{4} \d{2}:\d{2}(?::\d{2})?", source
    ):
        raise ValueError("DEGIRO-Screenshot: vollständige Originalzeit fehlt")
    text = source.replace("/", ".")
    fmt = "%d.%m.%Y %H:%M:%S" if len(text) == 19 else "%d.%m.%Y %H:%M"
    try:
        naive = datetime.strptime(text, fmt)
        local = naive.replace(tzinfo=ZONE)
        # 02:xx after DST fallback may have two distinct instants.
        if local.replace(fold=0).utcoffset() != local.replace(fold=1).utcoffset():
            raise ValueError("Mehrdeutige Schweizer Zeit")
        if local.astimezone(timezone.utc).astimezone(ZONE).replace(tzinfo=None) != naive:
            raise ValueError("Nicht existierende Schweizer Zeit")
    except ValueError as exc:
        raise ValueError("DEGIRO-Screenshot: Originalzeit nicht eindeutig") from exc
    if local.date() != now.astimezone(ZONE).date():
        raise ValueError("DEGIRO-Detailbild muss vom heutigen Schweizer Datum sein")
    if local > now or now.astimezone(ZONE).hour >= 22:
        raise ValueError("DEGIRO-Produktnachweis aus Zukunft oder nach 22 Uhr")
    return local


def _positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def validate(payload, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Serveruhr ohne Zeitzone")
    if not isinstance(payload, dict) or set(payload) != {
        "isin", "venue", "currency", "sourceTime", "source",
        "brokerDisplayConfirmed", "isExecutableQuote",
        "orderWindowVerified", "orderSubmitted", "executionGuaranteed",
        "imageSha256", "imageBytes", "imageMime", "bid", "ask"
    }:
        raise ValueError("DEGIRO-Produktbild: fehlende oder unerwartete Belegfelder")
    isin = payload["isin"]
    if not isinstance(isin, str) or not valid_isin(isin):
        raise ValueError("ISIN/Prüfziffer im Bild nicht eindeutig")
    if payload["source"] != "DEGIRO-Produktdetail" or any(
        payload[k] is not expected for k, expected in {
            "brokerDisplayConfirmed": True, "isExecutableQuote": False,
            "orderWindowVerified": False, "orderSubmitted": False,
            "executionGuaranteed": False,
        }.items()
    ):
        raise ValueError("Nur eine beobachtete DEGIRO-Produktdetailanzeige zulässig")
    venue = payload["venue"]
    if (not isinstance(venue, str) or not 1 <= len(venue.strip()) <= 100
            or re.fullmatch(r"[-—]|unbekannt|unknown", venue.strip(), re.I)
            or any(ord(c) < 32 for c in venue)):
        raise ValueError("Börse/Handelsplatz im DEGIRO-Produktbild fehlt")
    currency = payload["currency"]
    if currency not in ("EUR", "CHF"):
        raise ValueError("Produktwährung EUR oder CHF nicht belegt")
    digest = payload["imageSha256"]
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Bild-Fingerabdruck fehlt")
    if not isinstance(payload["imageBytes"], int) or type(payload["imageBytes"]) is not int:
        raise ValueError("Ungültige Bildgröße")
    if (not 1024 <= payload["imageBytes"] <= 12_000_000 or
            not isinstance(payload["imageMime"], str) or payload["imageMime"] not in VALID_MIME):
        raise ValueError("Unterstützt: PNG, JPEG oder WebP bis 12 MB")
    bid, ask = payload["bid"], payload["ask"]
    if (bid is None) != (ask is None):
        raise ValueError("Geld/Brief nur als belegtes Paar")
    if bid is not None and (not _positive(bid) or not _positive(ask) or ask < bid):
        raise ValueError("Ungültiges Geld-/Briefpaar im Screenshot")
    at = _local_time(payload["sourceTime"], now)
    until = at.replace(hour=22, minute=0, second=0, microsecond=0)
    return {
        "isin": isin, "broker": "DEGIRO", "venue": venue.strip(),
        "currency": currency, "kind": KIND, "origin": ORIGIN,
        "observedMinute": at.strftime("%Y-%m-%dT%H:%M"),
        "originalSourceTime": payload["sourceTime"],
        "observedAt": at.isoformat(), "validUntil": until.isoformat(),
        "imageSha256": digest, "imageBytes": payload["imageBytes"],
        "imageMime": payload["imageMime"], "listingConfirmed": True,
        "brokerDisplayObserved": True, "executionConfirmed": False,
        "tradeApproved": False, "rankingsEligible": False,
        "isExecutableQuote": False, "source": "Nutzerbild · DEGIRO-Produktdetail",
        "checkedAt": now.isoformat(), "bid": bid, "ask": ask,
        "timezone": "Europe/Zurich", "timePrecision": "minute",
        "note": "Nur aus hochgeladenem Bild gelesene Broker-Anzeige, keine Live-Konto- oder Ausführungsgarantie",
    }


def _at(value):
    if not isinstance(value, str):
        return None
    try:
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value if value.tzinfo is not None else None
    except ValueError:
        return None


def current(record, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(record, dict):
        return False
    at = _at(record.get("observedAt"))
    until = _at(record.get("validUntil"))
    if not at or not until or record.get("kind") != KIND or record.get("origin") != ORIGIN:
        return False
    return bool(
        record.get("broker") == "DEGIRO"
        and record.get("listingConfirmed") is True
        and record.get("executionConfirmed") is False
        and record.get("isExecutableQuote") is False
        and isinstance(record.get("isin"), str)
        and valid_isin(record["isin"])
        and at <= now < until
        and at.astimezone(ZONE).date() == now.astimezone(ZONE).date()
        and until.astimezone(ZONE).hour == 22
        and record.get("timePrecision") == "minute"
        and record.get("timezone") == "Europe/Zurich"
    )


def save(conn, payload, now=None):
    now = now or datetime.now(timezone.utc)
    record = validate(payload, now)
    if not current(record, now):
        raise ValueError("DEGIRO-Produktnachweis nicht aktuell")
    # Avoid replacing a stronger or newer original with an older screenshot.
    old = conn.execute(
        "SELECT payload FROM bob_degiro_candidate_proofs WHERE isin=%s FOR UPDATE",
        (record["isin"],)
    ).fetchone()
    if old:
        previous = old[0]
        original = _at(previous.get("observedAt"))
        update = _at(record.get("observedAt"))
        if current(previous, now) and original and update and original > update:
            return {"ok": True, "preserved": True, "evidence": previous,
                    "ordersEnabled": False, "rankingsEligible": False}
        if current(previous, now) and original == update:
            if previous.get("venue") != record["venue"] or previous.get("currency") != record["currency"]:
                raise ValueError("Widersprüchliche DEGIRO-Produktdetails zur selben Originalzeit")
    conn.execute(
        """INSERT INTO bob_degiro_candidate_proofs(isin,payload,observed_at)
        VALUES(%s,%s::jsonb,%s) ON CONFLICT(isin) DO UPDATE SET
        payload=EXCLUDED.payload, observed_at=EXCLUDED.observed_at, updated_at=NOW()""",
        (record["isin"], json.dumps(record, ensure_ascii=False), record["observedAt"])
    )
    # Keep only a bounded set of historical proof identities.
    conn.execute(
        """DELETE FROM bob_degiro_candidate_proofs WHERE isin IN (
          SELECT isin FROM bob_degiro_candidate_proofs
          ORDER BY observed_at DESC, isin ASC OFFSET %s
        )""", (MAX_ITEMS,)
    )
    return {"ok": True, "preserved": False, "evidence": record,
            "ordersEnabled": False, "rankingsEligible": False}


def report(conn, now=None):
    now = now or datetime.now(timezone.utc)
    rows = conn.execute(
        "SELECT payload FROM bob_degiro_candidate_proofs ORDER BY observed_at DESC LIMIT %s",
        (MAX_ITEMS,)
    ).fetchall()
    items=[]
    for (source,) in rows:
        # No unverified older row may regain listing status by polling.
        record = dict(source)
        record["listingConfirmed"] = current(record, now)
        record["executionConfirmed"] = False
        record["isExecutableQuote"] = False
        record["tradeApproved"] = False
        record["rankingsEligible"] = False
        items.append(record)
    # Existing current same-ISIN screenshot identity may be reused without
    # another upload. Expired proofs cannot be silently refreshed by reads.
    from degiro_research_review import proof_reuse_summary
    reusable = proof_reuse_summary(
        [{**row, 'current': row['listingConfirmed']} for row in items],
        [row['isin'] for row in items])
    return {
        "status": "ok", "checkedAt": now.isoformat(),
        "proofReuse": {'currentIdentityCount': reusable['currentIdentityCount'],
                       'furtherIdentityProofNeeded': reusable['furtherIdentityProofNeeded'],
                       'quoteFreshnessExtended': False, 'tradeApproved': False},
        "source": ORIGIN, "items": items,
        "degiroApiConnected": False, "ordersEnabled": False,
        "note": "Aus Nutzerbildern erkannte Anzeigen; keine automatische DEGIRO-Abfrage",
    }
