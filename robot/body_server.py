"""Jarvis Nano's body: a small web server on the robot's Raspberry Pi.

Jarvis Nano (running on a computer, see jarvis/nano) calls it over Wi-Fi to
drive, work the claw, change the eyes, take photos, hear through the robot's
microphone and talk through its speaker. Built for the Jarvis Mini build:
Pi Zero 2 W, Adafruit Crickit HAT, two DC motors, a Pololu gripper on Servo 1
(position feedback on Signal 1), two 12-LED NeoPixel rings as eyes, a Pi
Camera Module 3, a USB microphone and the Crickit's speaker.

Every request except /health needs the X-Token header to match BOT_TOKEN.
Keep it on your home network: there's no encryption.

Run it with:  BOT_TOKEN=... uvicorn body_server:app --host 0.0.0.0 --port 8080
"""

import io
import math
import os
import re
import subprocess
import tempfile
import threading
import time

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

TOKEN = os.environ.get("BOT_TOKEN", "")
# The longest a single drive command may run. Jarvis sends short moves and
# looks again between them; this is the backstop if it never sends a stop.
MAX_DRIVE_SECONDS = 3.0
PIXELS_PER_EYE = 12
# Which pixel sits at the top of each ring, depending on how they're glued in.
EYE_TOP = int(os.environ.get("EYE_TOP_PIXEL", "0"))
# Claw servo pulse range; nudge by 50 if it doesn't fully open or close.
CLAW_MIN_PULSE = int(os.environ.get("CLAW_MIN_PULSE", "500"))
CLAW_MAX_PULSE = int(os.environ.get("CLAW_MAX_PULSE", "2400"))
SAMPLE_RATE = 16000


# ---- the hardware -----------------------------------------------------------------


class Hardware:
    """The Crickit's motors, claw and eyes, the camera, mic and speaker.
    Everything is set up on first use, so a missing part only breaks the
    endpoints that need it."""

    def __init__(self):
        self._crickit = None
        self._camera = None
        self._lock = threading.Lock()

    @property
    def crickit(self):
        if self._crickit is None:
            from adafruit_crickit import crickit

            crickit.servo_1.set_pulse_width_range(CLAW_MIN_PULSE, CLAW_MAX_PULSE)
            crickit.init_neopixel(PIXELS_PER_EYE * 2, auto_write=False)
            self._crickit = crickit
        return self._crickit

    def wheels(self, left: float, right: float) -> None:
        self.crickit.dc_motor_1.throttle = left
        self.crickit.dc_motor_2.throttle = right

    def claw(self, position: float) -> None:
        self.crickit.servo_1.angle = 180 * position

    def claw_feedback(self) -> float | None:
        """Where the claw really is, 0 open to 1 closed, from the gripper's
        feedback wire on Signal 1 (0.5 V open, 2.2 V closed), or None."""
        try:
            raw = self.crickit.seesaw.analog_read(self.crickit.SIGNAL1)
        except Exception:
            return None
        volts = raw / 1023 * 3.3
        if volts < 0.2:  # the feedback wire isn't connected
            return None
        return max(0.0, min(1.0, (volts - 0.5) / (2.2 - 0.5)))

    def pixels(self, colors: list[tuple[int, int, int]]) -> None:
        strip = self.crickit.neopixel
        for i, color in enumerate(colors):
            strip[i] = color
        strip.show()

    def photo(self) -> bytes:
        with self._lock:
            if self._camera is None:
                from picamera2 import Picamera2

                camera = Picamera2()
                camera.configure(camera.create_still_configuration(main={"size": (1024, 768)}))
                camera.start()
                time.sleep(1)  # let exposure settle
                self._camera = camera
            buffer = io.BytesIO()
            self._camera.capture_file(buffer, format="jpeg")
            return buffer.getvalue()


def find_mic() -> str:
    """The USB microphone's ALSA device (the speaker owns the default)."""
    if os.environ.get("MIC_DEVICE"):
        return os.environ["MIC_DEVICE"]
    listing = subprocess.run(["arecord", "-l"], capture_output=True, text=True).stdout
    for line in listing.splitlines():
        match = re.match(r"card (\d+): .*USB", line, re.IGNORECASE)
        if match:
            return f"plughw:{match.group(1)},0"
    return "default"


# ---- the eyes ---------------------------------------------------------------------


