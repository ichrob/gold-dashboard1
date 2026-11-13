"""Fixed CHF Classic contract model for isolated handset comparisons only.

No network, quotes, clocks, eligibility or general ranking are modified.
Explicit matched secondary currency treatment supplements verified SG terms.
"""
import copy
import math
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo


def attach(quote, now):
    if not isinstance(quote, dict) or quote.get('productModel'):
        return quote
    from product_quotes import valid_isin
    from sg_chf_contract import valid_source
    isin=quote.get('isin')
    m=quote.get('metadata') or {}
    terms=quote.get('conditions') or {}
    backup=quote.get('termsBackup') or {}
    proof=backup.get('currencyTreatment') or {}
    if (not isinstance(isin,str) or not valid_isin(isin)
            or quote.get('productVerified') is not True or quote.get('importActive') is not True
            or quote.get('sourceDisabled') or quote.get('sourceFailure') or quote.get('quoteFailureCode')
            or m.get('status') != 1 or m.get('tradingHalted')
            or m.get('currency') != 'CHF' or m.get('issuerExchangeCode') != 'CBSW'
            or m.get('classificationId') != 43 or m.get('simpleTurbo') is not True
            or m.get('quantoState') != 'unknown' or m.get('termsFixed') is not True
            or m.get('underlyingType') != 'SPOT' or m.get('underlying') != 'XAU/USD'
            or m.get('direction') not in ('LONG','SHORT')
            or backup.get('state') != 'active' or proof.get('quanto') is not False
            or any(proof.get(k) for k in ('conflict','revoked','ocrCorrection'))
            or proof.get('isin') != isin
            or not (proof.get('source') == 'https://www.finanzen.ch/derivate/'+isin.lower()
                or (proof.get('evidenceKind') == 'sg-kid' and valid_source(proof.get('source'),isin)
                    and isinstance(proof.get('documentSha256'),str) and len(proof['documentSha256'])==64))
            or proof.get('type') != 'Knock-out Warrant'
            or any(proof.get(k) != m.get(k) for k in
                   ('direction','currency','underlying','ratio','ko','strike'))):
        return quote
    try:
        reviewed=datetime.fromisoformat(proof['reviewedAt'].replace('Z','+00:00'))
        if reviewed.tzinfo is None or not 0 <= (now-reviewed).total_seconds() <= 8*3600:
            return quote
        local=now.astimezone(ZoneInfo('Europe/Zurich'))
        if local.weekday() >= 5 or not 8 <= local.hour < 22:
            return quote
        maturity=datetime.strptime(proof['maturity'],'%d.%m.%Y').date()
        if maturity < local.date() or terms.get('maturity',{}).get('value') != proof['maturity']:
            return quote
        issuer='https://www.sg-zertifikate.ch/product-details/'+isin.lower()
        for k in ('ko','strike','ratio'):
            value=m[k]
            if type(value) not in (int,float) or not math.isfinite(value) or value <= 0:
                return quote
        if m['ko'] != m['strike']:
            return quote
        for k in ('ko','strike'):
            term=terms[k]
            if (term.get('conditionVerified') is not True or term.get('fixed') is not True
                    or term.get('source') != issuer or term.get('value') != m[k]
                    or term.get('conflict') or term.get('revoked')
                    or datetime.strptime(term['validUntil'],'%Y-%m-%d').date() != maturity):
                return quote
        end=datetime.combine(local.date(),time(22),tzinfo=local.tzinfo)
    except (KeyError,ValueError,TypeError,OverflowError):
        return quote
    out=copy.deepcopy(quote)
    out['productModel']=dict(isin=isin,underlying='XAU/USD',direction=m['direction'],
        ratio=m['ratio'],strike=m['strike'],ko=m['ko'],classification=43,
        verifiedSimpleTurbo=True,tradingEndAt=end.astimezone(timezone.utc).isoformat(),
        currencyModelEvidence=copy.deepcopy(proof),researchOnly=True,scope='handset-comparison')
    return out


def prepare(quote, now):
    """Expose bounded private failure evidence without guessing missing terms."""
    out=attach(quote,now)
    if not isinstance(out,dict) or (out.get('metadata') or {}).get('currency') != 'CHF':
        return out
    out=copy.deepcopy(out)
    meta=out.get('metadata') or {}
    backup=out.get('termsBackup') or {}
    proof=backup.get('currencyTreatment') or {}
    out['handsetModelCheck']=dict(
        modelAttached=bool(out.get('productModel')),
        issuerContract=out.get('issuerContractCheck'),evidenceKind=proof.get('evidenceKind'),
        backupState=backup.get('state'),backupCode=backup.get('code'),
        evidencePresent=bool(proof),reviewedAt=proof.get('reviewedAt'),
        classification=meta.get('classificationId'),fixedTerms=meta.get('termsFixed'),
        quantoState=meta.get('quantoState'),importActive=out.get('importActive'),
        quoteFailureCode=out.get('quoteFailureCode'),
        matchingFields=[k for k in ('direction','currency','underlying','ratio','ko','strike')
                        if k in proof and proof[k]==meta.get(k)])
    return out
