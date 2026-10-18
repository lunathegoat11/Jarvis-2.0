"""First-run setup for the downloadable app: pick an AI provider, paste a
key, and Jarvis saves it to ~/.jarvis/.env and restarts itself.
"""

import re
import shlex
import subprocess
from pathlib import Path

from . import config as settings

# What each provider needs from the person setting it up.
PROVIDER_KEYS = {
    "nvidia": "NVIDIA_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "ollama": None,  # runs on this computer, no key
}


def write_settings(provider: str, key: str = "", model: str = "", path: Path | None = None) -> Path:
    """Updates the app's .env file, keeping any other lines already in it."""
    if provider not in PROVIDER_KEYS:
        raise ValueError(f"Unknown provider: {provider}")
    key, model = key.strip(), model.strip()
    key_name = PROVIDER_KEYS[provider]
    if key_name and not key:
        raise ValueError("Paste your API key first.")
    if provider == "ollama" and not model:
        raise ValueError("Type the model name exactly as `ollama list` shows it.")

    updates = {"JARVIS_PROVIDER": provider}
    if key_name:
        updates[key_name] = key
    updates["JARVIS_MODEL"] = model  # empty means the provider's default

    return save_settings(updates, path)


def save_settings(updates: dict, path: Path | None = None) -> Path:
    """Sets these settings in the .env file (an empty value removes one),
    keeping any other lines already in it."""
    path = path or settings.USER_ENV
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text().splitlines() if path.exists() else []
    kept = [line for line in lines if line.split("=", 1)[0].strip() not in updates]
    kept += [f"{name}={value}" for name, value in updates.items() if value]
    path.write_text("\n".join(kept) + "\n")
    path.chmod(0o600)  # the file holds an API key
    return path


def relaunch() -> None:
    """Starts a fresh copy of the app (so it reads the new settings) and quits."""
    from AppKit import NSApplication, NSBundle

    if settings.IS_APP:
        bundle = str(NSBundle.mainBundle().bundlePath())
        # The 2s delay lets this copy fully exit first; quitting releases the
        # single-instance lock (the OS frees it when the process dies), and the
        # fresh copy's acquire retries long enough to pick it up. Don't release
        # the lock earlier than exit, or the two could briefly overlap.
        subprocess.Popen(["/bin/sh", "-c", f"sleep 2; open -n {shlex.quote(bundle)}"])
    else:
        print("Settings saved. Start Jarvis again with: python -m jarvis")
    NSApplication.sharedApplication().terminate_(None)


def run_setup_window(problem: str) -> None:
    """Shows the setup screen in the Jarvis window until the person saves."""
    from AppKit import NSApplication, NSApplicationActivationPolicyRegular
    from PyObjCTools import AppHelper

    from .app import JarvisApp

    from .notch import _name_the_app

    _name_the_app()
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)
    window = JarvisApp({"provider": "", "model": "", "vision_model": "", "setup": problem})
    window.show()
    AppHelper.runEventLoop(installInterrupt=True)


# ---- the rest of the settings, from the app's Settings screen -----------------
#
# Phone alerts, messages from the phone, iMessage, the weather and briefing,
# and other Macs: everything that used to mean editing .env in Terminal. They
# take effect when Jarvis restarts. API keys aren't here; the setup screen
# handles those.

APP_SETTINGS = {
    "NTFY_TOPIC": lambda: settings.config.ntfy_topic,
    "NTFY_REPLY_TOPIC": lambda: settings.config.ntfy_reply_topic,
    "JARVIS_PHONE_REPLIES": lambda: settings.config.phone_replies,
    "JARVIS_IMESSAGE": lambda: "1" if settings.config.imessage_commands else "0",
    "JARVIS_LOCATION": lambda: settings.config.location,
    "JARVIS_BRIEFING_TIME": lambda: settings.config.briefing_time,
    "JARVIS_MAC_NAME": lambda: settings.config.mac_name,
    "NTFY_MACS_TOPIC": lambda: settings.config.ntfy_macs_topic,
}
# Changes saved since Jarvis started, so the screen shows them before a restart.
_changed: dict[str, str] = {}


def app_settings() -> dict:
    return {key: _changed.get(key, read()) for key, read in APP_SETTINGS.items()}


def _check(key: str, value: str) -> str:
    from . import macs

    value = " ".join(str(value).split())  # one line, so it can't add others to .env
    if not value:
        return ""
    if key == "JARVIS_PHONE_REPLIES" and value not in ("imessage", ""):
        raise ValueError("Phone replies are either by iMessage or by notification.")
    if key == "JARVIS_IMESSAGE" and value not in ("0", "1"):
        raise ValueError("iMessage commands are either on or off.")
    if key == "JARVIS_BRIEFING_TIME" and not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", value):
        raise ValueError("Give the briefing time like 07:30.")
    if key == "JARVIS_MAC_NAME":
        value = macs.name_of(value)
        if not value:
            raise ValueError('Give this Mac a short name, like "main" or "old".')
    if key in ("NTFY_TOPIC", "NTFY_REPLY_TOPIC", "NTFY_MACS_TOPIC"):
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,64}", value):
            raise ValueError("That isn't a valid code. Copy it again.")
        others = {k: v for k, v in app_settings().items() if k.endswith("TOPIC") and k != key}
        if value in others.values():
            raise ValueError("Each of these needs its own code.")
    return value


def set_app_setting(key: str, value: str, path: Path | None = None) -> dict:
    """Saves one setting from the Settings screen and returns them all."""
    if key not in APP_SETTINGS:
        raise ValueError(f"The app can't change {key}.")
    value = _check(key, value)
    save_settings({key: value}, path)
    _changed[key] = value
    return app_settings()


def new_code(key: str, path: Path | None = None) -> dict:
    """Makes a long random private topic for phone alerts, messages from the
    phone, or the Macs, keeping one that's already set."""
    import secrets

    from . import macs

    if app_settings().get(key):
        return app_settings()
    prefix = {"NTFY_TOPIC": "jarvis-alerts-", "NTFY_REPLY_TOPIC": "jarvis-tell-",
              "NTFY_MACS_TOPIC": macs.TOPIC_PREFIX}[key]
    return set_app_setting(key, prefix + secrets.token_urlsafe(18), path)