MOOD_COLORS = {
    "idle": (0, 60, 160),
    "listening": (0, 140, 255),
    "thinking": (150, 60, 255),
    "speaking": (0, 200, 200),
    "happy": (255, 170, 0),
    "sad": (40, 60, 200),
    "angry": (255, 20, 0),
    "surprised": (255, 255, 255),
    "sleepy": (30, 30, 80),
}


def _ring(lit, color) -> list[tuple[int, int, int]]:
    """One eye: pixel i (counted from the top, clockwise) lit by lit(angle)."""
    out = [(0, 0, 0)] * PIXELS_PER_EYE
    for i in range(PIXELS_PER_EYE):
        angle = 2 * math.pi * i / PIXELS_PER_EYE  # 0 at the top, clockwise
        level = max(0.0, min(1.0, lit(angle)))
        out[(i + EYE_TOP) % PIXELS_PER_EYE] = tuple(int(c * level) for c in color)
    return out


def eye_frame(expression: str, color, t: float, look: float = 0.0) -> list[tuple[int, int, int]]:
    """Both rings for an expression at time t (seconds), for animating.
    look is -1 (glancing left) to 1 (glancing right)."""
    if expression == "blink":
        return [(0, 0, 0)] * (PIXELS_PER_EYE * 2)
    if expression == "thinking":
        spot = (t * 2 * math.pi * 0.8) % (2 * math.pi)  # a light going round
        lit = lambda a: 1 - min(abs(a - spot), 2 * math.pi - abs(a - spot)) / 1.2  # noqa: E731
    elif expression == "speaking":
        pulse = 0.55 + 0.45 * abs(math.sin(t * 7))
        lit = lambda a: pulse  # noqa: E731
    elif expression == "listening":
        lit = lambda a: 0.6 + 0.4 * math.sin(t * 3)  # noqa: E731
    elif expression == "happy":  # an upward curve: the top half
        lit = lambda a: 1.0 if math.cos(a) > -0.1 else 0.0  # noqa: E731
    elif expression == "sad":  # the bottom half
        lit = lambda a: 1.0 if math.cos(a) < 0.1 else 0.0  # noqa: E731
    elif expression == "angry":  # inner top corners, slanting down to the middle
        lit = lambda a: 1.0 if math.cos(a) > 0.3 else 0.25  # noqa: E731
    elif expression == "sleepy":  # half-closed lids
        lit = lambda a: 0.6 if math.cos(a) < -0.2 else 0.0  # noqa: E731
    else:  # idle, surprised and plain colours: a full ring
        lit = lambda a: 1.0  # noqa: E731
    if look:
        base = lit
        # Brighter on the side being looked towards (sin is + on the right).
        lit = lambda a: base(a) * (0.35 + 0.65 * max(0.0, math.sin(a) * look + 0.4))  # noqa: E731
    return _ring(lit, color) + _ring(lit, color)


class Eyes:
    """Runs the eye animation in the background and blinks now and then."""

    def __init__(self, hardware: Hardware):
        self.hardware = hardware
        self.expression = "idle"
        self.color = MOOD_COLORS["idle"]
        self.look = 0.0
        self._until = 0.0  # a one-off expression (e.g. happy) wears off then
        threading.Thread(target=self._animate, daemon=True).start()

    def set(self, expression: str, color=None, look: float = 0.0, seconds: float = 0.0) -> None:
        self.expression = expression
        self.color = color or MOOD_COLORS.get(expression, self.color)
        self.look = max(-1.0, min(1.0, look))
        self._until = time.monotonic() + seconds if seconds else 0.0

    def _animate(self) -> None:
        next_blink = time.monotonic() + 4
        while True:
            now = time.monotonic()
            if self._until and now > self._until:
                self.set("idle")
            expression = self.expression
            if expression in ("idle", "listening") and now >= next_blink:
                expression = "blink"
                if now >= next_blink + 0.15:
                    next_blink = now + 3 + 4 * (math.sin(now) + 1) / 2
            try:
                self.hardware.pixels(eye_frame(expression, self.color, now, self.look))
            except Exception:
                time.sleep(2)  # eyes not wired yet; don't spin
            time.sleep(0.05)


# ---- the server ---------------------------------------------------------------------


class DriveCommand(BaseModel):
    left: float  # -1 full reverse .. 1 full forward
    right: float
    seconds: float = 0.5


class ClawCommand(BaseModel):
    position: float  # 0 open .. 1 closed


class EyesCommand(BaseModel):
    expression: str = "idle"
    r: int | None = None
    g: int | None = None
    b: int | None = None
    look: float = 0.0
    seconds: float = 0.0  # how long before going back to idle; 0 keeps it


