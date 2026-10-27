"""Read-only cost sensitivity on settled product cases, never ledger mutations."""
import math

VERSION = 'paper-cost-sensitivity-v1'
SCENARIOS = (
    dict(name='Beispiel', feeEurPerOrder=1., slippageBpsPerSide=5., extraHoldingBpsPerDay=0.),
    dict(name='Belastungstest', feeEurPerOrder=2., slippageBpsPerSide=15., extraHoldingBpsPerDay=5.),
)


def finite(v):
    return type(v) in (int, float) and math.isfinite(v)


def evaluate(c, assumption):
    if (c.get('demonstration') or c.get('status') != 'closed' or c.get('productReturnKnown') is not True
            or c.get('pendingUnits') != 0 or c.get('remainingUnits') != 0
            or not finite(c.get('allocated')) or c['allocated'] <= 0
            or not finite(c.get('cashReleased')) or c['cashReleased'] < 0):
        return None
    events = c.get('events') or []
    sells = [e for e in events if finite(e.get('units')) and e['units'] > 0
             and isinstance(e.get('quote'), dict) and finite(e['quote'].get('bid')) and e['quote']['bid'] > 0]
    if not sells or sum(e['units'] for e in sells) != c.get('quantity'):
        return None
    start = c.get('startedAt'); end = c.get('settledAt') or c.get('closedAt')
    if not finite(start) or not finite(end) or end < start:
        return None
    if any(not finite(assumption.get(k)) or assumption[k] < 0 for k in
           ('feeEurPerOrder', 'slippageBpsPerSide', 'extraHoldingBpsPerDay')):
        raise ValueError('Ungültige Kostenannahmen')
    fees = (1+len(sells))*assumption['feeEurPerOrder']
    slippage = (c['allocated']+c['cashReleased'])*assumption['slippageBpsPerSide']/10000
    # Conservative full-entry-capital holding stress, also after partial exits.
    holding = c['allocated']*(end-start)/86400000*assumption['extraHoldingBpsPerDay']/10000
    gross = c['cashReleased']-c['allocated']
    return dict(grossEur=gross, modelNetEur=gross-fees-slippage-holding,
                feesEur=fees, slippageEur=slippage, extraHoldingEur=holding,
                orders=1+len(sells))


def report(cases):
    scenarios = []
    for assumption in SCENARIOS:
        values = [v for c in cases if (v := evaluate(c, assumption)) is not None]
        wins = [v['modelNetEur'] for v in values if v['modelNetEur'] > 0]
        losses = [v['modelNetEur'] for v in values if v['modelNetEur'] < 0]
        scenarios.append(dict(**assumption, evaluated=len(values), excluded=len(cases)-len(values),
            grossEur=sum(v['grossEur'] for v in values) if values else None,
            modelNetEur=sum(v['modelNetEur'] for v in values) if values else None,
            averageWinEur=sum(wins)/len(wins) if wins else None,
            averageLossEur=sum(losses)/len(losses) if losses else None,
            feesEur=sum(v['feesEur'] for v in values) if values else None,
            slippageEur=sum(v['slippageEur'] for v in values) if values else None,
            extraHoldingEur=sum(v['extraHoldingEur'] for v in values) if values else None))
    return dict(version=VERSION, scenarios=scenarios, netReturnKnown=False,
        note='Nur abgeschlossene, vollständig bepreiste Fälle des gewählten Tages (maximal 100). '
             'Brief-Einstieg/Geld-Ausstieg enthalten den beobachteten Spread bereits. '
             'Gebühren und schlechtere Ausführung sind Beispielannahmen, keine DEGIRO-Tarife oder gemessene Slippage. '
             'Zusätzlicher Haltekosten-Stress auf das volle Einstiegskapital; eingebettete Emittentenfinanzierung '
             'wird nicht als nochmals gemessene Gebühr abgezogen. Tatsächliche Kosten unbekannt. '
             'Zusätzlicher Szenariovergleich ohne weitere Abbuchung. Neue automatische Kontofälle ab 19.10.2026 buchen ihre eingefrorenen Beispielkosten bereits im Spielgeld; dieser Vergleich zieht sie nicht nochmals ab.')

def evidence_report(cases):
    """Bounded read-only audit; calculated analysis never becomes an observed fill."""
    rows=[]
    for c in cases:
        if c.get('demonstration'):continue
        entry=c.get('entryQuote') or {}
        basis=c.get('priceBasis') or {}
        kind='observed' if entry else 'calculated' if basis.get('kind')=='calculated' else 'unpriced'
        eligible=(kind=='observed' and c.get('status')=='closed' and c.get('productReturnKnown') is True
                  and c.get('performanceEligible') is not False and c.get('remainingUnits')==0
                  and c.get('pendingUnits')==0)
        exits=[dict(kind=e.get('kind'),at=e.get('at'),recordedAt=e.get('recordedAt'),
                    source=(e.get('quote') or {}).get('source'),
                    bidAt=(e.get('quote') or {}).get('bidAt'),bid=(e.get('quote') or {}).get('bid'),
                    units=e.get('units'),reason=e.get('reason'))
               for e in c.get('events',[]) if finite(e.get('units')) and e['units']>0]
        rows.append(dict(id=c.get('id'),direction=c.get('plan',{}).get('direction'),kind=kind,
            status=c.get('status'),performanceEligible=eligible,priceBasis=basis or None,
            entry=dict(at=entry.get('askAt'),source=entry.get('source'),ask=c.get('entryAsk')),
            exits=exits,grossPct=c.get('productGrossPct') if eligible else None,
            observedMaxDrawdownPct=c.get('observedMaxDrawdownPct'),
            observedValuationChecks=c.get('observedValuationChecks',0),
            costAssumptions=c.get('ledgerCostModel'),actualNetKnown=False))
    return dict(version=1,groups=[dict(kind=kind,cases=sum(r['kind']==kind for r in rows),
        eligible=sum(r['kind']==kind and r['performanceEligible'] for r in rows))
        for kind in ('observed','calculated','unpriced')],cases=rows,actualNetKnown=False,
        note='Gewählter Tag, höchstens 100 Fälle. Beobachtete Geld/Brief-Positionen, berechnete Analyse und unbelegte Fälle getrennt. '
             'Größter Rückgang nur an beobachteten Bewertungspunkten, ohne erfundene Zwischenkurse. '
             'Kosten sind eingefrorene Beispielannahmen; tatsächlicher Nettogewinn unbekannt.')
