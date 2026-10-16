"""Learning your habits from what you ask Jarvis.

Every command is noted in ~/.jarvis/activity.jsonl (on this computer only):
when you asked, what you said, and what Jarvis did. Something you ask for at
about the same time of day on at least three different days counts as a
habit, and around that time Jarvis offers to do it for you. "Stop suggesting
the weather" turns one off.

Requests are grouped by what Jarvis did rather than the exact words, so
"what's the weather" and "do I need a coat" both count as checking the
weather.
"""

import json
import threading
from datetime import datetime, timedelta
from statistics import median
from urllib.parse import urlparse

from .config import config

# A habit needs this many different days, within this many recent days, at
# times no further apart than this.
MIN_DAYS = 3
LOOKBACK_DAYS = 21
MAX_SPREAD_MINUTES = 90
# Offer from a little before the usual time until a while after.
OFFER_BEFORE = timedelta(minutes=5)
OFFER_AFTER = timedelta(minutes=30)
# Keep the log from growing forever.
KEEP_ENTRIES = 3000

# The input that tells two uses of a tool apart ("open Spotify" vs "open Notes").
KEY_ARG = {
    "open_app": "name", "search_web": "site", "media_control": "action", "get_news": "topic",
    "control_device": "device", "smart_home": "command", "tv_open_app": "app",
    "check_calendar": None, "check_email": None, "get_weather": None,
}

_lock = threading.Lock()


def _log_path():
    return config.data_dir / "activity.jsonl"


def _state_path():
    return config.data_dir / "habits.json"


def signature(calls: list[tuple[str, dict]], text: str) -> str:
    """What a request did, as a short key: its first tool and the input
    that matters, or its words if it used no tools."""
    for name, args in calls:
        if name in ("remember", "forget", "learn_lesson", "save_skill", "add_to_dictionary",
                    "stop_suggesting", "list_timers"):
            continue  # bookkeeping, not the request itself
        args = args or {}
        if name in ("open_url", "browse_open", "new_tab"):
            host = urlparse(args.get("url", "") if "://" in args.get("url", "")
                            else "https://" + args.get("url", "")).hostname or ""
            return f"{name}:{host.removeprefix('www.')}"
        key = KEY_ARG.get(name)
        value = str(args.get(key, "")).strip().lower() if key else ""
        return f"{name}:{value}" if value else name
    return "say:" + " ".join("".join(c for c in text.lower() if c.isalnum() or c.isspace()).split())


def record(text: str, calls: list[tuple[str, dict]], when: datetime | None = None) -> None:
    """Notes a finished request."""
    when = when or datetime.now()
    entry = {"at": when.isoformat(timespec="minutes"), "said": text, "did": signature(calls, text)}
    with _lock:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        path = _log_path()
        with path.open("a") as log:
            log.write(json.dumps(entry) + "\n")
        try:
            lines = path.read_text().splitlines()
        except OSError:
            return
        if len(lines) > KEEP_ENTRIES * 1.5:
            path.write_text("\n".join(lines[-KEEP_ENTRIES:]) + "\n")


def _entries() -> list[dict]:
    try:
        lines = _log_path().read_text().splitlines()
    except OSError:
        return []
    entries = []
    for line in lines:
        try:
            entry = json.loads(line)
            entry["at"] = datetime.fromisoformat(entry["at"])
            entries.append(entry)
        except (ValueError, KeyError, TypeError):
            continue
    return entries


def _state() -> dict:
    try:
        return json.loads(_state_path().read_text())
    except (OSError, ValueError):
        return {}


def _save_state(state: dict) -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    _state_path().write_text(json.dumps(state, indent=2))


def find(now: datetime | None = None) -> list[dict]:
    """The habits in the recent log, earliest in the day first. Each has
    the usual time ("08:05"), what was done, and the latest words used."""
    now = now or datetime.now()
    since = now - timedelta(days=LOOKBACK_DAYS)
    ignored = set(_state().get("ignored", []))
    groups: dict[str, list[dict]] = {}
    for entry in _entries():
        if entry["at"] >= since and entry["did"] not in ignored:
            groups.setdefault(entry["did"], []).append(entry)

    habits = []
    for did, entries in groups.items():
        # The first time it happened each day.
        firsts: dict = {}
        for entry in entries:
            day = entry["at"].date()
            if day not in firsts or entry["at"] < firsts[day]["at"]:
                firsts[day] = entry
        if len(firsts) < MIN_DAYS:
            continue
        minutes = sorted(e["at"].hour * 60 + e["at"].minute for e in firsts.values())
        # Use the tightest run of MIN_DAYS or more days, so one odd day
        # doesn't hide a real habit.
        best = None
        for i in range(len(minutes)):
            for j in range(i + MIN_DAYS - 1, len(minutes)):
                if minutes[j] - minutes[i] <= MAX_SPREAD_MINUTES:
                    if best is None or j - i > best[1] - best[0]:
                        best = (i, j)
        if best is None:
            continue
        usual = int(median(minutes[best[0]: best[1] + 1]))
        latest = max(entries, key=lambda e: e["at"])
        habits.append({
            "did": did,
            "time": f"{usual // 60:02d}:{usual % 60:02d}",
            "minutes": usual,
            "days": best[1] - best[0] + 1,
            "said": latest["said"],
        })
    return sorted(habits, key=lambda h: h["minutes"])


def due_suggestion(now: datetime | None = None) -> dict | None:
    """A habit to offer now: it's around the usual time, it hasn't been
    done or offered today. Marks it offered."""
    now = now or datetime.now()
    today = now.date()
    done_today = {e["did"] for e in _entries() if e["at"].date() == today}
    with _lock:
        state = _state()
        offered = state.get("offered", {})
        for habit in find(now):
            usual = datetime.combine(today, datetime.min.time()) + timedelta(minutes=habit["minutes"])
            if not (usual - OFFER_BEFORE <= now <= usual + OFFER_AFTER):
                continue
            if habit["did"] in done_today or offered.get(habit["did"]) == today.isoformat():
                continue
            offered[habit["did"]] = today.isoformat()
            state["offered"] = offered
            _save_state(state)
            return habit
    return None


def stop_suggesting(about: str) -> str:
    """Stops offering habits whose words or action contain `about`."""
    about = about.strip().lower()
    if not about:
        raise ValueError("Say which habit.")
    matches = [h for h in find() if about in h["said"].lower() or about in h["did"].lower()]
    if not matches:
        return "I haven't noticed a habit like that."
    with _lock:
        state = _state()
        ignored = set(state.get("ignored", []))
        ignored.update(h["did"] for h in matches)
        state["ignored"] = sorted(ignored)
        _save_state(state)
    return "OK, I won't suggest that any more."


def prompt_section() -> str:
    habits = find()
    if not habits:
        return ""
    lines = "\n".join(
        f"- Around {h['time']}: \"{h['said']}\" (on {h['days']} days recently)" for h in habits
    )
    return f"\n\nHabits you've noticed in what the user asks you:\n{lines}"


YES = {"yes", "yeah", "yep", "yup", "sure", "ok", "okay", "do it", "go ahead", "please",
       "yes please", "sure thing", "go for it", "yes do it", "sounds good"}


def is_yes(text: str) -> bool:
    words = " ".join("".join(c for c in text.lower() if c.isalpha() or c.isspace()).split())
    return words in YES