def create_app(hardware: Hardware | None = None, token: str | None = None) -> FastAPI:
    hardware = hardware or Hardware()
    token = TOKEN if token is None else token
    app = FastAPI(title="Jarvis Nano body")
    eyes = Eyes(hardware)
    state = {"stop_at": 0.0, "player": None, "recorder": None}
    lock = threading.Lock()

    def check(x_token: str | None) -> None:
        if not token or x_token != token:
            raise HTTPException(status_code=401, detail="Wrong or missing X-Token")

    def watchdog() -> None:
        # Stops the wheels when a drive command's time is up, even if Jarvis
        # never says stop (lost Wi-Fi, a crash...).
        while True:
            with lock:
                if state["stop_at"] and time.time() > state["stop_at"]:
                    hardware.wheels(0, 0)
                    state["stop_at"] = 0.0
            time.sleep(0.05)

    threading.Thread(target=watchdog, daemon=True).start()

    def stop_speaking() -> None:
        player = state["player"]
        if player is not None and player.poll() is None:
            player.terminate()

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.post("/drive")
    def drive(cmd: DriveCommand, x_token: str | None = Header(default=None)):
        check(x_token)
        with lock:
            hardware.wheels(max(-1.0, min(1.0, cmd.left)), max(-1.0, min(1.0, cmd.right)))
            state["stop_at"] = time.time() + max(0.0, min(cmd.seconds, MAX_DRIVE_SECONDS))
        return {"ok": True}

    @app.post("/stop")
    def stop(x_token: str | None = Header(default=None)):
        check(x_token)
        with lock:
            hardware.wheels(0, 0)
            state["stop_at"] = 0.0
        stop_speaking()
        return {"ok": True}

    @app.post("/claw")
    def claw(cmd: ClawCommand, x_token: str | None = Header(default=None)):
        check(x_token)
        hardware.claw(max(0.0, min(1.0, cmd.position)))
        return {"ok": True}

    @app.get("/claw")
    def claw_position(x_token: str | None = Header(default=None)):
        check(x_token)
        return {"position": hardware.claw_feedback()}

    @app.post("/eyes")
    def set_eyes(cmd: EyesCommand, x_token: str | None = Header(default=None)):
        check(x_token)
        color = (cmd.r, cmd.g, cmd.b) if None not in (cmd.r, cmd.g, cmd.b) else None
        if color:
            color = tuple(max(0, min(255, c)) for c in color)
        eyes.set(cmd.expression, color, cmd.look, cmd.seconds)
        return {"ok": True}

    @app.get("/photo")
    def photo(x_token: str | None = Header(default=None)):
        check(x_token)
        return Response(hardware.photo(), media_type="image/jpeg")

    @app.get("/mic")
    def mic(x_token: str | None = Header(default=None)):
        """The microphone as a live stream of 16 kHz mono 16-bit samples.
        One listener at a time: a new one takes over."""
        check(x_token)
        old = state["recorder"]
        if old is not None and old.poll() is None:
            old.terminate()
        recorder = subprocess.Popen(
            ["arecord", "-q", "-D", find_mic(), "-f", "S16_LE", "-r", str(SAMPLE_RATE),
             "-c", "1", "-t", "raw"],
            stdout=subprocess.PIPE,
        )
        state["recorder"] = recorder

        def chunks():
            try:
                while chunk := recorder.stdout.read(2560):  # 80 ms
                    yield chunk
            finally:
                if recorder.poll() is None:
                    recorder.terminate()

        return StreamingResponse(chunks(), media_type="application/octet-stream")

    @app.post("/say")
    async def say(request: Request, x_token: str | None = Header(default=None)):
        """Plays a WAV through the speaker and returns when it's finished
        (or stopped), so sentences sent one after another play in order."""
        check(x_token)
        audio = await request.body()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as file:
            file.write(audio)
        try:
            stop_speaking()
            player = subprocess.Popen(["aplay", "-q", file.name])
            state["player"] = player
            await _wait(player)
        finally:
            os.unlink(file.name)
        return {"ok": True}

    @app.post("/stop_speaking")
    def stop_talking(x_token: str | None = Header(default=None)):
        check(x_token)
        stop_speaking()
        return {"ok": True}

    return app


async def _wait(process) -> None:
    import asyncio

    while process.poll() is None:
        await asyncio.sleep(0.05)


if __name__ != "__main__" and os.environ.get("JARVIS_BODY_NO_APP") != "1":
    app = create_app()
