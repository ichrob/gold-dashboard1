"""Optional native-caption provider, disabled until a server-side key is configured.
Public video IDs only. No paid mode, auto recharge, proxies, or client cookies.
"""
import json
import math
import os
import re
import secrets
import urllib.request
from urllib.parse import urlencode
from bob_auth import NoRedirect

CHANNEL='UCsl6Z6p7GOkczo8Cv-GH6Dg'
MAX_BYTES=600000


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_research_transcripts (
        video_id TEXT PRIMARY KEY, result JSONB, attempted_at TIMESTAMPTZ NOT NULL,
        claim TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_research_requests (
        claim TEXT PRIMARY KEY, attempted_at TIMESTAMPTZ NOT NULL DEFAULT now())''')


def parse(data):
    if not isinstance(data,dict) or not isinstance(data.get('content'),list):raise ValueError('Transkript-Dienst liefert keinen verwendbaren Text')
    language=data.get('lang')
    if not isinstance(language,str) or language.split('-')[0] not in ('de','en'):raise ValueError('Transkript-Sprache wird nicht unterstützt')
    segments=[];size=0
    for row in data['content']:
        if not isinstance(row,dict):raise ValueError('Ungültige Transkriptzeile')
        text=row.get('text');at=row.get('offset')
        if not isinstance(text,str) or isinstance(at,bool) or not isinstance(at,(float,int)) or not math.isfinite(at) or not 0<=at<=86400000:raise ValueError('Ungültige Transkriptzeile')
        row_language=row.get('lang',language)
        if not isinstance(row_language,str) or row_language.split('-')[0]!=language.split('-')[0]:raise ValueError('Gemischte Transkriptsprachen')
        size+=len(text)
        if size>200000 or len(segments)>=30000:raise ValueError('Transkript zu groß')
        if text.strip():segments.append({'at':at/1000,'text':text.strip()})
    if len(' '.join(s['text'] for s in segments).split())<40:raise ValueError('Transkript zu kurz')
    return {'segments':segments,'language':language,'provider':'Supadata · vorhandene YouTube-Untertitel'}


def fetch(identity,key):
    url='https://api.supadata.ai/v1/transcript?'+urlencode({'url':'https://www.youtube.com/watch?v='+identity,'mode':'native','lang':'de','text':'false'})
    request=urllib.request.Request(url,headers={'x-api-key':key,'Accept':'application/json'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=15) as response:
            if response.status!=200:raise ValueError('Transkript noch nicht verfügbar')
            raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('Transkriptantwort zu groß')
        return parse(json.loads(raw))
    except Exception:
        # Provider error bodies can contain credentials. Never forward them.
        raise ValueError('Zusätzlicher Transkript-Dienst derzeit nicht verfügbar; Zugang, Kontingent oder Videoabruf prüfen.') from None


def handle(connect,payload,fetcher=fetch):
    identity=payload.get('videoId','')
    if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',identity) or payload.get('channelId')!=CHANNEL:raise ValueError('Ungültige MCO-Videozuordnung')
    key=os.environ.get('SUPADATA_API_KEY','')
    if not key:raise ValueError('Zusätzlicher Transkript-Abruf vorbereitet; SUPADATA_API_KEY ist noch nicht eingerichtet.')
    claim=secrets.token_hex(16)
    # Durable quota, reservations and cooldown survive rolling deployments.
    # Count attempts conservatively, including failures: <=90 per rolling 31 days.
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(68431029)')
        row=conn.execute('SELECT result,attempted_at>now()-interval \'24 hours\' FROM bob_research_transcripts WHERE video_id=%s',(identity,)).fetchone()
        if row and row[0]:return row[0]
        if row and row[1]:raise ValueError('Untertitelabruf für dieses Video pausiert bis zum nächsten Tag.')
        count=conn.execute("SELECT count(*) FROM bob_research_requests WHERE attempted_at>now()-interval '31 days'").fetchone()[0]
        if count>=90:raise ValueError('Bob-Abruflimit erreicht: maximal 90 Versuche innerhalb von 31 Tagen. Keine automatische Aufladung.')
        conn.execute('INSERT INTO bob_research_requests(claim) VALUES(%s)',(claim,))
        conn.execute('''INSERT INTO bob_research_transcripts(video_id,attempted_at,claim) VALUES(%s,now(),%s)
            ON CONFLICT(video_id) DO UPDATE SET attempted_at=now(),claim=excluded.claim''',(identity,claim))
    result=fetcher(identity,key)
    with connect() as conn:
        conn.execute('UPDATE bob_research_transcripts SET result=%s::jsonb WHERE video_id=%s AND claim=%s',(json.dumps(result),identity,claim))
    return result


def request(identity):
    base=os.environ.get('PUSH_SERVICE_URL','').rstrip('/');token=os.environ.get('PUSH_SERVICE_TOKEN','')
    if not base or not token:raise ValueError('Zusätzlicher Transkript-Abruf nicht angebunden')
    if not base.startswith(('http://','https://')):base='http://'+base
    req=urllib.request.Request(base+'/research-transcript/read',data=json.dumps({'videoId':identity,'channelId':CHANNEL}).encode(),headers={'Content-Type':'application/json','X-Bob-Push-Token':token},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=20) as response:raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('Antwort zu groß')
        result=json.loads(raw)
        if not isinstance(result,dict) or not result.get('segments'):raise ValueError('Text fehlt')
        return result
    except Exception:
        raise ValueError('YouTube liefert keinen Text. Der zusätzliche Transkript-Zugang ist noch nicht eingerichtet oder derzeit nicht verfügbar.') from None
