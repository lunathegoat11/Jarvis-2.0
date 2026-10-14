"""Settings for Jarvis, read from environment variables or a .env file."""

import os
import platform
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# The .env file next to the jarvis folder, wherever Jarvis is started from.
ENV_FILE = Path(os.environ.get("JARVIS_ENV_FILE", Path(__file__).resolve().parent.parent / ".env"))
load_dotenv(ENV_FILE)

DATA_DIR = Path(os.environ.get("JARVIS_DATA_DIR", Path.home() / ".jarvis"))

# Ready-made settings for each AI provider. Every one apart from "anthropic"
# speaks the OpenAI chat-completions format. "custom" covers any other
# OpenAI-compatible service (OpenRouter, Groq, Together, LM Studio, ...) and
# needs JARVIS_BASE_URL, JARVIS_API_KEY and JARVIS_MODEL set by hand.
PROVIDERS = {
    "anthropic": {
        "model": "claude-opus-5-5",
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "model": "meta/llama-3.3-70b-instruct",
        "vision_model": "meta/llama-3.2-90b-vision-instruct",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",  # Ollama ignores the key but the client needs one
        "model": "llama3.2",
        "vision_model": "llama3.2-vision",
    },
    "custom": {},
}

PROVIDER = os.environ.get("JARVIS_PROVIDER", "anthropic").strip().lower()
if PROVIDER not in PROVIDERS:
    raise SystemExit(f"JARVIS_PROVIDER={PROVIDER!r} isn't one of: {', '.join(PROVIDERS)}")
_preset = PROVIDERS[PROVIDER]


def _setting(env_name: str, preset_key: str) -> str:
    return os.environ.get(env_name) or _preset.get(preset_key, "")


def _api_key() -> str:
    if os.environ.get("JARVIS_API_KEY"):
        return os.environ["JARVIS_API_KEY"]
    if "api_key_env" in _preset:
        return os.environ.get(_preset["api_key_env"], "")
    return _preset.get("api_key", "")


@dataclass(frozen=True)
class Config:
    provider: str = PROVIDER
    model: str = _setting("JARVIS_MODEL", "model")
    # Ask mode sends a screenshot, so it needs a model that can read images.
    # A model you pick yourself is used for Ask mode too, unless you also set
    # JARVIS_VISION_MODEL.
    vision_model: str = (
        os.environ.get("JARVIS_VISION_MODEL")
        or os.environ.get("JARVIS_MODEL")
        or _preset.get("vision_model")
        or _preset.get("model", "")
    )
    # Only used by OpenAI-compatible providers; the Anthropic client finds
    # ANTHROPIC_API_KEY by itself.
    base_url: str = _setting("JARVIS_BASE_URL", "base_url")
    api_key: str = _api_key()

    whisper_model: str = os.environ.get("JARVIS_WHISPER_MODEL", "base.en")
    speak_replies: bool = os.environ.get("JARVIS_SPEAK", "1") == "1"
    sample_rate: int = 16000

    # Hotkeys are written like "<ctrl>+<alt>+d". Press once to start
    # listening, press again to stop.
    dictate_hotkey: str = os.environ.get("JARVIS_DICTATE_KEY", "<ctrl>+<alt>+d")
    ask_hotkey: str = os.environ.get("JARVIS_ASK_KEY", "<ctrl>+<alt>+a")
    command_hotkey: str = os.environ.get("JARVIS_COMMAND_KEY", "<ctrl>+<alt>+j")

    data_dir: Path = DATA_DIR
    is_mac: bool = platform.system() == "Darwin"
    is_windows: bool = platform.system() == "Windows"


config = Config()
