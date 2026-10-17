"""Hearing "Hey Jarvis", and hearing when you've finished talking.

The wake word uses openWakeWord's ready-made "hey jarvis" model, which runs
on the computer (not the robot) from the robot's microphone stream. Its
pre-trained models are licensed for non-commercial use only.
"""

import numpy as np

from ..config import config


class WakeWord:
    def __init__(self, threshold: float | None = None):
        from openwakeword.model import Model
        from openwakeword.utils import download_models

        download_models(["hey_jarvis"])  # once; then it's on disk
        self.model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
        self.threshold = config.nano_wake_threshold if threshold is None else threshold

    def heard(self, frame: np.ndarray, speaking: bool = False) -> bool:
        """Whether this 80 ms frame finishes a "Hey Jarvis". While Jarvis is
        talking, it must be surer, so its own voice doesn't set it off."""
        scores = self.model.predict(frame)
        threshold = min(0.95, self.threshold + 0.25) if speaking else self.threshold
        if max(scores.values(), default=0.0) >= threshold:
            self.model.reset()  # don't fire again on the same words
            return True
        return False


class Endpointer:
    """Decides when a spoken request is over, from how loud the audio is
    compared with the room's background noise."""

    FRAME_SECONDS = 0.08

    def __init__(self, silence_after: float = 0.9, no_speech_after: float = 3.0,
                 longest: float = 15.0):
        self.silence_after = silence_after
        self.no_speech_after = no_speech_after
        self.longest = longest
        self.noise = 200.0  # running estimate of the room's level
        self.start()

    @staticmethod
    def level(frame: np.ndarray) -> float:
        return float(np.sqrt(np.mean(frame.astype(np.float32) ** 2))) if len(frame) else 0.0

    def background(self, frame: np.ndarray) -> None:
        """Learns the room's noise from audio heard while nobody's talking."""
        self.noise = 0.95 * self.noise + 0.05 * min(self.level(frame), 3000.0)

    def start(self) -> None:
        self.frames: list[np.ndarray] = []
        self.heard_speech = False
        self.quiet_for = 0.0

    def add(self, frame: np.ndarray) -> bool:
        """Adds a frame; True when the request is over."""
        self.frames.append(frame)
        loud = self.level(frame) > max(3 * self.noise, 400.0)
        if loud:
            self.heard_speech = True
            self.quiet_for = 0.0
        else:
            self.quiet_for += self.FRAME_SECONDS
        elapsed = len(self.frames) * self.FRAME_SECONDS
        if not self.heard_speech:
            return elapsed >= self.no_speech_after
        return self.quiet_for >= self.silence_after or elapsed >= self.longest

    def audio(self) -> np.ndarray:
        """What was said, as floats in -1..1 the way Whisper wants them."""
        if not self.frames or not self.heard_speech:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.frames).astype(np.float32) / 32768.0
