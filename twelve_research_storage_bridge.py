"""Manual-only storage proofs for Bob's licensed Twelve Data research.

No scheduler/import from startup or trading services. The Aiven component
observes an existing *restore* target read-only; it never writes a ledger.
The Drive component uploads a small SYNTHETIC, encrypted canary into a
separate private app-accessible folder. It NEVER exports actual licensed bars.
ChatGPT's Drive connector does not provide Bob runtime OAuth credentials.
"""
import hashlib
import json
import os
from pathlib import Path
import secrets
import tempfile


def aiven_readiness(inspect=None):
    """Report observation without implying RAM safety or write permission."""
    if inspect is None:
        from aiven_health import inspect
    report = inspect()
    status = report.get('status', 'not-observed')
    if status != 'observed':
        code = 'AIVEN_UNVERIFIED'
    elif report.get('findings') or report.get('clientConnections', 99) >= 15:
        code = 'AIVEN_BUSY'
    else:
        code = 'AIVEN_READ_ONLY_OBSERVED'
    return {'code': code, 'readOnly': True, 'writesEnabled': False,
            'hostRamVerified': False,
            'readyForQuotaLedger': False, 'licensedBarsStored': False}


def drive_scope(env=None):
    """No cross-contamination with Bob's existing evidence archive."""
    env = os.environ if env is None else env
    if env.get('BOB_TWELVE_DRIVE_SYNTHETIC_TEST') != '1':
        return {'code': 'MANUAL_TEST_NOT_AUTHORIZED'}
    folder = env.get('BOB_TWELVE_RESEARCH_DRIVE_FOLDER_ID', '')
    parent = env.get('BOB_TWELVE_RESEARCH_PRIVATE_PARENT_ID', '')
    if (not folder or not parent or len(folder) > 200 or len(parent) > 200
            or folder == parent
            or folder == env.get('BOB_ARCHIVE_DRIVE_FOLDER_ID')):
        return {'code': 'DEDICATED_PRIVATE_FOLDER_REQUIRED'}
    return {'code': 'SYNTHETIC_TEST_ALLOWED'}


def synthetic_drive_roundtrip(drive, env=None):
    """Encrypt, upload, independently download and authenticate one fake sample.

    A synthetic canary stays in the dedicated private folder on success.
    Never issue a false success after a partial upload or corrupt download.
    No actual Twelve Data data, indicators, API key or product prices are read.
    """
    if drive_scope(env)['code'] != 'SYNTHETIC_TEST_ALLOWED':
        return {'code': drive_scope(env)['code'], 'licensedBarsStored': False}
    import drive_archive_encryption as sealing
    # Unique fixed-format random fixture; no external or original inputs.
    payload = b'BOB-TWELVE-DRIVE-SYNTHETIC-V1\n' + secrets.token_bytes(128)
    with tempfile.TemporaryDirectory(prefix='bob-td-storage-') as work:
        p = Path(work)
        original = p / 'synthetic-fixture.bin'
        encrypted = p / ('twelve-synthetic-' + secrets.token_hex(8) + '.aesgcm')
        downloaded = p / 'received.aesgcm'
        restored = p / 'restored.bin'
        original.write_bytes(payload)
        original.chmod(0o600)
        plain_hash = hashlib.sha256(payload).hexdigest()
        proof = sealing.seal(original, encrypted, plain_hash)
        original.unlink()
        drive.preflight(proof['ciphertextBytes'])
        file_id = drive.upload(encrypted, proof['ciphertextSha256'])
        drive.download(file_id, downloaded, max_bytes=1024 * 1024)
        if hashlib.sha256(downloaded.read_bytes()).hexdigest() != proof['ciphertextSha256']:
            return {'code': 'REMOTE_CIPHERTEXT_MISMATCH',
                    'licensedBarsStored': False}
        sealing.unseal(downloaded, restored, plain_hash)
        if restored.read_bytes() != payload:
            return {'code': 'REMOTE_RESTORE_MISMATCH',
                    'licensedBarsStored': False}
    return {'code': 'SYNTHETIC_DRIVE_ROUNDTRIP_VERIFIED',
            'encrypted': True, 'remoteDownloadVerified': True,
            'licensedBarsStored': False, 'originalsDeleted': False}


def run_manual(env=None, drive=None, inspect=None):
    env = os.environ if env is None else env
    aiven = aiven_readiness(inspect)
    scope = drive_scope(env)
    if scope['code'] != 'SYNTHETIC_TEST_ALLOWED':
        return {'aiven': aiven, 'drive': scope}
    if drive is None:
        # Google's own narrow app authorization must be configured separately.
        from drive_evidence_archive import GoogleDrive
        drive = GoogleDrive(folder_id=env['BOB_TWELVE_RESEARCH_DRIVE_FOLDER_ID'],
                            parent_id=env['BOB_TWELVE_RESEARCH_PRIVATE_PARENT_ID'])
    return {'aiven': aiven, 'drive': synthetic_drive_roundtrip(drive, env)}


def main():
    # An explicit operator command only. Never add to gunicorn, startup,
    # CI credentials or a timed task. Results contain statuses only.
    try:
        result = run_manual()
    except Exception:
        result = {'aiven': {'code': 'UNVERIFIED', 'writesEnabled': False},
                  'drive': {'code': 'TEST_FAILED', 'licensedBarsStored': False}}
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get('drive', {}).get('code') == 'SYNTHETIC_DRIVE_ROUNDTRIP_VERIFIED' else 2


if __name__ == '__main__':
    raise SystemExit(main())
