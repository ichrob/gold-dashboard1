"""Project only evidence stored in the same paper case; never join by proximity."""
import math
from datetime import datetime


def positive(v):
    return type(v) in (int,float) and math.isfinite(v) and v > 0


def capture_selection(selection, choice, now):
    # Freeze the bounded ranked candidate universe actually considered for a
    # PAPER entry. The visible top three stay unchanged. Legacy selections
    # without a separate paperCandidates list retain their original top three.
    pool = selection.get('paperCandidates')
    if not isinstance(pool,list):
        pool = selection.get('choices') or []
    rows=[{k:item.get(k) for k in ('isin','direction','score','source','at','indicative','estimated')}
          for item in pool[:12] if isinstance(item,dict)]
    return dict(version=1,capturedAt=now,selectedIsin=choice.get('isin'),rankedShortlist=rows)


def mapping(value):
    return value if isinstance(value, dict) else {}


def source_clock(quote, side):
    value = quote.get(side + 'At')
    if value is None:
        value = quote.get('quoteAt')
    if positive(value):
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
            result = parsed.timestamp() * 1000 if parsed.tzinfo else None
            return result if positive(result) else None
        except (ValueError, OverflowError, OSError):
            pass
    return None


def quote_observed(quote, side, isin, currency, at):
    quote = mapping(quote)
    clock = source_clock(quote, side)
    return (isinstance(isin, str) and bool(isin) and quote.get('isin') == isin
            and currency in ('EUR', 'CHF') and quote.get('currency') == currency
            and isinstance(quote.get('source'), str) and bool(quote['source'].strip())
            and not quote.get('estimated') and not quote.get('indicative')
            and positive(quote.get(side)) and positive(clock) and positive(at)
            and 0 <= at - clock <= 90000)


def review(case):
    case = mapping(case)
    checklist = mapping(case.get('entryChecklist'))
    analysis = mapping(case.get('analysis'))
    quote = mapping(case.get('entryQuote'))
    product = mapping(case.get('product'))
    raw_events = case.get('events')
    events = raw_events if isinstance(raw_events, list) else []
    source = analysis.get('dataAt')
    start = case.get('startedAt')
    source_ok = positive(source) and positive(start) and 0 <= start-source <= 60000
    isin, currency = product.get('isin'), quote.get('currency')
    selected = quote_observed(quote, 'ask', isin, currency, start)
    exits = [e for e in events if isinstance(e, dict) and e.get('kind') != 'entry'
             and positive(e.get('units'))]
    excluded = case.get('status') == 'inconclusive' or case.get('performanceEligible') is False
    end, quantity = case.get('closedAt'), case.get('quantity')
    # A later settlement or unrelated quote cannot certify the original exit.
    quoted = (bool(events) and all(isinstance(e, dict) for e in events)
              and bool(exits) and type(quantity) is int and quantity > 0
              and sum(e['units'] for e in exits) == quantity
              and positive(start) and positive(end) and end >= start
              and case.get('remainingUnits') == 0 and case.get('pendingUnits') == 0
              and not any(e.get('kind') in ('data-gap', 'deferred-sale',
                  'ko-barrier-crossed-observed', 'product-terminated', 'knockout-confirmed')
                  for e in events)
              and all(type(e['units']) is int and e['units'] > 0
                  and positive(e.get('recordedAt')) and start <= e['recordedAt'] <= end
                  and quote_observed(e.get('quote'), 'bid', isin, currency, e['recordedAt'])
                  for e in exits))
    selection = mapping(case.get('selectionEvidence'))
    ranked = selection.get('rankedShortlist')
    ranking_ok = (isinstance(ranked, list) and isinstance(isin, str) and bool(isin)
                  and selection.get('selectedIsin') == isin
                  and any(isinstance(r, dict) and r.get('isin') == isin for r in ranked)
                  and selection.get('capturedAt') == start)
    stages=[dict(label='Original-Marktkurs',observed=source_ok),
        dict(label='Einstiegsentscheidung',observed=checklist.get('decision')=='entry' and bool(checklist.get('ruleVersion'))),
        dict(label='Ausgewähltes Produkt und Einstiegskurs',observed=selected),
        dict(label='Gespeicherte Ranglisten-Auswahl',observed=ranking_ok),
        dict(label='Simulierter Ausstieg mit Kursbeleg',observed=quoted and case.get('status')=='closed' and not excluded)]
    return dict(version=2,sourceAt=source if source_ok else None,startedAt=start,
        stages=stages,complete=all(s['observed'] for s in stages),performanceExcluded=excluded,
        pushLinkVerified=False,brokerExecutionVerified=False,
        note='Nachweise aus demselben Simulationsfall. Produktidentität, Währung, Originalkurszeiten und vollständige Ausstiegsstückzahlen werden geprüft. Fehlende Historie wird nicht ergänzt; keine Broker-Ausführung oder bestätigte Nettorendite.')
