"""iMessage: text Jarvis from your phone, and let Jarvis read and send your
messages.

The Messages app keeps every message in ~/Library/Messages/chat.db. Jarvis
reads that (it needs Full Disk Access for Terminal, or for Jarvis if you
use the app) and sends through Messages with AppleScript.

Texting Jarvis: send yourself a message that starts with "Jarvis" (the
trigger word, JARVIS_IMESSAGE_TRIGGER). Only messages in your conversation
with your own number count, so nobody else can control your Mac by texting
you. Jarvis runs it like a spoken command and texts you the answer.
"""

import re
import sqlite3
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import config

DB = Path.home() / "Library" / "Messages" / "chat.db"
# Messages counts time from the start of 2001.
APPLE_EPOCH = 978307200
# Replies start with this, so Jarvis never mistakes its own replies (which
# land in the same conversation with yourself) for new commands.
REPLY_MARK = "🤖 "

FULL_DISK_ACCESS = (
    "Jarvis can't read your messages yet. In System Settings > Privacy & Security > "
    "Full Disk Access, turn on Terminal (or Jarvis, if you use the app), then quit and "
    "reopen it."
)


def _digits(text: str) -> str:
    return "".join(c for c in text if c.isdigit())


def same_person(handle: str, number: str) -> bool:
    """Whether a Messages handle (a phone number or email) is this number or
    address. Compares the last 10 digits so +1 and spacing don't matter."""
    handle, number = (handle or "").strip().lower(), (number or "").strip().lower()
    if not handle or not number:
        return False
    if "@" in handle or "@" in number:
        return handle == number
    a, b = _digits(handle), _digits(number)
    return len(a) >= 7 and len(b) >= 7 and a[-10:] == b[-10:]


def decode_body(blob: bytes | None) -> str:
    """The text of a message stored only in its attributedBody (as newer
    macOS does): a serialized NSAttributedString whose NSString holds it."""
    if not blob:
        return ""
    start = blob.find(b"NSString")
    if start < 0:
        return ""
    data = blob[start + len(b"NSString") + 5:]
    if not data:
        return ""
    length, offset = data[0], 1
    if length == 0x81:
        length, offset = int.from_bytes(data[1:3], "little"), 3
    elif length == 0x82:
        length, offset = int.from_bytes(data[1:4], "little"), 4
    elif length == 0x83:
        length, offset = int.from_bytes(data[1:5], "little"), 5
    return data[offset: offset + length].decode("utf-8", errors="replace")


def _connect():
    try:
        return sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=5)
    except sqlite3.OperationalError:
        raise RuntimeError(FULL_DISK_ACCESS) from None


QUERY = """
SELECT m.ROWID, m.text, m.attributedBody, m.is_from_me, m.date,
       COALESCE(h.id, ''), COALESCE(c.chat_identifier, ''), COALESCE(c.style, 45)
FROM message m
LEFT JOIN handle h ON m.handle_id = h.ROWID
LEFT JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
LEFT JOIN chat c ON c.ROWID = cmj.chat_id
"""


def _rows(sql: str, params=()) -> list[dict]:
    try:
        with _connect() as db:
            rows = db.execute(sql, params).fetchall()
    except sqlite3.OperationalError as error:
        if "unable to open" in str(error) or "authorization" in str(error).lower():
            raise RuntimeError(FULL_DISK_ACCESS) from None
        raise
    messages = []
    for rowid, text, body, from_me, date, handle, chat, style in rows:
        text = text or decode_body(body)
        seconds = date / 1e9 if date and date > 1e11 else (date or 0)
        messages.append({
            "id": rowid, "text": (text or "").strip(), "from_me": bool(from_me),
            "when": datetime.fromtimestamp(APPLE_EPOCH + seconds),
            "handle": handle or chat, "chat": chat, "group": style == 43,
        })
    return messages


def latest_id() -> int:
    with _connect() as db:
        return db.execute("SELECT COALESCE(MAX(ROWID), 0) FROM message").fetchone()[0]


# ---- contacts -------------------------------------------------------------------


def _osascript(script: str) -> str:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        message = result.stderr.strip()
        if "-1743" in message or "not authori" in message.lower():
            raise RuntimeError(
                "macOS hasn't let Jarvis use Contacts or Messages yet. In System Settings > "
                "Privacy & Security > Automation, turn them on under Terminal (or Jarvis)."
            )
        raise RuntimeError(message or "Messages didn't respond.")
    return result.stdout.strip()


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def find_contact(name: str) -> list[tuple[str, str]]:
    """(name, phone or email) for people in Contacts whose name contains
    `name`."""
    script = (
        'tell application "Contacts"\n'
        "    set found to {}\n"
        f"    repeat with p in (every person whose name contains {_quote(name)})\n"
        "        repeat with v in (value of phones of p) & (value of emails of p)\n"
        '            set end of found to (name of p) & "\\t" & v\n'
        "        end repeat\n"
        "    end repeat\n"
        "    set AppleScript's text item delimiters to linefeed\n"
        "    return found as text\n"
        "end tell"
    )
    pairs = []
    for line in _osascript(script).splitlines():
        person, _, address = line.partition("\t")
        if address.strip():
            pairs.append((person.strip(), address.strip()))
    return pairs


