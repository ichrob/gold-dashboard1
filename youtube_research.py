"""Read publicly exposed YouTube caption tracks; no login, proxy or challenge bypass."""
import html
import json
import re
import threading
import time
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from urllib.parse import urlparse, parse_qs, urlencode

_MAX = 2000000
_lock = threading.Lock()
_cache = {}
_manual = {}
_busy = threading.Semaphore(2)


def video_id(url):
    if not isinstance(url,str):raise ValueError('YouTube-Link fehlt')
    p=urlparse(url)
    if p.scheme!='https' or p.username or p.password or p.port not in (None,443):raise ValueError('HTTPS-YouTube-Link erforderlich')
    if p.hostname=='youtu.be':value=p.path.strip('/')
    elif p.hostname in ('youtube.com','www.youtube.com','m.youtube.com'):
        value=parse_qs(p.query).get('v',[''])[0] if p.path=='/watch' else p.path.split('/')[-1] if p.path.startswith(('/shorts/','/live/')) else ''
    else:raise ValueError('Nur direkte YouTube-Links sind erlaubt')
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}',value):raise ValueError('Ungültige YouTube-Video-ID')
    return value


def safe_url(url):
    p=urlparse(url)
    return p.scheme=='https' and p.hostname in ('www.youtube.com','youtube.com') and not p.username and not p.password and p.port in (None,443) and p.path in ('/watch','/api/timedtext','/results')


class Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        if not safe_url(newurl):raise ValueError('YouTube-Abruf umgeleitet; keine Anmeldung oder Umgehung')
        return super().redirect_request(req,fp,code,msg,headers,newurl)


def read_url(url):
    if not safe_url(url):raise ValueError('Unzulässige Untertitel-Adresse')
    req=urllib.request.Request(url,headers={'User-Agent':'Bob-GoldResearch/1.0 (public caption reader)'})
    with urllib.request.build_opener(Redirects()).open(req,timeout=10) as response:data=response.read(_MAX+1)
    if len(data)>_MAX:raise ValueError('Antwort zu groß')
    return data


