"""Offline DEGIRO integration laboratory. No broker SDK, credentials or IO.

The internal adapter contract is deliberately NOT a DEGIRO wire format.
Replacing this adapter requires a separately reviewed broker integration.
"""
from copy import deepcopy
from math import isfinite
import vollautomatisch_engine


class PaperAdapter:
    def __init__(self):
        self.position = 0
        self.stop = None
        self.journal = []
        self.seen = {}

    def dispatch(self, key, event):
        if not isinstance(key, str) or not key:
            raise ValueError('Ereignisschlüssel fehlt')
        if key in self.seen:
            original, receipt = self.seen[key]
            if original != event:
                raise ValueError('Schlüssel bereits für andere Daten verwendet')
            return deepcopy(receipt)
        kind = event.get('event')
        if kind not in ('BUY_PAPER', 'SELL_PAPER', 'TRAIL_PAPER'):
            raise ValueError('Nur simulierte Orderereignisse erlaubt')
        if kind in ('BUY_PAPER', 'SELL_PAPER'):
            qty, price = event.get('quantity'), event.get('price_eur')
            if type(qty) is not int or qty <= 0:
                raise ValueError('Ungültige Stückzahl')
            if type(price) not in (int, float) or not isfinite(price) or price <= 0:
                raise ValueError('Ungültiger Preis')
            if kind == 'BUY_PAPER':
                if self.position:
                    raise ValueError('Position bereits offen')
                stop = event.get('stop_eur')
                if type(stop) not in (int, float) or not isfinite(stop) or not 0 < stop < price:
                    raise ValueError('Gültiger Anfangsstop fehlt')
                self.position, self.stop = qty, stop
            else:
                if qty != self.position:
                    raise ValueError('Verkauf passt nicht zur simulierten Position')
                self.position, self.stop = 0, None
        else:
            stop = event.get('stop_eur')
            if not self.position or type(stop) not in (int, float) or not isfinite(stop) or stop < self.stop:
                raise ValueError('Stop darf nicht gelockert werden')
            self.stop = stop
        receipt = {'id': f'SIM-{len(self.journal)+1}', 'mode': 'OFFLINE_SIMULATION',
                   'event': deepcopy(event), 'position': self.position,
                   'stop': self.stop, 'brokerSubmitted': False}
        self.seen[key] = (deepcopy(event), deepcopy(receipt))
        self.journal.append(deepcopy(receipt))
        return receipt


def run(scenario='target'):
    replay = vollautomatisch_engine.demonstration(scenario)
    adapter = PaperAdapter()
    duplicates = 0
    for i, event in enumerate(replay['events']):
        if event['event'] not in ('BUY_PAPER', 'SELL_PAPER', 'TRAIL_PAPER'):
            continue
        key = f'{scenario}:{i}'
        receipt = adapter.dispatch(key, event)
        # Retry the same event: the journal and position must not change.
        before = len(adapter.journal)
        assert adapter.dispatch(key, event) == receipt
        assert len(adapter.journal) == before
        duplicates += 1
    return {'mode': 'OFFLINE_SIMULATION', 'brokerConnected': False,
            'liveOrdersEnabled': False, 'connectorCompatibility': 'NOT_TESTED',
            'scenario': scenario, 'duplicateRetriesChecked': duplicates,
            'journal': adapter.journal, 'simulation': replay,
            'notice': 'Künstliche Kurse. Interner Schnittstellentest; keine DEGIRO-Verbindung.'}
