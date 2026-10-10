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
_retained_video_ids = set()
_busy = threading.Semaphore(2)


def retain_only(items):
    """Evict old in-process subtitles, summaries and manual imports."""
    ids = set()
    for item in items:
        try:
            if item.get('channelId') == 'UCsl6Z6p7GOkczo8Cv-GH6Dg':
                ids.add(video_id(item['url']))
        except (AttributeError, ValueError, KeyError):
            continue
    if not ids:
        return
    ids = set(list(ids)[:3])
    with _lock:
        _retained_video_ids.clear()
        _retained_video_ids.update(ids)
        for cache in (_cache, _manual):
            for identity in list(cache):
                if identity not in ids:
                    del cache[identity]



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


def require_mco(details):
    if details.get('channelId')!='UCsl6Z6p7GOkczo8Cv-GH6Dg':raise ValueError('Recherche ist auf MCO Markets beschränkt. Dieses Video gehört zu einem anderen Kanal.')
    if not re.search(r'\bgold\b|goldpreis|xau\s*/?\s*usd',details.get('title',''),re.I):raise ValueError('Recherche ist auf Gold-Videos von MCO Markets beschränkt.')


def transcript_context(segments):
    # Extract whole sentences, retaining conditional clauses and negation.
    text=' '.join(s['text'] for s in segments)
    sentences=re.split(r'(?<=[.!?])\s+(?=[A-ZÄÖÜ])',text)
    chosen=[];words=0
    for sentence in sentences:
        if not re.search(r'gold|support|resistance|bull|bear|retracement|unterst[uü]tz|widerstand|abwärts|aufwärts',sentence,re.I):continue
        if re.search(r'affiliate|subscribe|membership|mitgliedschaft|broker',sentence,re.I):continue
        n=len(sentence.split())
        if n>90 or words+n>90:continue
        chosen.append(sentence);words+=n
        if len(chosen)==3:break
    return ' '.join(chosen)



# Only report concrete MCO Fibonacci percentages paired with an actual quoted
# gold price. No OCR, reconstructed numbers or inferred Fibonacci anchors.
_FIB_PERCENT = re.compile(r'(?<![\d.,])(38[.,]2|50(?:[.,]0)?|61[.,]8|78[.,]6|127[.,]2|161[.,]8)\s*(?:%|prozent|percent)(?!\w)', re.I)
_FIB_CONTEXT = re.compile(r'fibonacci|fibo\b|retracement|extension', re.I)
_FIB_PRICE = re.compile(r'(?<![\w.,])\$?\s*(?:[1-9]\d{3,4}(?:[.,]\d{1,2})?|[1-9]\d?[.,]\d{3}(?:[.,]\d{1,2})?)(?![\d.,%])')
_FIB_JOIN = re.compile(r'\b(?:bei|um|liegt|kurs|ziel|marke|level|at|around|target|usd|dollar)\b|[:=]', re.I)
_FIB_KEYS = {'38.2':'r382','50':'r500','61.8':'r618','78.6':'r786','127.2':'e1272','161.8':'e1618'}


