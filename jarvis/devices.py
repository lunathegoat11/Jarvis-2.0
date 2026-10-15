"""TVs, speakers and the smart home.

Found automatically on your Wi-Fi:
- Chromecast, Google TV and Nest speakers (pychromecast)
- Sonos speakers (soco)
- Roku TVs and sticks (Roku's own network remote; nothing to install)

Through Home Assistant, if you use it: everything it knows about, including
Alexa devices, lights, plugs and most other TVs. Jarvis passes the sentence
to Home Assistant's Assist, which works out what to do.
"""

import json
import re
import socket
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

from .config import config

# Roku app IDs for the common channels.
ROKU_APPS = {
    "youtube": 837, "netflix": 12, "hulu": 2285, "prime video": 13, "amazon prime": 13,
    "disney+": 291097, "disney plus": 291097, "spotify": 22297, "max": 61322, "hbo max": 61322,
    "apple tv": 551012, "peacock": 593099, "paramount+": 31440, "plex": 13535, "twitch": 50539,
}

ROKU_KEYS = {
    "play": "Play", "pause": "Play", "play_pause": "Play", "home": "Home", "back": "Back",
    "select": "Select", "up": "Up", "down": "Down", "left": "Left", "right": "Right",
    "rewind": "Rev", "forward": "Fwd", "volume_up": "VolumeUp", "volume_down": "VolumeDown",
    "mute": "VolumeMute", "unmute": "VolumeMute", "power_off": "PowerOff", "power_on": "PowerOn",
}

ACTIONS = [
    "play", "pause", "stop", "next", "previous", "volume_up", "volume_down",
    "set_volume", "mute", "unmute", "power_on", "power_off", "home", "back",
]


@dataclass
class Device:
    name: str
    kind: str  # "chromecast", "sonos" or "roku"
    handle: object = field(repr=False, default=None)  # library object, or Roku's base URL


# ---- discovery --------------------------------------------------------------

_cache: list[Device] = []
_cached_at = 0.0
_lock = threading.Lock()
CACHE_SECONDS = 300


def parse_ssdp(response: str) -> str | None:
    """The LOCATION header from an SSDP reply, e.g. http://192.168.1.20:8060/."""
    match = re.search(r"^location:\s*(\S+)", response, re.IGNORECASE | re.MULTILINE)
    return match[1].strip() if match else None


def _find_rokus(timeout: float = 2.0) -> list[Device]:
    request = (
        "M-SEARCH * HTTP/1.1\r\nHost: 239.255.255.250:1900\r\n"
        'Man: "ssdp:discover"\r\nST: roku:ecp\r\nMX: 1\r\n\r\n'
    )
    found: dict[str, Device] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.settimeout(timeout)
    try:
        sock.sendto(request.encode(), ("239.255.255.250", 1900))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                data, _ = sock.recvfrom(4096)
            except socket.timeout:
                break
            base = parse_ssdp(data.decode(errors="replace"))
            if base and base not in found:
                found[base] = Device(_roku_name(base), "roku", base.rstrip("/"))
    finally:
        sock.close()
    return list(found.values())


def _roku_name(base: str) -> str:
    try:
        with urllib.request.urlopen(base.rstrip("/") + "/query/device-info", timeout=2) as reply:
            info = reply.read().decode(errors="replace")
    except OSError:
        return "Roku"
    for tag in ("user-device-name", "friendly-device-name", "default-device-name"):
        match = re.search(rf"<{tag}>([^<]+)</{tag}>", info)
        if match:
            return match[1].strip()
    return "Roku"


def _find_chromecasts(timeout: float = 4.0) -> list[Device]:
    try:
        import pychromecast
    except ImportError:
        return []
    casts, browser = pychromecast.get_chromecasts(timeout=timeout)
    try:
        browser.stop_discovery()
    except Exception:
        pass
    devices = []
    for cast in casts:
        info = getattr(cast, "cast_info", None)
        name = getattr(info, "friendly_name", None) or getattr(cast, "name", "Chromecast")
        devices.append(Device(name, "chromecast", cast))
    return devices


def _find_sonos(timeout: float = 3.0) -> list[Device]:
    try:
        import soco
    except ImportError:
        return []
    speakers = soco.discover(timeout=int(timeout)) or set()
    return [Device(s.player_name, "sonos", s) for s in speakers]


