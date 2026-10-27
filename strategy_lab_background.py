"""Independent daily background driver for read-only Zukunft research.

No manual browser visit is needed. Runs in Bob's server process, retries
temporary failures, stores on Bob's existing private PostgreSQL service.
Does not touch live decisions, subscriptions, brokers, or paper portfolios.
"""
import copy
import json
import os
import threading
import time
from datetime import datetime
from urllib.request import Request, build_opener
from zoneinfo import ZoneInfo

from bob_auth import NoRedirect
import strategy_lab
import research_learning

TZ = ZoneInfo("Europe/Zurich")
POLL_SECONDS = 300
RETRY_SECONDS = 1800
_lock = threading.Lock()
_thread = None
_state = dict(enabled=False, running=False, phase="starting", lastAttemptAt=None,
              lastSuccessAt=None, lastRunDay=None, error=None)


def trading_day(now=None):
    now = now or datetime.now(TZ)
    local = now.astimezone(TZ)
    return local.date().isoformat() if local.weekday() < 5 and 8 <= local.hour < 21 else None


def research_day(now=None):
    """Weekday research plus a single mid-day weekend integrity audit."""
    now = now or datetime.now(TZ)
    local = now.astimezone(TZ)
    normal = trading_day(local)
    if normal:
        return normal
    if local.weekday() >= 5 and 11 <= local.hour < 17:
        return local.date().isoformat()
    return None


def request(action, payload):
    base = os.environ.get("PUSH_SERVICE_URL", "").rstrip("/")
    token = os.environ.get("PUSH_SERVICE_TOKEN", "")
    if not base or not token:
        raise OSError("Privater Forschungsarchivzugang fehlt")
    if not base.startswith(("https://","http://")):
        base="http://"+base
    data=json.dumps(payload, allow_nan=False).encode("utf-8")
    req=Request(base+"/strategy-lab/"+action, data=data, method="POST", headers={
        "Content-Type":"application/json", "X-Bob-Push-Token":token})
    with build_opener(NoRedirect()).open(req,timeout=14) as response:
        raw=response.read(1000001) if payload.get("replayId") else response.read(262145)
    if len(raw)>(1000000 if payload.get("replayId") else 262144):
        raise ValueError("Forschungsarchiv-Antwort zu gross")
    parsed=json.loads(raw)
    if not isinstance(parsed,dict):
        raise ValueError("Forschungsarchiv-Antwort ungültig")
    return parsed


def verified_hourly_research_archive(short_rows, *, now=None):
    """Use the single-source XAU/USD hourly archive for research, never live signals.

    Research's direct 3mo query can return fewer bars than Bob's already
    verified candle archive. Replace the short series ONLY with a whole,
    newer or equally current, source-identical closed series; never splice
    providers, resample hours, or manufacture candles/timestamps.
    """
    import candle_reliability as archive
    from market_review import frame_health
    observed = now or datetime.now(TZ)
    if observed.tzinfo is None:
        return None
    try:
        with archive._LOCK:
            saved = copy.deepcopy(archive._ROWS.get('xaus/1h') or [])
        required = (strategy_lab.TRAIN_END + strategy_lab.HORIZON +
                    strategy_lab.VALIDATION + strategy_lab.HORIZON + strategy_lab.TEST)
        if len(saved) < required or len(saved) <= len(short_rows):
            return None
        checked = archive.validated('xaus/1h', saved, now=observed.timestamp())
        if frame_health(checked, '1h', observed.timestamp()*1000)['state'] != 'ok':
            return None
        recent = [b['openTime'] for b in short_rows
                  if isinstance(b, dict) and type(b.get('openTime')) in (int, float)
                  and b.get('isOpen') is False]
        # A current source cannot be replaced by a materially older archive.
        if recent and checked[-1]['openTime'] < max(recent) - 3600000:
            return None
        return checked
    except (ValueError, TypeError, KeyError):
        # A corrupt/stale archive is ignored; the original evidence path stays.
        return None


