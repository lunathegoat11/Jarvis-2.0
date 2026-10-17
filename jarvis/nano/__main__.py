"""`python -m jarvis.nano` starts Jarvis Nano.

It keeps its own memory, timers and settings in ~/.jarvis-nano, so it can run
on the same computer as desktop Jarvis. Keys and settings it doesn't set
itself (the AI provider and key, your number, ntfy...) come from
~/.jarvis/.env, so you only enter them once.
"""

import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

# This must happen before anything reads the settings.
data = Path(os.environ.setdefault("JARVIS_DATA_DIR", str(Path.home() / ".jarvis-nano")))
load_dotenv(data / ".env")
for name, value in dotenv_values(Path.home() / ".jarvis" / ".env").items():
    if value and not os.environ.get(name):
        os.environ[name] = value

from .main import main  # noqa: E402

main()
