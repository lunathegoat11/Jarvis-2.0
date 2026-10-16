"""Things Jarvis does on your computer: paste text, take screenshots, speak, open things."""

import base64
import io
import subprocess
import threading
import time
import urllib.parse
import webbrowser

from .config import config


def _app_loop_running() -> bool:
    try:
        from AppKit import NSApp

        app = NSApp()
        return app is not None and bool(app.isRunning())
    except Exception:
        return False


def on_main_thread(fn, *args):
    """Runs fn on the main thread and waits for it.

    pynput reads the keyboard layout for every key it presses, and recent
    macOS kills the whole app ("trace trap") when that happens off the main
    thread. Requests run on background threads, so key presses come here.
    """
    if (
        not config.is_mac
        or threading.current_thread() is threading.main_thread()
        or not _app_loop_running()
    ):
        return fn(*args)
    from PyObjCTools import AppHelper

    done = threading.Event()
    outcome = {}

    def run():
        try:
            outcome["value"] = fn(*args)
        except BaseException as error:  # handed back to the caller below
            outcome["error"] = error
        finally:
            done.set()

    AppHelper.callAfter(run)
    if not done.wait(15):
        raise RuntimeError("The Mac took too long to press the keys.")
    if "error" in outcome:
        raise outcome["error"]
    return outcome.get("value")


def paste_text(text: str) -> None:
    """Puts text into whatever app has focus, via the clipboard.

    Your previous clipboard contents are restored afterwards.
    """
    import pyperclip
    from pynput.keyboard import Controller, Key

    try:
        previous = pyperclip.paste()
    except pyperclip.PyperclipException:
        previous = None

    pyperclip.copy(text)

    def press_paste():
        keyboard = Controller()
        modifier = Key.cmd if config.is_mac else Key.ctrl
        with keyboard.pressed(modifier):
            keyboard.press("v")
            keyboard.release("v")

    on_main_thread(press_paste)

    # Give the target app time to read the clipboard before we put it back.
    time.sleep(0.3)
    if previous is not None:
        pyperclip.copy(previous)


def selected_text() -> str:
    """The text selected in the app in front, or "" if nothing is selected.

    Copies the selection with Cmd+C and puts your clipboard back afterwards.
    """
    import pyperclip

    try:
        previous = pyperclip.paste()
    except pyperclip.PyperclipException:
        previous = None
    marker = "\u2063jarvis-no-selection\u2063"
    pyperclip.copy(marker)
    press_keys("cmd+c")
    selection = ""
    for _ in range(10):  # give the app up to half a second to copy
        time.sleep(0.05)
        current = pyperclip.paste()
        if current != marker:
            selection = current
            break
    if previous is not None:
        pyperclip.copy(previous)
    return selection


def read_clipboard() -> str:
    import pyperclip

    return pyperclip.paste()


def screenshot_png_base64(max_width: int = 1568) -> str:
    """Captures the main screen, scaled down so it isn't wasteful to send."""
    import mss
    from PIL import Image

    with mss.mss() as sct:
        shot = sct.grab(sct.monitors[1])
        image = Image.frombytes("RGB", shot.size, shot.rgb)

    if image.width > max_width:
        height = round(image.height * max_width / image.width)
        image = image.resize((max_width, height))

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.standard_b64encode(buffer.getvalue()).decode("ascii")


def speak(text: str) -> None:
    from . import voice

    voice.speak(text)


def open_url(url: str) -> None:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)


def open_app(name: str) -> None:
    if config.is_mac:
        subprocess.run(["open", "-a", name], check=True)
    elif config.is_windows:
        # "start" is a cmd builtin; the empty string is the window title.
        subprocess.run(["cmd", "/c", "start", "", name], check=True)
    else:
        subprocess.Popen([name], start_new_session=True)


BROWSERS = {
    "Safari", "Google Chrome", "Arc", "Firefox", "Microsoft Edge", "Brave Browser",
    "Opera", "Vivaldi", "Chromium", "Zen", "Orion", "Dia",
}

SEARCH_SITES = {
    "google": "https://www.google.com/search?q={}",
    "youtube": "https://www.youtube.com/results?search_query={}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={}",
    "amazon": "https://www.amazon.com/s?k={}",
    "maps": "https://www.google.com/maps/search/{}",
    "images": "https://www.google.com/search?tbm=isch&q={}",
}