def discover(refresh: bool = False) -> list[Device]:
    """Everything on the network, looked for at once and remembered for a few minutes."""
    global _cache, _cached_at
    with _lock:
        if _cache and not refresh and time.monotonic() - _cached_at < CACHE_SECONDS:
            return _cache
        results: list[list[Device]] = [[], [], []]

        def run(index, finder):
            try:
                results[index] = finder()
            except Exception as error:
                print(f"Device search ({finder.__name__}) failed: {error}")

        threads = [
            threading.Thread(target=run, args=(i, f), daemon=True)
            for i, f in enumerate((_find_chromecasts, _find_sonos, _find_rokus))
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(8)
        _cache = [d for group in results for d in group]
        _cached_at = time.monotonic()
        return _cache


def find(name: str, devices: list[Device]) -> Device:
    """The device whose name best matches what the user said."""
    wanted = re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()
    wanted = re.sub(r"^(the|my) ", "", wanted)
    if not devices:
        raise RuntimeError("I couldn't find any TVs or speakers on your Wi-Fi.")
    for device in devices:
        if device.name.lower() == wanted:
            return device
    for device in devices:
        lowered = device.name.lower()
        if wanted and (wanted in lowered or lowered in wanted):
            return device
    words = set(wanted.split())
    best = max(devices, key=lambda d: len(words & set(d.name.lower().split())))
    if words & set(best.name.lower().split()):
        return best
    if len(devices) == 1 and wanted in ("", "tv", "speaker", "the tv", "the speaker"):
        return devices[0]
    names = ", ".join(d.name for d in devices)
    raise RuntimeError(f"No device called {name!r}. I can see: {names}.")


# ---- control -----------------------------------------------------------------


def _roku(device: Device, path: str) -> None:
    request = urllib.request.Request(device.handle + path, data=b"", method="POST")
    with urllib.request.urlopen(request, timeout=4):
        pass


def control(device: Device, action: str, level: int = 0) -> str:
    if action not in ACTIONS:
        raise ValueError(f"Unknown action: {action}")
    if device.kind == "roku":
        if action == "set_volume":
            raise RuntimeError("Rokus can only turn the volume up or down, not to a number.")
        if action in ("next", "previous", "stop"):
            action = {"next": "forward", "previous": "rewind", "stop": "back"}[action]
        _roku(device, "/keypress/" + ROKU_KEYS[action])
    elif device.kind == "chromecast":
        cast = device.handle
        cast.wait(timeout=10)
        media = cast.media_controller
        if action == "play":
            media.play()
        elif action == "pause":
            media.pause()
        elif action == "stop":
            media.stop()
        elif action == "next":
            media.queue_next()
        elif action == "previous":
            media.queue_prev()
        elif action == "volume_up":
            cast.volume_up(0.1)
        elif action == "volume_down":
            cast.volume_down(0.1)
        elif action == "set_volume":
            cast.set_volume(max(0, min(100, level)) / 100)
        elif action in ("mute", "unmute"):
            cast.set_volume_muted(action == "mute")
        elif action == "power_off":
            cast.quit_app()
        else:
            raise RuntimeError(f"Chromecasts can't do {action.replace('_', ' ')}.")
    elif device.kind == "sonos":
        speaker = device.handle
        leader = speaker.group.coordinator if speaker.group else speaker
        if action == "play":
            leader.play()
        elif action in ("pause", "power_off"):
            leader.pause()
        elif action == "stop":
            leader.stop()
        elif action == "next":
            leader.next()
        elif action == "previous":
            leader.previous()
        elif action == "volume_up":
            speaker.volume = min(100, speaker.volume + 8)
        elif action == "volume_down":
            speaker.volume = max(0, speaker.volume - 8)
        elif action == "set_volume":
            speaker.volume = max(0, min(100, level))
        elif action in ("mute", "unmute"):
            speaker.mute = action == "mute"
        else:
            raise RuntimeError(f"Sonos speakers can't do {action.replace('_', ' ')}.")
    return f"Done: {action.replace('_', ' ')} on {device.name}."


def open_app(device: Device, app: str, search: str = "") -> str:
    """Opens a streaming app on a Roku, optionally searching inside it."""
    if device.kind != "roku":
        raise RuntimeError(
            "I can only open apps on Roku TVs. For other TVs, connect them through Home Assistant."
        )
    if search:
        query = urllib.parse.urlencode({"keyword": search, "launch": "true"})
        _roku(device, "/search/browse?" + query)
        return f"Searching for {search} on {device.name}."
    app_id = ROKU_APPS.get(app.lower().strip())
    if app_id is None:
        raise RuntimeError(f"I don't know the Roku app {app!r}. I know: {', '.join(ROKU_APPS)}.")
    _roku(device, f"/launch/{app_id}")
    return f"Opening {app} on {device.name}."


# ---- Home Assistant ---------------------------------------------------------


def home_assistant_configured() -> bool:
    return bool(config.home_assistant_url and config.home_assistant_token)


def _ha_request(path: str, body: dict | None = None) -> dict:
    url = config.home_assistant_url.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        method="POST" if body is not None else "GET",
        headers={
            "Authorization": f"Bearer {config.home_assistant_token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as reply:
        return json.loads(reply.read() or b"{}")


def home_command(text: str) -> str:
    """Hands a sentence ("turn off the kitchen lights") to Home Assistant's Assist."""
    if not home_assistant_configured():
        raise RuntimeError(
            "Home Assistant isn't set up. Add HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN to .env."
        )
    reply = _ha_request("/api/conversation/process", {"text": text, "language": "en"})
    speech = reply.get("response", {}).get("speech", {}).get("plain", {}).get("speech", "")
    return speech or "Home Assistant did that."


def alexa_announce(message: str, target: str = "") -> str:
    """Has an Echo speak a message, via Home Assistant's Alexa Media Player."""
    if not home_assistant_configured():
        raise RuntimeError(
            "Alexa works through Home Assistant with the Alexa Media Player add-on. "
            "Add HOME_ASSISTANT_URL and HOME_ASSISTANT_TOKEN to .env once that's set up."
        )
    # Alexa Media Player adds notify.alexa_media (every Echo) and
    # notify.alexa_media_<device name> for each one.
    service = "alexa_media"
    if target:
        service += "_" + re.sub(r"[^a-z0-9]+", "_", target.lower()).strip("_")
    _ha_request(f"/api/services/notify/{service}", {"message": message, "data": {"type": "announce"}})
    return f"Announced on {target or 'your Echo devices'}."


def summary(devices: list[Device]) -> str:
    if not devices:
        found = "No TVs or speakers found on your Wi-Fi."
    else:
        kinds = {"chromecast": "Chromecast / Google TV", "sonos": "Sonos", "roku": "Roku"}
        found = "\n".join(f"{d.name} ({kinds[d.kind]})" for d in devices)
    if home_assistant_configured():
        found += "\nHome Assistant is connected, for lights, Alexa and anything else it controls."
    return found
