"""Evidence-based post-trade lessons; no order execution or automatic rule tuning."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import math
import trade_risk_review


def window(snapshot):
    purchase = snapshot.get('purchase') or {}
    sale = snapshot.get('exitReceipt') or {}
    settlement = snapshot.get('settlement') or {}
    assumed = False
    def clock(explicit, local):
        nonlocal assumed
        if explicit:
            try:
                value = datetime.fromisoformat(explicit.replace('Z', '+00:00'))
                if value.tzinfo: return value
            except (ValueError, TypeError): pass
        if local:
            try:
                value = datetime.strptime(local, '%d.%m.%Y %H:%M:%S')
                assumed = True
                return value.replace(tzinfo=ZoneInfo('Europe/Zurich'))
            except (ValueError, TypeError): pass
        return None
    start = clock(purchase.get('at') or settlement.get('purchasedAt'), purchase.get('executedLocal') or settlement.get('purchaseExecutedLocal'))
    end = clock(sale.get('executedAt') or settlement.get('soldAt'), sale.get('executedLocal') or settlement.get('saleExecutedLocal'))
    if not start or not end or end <= start: return None
    return start, end, assumed


def review(conn, snapshot):
    out = trade_risk_review.evaluation(snapshot)
    out['lessons'] = []
    out['findings'] = []
    out['learning'] = dict(state='review-only', automaticRuleChange=False,
        independentTestRequired=True, productNetValidated=False,
        note='Trade-Befund ist ein Verbesserungsvorschlag. Erst spätere unabhängige Vergleiche mit Produktkosten können einen Vorteil bestätigen.')
    if out['realizedNetCHF'] is None and out['realizedNetProduct'] is None:
        out['lessons'].append('Kauf- und Verkaufsabrechnung vervollständigen; kein Gewinntraining mit offenen Kosten.')
    bounds = window(snapshot)
    if not bounds:
        out['lessons'].append('Ausführungszeitraum nicht eindeutig: Verlauf noch nicht dem gehaltenen Trade zugeordnet.')
        return out
    start, end, assumed = bounds
    out['holdingMinutes'] = round((end-start).total_seconds()/60, 1)
    out['windowNote'] = ('Beleg-Ortszeiten; Europe/Zurich für Verlaufszuordnung angenommen, keine bestätigte Broker-Zeitzone.' if assumed else 'Bestätigte Ausführungszeiten mit Zeitzone.')
    tid = snapshot['tradeId']
    row = conn.execute('''SELECT count(*),min(price),max(price),min(spot_at),max(spot_at)
        FROM bob_real_trade_price_curve WHERE trade_id=%s AND spot_at>=%s AND spot_at<=%s
        AND currency=%s''', (tid,start,end,(snapshot.get('product') or {}).get('currency','EUR'))).fetchone()
    if row and row[0]:
        count, low, high, first, last = row
        entry = (snapshot.get('product') or {}).get('entry')
        out['modelObservations'] = count
        out['modelOnly'] = True
        if type(entry) in (int,float) and math.isfinite(entry) and entry>0:
            out['modelMfePct'] = round(max(0,(high/entry-1)*100),2)
            out['modelMaePct'] = round(min(0,(low/entry-1)*100),2)
        out['observedFrom'] = first.isoformat()
        out['observedUntil'] = last.isoformat()
        out['unobservedStartMinutes'] = round(max(0,(first-start).total_seconds()/60),1)
        if out['unobservedStartMinutes']>1:
            out['lessons'].append('Überwachung begann nach dem Kauf: frühe Kursbewegungen fehlen; künftig direkt beim Kauf starten.')
    else:
        out['lessons'].append('Keine gespeicherten Produktmodellkurse im Ausführungszeitraum; kein nachträglicher optimaler Ausstieg belegbar.')
    rows = conn.execute('''SELECT recorded_at,payload FROM bob_real_trade_events
        WHERE trade_id=%s AND kind='observation' AND recorded_at>=%s AND recorded_at<=%s
        ORDER BY recorded_at LIMIT 20000''',(tid,start,end)).fetchall()
    direction = snapshot.get('dir')
    opposite = 'SHORT' if direction=='LONG' else 'LONG'
    adverse = sum(p.get('ready') is True and p.get('priceFresh') is True and p.get('direction')==opposite for _,p in rows)
    recommendations = sum(len(p.get('recommendations') or []) for _,p in rows)
    stops = [(at,p['planAfter']['stop']) for at,p in rows
             if isinstance(p.get('planAfter'),dict) and type(p['planAfter'].get('stop')) in (int,float)
             and math.isfinite(p['planAfter']['stop'])]
    loosened = sum((b[1]<a[1] if direction=='LONG' else b[1]>a[1]) for a,b in zip(stops,stops[1:]))
    out['trace'] = dict(observations=len(rows),recommendations=recommendations,
        adverseObservations=adverse,stopObservations=len(stops),stopLoosenings=loosened,
        truncated=len(rows)==20000,executionConfirmed=False)
    if adverse:
        out['lessons'].append('Bestätigte Gegenrichtung protokolliert: Reaktion der Stopp-Vorschläge in späteren Vergleichsfällen prüfen.')
    if loosened:
        out['lessons'].append('Gelockerte protokollierte Stopps gefunden: Planwechsel prüfen; keine Broker-Ausführung daraus ableiten.')
    if not stops:
        out['lessons'].append('Kein auswertbarer Stopp-Verlauf im gehaltenen Zeitraum gespeichert.')
    out['findings'] = findings(rows, start, end, direction, out)
    if not out['lessons']:
        out['lessons'].append('Abrechnung und Verlauf vorhanden; dieser Einzeltrade belegt noch keine bessere Handelsregel.')
    return out


def findings(rows, start, end, direction, result):
    """Evidence describes observations, never asserts a causal loss attribution."""
    out = []
    def add(code, status, text, at=None):
        out.append(dict(code=code,status=status,text=text,
            evidenceAt=at.isoformat() if at else None,causalLossProven=False))
    # A post-purchase signal cannot prove what was known at the purchase.
    entry = [(at,p) for at,p in rows if at == start]
    if entry:
        at,p = entry[0]
        gate = p.get('entryTimingGate') or {}
        if gate.get('allowed') is False:
            add('entry-timing','observed','Einstiegsfilter war zum Kaufzeitpunkt gesperrt: '+str(gate.get('reason') or 'Timing nicht bestätigt'),at)
        else:
            add('entry-timing','unknown','Verspäteter Einstieg ist aus diesem Protokoll nicht belegt.')
        if p.get('ready') is False or p.get('priceFresh') is False or p.get('direction') != direction:
            add('entry-signal','observed','Zum Kaufzeitpunkt fehlt im Protokoll ein frisches freigegebenes Signal in Handelsrichtung.',at)
        else:
            add('entry-signal','observed','Frisches Signal in Handelsrichtung zum Kaufzeitpunkt protokolliert.',at)
    else:
        add('entry-timing','unknown','Einstiegstiming und Signalstärke beim Kauf nicht belegbar: kein zeitgleicher Entscheidungsdatensatz.')
    if result.get('unobservedStartMinutes',0)>1:
        add('monitoring-gap','observed','Die ersten '+str(result['unobservedStartMinutes'])+' Minuten nach Kauf fehlen im Modellverlauf. Das beweist keinen verspäteten Einstieg.')
    opposite = 'SHORT' if direction=='LONG' else 'LONG'
    adverse = [(at,p) for at,p in rows if p.get('ready') is True and p.get('priceFresh') is True and p.get('direction')==opposite]
    if adverse:
        add('opposite-signal','observed','Erstes frisches freigegebenes Gegensignal während der Haltedauer. Stopp-Reaktion als separate Testhypothese prüfen.',adverse[0][0])
    last = None
    for at,p in rows:
        stop = (p.get('planAfter') or {}).get('stop')
        if type(stop) not in (int,float) or not math.isfinite(stop): continue
        if last is not None and (stop<last if direction=='LONG' else stop>last):
            add('stop-loosening','observed','Protokollierter Gold-Stopp wurde von '+str(last)+' auf '+str(stop)+' gelockert. Keine bestätigte Broker-Änderung.',at)
            break
        last=stop
    add('stop-outcome','unknown','Ob ein anderer Stopp den Nettoverlust vermindert hätte, benötigt einen vorab festgelegten Vergleich einschließlich Kosten und Ausführungsnachweis.')
    return out
