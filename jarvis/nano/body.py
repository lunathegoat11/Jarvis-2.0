"""Talking to the robot's body server (robot/body_server.py) over Wi-Fi."""

import json
import time
import urllib.error
import urllib.request

import numpy as np

from ..config import config

FRAME_SAMPLES = 1280  # 80 ms at 16 kHz, what the wake-word detector wants


class Body:
    def __init__(self, url: str | None = None, token: str | None = None):
        self.url = (url or config.nano_robot).rstrip("/")
        self.token = config.nano_token if token is None else token

    def _request(self, method: str, path: str, data: bytes | None = None,
                 content_type: str = "application/json", timeout: float = 15):
        request = urllib.request.Request(
            self.url + path, data=data, method=method,
            headers={"X-Token": self.token, "Content-Type": content_type},
        )
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            if error.code == 401:
                raise RuntimeError(
                    "The robot refused the token. Copy JARVIS_NANO_TOKEN from the robot's "
                    "setup into ~/.jarvis-nano/.env."
                ) from None
            raise RuntimeError(f"The robot said: HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise RuntimeError(
                f"Can't reach the robot at {self.url} ({reason}). Is it switched on and on "
                "the same Wi-Fi?"
            ) from None

    def _post(self, path: str, body: dict | None = None, timeout: float = 15) -> dict:
        data = json.dumps(body or {}).encode()
        with self._request("POST", path, data, timeout=timeout) as reply:
            return json.loads(reply.read() or b"{}")

    # ---- moving ---------------------------------------------------------------

    def drive(self, left: float, right: float, seconds: float) -> None:
        """Runs the wheels for a while, then waits for them to stop."""
        seconds = max(0.0, min(3.0, seconds))
        self._post("/drive", {"left": left, "right": right, "seconds": seconds})
        time.sleep(seconds + 0.15)

    def stop(self) -> None:
        self._post("/stop")

    def claw(self, position: float) -> None:
        self._post("/claw", {"position": position})

    def claw_position(self) -> float | None:
        with self._request("GET", "/claw") as reply:
            return json.loads(reply.read()).get("position")

    def eyes(self, expression: str = "idle", color: tuple[int, int, int] | None = None,
             look: float = 0.0, seconds: float = 0.0) -> None:
        body = {"expression": expression, "look": look, "seconds": seconds}
        if color:
            body.update(r=color[0], g=color[1], b=color[2])
        self._post("/eyes", body)

    def mood(self, expression: str) -> None:
        """Eyes for what Jarvis is doing; never lets a hiccup stop the talk."""
        try:
            self.eyes(expression)
        except RuntimeError:
            pass

    # ---- senses ---------------------------------------------------------------

    def photo(self) -> bytes:
        with self._request("GET", "/photo", timeout=20) as reply:
            return reply.read()

    def say(self, wav: bytes) -> None:
        """Plays audio on the robot; returns when it has finished."""
        if wav:
            with self._request("POST", "/say", wav, "audio/wav", timeout=120) as reply:
                reply.read()

    def stop_speaking(self) -> None:
        try:
            self._post("/stop_speaking", timeout=5)
        except RuntimeError:
            pass

    def mic_frames(self, log=print, sleep=time.sleep):
        """The robot's microphone as 80 ms frames of 16-bit samples, forever,
        reconnecting whenever the stream drops."""
        delay = 1
        while True:
            try:
                with self._request("GET", "/mic", timeout=30) as stream:
                    delay = 1
                    pending = b""
                    while chunk := stream.read(FRAME_SAMPLES * 2):
                        pending += chunk
                        while len(pending) >= FRAME_SAMPLES * 2:
                            frame, pending = pending[: FRAME_SAMPLES * 2], pending[FRAME_SAMPLES * 2:]
                            yield np.frombuffer(frame, dtype="<i2")
            except RuntimeError as error:
                log(f"Robot microphone: {error}")
            log(f"Robot microphone: reconnecting in {delay}s.")
            sleep(delay)
            delay = min(delay * 2, 30)
