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
    {
        "name": "write_document",
        "description": (
            "Write something longer the user asked for (a study guide or prep sheet, notes, "
            "a draft, a plan, a list) into a document and open it on the Mac. Use this "
            "instead of putting long text in your reply, then say in a sentence what you "
            "made. content is plain text; headings and '-' bullets are fine."
        ),
        "strict": True,
        "input_schema": _schema(
            {"title": {"type": "string"}, "content": {"type": "string"}}, ["title", "content"]
        ),
    },
]

# Memory, weather, news, timers and reminders. These work with every AI
# provider, so they don't depend on Claude's web search.
TOOLS += [
    {
        "name": "remember",
        "description": (
            "Save a lasting fact about the user so you know it in future conversations: "
            "their name, where they live, school or work, classes, people in their life, "
            "likes and dislikes, routines. Save one fact per call, in a short sentence "
            "about the user ('Lives in Princeton, NJ'). Never save passwords, codes or "
            "card numbers."
        ),
        "strict": True,
        "input_schema": _schema({"fact": {"type": "string"}}, ["fact"]),
    },
    {
        "name": "forget",
        "description": (
            "Delete saved facts about the user. Every fact containing the given words is "
            "removed, so quote the part that identifies it."
        ),
        "strict": True,
        "input_schema": _schema({"about": {"type": "string"}}, ["about"]),
    },
    {
        "name": "get_weather",
        "description": (
            "Current weather and a 3-day forecast. place is a town like 'Princeton, NJ'; "
            "use where the user lives (from what you remember) unless they name somewhere "
            "else, or an empty string to use their saved location."
        ),
        "strict": True,
        "input_schema": _schema({"place": {"type": "string"}}, ["place"]),
    },
    {
        "name": "get_news",
        "description": "Today's headlines from BBC News, with a line about each.",
        "strict": True,
        "input_schema": _schema(
            {
                "topic": {
                    "type": "string",
                    "enum": ["top", "world", "us", "business", "technology", "science",
                             "health", "entertainment", "sport"],
                },
                "count": {"type": "integer"},
            },
            ["topic", "count"],
        ),
    },
    {
        "name": "set_timer",
        "description": (
            "Start a timer; Jarvis says out loud when it's done. seconds is its length; "
            "label is what it's for ('pasta'), or an empty string."
        ),
        "strict": True,
        "input_schema": _schema(
            {"seconds": {"type": "integer"}, "label": {"type": "string"}}, ["seconds", "label"]
        ),
    },
    {
        "name": "remind_me",
        "description": (
            "Have Jarvis say a reminder out loud (and send it to the user's phone) at a "
            "set time, e.g. 'remind me at 5 to call grandma'. when is local time as "
            "'YYYY-MM-DD HH:MM'. For 'in 20 minutes' work out the time from the current "
            "time. This is Jarvis's own reminder, not the Reminders app (add_reminder)."
        ),
        "strict": True,
        "input_schema": _schema(
            {"when": {"type": "string"}, "message": {"type": "string"}}, ["when", "message"]
        ),
    },
    {
        "name": "list_timers",
        "description": "List the timers and reminders Jarvis has set, with how long is left.",
        "strict": True,
        "input_schema": _schema({}, []),
    },
    {
        "name": "cancel_timer",
        "description": (
            "Cancel a timer or reminder by its id from list_timers, or by words in it "
            "('pasta'), or 'all'."
        ),
        "strict": True,
        "input_schema": _schema({"which": {"type": "string"}}, ["which"]),
    },
]

# Documents written this run, newest last, so a request from the phone can
# send them there (see main.py).
made_documents: list = []

