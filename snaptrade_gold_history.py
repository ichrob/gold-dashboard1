"""Read-only Gold knock-out research candidates from existing SnapTrade activities.

No additional provider fetches. A historic trade proves neither current DEGIRO
listing nor issuer prices; records never enter the verified product list.
"""
import re
from snaptrade_portfolio import isin as valid_isin

MAX_CANDIDATES = 80
MAX_INPUT_ROWS = 3000  # Existing weekly filtered BUY/SELL read is limited to three 1k pages.
MAX_DESCRIPTION = 160
_GOLD = re.compile(r'(?<![a-z])(?:gold|xau(?:/usd)?)(?![a-z])', re.I)
_KO = re.compile(r'(?<![a-z])(?:knock[ -]?out|turbo|mini\s*future|mini\s*short|mini\s*long|barrier|best|unlimited|open\s*end|bull\s*certificate|bear\s*certificate)(?![a-z])', re.I)
_FACTOR = re.compile(r'(?<![a-z])(?:faktor|factor|constant\s*leverage|fixed\s*leverage)(?![a-z])', re.I)
_NOT_SPOT = re.compile(r'(?<![a-z])(?:gold\s*future|gold\s*futures|comex|gc[zfhkmnuqv]\d{2}|gold\s*miner|gold\s*mining|gold\s*etf|gold\s*etn|gold\s*corp|barrick\s*gold|gold\s*fields|goldman)(?![a-z])', re.I)
_LONG = re.compile(r'(?<![a-z])(?:long|call|bull)(?![a-z])', re.I)
_SHORT = re.compile(r'(?<![a-z])(?:short|put|bear)(?![a-z])', re.I)


def classify(name):
    if not isinstance(name, str) or not 4 <= len(name) <= MAX_DESCRIPTION:
        return None
    if not _GOLD.search(name) or _NOT_SPOT.search(name) or _FACTOR.search(name):
        return None
    if not _KO.search(name):
        return None
    lon, sho = bool(_LONG.search(name)), bool(_SHORT.search(name))
    if lon == sho:
        return None
    return 'LONG' if lon else 'SHORT'


def discover(accounts, limit=MAX_CANDIDATES):
    """Only checksum-confirmed ISINs in the *already cached* normalized journal.

    Partial history is explicitly flagged. Conflicting descriptions/sides
    are suppressed rather than choosing a direction. No broker API calls.
    """
    if not isinstance(accounts, list) or len(accounts) > 3:
        return dict(code='UNAVAILABLE', items=[], historyComplete=False,
                    tradeApproved=False, completeDegiroCatalog=False)
    by_isin = {}
    conflicts = set()
    scan_rows = scanned = 0
    any_history = False
    complete = True
    for account in accounts:
        if not isinstance(account, dict):
            continue
        activities = (account.get('journal') or {}).get('activities') or {}
        rows = activities.get('rows')
        if not isinstance(rows, list):
            complete = False
            continue
        any_history = True
        complete &= activities.get('complete') is True and activities.get('code') == 'READ_OK'
        if len(rows) > MAX_INPUT_ROWS:
            complete = False
            rows = rows[:MAX_INPUT_ROWS]
        for row in rows:
            scan_rows += 1
            if not isinstance(row, dict) or row.get('type') not in ('BUY','SELL'):
                continue
            scanned += 1
            identifier = valid_isin(row.get('isin'))
            side = classify(row.get('name'))
            if not identifier or not side or identifier in conflicts:
                continue
            name = row['name'].strip()
            date = row.get('date')
            if not isinstance(date,str) or not re.match(r'^\d{4}-\d{2}-\d{2}', date):
                date = None
            previous = by_isin.get(identifier)
            if previous and previous['direction'] != side:
                by_isin.pop(identifier, None)
                conflicts.add(identifier)
                continue
            if previous:
                previous['historicRecords'] += 1
                if date and (not previous['lastTradeDate'] or date > previous['lastTradeDate']):
                    previous['lastTradeDate'] = date
            else:
                by_isin[identifier] = dict(
                    isin=identifier, direction=side, name=name,
                    lastTradeDate=date, historicRecords=1,
                    source='SnapTrade · historische DEGIRO-Transaktionen',
                    brokerHistoricallyTransacted=True,
                    currentlyDegiroListed=None, originalBidAskConfirmed=False,
                    issuerVerified=False, eligibleForTop3=False,
                    tradeApproved=False, automaticOrders=False)
    # A weekly filtered BUY/SELL window is already fetched to assess historical
    # coverage. Reuse only its previously deduplicated, sanitized *candidate
    # summaries*: never retain new raw activity rows or add broker requests.
    filtered_sources = 0
    for account in accounts:
        coverage = ((account.get('journal') or {}).get('tradeCoverage') or {})
        hints = coverage.get('goldHistoryHints') or {}
        if coverage.get('code') != 'READ_OK' or not isinstance(hints,dict):
            continue
        candidate_rows = hints.get('items')
        if not isinstance(candidate_rows,list) or len(candidate_rows)>MAX_CANDIDATES:
            continue
        filtered_sources += 1
        for hint in candidate_rows:
            if not isinstance(hint,dict):
                continue
            identifier = valid_isin(hint.get('isin'))
            name = hint.get('name')
            side = classify(name)
            if not identifier or side != hint.get('direction') or identifier in conflicts:
                continue
            existing = by_isin.get(identifier)
            if existing and existing['direction'] != side:
                by_isin.pop(identifier,None)
                conflicts.add(identifier)
                continue
            date = hint.get('lastTradeDate')
            date = date if isinstance(date,str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}',date) else None
            count = hint.get('historicRecords')
            count = count if isinstance(count,int) and not isinstance(count,bool) and 0<count<=3000 else 1
            if existing:
                # The same transaction may occur in both history windows. Never
                # double-count it; keep the larger observed count.
                existing['historicRecords'] = max(existing['historicRecords'],count)
                if date and (not existing['lastTradeDate'] or date>existing['lastTradeDate']):
                    existing['lastTradeDate']=date
            else:
                by_isin[identifier]=dict(
                    isin=identifier,direction=side,name=name.strip(),
                    lastTradeDate=date,historicRecords=count,
                    source='SnapTrade · historische gefilterte BUY/SELL-Daten',
                    brokerHistoricallyTransacted=True,
                    currentlyDegiroListed=None,originalBidAskConfirmed=False,
                    issuerVerified=False,eligibleForTop3=False,
                    tradeApproved=False,automaticOrders=False)
    any_history = any_history or filtered_sources>0
    complete = complete and filtered_sources == 0  # Filtered trade history is not full account history.
    items = sorted(by_isin.values(), key=lambda v: (v['lastTradeDate'] or '', v['historicRecords'],v['isin']), reverse=True)
    return dict(code='HISTORICAL_PARTIAL' if any_history and not complete else
                'HISTORICAL_READ' if any_history else 'NO_HISTORY',
                items=items[:max(0,min(limit, MAX_CANDIDATES))],
                candidateCount=len(items), suppressedConflicts=len(conflicts),
                journalRowsExamined=scan_rows, tradesExamined=scanned,
                historyComplete=complete and any_history,
                filteredHistorySources=filtered_sources,
                currentlyDegiroListed=False, completeDegiroCatalog=False,
                tradeApproved=False, automaticOrders=False,
                note='Historische Trades sind nur Research-Hinweise, keine aktuelle DEGIRO-Liste.')
