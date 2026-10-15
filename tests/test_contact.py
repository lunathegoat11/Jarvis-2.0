import pytest

from jarvis import contact
from jarvis.config import Config


def mac(**kw):
    return Config(is_mac=True, **kw)


def test_quote_escapes_for_applescript():
    assert contact._quote('say "hi" \\ bye') == '"say \\"hi\\" \\\\ bye"'


def test_text_me_sends_imessage_on_a_mac(monkeypatch):
    monkeypatch.setattr(contact, "config", mac())
    monkeypatch.setattr(contact.prefs, "get", lambda k, d=None: "+15551234567" if k == "my_number" else d)
    scripts = []
    monkeypatch.setattr(contact, "_applescript", lambda s: scripts.append(s))
    assert contact.text_me("Running late") == "Texted you."
    assert "iMessage" in scripts[0] and "+15551234567" in scripts[0] and "Running late" in scripts[0]


def test_call_me_uses_facetime_on_a_mac(monkeypatch):
    monkeypatch.setattr(contact, "config", mac())
    monkeypatch.setattr(contact.prefs, "get", lambda k, d=None: "5551234567" if k == "my_number" else d)
    ran = []
    monkeypatch.setattr(contact.subprocess, "run", lambda cmd, **kw: ran.append(cmd))
    assert contact.call_me("") == "Calling you on FaceTime."
    assert ran[0] == ["open", "facetime-audio://5551234567"]


def test_no_number_is_refused(monkeypatch):
    monkeypatch.setattr(contact, "config", mac())
    monkeypatch.setattr(contact.prefs, "get", lambda k, d=None: "")
    with pytest.raises(RuntimeError, match="No number set"):
        contact.text_me("hi")


def test_twilio_is_preferred_when_set_up(monkeypatch):
    cfg = Config(is_mac=True, twilio_sid="AC1", twilio_token="t", twilio_from="+1999")
    monkeypatch.setattr(contact, "config", cfg)
    monkeypatch.setattr(contact.prefs, "get", lambda k, d=None: "+15551234567" if k == "my_number" else d)
    calls = []
    monkeypatch.setattr(contact, "_twilio_request", lambda path, fields: calls.append((path, fields)) or {})
    assert contact.text_me("hey") == "Texted you."
    assert calls[0][0] == "Messages.json"
    assert calls[0][1]["To"] == "+15551234567" and calls[0][1]["Body"] == "hey"
    assert contact.call_me("wake up") == "Calling you now."
    assert "wake up" in calls[1][1]["Twiml"]
