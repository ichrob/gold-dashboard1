"""Authenticated corrections of screenshot identity lists, preserving provenance."""
import copy
import hashlib
import json
from datetime import datetime, timezone
from product_quotes import valid_isin
import broker_venue_evidence


def version(feed):
    return hashlib.sha256(json.dumps([feed.get('listUploadedAt'),
        feed.get('listCorrection'), sorted(p.get('isin','') for p in feed.get('products',[]))],
        sort_keys=True).encode()).hexdigest()


def preview(feed):
    return dict(ok=True, version=version(feed), corrected=bool(feed.get('listCorrection')), listUploadedAt=feed.get('listUploadedAt'),
        products=[{k:p.get(k) for k in ('isin','name','productDirection','direction','currency','listingVenue')}
                  for p in feed.get('products',[])])


def prepare(feed, payload, now=None):
    now=now or datetime.now(timezone.utc)
    if payload.get('reviewed') is not True:
        raise ValueError('Angaben am Originalbild bestätigen')
    if payload.get('version')!=version(feed):
        raise ValueError('Liste wurde inzwischen geändert. Bitte neu laden.')
    if feed.get('listOrigin')!='degiro-screenshot' or not feed.get('listUploadedAt'):
        raise ValueError('Original-Listenstand fehlt')
    rows=payload.get('products')
    if not isinstance(rows,list) or not 1<=len(rows)<=12:
        raise ValueError('Ein bis zwölf Produkte erforderlich')
    old={p['isin']:p for p in feed['products']}
    out=copy.deepcopy(feed); products=[]; venues=[]; seen=set()
    for row in rows:
        isin=row.get('isin',''); direction=row.get('direction'); currency=row.get('currency')
        venue=row.get('venue','')
        if not valid_isin(isin) or isin in seen or direction not in ('LONG','SHORT') or currency not in ('EUR','CHF'):
            raise ValueError('ISIN, Richtung oder Währung ungültig / doppelt')
        if venue not in ('', 'Societe Generale OTC', 'BNP OTC'):
            raise ValueError('Handelsplatz nicht unterstützt')
        seen.add(isin)
        prior=old.get(isin,{})
        # Never carry price/KO/evidence to a different identity, direction or currency.
        compatible=(prior.get('productDirection',prior.get('direction'))==direction and
                    prior.get('currency') in (None,currency))
        product=copy.deepcopy(prior) if compatible else {}
        product.update(isin=isin, name=prior.get('name') or isin, productDirection=direction,
                       direction=direction, currency=currency, listingVenue=venue)
        product['isinConfirmed']=False
        products.append(product)
    out['products']=products
    out['references']=[r for r in (out.get('references') or []) if isinstance(r,dict) and r.get('isin') in seen]
    out['fixedBarriers']={k:v for k,v in (out.get('fixedBarriers') or {}).items() if k in seen}
    # Retain a private rollback record; never publish this payload in logs.
    out['listCorrection']=dict(at=now.isoformat(), previousVersion=version(feed),
        previousProducts=feed['products'], observedMinute=payload.get('observedMinute'))
    for row in rows:
        if row.get('venue')=='Societe Generale OTC':
            venues.append(broker_venue_evidence.validate(dict(isin=row['isin'], reviewed=True,
                venue=row['venue'],currency=row['currency'], observedMinute=payload.get('observedMinute'),
                imageReference=payload.get('imageReference')),out,now))
    return out,venues


def handle(conn,payload):
    row=conn.execute('SELECT payload FROM bob_paper_products WHERE id=1 FOR UPDATE').fetchone()
    feed=row[0] if row else {}
    if payload.get('action')=='read':return preview(feed)
    if payload.get('action')!='save':raise ValueError('Unbekannte Aktion')
    out,venues=prepare(feed,payload)
    conn.execute('UPDATE bob_paper_products SET payload=%s::jsonb,synced_at=now() WHERE id=1',(json.dumps(out),))
    for record in venues:
        conn.execute("""INSERT INTO bob_broker_venue_evidence(isin,payload) VALUES(%s,%s::jsonb)
            ON CONFLICT(isin) DO UPDATE SET payload=EXCLUDED.payload""",(record['isin'],json.dumps(record)))
    conn.execute('UPDATE subscriptions SET selection_evidence=NULL, product_selection=NULL WHERE selection_evidence IS NOT NULL OR product_selection IS NOT NULL')
    return {**preview(out),'saved':True}