def player_metadata(raw, identity):
    text=raw.decode('utf-8','replace')
    match=re.search(r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*',text)
    if not match:raise ValueError('Keine öffentlich lesbaren Videodaten')
    p=json.JSONDecoder().raw_decode(text[match.end():])[0]
    if p.get('playabilityStatus',{}).get('status')!='OK':raise ValueError('Video erfordert Anmeldung oder ist nicht verfügbar')
    if p.get('videoDetails',{}).get('videoId')!=identity:raise ValueError('Videozuordnung nicht bestätigt')
    return p


def parse_captions(raw):
    if not raw.strip():raise ValueError('Leere Untertitelantwort')
    segments=[]
    if raw.lstrip().startswith(b'{'):
        for row in json.loads(raw).get('events',[]):
            text=' '.join(x.get('utf8','') for x in row.get('segs',[]) if isinstance(x.get('utf8'),str))
            if text.strip():segments.append((float(row.get('tStartMs',0))/1000,text))
    else:
        if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('Ungültige Untertitel')
        root=ET.fromstring(raw)
        for row in root.iter():
            if row.tag in ('text','p'):
                stamp=float(row.get('start',0)) if row.tag=='text' else float(row.get('t',0))/1000
                segments.append((stamp,''.join(row.itertext())))
    out=[]
    for at,text in segments:
        text=re.sub(r'<[^>]*>','',html.unescape(text));text=re.sub(r'\s+',' ',text).strip()
        if not 0<=at<=86400 or len(text)>10000:raise ValueError('Ungültige Untertitelzeiten')
        if text and (not out or text!=out[-1]['text']):out.append({'at':at,'text':text})
    if not out or len(out)>30000 or len(' '.join(s['text'] for s in out))>200000:raise ValueError('Keine verwendbaren Untertitel')
    return out


def assess(segments, language, automatic=False):
    import gold_research as g
    text=' '.join(s['text'] for s in segments)
    if len(text.split())<40:raise ValueError('Transkript zu kurz für eine Inhaltsprüfung')
    supported=language.split('-')[0] in ('en','de')
    # Titles/thumbnails never count as transcript evidence.
    result=g.classify('',text,'Internet') if supported else dict(trend='UNKLAR',outlook='UNKLAR',horizon='unbekannt')
    moments=[]
    for s in segments:
        if re.search(r'\bgold\b|xau\s*/?\s*usd|goldpreis',s['text'],re.I):
            moments.append(int(s['at']))
            if len(moments)==3:break
    result.update(transcriptAnalyzed=True,transcriptWords=len(text.split()),transcriptLanguage=language,
        automaticCaptions=automatic,mentions=bool(re.search(r'\bgold\b|xau\s*/?\s*usd|goldpreis',text,re.I)),
        goldMoments=moments,coverage='Untertitel (automatische Textregeln)',
        reason=('Gesprochener Inhalt anhand '+('automatischer' if automatic else 'veröffentlichter')+' Untertitel regelbasiert geprüft. Keine Bild-/Chartanalyse und keine KI-Sprachanalyse. Erkennungsfehler möglich.' if supported else 'Untertitel abgerufen; Sprache wird noch nicht ausgewertet. Keine Richtungsstimme.'))
    if not supported:result['transcriptAnalyzed']=False
    return result


def analyze(url, fetch=read_url):
    identity=video_id(url);now=time.time()
    with _lock:
        saved=_cache.get(identity)
        if fetch is read_url and saved and now-saved[0]<3600:return dict(saved[1])
    if not _busy.acquire(blocking=False):raise ValueError('YouTube-Prüfung läuft bereits; bitte später erneut versuchen')
    try:
        p=player_metadata(fetch('https://www.youtube.com/watch?v='+identity),identity)
        d=p['videoDetails'];micro=p.get('microformat',{}).get('playerMicroformatRenderer',{})
        tracks=p.get('captions',{}).get('playerCaptionsTracklistRenderer',{}).get('captionTracks',[])
        tracks=[t for t in tracks if isinstance(t.get('baseUrl'),str) and t.get('languageCode','').split('-')[0] in ('en','de')]
        tracks.sort(key=lambda t:(t.get('kind')=='asr',t.get('languageCode','').split('-')[0]!='en'))
        if not tracks:raise ValueError('Keine öffentlich abrufbaren deutschen oder englischen Untertitel')
        track=tracks[0];caption_url=track['baseUrl']
        if not safe_url(caption_url) or urlparse(caption_url).path!='/api/timedtext' or parse_qs(urlparse(caption_url).query).get('v')!=[identity]:raise ValueError('Untertitel gehören nicht eindeutig zum Video')
        result=assess(parse_captions(fetch(caption_url)),track['languageCode'],track.get('kind')=='asr')
        result.update(videoId=identity,title=d.get('title','YouTube-Video')[:240],channelId=d.get('channelId'),publisher=d.get('author','Unbekannter Kanal')[:160],publishedDate=micro.get('publishDate'),checkedAt=now,url='https://www.youtube.com/watch?v='+identity)
        if fetch is read_url:
            with _lock:
                if len(_cache)>=40:_cache.pop(next(iter(_cache)))
                _cache[identity]=(now,dict(result))
        return result
    finally:_busy.release()


def enrich(item):
    try:
        result=analyze(item['url'])
        expected='UClnRIMiqpGha91ld0Zs4mwg' if item.get('sourceId')=='wgc-video' else None
        if expected and result.get('channelId')!=expected:raise ValueError('Kanalzuordnung nicht bestätigt')
        # Preserve publication timestamp from Atom, never substitute retrieval date.
        item.update(result)
        if expected:item['publisher']='World Gold Council'
        item['trustedTranscript']=bool(expected and result.get('transcriptAnalyzed'))
    except Exception:
        item['transcriptAnalyzed']=False
        item['articleStatus']='Untertitel nicht abrufbar oder Zuordnung unklar. Video bleibt ungeprüft; keine Richtungsstimme.'
    return item


def manual(payload):
    identity=video_id(payload.get('url'));url='https://www.youtube.com/watch?v='+identity
    transcript=payload.get('transcript','')
    if not isinstance(transcript,str) or len(transcript)>200000:raise ValueError('Transkript zu groß oder ungültig')
    if transcript.strip():
        # User supplied text stays explicitly unverified and cannot enter consensus.
        text=re.sub(r'(?m)^\s*(?:\d+|WEBVTT|\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?\s*-->.*)\s*$','',transcript)
        language=payload.get('language','en')
        if language not in ('en','de'):raise ValueError('Bitte Deutsch oder Englisch auswählen')
        result=assess([{'at':0,'text':text}],language)
        result.update(title='Eingefügtes Transkript · '+identity,publisher='Vom Nutzer zugeordnet',coverage='Eingefügtes Transkript (Zuordnung ungeprüft)',goldMoments=[],checkedAt=time.time())
    else:result=analyze(url)
    item=dict(id='youtube-'+identity,sourceId='manual-youtube',publishedAt=None,current=False,kind='YouTube',excerpt='',trustedTranscript=False)
    item.update(result)
    # Date-only metadata is informational, not an exact source timestamp for intraday.
    item['url']=url
    with _lock:
        if len(_manual)>=20:_manual.pop(next(iter(_manual)))
        _manual[identity]=item
    return item


def manual_items():
    with _lock:return [dict(x) for x in _manual.values() if time.time()-x['checkedAt']<7*86400]


def normalized(value):
    value=unicodedata.normalize('NFKD',html.unescape(value)).casefold()
    return ' '.join(re.findall(r'[a-z0-9]+',value))


def search_videos(query, fetch=read_url):
    raw=fetch('https://www.youtube.com/results?'+urlencode({'search_query':query[:160]}))
    text=raw.decode('utf-8','replace')
    match=re.search(r'(?:var\s+)?ytInitialData\s*=\s*',text)
    if not match:raise ValueError('YouTube-Suche momentan nicht öffentlich lesbar')
    data=json.JSONDecoder().raw_decode(text[match.end():])[0]
    videos={}
    def label(value):
        return value.get('simpleText') or ''.join(x.get('text','') for x in value.get('runs',[]))
    def walk(value,depth=0):
        if depth>35:return
        if isinstance(value,list):
            for x in value[:100]:walk(x,depth+1)
        elif isinstance(value,dict):
            row=value.get('videoRenderer')
            if isinstance(row,dict) and re.fullmatch(r'[A-Za-z0-9_-]{11}',row.get('videoId','')):
                title=label(row.get('title',{}));channel=label(row.get('ownerText') or row.get('longBylineText') or {})
                if title and channel:videos[row['videoId']]={'url':'https://www.youtube.com/watch?v='+row['videoId'],'title':title,'channel':channel}
            for x in value.values():walk(x,depth+1)
    walk(data)
    return list(videos.values())[:30]


def resolve_screenshot(text, search=search_videos):
    if not isinstance(text,str) or not 10<=len(text)<=10000:raise ValueError('Screenshot-Text fehlt oder ist zu lang')
    urls=set()
    for candidate in re.findall(r'(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?[^\s<>]+|shorts/[\w-]+|live/[\w-]+)|youtu\.be/[\w-]+)',text,re.I):
        try:urls.add('https://www.youtube.com/watch?v='+video_id(candidate if candidate.startswith('https://') else 'https://'+candidate.removeprefix('http://')))
        except ValueError:pass
    if len(urls)>1:raise ValueError('Mehrere YouTube-Links erkannt. Bitte nur das gewünschte Video abfotografieren.')
    if len(urls)==1:return {'url':next(iter(urls)),'title':'Video aus sichtbarem YouTube-Link','channel':'','matchedBy':'sichtbarer Link'}
    lines=[line.strip() for line in text.splitlines() if line.strip()]
    # Search only gold-title candidates, never the whole screen/comments/account data.
    candidates=[line for line in lines if re.search(r'\bgold\b|goldpreis|xau\s*/?\s*usd',line,re.I) and 15<=len(line)<=180]
    if len(candidates)>2:raise ValueError('Mehrere mögliche Videotitel im Screenshot. Bitte nur das gewünschte Video mit Titel und Kanal abfotografieren.')
    if not candidates:raise ValueError('Kein eindeutiger Link oder Gold-Videotitel erkannt. Bitte einen Screenshot mit vollständig sichtbarem Titel und Kanal verwenden.')
    haystack=' '+normalized(text)+' ';matches={}
    for query in sorted(candidates,key=len,reverse=True)[:2]:
        for video in search(query):
            title=normalized(video['title']);channel=normalized(video['channel'])
            # No fuzzy winner: title AND channel must be fully visible and unique.
            if len(title.split())>=4 and len(title)>=20 and len(channel)>=5 and ' '+title+' ' in haystack and ' '+channel+' ' in haystack:
                matches[video['url']]={**video,'matchedBy':'vollständiger Titel und Kanal'}
    if len(matches)!=1:raise ValueError('Video nicht eindeutig gefunden. Bitte den vollständigen Titel und Kanal ohne weitere Videovorschläge abfotografieren; Bob rät nicht.')
    return next(iter(matches.values()))


def from_screenshot(payload):
    resolved=resolve_screenshot(payload.get('screenshotText'))
    try:
        item=manual({'url':resolved['url']})
        return {'ok':True,'resolved':resolved,'item':item}
    except Exception:
        return {'ok':False,'resolved':resolved,'error':'Video erkannt, aber Untertitel derzeit nicht abrufbar. Der Screenshot allein enthält nicht den gesprochenen Videoinhalt. Keine Inhaltsanalyse möglich.'}
