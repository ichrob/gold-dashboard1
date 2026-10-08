"""Extractive overview across supplied captions. No invented paraphrases or visual claims."""
import bisect
import re

TOPICS = (
    ('overview', 'Einordnung', r'gold|xau|zusammenfass|fazit|overall|in summary'),
    ('bullish', 'Bullische Aussagen und Bedingungen', r'bull|aufwärts|steigen|anstieg|upside|rally|higher'),
    ('bearish', 'Bärische Aussagen und Bedingungen', r'bär|bear|abwärts|fallen|rückgang|downside|lower|decline'),
    ('levels', 'Kursmarken und Ziele', r'unterstütz|widerstand|support|resistance|retracement|kursziel|target|niveau|level'),
    ('conditions', 'Bedingungen und Gegenargumente', r'\bwenn\b|\bfalls\b|solange|ungültig|invalidation|\bunless\b|\bif\b|provided|break'),
    ('horizon', 'Genannter Zeithorizont', r'heute|morgen|intraday|kurzfrist|langfrist|woche|monat|today|tomorrow|short.term|long.term|week|month'),
)


def overview(segments, language):
    parts=[];offsets=[];times=[];length=0
    for segment in segments:
        text=re.sub(r'\s+', ' ',segment['text']).strip()
        if not text:continue
        offsets.append(length);times.append(int(segment['at']));parts.append(text);length+=len(text)+1
    body=' '.join(parts)
    if language.split('-')[0] not in ('de','en'):return None
    candidates=[]
    # Sentence punctuation only at whitespace; decimal price levels remain intact.
    for match in re.finditer(r'.+?(?:[.!?](?=\s|$)|$)',body):
        text=match[0].strip();words=len(text.split())
        if not 5<=words<=110:continue
        if re.search(r'subscribe|affiliate|mitgliedschaft|abonnier|broker|discount|rabatt|sponsor',text,re.I):continue
        tags=[key for key,_,pattern in TOPICS if re.search(pattern,text,re.I)]
        if not tags:continue
        start=match.start()+len(match[0])-len(match[0].lstrip())
        at=times[max(0,bisect.bisect_right(offsets,start)-1)]
        candidates.append({'text':text,'at':at,'tags':tags,'words':words,'position':start})
    sections=[];evidence=[];chosen={};budget=330
    for key,label,_ in TOPICS:
        relevant=[c for c in candidates if key in c['tags']]
        def score(c):
            numeric=bool(re.search(r'\b(?:[1-9]\d{3,5}|[1-9][.,]\d{3})(?!\d)',c['text']))
            condition=bool(re.search(r'\b(wenn|falls|solange|unless|if)\b',c['text'],re.I))
            return (20*numeric if key=='levels' else 0)+(8*condition+4*numeric if key=='conditions' else 0)+len(c['tags'])+2*bool(re.search(r'zusammenfass|fazit|in summary|overall',c['text'],re.I))
        relevant.sort(key=lambda c:(-score(c),c['position']))
        refs=[]
        for c in relevant:
            # One complete source sentence per topic; can reuse a shared condition.
            if c['position'] not in chosen and c['words']>budget:continue
            if c['position'] not in chosen:
                ref='e'+str(len(evidence)+1);chosen[c['position']]=ref
                evidence.append({'id':ref,'text':c['text'],'at':c['at']});budget-=c['words']
            refs.append(chosen[c['position']]);break
        sections.append({'key':key,'label':label,'evidenceIds':refs,'status':'found' if refs else 'not_identified'})
    moments=[]
    for section in sections:
        if section['key'] not in ('overview','levels','conditions'):continue
        for ref in section['evidenceIds']:
            e=next(e for e in evidence if e['id']==ref)
            if all(abs(e['at']-m['at'])>=15 for m in moments):moments.append({'at':e['at'],'label':section['label'],'evidenceId':ref})
    return {'version':1,'kind':'extractive','title':'Strukturierter Transkript-Überblick',
        'method':'Das gesamte gelieferte Transkript wurde nach Themen durchsucht. Die Übersicht verwendet ausgewählte vollständige Originalsätze; sie ist keine frei formulierte KI-Gesamtzusammenfassung. Wichtige Aussagen können fehlen.',
        'scope':'Nur gesprochener Inhalt; eingeblendete Charts und Bilder wurden nicht ausgewertet.',
        'sourceWords':len(body.split()),'sections':sections,'evidence':evidence,'moments':moments[:3]}