def _looks_like_address(text: str) -> bool:
    return "@" in text or len(_digits(text)) >= 7


# ---- what the tools call ------------------------------------------------------------


def read(who: str = "", count: int = 15) -> str:
    """Recent messages, all conversations or with one person (a name from
    Contacts, a number or an email)."""
    count = max(1, min(int(count or 15), 50))
    label = {}
    if who.strip() and not _looks_like_address(who):
        people = find_contact(who.strip())
        if not people:
            return f"I couldn't find {who} in your contacts."
        addresses = [address for _, address in people]
        label = {address: person for person, address in people}
    elif who.strip():
        addresses = [who.strip()]
    else:
        addresses = []
    rows = _rows(QUERY + " ORDER BY m.ROWID DESC LIMIT ?", (2000 if addresses else count * 3,))
    picked = []
    for row in rows:
        if not row["text"]:
            continue
        if addresses and not any(same_person(row["handle"], a) for a in addresses):
            continue
        picked.append(row)
        if len(picked) >= count:
            break
    if not picked:
        return "No messages found."
    lines = []
    for row in reversed(picked):
        name = next((label[a] for a in label if same_person(row["handle"], a)), row["handle"])
        where = " (group)" if row["group"] else ""
        sender = "Me" if row["from_me"] else name
        to = f" to {name}" if row["from_me"] else ""
        lines.append(f"[{row['when']:%a %H:%M}] {sender}{to}{where}: {row['text']}")
    return "\n".join(lines)


def send(to: str, text: str) -> str:
    """Sends an iMessage to a number, an email, or a name in Contacts."""
    to = to.strip()
    if _looks_like_address(to):
        address, person = to, to
    else:
        people = find_contact(to)
        if not people:
            raise RuntimeError(f"I couldn't find {to} in your contacts.")
        names = sorted({person for person, _ in people})
        if len(names) > 1:
            raise RuntimeError(f"More than one contact matches: {', '.join(names)}. Which one?")
        person, address = people[0]
    _osascript(
        'tell application "Messages"\n'
        "    set svc to 1st service whose service type = iMessage\n"
        f"    send {_quote(text)} to buddy {_quote(address)} of svc\n"
        "end tell"
    )
    return f"Sent to {person}."


def send_file(to: str, path) -> None:
    _osascript(
        'tell application "Messages"\n'
        "    set svc to 1st service whose service type = iMessage\n"
        f"    send (POSIX file {_quote(str(path))}) to buddy {_quote(to)} of svc\n"
        "end tell"
    )


# ---- texting Jarvis ---------------------------------------------------------------------


def command_in(message: dict, me: str, trigger: str) -> str | None:
    """The command in a message, if it's one for Jarvis: in the user's
    conversation with themselves, starting with the trigger word."""
    if message["group"] or not message["text"]:
        return None
    if not (same_person(message["handle"], me) or same_person(message["chat"], me)):
        return None
    text = message["text"]
    if text.startswith(REPLY_MARK.strip()):
        return None  # one of Jarvis's own replies
    match = re.match(rf"\s*{re.escape(trigger)}\b[\s,.:!-]*(.*)", text, re.IGNORECASE | re.DOTALL)
    if not match or not match.group(1).strip():
        return None
    return match.group(1).strip()


class Watcher:
    """Checks for new messages every couple of seconds and hands commands
    for Jarvis to on_command(text)."""

    def __init__(self, me: str, on_command, trigger: str = "jarvis", log=print, sleep=time.sleep):
        self.me, self.on_command, self.trigger, self.log, self.sleep = me, on_command, trigger, log, sleep
        self.last_id = latest_id()  # only messages sent from now on
        self._recent: list[tuple[str, float]] = []  # to skip the copy of a message synced twice

    def poll(self) -> None:
        for message in _rows(QUERY + " WHERE m.ROWID > ? ORDER BY m.ROWID", (self.last_id,)):
            self.last_id = max(self.last_id, message["id"])
            command = command_in(message, self.me, self.trigger)
            if command is None:
                continue
            now = time.monotonic()
            self._recent = [(t, at) for t, at in self._recent if now - at < 30]
            if any(t == command for t, _ in self._recent):
                continue
            self._recent.append((command, now))
            self.on_command(command)

    def run(self, stop: threading.Event | None = None) -> None:
        while not (stop and stop.is_set()):
            try:
                self.poll()
            except Exception as error:
                self.log(f"iMessage: {error}")
                self.sleep(30)
            self.sleep(2)


def start(me: str, on_command, trigger: str, log=print) -> Watcher:
    watcher = Watcher(me, on_command, trigger, log)
    threading.Thread(target=watcher.run, daemon=True).start()
    return watcher


def configured() -> bool:
    return config.is_mac and config.imessage_commands and DB.exists()
