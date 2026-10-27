"""Read-only price study for the user's last saved list, independent of trades."""
import hashlib
import json
from datetime import datetime, timezone
from statistics import median
import product_comparison_worker as worker
import product_trade_history as history


def init(conn):
    import precision_learning
    precision_learning.init(conn)
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_list_price_anchors (
        isin TEXT PRIMARY KEY, payload JSONB NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_list_price_pairs (
        identity TEXT NOT NULL, isin TEXT NOT NULL, quote_at TIMESTAMPTZ NOT NULL,
        evidence JSONB NOT NULL, PRIMARY KEY(identity,quote_at))''')
    conn.execute('CREATE INDEX IF NOT EXISTS bob_list_price_time ON bob_list_price_pairs(isin,quote_at DESC)')


def listed(feed):
    from product_quotes import valid_isin
    if not isinstance(feed,dict) or feed.get('listOrigin')!='degiro-screenshot':return set()
    # Observation membership survives the day's trading approval expiry.
    return {p['isin'] for p in (feed.get('products') or [])[:12]
            if isinstance(p,dict) and valid_isin(p.get('isin'))}


def anchor(quote,spots,now):
    from hybrid_product_price import model_for
    model=model_for(quote,now)
    # Native CHF SG instruments use the same explicit non-quanto metadata.
    m=quote.get('metadata') or {}
    if not model and (quote.get('productVerified') is True and quote.get('importActive') is True
        and quote.get('sourceUrl')=='https://www.sg-zertifikate.ch/product-details/'+str(quote.get('isin','')).lower()
        and not quote.get('sourceFailure') and not quote.get('sourceDisabled')
        and m.get('status')==1 and not m.get('tradingHalted')
        and m.get('issuerExchangeCode')=='CBSW' and m.get('currency')=='CHF'
        and m.get('underlying')=='XAU/USD' and m.get('underlyingType')=='SPOT'
        and m.get('simpleNonQuantoTurbo') is True and m.get('classificationId') in (43,45,47)):
        model=dict(m,isin=quote['isin'])
    if not model:return None
    from hybrid_product_price import observations
    candidates=[quote]+[dict(q,found=True,fresh=True,productVerified=True)
        for q in observations(quote) if q.get('priceKind')=='market-observation']
    for candidate in candidates:
        candidate_currency=candidate.get('currency')
        fx=(spots or {}).get('usd_chf_meta' if candidate_currency=='CHF' else 'usd_eur_meta') or {}
        trial={k:model.get(k) for k in ('isin','direction','ratio','strike','ko')}
        trial.update(currency=candidate_currency,bid=candidate.get('bid'),goldReference=(spots or {}).get('xaus'),
            fxReference=fx.get('rate'),referenceAt=candidate.get('bidAt'),referenceConfirmed=True,simpleSpotTurbo=True)
        if candidate_currency==m.get('currency') and worker.comparison(trial,spots,candidate,now):
            quote=candidate;break
    else:return None
    product={k:model[k] for k in ('isin','direction','ratio','strike','ko')}
    currency=quote.get('currency')
    fx=(spots or {}).get('usd_chf_meta' if currency=='CHF' else 'usd_eur_meta') or {}
    product.update(currency=currency,bid=quote.get('bid'),goldReference=(spots or {}).get('xaus'),
                   fxReference=fx.get('rate'),referenceAt=quote.get('bidAt'),
                   referenceConfirmed=True,simpleSpotTurbo=True)
    # Same native bid and source-time checks as the active-trade comparison.
    row=worker.comparison(product,spots,quote,now)
    if not row:return None
    return dict(product=product,source=row['source'],createdAt=now.isoformat(),
                observation={k:quote.get(k) for k in ('isin','currency','bid','ask','bidAt','askAt','source','found','fresh','productVerified','priceKind')})


def sample(previous,current,quote,spots,now):
    if not previous:return None
    old=previous['product'];new=current['product']
    if previous['source']!=current['source'] or any(old.get(k)!=new.get(k) for k in
        ('isin','currency','direction','ratio','strike','ko')):return None
    age=(now-history.clock(previous['createdAt'])).total_seconds()
    if not 0<age<=1800:return None
    row=worker.comparison(old,spots,quote,now)
    ref=history.clock(old['referenceAt'])
    if not row or not ref or row['at']<=ref.timestamp()*1000:return None
    identity=hashlib.sha256(json.dumps([worker.model_key(old),previous['source']],sort_keys=True).encode()).hexdigest()
    return dict(row,identity=identity,isin=old['isin'])


def metrics(rows):
    if not rows:return dict(count=0,status='waiting')
    rows=sorted(rows,key=lambda r:r['at'])
    latest=rows[-1]
    group=[r for r in rows if r['identity']==latest['identity']]
    result=dict(count=len(rows),evaluationCount=len(group),lastAt=latest['at'],currency=latest['currency'],status='collecting')
    if len(group)<5 or group[-1]['at']-group[0]['at']<300000:return result
    cut=max(3,int(len(group)*.6));train=group[:cut];test=group[cut:]
    offset=median(r['quoted']-r['estimated'] for r in train)
    raw=sum(abs(r['quoted']-r['estimated']) for r in test)/len(test)
    corrected=sum(abs(r['quoted']-r['estimated']-offset) for r in test)/len(test)
    scale=median(r['estimated'] for r in train)
    dispersion=median(abs(r['quoted']-r['estimated']-offset) for r in train)
    useful=raw>1e-8 and corrected<raw*.9 and abs(offset)<=scale*.03 and dispersion<=scale*.01
    return dict(result,rawMae=raw,correctedMae=corrected,offset=offset,
                validationCount=len(test),status='improved' if useful else 'rejected')


def summaries(conn,isins):
    out={}
    for isin in sorted(isins):
        total=conn.execute("SELECT count(*) FROM bob_list_price_pairs WHERE isin=%s AND quote_at>=now()-interval '30 days'",(isin,)).fetchone()[0]
        rows=conn.execute('''SELECT evidence FROM bob_list_price_pairs
            WHERE isin=%s AND quote_at>=now()-interval '30 days'
            AND identity=(SELECT identity FROM bob_list_price_pairs WHERE isin=%s ORDER BY quote_at DESC LIMIT 1)
            ORDER BY quote_at DESC LIMIT 1000''',(isin,isin)).fetchall()
        out[isin]=dict(metrics([r[0] for r in rows]),count=total)
        import precision_learning
        saved=conn.execute('SELECT payload FROM bob_list_price_anchors WHERE isin=%s',(isin,)).fetchone()
        if saved:
            out[isin]['automaticCorrection']=precision_learning.for_product(conn,saved[0]['product'],datetime.now(timezone.utc).timestamp()*1000)
    return out


def tick(db,bundle,quote_fetch,now):
    with db() as conn:
        row=conn.execute('SELECT payload FROM bob_paper_products WHERE id=1').fetchone()
        feed=row[0] if row else {};isins=listed(feed)
        anchors={i:a for i,a in conn.execute('SELECT isin,payload FROM bob_list_price_anchors').fetchall()}
    for isin in sorted(isins):
        try:
            quote=quote_fetch(isin)
            current=anchor(quote,bundle.get('spots'),now)
            if not current:continue
            previous=anchors.get(isin)
            pair=sample(previous,current,current['observation'],bundle.get('spots'),now)
            replace=not previous or any(previous['product'].get(k)!=current['product'].get(k)
                for k in ('currency','direction','ratio','strike','ko')) or previous['source']!=current['source'] or (
                now-history.clock(previous['createdAt'])).total_seconds()>1800
            with db() as conn:
                fresh=conn.execute('SELECT payload FROM bob_paper_products WHERE id=1 FOR SHARE').fetchone()
                if not fresh or isin not in listed(fresh[0]) or fresh[0].get('listUploadedAt')!=feed.get('listUploadedAt'):continue
                if pair:
                    import precision_learning
                    precision_learning.observe(conn,previous['product'],pair)
                    import metric_quality
                    metric_quality.pnl_check(conn,'list:'+isin,previous['product'],pair,now.timestamp()*1000)
                    conn.execute('''INSERT INTO bob_list_price_pairs(identity,isin,quote_at,evidence)
                        VALUES(%s,%s,%s,%s::jsonb) ON CONFLICT DO NOTHING''',
                        (pair['identity'],isin,history.clock(current['observation']['bidAt']),json.dumps(pair)))
                if replace:
                    conn.execute('''INSERT INTO bob_list_price_anchors VALUES(%s,%s::jsonb)
                        ON CONFLICT(isin) DO UPDATE SET payload=EXCLUDED.payload''',(isin,json.dumps(current)))
                # Research evidence has no automatic age-based expiry.
                conn.execute('DELETE FROM bob_list_price_anchors WHERE NOT (isin=ANY(%s))',(list(isins),))
                conn.commit()
        except Exception as exc:
            print('BOB_LIST_PRICE_STUDY error='+type(exc).__name__,flush=True)
