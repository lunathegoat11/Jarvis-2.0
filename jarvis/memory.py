"""Long-term memory: things about you that Jarvis keeps across days.

They're saved in ~/.jarvis/memory.json, a plain file you can read and edit,
and Jarvis sees them at the start of every command. Say "remember that..."
or "forget that..." to change them, or "what do you remember about me".
"""

import json
import threading
from datetime import date

from .config import config

# More than this and the oldest facts stop being shown to the AI (they stay
# in the file). Keeps every request small and cheap.
MAX_SHOWN = 150

_lock = threading.Lock()


def _path():
    return config.data_dir / "memory.json"


def load() -> list[dict]:
    try:
        facts = json.loads(_path().read_text())
    except (OSError, ValueError):
        return []
    return [f for f in facts if isinstance(f, dict) and str(f.get("text", "")).strip()]


def _save(facts: list[dict]) -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(facts, indent=2))


def remember(fact: str) -> str:
    fact = " ".join(fact.split())
    if not fact:
        raise ValueError("Nothing to remember.")
    with _lock:
        facts = load()
        if any(f["text"].lower() == fact.lower() for f in facts):
            return "I already knew that."
        facts.append({"text": fact, "saved": date.today().isoformat()})
        _save(facts)
    return "Got it, I'll remember that."


def forget(about: str) -> str:
    """Forgets every saved fact containing `about` (any case)."""
    about = " ".join(about.split()).lower()
    if not about:
        raise ValueError("Say what to forget.")
    with _lock:
        facts = load()
        kept = [f for f in facts if about not in f["text"].lower()]
        removed = len(facts) - len(kept)
        if removed:
            _save(kept)
    if not removed:
        return "I don't have anything saved about that."
    return "Forgotten." if removed == 1 else f"Forgot {removed} things."


def prompt_section() -> str:
    """The facts, ready to add to the AI's instructions."""
    facts = load()[-MAX_SHOWN:]
    if not facts:
        return ""
    lines = "\n".join(f"- {f['text']}" for f in facts)
    return f"\n\nWhat you remember about the user from earlier conversations:\n{lines}"
