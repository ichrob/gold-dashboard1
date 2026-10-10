"""Informational US exchange holiday watch; not a gold market closure oracle.

CME Globex holiday schedules vary by contract and are published/updated close
to each event. Never turn this calendar into a fresh-quote or trade signal.
Source: https://www.cmegroup.com/trading-hours.html
Dates below are CME Globex holiday observation periods, not all-day halts.
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# CME Globex 2026 general holiday trading schedule; all product hours vary.
CME_2026 = {
    "2026-01-01": "Neujahr",
    "2026-01-19": "Martin Luther King Jr. Day",
    "2026-02-16": "Presidents Day",
    "2026-04-03": "Karfreitag (USA)",
    "2026-05-25": "Memorial Day",
    "2026-06-19": "Juneteenth",
    "2026-07-03": "US-Unabhängigkeitstag (beobachtet)",
    "2026-09-07": "Labor Day",
    "2026-11-26": "Thanksgiving",
    "2026-11-27": "Thanksgiving-Folgehandel",
    "2026-12-24": "Weihnachts-Vorabend",
    "2026-12-25": "Weihnachten",
    "2026-12-31": "Silvester / Neujahrsübergang",
}
# EBS Spot FX & Precious Metals and related venues can additionally differ.
VENUE_NOTES_2026 = {
    "2026-10-12": "Columbus Day (USA): einzelne Spot-/CME-Handelsplätze mit Sonderzeiten",
}


def advisory(now=None):
    """A caution for source-specific hours, not proof of closure.

    The reference calendar is 2026 only; unknown dates do not become holidays.
    """
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Timezone required for holiday schedule")
    local = now.astimezone(ZoneInfo("Europe/Zurich"))
    key = local.date().isoformat()
    reason = CME_2026.get(key) or VENUE_NOTES_2026.get(key)
    if not reason:
        return None
    return {
        "date": key,
        "name": reason,
        "note": "Sonderhandelszeiten möglich · Gold-Spot, Futures und Produktanbieter getrennt prüfen. Kein automatischer Marktstopp.",
        "confirmedClosed": False,
        "source": "CME Group · Holiday and Trading Hours",
        "sourceUrl": "https://www.cmegroup.com/trading-hours.html",
    }
