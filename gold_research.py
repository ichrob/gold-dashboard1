"""Bounded, read-only public-feed research. Never grants trading permission."""
import copy
import hashlib
import html
import json
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from urllib.parse import urlparse, urlunparse

INTERVAL = 900
MCO_CHANNEL = 'UCsl6Z6p7GOkczo8Cv-GH6Dg'
SOURCES = [dict(id='mco-video', publisher='MCO Markets', kind='YouTube',
    url='https://www.youtube.com/feeds/videos.xml?channel_id='+MCO_CHANNEL,
    hosts=['www.youtube.com','youtube.com'],
    scope='Nur Gold-Videos von MCO Markets. Eine Anbietermeinung, kein Quellenkonsens.')]

def allowed_item(item):
    return (item.get('kind')=='YouTube' and item.get('channelId')==MCO_CHANNEL
            and bool(re.search(r'\bgold\b|goldpreis|xau\s*/?\s*usd',item.get('title',''),re.I)))

_lock = threading.Lock()
_thread = None
_report = None

class Plain(HTMLParser):
    def __init__(self):
        super().__init__(); self.parts=[]; self.skip=0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.skip+=1
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
    def handle_data(self, data):
        if not self.skip:self.parts.append(data)

def clean(value):
    p=Plain();p.feed(value or '')
    return re.sub(r'\s+',' ',html.unescape(' '.join(p.parts))).strip()

def timestamp(value):
    try:
        d=parsedate_to_datetime(value)
    except (ValueError, TypeError, OverflowError):
        try:d=datetime.fromisoformat((value or '').replace('Z','+00:00'))
        except (ValueError, TypeError):return None
    return d.timestamp() if d.tzinfo else None

def link(value, source):
    p=urlparse(value or '')
    if p.scheme!='https' or p.hostname not in source['hosts'] or p.username or p.password or p.port not in (None,443):return None
    # Keep YouTube v= identity; tracking does not multiply article counts.
    return urlunparse(p._replace(fragment='',query=p.query if source['kind']=='YouTube' else ''))

def classify(title, text, kind):
    """Conservative, disclosed text rules, not a semantic model or a forecast."""
    if kind=='YouTube':return dict(trend='UNKLAR', outlook='UNKLAR', horizon='unbekannt', reason='Video nicht inhaltlich geprüft; kein Transkript. Keine Richtungsstimme.')
    body=(title+'. '+text).lower()
    gold=r'(?:gold(?: price)?|xau\s*/?\s*usd|goldpreis)'
    # Only explicit subject-linked phrases; dollar gains are not gold gains.
    up=re.search(gold+r'\s+(?:rises|rebounds|rallies|climbs|gains|advances|steigt|erholt sich)\b',body)
    down=re.search(gold+r'\s+(?:falls|drops|slides|declines|tumbles|retreats|sinks|fällt|sinkt)\b',body)
    trend='LONG' if up and not down else 'SHORT' if down and not up else 'UNKLAR'
    sentences=re.split(r'(?<=[.!?])\s+',body)
    positive=negative=False
    for sentence in sentences:
        if not re.search(gold,sentence):continue
        # Conditional, quoted questions and negations cannot become firm calls.
        if re.search(r'\b(?:if|unless|not|never|no|could|may|might|wenn|nicht|könnte|falls)\b|\?',sentence):continue
        positive |= bool(re.search(gold+r'\s+(?:is expected to|is likely to|is forecast to|will)\s+(?:rise|climb|rally|gain|advance)\b',sentence) or re.search(r'\b(?:bullish outlook for gold|bullish on gold)\b',sentence) or re.search(gold+r'\s+wird(?:\s+heute)?\s+(?:steigen|zulegen)\b',sentence))
        negative |= bool(re.search(gold+r'\s+(?:is expected to|is likely to|is forecast to|will)\s+(?:fall|decline|drop|slide|retreat)\b',sentence) or re.search(r'\b(?:bearish outlook for gold|bearish on gold)\b',sentence) or re.search(gold+r'\s+wird(?:\s+heute)?\s+(?:fallen|sinken)\b',sentence))
    horizon='längerfristig' if re.search(r'\b(?:next year|year.end|annual|long.term|quarter|2027|2028|langfristig|jahresende)\b',body) else 'Intraday' if re.search(r'\b(?:today|intraday|this session|heute)\b',body) else 'unbekannt'
    outlook='LONG' if positive and not negative else 'SHORT' if negative and not positive else 'UNKLAR'
    return dict(trend=trend,outlook=outlook,horizon=horizon,reason='Automatische Textregel aus Feed-Auszug; keine Volltextprüfung. Ausblick nur bei ausdrücklicher, unbedingter Gold-Richtung; unklare Aussagen bleiben offen.')

