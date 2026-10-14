"""One key for everything: works out from what you said whether you want
dictation, a question about the screen, or a command.

- Starting with "type" or "write" means dictation: "type see you at six"
  types "See you at six." into the text box you're in.
- Talking about what's on screen ("what's this error", "summarise this
  page") means Ask.
- Everything else is a command. The command AI can still look at the
  screen itself if a question slips through.

This is plain pattern matching, so it costs nothing and adds no delay.
"""

import re

DICTATE = re.compile(
    r"^(?:(?:hey |ok |okay )?jarvis[, ]+)?(?:please )?"
    r"(?:type|write|dictate|type out|write down|write out)(?: this| that)?[:,]?\s+"
    # "write an email to Sam" is a request, not words to type.
    r"(?!(?:an? |the |me an? )?(?:e-?mail|message|note|reply|text)\b)"
    r"(?P<text>.+)$",
    re.IGNORECASE | re.DOTALL,
)

# Sentences that start like an instruction are commands, even if they
# mention the screen ("use my screen to play...", "close this tab").
COMMAND_START = re.compile(
    r"^(?:(?:hey |ok |okay )?jarvis[, ]+)?(?:please |can you |could you )?"
    r"(?:open|play|click|go|search|close|turn|set|send|reply|scroll|find|watch|launch|"
    r"start|pause|skip|mute|unmute|volume|new|take|remember|draft|email|use|show|put|"
    r"make|switch|bring|move|press|save|check my|read my)\b",
    re.IGNORECASE,
)

ASK = re.compile(
    r"\b(?:"
    r"(?:on|of) (?:my|the|this) screen"
    r"|screen"
    r"|what am i looking at"
    r"|what(?:'s| is) (?:this|that|going on here)"
    r"|(?:read|explain|summari[sz]e|translate|describe|check) (?:this|that|it)\b"
    r"|this (?:page|error|email|message|code|image|picture|photo|video|website|site|"
    r"document|doc|tab|window|chart|graph|question|problem|word|paragraph|text)"
    r")",
    re.IGNORECASE,
)


def route(text: str) -> tuple[str, str]:
    """Returns (mode, text): mode is "dictate", "ask" or "command"."""
    said = text.strip()
    dictate = DICTATE.match(said)
    if dictate:
        return "dictate", dictate["text"].strip()
    if COMMAND_START.match(said):
        return "command", said
    if ASK.search(said):
        return "ask", said
    return "command", said
