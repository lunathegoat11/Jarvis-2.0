import json
import threading

from jarvis import contact, main, remote
from jarvis.config import Config


class Stream:
    def __init__(self, events):
        self.lines = [json.dumps(e).encode() + b"\n" for e in events]

    def __enter__(self):
        return iter(self.lines)

    def __exit__(self, *exc):
        return False


def test_only_messages_are_run_once_each_across_reconnects(monkeypatch):
    monkeypatch.setattr(remote, "config", Config(ntfy_reply_topic="reply-xyz", ntfy_topic="alerts"))
    streams = [
        Stream([{"event": "open"}, {"event": "message", "id": "a1", "message": "open spotify"}]),
        OSError("connection reset"),
        # After reconnecting, ntfy can resend the last message; it must not run twice.
        Stream([
            {"event": "keepalive"},
            {"event": "message", "id": "a1", "message": "open spotify"},
            {"event": "message", "id": "a2", "message": "  "},
            {"event": "message", "id": "a3", "message": "lock the screen"},
        ]),
    ]
    urls = []
    got = []
    stop = threading.Event()

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        item = streams.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def on_message(text):
        got.append(text)
        if text == "lock the screen":
            stop.set()

    monkeypatch.setattr(remote.urllib.request, "urlopen", fake_urlopen)
    remote._listen_loop(on_message, log=lambda m: None, stop=stop, sleep=lambda s: None)
    assert got == ["open spotify", "lock the screen"]
    assert urls[0].startswith("https://ntfy.sh/reply-xyz/json?since=")
    # Picks up after the last message seen rather than from the start.
    assert urls[-1].endswith("since=a1")


def test_reply_topic_must_differ_from_the_alerts_topic(monkeypatch):
    monkeypatch.setattr(remote, "config", Config(ntfy_reply_topic="same", ntfy_topic="same"))
    assert not remote.configured()
    monkeypatch.setattr(remote, "config", Config(ntfy_reply_topic="reply", ntfy_topic="alerts"))
    assert remote.configured()


class FakeHUD:
    def __getattr__(self, name):
        return lambda *a, **k: None


class FakeBrain:
    def __init__(self):
        self.commands = []

    def run_command(self, text):
        self.commands.append(text)
        return "Done, **Spotify** is open."


def test_phone_message_runs_as_a_command_and_answers_the_phone(monkeypatch):
    jarvis = main.Jarvis.__new__(main.Jarvis)
    jarvis.hud, jarvis.brain, jarvis._job, jarvis._busy = FakeHUD(), FakeBrain(), 3, True
    sent = []
    monkeypatch.setattr(main.quick, "match", lambda text: None)
    monkeypatch.setattr(main.contact, "text_me", lambda message: sent.append(message))
    monkeypatch.setattr(contact, "last_alert", "Your 3pm meeting moved to 4.")
    jarvis._run_phone_job("ok, tell them I'll be there", 3)
    command = jarvis.brain.commands[0]
    assert "phone" in command and "Your 3pm meeting moved to 4." in command
    assert command.endswith("ok, tell them I'll be there")
    assert sent == ["Done, Spotify is open."]
    assert jarvis._busy is False


def test_a_failed_phone_message_reports_back(monkeypatch):
    jarvis = main.Jarvis.__new__(main.Jarvis)
    jarvis.hud, jarvis._job, jarvis._busy = FakeHUD(), 1, True

    class Broken:
        def run_command(self, text):
            raise RuntimeError("NVIDIA is down")

    jarvis.brain = Broken()
    sent = []
    monkeypatch.setattr(main.quick, "match", lambda text: None)
    monkeypatch.setattr(main.contact, "text_me", lambda message: sent.append(message))
    jarvis._run_phone_job("check my email", 1)
    assert sent == ["That didn't work: NVIDIA is down"]


def test_alerts_get_a_reply_button_when_replies_are_on(monkeypatch):
    cfg = Config(ntfy_topic="alerts", ntfy_reply_topic="reply")
    monkeypatch.setattr(contact, "config", cfg)
    monkeypatch.setattr(remote, "config", cfg)
    sent = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(contact.urllib.request, "urlopen", lambda r, timeout: sent.append(r) or Reply())
    contact.text_me("hello")
    assert sent[0].get_header("Actions") == "view, Reply, shortcuts://run-shortcut?name=Tell%20Jarvis"
    assert contact.last_alert == "hello"