def parse_feed(data, source, now):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('XML declarations unsupported')
    root=ET.fromstring(data)
    atom={'a':'http://www.w3.org/2005/Atom','m':'http://search.yahoo.com/mrss/','yt':'http://www.youtube.com/xml/schemas/2015'}
    nodes=root.findall('./channel/item') if root.tag=='rss' else root.findall('a:entry',atom)
    if root.tag!='rss' and root.tag!='{http://www.w3.org/2005/Atom}feed':raise ValueError('Kein Feed')
    if source['id']=='mco-video' and root.findtext('yt:channelId',namespaces=atom)!=MCO_CHANNEL:raise ValueError('Falscher YouTube-Kanal')
    items=[];scanned=0
    for node in nodes[:100]:
        scanned+=1
        if source['kind']=='YouTube':
            title=clean(node.findtext('a:title',default='',namespaces=atom));published=node.findtext('a:published',namespaces=atom)
            target=node.find('a:link',atom);url=target.get('href') if target is not None else None
            description=clean(node.findtext('m:group/m:description',default='',namespaces=atom))
        else:
            title=clean(node.findtext('title'));description=clean(node.findtext('description'));published=node.findtext('pubDate');url=node.findtext('link')
        url=link(url,source)
        if not url or not re.search(r'\bgold\b|xau\s*/?\s*usd|goldpreis',title if source['kind']=='YouTube' else title+' '+description,re.I):continue
        if source['id']=='mco-video' and node.findtext('yt:channelId',namespaces=atom)!=MCO_CHANNEL:continue
        at=timestamp(published)
        age=now-at if at is not None else None
        if age is not None and age>7*86400:continue
        assessment=classify(title,description,source['kind'])
        current=age is not None and 0<=age<=86400
        # No full articles retained. Only short source-provided excerpt and provenance.
        excerpt=' '.join(description.split()[:20])
        items.append(dict(id=hashlib.sha256(url.encode()).hexdigest()[:16],url=url,title=title[:240],excerpt=excerpt,
            publisher=source['publisher'],kind=source['kind'],publishedAt=at,checkedAt=now,current=current,
            sourceId=source['id'],channelId=MCO_CHANNEL if source['id']=='mco-video' else None,coverage='Videometadaten' if source['kind']=='YouTube' else 'Feed-Auszug',**assessment))
    return items,scanned

def download(source):
    req=urllib.request.Request(source['url'],headers={'User-Agent':'Bob-GoldResearch/1.0 (public RSS reader)','Accept':'application/rss+xml, application/atom+xml, application/xml'})
    with urllib.request.urlopen(req,timeout=10) as response:
        if urlparse(response.url).hostname not in source['hosts']:raise ValueError('Unexpected redirect')
        data=response.read(1000001)
    if len(data)>1000000:raise ValueError('Feed too large')
    return data

class ArticleData(HTMLParser):
    def __init__(self):
        super().__init__();self.active=False;self.parts=[];self.bodies=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script' and dict(attrs).get('type')=='application/ld+json':self.active=True;self.parts=[]
    def handle_data(self,data):
        if self.active:self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.active:
            self.active=False
            try:self.walk(json.loads(''.join(self.parts)))
            except (ValueError,TypeError):pass
    def walk(self,value):
        if isinstance(value,list):
            for item in value:self.walk(item)
        elif isinstance(value,dict):
            if isinstance(value.get('articleBody'),str):self.bodies.append(clean(value['articleBody']))
            if '@graph' in value:self.walk(value['@graph'])

def article_text(data):
    p=ArticleData();p.feed(data.decode('utf-8','replace'))
    body=max(p.bodies,key=len,default='')
    return body if len(body)>=200 else None

