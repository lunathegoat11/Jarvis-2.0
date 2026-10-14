"""Talking over Jarvis: speech stops, the old request is dropped, history survives."""

import threading
from types import SimpleNamespace as NS

from jarvis import brain, voice
from jarvis.config import Config


def make_brain():
    b = brain.Brain.__new__(brain.OpenAICompatibleBrain)
    brain.Brain.__init__(b)
    b._thinking_off = {}
    b.model, b.vision_model = "text-model", "vision-model"
    return b


def reply(content):
    return NS(choices=[NS(message=NS(content=content, tool_calls=None, refusal=None))])


def test_cancel_keeps_finished_turns_and_drops_the_cut_off_one():
    b = make_brain()

    class Slow:
        def __init__(self):
            self.release = threading.Event()
            self.answers = [reply("First answer."), reply("Too late.")]

        def create(self, **kwargs):
            answer = self.answers.pop(0)
            if answer.choices[0].message.content == "Too late.":
                self.release.wait(2)
            return answer

    slow = Slow()
    b.client = NS(chat=NS(completions=slow))
    assert b.run_command("first") == "First answer."
    finished = list(b._command_history)

    worker = threading.Thread(target=b.run_command, args=("second",))
    worker.start()
    b.cancel()  # the user presses the key again
    slow.release.set()
    worker.join(2)

    assert b._command_history == finished  # the interrupted turn left no trace


def test_cancel_stops_screen_control_started_before_it(monkeypatch):
    from jarvis import screen
    from jarvis.screen import Shot

    b = make_brain()
    shot = Shot(png_b64="IMG", width=100, height=100, left=0, top=0, scale=1)
    monkeypatch.setattr(screen, "capture", lambda width=None, grid=None: shot)
    monkeypatch.setattr(brain.time, "sleep", lambda s: None)
    acted = []
    monkeypatch.setattr(screen, "run_screen_tool", lambda *a: acted.append(a) or "ok")

    def scripted(**kwargs):
        b.cancel()  # interrupted while the model was choosing an action
        call = NS(id="c1", function=NS(name="click", arguments='{"x":1,"y":1,"button":"left","double":false}'))
        return NS(choices=[NS(message=NS(content="", tool_calls=[call], refusal=None))])

    b.client = NS(chat=NS(completions=NS(create=scripted)))
    assert b.operate("do something") == "Stopped."
    assert acted == []


def test_voice_stop_cuts_off_the_system_voice(monkeypatch):
    monkeypatch.setattr(voice, "config", Config(is_mac=True, voice_engine="system"))
    started = threading.Event()

    class FakeProcess:
        def __init__(self, *args, **kwargs):
            self.done = threading.Event()
            started.set()

        def poll(self):
            return 0 if self.done.is_set() else None

        def terminate(self):
            self.done.set()

        def wait(self):
            self.done.wait(2)

    monkeypatch.setattr(voice.subprocess, "Popen", FakeProcess)
    talking = threading.Thread(target=voice._speak_system, args=("A long reply.",))
    talking.start()
    started.wait(1)
    voice.stop()
    talking.join(1)
    assert not talking.is_alive()
