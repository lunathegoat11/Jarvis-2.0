"""Jarvis's speaking voice.

Two engines:

- "kokoro": Kokoro, a free open-source AI voice that runs on this computer
  and sounds close to a real person. Needs `pip install kokoro-onnx` and
  downloads its voice files (about 350 MB) the first time.
- "system": the computer's built-in voice (macOS `say`, or pyttsx3
  elsewhere). Nothing to download.

JARVIS_VOICE_ENGINE picks one; by default Kokoro is used when it's
installed. Long replies are spoken sentence by sentence, with the next one
prepared while the current one plays, so speech starts quickly.
"""

import queue
import re
import subprocess
import threading
import urllib.request

from . import prefs
from .config import config

KOKORO_FILES = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin",
}

_kokoro = None
_kokoro_lock = threading.Lock()


def kokoro_installed() -> bool:
    try:
        import kokoro_onnx  # noqa: F401
    except ImportError:
        return False
    return True


KOKORO_NAME = re.compile(r"[a-z]{2}_[a-z]+")


def engine() -> str:
    if config.voice_engine in ("kokoro", "system"):
        return config.voice_engine
    # Kokoro voices are named like "bm_george"; anything else ("Daniel") is a
    # built-in system voice.
    name = prefs.get("voice", config.voice)
    if name and not KOKORO_NAME.fullmatch(name):
        return "system"
    return "kokoro" if kokoro_installed() else "system"


def available_voices() -> list[dict]:
    """Voices the app can offer: Kokoro's if installed, plus the Mac's own."""
    voices = []
    if kokoro_installed():
        accents = {"a": "American", "b": "British"}
        kinds = {"f": "woman", "m": "man"}
        for name in ("bm_george", "bm_daniel", "bm_lewis", "bm_fable", "bf_emma", "bf_alice",
                     "bf_isabella", "bf_lily", "am_michael", "am_adam", "am_eric", "am_liam",
                     "am_onyx", "af_heart", "af_bella", "af_nicole", "af_sarah", "af_sky"):
            label = f"{name[3:].capitalize()} · {accents[name[0]]} {kinds[name[1]]}"
            voices.append({"id": name, "label": label})
    if config.is_mac:
        try:
            listing = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            listing = ""
        for line in listing.splitlines():
            match = re.match(r"^(.+?)\s{2,}(en[_-]\w+)", line)
            if match:
                name = match[1].strip()
                voices.append({"id": name, "label": f"{name} · Mac voice"})
    return voices


EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF\uFE0F\u200D]+"
)


def clean_for_speech(text: str, keep_links: bool = False) -> str:
    """Strips what people don't say out loud: markdown symbols, code, emoji,
    bullet markers and raw web addresses."""
    text = re.sub(r"```.*?```", " (I've left the code out.) ", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", text)  # [label](url) -> label
    if not keep_links:
        text = re.sub(r"https?://\S+|www\.\S+", "the link", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)  # headings
    text = re.sub(r"^\s*(?:[-*+•]|\d+[.)])\s+", "", text, flags=re.MULTILINE)  # list markers
    text = re.sub(r"^\s*>\s?", "", text, flags=re.MULTILINE)  # quotes
    text = re.sub(r"(\*{1,3}|_{2,3}|~~)(\S.*?\S|\S)\1", r"\2", text)  # bold, italics, strike
    text = re.sub(r"(?<!\w)_(\S.*?\S|\S)_(?!\w)", r"\1", text)
    text = re.sub(r"^[ \t]*\|?(?:[ \t]*:?-{3,}:?[ \t]*\|?)+[ \t]*$", "", text, flags=re.MULTILINE)  # table rules
    text = re.sub(r"^[ \t]*\||\|[ \t]*$", "", text, flags=re.MULTILINE)  # table edges
    text = re.sub(r"\s*\|\s*", ", ", text)
    text = re.sub(r"[*#~^<>{}\\]", "", text)
    text = EMOJI.sub("", text)
    # Line breaks become pauses.
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = " ".join(line if line[-1] in ".!?:;,)" else line + "." for line in lines)
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p for p in parts if p]


def _download(name: str, url: str, path) -> None:
    print(f"Downloading Jarvis's voice ({name}), one time only...", flush=True)
    partial = path.with_suffix(path.suffix + ".part")
    urllib.request.urlretrieve(url, partial)
    partial.rename(path)


def load_kokoro():
    """Loads Kokoro, downloading its files the first time. Thread-safe."""
    global _kokoro
    with _kokoro_lock:
        if _kokoro is None:
            from kokoro_onnx import Kokoro

            folder = config.data_dir / "kokoro"
            folder.mkdir(parents=True, exist_ok=True)
            for name, url in KOKORO_FILES.items():
                path = folder / name
                if not path.exists():
                    _download(name, url, path)
            _kokoro = Kokoro(str(folder / "kokoro-v1.0.onnx"), str(folder / "voices-v1.0.bin"))
        return _kokoro


def warm_up() -> None:
    """Loads the voice in the background so the first reply isn't slow."""
    if prefs.get("speak_replies", config.speak_replies) and engine() == "kokoro":
        threading.Thread(target=_warm, daemon=True).start()


def _warm():
    try:
        load_kokoro()
    except Exception as error:
        print(f"Couldn't load the Kokoro voice ({error}); using the built-in voice.")


def _speak_kokoro(text: str) -> None:
    import sounddevice as sd

    kokoro = load_kokoro()
    voice = prefs.get("voice", config.voice) or "bm_george"
    # British voices (bm_, bf_) are spoken with a British accent.
    lang = "en-gb" if voice[:2] in ("bm", "bf") else "en-us"
    speed = float(prefs.get("voice_speed", config.voice_speed))
    chunks: queue.Queue = queue.Queue(maxsize=2)

    def produce():
        try:
            for sentence in split_sentences(text):
                chunks.put(kokoro.create(sentence, voice=voice, speed=speed, lang=lang))
        finally:
            chunks.put(None)

    threading.Thread(target=produce, daemon=True).start()
    while (chunk := chunks.get()) is not None:
        audio, sample_rate = chunk
        sd.play(audio, sample_rate)
        sd.wait()


_pyttsx3_engine = None


def _speak_system(text: str) -> None:
    if config.is_mac:
        command = ["say"]
        name = prefs.get("voice", config.voice)
        speed = float(prefs.get("voice_speed", config.voice_speed))
        if name and not KOKORO_NAME.fullmatch(name):
            command += ["-v", name]
        if speed != 1.0:
            command += ["-r", str(round(175 * speed))]
        subprocess.run([*command, text], check=False)
        return
    global _pyttsx3_engine
    import pyttsx3

    if _pyttsx3_engine is None:
        _pyttsx3_engine = pyttsx3.init()
    _pyttsx3_engine.say(text)
    _pyttsx3_engine.runAndWait()


def speak(text: str) -> None:
    """Says `text` out loud and returns when it's finished."""
    if not prefs.get("speak_replies", config.speak_replies):
        return
    text = clean_for_speech(text)
    if not text:
        return
    if engine() == "kokoro":
        try:
            _speak_kokoro(text)
            return
        except Exception as error:
            print(f"Kokoro voice failed ({error}); using the built-in voice.")
    _speak_system(text)