def _fib_price(value):
    """Accept 4200.50, 4.200,50, 4,200.50 and avoid parsing ratios as prices."""
    value = value.strip().lstrip('
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
    result.update(context=transcript_context(segments),contextKind='Originalaussagen aus dem Transkript (Auszug)',transcriptAnalyzed=True,transcriptWords=len(text.split()),transcriptLanguage=language,
        automaticCaptions=automatic,mentions=bool(re.search(r'\bgold\b|xau\s*/?\s*usd|goldpreis',text,re.I)),
        goldMoments=moments,coverage='Untertitel (automatische Textregeln)',
        reason=('Gesprochener Inhalt anhand '+('automatischer' if automatic else 'veröffentlichter')+' Untertitel regelbasiert geprüft. Keine Bild-/Chartanalyse und keine KI-Sprachanalyse. Erkennungsfehler möglich.' if supported else 'Untertitel abgerufen; Sprache wird noch nicht ausgewertet. Keine Richtungsstimme.'))
    if supported:
        from research_overview import overview
        result['overview']=overview(segments,language)
        result['mcoFibonacci']=extract_fibonacci_levels(segments)
    if not supported:result['transcriptAnalyzed']=False
    return result


def listed_metadata(identity):
    """Confirm exact video membership on the public, verified MCO channel page."""
    import gold_research as g
    items, _ = g.channel_listing(g.download_channel(), time.time())
    item = next((x for x in items if video_id(x['url']) == identity), None)
    if item is None:
        raise ValueError('Video nicht in der öffentlichen MCO-Gold-Kanalliste bestätigt')
    require_mco(item)
    return {'videoDetails': {'videoId': identity, 'channelId': item['channelId'],
                             'title': item['title'], 'author': 'MCO Markets'}}


def analyze(url, fetch=read_url, *, verified_item=None):
    identity=video_id(url);now=time.time()
    with _lock:
        saved=_cache.get(identity)
        ttl=60 if saved and saved[1].get('enhancements',{}).get('unavailable') else 3600
        if fetch is read_url and saved and now-saved[0]<ttl:return dict(saved[1])
    if not _busy.acquire(blocking=False):raise ValueError('YouTube-Prüfung läuft bereits; bitte später erneut versuchen')
    try:
        try:
            p=player_metadata(fetch('https://www.youtube.com/watch?v='+identity),identity)
        except (ValueError, OSError):
            if fetch is not read_url:raise
            # A failed player request is not evidence that the public video is private.
            # Independently verify channel ownership before the supported provider API.
            if verified_item is not None:
                # Internal collector already verified the public channel listing this run.
                require_mco(verified_item)
                if video_id(verified_item['url']) != identity:raise ValueError('Videozuordnung nicht bestätigt')
                p={'videoDetails': {'videoId':identity,'channelId':verified_item['channelId'],
                    'title':verified_item['title'],'author':'MCO Markets'}}
            else:p=listed_metadata(identity)
        d=p['videoDetails']
        require_mco(d)
        micro=p.get('microformat',{}).get('playerMicroformatRenderer',{})
        tracks=p.get('captions',{}).get('playerCaptionsTracklistRenderer',{}).get('captionTracks',[])
        tracks=[t for t in tracks if isinstance(t.get('baseUrl'),str) and t.get('languageCode','').split('-')[0] in ('en','de')]
        tracks.sort(key=lambda t:(t.get('kind')=='asr',t.get('languageCode','').split('-')[0]!='en'))
        if not tracks and fetch is not read_url:raise ValueError('Keine öffentlich abrufbaren deutschen oder englischen Untertitel')
        result=None
        for track in tracks[:2]:
            caption_url=track['baseUrl']
            if not safe_url(caption_url) or urlparse(caption_url).path!='/api/timedtext' or parse_qs(urlparse(caption_url).query).get('v')!=[identity]:raise ValueError('Untertitel gehören nicht eindeutig zum Video')
            try:
                raw=fetch(caption_url)
                if not raw.strip():continue
                segments=parse_captions(raw)
                result=assess(segments,track['languageCode'],track.get('kind')=='asr')
            except (OSError, ValueError, ET.ParseError):
                continue
            break
        if result is None:
            if fetch is not read_url:raise ValueError('Untertitel vorhanden, aber kein Text abrufbar')
            import research_transcript_provider
            supplied=research_transcript_provider.request(identity)
            segments=supplied['segments']
            result=assess(segments,supplied['language'])
            result['automaticCaptions']=None
            result['reason']='Übermittelte Untertitel regelbasiert geprüft; automatische oder manuelle Herkunft nicht bestätigt. Keine KI-Sprach- oder Chartanalyse.'
            result['coverage']='Untertitel über zusätzlichen Transkript-Dienst (Textregeln)'
            result['transcriptProvider']=supplied['provider']
        if fetch is read_url:
            import research_enhancements
            extra=research_enhancements.request(identity,segments,p,(result.get('overview') or {}).get('moments',[]))
            result['enhancements']=extra
            if extra.get('summary'):
                result['reason']='Richtungsbewertung aus Untertiteln mit Textregeln; zusätzliche KI-Zusammenfassung mit Originalbelegen; niedrig aufgelöste Videobilder dienen ausschließlich der Orientierung, nicht als Kursnachweis.'
        result.update(videoId=identity,title=d.get('title','YouTube-Video')[:240],channelId=d.get('channelId'),publisher=d.get('author','Unbekannter Kanal')[:160],publishedDate=micro.get('publishDate'),checkedAt=now,url='https://www.youtube.com/watch?v='+identity)
        if fetch is read_url:
            with _lock:
                if not _retained_video_ids or identity in _retained_video_ids:
                    if len(_cache)>=3:_cache.pop(next(iter(_cache)))
                    _cache[identity]=(now,dict(result))
        return result
    finally:_busy.release()


def enrich(item):
    try:
        result=analyze(item['url'],verified_item=item)
        expected='UCsl6Z6p7GOkczo8Cv-GH6Dg'
        if expected and result.get('channelId')!=expected:raise ValueError('Kanalzuordnung nicht bestätigt')
        # Preserve publication timestamp from Atom, never substitute retrieval date.
        item.update(result)
        if expected:item['publisher']='MCO Markets'
        item['trustedTranscript']=bool(expected and result.get('transcriptAnalyzed'))
    except Exception as exc:
        item['transcriptAnalyzed']=False
        item['articleStatus']=str(exc) if isinstance(exc,ValueError) else 'Automatischer Untertitelabruf derzeit nicht verfügbar. Video bleibt ungeprüft.'
    return item


def manual(payload):
    identity=video_id(payload.get('url'));url='https://www.youtube.com/watch?v='+identity
    with _lock:
        if _retained_video_ids and identity not in _retained_video_ids:
            raise ValueError('Bob speichert ausschließlich die drei neuesten MCO-Gold-Videos. Dieses Video gehört nicht dazu.')
    transcript=payload.get('transcript','')
    if not isinstance(transcript,str) or len(transcript)>200000:raise ValueError('Transkript zu groß oder ungültig')
    if transcript.strip():
        metadata=player_metadata(read_url(url),identity)['videoDetails'];require_mco(metadata)
        # User supplied text stays explicitly unverified and cannot enter consensus.
        text=re.sub(r'(?m)^\s*(?:\d+|WEBVTT|\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?\s*-->.*)\s*$','',transcript)
        language=payload.get('language','en')
        if language not in ('en','de'):raise ValueError('Bitte Deutsch oder Englisch auswählen')
        result=assess([{'at':0,'text':text}],language)
        if result.get('overview'):
            result['overview']['moments']=[]
            for evidence in result['overview']['evidence']:evidence['at']=None
        result.update(title=metadata['title'],channelId=metadata['channelId'],publisher='MCO Markets',coverage='Eingefügtes Transkript (Zuordnung ungeprüft)',goldMoments=[],checkedAt=time.time())
    else:result=analyze(url)
    item=dict(id='youtube-'+identity,sourceId='manual-youtube',publishedAt=None,current=False,kind='YouTube',excerpt='',trustedTranscript=False)
    item.update(result)
    # Date-only metadata is informational, not an exact source timestamp for intraday.
    item['url']=url
    with _lock:
        if len(_manual)>=3:_manual.pop(next(iter(_manual)))
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
                owner=row.get('ownerText') or row.get('longBylineText') or {}
                owner_ids=[x.get('navigationEndpoint',{}).get('browseEndpoint',{}).get('browseId') for x in owner.get('runs',[])]
                if title and channel and 'UCsl6Z6p7GOkczo8Cv-GH6Dg' in owner_ids:videos[row['videoId']]={'url':'https://www.youtube.com/watch?v='+row['videoId'],'title':title,'channel':channel,'publishedText':label(row.get('publishedTimeText',{})),'viewsText':label(row.get('viewCountText',{}))}
            for x in value.values():walk(x,depth+1)
    walk(data)
    return list(videos.values())[:30]


class VideoSelectionRequired(ValueError):
    def __init__(self, candidates):
        super().__init__('Titel gefunden. Bitte das passende Video anhand von Kanal, Alter und Aufrufzahl auswählen.')
        self.candidates = candidates[:8]


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
    haystack=' '+normalized(text)+' ';matches={};title_matches={}
    for query in sorted(candidates,key=len,reverse=True)[:2]:
        for video in search(query):
            title=normalized(video['title']);channel=normalized(video['channel'])
            if len(title.split())>=4 and len(title)>=20 and ' '+title+' ' in haystack:
                title_matches[video['url']]=video
            # No fuzzy winner: title AND channel must be fully visible and unique.
            if len(title.split())>=4 and len(title)>=20 and len(channel)>=5 and ' '+title+' ' in haystack and ' '+channel+' ' in haystack:
                matches[video['url']]={**video,'matchedBy':'vollständiger Titel und Kanal'}
    if len(matches)!=1 and title_matches:raise VideoSelectionRequired(list(matches.values()) if matches else list(title_matches.values()))
    if len(matches)!=1:raise ValueError('Video nicht eindeutig gefunden. Bitte den vollständigen Titel und Kanal ohne weitere Videovorschläge abfotografieren; Bob rät nicht.')
    return next(iter(matches.values()))


def from_screenshot(payload):
    try:resolved=resolve_screenshot(payload.get('screenshotText'))
    except VideoSelectionRequired as exc:
        return {'ok':False,'candidates':exc.candidates,'error':str(exc)}
    try:
        item=manual({'url':resolved['url']})
        return {'ok':True,'resolved':resolved,'item':item}
    except Exception as exc:
        return {'ok':False,'resolved':resolved,'error':str(exc) if isinstance(exc,ValueError) else 'Video erkannt, aber Untertitel derzeit nicht abrufbar. Keine Inhaltsanalyse möglich.'}

).strip()
    if re.fullmatch(r'\d{1,2}[.,]\d{3}(?:[.,]\d{1,2})?', value):
        value = value[0:value.find('.') if '.' in value else value.find(',')] + value[(value.find('.') if '.' in value else value.find(','))+4:]
        if ',' in value and '.' not in value:
            value = value.replace(',', '.')
    elif ',' in value:
        value = value.replace(',', '.')
    try:
        number = float(value)
    except ValueError:
        return None
    return round(number, 2) if 500 <= number <= 25000 else None


