"""Timers and reminders that Jarvis says out loud when they're due, plus the
daily briefing at a set time.

They're saved in ~/.jarvis/timers.json, so a reminder survives Jarvis being
restarted; one that came due while Jarvis was off is announced when it next
starts. These are Jarvis's own, separate from the Reminders app.
"""

import json
import threading
import time
import uuid
from datetime import datetime, timedelta

from .config import config

# A briefing missed because the Mac was asleep still runs if Jarvis is back
# within this long; later than that it waits for tomorrow.
BRIEFING_GRACE = timedelta(hours=3)


def _describe_duration(seconds: int) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minutes:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
    if seconds and not hours:
        parts.append(f"{seconds} second" + ("s" if seconds != 1 else ""))
    return " ".join(parts) or "0 seconds"


class Scheduler:
    def __init__(self, announce, briefing=None, path=None, clock=time.time, now=datetime.now,
                 every_minute=None):
        self.announce = announce  # called with the words to say
        self.briefing = briefing  # called with no arguments at briefing time
        self.every_minute = every_minute  # e.g. offering habits
        self._last_minute = 0.0
        self.path = path or config.data_dir / "timers.json"
        self.clock = clock
        self.now = now
        self._lock = threading.Lock()
        self._alerts = self._load()
        self._stop = threading.Event()

    # ---- saved alerts -----------------------------------------------------

    def _load(self) -> list[dict]:
        try:
            saved = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return []
        return [a for a in saved.get("alerts", []) if {"id", "due", "message"} <= a.keys()]

    def _state(self) -> dict:
        try:
            return json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, **extra) -> None:
        state = self._state()
        state.update(extra, alerts=self._alerts)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state, indent=2))

    # ---- what the tools call ------------------------------------------------

    def add_timer(self, seconds: float, label: str = "") -> str:
        seconds = int(round(seconds))
        if seconds <= 0:
            raise ValueError("A timer needs a length longer than zero.")
        length = _describe_duration(seconds)
        label = label.strip()
        name = f" for {label}" if label else ""
        message = f"Time's up for {label}." if label else f"Time's up. That was {length}."
        self._add(self.clock() + seconds, message, "timer")
        return f"Timer set for {length}{name}."

    def add_reminder(self, when: str, message: str) -> str:
        try:
            due = datetime.strptime(when.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            raise ValueError("Give the time as 'YYYY-MM-DD HH:MM'.") from None
        if due <= self.now():
            raise ValueError("That time has already passed.")
        self._add(due.timestamp(), f"Reminder: {message.strip()}", "reminder")
        return f"I'll remind you {due.strftime('%A at %H:%M')}."

    def _add(self, due: float, message: str, kind: str) -> None:
        with self._lock:
            self._alerts.append(
                {"id": uuid.uuid4().hex[:6], "due": due, "message": message, "kind": kind}
            )
            self._alerts.sort(key=lambda a: a["due"])
            self._save()

    def pending(self) -> str:
        with self._lock:
            alerts = list(self._alerts)
        if not alerts:
            return "No timers or reminders set."
        lines = []
        for alert in alerts:
            left = alert["due"] - self.clock()
            when = datetime.fromtimestamp(alert["due"]).strftime("%a %d %b %H:%M")
            in_words = _describe_duration(max(0, left)) if left < 6 * 3600 else when
            lines.append(f"[{alert['id']}] {alert['message']} (due {when}, in {in_words})")
        return "\n".join(lines)

    def cancel(self, which: str) -> str:
        which = which.strip().lower()
        with self._lock:
            if which in ("all", "everything"):
                gone = len(self._alerts)
                self._alerts = []
            else:
                kept = [
                    a for a in self._alerts
                    if a["id"] != which and (not which or which not in a["message"].lower())
                ]
                gone = len(self._alerts) - len(kept)
                self._alerts = kept
            if gone:
                self._save()
        if not gone:
            return "I couldn't find that timer or reminder."
        return "Cancelled." if gone == 1 else f"Cancelled {gone}."

    # ---- running ----------------------------------------------------------

    def check(self) -> None:
        """Announces whatever is due, and starts the briefing if it's time."""
        now = self.clock()
        with self._lock:
            due = [a for a in self._alerts if a["due"] <= now]
            if due:
                self._alerts = [a for a in self._alerts if a["due"] > now]
                self._save()
        for alert in due:
            message = alert["message"]
            if now - alert["due"] > 120:  # came due while Jarvis was off
                late = datetime.fromtimestamp(alert["due"]).strftime("%H:%M")
                message += f" (This was due at {late}.)"
            self.announce(message)
        self._maybe_brief()
        if self.every_minute and now - self._last_minute >= 60:
            self._last_minute = now
            self.every_minute()

    def _maybe_brief(self) -> None:
        if not (self.briefing and config.briefing_time):
            return
        try:
            hour, minute = (int(p) for p in config.briefing_time.split(":"))
        except ValueError:
            return
        now = self.now()
        start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if not (start <= now <= start + BRIEFING_GRACE):
            return
        today = now.date().isoformat()
        with self._lock:
            if self._state().get("briefed_on") == today:
                return
            self._save(briefed_on=today)
        self.briefing()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self) -> None:
        while not self._stop.wait(1.0):
            try:
                self.check()
            except Exception as error:
                print(f"Timers: {error}", flush=True)

    def stop(self) -> None:
        self._stop.set()


# The one Jarvis uses, set up by main.py. Tools reach it through get().
_scheduler: Scheduler | None = None


def start(announce, briefing=None, every_minute=None) -> Scheduler:
    global _scheduler
    _scheduler = Scheduler(announce, briefing, every_minute=every_minute)
    _scheduler.start()
    return _scheduler


def get() -> Scheduler:
    if _scheduler is None:
        raise RuntimeError("Timers aren't running.")
    return _scheduler
