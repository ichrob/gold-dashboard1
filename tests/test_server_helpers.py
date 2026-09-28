import ast
import pathlib
import time
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
source = (ROOT / "server.py").read_text(encoding="utf-8")
tree = ast.parse(source)

wanted = {"normalize_biquote_bars", "mark_bar_state", "aggregate_bars", "iso_age_seconds"}
nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in wanted]
namespace = {"time": time, "datetime": datetime, "timezone": timezone}
exec(compile(ast.Module(body=nodes, type_ignores=[]), "server.py", "exec"), namespace)


def test_normalize_biquote_bars():
    fn = namespace["normalize_biquote_bars"]
    rows = fn({"bars": [
        {"openTime": 1000, "open": "10", "high": "12", "low": "9", "close": "11", "isOpen": False},
        {"openTime": 500, "open":  "8", "high": "9",  "low": "7", "close": "8",  "isOpen": True},
        {"openTime": 0, "open": "bad", "high": "1", "low": "1", "close": "1"},
    ]})
    assert [x["openTime"] for x in rows] == [500, 1000]
    assert rows[0]["close"] == 8.0
    assert rows[1]["high"] == 12.0


def test_aggregate_bars_builds_ohlc_without_inventing_values():
    fn = namespace["aggregate_bars"]
    rows = [
        {"openTime": 0, "open": 100, "high": 103, "low": 99, "close": 101},
        {"openTime": 60_000, "open": 101, "high": 105, "low": 100, "close": 104},
        {"openTime": 120_000, "open": 104, "high": 106, "low": 102, "close": 103},
    ]
    out = fn(rows, 2)
    assert len(out) == 2
    assert out[0]["open"] == 100.0
    assert out[0]["high"] == 105.0
    assert out[0]["low"] == 99.0
    assert out[0]["close"] == 104.0
    assert out[1]["open"] == 104.0
    assert out[1]["high"] == 106.0
    assert out[1]["low"] == 102.0
    assert out[1]["close"] == 103.0


def test_mark_bar_state_marks_only_current_window_open():
    fn = namespace["mark_bar_state"]
    now_ms = int(time.time() * 1000)
    rows = [
        {"openTime": now_ms - 10 * 60_000},
        {"openTime": now_ms - 1 * 60_000},
    ]
    out = fn(rows, 5)
    assert out[0]["isOpen"] is False
    assert out[1]["isOpen"] is True


def test_iso_age_seconds_is_non_negative():
    fn = namespace["iso_age_seconds"]
    age = fn("2000-01-01T00:00:00Z")
    assert age is not None and age >= 0