def extract_fibonacci_levels(segments):
    """A price/ratio pair must be supported by neighboring, timed transcript words."""
    found = []
    seen = set()
    for index, row in enumerate(segments):
        at = row.get('at')
        if not isinstance(at, (int, float)) or not 0 <= at <= 86400:
            continue
        nearby = [s for s in segments[max(0, index - 2):index + 1]
                  if isinstance(s.get('text'), str) and 0 <= at - s.get('at', -1e9) <= 22]
        text = ' '.join(s['text'] for s in nearby)
        for ratio in _FIB_PERCENT.finditer(text):
            surrounding = text[max(0, ratio.start() - 145): min(len(text), ratio.end() + 100)]
            if not _FIB_CONTEXT.search(surrounding):
                continue
            canonical = str(float(ratio.group(1).replace(',', '.'))).rstrip('0').rstrip('.')
            key = _FIB_KEYS.get(canonical)
            if not key:
                continue
            possible = []
            for match in _FIB_PRICE.finditer(text):
                a, b = sorted((ratio.start(), match.start()))
                gap = text[a + (len(ratio.group(0)) if a == ratio.start() else len(match.group(0))):b]
                if len(gap) > 65 or not _FIB_JOIN.search(gap):
                    continue
                if any(other.start() != ratio.start() and a < other.start() < b
                       for other in _FIB_PERCENT.finditer(text)):
                    continue
                value = _fib_price(match.group())
                if value is None:
                    continue
                if re.search(r'(?:jahr|year|in|seit)\s*
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
    result.update(context=transcript_context(segments),contextKind='Originalaussagen aus dem Transkript (Auszug)',transcriptAnalyzed=True,transcriptWords=len(text.split()),transcriptLanguage=language,
        automaticCaptions=automatic,mentions=bool(re.search(r'\bgold\b|xau\s*/?\s*usd|goldpreis',text,re.I)),
        goldMoments=moments,coverage='Untertitel (automatische Textregeln)',
        reason=('Gesprochener Inhalt anhand '+('automatischer' if automatic else 'veröffentlichter')+' Untertitel regelbasiert geprüft. Keine Bild-/Chartanalyse und keine KI-Sprachanalyse. Erkennungsfehler möglich.' if supported else 'Untertitel abgerufen; Sprache wird noch nicht ausgewertet. Keine Richtungsstimme.'))
    if supported:
        from research_overview import overview
        result['overview']=overview(segments,language)
    if not supported:result['transcriptAnalyzed']=False
    return result


def listed_metadata(identity):
    """Confirm exact video membership on the public, verified MCO channel page."""
    import gold_research as g
    items, _ = g.channel_listing(g.download_channel(), time.time())
    item = next((x for x in items if video_id(x['url']) == identity), None)
    if item is None:
        raise ValueError('Video nicht in der öffentlichen MCO-Gold-Kanalliste bestätigt')
    require_mco(item)
    return {'videoDetails': {'videoId': identity, 'channelId': item['channelId'],
                             'title': item['title'], 'author': 'MCO Markets'}}


def analyze(url, fetch=read_url, *, verified_item=None):
    identity=video_id(url);now=time.time()
    with _lock:
        saved=_cache.get(identity)
        ttl=60 if saved and saved[1].get('enhancements',{}).get('unavailable') else 3600
        if fetch is read_url and saved and now-saved[0]<ttl:return dict(saved[1])
    if not _busy.acquire(blocking=False):raise ValueError('YouTube-Prüfung läuft bereits; bitte später erneut versuchen')
    try:
        try:
            p=player_metadata(fetch('https://www.youtube.com/watch?v='+identity),identity)
        except (ValueError, OSError):
            if fetch is not read_url:raise
            # A failed player request is not evidence that the public video is private.
            # Independently verify channel ownership before the supported provider API.
            if verified_item is not None:
                # Internal collector already verified the public channel listing this run.
                require_mco(verified_item)
                if video_id(verified_item['url']) != identity:raise ValueError('Videozuordnung nicht bestätigt')
                p={'videoDetails': {'videoId':identity,'channelId':verified_item['channelId'],
                    'title':verified_item['title'],'author':'MCO Markets'}}
            else:p=listed_metadata(identity)
        d=p['videoDetails']
        require_mco(d)
        micro=p.get('microformat',{}).get('playerMicroformatRenderer',{})
        tracks=p.get('captions',{}).get('playerCaptionsTracklistRenderer',{}).get('captionTracks',[])
        tracks=[t for t in tracks if isinstance(t.get('baseUrl'),str) and t.get('languageCode','').split('-')[0] in ('en','de')]
        tracks.sort(key=lambda t:(t.get('kind')=='asr',t.get('languageCode','').split('-')[0]!='en'))
        if not tracks and fetch is not read_url:raise ValueError('Keine öffentlich abrufbaren deutschen oder englischen Untertitel')
        result=None
        for track in tracks[:2]:
            caption_url=track['baseUrl']
            if not safe_url(caption_url) or urlparse(caption_url).path!='/api/timedtext' or parse_qs(urlparse(caption_url).query).get('v')!=[identity]:raise ValueError('Untertitel gehören nicht eindeutig zum Video')
            try:
                raw=fetch(caption_url)
                if not raw.strip():continue
                segments=parse_captions(raw)
                result=assess(segments,track['languageCode'],track.get('kind')=='asr')
            except (OSError, ValueError, ET.ParseError):
                continue
            break
        if result is None:
            if fetch is not read_url:raise ValueError('Untertitel vorhanden, aber kein Text abrufbar')
            import research_transcript_provider
            supplied=research_transcript_provider.request(identity)
            segments=supplied['segments']
            result=assess(segments,supplied['language'])
            result['automaticCaptions']=None
            result['reason']='Übermittelte Untertitel regelbasiert geprüft; automatische oder manuelle Herkunft nicht bestätigt. Keine KI-Sprach- oder Chartanalyse.'
            result['coverage']='Untertitel über zusätzlichen Transkript-Dienst (Textregeln)'
            result['transcriptProvider']=supplied['provider']
        if fetch is read_url:
            import research_enhancements
            extra=research_enhancements.request(identity,segments,p,(result.get('overview') or {}).get('moments',[]))
            result['enhancements']=extra
            if extra.get('summary'):
                result['reason']='Richtungsbewertung aus Untertiteln mit Textregeln; zusätzliche KI-Zusammenfassung mit Originalbelegen; niedrig aufgelöste Videobilder dienen ausschließlich der Orientierung, nicht als Kursnachweis.'
        result.update(videoId=identity,title=d.get('title','YouTube-Video')[:240],channelId=d.get('channelId'),publisher=d.get('author','Unbekannter Kanal')[:160],publishedDate=micro.get('publishDate'),checkedAt=now,url='https://www.youtube.com/watch?v='+identity)
        if fetch is read_url:
            with _lock:
                if not _retained_video_ids or identity in _retained_video_ids:
                    if len(_cache)>=3:_cache.pop(next(iter(_cache)))
                    _cache[identity]=(now,dict(result))
        return result
    finally:_busy.release()


def enrich(item):
    try:
        result=analyze(item['url'],verified_item=item)
        expected='UCsl6Z6p7GOkczo8Cv-GH6Dg'
        if expected and result.get('channelId')!=expected:raise ValueError('Kanalzuordnung nicht bestätigt')
        # Preserve publication timestamp from Atom, never substitute retrieval date.
        item.update(result)
        if expected:item['publisher']='MCO Markets'
        item['trustedTranscript']=bool(expected and result.get('transcriptAnalyzed'))
    except Exception as exc:
        item['transcriptAnalyzed']=False
        item['articleStatus']=str(exc) if isinstance(exc,ValueError) else 'Automatischer Untertitelabruf derzeit nicht verfügbar. Video bleibt ungeprüft.'
    return item


def manual(payload):
    identity=video_id(payload.get('url'));url='https://www.youtube.com/watch?v='+identity
    with _lock:
        if _retained_video_ids and identity not in _retained_video_ids:
            raise ValueError('Bob speichert ausschließlich die drei neuesten MCO-Gold-Videos. Dieses Video gehört nicht dazu.')
    transcript=payload.get('transcript','')
    if not isinstance(transcript,str) or len(transcript)>200000:raise ValueError('Transkript zu groß oder ungültig')
    if transcript.strip():
        metadata=player_metadata(read_url(url),identity)['videoDetails'];require_mco(metadata)
        # User supplied text stays explicitly unverified and cannot enter consensus.
        text=re.sub(r'(?m)^\s*(?:\d+|WEBVTT|\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?\s*-->.*)\s*$','',transcript)
        language=payload.get('language','en')
        if language not in ('en','de'):raise ValueError('Bitte Deutsch oder Englisch auswählen')
        result=assess([{'at':0,'text':text}],language)
        if result.get('overview'):
            result['overview']['moments']=[]
            for evidence in result['overview']['evidence']:evidence['at']=None
        result.update(title=metadata['title'],channelId=metadata['channelId'],publisher='MCO Markets',coverage='Eingefügtes Transkript (Zuordnung ungeprüft)',goldMoments=[],checkedAt=time.time())
    else:result=analyze(url)
    item=dict(id='youtube-'+identity,sourceId='manual-youtube',publishedAt=None,current=False,kind='YouTube',excerpt='',trustedTranscript=False)
    item.update(result)
    # Date-only metadata is informational, not an exact source timestamp for intraday.
    item['url']=url
    with _lock:
        if len(_manual)>=3:_manual.pop(next(iter(_manual)))
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
                owner=row.get('ownerText') or row.get('longBylineText') or {}
                owner_ids=[x.get('navigationEndpoint',{}).get('browseEndpoint',{}).get('browseId') for x in owner.get('runs',[])]
                if title and channel and 'UCsl6Z6p7GOkczo8Cv-GH6Dg' in owner_ids:videos[row['videoId']]={'url':'https://www.youtube.com/watch?v='+row['videoId'],'title':title,'channel':channel,'publishedText':label(row.get('publishedTimeText',{})),'viewsText':label(row.get('viewCountText',{}))}
            for x in value.values():walk(x,depth+1)
    walk(data)
    return list(videos.values())[:30]


class VideoSelectionRequired(ValueError):
    def __init__(self, candidates):
        super().__init__('Titel gefunden. Bitte das passende Video anhand von Kanal, Alter und Aufrufzahl auswählen.')
        self.candidates = candidates[:8]


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
    haystack=' '+normalized(text)+' ';matches={};title_matches={}
    for query in sorted(candidates,key=len,reverse=True)[:2]:
        for video in search(query):
            title=normalized(video['title']);channel=normalized(video['channel'])
            if len(title.split())>=4 and len(title)>=20 and ' '+title+' ' in haystack:
                title_matches[video['url']]=video
            # No fuzzy winner: title AND channel must be fully visible and unique.
            if len(title.split())>=4 and len(title)>=20 and len(channel)>=5 and ' '+title+' ' in haystack and ' '+channel+' ' in haystack:
                matches[video['url']]={**video,'matchedBy':'vollständiger Titel und Kanal'}
    if len(matches)!=1 and title_matches:raise VideoSelectionRequired(list(matches.values()) if matches else list(title_matches.values()))
    if len(matches)!=1:raise ValueError('Video nicht eindeutig gefunden. Bitte den vollständigen Titel und Kanal ohne weitere Videovorschläge abfotografieren; Bob rät nicht.')
    return next(iter(matches.values()))


def from_screenshot(payload):
    try:resolved=resolve_screenshot(payload.get('screenshotText'))
    except VideoSelectionRequired as exc:
        return {'ok':False,'candidates':exc.candidates,'error':str(exc)}
    try:
        item=manual({'url':resolved['url']})
        return {'ok':True,'resolved':resolved,'item':item}
    except Exception as exc:
        return {'ok':False,'resolved':resolved,'error':str(exc) if isinstance(exc,ValueError) else 'Video erkannt, aber Untertitel derzeit nicht abrufbar. Keine Inhaltsanalyse möglich.'}

, text[max(0, match.start()-12):match.start()], re.I):
                    continue
                possible.append((abs(match.start()-ratio.start()), value))
            if not possible:
                continue
            price = sorted(possible)[0][1]
            unique = (key, price)
            if unique in seen:
                continue
            seen.add(unique)
            # Exact subtitle excerpt, never an AI-created or visually inferred mark.
            quote = text[max(0, ratio.start()-105):min(len(text), ratio.end()+125)].strip()
            found.append({'key': key, 'ratio': ratio.group(1).replace('.', ',') + ' %',
                          'price': price, 'at': int(at), 'quote': quote[:300]})
            if len(found) >= 12:
                return found
    return found



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
    result.update(context=transcript_context(segments),contextKind='Originalaussagen aus dem Transkript (Auszug)',transcriptAnalyzed=True,transcriptWords=len(text.split()),transcriptLanguage=language,
        automaticCaptions=automatic,mentions=bool(re.search(r'\bgold\b|xau\s*/?\s*usd|goldpreis',text,re.I)),
        goldMoments=moments,coverage='Untertitel (automatische Textregeln)',
        reason=('Gesprochener Inhalt anhand '+('automatischer' if automatic else 'veröffentlichter')+' Untertitel regelbasiert geprüft. Keine Bild-/Chartanalyse und keine KI-Sprachanalyse. Erkennungsfehler möglich.' if supported else 'Untertitel abgerufen; Sprache wird noch nicht ausgewertet. Keine Richtungsstimme.'))
    if supported:
        from research_overview import overview
        result['overview']=overview(segments,language)
    if not supported:result['transcriptAnalyzed']=False
    return result


