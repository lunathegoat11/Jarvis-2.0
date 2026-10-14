"""Tools the AI can call in command mode, and the code that runs them."""

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
        "name": "new_tab",
        "description": (
            "Open a new browser tab. Give a url to load it in the new tab, "
            "or an empty string for a blank tab."
        ),
        "strict": True,
        "input_schema": _schema({"url": {"type": "string"}}, ["url"]),
    },
    {
        "name": "search_web",
        "description": "Open a search in the browser, on Google or another site.",
        "strict": True,
        "input_schema": _schema(
            {
                "query": {"type": "string"},
                "site": {
                    "type": "string",
                    "enum": ["google", "youtube", "wikipedia", "amazon", "maps", "images"],
                },
            },
            ["query", "site"],
        ),
    },
    {
        "name": "press_keys",
        "description": (
            "Press a keyboard shortcut in the app that's in front, written like "
            "'cmd+t', 'cmd+shift+t' or 'enter'. Use this for things like closing a tab "
            "(cmd+w), going back in a browser (cmd+[) or switching apps (cmd+tab)."
        ),
        "strict": True,
        "input_schema": _schema({"keys": {"type": "string"}}, ["keys"]),
    },
    {
        "name": "media_control",
        "description": "Play or pause whatever music or video is playing, or skip tracks.",
        "strict": True,
        "input_schema": _schema(
            {"action": {"type": "string", "enum": ["play_pause", "next", "previous"]}},
            ["action"],
        ),
    },
    {
        "name": "set_volume",
        "description": (
            "Change the computer's volume. action 'set' uses level (0-100); "
            "'up' and 'down' move it by 10; 'mute' and 'unmute' ignore level."
        ),
        "strict": True,
        "input_schema": _schema(
            {
                "action": {"type": "string", "enum": ["set", "up", "down", "mute", "unmute"]},
                "level": {"type": "integer"},
            },
            ["action", "level"],
        ),
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
]

USE_SCREEN_TOOL = {
    "name": "use_screen",
    "description": (
        "Look at the screen and use the mouse and keyboard to get something done "
        "that needs seeing and clicking, like 'play the latest MrBeast video on "
        "YouTube' or 'turn on dark mode in Settings'. Describe the whole task. "
        "Takes a while, so prefer the direct tools when they're enough."
    ),
    "strict": True,
    "input_schema": _schema({"task": {"type": "string"}}, ["task"]),
}

EMAIL_TOOLS = [
    {
        "name": "check_email",
        "description": (
            "List the newest emails in the inbox: id, sender, subject, date, and "
            "whether each is unread. Doesn't mark anything as read."
        ),
        "strict": True,
        "input_schema": _schema(
            {"count": {"type": "integer"}, "unread_only": {"type": "boolean"}},
            ["count", "unread_only"],
        ),
    },
    {
        "name": "read_email",
        "description": "Read one email in full, by the id check_email gave.",
        "strict": True,
        "input_schema": _schema({"id": {"type": "string"}}, ["id"]),
    },
    {
        "name": "draft_email",
        "description": (
            "Open a new email in the user's mail app, filled in and ready for them "
            "to check and send. You can't send email yourself."
        ),
        "strict": True,
        "input_schema": _schema(
            {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
            ["to", "subject", "body"],
        ),
    },
]

# Claude's web search runs on Anthropic's servers, so only Claude gets it.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search", "max_uses": 3}


def command_tools(can_see_screen: bool = True) -> list[dict]:
    """The tools Command mode offers, in Anthropic's format."""
    from . import mail

    tools = list(TOOLS)
    if mail.configured():
        tools += EMAIL_TOOLS
    if can_see_screen:
        tools.append(USE_SCREEN_TOOL)
    return tools


def to_openai(tools: list[dict]) -> list[dict]:
    """Converts tools to the OpenAI chat-completions format that NVIDIA,
    Ollama and others use. "strict" is left out because not every provider
    accepts it, and Anthropic's own server tools are dropped."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools
        if "input_schema" in tool
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
    if name == "new_tab":
        desktop.new_tab(args["url"])
        return "Opened a new tab."
    if name == "search_web":
        desktop.search_web(args["query"], args["site"])
        return f"Searching {args['site']} for {args['query']}."
    if name == "press_keys":
        desktop.press_keys(args["keys"])
        return f"Pressed {args['keys']}."
    if name == "media_control":
        desktop.media(args["action"])
        return "Done."
    if name == "set_volume":
        action = args["action"]
        if action in ("mute", "unmute"):
            desktop.set_volume(mute=action == "mute")
            return f"{action.capitalize()}d."
        if action == "set":
            return f"Volume is now {desktop.set_volume(level=args['level'])}."
        change = 10 if action == "up" else -10
        return f"Volume is now {desktop.set_volume(change=change)}."
    if name == "check_email":
        from . import mail

        found = mail.recent(args["count"], args["unread_only"])
        if not found:
            return "No emails." if not args["unread_only"] else "No unread emails."
        return "\n".join(
            f"id {m.id}: {'UNREAD ' if m.unread else ''}from {m.sender}, \"{m.subject}\", {m.date}"
            for m in found
        )
    if name == "read_email":
        from . import mail

        return mail.read(args["id"])
    if name == "draft_email":
        from . import mail

        mail.draft(args["to"], args["subject"], args["body"])
        return "The draft is open in the mail app for the user to check and send."
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
