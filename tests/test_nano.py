"""Jarvis Nano: the robot's tools, hearing "Hey Jarvis", speaking through the
robot, and the robot's own body server."""

import io
import os
import sys
import threading
import time
import types

import numpy as np
import pytest

from jarvis import brain, habits
from jarvis.config import Config
from jarvis.nano import main as nano_main
from jarvis.nano import tools as nano_tools
from jarvis.nano.body import FRAME_SAMPLES, Body
from jarvis.nano.speech import RobotVoice
from jarvis.nano.wake import Endpointer


class FakeBody:
    def __init__(self):
        self.calls = []
        self.said = []
        self.claw_at = 1.0

    def __getattr__(self, name):
        def record(*args, **kwargs):
            self.calls.append((name, args))
        return record

    def say(self, wav):
        self.said.append(wav)

    def claw_position(self):
        return self.claw_at

    def photo(self):
        from PIL import Image

        buffer = io.BytesIO()
        Image.new("RGB", (1024, 768), (200, 30, 30)).save(buffer, format="JPEG")
        return buffer.getvalue()


# ---- which tools Jarvis Nano gets -----------------------------------------------------


def test_nano_keeps_jarvis_tools_that_work_without_a_screen(monkeypatch):
    from jarvis import contact, devices, mail

    monkeypatch.setattr(mail, "configured", lambda: True)
    monkeypatch.setattr(contact, "configured", lambda: True)
    monkeypatch.setattr(devices, "home_assistant_configured", lambda: False)
    fake = brain.OpenAICompatibleBrain.__new__(brain.OpenAICompatibleBrain)
    names = {t["name"] for t in nano_tools.tools_for(fake)}
    assert {"drive", "turn", "claw", "eyes", "look", "stop"} <= names
    assert {"remember", "learn_lesson", "save_skill", "get_weather", "set_timer",
            "check_email", "text_me"} <= names
    for desktop_only in ("use_screen", "look_at_screen", "add_calendar_event", "check_calendar",
                         "browse_open", "type_text", "press_keys", "open_app", "read_clipboard",
                         "read_messages", "write_document", "web_search"):
        assert desktop_only not in names
    claude = brain.AnthropicBrain.__new__(brain.AnthropicBrain)
    assert "web_search" in {t["name"] for t in nano_tools.tools_for(claude)}


def test_nano_instructions_share_jarvis_memory_and_learning_rules():
    assert nano_tools.NANO_SYSTEM.startswith("You are Jarvis, the same assistant")
    assert "save a lesson with learn_lesson" in nano_tools.NANO_SYSTEM
    assert "Look before" in nano_tools.NANO_SYSTEM


# ---- the robot's tools ---------------------------------------------------------------------


def test_driving_and_turning(monkeypatch):
    monkeypatch.setattr(nano_tools, "config", Config(nano_speed=0.5, nano_turn_seconds=0.8))
    body = FakeBody()
    run = lambda name, args: nano_tools.run_robot_tool(name, args, body, None)  # noqa: E731
    assert run("drive", {"direction": "forward", "seconds": 1}) == "Drove forward for 1 seconds."
    assert run("drive", {"direction": "backward", "seconds": 9}) == "Drove backward for 3 seconds."
    run("turn", {"direction": "left", "degrees": 180})
    assert body.calls == [
        ("drive", (0.5, 0.5, 1.0)), ("drive", (-0.5, -0.5, 3.0)), ("drive", (-0.5, 0.5, 1.6)),
    ]


def test_claw_reports_whether_it_caught_something(monkeypatch):
    monkeypatch.setattr(nano_tools.time, "sleep", lambda s: None)
    body = FakeBody()
    body.claw_at = 0.55
    assert nano_tools.run_robot_tool("claw", {"action": "close"}, body, None) == (
        "The claw closed on something (it stopped 55% of the way)."
    )
    body.claw_at = 0.98
    assert "isn't holding anything" in nano_tools.run_robot_tool("claw", {"action": "close"}, body, None)
    body.claw_at = None
    assert nano_tools.run_robot_tool("claw", {"action": "close"}, body, None) == "Closed the claw."
    assert nano_tools.run_robot_tool("claw", {"action": "open"}, body, None) == "Claw opened."
    assert ("claw", (0.0,)) in body.calls


def test_eyes_take_names_hex_and_glances():
    body = FakeBody()
    nano_tools.run_robot_tool("eyes", {"expression": "happy", "color": "pink", "seconds": 2}, body, None)
    nano_tools.run_robot_tool("eyes", {"expression": "look_left", "color": "#00ff80", "seconds": 0}, body, None)
    assert body.calls == [
        ("eyes", ("happy", (255, 60, 150), 0.0, 2.0)),
        ("eyes", ("idle", (0, 255, 128), -1.0, 0.0)),
    ]
    with pytest.raises(ValueError, match="colour"):
        nano_tools.parse_color("blurple")


