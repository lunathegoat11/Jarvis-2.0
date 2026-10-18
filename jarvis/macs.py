"""Jarvis on more than one Mac: "open YouTube on the old Mac".

Each Mac has a name (JARVIS_MAC_NAME, like "main" or "old") and they all
listen on one shared private ntfy topic (NTFY_MACS_TOPIC). Asking one Jarvis
to do something on another Mac sends the job over that topic. The other Mac
says it got it straight away, does it as if it had been typed there, and
sends back its answer, which the first Mac passes on to you.

Whoever knows the topic can control every Mac on it, so keep it as secret as
a password. Set it up with `python -m jarvis.macs main` on one Mac and
`python -m jarvis.macs old --paste` on the other.
"""

import json
import re
import secrets
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager

from . import remote
from .config import config

# How long to wait for the other Mac to say it got the job, then for it to
# finish. A job that takes longer is answered on your phone when it's done.
GOT_SECONDS = 15
DONE_SECONDS = 120
# ntfy takes messages up to 4096 bytes.
MAX_REPLY = 3000
TOPIC_PREFIX = "jarvis-macs-"

_pending: dict[str, dict] = {}
_lock = threading.Lock()
_local = threading.local()
_on_late = None


def name_of(text: str) -> str:
    """'The old MacBook' and 'old mac' are both "old"."""
    words = re.sub(r"[^a-z0-9 ]", " ", text.lower()).split()
    words = [w for w in words if w not in ("the", "my", "mac", "macbook", "macbooks", "macs", "computer", "laptop")]
    return " ".join(words)


def configured() -> bool:
    topic = config.ntfy_macs_topic
    return (
        bool(name_of(config.mac_name))
        and bool(topic)
        and topic not in (config.ntfy_topic, config.ntfy_reply_topic)
    )


def me() -> str:
    return name_of(config.mac_name)


# ---- which other Macs there are ---------------------------------------------------


def _known_path():
    return config.data_dir / "macs.json"


def known() -> list[str]:
    """The other Macs this one has heard from."""
    try:
        names = json.loads(_known_path().read_text())
    except (OSError, ValueError):
        return []
    return [n for n in names if isinstance(n, str) and n and n != me()]


def _learn(name: str) -> None:
    if not name or name == me() or name in known():
        return
    try:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        _known_path().write_text(json.dumps(sorted(known() + [name])))
    except OSError:
        pass


def prompt_section() -> str:
    """Tells the AI which Mac it's on and which others it can use."""
    if not configured():
        return ""
    others = known()
    text = f'\n\nThis Mac is called "{me()}".'
    if others:
        text += " Jarvis also runs on these Macs: " + ", ".join(f'"{n}"' for n in others) + "."
    return text + (
        " When the user asks for something to happen on another Mac (\"on the old Mac\", "
        "\"on my main MacBook\"), use other_mac with that Mac's name and the task in plain "
        "words, then tell them what it said. If they don't name a Mac, do it on this one."
    )


# ---- sending -------------------------------------------------------------------------


def _publish(payload: dict) -> None:
    url = f"{config.ntfy_server.rstrip('/')}/{config.ntfy_macs_topic}"
    headers = {"Title": "Jarvis", "Content-Type": "application/json"}
    if config.ntfy_token:
        headers["Authorization"] = f"Bearer {config.ntfy_token}"
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    try:
        urllib.request.urlopen(request, timeout=15).close()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"ntfy said: HTTP {error.code}") from None
    except urllib.error.URLError as error:
        raise RuntimeError(f"Couldn't reach ntfy ({error.reason}). Is the Mac online?") from None


@contextmanager
def passed_on():
    """Marks the job running on this thread as one another Mac sent here, so
    it can't be sent on again (and bounce between Macs forever)."""
    _local.passed_on = True
    try:
        yield
    finally:
        _local.passed_on = False


def ask(mac: str, task: str, got_seconds: float = GOT_SECONDS, done_seconds: float = DONE_SECONDS) -> str:
    """Has another Mac do a task and returns what it said. Raises when it
    can't be reached."""
    if not configured():
        raise RuntimeError(
            "Other Macs aren't set up. Run `python -m jarvis.macs <name>` on each Mac first."
        )
    target = name_of(mac)
    if not target:
        raise ValueError("Which Mac? Give its name, like \"old\".")
    if target == me():
        return "That's this Mac, so do it here with your own tools."
    if getattr(_local, "passed_on", False):
        raise RuntimeError("This job came from another Mac, so it can't be passed on again. Do it here.")

    job = uuid.uuid4().hex[:12]
    waiting = {"got": threading.Event(), "done": threading.Event(), "reply": "", "late": False}
    with _lock:
        _pending[job] = waiting
    _publish({"kind": "task", "id": job, "from": me(), "to": target, "task": task})

    if not waiting["got"].wait(got_seconds):
        with _lock:
            # If it turns up after all, its answer still reaches the phone.
            waiting["late"] = True
        names = ", ".join(known())
        hint = f" The Macs I know of are: {names}." if names else ""
        raise RuntimeError(
            f'The "{target}" Mac didn\'t answer. It may be asleep, offline, or not running '
            f"Jarvis, or there's no Mac with that name.{hint}"
        )
    if not waiting["done"].wait(done_seconds):
        with _lock:
            waiting["late"] = True
        return (
            f'The "{target}" Mac got it and is still working on it. Its answer will come to '
            "the user's phone when it's done."
        )
    with _lock:
        _pending.pop(job, None)
    return f'The "{target}" Mac said: {waiting["reply"]}'


