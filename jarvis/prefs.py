"""Settings you change in the Jarvis app while it's running.

They're saved to ~/.jarvis/settings.json and take effect straight away.
Anything not changed there comes from .env (see config.py).
"""

import json
import threading

from .config import config

# The settings the app can change, with the .env value each one overrides.
EDITABLE = {
    "voice": lambda: config.voice,
    "voice_speed": lambda: config.voice_speed,
    "speak_replies": lambda: config.speak_replies,
    "clean_dictation": lambda: config.clean_dictation,
    "vocabulary": lambda: config.vocabulary,
    "my_number": lambda: config.my_number,
}

_lock = threading.Lock()
_values: dict | None = None


def _path():
    return config.data_dir / "settings.json"


def _load() -> dict:
    global _values
    if _values is None:
        try:
            _values = json.loads(_path().read_text())
        except (OSError, ValueError):
            _values = {}
    return _values


def get(key: str, default=None):
    with _lock:
        values = _load()
    if key in values:
        return values[key]
    if default is not None:
        return default
    return EDITABLE[key]()


def set(key: str, value) -> None:
    if key not in EDITABLE:
        raise KeyError(key)
    with _lock:
        values = _load()
        values[key] = value
        config.data_dir.mkdir(parents=True, exist_ok=True)
        _path().write_text(json.dumps(values, indent=2))


def add_words(words: list[str]) -> str:
    """Adds words to the dictionary, skipping ones already in it."""
    current = [w.strip() for w in str(get("vocabulary")).split(",") if w.strip()]
    known = {w.lower() for w in current}
    for word in words:
        word = word.strip().strip(".")
        if word and word.lower() not in known:
            current.append(word)
            known.add(word.lower())
    value = ", ".join(current)
    set("vocabulary", value)
    return value


def all_values() -> dict:
    return {key: get(key) for key in EDITABLE}
