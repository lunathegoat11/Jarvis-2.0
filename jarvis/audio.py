"""Microphone recording and local speech-to-text."""

import threading

import numpy as np

from .config import config


def pick_device(devices, choice: str):
    """The index of the microphone to record from, or None for the system's.

    "auto" prefers the computer's own mic, because AirPods and other Bluetooth
    headsets often hand over silence (in the case, connected to a phone) and
    drop to call-quality sound while their mic is in use. Any other word picks
    the first input whose name contains it, e.g. "airpods" or "yeti".
    """
    choice = (choice or "").strip().lower()
    if choice in ("", "default", "system"):
        return None
    wanted = ["macbook", "built-in"] if choice == "auto" else [choice]
    inputs = [(i, d) for i, d in enumerate(devices) if d["max_input_channels"] > 0]
    for word in wanted:
        for index, device in inputs:
            if word in device["name"].lower():
                return index
    return None


class Recorder:
    """Records from the microphone between start() and stop()."""

    def __init__(self):
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._rate = config.sample_rate
        self._lock = threading.Lock()
        # Loudness of the latest audio chunk, 0 to 1, for the notch waveform.
        self.level = 0.0

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import sounddevice as sd

        self._chunks = []
        try:
            self._open(sd, pick_device(sd.query_devices(), config.mic))
        except sd.PortAudioError:
            # The device list is read once, so it goes stale when inputs change
            # (AirPods connecting, another mic picked in Settings). Re-read it
            # and try again, then fall back to whatever the system is using.
            sd._terminate()
            sd._initialize()
            try:
                self._open(sd, pick_device(sd.query_devices(), config.mic))
            except sd.PortAudioError:
                self._open(sd, None)

    def _open(self, sd, device) -> None:
        # Whisper wants 16 kHz, but some mics (Bluetooth ones especially)
        # refuse it, so fall back to the mic's own rate and convert in stop().
        rates = [config.sample_rate]
        try:
            native = int(sd.query_devices(device, "input")["default_samplerate"])
            if native not in rates:
                rates.append(native)
        except Exception:
            pass
        error = None
        for rate in rates:
            stream = None
            try:
                stream = sd.InputStream(
                    device=device,
                    samplerate=rate,
                    channels=1,
                    dtype="float32",
                    callback=self._on_audio,
                )
                stream.start()
            except sd.PortAudioError as problem:
                error = problem
                if stream is not None:
                    stream.close()
                continue
            self._stream, self._rate = stream, rate
            return
        raise error

    def _on_audio(self, indata, frames, time, status) -> None:
        with self._lock:
            self._chunks.append(indata.copy())
        rms = float(np.sqrt(np.mean(np.square(indata))))
        self.level = min(1.0, rms * 12)

    def stop(self) -> np.ndarray:
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self.level = 0.0
        with self._lock:
            if not self._chunks:
                return np.zeros(0, dtype=np.float32)
            audio = np.concatenate(self._chunks).flatten()
        if self._rate != config.sample_rate and audio.size:
            # Convert to the 16 kHz Whisper expects.
            length = int(round(audio.size * config.sample_rate / self._rate))
            audio = np.interp(
                np.linspace(0, audio.size - 1, length), np.arange(audio.size), audio
            ).astype(np.float32)
        return audio


class Transcriber:
    """Runs Whisper on this computer, so audio never leaves it."""

    def __init__(self):
        self._model = None
        # An interrupted request can still be transcribing when the next one
        # starts; Whisper runs one at a time.
        self._lock = threading.Lock()

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(config.whisper_model, device="auto", compute_type="int8")
        return self._model

    def warm_up(self) -> None:
        """Loads Whisper in the background so the first request isn't slow."""
        threading.Thread(target=self._load, daemon=True).start()

    def transcribe(self, audio: np.ndarray, vocabulary: str = "") -> str:
        # Anything shorter than a quarter second is a stray key press.
        if audio.size < config.sample_rate // 4:
            return ""
        # Greedy decoding (beam_size=1) is several times faster than the
        # default beam search and barely less accurate for short commands.
        with self._lock:
            segments, _ = self._load().transcribe(
                audio,
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
                # Names and terms from your dictionary, so Whisper spells them right.
                initial_prompt=f"Words that may come up: {vocabulary}." if vocabulary else None,
            )
            return " ".join(s.text.strip() for s in segments).strip()