class Replies:
    """Sends the answer to a job back to the Mac that asked. Jarvis's phone
    job uses it like it uses PhoneReplies."""

    def __init__(self, job: str, to: str):
        self.job = job
        self.to = to
        self.from_mac = to

    def text(self, message: str) -> None:
        if len(message) > MAX_REPLY:
            message = message[:MAX_REPLY] + "..."
        _publish({"kind": "done", "id": self.job, "from": me(), "to": self.to, "reply": message})

    def file(self, path, message: str) -> None:
        # Files can't go over this topic; they go to the phone instead.
        from . import contact

        try:
            contact.send_file(path, message)
            note = " (The file was sent to the user's phone.)"
        except Exception as error:
            note = f" (The file is saved on the {me()} Mac at {path}; it couldn't go to the phone: {error})"
        self.text(message + note)


# ---- receiving -----------------------------------------------------------------------


def _handle(text: str, on_task, log) -> None:
    try:
        message = json.loads(text)
    except ValueError:
        return
    if not isinstance(message, dict):
        return
    sender = name_of(str(message.get("from") or ""))
    if not sender or sender == me():
        return  # its own messages come back too
    _learn(sender)
    kind = message.get("kind")
    if kind == "hello":
        _publish({"kind": "here", "from": me()})
    elif kind == "task" and name_of(str(message.get("to") or "")) == me():
        job, task = str(message.get("id") or ""), str(message.get("task") or "").strip()
        if not job or not task:
            return
        _publish({"kind": "got", "id": job, "from": me(), "to": sender})
        on_task(task, Replies(job, sender))
    elif kind in ("got", "done") and name_of(str(message.get("to") or "")) == me():
        with _lock:
            waiting = _pending.get(str(message.get("id") or ""))
            if waiting is None:
                return
            if kind == "got":
                waiting["got"].set()
                return
            waiting["reply"] = str(message.get("reply") or "")
            waiting["done"].set()
            late = waiting["late"]
            if late:
                _pending.pop(str(message["id"]), None)
        if late and _on_late:
            _on_late(f'From the {sender} Mac: {waiting["reply"]}')


def start(on_task, on_late=None, log=print) -> None:
    """Listens for jobs from the other Macs. on_task(task, replies) runs one;
    on_late(text) passes on an answer that came after we stopped waiting."""
    global _on_late
    _on_late = on_late
    remote.listen(
        lambda text: _handle(text, on_task, log), log=log, topic=config.ntfy_macs_topic, label="Other Macs"
    )

    def say_hello():
        time.sleep(3)  # let the listener connect first, to hear the replies
        try:
            _publish({"kind": "hello", "from": me()})
        except RuntimeError as error:
            log(f"Other Macs: {error}")

    threading.Thread(target=say_hello, daemon=True).start()


# ---- setup: python -m jarvis.macs <name> [--paste] -------------------------------------


def setup(argv: list[str], clipboard_in=None, clipboard_out=None, out=print) -> int:
    from .setup import save_settings

    names = [a for a in argv if not a.startswith("-")]
    if len(names) != 1 or not name_of(names[0]):
        out("Give this Mac a short name, like:  python -m jarvis.macs main")
        return 1
    name = name_of(names[0])
    if "--paste" in argv:
        topic = (clipboard_in or _paste)().strip()
        if not re.fullmatch(re.escape(TOPIC_PREFIX) + r"[A-Za-z0-9_-]{16,}", topic):
            out("The clipboard doesn't hold the code from the other Mac. Copy it again, then rerun this.")
            return 1
    else:
        topic = config.ntfy_macs_topic or TOPIC_PREFIX + secrets.token_urlsafe(18)
    save_settings({"JARVIS_MAC_NAME": name, "NTFY_MACS_TOPIC": topic})
    out(f'This Mac is now called "{name}".')
    if "--paste" in argv:
        out("Done. Restart Jarvis on both Macs.")
    else:
        (clipboard_out or _copy)(topic)
        out("The shared code is copied to the clipboard. On the other Mac, run:")
        out("    .venv/bin/python -m jarvis.macs old --paste")
        out("(Use your own name instead of old. If the clipboard doesn't carry over between")
        out("your Macs, paste the code into an iMessage to yourself, copy it on the other Mac,")
        out("then run that command. Don't send it anywhere else: it's like a password.)")
    return 0


def _paste() -> str:
    return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout


def _copy(text: str) -> None:
    subprocess.run(["pbcopy"], input=text, text=True, check=True)


if __name__ == "__main__":
    sys.exit(setup(sys.argv[1:]))
