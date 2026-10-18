"""First-run setup for the downloadable app: pick an AI provider, paste a
key, and Jarvis saves it to ~/.jarvis/.env and restarts itself.
"""

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
