"""Push event classification and anti-spam for Bob.

The module is deliberately dependency-free so CI and the free deployment path
can use it without adding a paid notification service or a runtime package.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import time


@dataclass
class PushEvent:
    kind: str
    title: str
    body: str
    key: str


class PushEngine:
    """Turn signal/trade transitions into deduplicated push events."""

    def __init__(self, cooldown_seconds: int = 900):
        self.cooldown_seconds = max(0, int(cooldown_seconds))
        self._last_sent: dict[str, float] = {}
        self._last_signal = "NEUTRAL"
        self._last_stop = None

    def _allow(self, key: str, now: float) -> bool:
        previous = self._last_sent.get(key)
        if previous is not None and now - previous < self.cooldown_seconds:
            return False
        self._last_sent[key] = now
        return True

    def signal_transition(self, direction: str, score: float, mtf: str, *, now: float | None = None) -> PushEvent | None:
        direction = str(direction or "NEUTRAL").upper()
        mtf = str(mtf or "NEUTRAL").upper()
        if direction not in {"LONG", "SHORT", "NEUTRAL"}:
            direction = "NEUTRAL"
        current = self._last_signal
        self._last_signal = direction
        if direction == current or direction == "NEUTRAL":
            return None
        key = f"entry:{direction}"
        stamp = time() if now is None else float(now)
        if not self._allow(key, stamp):
            return None
        label = "LONG" if direction == "LONG" else "SHORT"
        return PushEvent(
            "entry",
            f"Bob – {label}-Signal",
            f"Bestätigtes {label}-Setup · Score {float(score):.0f}/100 · MTF {mtf}.",
            key,
        )

    def stop_update(self, direction: str, old_stop: float | None, new_stop: float | None, *, now: float | None = None) -> PushEvent | None:
        if old_stop is None or new_stop is None or float(old_stop) == float(new_stop):
            return None
        direction = str(direction or "NEUTRAL").upper()
        stamp = time() if now is None else float(now)
        key = f"stop:{direction}:{round(float(new_stop), 2):.2f}"
        if not self._allow(key, stamp):
            return None
        return PushEvent(
            "stop",
            "Bob – Stop-Loss anpassen",
            f"{direction}: Stop-Loss von {float(old_stop):.2f} auf {float(new_stop):.2f} anpassen.",
            key,
        )

    def trade_exit(self, direction: str, reason: str, *, now: float | None = None) -> PushEvent | None:
        stamp = time() if now is None else float(now)
        key = f"exit:{str(direction).upper()}:{reason}"
        if not self._allow(key, stamp):
            return None
        return PushEvent(
            "exit",
            "Bob – Trade schließen",
            f"{str(direction).upper()}: Trade-Management beendet. Grund: {reason}.",
            key,
        )

    def risk_alert(self, direction: str, price: float, stop: float, *, now: float | None = None) -> PushEvent | None:
        direction = str(direction or "NEUTRAL").upper()
        if direction not in {"LONG", "SHORT"}:
            return None
        distance = abs(float(price) - float(stop))
        stamp = time() if now is None else float(now)
        key = f"risk:{direction}"
        if not self._allow(key, stamp):
            return None
        return PushEvent(
            "risk",
            "Bob – Risikoalarm",
            f"{direction}: Kurs nähert sich dem Stop-Loss. Abstand {distance:.2f} USD/oz.",
            key,
        )
