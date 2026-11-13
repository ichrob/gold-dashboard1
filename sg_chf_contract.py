"""Free SG KID contract corroboration; never a quote or trading permission."""
import copy
import hashlib
import io
import re
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ORIGIN = 'https://www.sg-zertifikate.ch/'
API = ORIGIN+'EmcWebApi/api/'
_CACHE = {}
_LOCK = threading.Lock()
MONTHS = {'Januar':1,'Februar':2,'März':3,'April':4,'Mai':5,'Juni':6,
          'Juli':7,'August':8,'September':9,'Oktober':10,'November':11,'Dezember':12}


def valid_source(url, isin):
    return isinstance(url,str) and bool(re.fullmatch(re.escape(API+'Downloads/document/'+isin+'_KID/')+
                                                    r'[A-Za-z0-9+/]+={0,2}',url))


def parse_text(text, isin, source, digest, now):
    from product_quotes import valid_isin
    text = ' '.join(text.split())
    if (not valid_isin(isin) or not valid_source(source,isin)
            or not re.fullmatch('[a-f0-9]{64}',digest)
            or set(re.findall(r'\b[A-Z]{2}[A-Z0-9]{9}\d\b',text)) != {isin}
            or 'Basisinformationsblatt' not in text
            or 'HERSTELLER: Société Générale' not in text
            or 'Basiswert: Gold (unallocated gold) gemäß den Regeln der LBMA (Gold)' not in text
            or 'Währung des Basiswerts: US-Dollar (USD)' not in text
            or 'Währung des Produkts (Emissionswährung): Schweizer Franken (CHF)' not in text
            or 'Die Umrechnung in die Währung des Produkts erfolgt auf Basis des maßgeblichen Wechselkurses am Bewertungstag.' not in text):
        raise ValueError('KID_IDENTITY_MISMATCH')
    def unique(pattern):
        values=re.findall(pattern,text)
        if len(values)!=1: raise ValueError('KID_TERMS_MISSING_OR_AMBIGUOUS')
        return values[0]
    side=unique(r'Classic TURBO-Optionsscheine \((Call|Put)\) bezogen auf Gold \(Non-Quanto\)')
    if unique(r'\bTyp: (Call|Put)\b') != side: raise ValueError('KID_DIRECTION_MISMATCH')
    def number(label):
        return float(unique(re.escape(label)+r' ([0-9]+(?:\.[0-9]{3})*,[0-9]+)\b').replace('.','').replace(',','.'))
    def date(label):
        day,month,year=unique(re.escape(label)+r' (\d{1,2})\. ([A-Za-zä]+) (\d{4})')
        return datetime(int(year),MONTHS[month],int(day),tzinfo=timezone.utc).date()
    issued=date('ERSTELLUNGSDATUM DES BASISINFORMATIONSBLATTS:')
    exercise=date('Ausübungstag:')
    settlement=date('Fälligkeitstag:')
    if issued>now.date() or exercise<now.date() or settlement<exercise:
        raise ValueError('KID_INVALID_DATES')
    return dict(isin=isin,source=source,reviewedAt=now.isoformat(),documentDate=issued.isoformat(),
        documentSha256=digest,evidenceKind='sg-kid',quanto=False,
        direction='LONG' if side=='Call' else 'SHORT',type='Knock-out Warrant',
        underlying='XAU/USD',currency='CHF',ratio=number('Bezugsverhältnis:'),
        ko=number('Knock-out Barriere: USD'),strike=number('Basispreis: USD'),
        # SG metadata calls the last exercise date "maturity"; settlement is later.
        maturity=exercise.strftime('%d.%m.%Y'),settlementDate=settlement.isoformat())


