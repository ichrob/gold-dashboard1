"""Conservative metadata-only extraction from SG's PUBLIC product markdown.

Research hints only. This never certifies a live quote, source clock,
knock-out trading status, broker venue, or order suitability.
"""
import re

_VALUES = (
    ("direction", "Typ"),
    ("knockOut", "Knock-Out-Barriere"),
    ("underlying", "Basiswert"),
    ("currency", "Währung"),
    ("ratio", "Bezugsverhältnis"),
)

def _line(text):
    return re.sub(r'\s+', ' ', text.strip().strip('*').strip('_')).strip()

def extract_public_fields(markdown):
    """Extract labels and immediately adjacent values, never guess missing ones."""
    if not isinstance(markdown, str) or len(markdown) > 500000:
        return {}
    lines = [_line(x) for x in markdown.splitlines()]
    try:
        start = next(i for i, text in enumerate(lines) if text.casefold().lstrip('# ').strip() == 'stammdaten')
    except StopIteration:
        return {}
    values = {}
    for key, name in _VALUES:
        pattern = re.compile(r'^' + re.escape(name) + r'(?:\s+info_outlined)?$', re.I)
        for i in range(start+1, min(len(lines),start+150)):
            if lines[i].startswith('## ') and i > start+1:
                break
            if not pattern.fullmatch(lines[i]):
                continue
            upcoming = next((x for x in lines[i+1:i+5] if x and x.casefold()!='info_outlined'), None)
            if upcoming and not upcoming.startswith(('#', '[', '<')) and len(upcoming) <= 100:
                values[key] = upcoming
            break
    if values.get('direction','').casefold() not in ('call','put','long','short'):
        values.pop('direction',None)
    elif values['direction'].casefold() in ('put','short'):
        values['direction']='SHORT'
    else:
        values['direction']='LONG'
    if not re.fullmatch(r'[0-9]{1,3}(?:\.[0-9]{3})*(?:,[0-9]{1,4})?\s*(?:USD|EUR|CHF)|[0-9]{1,6}(?:,[0-9]{1,4})?\s*(?:USD|EUR|CHF)',values.get('knockOut','')):
        values.pop('knockOut',None)
    if values.get('underlying','').casefold() not in ('gold','gold spot','gold future','gold futures'):
        values.pop('underlying',None)
    if values.get('currency','').upper() not in ('EUR','CHF','USD'):
        values.pop('currency',None)
    if not re.fullmatch(r'[0-9]{1,5}:[1-9][0-9]{0,4}',values.get('ratio','')):
        values.pop('ratio',None)
    # Bid/ask and quoteTime deliberately absent: they require separate
    # original paired issuer evidence with independent clock checking.
    return values
