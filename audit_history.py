"""Read-only, dated access to original decisions. Never manufacture historical signals."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import Counter
import math
import stop_target_audit

ZONE = ZoneInfo('Europe/Zurich')

def bounds(day):
    if not isinstance(day, str):
        raise ValueError('Datum fehlt (JJJJ-MM-TT)')
    parsed = date.fromisoformat(day)
    if parsed.isoformat() != day:
        raise ValueError('Datum muss JJJJ-MM-TT sein')
    start = datetime.combine(parsed, time(), ZONE)
    end = datetime.combine(parsed + timedelta(days=1), time(), ZONE)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

def number(v):
    return isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) and v > 0

def compact(row):
    key, at, p, truths = row
    products = p.get('products') or []
    return dict(id=key, at=at.isoformat(), direction=p.get('direction'), price=p.get('price'),
        priceAt=p.get('priceAt'), barAt=p.get('barAt'), origin=p.get('origin'),
        ruleVersion=p.get('ruleVersion'), build=p.get('build'), reason=p.get('reason'),
        marketEvaluable=p.get('marketEvaluable', False), gateReasons=p.get('gateReasons') or [],
        selection=p.get('selection') or [], products=products, plan=p.get('plan'),
        outcomes=truths or {}, indicators=p.get('indicators'))

def summarize(rows):
    versions = {}; first = {}; counts = Counter(); reasons = Counter()
    for row in rows:
        p = row[2]; rule = p.get('ruleVersion', 'unbekannt'); direction = p.get('direction', 'NEUTRAL')
        counts[direction] += 1
        versions.setdefault(rule, Counter())[direction] += 1
        for reason in p.get('gateReasons') or []:
            reasons[str(reason)[:250]] += 1
        # A recorded direction is not proof of product approval, execution or a fresh candle.
        if direction in ('LONG', 'SHORT'):
            first.setdefault((rule, direction), compact(row))
    return dict(counts=dict(counts), rules={k:dict(v) for k,v in versions.items()},
                firstSignals=list(first.values()), obstacles=reasons.most_common(10))

def report(conn, payload):
    start, end = bounds(payload.get('day'))
    offset = payload.get('offset', 0)
    if isinstance(offset, bool) or not isinstance(offset, int) or not 0 <= offset <= 100000:
        raise ValueError('Ungültige Seitennummer')
    # No writes/harvest here: browsing history must not alter original evidence.
    total = conn.execute('SELECT count(*) FROM bob_decision_audit WHERE recorded_at >= %s AND recorded_at < %s', (start,end)).fetchone()[0]
    # Read only small summary fields for the whole day. Full payloads and outcome
    # lookups belong to the requested page, not every decision on every click.
    headers = conn.execute('''SELECT id,recorded_at,jsonb_build_object(
        'direction',COALESCE(payload->>'direction','NEUTRAL'),
        'ruleVersion',COALESCE(payload->>'ruleVersion','unbekannt'),
        'gateReasons',payload->'gateReasons'),NULL
        FROM bob_decision_audit WHERE recorded_at >= %s AND recorded_at < %s
        ORDER BY recorded_at,id''',(start,end)).fetchall()
    summary = summarize(headers)
    first_ids = [r['id'] for r in summary['firstSignals']]
    full_query = '''SELECT a.id,a.recorded_at,a.payload,
        (SELECT jsonb_object_agg(o.horizon::text,o.truth) FROM bob_decision_outcomes o WHERE o.decision_id=a.id)
        FROM bob_decision_audit a '''
    rows = conn.execute(full_query+'''WHERE a.recorded_at >= %s AND a.recorded_at < %s
        ORDER BY a.recorded_at,a.id LIMIT 100 OFFSET %s''', (start,end,offset)).fetchall()
    if first_ids:
        first_rows = conn.execute(full_query+'WHERE a.id = ANY(%s) ORDER BY a.recorded_at,a.id',
                                  (first_ids,)).fetchall()
        summary['firstSignals'] = [compact(r) for r in first_rows]
    quote_rows = conn.execute('''SELECT date_trunc('hour',quote_at),count(*),min(price),max(price),
        min(quote_at),max(quote_at),count(DISTINCT date_trunc('minute',quote_at))
        FROM bob_spot_observations WHERE stream='gold-api-xau-usd-v1' AND quote_at >= %s AND quote_at < %s
        GROUP BY 1 ORDER BY 1''',(start,end)).fetchall()
    coverage = [dict(hour=h.isoformat(),count=n,low=lo,high=hi,firstAt=f.isoformat(),lastAt=l.isoformat(),minutes=m) for h,n,lo,hi,f,l,m in quote_rows]
    comparisons = conn.execute('''SELECT payload,truth FROM bob_intraday_comparison
        WHERE slot >= %s AND slot < %s ORDER BY slot''',(int(start.timestamp()*1000),int(end.timestamp()*1000))).fetchall()
    return dict(version='audit-day-v1',day=payload['day'],timezone='Europe/Zurich',total=total,
        offset=offset,nextOffset=offset+100 if offset+100 < total else None,truncated=False,
        summary=summary,records=[compact(r) for r in rows],quoteCoverage=coverage,
        stopTargetReview=stop_target_audit.report(conn,start,end),
        comparisons=[dict(observation=p,truth=t) for p,t in comparisons],
        limitations=['Originale Entscheidungen aller damaligen Regelversionen; keine nachträgliche Neuberechnung.',
          'Richtung und Produktfreigabe getrennt prüfen. Aufzeichnung ist kein Nachweis einer Order oder Push-Zustellung.',
          'Stop/Ziel nur beurteilen, wenn damals als Plan gespeichert. Fehlende Pläne bleiben unbekannt.',
          'Gold-Ausgänge nach 15/60/240 Minuten sind keine Produktrendite und kein Stop-/Ziel-Verlaufstest.',
          'Spotarchiv rollierend sieben Tage. Fehlende Kursminuten und fehlende Produktkurse werden nicht ergänzt.'])


