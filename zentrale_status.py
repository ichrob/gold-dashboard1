"""Bounded hub display projections of existing reports; no I/O or control actions."""
from datetime import datetime
import math


def obj(value):
    return value if isinstance(value, dict) else {}


def rows(value, limit):
    return [v for v in value[:limit] if isinstance(v, dict)] if isinstance(value, list) else []


def clock(value):
    try:
        if isinstance(value, str):
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.timestamp() if dt.tzinfo else None
        if type(value) in (int, float) and math.isfinite(value) and value > 0:
            return value / 1000 if value > 1e11 else value
    except (ValueError, OverflowError):
        pass
    return None


def number(value, maximum=1000):
    return value if type(value) is int and 0 <= value <= maximum else None


STEPS = {
    'COMPLETE': ('Lesedaten erfasst', 'Produktnachweise bleiben separat zu prüfen.'),
    'PARTIAL': ('Teilweise gelesen', 'Fehlende Felder in den Produktnachweisen prüfen.'),
    'SEARCH_MISSING': ('Suche nicht gefunden', 'Letzte Lesediagnose im Bereich Probleme prüfen.'),
    'SEARCH_NO_PROGRESS': ('Suche kommt nicht weiter', 'Letzte Lesediagnose im Bereich Probleme prüfen.'),
    'SCREEN_LOCKED': ('Bildschirm gesperrt', 'Für einen neuen Leselauf muss das Handy entsperrt sein.'),
    'READ_TIMEOUT': ('Lesen hat zu lange gedauert', 'Fehler des letzten Leselaufs prüfen.'),
    'RETURN_FAILED': ('Rückkehr zur Liste fehlgeschlagen', 'Rücknavigation im Fehlerbericht prüfen.'),
    'RETURN_NOT_CONFIRMED': ('Rückkehr zur Liste nicht bestätigt', 'Rücknavigation im Fehlerbericht prüfen.'),
    'LIST_IMAGES_DELIVERED': ('Listenbilder übertragen', 'Importstatus darunter prüfen.'),
    'LIST_UPLOAD_FAILED': ('Bilder nicht übertragen', 'Verbindung und Importstatus prüfen.'),
    'USER_STOP': ('Vom Nutzer gestoppt', 'Kein neuer Start durch diese Anzeige.'),
    'STOPPED': ('Gestoppt', 'Kein neuer Start durch diese Anzeige.'),
    'NONE': ('Noch kein Leseschritt gemeldet', 'Auf eine echte Handy-Meldung warten.'),
}
IMPORTS = {'waiting-memory':'Wartet auf Arbeitsspeicher', 'fetching':'Übertragung läuft',
    'images-ready':'Bilder bereit', 'reading':'Bilder werden gelesen', 'stored':'Ergebnis gespeichert',
    'synced':'Liste übernommen', 'fetch-failed':'Übertragung fehlgeschlagen',
    'read-failed':'Bilderkennung fehlgeschlagen', 'store-failed':'Speichern fehlgeschlagen',
    'superseded':'Durch neuere Liste ersetzt'}


def phone_view(areas, now):
    telemetry = obj(areas.get('androidTelemetry'))
    devices = [d for d in rows(telemetry.get('devices'), 20)
               if d.get('revoked') is False and (clock(d.get('expiresAt')) or 0) > now]
    devices.sort(key=lambda d: clock(d.get('receivedAt')) or 0, reverse=True)
    device = devices[0] if devices else {}
    report = obj(device.get('report'))
    received = clock(device.get('receivedAt'))
    observed = clock(report.get('observedAt'))
    recent = all(t is not None and 0 <= now-t <= 120 for t in (received, observed))
    state = ('running' if report.get('running') is True else
             'waiting' if report.get('pendingRun') is True else
             'blocked' if report.get('serviceEnabled') is False or report.get('serviceConnectedInProcess') is False else
             'idle') if recent else 'unknown'
    step, advice = STEPS.get(report.get('lastCode') if isinstance(report.get('lastCode'), str) else None, ('Leseschritt nicht eingeordnet', 'Letzten Handy-Bericht im Bereich Probleme prüfen.'))
    runs = rows(obj(areas.get('androidReader')).get('runs'), 5)
    runs.sort(key=lambda r: clock(r.get('receivedAt')) or 0, reverse=True)
    run = runs[0] if runs else {}
    results = rows(run.get('results'), 100)
    requested = number(run.get('requested'),100)
    complete = sum(r.get('code') == 'COMPLETE' for r in results) if runs else None
    partial = sum(r.get('code') == 'PARTIAL' for r in results) if runs else None
    if requested is None or len(results) > requested:
        requested = complete = partial = None
    imports = rows(telemetry.get('listImports'), 5)
    imports.sort(key=lambda r: clock(r.get('uploadedAt')) or 0, reverse=True)
    latest = imports[0] if imports else {}
    receipt = obj(latest.get('import'))
    successes = [obj(i.get('import')) for i in imports if obj(i.get('import')).get('stage') == 'synced']
    success_times = [clock(i.get('at')) for i in successes]
    last_success = max((t for t in success_times if t is not None and 0 < t <= now), default=None)
    attachments = obj(latest.get('recognitionAttachments'))
    return dict(state=state, appVersion=number(report.get('appVersionCode'),2100000000),
        observedAt=observed, receivedAt=received, multipleDevices=len(devices)>1,
        step=step, nextAction=advice, stepAt=clock(report.get('lastEventAt')),
        runAt=clock(run.get('receivedAt')), requested=requested, complete=complete, partial=partial,
        importState=IMPORTS.get(receipt.get('stage') if isinstance(receipt.get('stage'), str) else None,'Kein Importstatus nachgewiesen'),
        importAt=clock(receipt.get('at')), importedCount=number(receipt.get('count'),10),
        lastSuccessfulImportAt=last_success,
        localOcrImages=number(attachments.get('localOcrImages'),10),
        appTextImages=number(attachments.get('appTextImages'),10),
        imageOnly=number(attachments.get('imageOnly'),10),
        recognitionScope='attachments-not-processing-proof', readOnly=True)


def priority(case):
    code = str(case.get('code','')).lower()
    if any(word in code for word in ('market','source','candle','push','database','worker','trade')):
        return 0
    if case.get('state') == 'needs-user': return 1
    if case.get('state') == 'blocked': return 2
    if code.startswith('product-'): return 3
    return 4