def test_look_sends_a_smaller_png_to_the_vision_model():
    import base64

    from PIL import Image

    asked = []
    fake_brain = types.SimpleNamespace(look=lambda q, b64: asked.append((q, b64)) or "A red wall.")
    reply = nano_tools.run_robot_tool("look", {"question": "what's ahead?"}, FakeBody(), fake_brain)
    assert reply == "A red wall."
    image = Image.open(io.BytesIO(base64.b64decode(asked[0][1])))
    assert image.format == "PNG" and image.width == 768


def test_fit_brain_routes_robot_tools_to_the_body(monkeypatch):
    fake = brain.OpenAICompatibleBrain.__new__(brain.OpenAICompatibleBrain)
    brain.Brain.__init__(fake)
    fake._run_command_tool = lambda call: ("desktop tool ran", False)
    body = FakeBody()
    nano_main.fit_brain(fake, body, log=lambda m: None)
    assert fake._run_command_tool(brain.Call("1", "stop", {})) == ("Stopped.", False)
    assert fake._run_command_tool(brain.Call("2", "get_weather", {"place": ""})) == ("desktop tool ran", False)
    assert fake._run_command_tool(brain.Call("3", "drive", None))[1] is True
    assert fake._command_system().startswith(nano_tools.NANO_SYSTEM)


# ---- hearing ---------------------------------------------------------------------------------


def _frame(level: float) -> np.ndarray:
    rng = np.random.default_rng(0)
    return (rng.standard_normal(FRAME_SAMPLES) * level).astype("<i2")


def test_endpointer_waits_for_you_to_finish():
    ear = Endpointer(silence_after=0.4)
    for _ in range(20):
        ear.background(_frame(100))
    ear.start()
    assert not any(ear.add(_frame(3000)) for _ in range(10))  # talking
    results = [ear.add(_frame(100)) for _ in range(5)]  # 0.4 s of quiet ends it
    assert results[-1] and not any(results[:-1])
    assert ear.audio().dtype == np.float32 and len(ear.audio()) == 15 * FRAME_SAMPLES


def test_endpointer_gives_up_if_nobody_speaks():
    ear = Endpointer(no_speech_after=0.8)
    for _ in range(20):
        ear.background(_frame(100))
    ear.start()
    done = [ear.add(_frame(100)) for _ in range(10)]
    assert done[-1] and ear.audio().size == 0


# ---- speaking through the robot --------------------------------------------------------------------


def test_robot_voice_says_each_sentence_as_it_arrives():
    body = FakeBody()
    started = []
    voice = RobotVoice(body, on_start=lambda: started.append(1), render=lambda text: text.encode())
    voice.feed("It's **sunny**. Hig")
    deadline = time.monotonic() + 2
    while not body.said and time.monotonic() < deadline:
        time.sleep(0.01)
    assert body.said == [b"It's sunny."]  # before the reply is finished
    voice.feed("h of 61.")
    voice.finish()
    assert body.said == [b"It's sunny.", b"High of 61."] and started == [1]


def test_robot_voice_goes_quiet_when_stopped():
    body = FakeBody()
    voice = RobotVoice(body, render=lambda text: text.encode())
    voice.stop()
    voice.feed("You won't hear this. Or this.")
    voice.finish()
    assert body.said == [] and ("stop_speaking", ()) in body.calls


# ---- the whole loop ------------------------------------------------------------------------------


class FakeWake:
    def __init__(self, fire_on: set[int]):
        self.fire_on, self.count = fire_on, 0

    def heard(self, frame, speaking=False):
        self.count += 1
        return self.count in self.fire_on


def test_hey_jarvis_then_a_question_gets_a_spoken_answer(monkeypatch, tmp_path):
    from jarvis.nano import speech

    monkeypatch.setattr(speech.voice, "render_wav", lambda text: text.encode())
    monkeypatch.setattr(nano_main.prefs, "get", lambda key, default=None: "")
    body = FakeBody()
    heard_audio = []
    transcriber = types.SimpleNamespace(
        transcribe=lambda audio, vocab: heard_audio.append(audio) or "what's the weather"
    )
    done = threading.Event()

    class Brain:
        last_calls = [("get_weather", {})]

        def run_command(self, text, on_text=None):
            on_text("It's 54 degrees. ")
            on_text("Bring a jacket.")
            return "It's 54 degrees. Bring a jacket."

        def cancel(self):
            pass

    nano = nano_main.Nano(body, Brain(), transcriber, FakeWake({5}),
                          Endpointer(silence_after=0.4), log=lambda m: None)
    original = nano._run_job

    def run_job(audio, job):
        original(audio, job)
        done.set()

    nano._run_job = run_job
    for _ in range(4):
        nano.on_frame(_frame(100))  # quiet room
    nano.on_frame(_frame(100))  # "Hey Jarvis" detected here
    assert nano.listening and ("mood", ("listening",)) in body.calls
    for _ in range(8):
        nano.on_frame(_frame(3000))  # the question
    for _ in range(6):
        nano.on_frame(_frame(100))  # and quiet
    assert done.wait(3)
    assert heard_audio and heard_audio[0].dtype == np.float32
    assert b"It's 54 degrees." in body.said and b"Bring a jacket." in body.said
    moods = [c[1][0] for c in body.calls if c[0] == "mood"]
    assert moods[-1] == "idle" and "thinking" in moods and "speaking" in moods
    assert habits._entries()[-1]["did"] == "get_weather"


