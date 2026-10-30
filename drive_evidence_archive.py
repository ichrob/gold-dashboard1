"""One bounded archive run; scheduling requires separately configured runtime access.

No new service, paid scaling, source deletion, email, or trading side effects.
The ChatGPT Drive connector does not provide runtime OAuth credentials to Bob.
"""
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

import evidence_archive as archive

# Folder identity is private configuration, never committed to this public repo.
FOLDER_ID = os.environ.get('BOB_ARCHIVE_DRIVE_FOLDER_ID', '')
RESERVE_BYTES = 256 * 1024 * 1024


class GoogleDrive:
    def __init__(self, info=None, folder_id=None, parent_id=None):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        # Supply through an approved secret store, never logs or repository.
        info = info if info is not None else json.loads(os.environ['BOB_ARCHIVE_GOOGLE_AUTHORIZED_USER_JSON'])
        self.folder_id = FOLDER_ID if folder_id is None else folder_id
        self.parent_id = parent_id
        credentials = Credentials.from_authorized_user_info(info)
        from google_auth_httplib2 import AuthorizedHttp
        from httplib2 import Http
        self.api = build('drive', 'v3', http=AuthorizedHttp(credentials, http=Http(timeout=30)), cache_discovery=False)

    def preflight(self, required_bytes):
        if not self.folder_id:
            raise ValueError('Private archive folder is not configured')
        folder = self.api.files().get(fileId=self.folder_id,
            fields='id,mimeType,trashed,shared,parents,capabilities(canAddChildren)').execute()
        if (folder.get('trashed') or folder.get('shared') is not False or
            folder.get('mimeType') != 'application/vnd.google-apps.folder' or
            not folder.get('capabilities', {}).get('canAddChildren')):
            raise ValueError('Private writable archive folder not verified')
        if self.parent_id is not None and (not self.parent_id or folder.get('parents') != [self.parent_id]):
            raise ValueError('Archive parent placement not verified')
        quota = self.api.about().get(fields='storageQuota').execute()['storageQuota']
        if 'limit' not in quota or 'usage' not in quota:
            raise ValueError('Drive quota unknown; no upload permitted')
        available = int(quota['limit']) - int(quota['usage'])
        if available < required_bytes + RESERVE_BYTES:
            raise ValueError('Drive reserve reached; no upgrade or deletion permitted')
        return dict(availableBytes=available, reserveBytes=RESERVE_BYTES)

    def upload(self, path, checksum):
        from googleapiclient.http import MediaFileUpload
        self.preflight(Path(path).stat().st_size)
        request = self.api.files().create(body=dict(name=Path(path).name, parents=[self.folder_id],
            appProperties={'bobArchiveSha256': checksum}),
            media_body=MediaFileUpload(str(path), chunksize=4*1024*1024, resumable=True),
            fields='id,size,parents,shared,sha256Checksum')
        result = None
        while result is None:
            _, result = request.next_chunk(num_retries=2)
        if (result.get('shared') is not False or result.get('parents') != [self.folder_id] or
            int(result.get('size', -1)) != Path(path).stat().st_size or
            result.get('sha256Checksum') != checksum):
            raise ValueError('Uploaded metadata mismatch; no verification receipt')
        return result['id']

    def download(self, file_id, destination):
        from googleapiclient.http import MediaIoBaseDownload
        with open(destination, 'xb') as out:
            os.chmod(destination, 0o600)
            request = MediaIoBaseDownload(out, self.api.files().get_media(fileId=file_id), chunksize=4*1024*1024)
            done = False
            while not done:
                _, done = request.next_chunk(num_retries=2)
                if out.tell() > archive.MAX_BYTES + 2*1024*1024:
                    raise ValueError('Downloaded archive exceeds bounded size')


