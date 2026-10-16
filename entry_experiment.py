"""Frozen, prospective threshold comparisons. Never changes signal approval."""
import market_optimization as market

VERSION = 'entry-experiment-v1'
LABELS = {'baseline': 'Aktuell / schnell', 'cautious': 'Vorsichtige Bestätigung',
          'reference': 'Einstieg 1,5 ATR / 15 Min.',
          'atr1': 'Einstieg 1 ATR / 15 Min.', 'atr2': 'Einstieg 2 ATR / 15 Min.',
          'age10': 'Einstieg 1,5 ATR / 10 Min.', 'age20': 'Einstieg 1,5 ATR / 20 Min.'}
THRESHOLDS = {'reference': (1.5,15), 'atr1': (1.,15), 'atr2': (2.,15),
              'age10': (1.5,10), 'age20': (1.5,20)}


def capture(r):
    frozen = r['marketOptimization']
    q = r.get('entryQuality') or {}
    entry = frozen['entry']
    base = r['direction']
    valid = (q.get('baselineDirection') == base and
             all(market.num(entry.get(k)) and entry[k] >= 0
                 for k in ('deviationAtr','roomR','signalAgeMinutes')))
    variants = dict(baseline=base, cautious=r.get('shadowDirection'))
    for key, (distance, age) in THRESHOLDS.items():
        variants[key] = ('NEUTRAL' if base == 'NEUTRAL' else
            None if not valid else base if entry['deviationAtr'] <= distance
            and entry['signalAgeMinutes'] <= age and entry['roomR'] >= 2 else 'NEUTRAL')
    return dict(version=VERSION, variants=variants, automaticRuleChange=False)


def report(rows, score, now=None):
    # Never reconstruct variants for old records from their future results.
    selected = []
    for r, truths in rows:
        trial = r.get('entryExperiment') or {}
        if trial.get('version') != VERSION:
            continue
        selected.append(({**r, 'marketOptimization': {
            **r['marketOptimization'], 'variants': trial['variants']}}, truths))
    result = market.report(selected, score, now, labels=LABELS)
    for group in result['groups']:
        baseline = group['variants']['baseline']['sumPct']
        for value in group['variants'].values():
            value['meanDifferencePct'] = (value['sumPct']-baseline)/group['cases']
    result.update(version=VERSION, primaryHorizon=15, winner=None,
        status='collecting' if not result['groups'] else 'descriptive-only',
        note='Punkte 2 und 4: vorab gespeicherte Varianten, gleiche Fälle je Zeitraum und Marktphase. '
        'Pro Variante wird nur eine Einstiegsschwelle verändert; Platz bleibt mindestens 2R. '
        'Primärer Zeitraum 15 Minuten; 1/5/30 Minuten sind Zusatzdiagnosen. '
        'Ab 26.10.2026 getrennte Prüfung; kein automatischer Sieger oder Regelwechsel. '
        'Abwarten zählt als null, fehlende Daten schließen den gemeinsamen Fall aus. '
        '0,04 % Beispielkosten auf Gold, keine Produktgewinne. Produktkosten separat im Papierkonto. '
        'Rollierendes Berichtsfenster; kein vollständiger Langzeitnachweis.')
    return result
