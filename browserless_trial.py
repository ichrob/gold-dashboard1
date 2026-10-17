"""One reserved Browserless session, never an automatic paid/retry fallback."""
import base64
import io
import json
import os
from pathlib import Path

import requests

# One additional attempt authorized after the user replaced the rejected token.
TRIAL = 'mco-single-video-v6'
ENDPOINT = 'https://production-sfo.browserless.io/function'


def capture(token, identity, moments):
    # Never log request exceptions: their URLs can contain the API token.
    try:
        with requests.post(ENDPOINT, params={'token': token, 'timeout': 90000},
                           json={'code': Path(__file__).with_name('browserless_trial.js').read_text(),
                                 'context': {'videoId': identity, 'moments': moments}},
                           timeout=(10, 100), allow_redirects=False, stream=True) as response:
            if response.status_code != 200:
                return 'http-' + str(response.status_code), []
            chunks=[]; size=0
            for chunk in response.iter_content(16384):
                size += len(chunk)
                if size > 500000:return 'response-too-large', []
                chunks.append(chunk)
            result=json.loads(b''.join(chunks))
        # Function API may return its {data, type} envelope or the JSON body.
        if isinstance(result,dict) and isinstance(result.get('data'),dict):
            result=result['data']
        if not isinstance(result,dict):return 'invalid-response', []
        diagnostic=result.get('diagnostic')
        if isinstance(diagnostic,dict):
            # Only public, logged-out YouTube page evidence; never provider errors/URLs.
            allowed=('title','text','player','method','videos','ready','paused','initial','frames','host')
            safe={k:str(diagnostic[k])[:1400].replace(token,'[redacted]') for k in allowed if k in diagnostic}
            print('BOB_BROWSERLESS_PAGE '+json.dumps(safe,ensure_ascii=True),flush=True)
        status=result.get('status')
        safe_statuses={'navigation-failed','consent-required','access-blocked','player-unavailable',
                       'playback-unavailable','identity-unconfirmed','identity-mismatch','metadata-unavailable','seek-failed','screenshot-failed'}
        if status in safe_statuses:return status, []
        if result.get('videoId') != identity:return 'identity-unconfirmed', []
        from video_evidence import checked_frames
        from PIL import Image, ImageStat
        raw=result.get('frames', [])
        if not raw:return 'no-video-frames', []
        if len(raw)>3:return 'invalid-frames', []
        frames=checked_frames(raw)
        for frame in frames:
            if not any(abs(frame['at']-m['at'])<=1 for m in moments):return 'wrong-position', []
            with Image.open(io.BytesIO(base64.b64decode(frame['dataUrl'].split(',')[1]))) as im:
                if max(ImageStat.Stat(im).stddev)<8:return 'blank-frame', []
            frame.update(userProvided=False,sourceKind='browserless',
                         source='YouTube-Videobild · Browserless-Test',
                         label='Videobild · Inhalt noch nicht geprüft')
        return 'captured', frames
    except Exception:
        return 'capture-failed', []


def run_once(connect):
    token=os.environ.get('BROWSERLESS_API_TOKEN', '').strip()
    if not token:
        print('BOB_BROWSERLESS_TRIAL status=not-configured', flush=True)
        return
    try:
        import youtube_feed_archive as archive
        from research_enhancements import summary_moments
        with connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS bob_browserless_trial (
                trial TEXT PRIMARY KEY, status TEXT NOT NULL, frame_count INTEGER NOT NULL DEFAULT 0,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now())''')
            row=conn.execute('SELECT items FROM bob_youtube_feed_archive WHERE feed_key=%s',(archive.KEY,)).fetchone()
            entries=archive.sanitize(row[0]) if row else []
            candidate=None
            for identity in archive.selected_ids(entries):
                saved=conn.execute('SELECT summary FROM bob_research_enhancements WHERE video_id=%s',(identity,)).fetchone()
                moments=summary_moments(saved[0] or {}) if saved else []
                if moments:
                    candidate=(identity,moments[:3]);break
            if not candidate:
                print('BOB_BROWSERLESS_TRIAL status=no-source-moments',flush=True);return
            reservation=conn.execute('''INSERT INTO bob_browserless_trial(trial,status) VALUES(%s,'reserved')
                ON CONFLICT DO NOTHING RETURNING trial''',(TRIAL,)).fetchone()
        if not reservation:
            print('BOB_BROWSERLESS_TRIAL status=already-reserved',flush=True);return
        print('BOB_BROWSERLESS_TRIAL status=started session_limit=1 image_limit=3',flush=True)
        identity,moments=candidate
        status,frames=capture(token,identity,moments)
        with connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(68431030)')
            if frames and archive.is_retained(conn,identity):
                old=conn.execute('SELECT frames FROM bob_research_enhancements WHERE video_id=%s',(identity,)).fetchone()
                if old and not any(not f.get('isCover') for f in (old[0] or [])):
                    conn.execute('''UPDATE bob_research_enhancements SET frames=%s::jsonb,
                        frame_status='browserless-trial',frame_attempt=now(),updated_at=now() WHERE video_id=%s''',
                        (json.dumps(frames),identity))
                    status='saved'
                else:status='existing-images-preserved'
            elif frames:status='video-removed'
            conn.execute('UPDATE bob_browserless_trial SET status=%s,frame_count=%s,updated_at=now() WHERE trial=%s',
                         (status,len(frames),TRIAL))
        print('BOB_BROWSERLESS_TRIAL status='+status+' images='+str(len(frames)),flush=True)
    except Exception:
        print('BOB_BROWSERLESS_TRIAL status=internal-failure',flush=True)
