"""Readiness for a new handset read; never dispatch, quote approval or orders."""
from datetime import datetime
import math


def clock(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp()*1000 if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def assess(item, now):
    """A newly calculated scenario does not refresh its original screen quote.

    The model reference is a minimum capture boundary, not a broker signal or
    quote clock. Even a recent post-reference capture needs independent source
    time verification. This report deliberately cannot approve an entry.
    """
    result = dict(version=1, checkedAt=now, readRequired=False,
                  readDispatched=False, entryApproved=False,
                  brokerExecutionVerified=False, realOrders=False)
    def blocked(code, reason, read=False):
        return dict(result, code=code, reason=reason, readRequired=read)
    if type(now) not in (int, float) or not math.isfinite(now):
        raise ValueError('Invalid assessment clock')
    if item.get('entrySuitable') is not True:
        return blocked('WAITING_FOR_SIGNAL', 'Kein bestätigter Einstieg; keine automatische Nachlesung ausgelöst.')
    if item.get('available') is not True or item.get('reasons'):
        return blocked('COMPARISON_BLOCKED', 'Produktvergleich noch gesperrt; Sperrgründe zuerst prüfen.')
    reference = clock(item.get('modelReferenceAt'))
    if reference is None or not 0 <= now-reference <= 90000:
        return blocked('MODEL_REFERENCE_NOT_FRESH', 'Aktuelle datierte Modellreferenz fehlt.')
    captured = clock(item.get('observedAt'))
    if captured is None or not reference <= captured <= now or now-captured > 90000:
        return blocked('NEW_DEGIRO_READ_REQUIRED',
                       'Neue DEGIRO-Nachlesung erforderlich: vorhandene Erfassung fehlt, ist veraltet oder liegt vor der Modellreferenz.', True)
    # The existing importer explicitly leaves sourceTime null and the screen
    # timezone/execution unverified. Never substitute capture time for them.
    return blocked('BROKER_SOURCE_TIME_UNVERIFIED',
                   'Neue Erfassung vorhanden; zugehörige DEGIRO-Kurszeit und Ausführbarkeit weiterhin unbestätigt.')
