"""Everyday commands Jarvis handles itself, without asking the AI.

These run in well under a second, so "new tab" or "volume up" doesn't wait
on a model. Anything that doesn't match goes to the AI as before.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime

from . import desktop
from .tools import run_tool

# Names people say -> the web address they mean. Anything else is treated as
# an app, unless it looks like a web address already ("bbc.co.uk").
SITES = {
    "youtube": "youtube.com",
    "google": "google.com",
    "gmail": "mail.google.com",
    "google docs": "docs.google.com",
    "google drive": "drive.google.com",
    "google maps": "maps.google.com",
    "github": "github.com",
    "reddit": "reddit.com",
    "twitter": "x.com",
    "x": "x.com",
    "instagram": "instagram.com",
    "facebook": "facebook.com",
    "netflix": "netflix.com",
    "chatgpt": "chatgpt.com",
    "claude": "claude.ai",
    "wikipedia": "wikipedia.org",
    "amazon": "amazon.com",
    "tiktok": "tiktok.com",
    "twitch": "twitch.tv",
    "linkedin": "linkedin.com",
    "pinterest": "pinterest.com",
}

SEARCH_SITES = "youtube|google|wikipedia|amazon|maps|images"

FILLER_START = re.compile(
    r"^(?:(?:hey|ok|okay|yo)\s+)?(?:jarvis\s*)?(?:(?:please|can you|could you|would you|will you)\s+)*"
)
FILLER_END = re.compile(r"\s+(?:please|for me|now|thanks|thank you)$")


@dataclass
class Quick:
    action: str
    args: dict = field(default_factory=dict)


def normalise(text: str) -> str:
    text = text.lower().replace("\u2019", "'").strip()
    text = re.sub(r"[.,!?;:\"]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = FILLER_START.sub("", text)
    while True:
        trimmed = FILLER_END.sub("", text)
        if trimmed == text:
            return text.strip()
        text = trimmed


def _site(name: str) -> str | None:
    name = name.strip()
    name = re.sub(r"^(?:the )", "", name)
    name = re.sub(r"\s+(?:website|site|dot com)$", "", name)
    if name in SITES:
        return SITES[name]
    if re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+(/\S*)?", name):
        return name
    return None


PATTERNS: list[tuple[str, object]] = [
    (r"(?:open |make |create )?(?:a )?new tab", lambda m: Quick("new_tab")),
    (r"open (?P<x>.+?) in (?:a )?new tab", lambda m: Quick("open", {"target": m["x"], "site_only": True})),
    (r"close (?:this |the |that |my )?(?:current )?tab", lambda m: Quick("browser_key", {"keys": "cmd+w", "done": "Closed the tab."})),
    (r"(?:reopen|restore|bring back) (?:the |my |that )?(?:last |closed |last closed )?tab", lambda m: Quick("browser_key", {"keys": "cmd+shift+t", "done": "Reopened it."})),
    (r"(?:switch to |go to )?(?:the )?next tab", lambda m: Quick("browser_key", {"keys": "cmd+shift+]", "done": "Next tab."})),
    (r"(?:switch to |go to )?(?:the )?previous tab", lambda m: Quick("browser_key", {"keys": "cmd+shift+[", "done": "Previous tab."})),
    (r"(?:open )?(?:a )?new window", lambda m: Quick("keys", {"keys": "cmd+n", "done": "Opened a new window."})),
    (r"go back(?: a page)?", lambda m: Quick("browser_key", {"keys": "cmd+[", "done": "Went back."})),
    (r"go forward(?: a page)?", lambda m: Quick("browser_key", {"keys": "cmd+]", "done": "Went forward."})),
    (r"(?:refresh|reload)(?: (?:the|this) page)?", lambda m: Quick("browser_key", {"keys": "cmd+r", "done": "Reloaded."})),
    (rf"search (?P<site>{SEARCH_SITES}) for (?P<q>.+)", lambda m: Quick("search", {"query": m["q"], "site": m["site"]})),
    (rf"(?:search|look up|google)(?: for)? (?P<q>.+?) on (?P<site>{SEARCH_SITES})", lambda m: Quick("search", {"query": m["q"], "site": m["site"]})),
    (r"play (?P<q>.+?) on youtube", lambda m: Quick("search", {"query": m["q"], "site": "youtube"})),
    (r"(?:search|look up|google)(?: for)? (?P<q>.+)", lambda m: Quick("search", {"query": m["q"], "site": "google"})),
    (r"(?:go to|visit|take me to) (?P<x>.+)", lambda m: Quick("open", {"target": m["x"], "site_only": True})),
    (r"(?:open|launch|start) (?:up )?(?P<x>.+)", lambda m: Quick("open", {"target": m["x"]})),
    (r"(?:pause|resume|play|unpause)(?: (?:the )?(?:music|song|video|track|podcast))?", lambda m: Quick("media", {"action": "play_pause"})),
    (r"(?:next|skip)(?: (?:this |the )?(?:song|track|one))?|skip (?:this |the )?(?:song|track)", lambda m: Quick("media", {"action": "next"})),
    (r"(?:previous|last) (?:song|track)|go back a (?:song|track)", lambda m: Quick("media", {"action": "previous"})),
    (r"(?:turn )?(?:the )?volume up|turn (?:it|the volume) up|louder", lambda m: Quick("volume", {"change": 10})),
    (r"(?:turn )?(?:the )?volume down|turn (?:it|the volume) down|quieter", lambda m: Quick("volume", {"change": -10})),
    (r"(?:set |turn )?(?:the )?volume (?:to )?(?P<n>\d{1,3})(?: ?%| percent)?", lambda m: Quick("volume", {"level": int(m["n"])})),
    (r"mute(?: (?:the )?(?:sound|volume|audio))?", lambda m: Quick("volume", {"mute": True})),
    (r"unmute(?: (?:the )?(?:sound|volume|audio))?", lambda m: Quick("volume", {"mute": False})),
    (r"what time is it|what's the time|what is the time", lambda m: Quick("time")),
    (r"what(?:'s| is) (?:the )?(?:date|day)(?: today)?|what day is it(?: today)?|what's today's date", lambda m: Quick("date")),
    (r"(?:what are|read|list|show) (?:me )?my notes", lambda m: Quick("notes")),
    (r"(?:take a note|make a note|note|remember)(?: that)? (?P<t>.+)", lambda m: Quick("save_note", {"text": m["t"]})),
]

_COMPILED = [(re.compile(pattern), build) for pattern, build in PATTERNS]


def match(text: str) -> Quick | None:
    """Returns the quick command `text` asks for, or None if the AI should handle it."""
    said = normalise(text)
    for pattern, build in _COMPILED:
        m = pattern.fullmatch(said)
        if m:
            quick = build(m)
            # "open a new tab and go to youtube" or "open the file I was
            # working on" are more than an app name; let the AI work them out.
            if quick.action == "open":
                target = quick.args["target"]
                if " and " in f" {target} " or len(target.split()) > 3:
                    return None
            return quick
    return None


def run(quick: Quick) -> str:
    """Carries out a quick command and returns what Jarvis should say."""
    a = quick.args
    if quick.action == "new_tab":
        desktop.new_tab()
        return "New tab."
    if quick.action == "browser_key":
        result = desktop.browser_shortcut(a["keys"])
        if result.startswith("not_browser:"):
            return f"Your browser isn't in front, {result.split(':', 1)[1]} is."
        return a["done"]
    if quick.action == "keys":
        desktop.press_keys(a["keys"])
        return a["done"]
    if quick.action == "search":
        desktop.search_web(a["query"], a["site"])
        where = "" if a["site"] == "google" else f" on {a['site'].capitalize()}"
        return f"Searching{where} for {a['query']}."
    if quick.action == "open":
        target = a["target"].strip()
        site = _site(target)
        if site is None and a.get("site_only"):
            site = re.sub(r"\s+", "", target) + ".com"
        if site:
            desktop.open_url(site)
            return f"Opening {target}."
        try:
            desktop.open_app(target)
        except Exception:
            return f"I couldn't find an app called {target}."
        return f"Opening {target}."
    if quick.action == "media":
        desktop.media(a["action"])
        return {"play_pause": "Done.", "next": "Skipped.", "previous": "Going back a track."}[a["action"]]
    if quick.action == "volume":
        if "mute" in a:
            desktop.set_volume(mute=a["mute"])
            return "Muted." if a["mute"] else "Unmuted."
        level = desktop.set_volume(level=a.get("level"), change=a.get("change", 0))
        return f"Volume {level}."
    if quick.action == "time":
        return datetime.now().strftime("It's %-I:%M %p.")
    if quick.action == "date":
        return datetime.now().strftime("It's %A, %B %-d.")
    if quick.action == "notes":
        return run_tool("list_notes", {})
    if quick.action == "save_note":
        run_tool("save_note", {"text": a["text"]})
        return "Noted."
    raise ValueError(f"Unknown quick action: {quick.action}")
