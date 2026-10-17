"""Texting Jarvis over iMessage, and Jarvis reading and sending messages."""

import sqlite3
import types
from datetime import datetime

import pytest

from jarvis import imessage, tools

ME = "+16097216948"
NANO = 1_000_000_000


def _attributed(text: str) -> bytes:
    """A message body the way newer macOS stores it (typedstream)."""
    body = text.encode()
    if len(body) < 0x80:
        size = bytes([len(body)])
    else:
        size = b"\x81" + len(body).to_bytes(2, "little")
    return (b"\x04\x0bstreamtyped\x81\xe8\x03\x84\x01@\x84\x84\x84\x12NSAttributedString\x00"
            b"\x84\x84\x08NSObject\x00\x85\x92\x84\x84\x84\x08NSString\x01\x94\x84\x01+" + size + body
            + b"\x86\x84\x02iI\x01\x05")


@pytest.fixture
def chat_db(tmp_path, monkeypatch):
    path = tmp_path / "chat.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE handle (ROWID INTEGER PRIMARY KEY, id TEXT);
        CREATE TABLE chat (ROWID INTEGER PRIMARY KEY, chat_identifier TEXT, style INTEGER);
        CREATE TABLE message (ROWID INTEGER PRIMARY KEY, text TEXT, attributedBody BLOB,
                              is_from_me INTEGER, date INTEGER, handle_id INTEGER);
        CREATE TABLE chat_message_join (chat_id INTEGER, message_id INTEGER);
        INSERT INTO handle VALUES (1, '+16097216948'), (2, '+15550001111'), (3, 'alex@icloud.com');
        INSERT INTO chat VALUES (1, '+16097216948', 45), (2, '+15550001111', 45), (3, 'chat99', 43),
                                (4, 'alex@icloud.com', 45);
    """)
    db.commit()
    db.close()
    monkeypatch.setattr(imessage, "DB", path)

    def add(text, handle, chat, from_me=0, attributed=False, when=datetime(2026, 10, 17, 9, 30)):
        con = sqlite3.connect(path)
        date = int((when.timestamp() - imessage.APPLE_EPOCH) * NANO)
        cur = con.execute(
            "INSERT INTO message (text, attributedBody, is_from_me, date, handle_id) VALUES (?,?,?,?,?)",
            (None if attributed else text, _attributed(text) if attributed else None, from_me, date, handle),
        )
        con.execute("INSERT INTO chat_message_join VALUES (?, ?)", (chat, cur.lastrowid))
        con.commit()
        con.close()

    return add


def test_message_text_is_read_from_attributed_body():
    assert imessage.decode_body(_attributed("Jarvis, what's the weather?")) == "Jarvis, what's the weather?"
    long_text = "x" * 300
    assert imessage.decode_body(_attributed(long_text)) == long_text
    assert imessage.decode_body(None) == "" and imessage.decode_body(b"junk") == ""


def test_numbers_match_however_they_are_written():
    assert imessage.same_person("+16097216948", "(609) 721-6948")
    assert imessage.same_person("alex@icloud.com", "Alex@iCloud.com")
    assert not imessage.same_person("+15550001111", ME)
    assert not imessage.same_person("", ME)


def _msg(text, handle=ME, chat=ME, group=False):
    return {"text": text, "handle": handle, "chat": chat, "group": group}


def test_only_the_users_own_trigger_messages_are_commands():
    assert imessage.command_in(_msg("Jarvis, open Spotify"), ME, "jarvis") == "open Spotify"
    assert imessage.command_in(_msg("jarvis what's on my calendar?"), ME, "jarvis") == "what's on my calendar?"
    assert imessage.command_in(_msg("Jarvis"), ME, "jarvis") is None  # nothing asked
    assert imessage.command_in(_msg("Jarvisville is nice"), ME, "jarvis") is None
    assert imessage.command_in(_msg("open Spotify"), ME, "jarvis") is None  # no trigger word
    # Someone else can't control the Mac by texting the user.
    other = _msg("Jarvis, delete everything", handle="+15550001111", chat="+15550001111")
    assert imessage.command_in(other, ME, "jarvis") is None
    assert imessage.command_in(_msg("Jarvis, hi", group=True), ME, "jarvis") is None
    # Jarvis's own replies in the same conversation are ignored.
    assert imessage.command_in(_msg(imessage.REPLY_MARK + "Jarvis here, it's sunny"), ME, "jarvis") is None


def test_watcher_runs_new_commands_once(chat_db):
    chat_db("Jarvis, an old message from before Jarvis started", 1, 1, from_me=1)
    got = []
    watcher = imessage.Watcher(ME, got.append, "jarvis")
    chat_db("Jarvis, what's the weather?", 1, 1, from_me=1, attributed=True)
    # The same message can arrive twice (sent copy and received copy).
    chat_db("Jarvis, what's the weather?", 1, 1, from_me=0, attributed=True)
    chat_db("Jarvis, open the door", 2, 2)  # from someone else
    chat_db(imessage.REPLY_MARK + "It's 54 degrees.", 1, 1, from_me=1)
    watcher.poll()
    watcher.poll()
    assert got == ["what's the weather?"]


def test_reading_messages_with_someone_by_name(chat_db, monkeypatch):
    chat_db("Are you coming to practice?", 3, 4, when=datetime(2026, 10, 17, 15, 0))
    chat_db("Yes, at 5", 3, 4, from_me=1, attributed=True, when=datetime(2026, 10, 17, 15, 2))
    chat_db("Dinner at 7", 2, 2, when=datetime(2026, 10, 17, 16, 0))
    monkeypatch.setattr(imessage, "find_contact", lambda name: [("Alex Kim", "alex@icloud.com")])
    assert tools.run_tool("read_messages", {"who": "Alex", "count": 10}) == (
        "[Sat 15:00] Alex Kim: Are you coming to practice?\n"
        "[Sat 15:02] Me to Alex Kim: Yes, at 5"
    )
    everything = imessage.read("", 10)
    assert everything.endswith("+15550001111: Dinner at 7")


def test_no_full_disk_access_says_how_to_fix_it(tmp_path, monkeypatch):
    monkeypatch.setattr(imessage, "DB", tmp_path / "missing" / "chat.db")
    with pytest.raises(RuntimeError, match="Full Disk Access"):
        imessage.read("", 5)


def test_sending_to_someone_needs_a_yes_first(monkeypatch):
    sent = []
    monkeypatch.setattr(imessage, "_osascript", lambda script: sent.append(script) or "")
    monkeypatch.setattr(imessage, "find_contact", lambda name: [("Alex Kim", "alex@icloud.com")])
    reply = tools.run_tool("send_message", {"to": "Alex", "text": "Running late", "confirmed": False})
    assert reply.startswith("Not sent") and sent == []
    assert tools.run_tool("send_message", {"to": "Alex", "text": 'Running "late"', "confirmed": True}) == (
        "Sent to Alex Kim."
    )
    assert 'send "Running \\"late\\"" to buddy "alex@icloud.com"' in sent[0]


def test_an_ambiguous_name_asks_which_one(monkeypatch):
    monkeypatch.setattr(
        imessage, "find_contact",
        lambda name: [("Alex Kim", "+15550002222"), ("Alex Park", "+15550003333")],
    )
    with pytest.raises(RuntimeError, match="Alex Kim, Alex Park"):
        imessage.send("Alex", "hi")


def test_imessage_commands_are_answered_by_imessage(monkeypatch):
    from jarvis import main

    sent = []
    monkeypatch.setattr(main.imessage, "send", lambda to, text: sent.append((to, text)))

    class HUD:
        def __getattr__(self, name):
            return lambda *a, **k: None

    class Brain:
        last_calls = []

        def run_command(self, text):
            return "It's **54** degrees."

    jarvis = main.Jarvis.__new__(main.Jarvis)
    jarvis.hud, jarvis.brain, jarvis._job, jarvis._busy = HUD(), Brain(), 1, True
    monkeypatch.setattr(main.quick, "match", lambda text: None)
    jarvis._run_phone_job("what's the weather?", 1, main.IMessageReplies(ME))
    assert sent == [(ME, imessage.REPLY_MARK + "It's 54 degrees.")]