def listed_metadata(identity):
    """Confirm exact video membership on the public, verified MCO channel page."""
    import gold_research as g
    items, _ = g.channel_listing(g.download_channel(), time.time())
    item = next((x for x in items if video_id(x['url']) == identity), None)
    if item is None:
        raise ValueError('Video nicht in der öffentlichen MCO-Gold-Kanalliste bestätigt')
    require_mco(item)
    return {'videoDetails': {'videoId': identity, 'channelId': item['channelId'],
                             'title': item['title'], 'author': 'MCO Markets'}}


def analyze(url, fetch=read_url, *, verified_item=None):
    identity=video_id(url);now=time.time()
    with _lock:
        saved=_cache.get(identity)
        ttl=60 if saved and saved[1].get('enhancements',{}).get('unavailable') else 3600
        if fetch is read_url and saved and now-saved[0]<ttl:return dict(saved[1])
    if not _busy.acquire(blocking=False):raise ValueError('YouTube-Prüfung läuft bereits; bitte später erneut versuchen')
    try:
        try:
            p=player_metadata(fetch('https://www.youtube.com/watch?v='+identity),identity)
        except (ValueError, OSError):
            if fetch is not read_url:raise
            # A failed player request is not evidence that the public video is private.
            # Independently verify channel ownership before the supported provider API.
            if verified_item is not None:
                # Internal collector already verified the public channel listing this run.
                require_mco(verified_item)
                if video_id(verified_item['url']) != identity:raise ValueError('Videozuordnung nicht bestätigt')
                p={'videoDetails': {'videoId':identity,'channelId':verified_item['channelId'],
                    'title':verified_item['title'],'author':'MCO Markets'}}
            else:p=listed_metadata(identity)
        d=p['videoDetails']
        require_mco(d)
        micro=p.get('microformat',{}).get('playerMicroformatRenderer',{})
        tracks=p.get('captions',{}).get('playerCaptionsTracklistRenderer',{}).get('captionTracks',[])
        tracks=[t for t in tracks if isinstance(t.get('baseUrl'),str) and t.get('languageCode','').split('-')[0] in ('en','de')]
        tracks.sort(key=lambda t:(t.get('kind')=='asr',t.get('languageCode','').split('-')[0]!='en'))
        if not tracks and fetch is not read_url:raise ValueError('Keine öffentlich abrufbaren deutschen oder englischen Untertitel')
        result=None
        for track in tracks[:2]:
            caption_url=track['baseUrl']
            if not safe_url(caption_url) or urlparse(caption_url).path!='/api/timedtext' or parse_qs(urlparse(caption_url).query).get('v')!=[identity]:raise ValueError('Untertitel gehören nicht eindeutig zum Video')
            try:
                raw=fetch(caption_url)
                if not raw.strip():continue
                segments=parse_captions(raw)
                result=assess(segments,track['languageCode'],track.get('kind')=='asr')
            except (OSError, ValueError, ET.ParseError):
                continue
            break
        if result is None:
            if fetch is not read_url:raise ValueError('Untertitel vorhanden, aber kein Text abrufbar')
            import research_transcript_provider
            supplied=research_transcript_provider.request(identity)
            segments=supplied['segments']
            result=assess(segments,supplied['language'])
            result['automaticCaptions']=None
            result['reason']='Übermittelte Untertitel regelbasiert geprüft; automatische oder manuelle Herkunft nicht bestätigt. Keine KI-Sprach- oder Chartanalyse.'
            result['coverage']='Untertitel über zusätzlichen Transkript-Dienst (Textregeln)'
            result['transcriptProvider']=supplied['provider']
        if fetch is read_url:
            import research_enhancements
            extra=research_enhancements.request(identity,segments,p,(result.get('overview') or {}).get('moments',[]))
            result['enhancements']=extra
            if extra.get('summary'):
                result['reason']='Richtungsbewertung aus Untertiteln mit Textregeln; zusätzliche KI-Zusammenfassung mit Originalbelegen; niedrig aufgelöste Videobilder dienen ausschließlich der Orientierung, nicht als Kursnachweis.'
        result.update(videoId=identity,title=d.get('title','YouTube-Video')[:240],channelId=d.get('channelId'),publisher=d.get('author','Unbekannter Kanal')[:160],publishedDate=micro.get('publishDate'),checkedAt=now,url='https://www.youtube.com/watch?v='+identity)
        if fetch is read_url:
            with _lock:
                if not _retained_video_ids or identity in _retained_video_ids:
                    if len(_cache)>=3:_cache.pop(next(iter(_cache)))
                    _cache[identity]=(now,dict(result))
        return result
    finally:_busy.release()


