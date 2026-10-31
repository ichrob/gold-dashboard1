"""Single-ID one-shot coordinator for optional historical decision product pilot.

No server startup hook, HTTP route, or scheduler is registered.
A durable primary-key claim makes a restart incapable of repeating a pilot.
An explicitly invoked manual routine can replace at most one original after
independent restore and disk checks by the verified archive writer.
"""
import json
import os
import re
import time

import cold_metrics as codec
import cold_decision_product_writer as writer

_ID = re.compile(r'[A-Za-z0-9_-]{1,64}\Z')


def configuration():
    raw=os.environ.get('BOB_DECISION_PRODUCT_PILOT_ONCE','')
    if not raw:
        return None
    try:
        value=json.loads(raw)
    except (ValueError,TypeError):
        return None
    if (type(value) is not dict or set(value)!={'id','confirmed','maxUpdates'} or
            type(value.get('id')) is not str or
            not _ID.fullmatch(value['id']) or
            value.get('confirmed') is not True or
            type(value.get('maxUpdates')) is not int or value['maxUpdates'] != 1 or
            os.environ.get('BOB_COLD_DECISION_PRODUCTS_ENABLED') != '1'):
        return None
    return value


def _preflight(conn, seconds):
    """No source write or table creation without independent proof."""
    from storage_budget import archive_status
    proof=archive_status(conn)
    if writer._proof_state(proof,seconds)!='verified-fresh':
        return 'backup-proof-not-fresh'
    try:
        if __import__('archive_worker').status().get('status')=='running':
            return 'full-archive-running'
        volume=__import__('render_disk_metrics').report()
        measured_at=volume.get('observedAt')
        if (volume.get('status')!='observed' or
                volume.get('resource')!='dpg-datjno1srm7s738vv500-a' or
                volume.get('unit')!='bytes' or
                type(measured_at) not in (int,float) or
                not 0 <= seconds-measured_at <=300 or
                type(volume.get('diskUsage')) is not int or
                volume['diskUsage']>750_000_000):
            return 'fresh-volume-proof-unavailable'
    except Exception:
        return 'fresh-volume-proof-unavailable'
    return 'approved-for-single-row-pilot'


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS bob_cold_decision_pilot_attempts (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        moved_rows INTEGER NOT NULL DEFAULT 0,
        error_type TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")


def status(conn):
    """Private reader: never expose attempt IDs or original content."""
    try:
        with conn.transaction():
            row=conn.execute("""SELECT status,moved_rows,error_type,updated_at
                FROM bob_cold_decision_pilot_attempts
                ORDER BY updated_at DESC LIMIT 1""").fetchone()
        if not row:
            return {'status':'no-attempt','readOnly':True}
        return {'status':row[0], 'movedRows':int(row[1]),
                'errorType':row[2], 'updatedAt':str(row[3]),
                'readOnly':True,'diskBytesFreed':None}
    except Exception:
        return {'status':'not-observed','readOnly':True,'diskBytesFreed':None}


def run_once(*,connect=codec.connect,invoke=writer.run_once,now=None):
    """One explicit attempt; at-most-once claim survives process redeploys."""
    config=configuration()
    if config is None:
        return {'status':'disabled','movedRows':0}
    seconds=time.time() if now is None else now
    with connect() as conn:
        if not conn.autocommit:
            raise ValueError('Pilot needs an independent autocommit connection')
        gate=_preflight(conn,seconds)
        if gate!='approved-for-single-row-pilot':
            return {'status':gate,'movedRows':0}
        init(conn)
        claimed=conn.execute("""INSERT INTO bob_cold_decision_pilot_attempts
            (id,status) VALUES(%s,'running')
            ON CONFLICT(id) DO NOTHING RETURNING id""",(config['id'],)).fetchone()
        if not claimed:
            return {'status':'already-claimed','movedRows':0}
        try:
            approval={'restoreVerified':True,'remoteDownloadVerified':True,
                      'observedAt':seconds}
            result=invoke(approval=approval,now=seconds,max_updates=1)
            state=str(result.get('status','unknown'))
            moved=result.get('movedRows')
            if state=='verified-offload' and type(moved) is int and 0<=moved<=1:
                if moved and result.get('readThroughVerified') is not True:
                    raise ValueError('Original read-through not verified')
                state='verified-offload' if moved else 'no-change'
            elif state in ('sweep-completed','no-eligible-rows','page-scanned','busy',
                           'backup-proof-not-fresh','fresh-volume-proof-unavailable'):
                state='deferred-'+state
                moved=0
            else:
                raise ValueError('Pilot returned unsupported state')
            conn.execute("""UPDATE bob_cold_decision_pilot_attempts
                SET status=%s,moved_rows=%s,updated_at=now()
                WHERE id=%s""",(state,moved,config['id']))
            return {'status':state,'movedRows':moved,'diskBytesFreed':None}
        except Exception as exc:
            kind=type(exc).__name__
            conn.execute("""UPDATE bob_cold_decision_pilot_attempts
                SET status='failed',error_type=%s,updated_at=now()
                WHERE id=%s""",(kind,config['id']))
            return {'status':'failed','errorType':kind,'movedRows':0,
                    'diskBytesFreed':None}