def enrich_article(item):
    source=next(s for s in SOURCES if s['id']==item['sourceId'])
    try:
        with urllib.request.urlopen(urllib.request.Request(item['url'],headers={'User-Agent':'Bob-GoldResearch/1.0 (public article reader)'}),timeout=10) as response:
            if not link(response.url,source):raise ValueError('Unexpected redirect')
            data=response.read(2000001)
        if len(data)>2000000:raise ValueError('Article too large')
        body=article_text(data)
        if not body:raise ValueError('No structured article text')
        item.update(classify(item['title'],body,item['kind']))
        item['coverage']='Artikeltext (automatische Textregeln)'
        item['reason']=item['reason'].replace('aus Feed-Auszug; keine Volltextprüfung','aus strukturiertem Artikeltext; keine KI-Sprachanalyse')
    except Exception:
        item['articleStatus']='Artikeltext nicht abrufbar oder nicht eindeutig erkennbar; nur Feed-Auszug'

def relative_publication_label(text):
    match=re.search(r'\b(\d+)\s*(m|min(?:ute)?s?|h|hours?|d|days?|w|weeks?)\s+ago\b',text,re.I)
    if not match:return text[:100]
    amount=int(match[1]);unit=match[2].lower()[0]
    singular,plural={'m':('Minute','Minuten'),'h':('Stunde','Stunden'),'d':('Tag','Tagen'),'w':('Woche','Wochen')}[unit]
    return 'vor '+str(amount)+' '+(singular if amount==1 else plural)


def channel_listing(data, now):
    text=data.decode('utf-8','replace')
    match=re.search(r'(?:var\s+)?ytInitialData\s*=\s*',text)
    if not match:raise ValueError('Kanal nicht lesbar')
    root=json.JSONDecoder().raw_decode(text[match.end():])[0]
    if root.get('metadata',{}).get('channelMetadataRenderer',{}).get('externalId')!=MCO_CHANNEL:raise ValueError('Kanal nicht bestätigt')
    tabs=root.get('contents',{}).get('twoColumnBrowseResultsRenderer',{}).get('tabs',[])
    tab=next((t['tabRenderer'] for t in tabs if t.get('tabRenderer',{}).get('selected')),None)
    if not tab:raise ValueError('Keine Videoliste')
    rows=tab.get('content',{}).get('richGridRenderer',{}).get('contents',[])
    items=[];scanned=0
    for row in rows[:60]:
        content=row.get('richItemRenderer',{}).get('content',{})
        v=content.get('lockupViewModel',{});old=content.get('videoRenderer',{})
        identity=v.get('contentId') or old.get('videoId','')
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}',identity):continue
        if v and v.get('contentType')!='LOCKUP_CONTENT_TYPE_VIDEO':continue
        scanned+=1
        meta=v.get('metadata',{}).get('lockupMetadataViewModel',{})
        title=meta.get('title',{}).get('content') or ''.join(x.get('text','') for x in old.get('title',{}).get('runs',[]))
        if not re.search(r'\bgold\b|goldpreis|xau\s*/?\s*usd',title,re.I):continue
        parts=[p.get('text',{}).get('content','') for r in meta.get('metadata',{}).get('contentMetadataViewModel',{}).get('metadataRows',[]) for p in r.get('metadataParts',[])]
        relative=next((part for part in parts if re.search(r'\bago\b|\bvor\b',part,re.I)), '')
        if not relative:
            pub=old.get('publishedTimeText',{})
            relative=pub.get('simpleText') or ''.join(x.get('text','') for x in pub.get('runs',[]))
        items.append(dict(publishedRelative=relative_publication_label(relative),publishedRelativeObservedAt=now,id='youtube-'+identity,url='https://www.youtube.com/watch?v='+identity,title=title[:240],excerpt='',
            publisher='MCO Markets',kind='YouTube',channelId=MCO_CHANNEL,sourceId='mco-video',publishedAt=None,checkedAt=now,current=False,
            listingInfo=' · '.join(parts)[:160],coverage='Videometadaten; Veröffentlichungszeit nicht exakt bestätigt',**classify(title,'','YouTube')))
    return items,scanned


