"""Pure, non-trading comparison of AI scraped public fields to cached issuer evidence.

No new network requests, no DB writes, no quote timestamp renewal. In particular,
matching an AI field does not promote it to executable price evidence.
"""
import math
import re

def _number(raw):
    if isinstance(raw, bool) or not isinstance(raw, str):
        return None
    # Conservative interpretation of German source numbers; do not infer
    # missing decimals, units, or mixed locale/ambiguous values.
    text=raw.strip()
    m=re.match(r'^(?:([0-9]{1,3}(?:\.[0-9]{3})+)(?:,([0-9]+))?|([0-9]+)(?:,([0-9]+))?)(?=$|\s)',text)
    if not m:
        return None
    if m[1]:
        integer=m[1].replace('.','')
        decimals=m[2] or ''
    else:
        integer=m[3]
        decimals=m[4] or ''
    try:
        return float(integer + ('.'+decimals if decimals else ''))
    except ValueError:
        return None


def _direction(raw):
    if not isinstance(raw,str):
        return None
    v=raw.strip().casefold()
    if v in ('put','short','bear','verkauf'):
        return 'SHORT'
    if v in ('call','long','bull','kauf'):
        return 'LONG'
    return None


def compare(research, issuer):
    """Only an already-cached independently identified issuer observation counts."""
    out=dict(state='reference-unavailable', matches=[], mismatches=[], unknown=[],
             researchOnly=True, tradeApproved=False, eligible=False,
             executableQuoteVerified=False, originalQuoteTimeVerified=False)
    if not isinstance(research,dict) or research.get('state')!='unverified-research':
        return out
    isin=research.get('isin')
    if (not isinstance(issuer,dict) or issuer.get('isin')!=isin
            or issuer.get('productVerified') is not True
            or issuer.get('sourceFailure') or issuer.get('quoteFailureCode')):
        return out
    metadata=issuer.get('metadata') or {}
    fields=research.get('fields') or {}
    if not isinstance(metadata,dict) or not isinstance(fields,dict):
        return out
    direction=_direction(fields.get('direction'))
    issuer_direction=metadata.get('direction')
    if direction is None or issuer_direction not in ('LONG','SHORT'):
        out['unknown'].append('direction')
    elif direction==issuer_direction:
        out['matches'].append('direction')
    else:
        out['mismatches'].append('direction')
    price=_number(fields.get('knockOut'))
    issuer_ko=metadata.get('ko')
    if price is None or isinstance(issuer_ko,bool) or not isinstance(issuer_ko,(int,float)) or not math.isfinite(issuer_ko):
        out['unknown'].append('knockOut')
    elif math.isclose(price,issuer_ko,rel_tol=0,abs_tol=0.0001):
        out['matches'].append('knockOut')
    else:
        out['mismatches'].append('knockOut')
    out['state']=('mismatch' if out['mismatches'] else
                  'static-fields-match' if len(out['matches'])==2 else 'incomplete')
    out['issuerEvidenceSource']=issuer.get('source') if isinstance(issuer.get('source'),str) else None
    out['issuerObservationAt']=issuer.get('quoteAt') or (issuer.get('chartEvidence') or {}).get('pointAt')
    out['note']='Nur Vergleich vorhandener Emittentenwerte. Kein Originalkurs-/DEGIRO-Handelsnachweis.'
    return out
