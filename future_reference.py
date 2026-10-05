"""Current GCZ26 working reference: identified CFD first, estimate fallback.

The CFD remains a proxy, never an exchange quote or historical candle.
Its comparison measurements are isolated from the estimate's accuracy record.
"""
from datetime import datetime, timezone
import investing_card
import estimate_quality
from future_estimate import stamp, number

KEY = 'future:GCZ26:investing-cfd-direct:v1'


def select(research, fallback, now=None):
    now = now or datetime.now(timezone.utc)
    try:
        if research.get('contract') != 'GCZ26':
            raise ValueError('CFD nicht diesem Future-Kontrakt zugeordnet')
        quote = investing_card.fetch()
        price, at = number(quote['price']), stamp(quote['at'])
        if (quote.get('kind') != 'cfd' or quote.get('declaredContract') != 'GCZ26'
                or quote.get('realtimeCfd') is not True
                or not 0 <= (now-at).total_seconds() <= 60):
            raise ValueError('CFD-Kurs veraltet oder Kontraktzuordnung nicht bestätigt')
        validation = dict(ready=False, sampleCount=0, reason='CFD-/Börsenkurs-Abweichung noch nicht ausreichend gemessen')
        out = dict(available=True, contract='GCZ26', kind='cfd-reference', priceUsd=price,
                   priceAt=quote['at'], proxyKind='investing-cfd-direct',
                   proxySource='Investing.com · Gold-CFD', sourceUrl=quote.get('sourceUrl'),
                   label='Gold-CFD als Future-Referenz', isExchangeRealtime=False,
                   eligible=False, validation=validation,
                   note='Abgeleiteter CFD-Kurs; kein Börsenkurs. Historische Indikatoren stammen aus GCZ26-Börsenkerzen.')
        # Only an independently received exact-contract reference may measure
        # the proxy's deviation. Do not reuse spot-model validation.
        try:
            ref = stamp(research['underlyingAt'])
            value = number(research['underlyingPriceUsd'])
            horizon = (at-ref).total_seconds()
            if 0 < horizon <= 1800:
                estimate_quality.observe(KEY, value, research['underlyingAt'], now.isoformat())
                estimate_quality.record(KEY, price, quote['at'], research['underlyingAt'], now.isoformat())
                out['validation'] = estimate_quality.quality(KEY, horizon, now)
                if out['validation'].get('ready'):
                    out['comparisonErrorUsd'] = max(.1, out['validation']['maxAbsoluteError'])
        except (KeyError, ValueError, TypeError, OverflowError):
            pass
        return out
    except (OSError, ValueError, KeyError, TypeError, OverflowError):
        result = dict(fallback)
        result['selectionNote'] = 'Gold-CFD nicht aktuell oder nicht passend; Bobs Futures-Schätzung als Ersatz'
        return result
