"""Things Jarvis does on your computer: paste text, take screenshots, speak, open things."""

import base64
import io
import subprocess
import time
import webbrowser

from .config import config


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
    keyboard = Controller()
    modifier = Key.cmd if config.is_mac else Key.ctrl
    with keyboard.pressed(modifier):
        keyboard.press("v")
        keyboard.release("v")

    # Give the target app time to read the clipboard before we put it back.
    time.sleep(0.3)
    if previous is not None:
        pyperclip.copy(previous)


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


_tts_engine = None


def speak(text: str) -> None:
    if not config.speak_replies or not text:
        return
    if config.is_mac:
        # macOS's own voice sounds better than pyttsx3 and works off the main thread.
        subprocess.run(["say", text], check=False)
        return
    global _tts_engine
    import pyttsx3

    if _tts_engine is None:
        _tts_engine = pyttsx3.init()
    _tts_engine.say(text)
    _tts_engine.runAndWait()


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


def notify(title: str, message: str) -> None:
    """Shows a desktop notification, falling back to the terminal."""
    try:
        from plyer import notification

        notification.notify(title=title, message=message[:256], app_name="Jarvis")
    except Exception:
        pass
    print(f"[{title}] {message}")