def download_channel():
    source=dict(SOURCES[0],url='https://www.youtube.com/channel/'+MCO_CHANNEL+'/videos')
    req=urllib.request.Request(source['url'],headers={'User-Agent':'Bob-GoldResearch/1.0 (public channel reader)'})
    with urllib.request.urlopen(req,timeout=10) as response:
        if urlparse(response.url).hostname!='www.youtube.com' or urlparse(response.url).path!='/channel/'+MCO_CHANNEL+'/videos':raise ValueError('Kanal umgeleitet')
        data=response.read(2500001)
    if len(data)>2500000:raise ValueError('Kanalantwort zu groß')
    return data


# Verified against the public YouTube player metadata on 2026-10-09.
# Keep the source timezone; display conversion belongs to the UI.
_VERIFIED_PUBLICATIONS = {
    'wjLMQ7QfMiM': dict(publishedAt=timestamp('2026-10-07T20:29:53-07:00'),
                        publishedDate='2026-10-07T20:29:53-07:00',
                        publicationSource='YouTube-Videometadaten; geprüft 09.10.2026')
}
_publication_cache = dict(_VERIFIED_PUBLICATIONS)


def enrich_publication(item, fetch=None):
    """Read publication metadata independently of captions; never date relative ages."""
    if item.get('publishedAt') is not None:
        return item
    import youtube_research as y
    identity = y.video_id(item['url'])
    cached = _publication_cache.get(identity)
    if cached:
        item.update(cached)
        return item
    try:
        player = y.player_metadata((fetch or y.read_url)(item['url']), identity)
        y.require_mco(player.get('videoDetails', {}))
        micro = player.get('microformat', {}).get('playerMicroformatRenderer', {})
        value = micro.get('publishDate')
        exact = timestamp(value)
        if exact is not None and exact <= time.time():
            publication = dict(publishedAt=exact, publishedDate=value,
                               publicationSource='YouTube-Videometadaten')
        elif isinstance(value, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            datetime.strptime(value, '%Y-%m-%d')
            publication = dict(publishedDate=value, publicationSource='YouTube-Videometadaten; Uhrzeit fehlt')
        else:
            return item
        item.update(publication)
        if exact is not None:
            if len(_publication_cache) >= 200:
                _publication_cache.pop(next(iter(_publication_cache)))
            _publication_cache[identity] = publication
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return item


def collect(now=None, fetch=download):
    now=time.time() if now is None else now
    def one(source):
        try:
            items,scanned=parse_feed(fetch(source),source,now)
            return dict(**source,status='ok',checkedAt=now,scanned=scanned,relevant=len(items)),items
        except Exception as exc:
            if fetch is download:
                try:
                    items,scanned=channel_listing(download_channel(),now)
                    return dict(**source,status='ok',checkedAt=now,scanned=scanned,relevant=len(items),route='Kanal-Videoseite; Feed nicht erreichbar'),items
                except Exception:pass
            return dict(**source,status='unavailable',checkedAt=now,scanned=0,relevant=0,error=type(exc).__name__),[]
    with ThreadPoolExecutor(max_workers=4,thread_name_prefix='bob-research-fetch') as pool:results=list(pool.map(one,SOURCES))
    sources=[r[0] for r in results];unique={}
    for _,items in results:
        for item in items:
            if allowed_item(item):unique[item['url']]=item
    items=sorted(unique.values(),key=lambda x:x['publishedAt'] or 0,reverse=True)
    if fetch is download:
        eligible=[x for x in items if x['kind']=='Internet' and x['current']][:6]
        with ThreadPoolExecutor(max_workers=3,thread_name_prefix='bob-research-article') as pool:
            list(pool.map(enrich_article,eligible))
        with ThreadPoolExecutor(max_workers=3,thread_name_prefix='bob-video-publication') as pool:
            list(pool.map(enrich_publication,[x for x in items if x['kind']=='YouTube']))
        items.sort(key=lambda x:x.get('publishedAt') or 0,reverse=True)
        import youtube_research
        for item in [x for x in items if x['kind']=='YouTube'][:3]:
            publication={key:item[key] for key in ('publishedAt','publishedDate','publicationSource') if item.get(key) is not None}
            youtube_research.enrich(item)
            item.update(publication)
    return dict(version='mco-gold-research-v3',checkedAt=now,intervalSeconds=INTERVAL,sources=sources,items=items,
        method='Nur Gold-Videos des bestätigten Kanals MCO Markets. Neue Videos werden alle 15 Minuten gesucht; bis zu drei Videos je Lauf werden auf abrufbare Untertitel geprüft. Kurzer Kontext aus dem tatsächlich gelesenen Transkript mit Quellenstellen. Richtungsbewertung mit Textregeln; zusätzliche KI-Zusammenfassung und gespeicherte Videovorschaubilder abhängig vom ausgewiesenen Abrufstatus. Keine KI-Chartanalyse; fehlender Text bleibt ungeprüft.')


def summarize(report, now=None):
    now=time.time() if now is None else now
    result=copy.deepcopy(report)
    result['sources']=[s for s in result.get('sources',[]) if s.get('id')=='mco-video']
    fresh=bool(result.get('checkedAt') and 0<=now-result['checkedAt']<=INTERVAL*2)
    items=[x for x in result.get('items',[]) if allowed_item(x)]
    result['items']=items
    for x in items:x['current']=bool(fresh and x['publishedAt'] is not None and 0<=now-x['publishedAt']<=86400)
    counts={k:0 for k in ('LONG','SHORT','UNKLAR')}
    for x in items:
        if x['current'] and (x['kind']=='Internet' or x.get('trustedTranscript')):counts[x['outlook']]+=1
    votes={}
    for x in items:
        if x['current'] and (x['kind']=='Internet' or x.get('trustedTranscript')) and x['horizon']=='Intraday' and x['outlook'] in ('LONG','SHORT'):votes.setdefault(x['publisher'],set()).add(x['outlook'])
    longs=sum(v=={'LONG'} for v in votes.values());shorts=sum(v=={'SHORT'} for v in votes.values())
    consensus='LONG' if longs>=2 and not shorts and all(len(v)==1 for v in votes.values()) else 'SHORT' if shorts>=2 and not longs and all(len(v)==1 for v in votes.values()) else 'ABWARTEN'
    result.update(fresh=fresh,counts=counts,consensus=consensus,independentLong=longs,independentShort=shorts,
        scanned=sum(s['scanned'] for s in result.get('sources',[])),successfulFeeds=sum(s['status']=='ok' for s in result.get('sources',[])),
        publishers=len({s['publisher'] for s in result.get('sources',[]) if s['status']=='ok'}),
        articles=sum(x['kind']=='Internet' for x in items),fullTexts=sum(x['coverage'].startswith('Artikeltext') for x in items),videosFound=sum(x['kind']=='YouTube' for x in items),videosAnalyzed=sum(bool(x.get('transcriptAnalyzed')) for x in items),
        reason='Recherche enthält ausschließlich MCO Markets: eine Anbietermeinung, kein unabhängiger Quellenkonsens. Nicht gelesene Videos zählen nicht als neutral. Keine Handelsfreigabe.')
    return result

def snapshot():
    with _lock:report=copy.deepcopy(_report)
    import youtube_research
    report=report or dict(checkedAt=None,sources=[],items=[],method='Recherche startet; noch keine Quellen geprüft.',intervalSeconds=INTERVAL)
    manual={x['url']:x for x in youtube_research.manual_items() if allowed_item(x)}
    for item in report['items']:
        if item['url'] in manual and not item.get('transcriptAnalyzed'):
            publication={key:item[key] for key in ('publishedAt','publishedRelative','publishedRelativeObservedAt','listingInfo') if item.get(key) is not None}
            item.update(manual.pop(item['url']))
            item.update(publication)
    urls={x['url'] for x in report['items']}
    report['items'] += [x for url,x in manual.items() if url not in urls]
    # Apply verified metadata to stored/manual entries as well as fresh listings.
    for item in report['items']:
        if item.get('publishedAt') is None:
            try:
                saved=_VERIFIED_PUBLICATIONS.get(youtube_research.video_id(item['url']))
                if saved:item.update(saved)
            except (ValueError, KeyError):pass
    return summarize(report)

def _run():
    global _report
    while True:
        try:
            report=collect()
            with _lock:_report=report
        except Exception:pass
        threading.Event().wait(INTERVAL)

def start():
    global _thread
    with _lock:
        if _thread is None or not _thread.is_alive():
            _thread=threading.Thread(target=_run,name='bob-gold-research',daemon=True);_thread.start()
