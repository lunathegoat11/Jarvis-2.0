"""Messages from your phone, through ntfy.

Jarvis listens on a second private ntfy topic (NTFY_REPLY_TOPIC). Anything
published there, e.g. by the "Tell Jarvis" Shortcut on an iPhone, is run
as a command, just as if you'd said it at the Mac, and the answer comes
back as an alert on your main topic.

Whoever knows the reply topic can control this Mac through Jarvis, so keep
it as secret as a password. ntfy.sh also keeps messages for a few hours,
so anyone with the topic name could read recent ones.
"""

import json
import threading
import time
import urllib.parse
import urllib.request

from .config import config


def configured() -> bool:
    topic = config.ntfy_reply_topic
    # Listening on the alerts topic would read Jarvis's own alerts back as
    # commands, forever.
    return bool(topic) and topic != config.ntfy_topic


def _url(since: str, topic: str | None = None) -> str:
    server = config.ntfy_server.rstrip("/")
    topic = topic or config.ntfy_reply_topic
    return f"{server}/{topic}/json?since={urllib.parse.quote(since)}"


def _headers() -> dict:
    if config.ntfy_token:
        return {"Authorization": f"Bearer {config.ntfy_token}"}
    return {}


def listen(on_message, log=print, topic: str | None = None, label: str = "Phone messages") -> threading.Thread:
    """Calls on_message(text) for each message sent to the reply topic (or
    another topic), on a background thread, reconnecting whenever the
    connection drops."""
    thread = threading.Thread(
        target=_listen_loop, args=(on_message, log), kwargs={"topic": topic, "label": label}, daemon=True
    )
    thread.start()
    return thread


def _listen_loop(
    on_message, log, stop: threading.Event | None = None, sleep=time.sleep,
    topic: str | None = None, label: str = "Phone messages",
) -> None:
    # Start from now, so messages sent while Jarvis was off (which ntfy keeps
    # for a while) aren't run as stale commands. After that, resume from the
    # last message seen so nothing is missed or run twice across reconnects.
    since = str(int(time.time()))
    seen: set[str] = set()
    delay = 2
    while not (stop and stop.is_set()):
        try:
            request = urllib.request.Request(_url(since, topic), headers=_headers())
            # ntfy sends a keepalive about every 45 seconds, so a longer
            # silence means the connection is dead.
            with urllib.request.urlopen(request, timeout=120) as stream:
                delay = 2
                for line in stream:
                    event = json.loads(line or b"{}")
                    if event.get("event") != "message" or event.get("id") in seen:
                        continue
                    seen.add(event["id"])
                    since = event["id"]
                    text = (event.get("message") or "").strip()
                    if not text:
                        continue
                    try:
                        on_message(text)
                    except Exception as error:
                        log(f"{label}: a message failed: {error}")
                    if stop and stop.is_set():
                        return
        except Exception as error:
            if stop and stop.is_set():
                return
            log(f"{label}: lost the connection to ntfy ({error}); retrying in {delay}s.")
            sleep(delay)
            delay = min(delay * 2, 60)
