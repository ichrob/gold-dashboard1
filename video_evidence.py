"""Private, bounded user-supplied video stills. No video uploads or paid services."""
import base64
import io
import json
import math
import re


def checked_frames(value):
    from PIL import Image
    if not isinstance(value,list) or not 1<=len(value)<=5:raise ValueError('Ein bis fünf Bilder erforderlich')
    out=[]
    for frame in value:
        if not isinstance(frame,dict):raise ValueError('Ungültiges Bild')
        at=frame.get('at');url=frame.get('dataUrl')
        if isinstance(at,bool) or not isinstance(at,(float,int)) or not math.isfinite(at) or not 0<=at<=86400:raise ValueError('Ungültige Videoposition')
        if not isinstance(url,str) or not re.fullmatch(r'data:image/jpeg;base64,[A-Za-z0-9+/=]{100,140000}',url):raise ValueError('Ungültiges JPEG')
        raw=base64.b64decode(url.split(',')[1],validate=True)
        with Image.open(io.BytesIO(raw)) as im:
            if im.format!='JPEG' or im.width*im.height>500000 or im.width<200 or im.height<100:raise ValueError('Ungültige Bildgröße')
            im.load();clean=io.BytesIO();im.convert('RGB').save(clean,'JPEG',quality=82)
        data='data:image/jpeg;base64,'+base64.b64encode(clean.getvalue()).decode()
        if len(data)>140000:raise ValueError('Bild zu groß')
        out.append(dict(at=round(at,3),dataUrl=data,isCover=False,userProvided=True,
                        source='Vom Nutzer zugeordnete Videodatei',label='Videodatei · Zuordnung durch Nutzer'))
    if len({f['at'] for f in out})!=len(out):raise ValueError('Doppelte Videopositionen')
    return sorted(out,key=lambda f:f['at'])


def handle(connect,payload):
    import video_ocr
    import youtube_feed_archive
    identity=payload.get('videoId','')
    if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}',identity):raise ValueError('Ungültiges Video')
    action=payload.get('action','read')
    if action not in ('read','write'):raise ValueError('Ungültige Aktion')
    frames=checked_frames(payload.get('frames')) if action=='write' else None
    with connect() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(68431030)')
        if not youtube_feed_archive.is_retained(conn,identity):raise ValueError('Video gehört nicht zu den drei gespeicherten MCO-Videos')
        if action=='write':
            if payload.get('assignedByUser') is not True:raise ValueError('Bitte Videodatei zuordnen')
            row=conn.execute('SELECT frame_attempt>now()-interval \'2 minutes\' FROM bob_research_enhancements WHERE video_id=%s',(identity,)).fetchone()
            if row and row[0]:raise ValueError('Bitte zwei Minuten seit dem letzten Bildabruf warten')
            # Reset image-linked summaries, keeping their rate-limit accounting.
            conn.execute('''INSERT INTO bob_research_enhancements(video_id,fingerprint,frames,frame_attempt,frame_status)
                VALUES(%s,'user-video',%s::jsonb,now(),'user-video') ON CONFLICT(video_id) DO UPDATE
                SET frames=excluded.frames,summary=NULL,frame_attempt=now(),frame_status='user-video',updated_at=now()''',
                (identity,json.dumps(frames)))
            conn.commit()
        row=conn.execute('SELECT frames,summary FROM bob_research_enhancements WHERE video_id=%s',(identity,)).fetchone()
        return dict(frames=row[0] if row and row[0] else [],summary=row[1] if row else None,ocr=video_ocr.report(conn,identity))