def fetch(isin):
    from product_quotes import issuer_json, valid_isin
    if not valid_isin(isin): return dict(state='unavailable',code='INVALID_ISIN')
    with _LOCK:
        cached=_CACHE.get(isin)
        if cached and time.monotonic()<cached[0]: return copy.deepcopy(cached[1])
        try:
            product=issuer_json(API+'Products/'+isin,ORIGIN,timeout=8)
            if (product.get('Isin')!=isin or type(product.get('Id')) is not int
                    or product['Id']<=0 or product.get('ProductClassificationId')!=43
                    or product.get('Currency')!='CHF' or product.get('ExchangeCode')!='CBSW'
                    or product.get('AssetCurrency')!='USD' or product.get('AssetNMP')!='XAUUSD'):
                raise ValueError('KID_IDENTITY_MISMATCH')
            docs=issuer_json(API+'Downloads/'+str(product['Id']),ORIGIN,timeout=8)
            if not isinstance(docs,list) or len(docs)>30: raise ValueError('KID_DOCUMENT_LIST_INVALID')
            links=[ORIGIN+d['Href'] for d in docs if isinstance(d,dict)
                   and d.get('Name')=='Basisinformationsblatt' and d.get('LinkType')==0
                   and d.get('FileType')==0 and isinstance(d.get('Href'),str)]
            if len(links)!=1 or not valid_source(links[0],isin): raise ValueError('KID_DOCUMENT_LINK_INVALID')
            req=Request(links[0],headers={'User-Agent':'Bob/1.7 public product research','Accept':'application/pdf'})
            with urlopen(req,timeout=8) as response:
                if response.url!=links[0]: raise ValueError('KID_UNEXPECTED_REDIRECT')
                body=response.read(500001)
            if len(body)>500000 or not body.startswith(b'%PDF-'): raise ValueError('KID_INVALID_PDF')
            from pypdf import PdfReader
            reader=PdfReader(io.BytesIO(body),strict=True)
            if reader.is_encrypted or not 1<=len(reader.pages)<=5: raise ValueError('KID_INVALID_PDF')
            text=reader.pages[0].extract_text()
            if len(text)>30000: raise ValueError('KID_INVALID_PDF')
            proof=parse_text(text,isin,links[0],hashlib.sha256(body).hexdigest(),datetime.now(timezone.utc))
            result=dict(state='active',source='Société Générale · Basisinformationsblatt',currencyTreatment=proof)
        except Exception as exc:
            code=('HTTP_'+str(exc.code) if isinstance(exc,HTTPError) else str(exc)
                  if isinstance(exc,ValueError) and re.fullmatch('[A-Z_]+',str(exc)) else 'KID_UNAVAILABLE')
            result=dict(state='unavailable',code=code,source='Société Générale · Basisinformationsblatt')
        if len(_CACHE)>=128: _CACHE.pop(next(iter(_CACHE)))
        _CACHE[isin]=(time.monotonic()+900,result)
        return copy.deepcopy(result)


def apply(primary, isin):
    m=primary.get('metadata') or {}
    if (primary.get('isin')!=isin or primary.get('productVerified') is not True
            or primary.get('sourceDisabled') or primary.get('sourceFailure')
            or m.get('status')!=1 or m.get('currency')!='CHF' or m.get('issuerExchangeCode')!='CBSW'
            or m.get('classificationId')!=43 or m.get('simpleTurbo') is not True
            or m.get('quantoState')!='unknown' or m.get('underlyingType')!='SPOT'):
        return primary
    backup=fetch(isin)
    out=copy.deepcopy(primary)
    out['issuerContractCheck']={k:v for k,v in backup.items() if k!='currencyTreatment'}
    if backup.get('state')!='active': return out
    proof=backup['currencyTreatment']
    if (any(proof.get(k)!=m.get(k) for k in ('direction','currency','underlying','ratio','ko','strike'))
            or proof.get('maturity')!=(primary.get('conditions') or {}).get('maturity',{}).get('value')):
        out['issuerContractCheck'].update(state='rejected',code='KID_TERMS_MISMATCH')
        out['termsBackup']=dict(state='rejected',code='KID_TERMS_MISMATCH')
        return out
    out['termsBackup']=copy.deepcopy(backup)
    return out
