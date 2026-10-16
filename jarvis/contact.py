"""Letting Jarvis text and call you.

On a Mac this uses your own Messages and FaceTime, signed into your Apple
ID: a text arrives from you, and a call is a FaceTime audio call placed
from your Mac to your number (so it rings your phone). Jarvis doesn't get
its own number this way. For a real separate number that can SMS and call,
set up Twilio (see the README) and Jarvis uses that instead. For free
alerts with no phone number at all, set NTFY_TOPIC and install the ntfy app;
that takes priority over both.

Set your number in the app settings, or JARVIS_MY_NUMBER in .env.
"""

import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request

from . import prefs
from .config import config


def my_number() -> str:
    return str(prefs.get("my_number", config.my_number) or "").strip()


def configured() -> bool:
    # ntfy needs no number. A Mac can text/call through your own Apple ID;
    # otherwise Twilio is needed.
    if ntfy_configured():
        return True
    return bool(my_number()) and (config.is_mac or twilio_configured())


def ntfy_configured() -> bool:
    return bool(config.ntfy_topic)


def twilio_configured() -> bool:
    return bool(config.twilio_sid and config.twilio_token and config.twilio_from)


def _twilio_missing() -> list[str]:
    """The Twilio settings still missing, if Twilio is partly set up."""
    settings = {
        "TWILIO_SID": config.twilio_sid,
        "TWILIO_TOKEN": config.twilio_token,
        "TWILIO_FROM": config.twilio_from,
    }
    if not any(settings.values()):
        return []
    return [name for name, value in settings.items() if not value]


def _check_twilio() -> bool:
    """True to use Twilio. Refuses to quietly fall back to iMessage when
    Twilio is only half set up, since that hides what's wrong."""
    if twilio_configured():
        return True
    missing = _twilio_missing()
    if missing:
        raise RuntimeError(
            f"Twilio is only partly set up: {', '.join(missing)} missing from ~/.jarvis/.env."
        )
    return False


def e164(number: str) -> str:
    """A phone number in the +15551234567 form Twilio needs. Ten digits
    without a country code are taken as a US number."""
    digits = "".join(ch for ch in number if ch.isdigit())
    if number.strip().startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits


def _applescript(script: str) -> None:
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        message = result.stderr.strip()
        if "-1743" in message or "not authori" in message.lower():
            raise RuntimeError(
                "macOS hasn't allowed Jarvis to use Messages yet. In System Settings > "
                "Privacy & Security > Automation, turn on Messages under Terminal (or "
                "under Jarvis, if you use the app), then try again."
            )
        raise RuntimeError(message or "Messages failed")


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def text_me(message: str) -> str:
    """Sends you a text."""
    if ntfy_configured():
        return _ntfy(message, urgent=False)
    number = my_number()
    if not number:
        raise RuntimeError("No number set. Add your number in Jarvis's settings.")
    if _check_twilio():
        return _twilio_text(e164(number), message)
    if not config.is_mac:
        raise RuntimeError("Texting needs a Mac (Messages) or Twilio set up.")
    script = (
        'tell application "Messages"\n'
        "    set svc to 1st service whose service type = iMessage\n"
        f"    send {_quote(message)} to buddy {_quote(number)} of svc\n"
        "end tell\n"
    )
    _applescript(script)
    return "Texted you."


def call_me(reason: str = "") -> str:
    """Calls you: a FaceTime audio call on a Mac, or a Twilio call otherwise.
    With ntfy it's an urgent alert instead, since ntfy can't ring."""
    if ntfy_configured():
        return _ntfy(reason or "Jarvis needs you.", urgent=True)
    number = my_number()
    if not number:
        raise RuntimeError("No number set. Add your number in Jarvis's settings.")
    if _check_twilio():
        return _twilio_call(e164(number), reason)
    if not config.is_mac:
        raise RuntimeError("Calling needs a Mac (FaceTime) or Twilio set up.")
    # The facetime-audio URL opens FaceTime and places the call.
    subprocess.run(["open", f"facetime-audio://{number}"], check=True)
    return "Calling you on FaceTime."


# ---- ntfy (free phone notifications, optional) -------------------------------


# The last alert sent, so a reply from the phone hours later still has
# something to answer.
last_alert = ""

# The iPhone Shortcut that sends messages back to Jarvis (see remote.py).
REPLY_SHORTCUT = "Tell Jarvis"


