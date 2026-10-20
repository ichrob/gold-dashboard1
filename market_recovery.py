"""Proactively retry market adapters, including when the app is closed.

Adapter caches, source validation and provider backoffs remain authoritative.
One pending call per input prevents a stalled source accumulating new work.
Successful calls are not a claim of fresh or executable market evidence.
"""
import threading
import time
from concurrent.futures import ThreadPoolExecutor

_LOCK = threading.Lock()
_POOL = ThreadPoolExecutor(max_workers=4, thread_name_prefix='market-recovery')
_PENDING = {}
_STATE = {}
_NEXT = {}


def operations():
    import spot_data, sg_quotes, investing_card, future_analysis, server
    return {'spot': spot_data.current, 'fx': lambda: sg_quotes.market_input('fx'),
            'cfd': investing_card.fetch, 'future': future_analysis.fetch_reference,
            **{'history-'+interval: lambda i=interval, r=span: server.fetch_technical_history(i, r)
               for interval, span in [('1m','1d'),('5m','5d'),('15m','5d'),('30m','1mo'),('1h','3mo'),('4h','3mo')]}}


def tick(now=None, probes=None):
    import background_push
    if background_push.gold_weekend_seconds_remaining()>0:
        return
    now = time.monotonic() if now is None else now
    probes = operations() if probes is None else probes
    with _LOCK:
        for key, future in list(_PENDING.items()):
            if not future.done():
                continue
            try:
                result = future.result()
                if result is None or result == []:
                    raise ValueError("Empty market response")
                _STATE[key] = {'state':'call-completed', 'checkedAt':time.time()}
            except Exception as exc:
                _STATE[key] = {'state':'retrying', 'code':type(exc).__name__, 'checkedAt':time.time()}
            del _PENDING[key]
            _NEXT[key] = now+30
        for key, operation in probes.items():
            if key not in _PENDING and now >= _NEXT.get(key, 0):
                _PENDING[key] = _POOL.submit(operation)


def health():
    with _LOCK:
        return {'inputs':{k:dict(v) for k,v in _STATE.items()},
                'checking':sorted(_PENDING), 'freshnessValidatedByAdapters':True}
