"""Settings for Jarvis, read from environment variables or a .env file."""

import os
import platform
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(os.environ.get("JARVIS_DATA_DIR", Path.home() / ".jarvis"))


@dataclass(frozen=True)
class Config:
    model: str = os.environ.get("JARVIS_MODEL", "claude-opus-5-5")
    whisper_model: str = os.environ.get("JARVIS_WHISPER_MODEL", "base.en")
    speak_replies: bool = os.environ.get("JARVIS_SPEAK", "1") == "1"
    sample_rate: int = 16000

    # Hotkeys use pynput's GlobalHotKeys syntax. Press once to start
    # listening, press again to stop.
    dictate_hotkey: str = os.environ.get("JARVIS_DICTATE_KEY", "<ctrl>+<alt>+d")
    ask_hotkey: str = os.environ.get("JARVIS_ASK_KEY", "<ctrl>+<alt>+a")
    command_hotkey: str = os.environ.get("JARVIS_COMMAND_KEY", "<ctrl>+<alt>+j")

    data_dir: Path = DATA_DIR
    is_mac: bool = platform.system() == "Darwin"
    is_windows: bool = platform.system() == "Windows"


config = Config()
