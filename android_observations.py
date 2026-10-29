"""Private app-screen observations, isolated from quotes, approvals and simulations."""
import hashlib
import json
import re
from datetime import datetime, timezone
from product_quotes import valid_isin

FIELDS = ('Geld','Brief','Zuletzt','Anzeigezeit','Hebel','KO-Schwelle','Basispreis','Bv','Handelsplatz')
REQUIRED = ('Geld','Brief','Anzeigezeit','Hebel','KO-Schwelle','Basispreis','Bv')
CODES = set('COMPLETE PARTIAL READ_TIMEOUT SEARCH_MISSING SEARCH_TREE_EMPTY SEARCH_NOT_ACTIONABLE GOLD_IDENTITIES_MISSING SEARCH_AMBIGUOUS RESULT_MISSING NAVIGATION_REJECTED PROTECTED_VIEW PROTECTED_PASSWORD PROTECTED_LOGIN PROTECTED_ORDER PROTECTED_ORDER_CONFIRM PROTECTED_ORDER_TYPE PROTECTED_ORDER_PRICE PROTECTED_ORDER_QUANTITY PROTECTED_SENSITIVE_INPUT PROTECTED_SENSITIVE_CONTENT UNRECOGNIZED_INPUT INVALID_VIEW IDENTITY_CHANGED NO_QUOTES RETURN_FAILED SCROLL_LIMIT INVALID_QUOTES SEEK_LIMIT SCROLL_LAYOUT_CHANGED UNSAFE_VIEW USER_STOP STOPPED RUN_TIMEOUT USER_INTERRUPTED TRANSFER_ERROR STORAGE_ERROR SCREEN_LOCKED SERVICE_INTERRUPTED'.split())


def timestamp(value):
    if not isinstance(value,str) or len(value)>40: raise ValueError('Zeitangabe fehlt')
    at=datetime.fromisoformat(value.replace('Z','+00:00'))
    if at.tzinfo is None: raise ValueError('Zeitzone fehlt')
    return at


def parse_draft(raw, isin, now):
    if not isinstance(raw,str) or len(raw)>8000: raise ValueError('Leseentwurf zu groß')
    lines=raw.splitlines()
    if not lines or lines[0]!='BOB APP-LESEENTWURF – NICHT VERIFIZIERT': raise ValueError('App-Entwurf fehlt')
    fixed={}; fields={}
    for line in lines[1:]:
        if line=='Kein automatischer Handelsnachweis, keine Freigabe, keine Order.': continue
        m=re.fullmatch(r'(ISIN|Quelle|Erfasst): (.+)',line)
        if m:
            if m[1] in fixed: raise ValueError('Doppelte Angabe')
            fixed[m[1]]=m[2];continue
        m=re.fullmatch(r'(.+) \(Anzeige ungeprüft\): (.{1,60})',line)
        if not m or m[1] not in FIELDS+('Währung','Hinweis') or m[1] in fields: raise ValueError('Unbekanntes oder doppeltes Feld')
        fields[m[1]]=m[2]
    if fixed.get('ISIN')!=isin or fixed.get('Quelle')!='DEGIRO-App': raise ValueError('Produktkennung stimmt nicht')
    at=timestamp(fixed.get('Erfasst'))
    if at.year<2020 or (now-at).total_seconds() < -60: raise ValueError('Ungültige Erfassungszeit')
    if fields.get('Währung') not in ('EUR','CHF'): raise ValueError('Währung fehlt')
    if fields.get('Hinweis') not in ('Handel eingeschränkt','Kurse verzögert','Keine Aussage zur Handelbarkeit'): raise ValueError('Hinweis fehlt')
    for key in ('Geld','Brief','Zuletzt','Hebel','KO-Schwelle','Basispreis','Bv'):
        if key in fields and (not re.fullmatch(r'\d{1,9}(?:[,.]\d{1,4})?',fields[key]) or float(fields[key].replace(',','.'))<=0): raise ValueError('Ungültige Zahl')
    if not any(k in fields for k in ('Geld','Brief','Zuletzt')): raise ValueError('Kurs fehlt')
    if 'Geld' in fields and 'Brief' in fields and float(fields['Geld'].replace(',','.'))>float(fields['Brief'].replace(',','.')): raise ValueError('Widersprüchliches Kurspaar')
    if 'Anzeigezeit' in fields:
        datetime.strptime(fields['Anzeigezeit'],'%d/%m/%Y %H:%M')
    if 'Handelsplatz' in fields and not re.fullmatch(r'[\w ./-]{2,48}',fields['Handelsplatz']): raise ValueError('Handelsplatz ungültig')
    missing=[k for k in REQUIRED if k not in fields]
    return dict(isin=isin,observedAt=at.isoformat(),fields=fields,missingFields=missing,
                verified=False,tradeApproved=False,executable=False,sourceTime=None,source='DEGIRO-App',raw=raw,staleAtReceipt=(now-at).total_seconds()>86400)


