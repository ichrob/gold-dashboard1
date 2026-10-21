"""Identifier-only reconciliation. Names and quantities never prove an ISIN."""
import copy
import json
import re
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler

_CACHE = {}
_NEXT = 0.0
FIGI = re.compile(r'BBG[A-Z0-9]{9}')


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def lookup_figis(records):
    """One bounded public batch. Never send account IDs, names, units or keys."""
    global _NEXT
    now=time.monotonic()
    selected=list(records.values())
    pending=[r for r in selected if (r['isin'],r['currency']) not in _CACHE or _CACHE[(r['isin'],r['currency'])][0] <= now][:10]
    if pending and now >= _NEXT:
        _NEXT=now+60
        payload=[{'idType':'ID_ISIN','idValue':r['isin'],'currency':r['currency']} for r in pending]
        result=None
        try:
            req=Request('https://api.openfigi.com/v3/mapping',data=json.dumps(payload).encode(),method='POST',headers={'Content-Type':'application/json','Accept':'application/json'})
            with build_opener(NoRedirect()).open(req,timeout=8) as response:
                raw=response.read(500001)
            if len(raw)>500000:raise ValueError()
            result=json.loads(raw)
            if not isinstance(result,list) or len(result)!=len(pending):raise ValueError()
        except Exception:
            result=None
        for i,r in enumerate(pending):
            found=set()
            item=result[i] if result else None
            if isinstance(item,dict) and isinstance(item.get('data'),list):
                for row in item['data']:
                    if isinstance(row,dict) and isinstance(row.get('figi'),str) and FIGI.fullmatch(row['figi']):found.add(row['figi'])
            _CACHE[(r['isin'],r['currency'])]=(now+(86400 if found else 900),found)
        while len(_CACHE)>1000:_CACHE.pop(next(iter(_CACHE)))
    return {r['isin']:set(_CACHE.get((r['isin'],r['currency']),(0,set()))[1]) for r in selected if _CACHE.get((r['isin'],r['currency']),(0,set()))[0]>now}


def reconcile(entry, account, previous=None, lookup=lookup_figis):
    entry=copy.deepcopy(entry)
    records=entry['records'];old=(previous or {}).get('links',{})
    reference={}
    if any(FIGI.fullmatch(p.get('figi') or '') and not p.get('providerIsin') for p in account['positions']):
        try:reference=lookup(records)
        except Exception:reference={}
    candidates={};reasons={}
    for p in account['positions']:
        key=p['positionKey'];matches=[]
        original=p.get('providerIsin',p.get('isin'))
        prior=old.get(key)
        if not original and not p.get('stableInstrumentId'):
            reasons[key]='Stabile Anbieterkennung fehlt.';continue
        for isin,r in records.items():
            if r['currency']!=p['currency']:continue
            method=None
            if original:
                if original==isin:method='provider-isin'
            elif prior and prior['isin']==isin and prior['symbol']==p['symbol'] and prior['currency']==p['currency'] and not (prior.get('figi') and p.get('figi') and prior['figi']!=p['figi']):
                method=prior['method']
            elif FIGI.fullmatch(p.get('figi') or '') and p['figi'] in reference.get(isin,set()):
                method='figi-verified'
            # WKN only if explicitly labeled by the institution, never an
            # arbitrary six-character ticker that happens to resemble a WKN.
            elif isin.startswith('DE000') and (p.get('rawSymbol') or '').upper().replace(' ','')=='WKN:'+isin[5:11]:
                method='provider-wkn'
            if method:matches.append(dict(isin=isin,method=method,symbol=p['symbol'],currency=p['currency'],figi=p.get('figi') or None))
        candidates[key]=matches
        if not matches:reasons[key]='Keine übereinstimmende ISIN, ausdrücklich bezeichnete WKN oder FIGI geliefert. Produktname allein genügt nicht.'
        elif len(matches)>1:reasons[key]='Mehrere Kennungen passen; Zuordnung bleibt offen.'
    counts={}
    for matches in candidates.values():
        for m in matches:counts[m['isin']]=counts.get(m['isin'],0)+1
    links={}
    for key,matches in candidates.items():
        if len(matches)==1 and counts[matches[0]['isin']]==1:links[key]=matches[0]
        elif matches and key not in reasons:reasons[key]='Kennung passt zu mehreren Depotpositionen; Zuordnung bleibt offen.'
    entry.update(links=links,automatic=True,report={'matched':len(links),'total':len(account['positions']),
        'unresolved':[{'positionKey':p['positionKey'],'reason':reasons.get(p['positionKey'],'Zuordnung nicht eindeutig.')} for p in account['positions'] if p['positionKey'] not in links]})
    return entry
