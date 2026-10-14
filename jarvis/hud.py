"""What Jarvis shows on screen while it listens, thinks and replies.

On a Mac this is the notch panel in notch.py. Everywhere else, or with
JARVIS_NOTCH=0, it's the terminal plus desktop notifications.
"""

import os
from collections.abc import Callable

from . import desktop
from .config import config

MODE_LABELS = {"dictate": "Dictate", "ask": "Ask", "command": "Command"}


def reply_seconds(text: str) -> float:
    """How long a reply stays on screen: long enough to read, within reason."""
    return max(4.0, min(15.0, len(text.split()) * 0.35))


class ConsoleHUD:
    """Same methods as NotchHUD; every method is safe to call from any thread."""

    def run(self, main: Callable[[], None]) -> None:
        main()

    def set_level_source(self, level: Callable[[], float]) -> None:
        pass

    def listening(self, mode: str) -> None:
        print(f"Listening ({MODE_LABELS[mode]})...")

    def thinking(self, heard: str) -> None:
        print(f"You said: {heard}" if heard else "Thinking...")

    def reply(self, text: str, heard: str = "") -> None:
        desktop.notify("Jarvis", text)

    def flash(self, text: str) -> None:
        print(text)

    def error(self, text: str) -> None:
        desktop.notify("Jarvis hit a problem", text)

    def hide(self, after: float = 0.0) -> None:
        pass


def make_hud():
    if config.is_mac and os.environ.get("JARVIS_NOTCH", "1") == "1":
        try:
            from .notch import NotchHUD

            return NotchHUD()
        except ImportError as error:
            print(f"Notch panel unavailable ({error}); using the terminal instead.")
    return ConsoleHUD()