def search_url(query: str, site: str = "google") -> str:
    template = SEARCH_SITES.get(site, SEARCH_SITES["google"])
    return template.format(urllib.parse.quote_plus(query))


def search_web(query: str, site: str = "google") -> None:
    webbrowser.open(search_url(query, site))


def frontmost_app() -> str:
    """Name of the app in front, or "" if it can't be told."""
    if not config.is_mac:
        return ""
    try:
        from AppKit import NSWorkspace

        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return str(app.localizedName()) if app else ""
    except Exception:
        return ""


# When Jarvis last pressed keys itself, so its own Esc isn't mistaken for the
# user asking it to stop.
last_keys_at = 0.0


def press_keys(combo: str) -> None:
    """Presses a shortcut such as "cmd+t" or "cmd+shift+t" in the app in front.

    On Windows and Linux "cmd" means Ctrl, so the same shortcuts work there.
    """
    from pynput.keyboard import Controller, Key

    names = {
        "cmd": Key.cmd if config.is_mac else Key.ctrl,
        "command": Key.cmd if config.is_mac else Key.ctrl,
        "ctrl": Key.ctrl, "control": Key.ctrl,
        "alt": Key.alt, "option": Key.alt,
        "shift": Key.shift,
        "enter": Key.enter, "return": Key.enter, "esc": Key.esc, "escape": Key.esc,
        "tab": Key.tab, "space": Key.space, "delete": Key.backspace,
        "left": Key.left, "right": Key.right, "up": Key.up, "down": Key.down,
    }
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError("No keys given")
    keys = []
    for part in parts:
        if part in names:
            keys.append(names[part])
        elif len(part) == 1:
            keys.append(part)
        else:
            raise ValueError(f"Unknown key: {part}")

    global last_keys_at
    # Let go of the hotkey that triggered Jarvis before pressing anything.
    time.sleep(0.15)
    last_keys_at = time.monotonic()

    def press():
        keyboard = Controller()
        *held, last = keys
        for key in held:
            keyboard.press(key)
        keyboard.press(last)
        keyboard.release(last)
        for key in reversed(held):
            keyboard.release(key)

    on_main_thread(press)


def browser_shortcut(combo: str) -> str:
    """Sends a shortcut to the browser if one is in front; returns what happened."""
    app = frontmost_app()
    if config.is_mac and app and app not in BROWSERS:
        return f"not_browser:{app}"
    press_keys(combo)
    return app or "browser"


def new_tab(url: str = "") -> None:
    """Opens a new browser tab, with a page in it if given."""
    if url:
        open_url(url)
        return
    if browser_shortcut("cmd+t").startswith("not_browser:"):
        # No browser in front: open the default browser on a fresh page.
        webbrowser.open("https://www.google.com")


MEDIA_KEYS = {"play_pause": "media_play_pause", "next": "media_next", "previous": "media_previous"}


def media(action: str) -> None:
    from pynput.keyboard import Controller, Key

    key = getattr(Key, MEDIA_KEYS[action])

    def press():
        keyboard = Controller()
        keyboard.press(key)
        keyboard.release(key)

    on_main_thread(press)


def set_volume(level: int | None = None, change: int = 0, mute: bool | None = None) -> int:
    """Sets the output volume (0-100) on a Mac and returns the new level."""
    if not config.is_mac:
        raise RuntimeError("Volume control only works on a Mac for now.")
    if mute is not None:
        state = "true" if mute else "false"
        subprocess.run(["osascript", "-e", f"set volume output muted {state}"], check=True)
    if level is None and change:
        current = subprocess.run(
            ["osascript", "-e", "output volume of (get volume settings)"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        level = int(current or 50) + change
    if level is not None:
        level = max(0, min(100, level))
        subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=True)
        return level
    return -1


def notify(title: str, message: str) -> None:
    """Shows a desktop notification, falling back to the terminal."""
    try:
        from plyer import notification

        notification.notify(title=title, message=message[:256], app_name="Jarvis")
    except Exception:
        pass
    print(f"[{title}] {message}")