def enrich(item):
    try:
        result=analyze(item['url'],verified_item=item)
        expected='UCsl6Z6p7GOkczo8Cv-GH6Dg'
        if expected and result.get('channelId')!=expected:raise ValueError('Kanalzuordnung nicht bestätigt')
        # Preserve publication timestamp from Atom, never substitute retrieval date.
        item.update(result)
        if expected:item['publisher']='MCO Markets'
        item['trustedTranscript']=bool(expected and result.get('transcriptAnalyzed'))
    except Exception as exc:
        item['transcriptAnalyzed']=False
        item['articleStatus']=str(exc) if isinstance(exc,ValueError) else 'Automatischer Untertitelabruf derzeit nicht verfügbar. Video bleibt ungeprüft.'
    return item


def manual(payload):
    identity=video_id(payload.get('url'));url='https://www.youtube.com/watch?v='+identity
    with _lock:
        if _retained_video_ids and identity not in _retained_video_ids:
            raise ValueError('Bob speichert ausschließlich die drei neuesten MCO-Gold-Videos. Dieses Video gehört nicht dazu.')
    transcript=payload.get('transcript','')
    if not isinstance(transcript,str) or len(transcript)>200000:raise ValueError('Transkript zu groß oder ungültig')
    if transcript.strip():
        metadata=player_metadata(read_url(url),identity)['videoDetails'];require_mco(metadata)
        # User supplied text stays explicitly unverified and cannot enter consensus.
        text=re.sub(r'(?m)^\s*(?:\d+|WEBVTT|\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d+)?\s*-->.*)\s*$','',transcript)
        language=payload.get('language','en')
        if language not in ('en','de'):raise ValueError('Bitte Deutsch oder Englisch auswählen')
        result=assess([{'at':0,'text':text}],language)
        if result.get('overview'):
            result['overview']['moments']=[]
            for evidence in result['overview']['evidence']:evidence['at']=None
        result.update(title=metadata['title'],channelId=metadata['channelId'],publisher='MCO Markets',coverage='Eingefügtes Transkript (Zuordnung ungeprüft)',goldMoments=[],checkedAt=time.time())
    else:result=analyze(url)
    item=dict(id='youtube-'+identity,sourceId='manual-youtube',publishedAt=None,current=False,kind='YouTube',excerpt='',trustedTranscript=False)
    item.update(result)
    # Date-only metadata is informational, not an exact source timestamp for intraday.
    item['url']=url
    with _lock:
        if len(_manual)>=3:_manual.pop(next(iter(_manual)))
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
                owner=row.get('ownerText') or row.get('longBylineText') or {}
                owner_ids=[x.get('navigationEndpoint',{}).get('browseEndpoint',{}).get('browseId') for x in owner.get('runs',[])]
                if title and channel and 'UCsl6Z6p7GOkczo8Cv-GH6Dg' in owner_ids:videos[row['videoId']]={'url':'https://www.youtube.com/watch?v='+row['videoId'],'title':title,'channel':channel,'publishedText':label(row.get('publishedTimeText',{})),'viewsText':label(row.get('viewCountText',{}))}
            for x in value.values():walk(x,depth+1)
    walk(data)
    return list(videos.values())[:30]


