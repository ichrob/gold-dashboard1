"""SG regular quoting *advisory* in Europe/Zurich, never an execution status.

Official SG source: https://zertifikate.societegenerale.ch/aktuelles/produkte-handel/handelszeiten
Weekdays 08:00-22:00 are ordinary quote-indication hours, subject to
market conditions and exceptional holidays. This advisory cannot mark any
product quote fresh or traded and applies only to positively identified SG
product names; all other issuer products remain unaffected.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

_ZURICH = ZoneInfo("Europe/Zurich")
_TERMS_ONLY = frozenset(("KO-Schwelle", "Basispreis", "Bv", "Währung"))
_URL = "https://zertifikate.societegenerale.ch/aktuelles/produkte-handel/handelszeiten"


def advisory(now):
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    local = now.astimezone(_ZURICH)
    routine = local.weekday() < 5 and time(8) <= local.time() < time(22)
    next_date = local.date() if local.weekday() < 5 and local.time() < time(8) else local.date() + timedelta(days=1)
    while next_date.weekday() >= 5:
        next_date += timedelta(days=1)
    next_at = datetime.combine(next_date, time(8), tzinfo=_ZURICH)
    return dict(
        scheduledPause=not routine,
        localTime=local.isoformat(),
        routineHours="Mo–Fr 08:00–22:00 Europe/Zurich",
        nextRoutineCheckAt=next_at.isoformat() if not routine else None,
        source="Société Générale · reguläre Emittenten-Kursstellung",
        sourceUrl=_URL,
        holidayVerified=False, marketOpenConfirmed=False, quoteFresh=False,
        message=("Außerhalb der regulären SG-Kursstellung: letzte Originalkurse nur historisch, "
                 "Emittenten-/Ersatzquellen separat weiter prüfen." if not routine else
                 "Innerhalb der regulären SG-Kursstellungszeit; aktuelle Kurse nur mit "
                 "Originalzeit und eigenem Quellnachweis."),
    )


def is_sg_gold(item, product):
    """A name on the same ISIN's imported list is a narrow scheduling hint."""
    for entry in (item, product):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name.strip().lower().startswith("sg gold "):
            return True
    return False


def filter_handset_fields(fields, now, item, product):
    """After-hours request only static missing SG terms on the phone.

    Never erase historical values or invent a quote. Existing issuer/backup
    refreshes remain independent. Unknown issuers are not assumed closed.
    """
    if advisory(now)["scheduledPause"] and is_sg_gold(item, product):
        return [name for name in fields if name in _TERMS_ONLY]
    return list(fields)
