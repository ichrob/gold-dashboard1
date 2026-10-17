"""Named Browserless profile handoff. Never handles passwords or profile contents."""
import hashlib
import json
import os
import threading

import requests

PROFILE='bob-mco-youtube'
ORIGIN='https://production-sfo.browserless.io'
MESSAGES={
 'not-configured':'Browserless-Schlüssel fehlt auf dem Server.',
 'profile-missing':'Noch kein Profil bob-mco-youtube für Bobs API-Schlüssel gefunden.',
 'profile-unavailable':'Profilprüfung nicht möglich. Browserless-Zugang oder Tarif prüfen; kein kostenpflichtiger Ersatz.',
 'profile-ready':'Anmeldeprofil vorhanden. Ob YouTube das Video abspielt, muss der Bildtest zeigen.',
 'running':'Bildtest läuft auf dem Server (höchstens 90 Sekunden).',
 'saved':'Videobilder gespeichert. Die Chartinhalte sind noch nicht manuell geprüft.',
 'existing-images-preserved':'Vorhandene Videobilder wurden beibehalten.',
 'access-blocked':'YouTube verlangt weiterhin eine Anmeldung oder Bestätigung. Automatik bleibt pausiert.',
 'quota':'Drei Bildtests heute erreicht. Morgen ist wieder ein Test möglich.',
 'busy':'Ein Bildtest läuft bereits. Bitte kurz warten.',
 'no-source-moments':'Für dieses Video fehlen zeitlich belegte Textstellen.',
 'video-removed':'Dieses Video gehört nicht mehr zu den gespeicherten MCO-Videos.',
 'interrupted':'Bildtest abgebrochen oder Zeitlimit erreicht. Kein automatischer Neuversuch.',
}


def init(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS bob_browserless_profile_jobs(
        job TEXT PRIMARY KEY,video_id TEXT NOT NULL,status TEXT NOT NULL,
        images INTEGER NOT NULL DEFAULT 0,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now())''')


def profile_revision():
    token=os.environ.get('BROWSERLESS_API_TOKEN','').strip()
    if not token:return 'not-configured',None
    try:
        with requests.get(ORIGIN+'/profile/'+PROFILE,params={'token':token},
                          timeout=(5,10),allow_redirects=False,stream=True) as response:
            if response.status_code==404:return 'profile-missing',None
            if response.status_code!=200:return 'profile-unavailable',None
            data=b''
            for chunk in response.iter_content(4096):
                data+=chunk
                if len(data)>16384:return 'profile-unavailable',None
            info=json.loads(data)
        if not isinstance(info,dict) or info.get('name')!=PROFILE:return 'profile-missing',None
        if not info.get('updatedAt'):return 'profile-unavailable',None
        # Metadata only. Never request /download, cookies or account identity.
        revision=hashlib.sha256(str(info['updatedAt']).encode()).hexdigest()[:24]
        return 'profile-ready',revision
    except Exception:return 'profile-unavailable',None


def result(status,images=0):
    return {'profileName':PROFILE,'status':status,'images':images,
            'message':MESSAGES.get(status,'Bildtest ohne gespeicherte Bilder abgeschlossen ('+status+').')}


def status(connect,identity):
    with connect() as conn:
        init(conn)
        row=conn.execute('''SELECT status,images,created_at < now()-interval '3 minutes'
            FROM bob_browserless_profile_jobs WHERE video_id=%s ORDER BY created_at DESC LIMIT 1''',(identity,)).fetchone()
    if not row:return result('profile-missing')
    return result('interrupted' if row[0]=='running' and row[2] else row[0],row[1])


def start(connect,identity):
    from research_enhancements import summary_moments
    import youtube_feed_archive as archive
    state,revision=profile_revision()
    if state!='profile-ready':return result(state)
    job=hashlib.sha256((PROFILE+revision+identity).encode()).hexdigest()
    with connect() as conn:
        init(conn)
        conn.execute('SELECT pg_advisory_xact_lock(68431031)')
        if not archive.is_retained(conn,identity):return result('video-removed')
        old=conn.execute('SELECT status,images FROM bob_browserless_profile_jobs WHERE job=%s',(job,)).fetchone()
        if old:return result(old[0],old[1])
        busy=conn.execute("SELECT count(*) FROM bob_browserless_profile_jobs WHERE status='running' AND created_at>now()-interval '3 minutes'").fetchone()[0]
        if busy:return result('busy')
        count=conn.execute("SELECT count(*) FROM bob_browserless_profile_jobs WHERE created_at>now()-interval '24 hours'").fetchone()[0]
        if count>=3:return result('quota')
        saved=conn.execute('SELECT summary FROM bob_research_enhancements WHERE video_id=%s',(identity,)).fetchone()
        moments=summary_moments(saved[0] or {})[:3] if saved else []
        if not moments:return result('no-source-moments')
        conn.execute("INSERT INTO bob_browserless_profile_jobs(job,video_id,status) VALUES(%s,%s,'running')",(job,identity))
    # Durable reservation is committed before spending any browser units.
    threading.Thread(target=worker,args=(connect,job,identity,moments),name='bob-profile-frame-test',daemon=True).start()
    return result('running')


def worker(connect,job,identity,moments):
    import browserless_trial
    import youtube_feed_archive as archive
    try:
        state,frames=browserless_trial.capture(os.environ.get('BROWSERLESS_API_TOKEN','').strip(),identity,moments,profile=PROFILE)
        with connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(68431030)')
            if frames and archive.is_retained(conn,identity):
                old=conn.execute('SELECT frames FROM bob_research_enhancements WHERE video_id=%s',(identity,)).fetchone()
                if old and not any(not f.get('isCover') for f in (old[0] or [])):
                    conn.execute("UPDATE bob_research_enhancements SET frames=%s::jsonb,frame_status='browserless-profile',frame_attempt=now(),updated_at=now() WHERE video_id=%s",(json.dumps(frames),identity))
                    state='saved'
                else:state='existing-images-preserved'
            elif frames:state='video-removed'
            conn.execute('UPDATE bob_browserless_profile_jobs SET status=%s,images=%s,updated_at=now() WHERE job=%s',(state,len(frames),job))
        print('BOB_BROWSERLESS_PROFILE status='+state+' images='+str(len(frames)),flush=True)
    except Exception:
        # No exception strings: provider URLs can include credentials.
        print('BOB_BROWSERLESS_PROFILE status=internal-failure',flush=True)


def probe():
    state,_=profile_revision()
    print('BOB_BROWSERLESS_PROFILE setup='+state,flush=True)
