"""Letting Jarvis text and call you.

On a Mac this uses your own Messages and FaceTime, signed into your Apple
ID: a text arrives from you, and a call is a FaceTime audio call placed
from your Mac to your number (so it rings your phone). Jarvis doesn't get
its own number this way. For a real separate number that can SMS and call,
set up Twilio (see the README) and Jarvis uses that instead.

Set your number in the app settings, or JARVIS_MY_NUMBER in .env.
"""

import json
import subprocess
import urllib.request

from . import prefs
from .config import config


def my_number() -> str:
    return str(prefs.get("my_number", config.my_number) or "").strip()


def configured() -> bool:
    # A Mac can text/call through your own Apple ID; otherwise Twilio is needed.
    return bool(my_number()) and (config.is_mac or twilio_configured())


def twilio_configured() -> bool:
    return bool(config.twilio_sid and config.twilio_token and config.twilio_from)


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
    number = my_number()
    if not number:
        raise RuntimeError("No number set. Add your number in Jarvis's settings.")
    if twilio_configured():
        return _twilio_text(number, message)
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
    """Calls you: a FaceTime audio call on a Mac, or a Twilio call otherwise."""
    number = my_number()
    if not number:
        raise RuntimeError("No number set. Add your number in Jarvis's settings.")
    if twilio_configured():
        return _twilio_call(number, reason)
    if not config.is_mac:
        raise RuntimeError("Calling needs a Mac (FaceTime) or Twilio set up.")
    # The facetime-audio URL opens FaceTime and places the call.
    subprocess.run(["open", f"facetime-audio://{number}"], check=True)
    return "Calling you on FaceTime."


# ---- Twilio (a real separate number, optional) ------------------------------


def _twilio_request(path: str, fields: dict) -> dict:
    import base64
    import urllib.parse

    url = f"https://api.twilio.com/2010-04-01/Accounts/{config.twilio_sid}/{path}"
    data = urllib.parse.urlencode(fields).encode()
    auth = base64.b64encode(f"{config.twilio_sid}:{config.twilio_token}".encode()).decode()
    request = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(request, timeout=20) as reply:
        return json.loads(reply.read() or b"{}")


def _twilio_text(number: str, message: str) -> str:
    _twilio_request("Messages.json", {"To": number, "From": config.twilio_from, "Body": message})
    return "Texted you."


def _twilio_call(number: str, reason: str) -> str:
    # Twilio reads this TwiML aloud when you pick up.
    words = reason or "Hello, this is Jarvis calling."
    twiml = f"<Response><Say>{words}</Say></Response>"
    _twilio_request(
        "Calls.json",
        {"To": number, "From": config.twilio_from, "Twiml": twiml},
    )
    return "Calling you now."
