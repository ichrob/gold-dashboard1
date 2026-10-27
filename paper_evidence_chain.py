"""Project only evidence stored in the same paper case; never join by proximity."""
import math


def positive(v):
    return type(v) in (int,float) and math.isfinite(v) and v > 0


def capture_selection(selection, choice, now):
    # Freeze exactly the ranked shortlist used by this entry; never all raw input.
    rows=[{k:item.get(k) for k in ('isin','direction','score','source','at','indicative','estimated')}
          for item in (selection.get('choices') or [])[:3] if isinstance(item,dict)]
    return dict(version=1,capturedAt=now,selectedIsin=choice.get('isin'),rankedShortlist=rows)


def review(case):
    checklist=case.get('entryChecklist') or {}
    analysis=case.get('analysis') or {}
    quote=case.get('entryQuote') or {}
    product=case.get('product') or {}
    events=case.get('events') or []
    source=analysis.get('dataAt')
    start=case.get('startedAt')
    source_ok=positive(source) and positive(start) and 0<=start-source<=60000
    selected=bool(product.get('isin')) and product.get('isin')==quote.get('isin')
    exits=[e for e in events if positive(e.get('units')) and e.get('kind')!='entry']
    quoted=bool(exits) and all(positive((e.get('quote') or {}).get('bid')) for e in exits)
    excluded=case.get('status')=='inconclusive' or case.get('performanceEligible') is False
    selection=case.get('selectionEvidence') or {}
    ranked=(selection.get('rankedShortlist') or [])
    ranking_ok=selection.get('selectedIsin')==product.get('isin') and any(r.get('isin')==product.get('isin') for r in ranked) and selection.get('capturedAt')==start
    stages=[dict(label='Original-Marktkurs',observed=source_ok),
        dict(label='Einstiegsentscheidung',observed=checklist.get('decision')=='entry' and bool(checklist.get('ruleVersion'))),
        dict(label='Ausgewähltes Produkt und Einstiegskurs',observed=selected and positive(quote.get('ask'))),
        dict(label='Gespeicherte Ranglisten-Auswahl',observed=ranking_ok),
        dict(label='Simulierter Ausstieg mit Kursbeleg',observed=quoted and case.get('status')=='closed' and not case.get('pendingUnits') and not excluded)]
    return dict(version=1,sourceAt=source if source_ok else None,startedAt=start,
        stages=stages,complete=all(s['observed'] for s in stages),performanceExcluded=excluded,
        pushLinkVerified=False,brokerExecutionVerified=False,
        note='Nachweise aus demselben Simulationsfall. Originale Ranglisten-Auswahl wird ab Einführung gespeichert. Push-Zuordnung separat, kein Bestandteil eines simulierten Ausstiegs; fehlende Historie wird nicht ergänzt.')