def prepare(payload, feed, now=None):
    now=now or datetime.now(timezone.utc)
    if not isinstance(payload,dict) or len(json.dumps(payload))>65536: raise ValueError('Leselauf zu groß')
    revision=payload.get('revision')
    if type(revision) is not int or not 1<=revision<=10000: raise ValueError('Ungültige Speicherversion')
    version=payload.get('appVersionCode')
    if version is not None and (type(version) is not int or not 1<=version<=2100000000): raise ValueError('Ungültige App-Version')
    batch=payload.get('batchId','');ids=payload.get('isins');rows=payload.get('results');events=payload.get('events')
    if not isinstance(batch,str) or not re.fullmatch('[a-f0-9]{32}',batch): raise ValueError('Leselauf-Kennung fehlt')
    if not isinstance(ids,list) or not 1<=len(ids)<=12 or any(not isinstance(i,str) or not valid_isin(i) for i in ids) or len(set(ids))!=len(ids): raise ValueError('Ungültige Produktliste')
    uploaded=timestamp(payload.get('listUploadedAt'))
    source=payload.get('listSource','bob-saved-list')
    if source not in ('bob-saved-list','degiro-gold-search'): raise ValueError('Ungültige Listenquelle')
    if uploaded.year<2020 or (now-uploaded).total_seconds() < -60: raise ValueError('Ungültiger Listenstand')
    if not isinstance(rows,list) or len(rows)>12 or not isinstance(events,list) or len(events)>48: raise ValueError('Leselauf unvollständig')
    current={p.get('isin') for p in feed.get('products',[]) if isinstance(p,dict)}
    results=[];seen=set()
    for row in rows:
        if not isinstance(row,dict) or row.get('isin') not in ids or row['isin'] in seen: raise ValueError('Uneindeutige Zuordnung')
        seen.add(row['isin'])
        attempts=row.get('attempts')
        if type(attempts) is not int or not 1<=attempts<=2: raise ValueError('Versuchszahl ungültig')
        raw=row.get('draft','')
        observation=parse_draft(raw,row['isin'],now) if raw else None
        code=('PARTIAL' if observation['missingFields'] else 'COMPLETE') if observation else row.get('code')
        if not isinstance(code,str) or code not in CODES or (not observation and code in ('COMPLETE','PARTIAL')): raise ValueError('Unbekannter oder unbelegter Lesestatus')
        results.append(dict(isin=row['isin'],code=code,attempts=attempts,observation=observation,
                            matchedCurrentList=row['isin'] in current))
    safe_events=[]
    for e in events:
        if not isinstance(e,dict) or e.get('isin') not in ids or not isinstance(e.get('code'),str) or e.get('code') not in CODES or type(e.get('attempt')) is not int or not 1<=e['attempt']<=2: raise ValueError('Ungültiger Fehlereintrag')
        at=timestamp(e.get('at'))
        if at.year<2020 or (now-at).total_seconds() < -60: raise ValueError('Protokollzeit ungültig')
        safe_events.append(dict(isin=e['isin'],code=e['code'],attempt=e['attempt'],at=at.isoformat()))
    return dict(batchId=batch,revision=revision,appVersionCode=version,listUploadedAt=uploaded.isoformat(),listSource=source,isins=ids,results=results,events=safe_events,
                receivedAt=now.isoformat(),verified=False,tradeApproved=False,realOrders=False,
                scope='unverified-app-observations-not-market-inputs')


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_android_read_runs (
        batch_id TEXT PRIMARY KEY, received_at TIMESTAMPTZ NOT NULL DEFAULT now(), payload JSONB NOT NULL)''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_android_read_runs_time ON bob_android_read_runs(received_at DESC)')


