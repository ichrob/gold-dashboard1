"""Server-side selection verification and durable notification transitions."""
import json
import re
import subprocess
import evaluator_runtime
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def evaluate(payload):
    process = evaluator_runtime.run(['node', str(Path(__file__).with_name('selection_push_evaluator.js'))],
                             input=json.dumps(payload), text=True, capture_output=True, timeout=8, check=True)
    return json.loads(process.stdout)


def transition(previous, checked, now=None):
    now = int(time.time()*1000) if now is None else now
    previous = previous or {}
    products = checked.get('products', []) if checked.get('expiresAt', 0) > now else []
    signature = '|'.join(sorted(':'.join((p['isin'], p['direction'], p['scope'])) for p in products))
    state = {**previous, 'signature': signature, 'products': products,
             'expiresAt': checked.get('expiresAt', now), 'notified': False}
    stamp = datetime.fromtimestamp(now/1000, ZoneInfo('Europe/Zurich')).strftime('%H:%M:%S')
    if products:
        if signature == previous.get('signature') and previous.get('notified'):
            state['notified'] = True
            return state, None
        if signature == previous.get('lastSignature') and now-previous.get('lastSentAt', 0) < 300000:
            return state, None
        state.update(notified=True, lastSignature=signature, lastSentAt=now)
        labels = '; '.join(p['isin']+' · '+p.get('name', '')+' · '+p['direction']+' · '+('berechneter Kurs' if p.get('estimated') else 'Produktkurs')+' · Kurszeit: '+str(p.get('quoteAt') or 'unbekannt') for p in products)
        reason = next((str(r) for p in products for r in p.get('reasons', []) if r), 'Markt- und Produktpflichtprüfungen bestanden')
        valid_until = datetime.fromtimestamp(checked['expiresAt']/1000, ZoneInfo('Europe/Zurich')).strftime('%H:%M:%S')
        body = 'Neue Produktauswahl prüfen. Grund: ' + reason[:220] + '. ' + labels + '. Prüfung ' + stamp + ' Uhr; spätestens bis '+valid_until+' Uhr bestätigt. Aktuellen Status in Bob prüfen.'
        removed = [p['isin'] for p in previous.get('products', []) if p['isin'] not in {x['isin'] for x in products}]
        if previous.get('notified') and removed:
            body += ' Nicht mehr freigegeben: ' + ', '.join(removed) + '.'
        title = 'PRODUKTFREIGABE · Bob'
        kind = 'product-approved'
    elif previous.get('notified'):
        labels = ', '.join(p['isin'] for p in previous.get('products', []))
        reasons = checked.get('reasons') or ['Aktuelle Bestätigung abgelaufen']
        market_issue = bool(checked.get('gateReasons')) or any(
            re.search(r'Marktsignal|Marktrichtung|Momentum|MTF|Marktprüfung', str(r), re.I)
            for r in reasons)
        title = ('Marktlage geändert – Einstieg erneut prüfen' if market_issue
                 else 'Produktprüfung – Klärung erforderlich')
        kind = 'product-withdrawn'
        issues = {p.get('isin'): p.get('reasons') or [] for p in checked.get('productIssues', [])}
        details = []
        for product in previous.get('products', []):
            own_reasons = issues.get(product['isin']) or reasons
            details.append(product['isin'] + ': ' + '; '.join(str(r) for r in own_reasons))
        action = ('Aktuelle Marktanalyse in Bob prüfen.' if market_issue else
                  'Betroffene Angaben auf der Emittentenseite prüfen; Kurs- oder Datennachweis '
                  'per Screenshot oder automatischem Abruf aktualisieren.')
        body = (' | '.join(details) + '. ' + action
                + ' Produkt bleibt gespeichert. Einstiegsfreigabe pausiert bis zur erneuten '
                'Markt- und Produktprüfung. Kein Verkaufssignal. Prüfung ' + stamp + ' Uhr.')

    else:
        return state, None
    return state, {'title': title, 'body': body[:1000], 'tag': 'bob-product-selection',
                   'data': {'kind': kind, 'url': '/', 'checkedAt': now,
                            'expiresAt': checked.get('expiresAt', now) if products else now+300000}}
