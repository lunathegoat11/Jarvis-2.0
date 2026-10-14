"""Screen control, with a scripted model, fake screenshots and no real mouse."""

import json
from types import SimpleNamespace as NS

import pytest

from jarvis import brain, screen
from jarvis.screen import Shot


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def tool_reply(text, *calls):
    tool_calls = [
        NS(id=f"c{i}", function=NS(name=name, arguments=json.dumps(args)))
        for i, (name, args) in enumerate(calls)
    ]
    message = NS(content=text, tool_calls=tool_calls or None, refusal=None)
    return NS(choices=[NS(message=message)])


class RecordingHUD:
    def __init__(self):
        self.events = []

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.events.append((name, args, kwargs))


@pytest.fixture
def setup(monkeypatch):
    shot = Shot(png_b64="IMG", width=1280, height=800, left=0, top=0, scale=1.25)
    monkeypatch.setattr(screen, "capture", lambda width=None, grid=None: shot)
    monkeypatch.setattr(brain.time, "sleep", lambda s: None)
    actions = []
    monkeypatch.setattr(
        screen, "run_screen_tool", lambda name, args, s, hud: actions.append((name, args)) or "ok"
    )
    b = brain.Brain.__new__(brain.OpenAICompatibleBrain)
    brain.Brain.__init__(b)
    b._thinking_off = {}
    b.model, b.vision_model = "text-model", "vision-model"
    hud = RecordingHUD()
    b.attach(hud)
    return b, actions, hud


def test_looks_clicks_and_finishes(setup):
    b, actions, hud = setup
    fake = FakeCompletions(
        [
            tool_reply("Opening the channel", ("open_url", {"url": "https://www.youtube.com/@MrBeast/videos"})),
            tool_reply("Clicking the newest video", ("click", {"x": 200, "y": 300, "button": "left", "double": False})),
            tool_reply("", ("done", {"summary": "Playing MrBeast's newest video."})),
        ]
    )
    b.client = NS(chat=NS(completions=fake))

    assert b.operate("play the latest MrBeast video") == "Playing MrBeast's newest video."
    assert [a[0] for a in actions] == ["open_url", "click"]
    assert fake.calls[0]["model"] == "vision-model"
    # Every look after an action carries a fresh screenshot.
    last = fake.calls[2]["messages"][-1]
    assert last["role"] == "user" and last["content"][1]["type"] == "image_url"
    assert ("pointer_hide", (), {}) in hud.events
    assert any(e[0] == "status" and "Clicking the newest video" in e[1] for e in hud.events)


def test_escape_stops_between_steps(setup):
    b, actions, _ = setup

    class StopAfterFirst(FakeCompletions):
        def create(self, **kwargs):
            b.stop_event.set()  # the user presses Esc while the model thinks
            return super().create(**kwargs)

    fake = StopAfterFirst([tool_reply("Scrolling", ("scroll", {"x": 1, "y": 1, "direction": "down", "amount": 3}))])
    b.client = NS(chat=NS(completions=fake))
    assert b.operate("anything") == "Stopped."
    assert actions == []


def test_command_mode_hands_screen_tasks_to_operate(setup, monkeypatch):
    b, _, _ = setup
    monkeypatch.setattr(b, "operate", lambda task: f"did: {task}")
    fake = FakeCompletions(
        [
            tool_reply("", ("use_screen", {"task": "play the latest MrBeast video"})),
            tool_reply("It's playing."),
        ]
    )
    b.client = NS(chat=NS(completions=fake))
    assert b.run_command("play the latest MrBeast video") == "It's playing."
    tool_message = fake.calls[1]["messages"][-1]
    assert tool_message == {"role": "tool", "tool_call_id": "c0", "content": "did: play the latest MrBeast video"}


def test_shot_maps_image_pixels_to_screen_points():
    shot = Shot(png_b64="", width=1280, height=800, left=0, top=0, scale=1470 / 1280)
    x, y = shot.to_screen(640, 400)
    assert round(x) == 735 and round(y) == 459
    assert shot.to_screen(5000, -10) == shot.to_screen(1279, 0)
