"""Calendar and Reminders through the Mac's own apps.

Uses AppleScript, so any account you've added to Calendar (iCloud, Google,
Exchange) works without a separate login. macOS asks once for permission
to let Terminal control Calendar and Reminders.
"""

import subprocess
from datetime import datetime

from .config import config


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _run(script: str, timeout: int = 30) -> str:
    if not config.is_mac:
        raise RuntimeError("Calendar and Reminders only work on a Mac.")
    result = subprocess.run(
        ["osascript", "-e", script], capture_output=True, text=True, timeout=timeout
    )
    if result.returncode != 0:
        message = result.stderr.strip()
        if "-1743" in message or "Not authorized" in message:
            raise RuntimeError(
                "macOS hasn't allowed Jarvis to use that app yet. In System Settings → "
                "Privacy & Security → Automation, let Terminal control Calendar and Reminders."
            )
        raise RuntimeError(message or "AppleScript failed")
    return result.stdout.strip()


def parse_when(text: str) -> datetime:
    """Accepts 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DDTHH:MM' (seconds optional)."""
    return datetime.fromisoformat(text.strip().replace(" ", "T"))


def _date_script(name: str, when: datetime) -> str:
    """AppleScript that builds a date without depending on the Mac's locale."""
    return (
        f"set {name} to current date\n"
        f"set day of {name} to 1\n"
        f"set year of {name} to {when.year}\n"
        f"set month of {name} to {when.month}\n"
        f"set day of {name} to {when.day}\n"
        f"set hours of {name} to {when.hour}\n"
        f"set minutes of {name} to {when.minute}\n"
        f"set seconds of {name} to 0\n"
    )


def upcoming_events(days: int = 1) -> str:
    days = max(1, min(14, days))
    script = f"""
set startD to current date
set hours of startD to 0
set minutes of startD to 0
set seconds of startD to 0
set endD to startD + ({days} * days)
set out to ""
tell application "Calendar"
    repeat with c in calendars
        set evs to (every event of c whose start date ≥ startD and start date < endD)
        repeat with e in evs
            set out to out & (summary of e) & " | " & ((start date of e) as string) & " | " & (name of c) & linefeed
        end repeat
    end repeat
end tell
return out
"""
    listing = _run(script, timeout=60)
    if not listing:
        return "Nothing on the calendar." if days == 1 else f"Nothing in the next {days} days."
    return listing


def add_event(title: str, start: str, duration_minutes: int) -> str:
    when = parse_when(start)
    calendar = (
        f"calendar {_quote(config.calendar_name)}" if config.calendar_name
        else "first calendar whose writable is true"
    )
    script = (
        _date_script("startD", when)
        + f"set endD to startD + ({max(5, duration_minutes)} * minutes)\n"
        + 'tell application "Calendar"\n'
        + f"    set target to {calendar}\n"
        + f"    make new event at end of events of target with properties "
        + f"{{summary:{_quote(title)}, start date:startD, end date:endD}}\n"
        + "    return name of target\n"
        + "end tell\n"
    )
    name = _run(script)
    return f"Added \"{title}\" on {when:%A %-d %B at %-I:%M %p} to the {name} calendar."


def add_reminder(title: str, due: str = "") -> str:
    props = f"name:{_quote(title)}"
    prefix = ""
    if due.strip():
        prefix = _date_script("dueD", parse_when(due))
        props += ", due date:dueD"
    script = prefix + f'tell application "Reminders" to make new reminder with properties {{{props}}}\n'
    _run(script)
    return f"Reminder added: {title}."