# Driving the user's own browser by reading the page (see browser.py). Much
# more reliable on websites than clicking on screenshots.
BROWSER_TOOLS = [
    {
        "name": "browse_open",
        "description": (
            "Open a web page in the user's browser (Safari or Chrome) and read it: you get "
            "its text and a numbered list of the links, buttons and boxes on it. new_tab "
            "false reuses the current tab. Use this, then browse_click and browse_type, to "
            "get things done on websites."
        ),
        "strict": True,
        "input_schema": _schema(
            {"url": {"type": "string"}, "new_tab": {"type": "boolean"}}, ["url", "new_tab"]
        ),
    },
    {
        "name": "browse_read",
        "description": "Read the page open in the browser now, with its numbered links, buttons and boxes.",
        "strict": True,
        "input_schema": _schema({}, []),
    },
    {
        "name": "browse_click",
        "description": "Click a link or button on the page by its number from the latest read.",
        "strict": True,
        "input_schema": _schema({"number": {"type": "integer"}}, ["number"]),
    },
    {
        "name": "browse_type",
        "description": (
            "Type into a box on the page by its number, replacing what's there. submit true "
            "presses Enter afterwards (to search, say)."
        ),
        "strict": True,
        "input_schema": _schema(
            {"number": {"type": "integer"}, "text": {"type": "string"}, "submit": {"type": "boolean"}},
            ["number", "text", "submit"],
        ),
    },
    {
        "name": "browse_scroll",
        "description": "Scroll the page and read what's now in view.",
        "strict": True,
        "input_schema": _schema(
            {"direction": {"type": "string", "enum": ["down", "up", "top", "bottom"]}}, ["direction"]
        ),
    },
    {
        "name": "browse_back",
        "description": "Go back to the previous page in the browser.",
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

LOOK_AT_SCREEN_TOOL = {
    "name": "look_at_screen",
    "description": (
        "Take a screenshot and answer a question about what's on the user's "
        "screen, e.g. 'what does this error mean' or 'summarise this page'."
    ),
    "strict": True,
    "input_schema": _schema({"question": {"type": "string"}}, ["question"]),
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

CALENDAR_TOOLS = [
    {
        "name": "check_calendar",
        "description": "List calendar events from today through the next few days (1 = just today).",
        "strict": True,
        "input_schema": _schema({"days": {"type": "integer"}}, ["days"]),
    },
    {
        "name": "add_calendar_event",
        "description": (
            "Add an event to the user's calendar. start is local time as 'YYYY-MM-DD HH:MM'. "
            "First say back the title, day and time and ask the user to confirm; only call "
            "this with confirmed=true after they've said yes in this conversation."
        ),
        "strict": True,
        "input_schema": _schema(
            {
                "title": {"type": "string"},
                "start": {"type": "string"},
                "duration_minutes": {"type": "integer"},
                "confirmed": {"type": "boolean"},
            },
            ["title", "start", "duration_minutes", "confirmed"],
        ),
    },
    {
        "name": "add_reminder",
        "description": (
            "Add a reminder to the Reminders app. due is local time as 'YYYY-MM-DD HH:MM', "
            "or an empty string for no due time."
        ),
        "strict": True,
        "input_schema": _schema(
            {"title": {"type": "string"}, "due": {"type": "string"}}, ["title", "due"]
        ),
    },
]

DEVICE_TOOLS = [
    {
        "name": "list_devices",
        "description": (
            "List the TVs and speakers on the user's Wi-Fi (Chromecast / Google TV, Sonos, "
            "Roku) and say whether Home Assistant is connected."
        ),
        "strict": True,
        "input_schema": _schema({}, []),
    },
    {
        "name": "control_device",
        "description": (
            "Control a TV or speaker by name, e.g. 'living room TV' or 'kitchen'. level is "
            "0-100 and only used by set_volume (send 0 otherwise)."
        ),
        "strict": True,
        "input_schema": _schema(
            {
                "device": {"type": "string"},
                "action": {
                    "type": "string",
                    "enum": [
                        "play", "pause", "stop", "next", "previous", "volume_up", "volume_down",
                        "set_volume", "mute", "unmute", "power_on", "power_off", "home", "back",
                    ],
                },
                "level": {"type": "integer"},
            },
            ["device", "action", "level"],
        ),
    },
    {
        "name": "tv_open_app",
        "description": (
            "On a Roku TV: open a streaming app (YouTube, Netflix, Hulu, Disney+, Prime Video, "
            "Spotify, Max, Plex...), or search for a show or film when search is given "
            "(otherwise send an empty search)."
        ),
        "strict": True,
        "input_schema": _schema(
            {"device": {"type": "string"}, "app": {"type": "string"}, "search": {"type": "string"}},
            ["device", "app", "search"],
        ),
    },
]

HOME_ASSISTANT_TOOLS = [
    {
        "name": "smart_home",
        "description": (
            "Control the smart home through Home Assistant with a plain sentence, e.g. 'turn "
            "off the bedroom lights', 'set the thermostat to 21', 'is the front door locked', "
            "'turn on the living room TV'. Also covers Alexa devices connected to it."
        ),
        "strict": True,
        "input_schema": _schema({"command": {"type": "string"}}, ["command"]),
    },
    {
        "name": "alexa_announce",
        "description": (
            "Make an Amazon Echo say something out loud. device is the Echo's name, or an "
            "empty string for all of them."
        ),
        "strict": True,
        "input_schema": _schema(
            {"message": {"type": "string"}, "device": {"type": "string"}}, ["message", "device"]
        ),
    },
]

CONTACT_TOOLS = [
    {
        "name": "text_me",
        "description": (
            "Send the user a text message to their own phone. Use it when they ask, or "
            "on your own when something genuinely urgent or time-sensitive comes up and "
            "they should know now. This is the default way to reach them."
        ),
        "strict": True,
        "input_schema": _schema({"message": {"type": "string"}}, ["message"]),
    },
    {
        "name": "call_me",
        "description": (
            "Call the user's phone, or send an urgent alert when calls aren't set up, for "
            "something that truly can't wait for a text. Give a short reason; it's read "
            "out or shown to them. Prefer text_me unless it's really urgent."
        ),
        "strict": True,
        "input_schema": _schema({"reason": {"type": "string"}}, ["reason"]),
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
    if config.is_mac:
        tools += CALENDAR_TOOLS + BROWSER_TOOLS
    from . import contact

    if contact.configured():
        tools += CONTACT_TOOLS
    if config.devices:
        tools += DEVICE_TOOLS
    from . import devices

    if devices.home_assistant_configured():
        tools += HOME_ASSISTANT_TOOLS
    if can_see_screen:
        tools += [LOOK_AT_SCREEN_TOOL, USE_SCREEN_TOOL]
    return tools


# Claude accepts at most this many tools in strict mode per request.
MAX_STRICT_TOOLS = 20


def limit_strict(tools: list[dict], limit: int = MAX_STRICT_TOOLS) -> list[dict]:
    """Takes strict mode off tools beyond the limit. Tools with no inputs gain
    nothing from it, so they lose it first; after that, the tools listed
    earliest keep it. The rest still work, just without the guarantee."""
    strict = [t for t in tools if t.get("strict")]
    if len(strict) <= limit:
        return tools
    with_inputs = [t for t in strict if t.get("input_schema", {}).get("properties")]
    keep = {id(t) for t in (with_inputs + [t for t in strict if t not in with_inputs])[:limit]}
    return [
        t if not t.get("strict") or id(t) in keep else {k: v for k, v in t.items() if k != "strict"}
        for t in tools
    ]


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
    if name in ("list_devices", "control_device", "tv_open_app", "smart_home", "alexa_announce"):
        from . import devices

        if name == "list_devices":
            return devices.summary(devices.discover(refresh=True))
        if name == "smart_home":
            return devices.home_command(args["command"])
        if name == "alexa_announce":
            return devices.alexa_announce(args["message"], args["device"])
        device = devices.find(args["device"], devices.discover())
        if name == "control_device":
            return devices.control(device, args["action"], args["level"])
        return devices.open_app(device, args["app"], args["search"])
    if name == "text_me":
        from . import contact

        return contact.text_me(args["message"])
    if name == "call_me":
        from . import contact

        return contact.call_me(args["reason"])
    if name == "check_calendar":
        from . import macapps

        return macapps.upcoming_events(args["days"])
    if name == "add_calendar_event":
        if not args["confirmed"]:
            return "Not added. Ask the user to confirm the title, day and time first."
        from . import macapps

        return macapps.add_event(args["title"], args["start"], args["duration_minutes"])
    if name == "add_reminder":
        from . import macapps

        return macapps.add_reminder(args["title"], args["due"])
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
    if name in ("remember", "forget"):
        from . import memory

        return memory.remember(args["fact"]) if name == "remember" else memory.forget(args["about"])
    if name == "get_weather":
        from . import info

        return info.weather(args["place"])
    if name == "get_news":
        from . import info

        return info.news(args["topic"], args["count"])
    if name in ("set_timer", "remind_me", "list_timers", "cancel_timer"):
        from . import timers

        scheduler = timers.get()
        if name == "set_timer":
            return scheduler.add_timer(args["seconds"], args["label"])
        if name == "remind_me":
            return scheduler.add_reminder(args["when"], args["message"])
        if name == "list_timers":
            return scheduler.pending()
        return scheduler.cancel(args["which"])
    if name.startswith("browse_"):
        from . import browser

        if name == "browse_open":
            return browser.open_page(args["url"], args["new_tab"])
        if name == "browse_read":
            return browser.read_page()
        if name == "browse_click":
            return browser.click(args["number"])
        if name == "browse_type":
            return browser.type_into(args["number"], args["text"], args["submit"])
        if name == "browse_scroll":
            return browser.scroll(args["direction"])
        if name == "browse_back":
            return browser.go_back()
    if name == "write_document":
        path = write_document(args["title"], args["content"])
        return f"Saved it as {path.name} in Documents > Jarvis and opened it."
    raise ValueError(f"Unknown tool: {name}")


def write_document(title: str, content: str):
    """Saves a document to ~/Documents/Jarvis and opens it. Returns its path."""
    import re
    import subprocess
    from pathlib import Path

    folder = Path.home() / "Documents" / "Jarvis"
    folder.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w\- ]", "", title).strip()[:80] or "Jarvis document"
    path = folder / f"{name}.txt"
    if path.exists():
        path = folder / f"{name} {datetime.now().strftime('%Y-%m-%d %H.%M.%S')}.txt"
    path.write_text(f"{title}\n\n{content.strip()}\n", encoding="utf-8")
    made_documents.append(path)
    try:
        if config.is_mac:
            subprocess.run(["open", str(path)], check=False)
        elif config.is_windows:
            import os

            os.startfile(path)  # noqa: S606
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass  # saved either way; opening it is a nicety
    return path
