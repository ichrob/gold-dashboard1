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
        raw=response.read(262145)
    if len(raw)>262144:
        raise ValueError("Forschungsarchiv-Antwort zu gross")
    parsed=json.loads(raw)
    if not isinstance(parsed,dict):
        raise ValueError("Forschungsarchiv-Antwort ungültig")
    return parsed


def evaluate_and_store(fetcher, marker, *, now=None, storage=request):
    """One atomic per-date research snapshot, subject to archived-day dedupe."""
    day=trading_day(now)
    if day is None:
        return dict(status="paused", reason="ausserhalb der automatischen Marktzeit")
    previous=storage("read",{})
    if not isinstance(previous,dict) or previous.get("mode")!="RESEARCH_ONLY":
        raise ValueError("Forschungsarchiv nicht bestätigt")
    auto=previous.get("automation") or {}
    old=previous.get("latestReport") or {}
    if auto.get("lastDay")==day and old.get("status")=="evaluated" and old.get("version")==strategy_lab.VERSION:
        return dict(status="already-stored", day=day)
    rows=fetcher("1h","3mo")
    closed=marker([dict(row) for row in rows],60)
    report=strategy_lab.run(closed)
    if report.get("status") not in ("evaluated","insufficient"):
        raise ValueError("Forschungsbericht nicht speicherfähig")
    ack=storage("write",dict(day=day,report=report))
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
        day=trading_day()
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
                if phase in ("evaluated","already-stored"):
                    _state["lastSuccessAt"]=int(time.time()*1000)
            print("BOB_STRATEGY_DAILY status="+phase+" day="+str(result.get("day")),flush=True)
            next_attempt=time.monotonic()+(3600 if phase in ("evaluated","already-stored") else RETRY_SECONDS)
        except Exception as exc:
            with _lock:
                _state.update(phase="retry",error=type(exc).__name__)
            print("BOB_STRATEGY_DAILY error="+type(exc).__name__,flush=True)
            next_attempt=time.monotonic()+RETRY_SECONDS
        time.sleep(POLL_SECONDS)
