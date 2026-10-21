"""Explicit CSV-to-holdings identity links and dated export evidence.

No name-only automatic matching, current cash replacement, or trade approvals.
"""
import copy
from decimal import Decimal
import re
import snaptrade_portfolio as portfolio


def prepare(payload, snapshot, number, text, source_time):
    if not isinstance(payload, dict) or set(payload) != {'accountKey','importedAt','records','links'}:
        raise ValueError('Invalid CSV link')
    account = next((a for a in snapshot['accounts'] if a['accountKey'] == payload['accountKey']), None)
    at = source_time(payload['importedAt'])
    if not account or not at or not isinstance(payload['records'], list) or not 1 <= len(payload['records']) <= 1000:
        raise ValueError('Invalid CSV account or rows')
    records = {}
    for row in payload['records']:
        if not isinstance(row, dict) or set(row) != {'isin','name','quantity','currency','price','value','costBasis'}:
            raise ValueError('Invalid CSV record')
        isin = portfolio.isin(row['isin'])
        quantity = number(row['quantity'])
        currency = row['currency']
        if not isin or isin in records or quantity is None or not isinstance(currency,str) or not re.fullmatch('[A-Z]{3}',currency):
            raise ValueError('Invalid CSV identity or currency')
        values = {key:number(row[key]) for key in ('price','value','costBasis')}
        if any(row[key] is not None and values[key] is None for key in values):
            raise ValueError('Invalid CSV number')
        records[isin] = dict(isin=isin,name=text(row['name']),quantity=quantity,currency=currency,**values)
    if not isinstance(payload['links'], list) or len(payload['links']) > len(account['positions']):
        raise ValueError('Invalid CSV links')
    positions = {p['positionKey']:p for p in account['positions']}
    links, assigned_isins = {}, set()
    for link in payload['links']:
        if not isinstance(link,dict) or set(link) != {'positionKey','isin','confirmed'}:
            raise ValueError('Invalid CSV mapping')
        key, isin = link['positionKey'], link['isin']
        position, record = positions.get(key), records.get(isin)
        if not position or not record or key in links or isin in assigned_isins or position['currency'] != record['currency']:
            raise ValueError('Conflicting CSV mapping')
        original = position.get('providerIsin',position.get('isin'))
        if original and original != isin:
            raise ValueError('Provider ISIN conflict')
        # No persistent name-based substitute for an institution's instrument ID.
        if not original and (link['confirmed'] is not True or position.get('stableInstrumentId') is not True):
            raise ValueError('Explicit confirmation and stable instrument ID required')
        assigned_isins.add(isin)
        links[key] = dict(isin=isin,method='provider-isin' if original else 'user-confirmed',
                          symbol=position['symbol'],currency=position['currency'])
    if not links:
        raise ValueError('No confirmed CSV links')
    return dict(importedAt=at,records=records,links=links)


def apply(snapshot, csv_by_account):
    for account in snapshot['accounts']:
        entry = csv_by_account.get(account['accountKey'])
        account.pop('csvImportedAt',None)
        if entry: account['csvImportedAt'] = entry['importedAt']
        for p in account['positions']:
            original = p.setdefault('providerIsin',p.get('isin'))
            old_isin = p.get('isin')
            base = p.setdefault('providerValuation',{k:p.get(k) for k in ('marketValue','unrealizedPnl','unrealizedPercent','valuationNote')})
            p.update(copy.deepcopy(base),isin=original)
            for k in ('csvEvidence','csvLinkConflict','isinSource','valuationBasis'): p.pop(k,None)
            if old_isin != original: p.pop('issuerQuote',None)
            if not original and 'isin' not in p['missing']: p['missing'].append('isin')
            if not entry: continue
            link = entry['links'].get(p['positionKey'])
            if not link: continue
            isin = link['isin']
            if ((original and original != isin) or p['symbol'] != link['symbol'] or p['currency'] != link['currency']):
                p['csvLinkConflict'] = True
                continue
            record = entry['records'].get(isin)
            if not record or record['currency'] != p['currency']: continue
            p.update(isin=isin,isinSource=link['method'],csvEvidence={**copy.deepcopy(record),
                'importedAt':entry['importedAt'],'exportAt':None})
            p['missing'] = [x for x in p['missing'] if x != 'isin']
            # CSV market value is always historical, never a current broker value.
            # Only recognizable unit-quoted certificates can gain a calculated
            # per-unit valuation; no guessed multipliers for futures/options/bonds.
            certificate = re.search(r'\bfaktor\b|\bfactor\b|\bturbo\b|knock[ -]?out',record['name'],re.I)
            if p['kind'] != 'other' or not certificate: continue
            if any(record[k] is None for k in ('quantity','price','value')): continue
            qty, price, value = (Decimal(record[k]) for k in ('quantity','price','value'))
            if qty == 0 or price <= 0 or abs(qty*price-value) > max(Decimal('.02'),abs(value)*Decimal('.0001')):
                continue
            if p['units'] is None or p['valuationPrice'] is None: continue
            units, current = Decimal(p['units']), Decimal(p['valuationPrice'])
            p['marketValue'] = str(units*current)
            p['valuationBasis'] = 'csv-calculated-unit-quotation'
            p['valuationNote'] = 'CSV-Rechenwert: Exportwert passt zu Menge × Kurs. Stücknotierung daraus abgeleitet, nicht unabhängig bestätigt.'
            if p['costBasis'] is not None:
                basis = Decimal(p['costBasis'])
                p['unrealizedPnl'] = str(units*(current-basis))
                p['unrealizedPercent'] = str((current-basis)/basis*100*(1 if units>0 else -1)) if basis>0 and units else None
            # Acquisition costs in CSV remain historical. Never overwrite the
            # latest broker acquisition price, even when quantities happen to match.
