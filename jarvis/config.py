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
        # If NVIDIA has retired these, Jarvis picks a current model at startup
        # (see models.py).
        "model": "meta/llama-4-maverick-17b-128e-instruct",
        "vision_model": "meta/llama-4-maverick-17b-128e-instruct",
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
    # Whether you picked the models yourself. If not, Jarvis may swap the
    # defaults for ones the provider still offers.
    model_chosen: bool = bool(os.environ.get("JARVIS_MODEL"))
    vision_model_chosen: bool = bool(
        os.environ.get("JARVIS_VISION_MODEL") or os.environ.get("JARVIS_MODEL")
    )
    # Only used by OpenAI-compatible providers; the Anthropic client finds
    # ANTHROPIC_API_KEY by itself.
    base_url: str = _setting("JARVIS_BASE_URL", "base_url")
    api_key: str = _api_key()

    whisper_model: str = os.environ.get("JARVIS_WHISPER_MODEL", "base.en")
    speak_replies: bool = os.environ.get("JARVIS_SPEAK", "1") == "1"
    # Whisper already adds punctuation, so dictation can skip the AI tidy-up
    # (filler words stay in) to save a round trip to the model.
    clean_dictation: bool = os.environ.get("JARVIS_CLEAN_DICTATION", "1") == "1"
    # Lets Ollama models think before answering: sometimes smarter, much slower.
    thinking: bool = os.environ.get("JARVIS_THINKING", "0") == "1"
    # Smaller screenshots make Ask mode much faster on local models, which
    # spend most of their time reading the image.
    screenshot_width: int = int(
        os.environ.get("JARVIS_SCREENSHOT_WIDTH", "1568" if PROVIDER == "anthropic" else "1024")
    )
    sample_rate: int = 16000

    # On a Mac, hold a key to talk and let go to send. Choose from fn,
    # right_cmd, right_option, right_ctrl and right_shift.
    hold_keys: bool = platform.system() == "Darwin" and os.environ.get("JARVIS_HOLD_KEYS", "1") == "1"
    dictate_hold: str = os.environ.get("JARVIS_DICTATE_HOLD", "fn")
    ask_hold: str = os.environ.get("JARVIS_ASK_HOLD", "right_cmd")
    command_hold: str = os.environ.get("JARVIS_COMMAND_HOLD", "right_option")

    # Elsewhere, or with JARVIS_HOLD_KEYS=0, hotkeys are written like
    # "<ctrl>+<alt>+d". Press once to start listening, press again to stop.
    dictate_hotkey: str = os.environ.get("JARVIS_DICTATE_KEY", "<ctrl>+<alt>+d")
    ask_hotkey: str = os.environ.get("JARVIS_ASK_KEY", "<ctrl>+<alt>+a")
    command_hotkey: str = os.environ.get("JARVIS_COMMAND_KEY", "<ctrl>+<alt>+j")

    data_dir: Path = DATA_DIR
    is_mac: bool = platform.system() == "Darwin"
    is_windows: bool = platform.system() == "Windows"


config = Config()