def _ntfy(message: str, urgent: bool) -> str:
    global last_alert
    from . import remote

    url = f"{config.ntfy_server.rstrip('/')}/{config.ntfy_topic}"
    headers = {
        "Title": "Jarvis needs you" if urgent else "Jarvis",
        # 5 is ntfy's top priority: a long buzz, and on Android it can sound
        # through Do Not Disturb if you allow it in the app.
        "Priority": "5" if urgent else "3",
        "Tags": "rotating_light" if urgent else "speech_balloon",
    }
    if remote.configured():
        # A button on the alert that opens the Shortcut for replying.
        name = urllib.parse.quote(REPLY_SHORTCUT)
        headers["Actions"] = f"view, Reply, shortcuts://run-shortcut?name={name}"
    if config.ntfy_token:
        headers["Authorization"] = f"Bearer {config.ntfy_token}"
    request = urllib.request.Request(url, data=message.encode("utf-8"), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=20):
            pass
    except urllib.error.HTTPError as error:
        if error.code in (401, 403):
            raise RuntimeError(
                "ntfy refused the message. That topic is protected; set NTFY_TOKEN, "
                "or pick a different NTFY_TOPIC."
            ) from None
        raise RuntimeError(f"ntfy said: HTTP {error.code}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"Couldn't reach ntfy ({error.reason}). Is the Mac online?") from None
    last_alert = message
    return "Sent an urgent alert to your phone." if urgent else "Sent it to your phone."


def send_file(path, message: str) -> str:
    """Sends a file to the phone through ntfy, with a short message. The
    ntfy app shows it as an attachment you can open."""
    global last_alert
    if not ntfy_configured():
        raise RuntimeError("Sending files to the phone needs ntfy (NTFY_TOPIC) set up.")
    from pathlib import Path

    path = Path(path)
    query = urllib.parse.urlencode({"filename": path.name, "message": message, "title": "Jarvis"})
    url = f"{config.ntfy_server.rstrip('/')}/{config.ntfy_topic}?{query}"
    headers = {"Tags": "page_facing_up"}
    if config.ntfy_token:
        headers["Authorization"] = f"Bearer {config.ntfy_token}"
    request = urllib.request.Request(url, data=path.read_bytes(), headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(request, timeout=60):
            pass
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"ntfy wouldn't take the file: HTTP {error.code}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"Couldn't reach ntfy ({error.reason}). Is the Mac online?") from None
    last_alert = message
    return "Sent it to your phone."


# ---- Twilio (a real separate number, optional) ------------------------------


def _twilio_request(path: str, fields: dict) -> dict:
    import base64
    import urllib.parse

    url = f"https://api.twilio.com/2010-04-01/Accounts/{config.twilio_sid}/{path}"
    data = urllib.parse.urlencode(fields).encode()
    auth = base64.b64encode(f"{config.twilio_sid}:{config.twilio_token}".encode()).decode()
    request = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth}"})
    try:
        with urllib.request.urlopen(request, timeout=20) as reply:
            return json.loads(reply.read() or b"{}")
    except urllib.error.HTTPError as error:
        raise RuntimeError(_twilio_problem(error)) from None


# Plain-English help for the Twilio errors people hit while setting up.
TWILIO_HINTS = {
    20003: "Twilio rejected the Account SID or Auth Token. Copy both again from the "
    "Twilio Console home page into ~/.jarvis/.env.",
    21211: "Twilio says your number isn't a valid phone number. Check it in Jarvis's settings.",
    21606: "TWILIO_FROM isn't a number on your Twilio account that can send texts.",
    21608: "A Twilio trial account can only text and call verified numbers. Verify your "
    "number in the Twilio Console under Phone Numbers > Verified Caller IDs.",
    21659: "TWILIO_FROM isn't a number on your Twilio account.",
    572006: "Twilio trial accounts can only send Twilio's ready-made sample texts, not "
    "your own words. Upgrade the Twilio account (add a payment method) to send real texts.",
}


def _twilio_problem(error) -> str:
    try:
        body = json.loads(error.read() or b"{}")
    except ValueError:
        body = {}
    code = body.get("code")
    if code in TWILIO_HINTS:
        return TWILIO_HINTS[code]
    message = body.get("message") or f"HTTP {error.code}"
    return f"Twilio said: {message}" + (f" (error {code})" if code else "")


def _twilio_text(number: str, message: str) -> str:
    _twilio_request("Messages.json", {"To": number, "From": e164(config.twilio_from), "Body": message})
    return "Texted you."


def _twilio_call(number: str, reason: str) -> str:
    from xml.sax.saxutils import escape

    # Twilio reads this aloud when you pick up. Twilio can't play Jarvis's
    # own Kokoro voice, so it uses Brian, the closest British man's voice.
    words = escape(reason or "Hello, this is Jarvis calling.")
    twiml = f'<Response><Say voice="Polly.Brian">{words}</Say></Response>'
    _twilio_request(
        "Calls.json",
        {"To": number, "From": e164(config.twilio_from), "Twiml": twiml},
    )
    return "Calling you now."
