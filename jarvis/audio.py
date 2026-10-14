"""Microphone recording and local speech-to-text."""

import threading

import numpy as np

from .config import config


class Recorder:
    """Records from the default microphone between start() and stop()."""

    def __init__(self):
        self._chunks: list[np.ndarray] = []
        self._stream = None
        self._lock = threading.Lock()
        # Loudness of the latest audio chunk, 0 to 1, for the notch waveform.
        self.level = 0.0

    @property
    def recording(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        import sounddevice as sd

        self._chunks = []
        self._stream = sd.InputStream(
            samplerate=config.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._on_audio,
        )
        self._stream.start()

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
            return np.concatenate(self._chunks).flatten()


class Transcriber:
    """Runs Whisper on this computer, so audio never leaves it."""

    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(config.whisper_model, device="auto", compute_type="int8")
        return self._model

    def warm_up(self) -> None:
        """Loads Whisper in the background so the first request isn't slow."""
        threading.Thread(target=self._load, daemon=True).start()

    def transcribe(self, audio: np.ndarray) -> str:
        # Anything shorter than a quarter second is a stray key press.
        if audio.size < config.sample_rate // 4:
            return ""
        # Greedy decoding (beam_size=1) is several times faster than the
        # default beam search and barely less accurate for short commands.
        segments, _ = self._load().transcribe(
            audio, beam_size=1, vad_filter=True, condition_on_previous_text=False
        )
        return " ".join(s.text.strip() for s in segments).strip()
