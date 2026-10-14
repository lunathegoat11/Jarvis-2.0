"""Tools Claude can call in command mode, and the code that runs them."""

import json
from datetime import datetime

from . import desktop
from .config import config


def _schema(properties: dict, required: list[str]) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


TOOLS = [
    {
        "name": "open_url",
        "description": "Open a web page in the default browser.",
        "strict": True,
        "input_schema": _schema({"url": {"type": "string"}}, ["url"]),
    },
    {
        "name": "open_app",
        "description": (
            "Launch an application by name, e.g. 'Spotify', 'Calculator', 'notepad'. "
            "Use the name the operating system knows it by."
        ),
        "strict": True,
        "input_schema": _schema({"name": {"type": "string"}}, ["name"]),
    },
    {
        "name": "type_text",
        "description": "Type text into whichever app and text field currently has focus.",
        "strict": True,
        "input_schema": _schema({"text": {"type": "string"}}, ["text"]),
    },
    {
        "name": "read_clipboard",
        "description": "Read the text currently on the clipboard.",
        "strict": True,
        "input_schema": _schema({}, []),
    },
    {
        "name": "save_note",
        "description": "Save a note the user wants Jarvis to remember for later.",
        "strict": True,
        "input_schema": _schema({"text": {"type": "string"}}, ["text"]),
    },
    {
        "name": "list_notes",
        "description": "Read back every note saved so far, oldest first, with timestamps.",
        "strict": True,
        "input_schema": _schema({}, []),
    },
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 3},
]


def _notes_path():
    config.data_dir.mkdir(parents=True, exist_ok=True)
    return config.data_dir / "notes.json"


def _load_notes() -> list[dict]:
    path = _notes_path()
    if not path.exists():
        return []
    return json.loads(path.read_text())


def run_tool(name: str, args: dict) -> str:
    """Runs one tool call and returns text for the tool_result block.

    Raises on failure; the caller turns that into an is_error result.
    """
    if name == "open_url":
        desktop.open_url(args["url"])
        return f"Opened {args['url']}"
    if name == "open_app":
        desktop.open_app(args["name"])
        return f"Opened {args['name']}"
    if name == "type_text":
        desktop.paste_text(args["text"])
        return "Typed it."
    if name == "read_clipboard":
        return desktop.read_clipboard() or "(clipboard is empty)"
    if name == "save_note":
        notes = _load_notes()
        notes.append({"time": datetime.now().isoformat(timespec="minutes"), "text": args["text"]})
        _notes_path().write_text(json.dumps(notes, indent=2))
        return "Saved."
    if name == "list_notes":
        notes = _load_notes()
        if not notes:
            return "No notes saved yet."
        return "\n".join(f"{n['time']}: {n['text']}" for n in notes)
    raise ValueError(f"Unknown tool: {name}")
