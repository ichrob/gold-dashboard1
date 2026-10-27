"""Read-only connection inventory from existing bounded observations."""
from bob_operations import fresh, stamp


def snapshot(report, now):
    a = report.get('areas') or {}
    runtime = a.get('runtime') or {}
    snap = runtime.get('snaptradePersonal') or {}
    sim = a.get('simulationAndPush') or {}
    watch = sim.get('runtimeWatchdog') or {}
    deploy = watch.get('deployment') or {}
    rows = []

    def add(key, label, at, available, current, note, seconds=300):
        recent = fresh(at, now, seconds)
        state = 'current' if available and current and recent else 'stale-or-partial' if available else 'unknown'
        rows.append(dict(id=key, label=label, state=state,
            lastObservedAt=at if stamp(at) is not None else None,
            lastSuccessAt=at if available and recent else None,
            dataFresh=bool(current and recent), note=note))

    add('bob-reader', 'ChatGPT → Bob', report.get('observedAt'), True, True,
        'Privater Diagnoseabruf; nur lesend. Kein Nachweis aller Funktionen.')
    add('snaptrade', 'SnapTrade → DEGIRO', snap.get('checkedAt'), snap.get('code') == 'READ_OK', snap.get('fresh') is True,
        'Depot-Lesezugriff und Datenfrische getrennt. Keine ausführbaren Brokerkurse oder Orders.', 1800)
    products = a.get('products') or {}
    add('products', 'Produktquellen', products.get('lastCheckedAt'), products.get('status') == 'ok',
        products.get('incomplete') == 0 and products.get('total', 0) > 0,
        'Abrufstatus ist keine Handelsfreigabe. Original → Ersatzquelle → gekennzeichnete Berechnung.')
    research = a.get('research') or {}
    add('research', 'MCO-Recherche', research.get('checkedAt'), research.get('successfulFeeds', 0) > 0,
        research.get('fresh') is True and not research.get('accessFallback'),
        'Fehlende Untertitel, Zugriffsrechte und Veröffentlichungsdaten bleiben offen.', 1800)
    add('deployment', 'GitHub → Render', deploy.get('checkedAt'), deploy.get('state') == 'verified',
        deploy.get('fresh') is True, 'Bestätigter Versionsabgleich; kein Nachweis einer späteren Veröffentlichung.', 2400)
    index = a.get('problems') or {}
    add('issues', 'GitHub-Problemabgleich', index.get('checkedAt'), index.get('status') == 'ok',
        index.get('status') == 'ok', 'Codekorrektur, Veröffentlichung und bestätigte Erholung bleiben getrennte Schritte.', 1200)
    deliveries = (a.get('pushDeliveries') or {}).get('records') or []
    clocks = [r.get('browserShowAt') for r in deliveries if r.get('browserShowReceipt') == 'confirmed']
    at = max(clocks, key=lambda v: stamp(v) or 0) if clocks else None
    add('push', 'Bob → Handy-Push', at, bool(at), False,
        'Browser-Rückmeldung ist kein Nachweis einer sichtbaren Android-Meldung. Ohne Signal ist kein neuer Push nötig.', 86400)
    for key, label in [('android','Bob Handy'), ('mail','Mail-/PDF-Import')]:
        add(key, label, None, False, False, 'Kein aktueller Ende-zu-Ende-Nachweis in dieser Diagnose vorhanden.')
    return dict(items=rows, readOnly=True, realOrders=False,
        retryPolicy='Bestehende begrenzte Wiederholungen und Anbieter-Wartezeiten; diese Übersicht startet keine zusätzlichen Abrufe.',
        repairPolicy='Erkannt → Korrektur → Tests → veröffentlicht → unabhängige Gesundheitsprüfung. Erst bestätigte Erholung gilt als behoben.')