def evaluate_and_store(fetcher, marker, *, now=None, storage=request):
    """One atomic per-date research snapshot, subject to archived-day dedupe."""
    day=research_day(now)
    if day is None:
        return dict(status="paused", reason="ausserhalb der automatischen Marktzeit")
    previous=storage("read",{})
    if not isinstance(previous,dict) or previous.get("mode")!="RESEARCH_ONLY":
        raise ValueError("Forschungsarchiv nicht bestätigt")
    auto=previous.get("automation") or {}
    old=previous.get("latestReport") or {}
    local=(now or datetime.now(TZ)).astimezone(TZ)
    same_day=(auto.get("lastDay")==day and old.get("version")==strategy_lab.VERSION
              and (old.get("status")=="maintenance" or (old.get("replay") or {}).get("available") is True))
    if same_day and (old.get("status")=="maintenance" or
         (old.get("status")=="evaluated" and
          (local.hour<20 or (old.get("learningCycle") or {}).get("checkpoint")=="evening"))):
        return dict(status="already-stored", day=day)
    if local.weekday() >= 5:
        # Weekends verify durable state only: do not refit models on stale prices.
        report=research_learning.maintenance(old,day)
        report["learningCycle"]["checkpoint"]="weekend"
    else:
        rows=fetcher("1h","3mo")
        closed=marker([dict(row) for row in rows],60)
        # Keep the freshest original source as-is unless a longer independent,
        # fully verified ONE-provider archive is available for research only.
        archived=verified_hourly_research_archive(closed,now=local)
        research_rows=archived if archived is not None else closed
        report=strategy_lab.run(research_rows)
        if report.get("status") not in ("evaluated","insufficient"):
            raise ValueError("Forschungsbericht nicht speicherfähig")
        report=research_learning.enrich(report,research_rows,old,day=day)
        report["learningCycle"]["checkpoint"]="evening" if local.hour>=20 else "morning"
    payload=dict(day=day,report=report)
    if local.weekday()<5:
        import research_replay
        envelope=research_replay.make(research_rows,old,day,report['learningCycle']['checkpoint'],report)
        report['replay']={'available':True,'id':envelope['id']}
        payload['replay']=envelope
    ack=storage("write",payload)
    if not isinstance(ack,dict) or ack.get("saved") is not True or ack.get("day")!=day:
        raise ValueError("Forschungsarchiv hat Speicherung nicht bestätigt")
    return dict(status=report["status"],day=day,closedBars=report["closedBars"],
                folds=len(report["folds"]))


def status():
    with _lock:
        return dict(_state, running=bool(_thread and _thread.is_alive()))


def start(fetcher, marker):
    global _thread
    if not os.environ.get("PUSH_SERVICE_URL") or not os.environ.get("PUSH_SERVICE_TOKEN"):
        with _lock:
            _state.update(enabled=False, phase="unconfigured")
        return False
    with _lock:
        _state["enabled"]=True
        if _thread and _thread.is_alive():
            return True
        _thread=threading.Thread(target=_loop,args=(fetcher,marker),
                                 daemon=True,name="bob-strategy-lab-daily")
        _thread.start()
        return True


def _loop(fetcher,marker):
    next_attempt=0.
    while True:
        day=research_day()
        now=time.monotonic()
        if day is None:
            with _lock:
                _state["phase"]="market-closed"
            time.sleep(POLL_SECONDS)
            continue
        if now<next_attempt:
            time.sleep(min(POLL_SECONDS,next_attempt-now))
            continue
        with _lock:
            _state.update(phase="checking",lastAttemptAt=int(time.time()*1000),error=None)
        try:
            result=evaluate_and_store(fetcher,marker)
            phase=result["status"]
            with _lock:
                _state["phase"]=phase
                _state["lastRunDay"]=result.get("day")
                if phase in ("evaluated","maintenance","already-stored"):
                    _state["lastSuccessAt"]=int(time.time()*1000)
            print("BOB_STRATEGY_DAILY status="+phase+" day="+str(result.get("day")),flush=True)
            next_attempt=time.monotonic()+(3600 if phase in ("evaluated","maintenance","already-stored") else RETRY_SECONDS)
        except Exception as exc:
            with _lock:
                _state.update(phase="retry",error=type(exc).__name__)
            print("BOB_STRATEGY_DAILY error="+type(exc).__name__,flush=True)
            next_attempt=time.monotonic()+RETRY_SECONDS
        time.sleep(POLL_SECONDS)