def verify_restore_isolation(source_dsn, restore_dsn):
    """Fail before export if configuration aliases the production server.

    Both probes are read-only. No credentials, hostnames or network addresses are
    returned. A separate database name alone does not isolate disk or compute.
    """
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    source = conninfo_to_dict(source_dsn)
    target = conninfo_to_dict(restore_dsn)
    if not source.get('host') or not target.get('host') or source['host'] == target['host']:
        raise ValueError('Separate restore server required')
    identities = []
    for dsn in (source_dsn, restore_dsn):
        with psycopg.connect(dsn, connect_timeout=10, options='-c statement_timeout=10000') as conn:
            conn.execute('SET TRANSACTION READ ONLY')
            row = conn.execute('SELECT inet_server_addr()::text, inet_server_port(), current_database(), pg_is_in_recovery()').fetchone()
            if not row or not row[0] or row[3]:
                raise ValueError('Writable separate restore server not verified')
            identities.append(row)
    if identities[0][0] == identities[1][0] or identities[0][2] == identities[1][2]:
        raise ValueError('Separate restore server and database required')
    return 'separate-database-instance'


def run(source_dsn, restore_dsn, work_directory, drive, *, temporary_session=False, progress=None):
    """Retain local evidence on failure; receipt exists only after remote restore.

    No schedule is installed by this function. Use an existing authorized runner
    only after real export, download and isolated restore have passed.
    """
    progress = progress or (lambda phase: None)
    progress('drive-preflight')
    root = Path(work_directory)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    work = Path(tempfile.mkdtemp(prefix='bob-archive-', dir=root))
    now = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    path = work / f'bob-evidence-{now}.zip'
    quota = drive.preflight(archive.MAX_BYTES + 2*1024*1024)
    progress('restore-isolation-check')
    isolation = verify_restore_isolation(source_dsn, restore_dsn)
    progress('export')
    result = archive.export(source_dsn, path)
    checksum = result['sha256']
    # Check locally before consuming Drive storage, then restore again from Drive.
    progress('local-restore')
    archive.restore_check(path, checksum, restore_dsn, temporary_session=temporary_session)
    progress('upload')
    file_id = drive.upload(path, checksum)
    downloaded = work / 'downloaded.zip'
    progress('download')
    drive.download(file_id, downloaded)
    progress('remote-restore')
    receipt = archive.restore_check(downloaded, checksum, restore_dsn, temporary_session=temporary_session)
    receipt.update(restoreIsolation=isolation, driveFileId=file_id, driveFolderId=getattr(drive, 'folder_id', FOLDER_ID),
        remoteDownloadVerified=True, driveQuotaBefore=quota,
        databaseBytes=result['databaseBytes'],
        storageState=('action-required' if result['databaseBytes'] >= 700_000_000 else
                      'caution' if result['databaseBytes'] >= 500_000_000 else 'below-budget-threshold'))
    receipt_path = work / f'bob-evidence-{now}-verified.json'
    receipt_path.write_text(json.dumps(receipt, sort_keys=True, indent=2))
    os.chmod(receipt_path, 0o600)
    progress('receipt-upload')
    receipt_id = drive.upload(receipt_path, archive.digest(receipt_path))
    # Only redundant scratch copies after verified remote restore and receipt.
    # Database originals and the durable Drive archive remain untouched.
    downloaded.unlink()
    path.unlink()
    return dict(**receipt, receiptFileId=receipt_id)


if __name__ == '__main__':
    # Missing credentials fail before export. Do not print exception details that
    # could contain connection strings, OAuth content or signed upload URLs.
    try:
        result = run(os.environ['DATABASE_URL'], os.environ['BOB_ARCHIVE_RESTORE_DATABASE_URL'],
                     os.environ['BOB_ARCHIVE_WORK_DIRECTORY'], GoogleDrive())
    except Exception as error:
        print(json.dumps(dict(status='blocked-or-failed', errorType=type(error).__name__,
                              evidenceDeleted=False, deletionPermitted=False)))
        raise SystemExit(1)
    print(json.dumps(result, sort_keys=True))
