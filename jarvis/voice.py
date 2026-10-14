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


def engine() -> str:
    if config.voice_engine in ("kokoro", "system"):
        return config.voice_engine
    # Kokoro voices are named like "bm_george"; anything else ("Daniel") is a
    # built-in system voice.
    if config.voice and not re.fullmatch(r"[a-z]{2}_[a-z]+", config.voice):
        return "system"
    return "kokoro" if kokoro_installed() else "system"


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
    if config.speak_replies and engine() == "kokoro":
        threading.Thread(target=_warm, daemon=True).start()


def _warm():
    try:
        load_kokoro()
    except Exception as error:
        print(f"Couldn't load the Kokoro voice ({error}); using the built-in voice.")


def _speak_kokoro(text: str) -> None:
    import sounddevice as sd

    kokoro = load_kokoro()
    voice = config.voice or "bm_george"
    # British voices (bm_, bf_) are spoken with a British accent.
    lang = "en-gb" if voice[:2] in ("bm", "bf") else "en-us"
    chunks: queue.Queue = queue.Queue(maxsize=2)

    def produce():
        try:
            for sentence in split_sentences(text):
                chunks.put(kokoro.create(sentence, voice=voice, speed=config.voice_speed, lang=lang))
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
        if config.voice:
            command += ["-v", config.voice]
        if config.voice_speed != 1.0:
            command += ["-r", str(round(175 * config.voice_speed))]
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
    if not config.speak_replies or not text:
        return
    if engine() == "kokoro":
        try:
            _speak_kokoro(text)
            return
        except Exception as error:
            print(f"Kokoro voice failed ({error}); using the built-in voice.")
    _speak_system(text)
