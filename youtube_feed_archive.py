"""Durable, public-metadata-only MCO Markets YouTube video list.

Never stores transcripts, private screenshots or unverified channel entries.
Archived listings are display only and cannot confirm an intraday outlook.
"""
import json
import os
import re
import time
from datetime import datetime,timezone
from urllib.parse import urlparse,parse_qs
from urllib.request import Request,build_opener
from bob_auth import NoRedirect

CHANNEL='UCsl6Z6p7GOkczo8Cv-GH6Dg'
VIDEO_ID=re.compile(r'^[A-Za-z0-9_-]{11}$')
GOLD=re.compile(r'\bgold\b|goldpreis|xau\s*/?\s*usd',re.I)
MAX_DAYS=30
KEY='mco-markets-gold-youtube'


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_youtube_feed_archive (
        feed_key TEXT PRIMARY KEY,
        saved_at TIMESTAMPTZ NOT NULL,
        items JSONB NOT NULL
    )""")


def sanitize(items):
    if not isinstance(items,list):
        raise ValueError('Ungültige Videoeinträge')
    result=[]; seen=set()
    for entry in items[:50]:
        if not isinstance(entry,dict) or entry.get('channelId')!=CHANNEL or entry.get('kind')!='YouTube':
            continue
        try:
            raw=entry.get('url','')
            if not isinstance(raw,str):continue
            u=urlparse(raw)
            if u.scheme!='https' or u.hostname not in ('www.youtube.com','youtube.com') or u.path!='/watch' or u.username or u.password:
                continue
            identity=(parse_qs(u.query).get('v') or [None])[0]
            title=entry.get('title','')
            if not VIDEO_ID.fullmatch(identity or '') or not isinstance(title,str) or not GOLD.search(title) or identity in seen:
                continue
            seen.add(identity)
            published=entry.get('publishedAt')
            if not isinstance(published,(float,int)) or isinstance(published,bool) or published<=0 or published>time.time()+86400:
                published=None
            relative=entry.get('publishedRelative')
            saved=dict(id='youtube-'+identity,url='https://www.youtube.com/watch?v='+identity,
                title=title[:240],publisher='MCO Markets',kind='YouTube',channelId=CHANNEL,
                sourceId='mco-video',publishedAt=published,publishedDate=entry.get('publishedDate') if isinstance(entry.get('publishedDate'),str) else None,
                publishedRelative=relative[:90] if isinstance(relative,str) else '',
                publishedRelativeObservedAt=entry.get('publishedRelativeObservedAt') if isinstance(entry.get('publishedRelativeObservedAt'),(float,int)) else None,
                listingInfo=str(entry.get('listingInfo') or '')[:160],
                checkedAt=entry.get('checkedAt') if isinstance(entry.get('checkedAt'),(float,int)) else None,
                current=False,excerpt='',coverage='Gespeicherte öffentliche Videometadaten; Inhalt nicht erneut geprüft',
                trend='UNKLAR',outlook='UNKLAR',horizon='unbekannt',
                reason='Aus zuletzt bestätigter MCO-Kanalliste wiederhergestellt; keine aktuelle Transkriptprüfung.',
                transcriptAnalyzed=False,trustedTranscript=False)
            result.append(saved)
            if len(result)==25:break
        except (ValueError,TypeError,AttributeError):
            continue
    return result


def handle(conn,action,payload):
    if action=='write':
        entries=sanitize(payload.get('items',[]))
        if not entries:return {'ok':False,'saved':0}
        conn.execute("""INSERT INTO bob_youtube_feed_archive(feed_key,saved_at,items)
            VALUES(%s,now(),%s::jsonb)
            ON CONFLICT(feed_key) DO UPDATE SET saved_at=excluded.saved_at,items=excluded.items""",
            (KEY,json.dumps(entries,ensure_ascii=False)))
        return {'ok':True,'saved':len(entries)}
    if action=='read':
        row=conn.execute("""SELECT saved_at,items FROM bob_youtube_feed_archive
            WHERE feed_key=%s AND saved_at>now()-interval '30 days'""",(KEY,)).fetchone()
        if row:
            return {'items':sanitize(row[1]),'savedAt':row[0].astimezone(timezone.utc).isoformat(),'displayOnly':True}
        return {'items':[],'savedAt':None,'displayOnly':True}
    raise ValueError('Unbekannte Videoarchivaktion')


def request(action,payload):
    base=os.environ.get('PUSH_SERVICE_URL','').rstrip('/')
    token=os.environ.get('PUSH_SERVICE_TOKEN','')
    if not base or not token:
        raise OSError('Dauerhafter YouTube-Speicher nicht konfiguriert')
    if not base.startswith(('https://','http://')):
        base='http://'+base
    req=Request(base+'/youtube-feed/'+action,data=json.dumps(payload,ensure_ascii=False).encode(),
        headers={'Content-Type':'application/json','X-Bob-Push-Token':token},method='POST')
    with build_opener(NoRedirect()).open(req,timeout=9) as response:
        data=response.read(65537)
    if len(data)>65536:raise ValueError('Videoarchivantwort zu groß')
    result=json.loads(data)
    if not isinstance(result,dict):raise ValueError('Ungültige Videoarchivantwort')
    return result
