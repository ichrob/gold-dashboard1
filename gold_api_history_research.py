"""Manual, free-tier-only Gold-API historical research, isolated from live Bob.

Only /history (daily averages) and /ohlc (one whole-range summary) are
permitted. Both share the account's 10/hour limit; a private SQLite journal
reserves at most 8/hour for this one exclusive operator. No cron/worker,
live trade/DEGIRO feed, product quote or paid-plan fallback imports it.
"""
import argparse
import hashlib
import json
import math
import os
import sqlite3
import stat
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from urllib.error import HTTPError, URLError

BASE = "https://api.gold-api.com"
MAX_LOCAL_HOURLY = 8
MAX_BYTES = 131072
CREATE_SQL = """
CREATE TABLE IF NOT EXISTS request_ledger (
    attempt_at INTEGER NOT NULL, purpose TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS historical_originals (
    digest TEXT PRIMARY KEY,
    requested_at INTEGER NOT NULL,
    mode TEXT NOT NULL,
    start_ts INTEGER NOT NULL,
    end_ts INTEGER NOT NULL,
    raw_json TEXT NOT NULL,
    source TEXT NOT NULL,
    research_only INTEGER NOT NULL CHECK(research_only=1)
);
"""

class NoRedirect(__import__("urllib.request", fromlist=["HTTPRedirectHandler"]).HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("redirect-denied")

def _utc(ts):
    if type(ts) is not int or ts < 946684800 or ts > 4102444800:
        raise ValueError("Invalid UTC Unix timestamp")
    return datetime.fromtimestamp(ts, timezone.utc)

def build_request(mode, start, end, now=None):
    now = int(datetime.now(timezone.utc).timestamp()) if now is None else now
    _utc(start)
    _utc(end)
    if type(now) is not int or not start < end <= now-60:
        raise ValueError("Historical interval is not closed")
    if mode == "history-day":
        if start % 86400 or end % 86400 or end-start > 62*86400:
            raise ValueError("Daily research must use <=62 whole UTC days")
        params = urlencode({"symbol":"XAU","startTimestamp":start,
                            "endTimestamp":end,"groupBy":"day",
                            "aggregation":"avg","orderBy":"asc"})
        return BASE+"/history?"+params
    if mode == "ohlc-range":
        if end-start < 3600 or end-start > 31*86400:
            raise ValueError("OHLC research window must be 1h to 31d")
        params = urlencode({"startTimestamp":start,"endTimestamp":end})
        return BASE+"/ohlc/XAU?"+params
    raise ValueError("Unsupported or premium research scope")

def _positive(value):
    if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
        raise ValueError("Invalid historical OHLC/price")
    return float(value)

def validate(mode, data, start, end):
    """No claim of closed 1m/5m bars or source-clock precision beyond provider."""
    if mode == "history-day":
        if not isinstance(data, list) or not 0 < len(data) <= 64:
            raise ValueError("No valid daily history")
        dates = []
        for row in data:
            if not isinstance(row, dict) or set(row) != {"day", "avg_price"}:
                raise ValueError("Unexpected history schema")
            day = row["day"]
            if not isinstance(day, str):
                raise ValueError("Missing UTC day")
            try:
                parsed = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError as exc:
                raise ValueError("Invalid UTC day") from exc
            at = int(parsed.timestamp())
            if not start <= at < end or (dates and at <= dates[-1]):
                raise ValueError("Outside window or non-monotonic/duplicate date")
            _positive(row["avg_price"])
            dates.append(at)
        return len(dates)
    if mode == "ohlc-range":
        if not isinstance(data, dict):
            raise ValueError("Missing range summary")
        required = {"open","high","low","close","startTimestamp","endTimestamp"}
        if not required <= set(data):
            raise ValueError("Incomplete range summary")
        op, hi, lo, cl = (_positive(data[k]) for k in ("open","high","low","close"))
        if lo > min(op,cl) or hi < max(op,cl):
            raise ValueError("Invalid OHLC bounds")
        if type(data["startTimestamp"]) is not int or type(data["endTimestamp"]) is not int:
            raise ValueError("Missing original query window")
        if data["startTimestamp"] != start or data["endTimestamp"] != end:
            raise ValueError("Window mismatch")
        return 1
    raise ValueError("Unsupported response")

def reserve(db, mode, now):
    """SQLite BEGIN IMMEDIATE is a single-process-host lock, NOT multi-host quota."""
    db.execute("BEGIN IMMEDIATE")
    try:
        count = db.execute(
            "SELECT COUNT(*) FROM request_ledger WHERE attempt_at>?",
            (now-3600,)).fetchone()[0]
        if count >= MAX_LOCAL_HOURLY:
            db.rollback()
            return False
        db.execute("INSERT INTO request_ledger VALUES (?,?)",(now,mode))
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise

def request_json(url, key):
    if not url.startswith(BASE+"/history?") and not url.startswith(BASE+"/ohlc/XAU?"):
        raise ValueError("Unexpected endpoint")
    if not isinstance(key,str) or not key or len(key)>512:
        raise ValueError("Key not configured")
    req = Request(url, headers={"x-api-key":key, "Accept":"application/json",
                                "User-Agent":"BobResearchFree/1"})
    try:
        with build_opener(NoRedirect()).open(req, timeout=8) as response:
            raw=response.read(MAX_BYTES+1)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        # Never surface response body, API-key, URL with params, or private errors.
        raise ValueError("Provider request unavailable") from None
    if len(raw)>MAX_BYTES:
        raise ValueError("Provider response too large")
    try:
        return json.loads(raw)
    except (ValueError,UnicodeDecodeError):
        raise ValueError("Invalid provider JSON") from None

def record(db,mode,start,end,now,payload):
    count=validate(mode,payload,start,end)
    raw=json.dumps(payload,sort_keys=True,separators=(",",":"),ensure_ascii=True)
    digest=hashlib.sha256(
        (mode+":"+str(start)+":"+str(end)+":"+raw).encode()).hexdigest()
    with db:
        db.execute("""INSERT OR IGNORE INTO historical_originals
           (digest,requested_at,mode,start_ts,end_ts,raw_json,source,research_only)
           VALUES (?,?,?,?,?,?,?,1)""",
           (digest,now,mode,start,end,raw,"Gold-API.com XAU/USD research"))
    return {"status":"stored-research-only","rows":count,"digestPrefix":digest[:10],
            "usableAsLiveBar":False,"usableAsExecutableQuote":False}

def run(db,mode,start,end,*,environ=None,requester=request_json,now=None):
    env=os.environ if environ is None else environ
    if env.get("BOB_GOLD_API_FREE_HISTORY_ENABLED")!="1":
        return {"status":"disabled"}
    if env.get("BOB_GOLD_API_EXCLUSIVE_ACCOUNT_CONFIRMED")!="1":
        return {"status":"account-coordination-unconfirmed"}
    key=env.get("GOLD_API_KEY","")
    if not isinstance(key,str) or not key:
        return {"status":"api-key-not-configured"}
    now=int(datetime.now(timezone.utc).timestamp()) if now is None else now
    url=build_request(mode,start,end,now)
    if not reserve(db,mode,now):
        return {"status":"hourly-reserve-exhausted"}
    try:
        payload=requester(url,key)
        return record(db,mode,start,end,now,payload)
    except (ValueError,TypeError,sqlite3.Error):
        # Reservation is consumed on an uncertain request, never silently retried.
        return {"status":"provider-or-validation-failed"}

def private_archive(path):
    path=Path(path).expanduser()
    if not path.is_absolute() or any(str(path).startswith(p) for p in
                                      ("/tmp/","/var/tmp/","/mnt/data/","/workspace/")):
        raise ValueError("Durable private archive path required")
    if not path.parent.is_dir():
        raise ValueError("Archive directory not available")
    if path.is_symlink():
        raise ValueError("No archive symlinks")
    if not path.exists():
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        os.close(fd)
    info=path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError("Archive must be private 0600")
    db=sqlite3.connect(path,timeout=8)
    db.executescript(CREATE_SQL)
    return db

def main():
    p=argparse.ArgumentParser(description="Manual XAU historical research only")
    p.add_argument("--mode",choices=("history-day","ohlc-range"),required=True)
    p.add_argument("--start",type=int,required=True,help="UTC Unix seconds")
    p.add_argument("--end",type=int,required=True,help="UTC Unix seconds, exclusive")
    p.add_argument("--archive",required=True,help="Private persistent SQLite file")
    args=p.parse_args()
    try:
        with private_archive(args.archive) as db:
            result=run(db,args.mode,args.start,args.end)
        print(json.dumps(result,sort_keys=True))
    except (ValueError,sqlite3.Error,OSError):
        print('{"status":"not-ready-or-invalid-input"}')

if __name__ == "__main__":
    main()
