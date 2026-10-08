"""Optional native-caption provider, disabled until a server-side key is configured.
Public video IDs only. No paid mode, auto recharge, proxies, or client cookies.
"""
import json
import math
import os
import re
import secrets
import urllib.request
import urllib.error
from urllib.parse import urlencode
from bob_auth import NoRedirect

CHANNEL='UCsl6Z6p7GOkczo8Cv-GH6Dg'
MAX_BYTES=600000
ERRORS = {
    'provider_auth': 'Transkript-Dienst: API-Schlüssel wird nicht akzeptiert.',
    'provider_limit': 'Transkript-Dienst: Kontingent oder Abrufrate erreicht.',
    'provider_unavailable': 'Transkript-Dienst vorübergehend nicht erreichbar.',
    'provider_video': 'Transkript-Dienst kann für dieses Video derzeit keinen Text liefern.',
    'provider_invalid': 'Transkript-Dienst liefert keinen verwendbaren deutschen oder englischen Text.',
    'provider_pending': 'Transkript-Dienst hat den Text noch nicht bereitgestellt.',
    'not_configured': 'SUPADATA_API_KEY ist im Transkript-Dienst noch nicht eingerichtet.',
    'cooldown': 'Nach einem fehlgeschlagenen Abruf pausiert dieses Video eine Stunde. Andere Videos werden weiter geprüft.',
    'video_limit': 'Für dieses Video wurden die drei Abrufversuche innerhalb von 24 Stunden erreicht. Bob versucht es später automatisch erneut.',
    'local_limit': 'Bob-Abruflimit erreicht: maximal 90 Versuche innerhalb von 31 Tagen. Keine automatische Aufladung.',
}

class TranscriptError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(ERRORS[code])



def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_research_transcripts (
        video_id TEXT PRIMARY KEY, result JSONB, attempted_at TIMESTAMPTZ NOT NULL,
        claim TEXT NOT NULL)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_research_requests (
        claim TEXT PRIMARY KEY, attempted_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
    conn.execute('ALTER TABLE bob_research_requests ADD COLUMN IF NOT EXISTS video_id TEXT')


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
            if response.status!=200:raise TranscriptError('provider_pending')
            raw=response.read(MAX_BYTES+1)
        if len(raw)>MAX_BYTES:raise ValueError('Transkriptantwort zu groß')
        return parse(json.loads(raw))
    except TranscriptError:
        raise
    except urllib.error.HTTPError as exc:
        code = 'provider_auth' if exc.code in (401,403) else 'provider_limit' if exc.code in (402,429) else 'provider_unavailable' if exc.code >= 500 else 'provider_video'
        raise TranscriptError(code) from None
    except (ValueError, TypeError, KeyError):
        raise TranscriptError('provider_invalid') from None
    except Exception:
        # Never forward provider bodies, URLs, keys or raw exceptions.
        raise TranscriptError('provider_unavailable') from None


def handle(connect,payload,fetcher=fetch):
    identity=payload.get('videoId','')
    if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',identity) or payload.get('channelId')!=CHANNEL:raise ValueError('Ungültige MCO-Videozuordnung')
    key=os.environ.get('SUPADATA_API_KEY','')
    if not key:raise TranscriptError('not_configured')
    claim=secrets.token_hex(16)
    # Durable quota, reservations and cooldown survive rolling deployments.
    # Count attempts conservatively, including failures: <=90 per rolling 31 days.
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(68431029)')
        row=conn.execute('SELECT result,attempted_at>now()-interval \'1 hour\' FROM bob_research_transcripts WHERE video_id=%s',(identity,)).fetchone()
        if row and row[0]:return row[0]
        if row and row[1]:raise TranscriptError('cooldown')
        video_count=conn.execute("SELECT count(*) FROM bob_research_requests WHERE video_id=%s AND attempted_at>now()-interval '24 hours'",(identity,)).fetchone()[0]
        if video_count>=3:raise TranscriptError('video_limit')
        count=conn.execute("SELECT count(*) FROM bob_research_requests WHERE attempted_at>now()-interval '31 days'").fetchone()[0]
        if count>=90:raise TranscriptError('local_limit')
        conn.execute('INSERT INTO bob_research_requests(claim,video_id) VALUES(%s,%s)',(claim,identity))
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
    except urllib.error.HTTPError as exc:
        code = None
        try:
            body = json.loads(exc.read(4096))
            candidate = body.get('errorCode') if isinstance(body, dict) else None
            if isinstance(candidate, str) and candidate in ERRORS:code = candidate
        except Exception:pass
        if code:raise TranscriptError(code) from None
        if exc.code == 401:raise ValueError('Interne Verbindung zum Transkript-Dienst nicht autorisiert.') from None
        raise ValueError('Transkript-Dienst meldet einen Abruffehler (HTTP '+str(exc.code)+').') from None
    except Exception:
        raise ValueError('Interne Verbindung zum Transkript-Dienst derzeit nicht verfügbar.') from None