def test_saying_hey_jarvis_again_interrupts(monkeypatch):
    body = FakeBody()
    cancelled = []
    fake_brain = types.SimpleNamespace(cancel=lambda: cancelled.append(1))
    nano = nano_main.Nano(body, fake_brain, None, FakeWake({1}), log=lambda m: None)
    nano.busy = True
    nano.voice = types.SimpleNamespace(stop=lambda: body.calls.append(("voice_stop", ())))
    nano.on_frame(_frame(100))
    assert cancelled == [1] and ("voice_stop", ()) in body.calls and ("stop", ()) in body.calls
    assert nano.listening and nano.job == 1


# ---- the robot client ------------------------------------------------------------------------------


def test_mic_stream_is_cut_into_80ms_frames(monkeypatch):
    samples = (np.arange(FRAME_SAMPLES * 2 + 100) % 1000).astype("<i2").tobytes()

    class Stream:
        def __init__(self):
            self.data = io.BytesIO(samples)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self, n):
            return self.data.read(n)

    body = Body("http://robot:8080", "t")
    monkeypatch.setattr(body, "_request", lambda method, path, timeout=30: Stream())
    frames = body.mic_frames(log=lambda m: None, sleep=lambda s: None)
    first, second = next(frames), next(frames)
    assert len(first) == len(second) == FRAME_SAMPLES and first[1] == 1


def test_wrong_token_and_offline_robot_are_explained(monkeypatch):
    import urllib.error

    body = Body("http://robot:8080", "t")

    def refuse(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO(b""))

    monkeypatch.setattr("urllib.request.urlopen", refuse)
    with pytest.raises(RuntimeError, match="JARVIS_NANO_TOKEN"):
        body.stop()

    def offline(request, timeout):
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    with pytest.raises(RuntimeError, match="same Wi-Fi"):
        body.stop()


# ---- the body server on the robot --------------------------------------------------------------------


@pytest.fixture
def server(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    monkeypatch.setenv("JARVIS_BODY_NO_APP", "1")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "robot"))
    import body_server

    class FakeHardware:
        def __init__(self):
            self.wheel_log, self.claw_log, self.frames = [], [], []
            self.feedback = 0.4

        def wheels(self, left, right):
            self.wheel_log.append((left, right))

        def claw(self, position):
            self.claw_log.append(position)

        def claw_feedback(self):
            return self.feedback

        def pixels(self, colors):
            self.frames.append(colors)

        def photo(self):
            return b"\xff\xd8jpeg"

    hardware = FakeHardware()
    client = TestClient(body_server.create_app(hardware, token="secret"))
    yield types.SimpleNamespace(client=client, hw=hardware, module=body_server)
    sys.path.pop(0)


def test_body_server_needs_the_token(server):
    assert server.client.get("/health").json() == {"ok": True}
    assert server.client.post("/stop").status_code == 401
    assert server.client.post("/stop", headers={"X-Token": "wrong"}).status_code == 401


def test_body_server_drives_then_stops_by_itself(server):
    headers = {"X-Token": "secret"}
    reply = server.client.post("/drive", json={"left": 2, "right": -0.5, "seconds": 0.2}, headers=headers)
    assert reply.json() == {"ok": True}
    assert server.hw.wheel_log[0] == (1.0, -0.5)  # clamped to full speed
    time.sleep(0.4)
    assert server.hw.wheel_log[-1] == (0, 0)  # the watchdog stopped it


def test_body_server_claw_photo_and_eyes(server):
    headers = {"X-Token": "secret"}
    server.client.post("/claw", json={"position": 1.7}, headers=headers)
    assert server.hw.claw_log == [1.0]
    assert server.client.get("/claw", headers=headers).json() == {"position": 0.4}
    photo = server.client.get("/photo", headers=headers)
    assert photo.headers["content-type"] == "image/jpeg" and photo.content.startswith(b"\xff\xd8")
    reply = server.client.post("/eyes", json={"expression": "happy", "r": 300, "g": 0, "b": 0}, headers=headers)
    assert reply.json() == {"ok": True}
    time.sleep(0.2)
    assert server.hw.frames and len(server.hw.frames[-1]) == 24


def test_eye_shapes(server):
    happy = server.module.eye_frame("happy", (255, 0, 0), 0.0)
    sad = server.module.eye_frame("sad", (255, 0, 0), 0.0)
    assert happy[0] == (255, 0, 0) and happy[6] == (0, 0, 0)  # top lit, bottom dark
    assert sad[0] == (0, 0, 0) and sad[6] == (255, 0, 0)
    assert all(p == (0, 0, 0) for p in server.module.eye_frame("blink", (255, 0, 0), 0.0))
    right = server.module.eye_frame("idle", (200, 200, 200), 0.0, look=1.0)
    assert right[3][0] > right[9][0]  # brighter on the right side of the ring