class VideoSelectionRequired(ValueError):
    def __init__(self, candidates):
        super().__init__('Titel gefunden. Bitte das passende Video anhand von Kanal, Alter und Aufrufzahl auswählen.')
        self.candidates = candidates[:8]


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
    haystack=' '+normalized(text)+' ';matches={};title_matches={}
    for query in sorted(candidates,key=len,reverse=True)[:2]:
        for video in search(query):
            title=normalized(video['title']);channel=normalized(video['channel'])
            if len(title.split())>=4 and len(title)>=20 and ' '+title+' ' in haystack:
                title_matches[video['url']]=video
            # No fuzzy winner: title AND channel must be fully visible and unique.
            if len(title.split())>=4 and len(title)>=20 and len(channel)>=5 and ' '+title+' ' in haystack and ' '+channel+' ' in haystack:
                matches[video['url']]={**video,'matchedBy':'vollständiger Titel und Kanal'}
    if len(matches)!=1 and title_matches:raise VideoSelectionRequired(list(matches.values()) if matches else list(title_matches.values()))
    if len(matches)!=1:raise ValueError('Video nicht eindeutig gefunden. Bitte den vollständigen Titel und Kanal ohne weitere Videovorschläge abfotografieren; Bob rät nicht.')
    return next(iter(matches.values()))


def from_screenshot(payload):
    try:resolved=resolve_screenshot(payload.get('screenshotText'))
    except VideoSelectionRequired as exc:
        return {'ok':False,'candidates':exc.candidates,'error':str(exc)}
    try:
        item=manual({'url':resolved['url']})
        return {'ok':True,'resolved':resolved,'item':item}
    except Exception as exc:
        return {'ok':False,'resolved':resolved,'error':str(exc) if isinstance(exc,ValueError) else 'Video erkannt, aber Untertitel derzeit nicht abrufbar. Keine Inhaltsanalyse möglich.'}

