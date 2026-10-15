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


def test_half_set_up_twilio_says_what_is_missing(monkeypatch):
    # Without this, Jarvis quietly used iMessage instead and hit a Messages
    # permission error that had nothing to do with Twilio.
    monkeypatch.setattr(contact, "config", Config(is_mac=True, twilio_from="+17372324091"))
    monkeypatch.setattr(contact.prefs, "get", lambda k, d=None: "+15551234567" if k == "my_number" else d)
    with pytest.raises(RuntimeError, match="TWILIO_SID, TWILIO_TOKEN"):
        contact.text_me("hi")


def test_numbers_are_put_in_the_form_twilio_needs():
    assert contact.e164("(609) 721-6948") == "+16097216948"
    assert contact.e164("1 609 721 6948") == "+16097216948"
    assert contact.e164("+44 7700 900123") == "+447700900123"


def test_twilio_errors_are_explained(monkeypatch):
    import io
    import urllib.error

    cfg = Config(is_mac=True, twilio_sid="AC1", twilio_token="t", twilio_from="+1999")
    monkeypatch.setattr(contact, "config", cfg)
    monkeypatch.setattr(contact.prefs, "get", lambda k, d=None: "+15551234567" if k == "my_number" else d)

    def refuse(request, timeout):
        body = io.BytesIO(b'{"code": 21608, "message": "unverified"}')
        raise urllib.error.HTTPError(request.full_url, 400, "Bad Request", {}, body)

    monkeypatch.setattr(contact.urllib.request, "urlopen", refuse)
    with pytest.raises(RuntimeError, match="verified numbers"):
        contact.text_me("hi")


def test_call_text_is_escaped_for_twiml(monkeypatch):
    cfg = Config(is_mac=True, twilio_sid="AC1", twilio_token="t", twilio_from="+1999")
    monkeypatch.setattr(contact, "config", cfg)
    monkeypatch.setattr(contact.prefs, "get", lambda k, d=None: "+15551234567" if k == "my_number" else d)
    sent = []
    monkeypatch.setattr(contact, "_twilio_request", lambda path, fields: sent.append(fields) or {})
    contact.call_me("Rent & bills <due>")
    assert "Rent &amp; bills &lt;due&gt;" in sent[0]["Twiml"]


def test_twilio_accepts_its_own_setting_names(monkeypatch):
    import importlib

    from jarvis import config as config_module

    monkeypatch.setenv("TWILIO_ACCOUNT_SID", ' "AC123" ')
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "secret")
    monkeypatch.setenv("TWILIO_PHONE_NUMBER", "+17372324091")
    try:
        reloaded = importlib.reload(config_module)
        assert reloaded.config.twilio_sid == "AC123"
        assert reloaded.config.twilio_token == "secret"
        assert reloaded.config.twilio_from == "+17372324091"
    finally:
        for name in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER"):
            monkeypatch.delenv(name, raising=False)
        importlib.reload(config_module)


def _ntfy_config(**kw):
    return Config(is_mac=True, ntfy_topic="jarvis-abc123", ntfy_server="https://ntfy.sh", **kw)


def test_ntfy_sends_without_a_phone_number(monkeypatch):
    # ntfy wins over Twilio, so a Twilio trial account can't get in the way.
    cfg = _ntfy_config(twilio_sid="AC1", twilio_token="t", twilio_from="+1999")
    monkeypatch.setattr(contact, "config", cfg)
    monkeypatch.setattr(contact.prefs, "get", lambda k, d=None: "")
    sent = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(request, timeout):
        sent.append(request)
        return Reply()

    monkeypatch.setattr(contact.urllib.request, "urlopen", fake_urlopen)
    assert contact.configured()
    assert contact.text_me("Meeting moved to 3") == "Sent it to your phone."
    assert sent[0].full_url == "https://ntfy.sh/jarvis-abc123"
    assert sent[0].data == b"Meeting moved to 3"
    assert sent[0].get_header("Priority") == "3"
    assert contact.call_me("Your flight is boarding") == "Sent an urgent alert to your phone."
    assert sent[1].get_header("Priority") == "5"
    assert sent[1].data == b"Your flight is boarding"


def test_ntfy_protected_topic_is_explained(monkeypatch):
    import io
    import urllib.error

    monkeypatch.setattr(contact, "config", _ntfy_config())

    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, io.BytesIO(b""))

    monkeypatch.setattr(contact.urllib.request, "urlopen", refuse)
    with pytest.raises(RuntimeError, match="NTFY_TOKEN"):
        contact.text_me("hi")
