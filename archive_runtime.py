"""Internal encrypted-credential bridge and resumable private folder preparation.

Preparation creates only an empty app-owned folder. Export remains separately gated.
"""
import json
import os
import re
import archive_connection

KEY = 'bob_archive_runtime_v1'
FOLDER_NAME = 'Bob – Originalarchive (automatisch)'


def load(conn):
    row = conn.execute('SELECT value FROM bob_settings WHERE key=%s', (KEY,)).fetchone()
    return json.loads(row[0]) if row else {}


def save(conn, state):
    conn.execute('INSERT INTO bob_settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                 (KEY, json.dumps(state)))


def credentials(conn):
    row = conn.execute('SELECT value FROM bob_settings WHERE key=%s', (archive_connection.KEY,)).fetchone()
    if not row:
        raise ValueError('Google consent missing')
    state = json.loads(archive_connection.cipher().decrypt(row[0].encode()))
    info = state.get('credentials', {})
    if (info.get('type') != 'authorized_user' or info.get('scopes') != [archive_connection.SCOPE]
            or info.get('token_uri') != 'https://oauth2.googleapis.com/token'
            or not info.get('refresh_token')):
        raise ValueError('Narrow offline consent required')
    return info


def drive_client(db):
    from drive_evidence_archive import GoogleDrive
    with db() as conn:
        info = credentials(conn)
        state = load(conn)
    return GoogleDrive(info=info, folder_id=state.get('folderId', ''),
                       parent_id=os.environ.get('BOB_ARCHIVE_PARENT_FOLDER_ID', ''))


def prepare(db):
    """Persist a generated Drive ID before creation: retries cannot duplicate folders."""
    from drive_evidence_archive import GoogleDrive
    with db() as conn:
        info = credentials(conn)
    drive = GoogleDrive(info=info, folder_id='')
    with db() as conn:
        conn.execute('SELECT pg_advisory_xact_lock(736981025)')
        state = load(conn)
        if not state.get('folderId'):
            reply = drive.api.files().generateIds(count=1, space='drive', type='files').execute()
            folder_id = reply['ids'][0]
            if not re.fullmatch(r'[A-Za-z0-9_-]{10,200}', folder_id):
                raise ValueError('Invalid generated folder ID')
            state = {'folderId': folder_id}
            save(conn, state)
    folder_id = state['folderId']
    fields = 'id,mimeType,trashed,shared,parents,capabilities(canAddChildren),appProperties'
    try:
        folder = drive.api.files().get(fileId=folder_id, fields=fields).execute()
    except Exception as error:
        if getattr(getattr(error, 'resp', None), 'status', None) != 404:
            raise
        folder = drive.api.files().create(body={'id':folder_id, 'name':FOLDER_NAME,
            'mimeType':'application/vnd.google-apps.folder',
            'appProperties':{'bobArchiveFolder':'v1'}}, fields=fields).execute()
    if (folder.get('id') != folder_id or folder.get('shared') is not False or folder.get('trashed')
            or folder.get('mimeType') != 'application/vnd.google-apps.folder'
            or folder.get('appProperties', {}).get('bobArchiveFolder') != 'v1'
            or folder.get('capabilities', {}).get('canAddChildren') is not True):
        raise ValueError('Private app-owned folder required')
    parent = os.environ.get('BOB_ARCHIVE_PARENT_FOLDER_ID', '')
    placed = bool(parent) and folder.get('parents') == [parent]
    return {'status':'prepared' if placed else 'awaiting-folder-placement',
            'folderId':folder_id, 'evidenceDeleted':False, 'archiveEnabled':False}