def handle(conn,payload):
    if not isinstance(payload,dict): raise ValueError('Ungültige Anfrage')
    if payload.get('action')=='read':
        rows=conn.execute('SELECT payload FROM bob_android_read_runs ORDER BY received_at DESC LIMIT 20').fetchall()
        return dict(ok=True,runs=[r[0] for r in rows],verified=False,tradeApproved=False)
    if payload.get('action')!='save': raise ValueError('Unbekannte Aktion')
    run=payload.get('run')
    if not isinstance(run,dict): raise ValueError('Leselauf fehlt')
    batch=run.get('batchId');revision=run.get('revision')
    if not isinstance(batch,str) or not re.fullmatch('[a-f0-9]{32}',batch) or type(revision) is not int or not 1<=revision<=10000: raise ValueError('Leselauf-Kennung fehlt')
    key=f'{batch}:{revision}'
    digest=hashlib.sha256(json.dumps(run,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    prior=conn.execute('SELECT payload FROM bob_android_read_runs WHERE batch_id=%s',(key,)).fetchone()
    if prior:
        if prior[0].get('transferHash')!=digest: raise ValueError('Speicherversion widerspricht gespeichertem Lauf')
        return dict(ok=True,saved=True,batchId=batch,revision=revision,duplicate=True,verified=False,tradeApproved=False)
    row=conn.execute('SELECT payload FROM bob_paper_products WHERE id=1').fetchone()
    result=prepare(run,row[0] if row else {})
    result['transferHash']=digest
    conn.execute('''INSERT INTO bob_android_read_runs(batch_id,payload) VALUES(%s,%s::jsonb)
        ON CONFLICT(batch_id) DO NOTHING''',(key,json.dumps(result)))
    stored=conn.execute('SELECT payload FROM bob_android_read_runs WHERE batch_id=%s',(key,)).fetchone()
    if not stored or stored[0].get('transferHash')!=digest: raise ValueError('Speicherung nicht bestätigt')
    return dict(ok=True,saved=True,batchId=batch,revision=revision,verified=False,tradeApproved=False)


def status(conn):
    """Bounded read-only AI/guardian diagnosis; no broker account data or raw text."""
    rows=conn.execute('SELECT payload FROM bob_android_read_runs ORDER BY received_at DESC LIMIT 5').fetchall()
    runs=[]
    for row in rows:
        r=row[0]
        runs.append(dict(batchId=r['batchId'],revision=r['revision'],receivedAt=r['receivedAt'],
            appVersionCode=r.get('appVersionCode'),listUploadedAt=r['listUploadedAt'],listSource=r.get('listSource','bob-saved-list'),requested=len(r['isins']),
            results=[dict(isin=x['isin'],code=x['code'],attempts=x['attempts'],
                missingFields=(x.get('observation') or {}).get('missingFields',list(REQUIRED)),
                matchedCurrentList=x['matchedCurrentList']) for x in r['results']],events=r['events'][-12:]))
    return dict(status='observed' if runs else 'not-observed',readOnly=True,runs=runs,
                scope='unverified-app-reader-results-not-trade-proof')
