"""Dated CHF chart observations converted for Bob's EUR analysis only."""
import copy
from datetime import datetime, timezone
import product_quotes as q

def convert_analysis(result, fx=None, now=None):
    out = copy.deepcopy(result)
    chart = out.get('chartEvidence')
    if not chart or chart.get('currency') != 'CHF':
        return out
    out['nativeChartEvidence'] = copy.deepcopy(chart)
    out.pop('chartEvidence', None)
    try:
        if fx is None:
            from sg_quotes import market_input
            fx = market_input('fx')
        now = now or datetime.now(timezone.utc)
        if fx.get('result') != 'success' or fx.get('base') != 'USD' or fx.get('market_session') != 'open' or any(fx.get('sources', {}).get(k) != 'live' for k in ('EUR','CHF')):
            raise ValueError('Aktuelle CHF/EUR-Umrechnung fehlt')
        rate = q.number(fx['rates']['EUR']) / q.number(fx['rates']['CHF'])
        times = [q.stamp(chart['pointAt']),q.stamp(fx['data_updated_at']),q.stamp(fx['effective_at']['EUR']),q.stamp(fx['effective_at']['CHF'])]
        if not 0 < rate < 10 or any(not 0 <= (now-t).total_seconds() <= 300 for t in times) or (max(times)-min(times)).total_seconds() > 90:
            raise ValueError('CHF/EUR-Daten veraltet oder zeitlich abweichend')
        out['chartEvidence'] = dict(chart, bid=chart['bid']*rate, ask=chart['ask']*rate, currency='EUR',pointAt=min(times).isoformat())
        out['currencyConversion'] = dict(fromCurrency='CHF',toCurrency='EUR',rate=rate,source='exchangerate.dev',at=min(times).isoformat(),nativeAt=chart['pointAt'],
            evidence=dict(base='USD', eur=q.number(fx['rates']['EUR']), chf=q.number(fx['rates']['CHF']),
                          dataAt=times[1].isoformat(), eurAt=times[2].isoformat(), chfAt=times[3].isoformat(),
                          marketSession=fx['market_session'], eurSource=fx['sources']['EUR'], chfSource=fx['sources']['CHF']))
    except (KeyError,ValueError,TypeError,OSError,ZeroDivisionError):
        out['reason'] = 'CHF-Originalkurse vorhanden; aktuelle zeitlich passende CHF/EUR-Umrechnung fehlt'
    return out
