"""Long-term memory: what Jarvis keeps across days.

Three kinds of thing, all in ~/.jarvis/memory.json (a plain file you can
read and edit), and all shown to the AI at the start of every command:

- facts about you ("Lives in Princeton, NJ")
- lessons from your corrections ("'My email' means Gmail in Chrome")
- skills: steps that worked for a task, reused the next time

Say "remember that...", "forget that..." or "what do you remember about
me". Lessons and skills are saved by Jarvis itself as it learns.
"""

import json
import threading
from datetime import date

from .config import config

# More than this of each kind and the oldest stop being shown to the AI
# (they stay in the file). Keeps every request small and cheap.
MAX_SHOWN = {"fact": 150, "lesson": 60, "skill": 40}
# Skills longer than this are cut when shown.
MAX_SKILL_CHARS = 700

_lock = threading.Lock()


def _path():
    return config.data_dir / "memory.json"


def load() -> list[dict]:
    try:
        entries = json.loads(_path().read_text())
    except (OSError, ValueError):
        return []
    entries = [e for e in entries if isinstance(e, dict) and str(e.get("text", "")).strip()]
    for entry in entries:
        entry.setdefault("kind", "fact")
    return entries


def _save(entries: list[dict]) -> None:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    _path().write_text(json.dumps(entries, indent=2))


def _tidy(text: str) -> str:
    return " ".join(text.split())


def remember(fact: str, kind: str = "fact") -> str:
    fact = _tidy(fact)
    if not fact:
        raise ValueError("Nothing to remember.")
    with _lock:
        entries = load()
        if any(e["kind"] == kind and e["text"].lower() == fact.lower() for e in entries):
            return "I already knew that."
        entries.append({"kind": kind, "text": fact, "saved": date.today().isoformat()})
        _save(entries)
    if kind == "lesson":
        return "Lesson learned."
    return "Got it, I'll remember that."


def save_skill(task: str, steps: str) -> str:
    """Saves the steps that worked for a task, replacing older steps for
    the same task."""
    task, steps = _tidy(task), steps.strip()
    if not task or not steps:
        raise ValueError("A skill needs a task and its steps.")
    with _lock:
        entries = [
            e for e in load()
            if not (e["kind"] == "skill" and e.get("task", "").lower() == task.lower())
        ]
        entries.append({
            "kind": "skill", "task": task, "text": steps, "saved": date.today().isoformat(),
        })
        _save(entries)
    return f"Saved how to {task}."


def forget(about: str) -> str:
    """Forgets every fact, lesson or skill containing `about` (any case)."""
    about = _tidy(about).lower()
    if not about:
        raise ValueError("Say what to forget.")
    with _lock:
        entries = load()
        kept = [
            e for e in entries
            if about not in e["text"].lower() and about not in e.get("task", "").lower()
        ]
        removed = len(entries) - len(kept)
        if removed:
            _save(kept)
    if not removed:
        return "I don't have anything saved about that."
    return "Forgotten." if removed == 1 else f"Forgot {removed} things."


def prompt_section() -> str:
    """Everything remembered, ready to add to the AI's instructions."""
    entries = load()

    def latest(kind):
        return [e for e in entries if e["kind"] == kind][-MAX_SHOWN[kind]:]

    parts = []
    facts = latest("fact")
    if facts:
        lines = "\n".join(f"- {e['text']}" for e in facts)
        parts.append(f"What you remember about the user from earlier conversations:\n{lines}")
    lessons = latest("lesson")
    if lessons:
        lines = "\n".join(f"- {e['text']}" for e in lessons)
        parts.append(f"Lessons you've learned from the user's corrections. Follow them:\n{lines}")
    skills = latest("skill")
    if skills:
        lines = "\n".join(
            f"- To {e['task']}: {e['text'][:MAX_SKILL_CHARS]}" for e in skills
        )
        parts.append(
            "Skills you've learned (steps that worked before). When a request matches "
            f"one, follow its steps, and update it with save_skill if they no longer work:\n{lines}"
        )
    return "".join(f"\n\n{part}" for part in parts)
