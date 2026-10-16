"""Browsing, Claude's computer-use toolset, and speech recognition."""

import sys
import types

import pytest

from jarvis import audio, brain, browser, computer, screen
from jarvis.config import Config


# ---- a stand-in for pynput ------------------------------------------------------


class FakeMouse:
    log: list = []
    position = (0, 0)

    def __init__(self):
        pass

    def click(self, button, count=1):
        FakeMouse.log.append(("click", button, count, FakeMouse.position))

    def press(self, button):
        FakeMouse.log.append(("press", button, FakeMouse.position))

    def release(self, button):
        FakeMouse.log.append(("release", button, FakeMouse.position))

    def scroll(self, dx, dy):
        FakeMouse.log.append(("scroll", dx, dy, FakeMouse.position))

    def __setattr__(self, name, value):
        if name == "position":
            FakeMouse.position = value
        else:
            object.__setattr__(self, name, value)


class FakeKeyboard:
    log: list = []

    def press(self, key):
        FakeKeyboard.log.append(("down", key))

    def release(self, key):
        FakeKeyboard.log.append(("up", key))


@pytest.fixture
def pynput(monkeypatch):
    keys = types.SimpleNamespace(**{
        name: name for name in (
            "enter tab esc backspace delete space up down left right home end page_up "
            "page_down ctrl alt shift cmd caps_lock " + " ".join(f"f{n}" for n in range(1, 13))
        ).split()
    })
    keyboard = types.SimpleNamespace(Controller=FakeKeyboard, Key=keys)
    mouse = types.SimpleNamespace(
        Controller=FakeMouse, Button=types.SimpleNamespace(left="L", right="R", middle="M")
    )
    monkeypatch.setitem(sys.modules, "pynput", types.SimpleNamespace(keyboard=keyboard, mouse=mouse))
    monkeypatch.setitem(sys.modules, "pynput.keyboard", keyboard)
    monkeypatch.setitem(sys.modules, "pynput.mouse", mouse)
    monkeypatch.setattr(computer.desktop, "on_main_thread", lambda fn, *a: fn(*a))
    monkeypatch.setattr(computer.time, "sleep", lambda s: None)
    FakeMouse.log, FakeKeyboard.log = [], []
    return types.SimpleNamespace(mouse=FakeMouse, keyboard=FakeKeyboard)


class QuietHUD:
    def __getattr__(self, name):
        return lambda *a, **k: None


def _computer_with_shot():
    pc = computer.Computer(QuietHUD(), 1280)
    # A 1280-pixel-wide image of a 1512-point-wide screen.
    pc.shot = screen.Shot(png_b64="", width=1280, height=800, left=0, top=0, scale=1512 / 1280)
    return pc


# ---- Claude's computer-use toolset -----------------------------------------------


def test_key_names_from_claude_map_to_mac_keys(pynput):
    assert computer.parse_keys("Return") == ["enter"]
    assert computer.parse_keys("ctrl+s") == ["ctrl", "s"]
    assert computer.parse_keys("super+Tab") == ["cmd", "tab"]
    assert computer.parse_keys("cmd+shift+T") == ["cmd", "shift", "t"]
    with pytest.raises(ValueError, match="Unknown key"):
        computer.parse_keys("hyper+x")


def test_clicks_land_where_claude_aimed_in_screen_points(pynput):
    pc = _computer_with_shot()
    assert pc.run("left_click", {"coordinate": [640, 400]}) == "OK"
    kind, button, count, (x, y) = FakeMouse.log[0]
    assert (kind, button, count) == ("click", "L", 1)
    assert (x, y) == (pytest.approx(756.0), pytest.approx(472.5))
    pc.run("double_click", {"coordinate": [0, 0]})
    assert FakeMouse.log[-1] == ("click", "L", 2, (0.0, 0.0))
    pc.run("right_click", {"coordinate": [10, 10], "text": "shift"})
    assert FakeKeyboard.log == [("down", "shift"), ("up", "shift")]
    assert FakeMouse.log[-1][:3] == ("click", "R", 1)


def test_scroll_drag_keys_and_cursor(pynput):
    pc = _computer_with_shot()
    pc.run("scroll", {"coordinate": [100, 100], "scroll_direction": "down", "scroll_amount": 5})
    assert FakeMouse.log[-1][:3] == ("scroll", 0, -5)
    pc.run("left_click_drag", {"start_coordinate": [0, 0], "coordinate": [640, 0]})
    assert FakeMouse.log[-2][0] == "press" and FakeMouse.log[-2][2] == (0.0, 0.0)
    assert FakeMouse.log[-1][0] == "release" and FakeMouse.log[-1][2] == (pytest.approx(756.0), 0.0)
    pc.run("key", {"text": "cmd+l", "repeat": 2})
    assert FakeKeyboard.log == [("down", "cmd"), ("down", "l"), ("up", "l"), ("up", "cmd")] * 2
    FakeMouse.position = (756.0, 472.5)
    assert pc.run("cursor_position", {}) == "X=640, Y=400"
    with pytest.raises(ValueError, match="Unknown computer action"):
        pc.run("teleport", {})


def _use(id, name, input):
    return types.SimpleNamespace(type="tool_use", id=id, name=name, input=input, toolset_name="computer")


def test_a_failed_action_stops_the_rest_of_the_batch(pynput):
    pc = _computer_with_shot()
    results = brain.AnthropicBrain._computer_results(
        pc,
        [_use("a", "left_click", {"coordinate": [1, 1]}), _use("b", "key", {"text": "hyper"}),
         _use("c", "type", {"text": "never typed"})],
        stopped=lambda: False,
    )
    assert [r["toolset_name"] for r in results] == ["computer"] * 3
    assert results[0]["content"] == "OK" and "is_error" not in results[0]
    assert results[1]["is_error"] and "Unknown key" in results[1]["content"]
    assert results[2] == {
        "type": "tool_result", "tool_use_id": "c", "toolset_name": "computer",
        "is_error": True, "content": computer.HALTED,
    }


def test_claude_screen_control_uses_the_toolset_and_returns_screenshots(pynput, monkeypatch):
    shots = iter(["first", "second"])
    monkeypatch.setattr(
        computer.screen, "capture",
        lambda width, grid=False: screen.Shot(next(shots), 1280, 800, 0, 0, 1.0),
    )
    replies = [
        types.SimpleNamespace(stop_reason="tool_use", content=[
            _use("a", "left_click", {"coordinate": [5, 5]}), _use("b", "screenshot", {}),
        ]),
        types.SimpleNamespace(stop_reason="end_turn", content=[
            types.SimpleNamespace(type="text", text="I opened the Downloads folder."),
        ]),
    ]
    requests = []

    def create(**kwargs):
        requests.append({**kwargs, "messages": list(kwargs["messages"])})
        return replies.pop(0)

    fake = brain.AnthropicBrain.__new__(brain.AnthropicBrain)
    brain.Brain.__init__(fake)
    fake.vision_model = "claude-sonnet-5-5"
    fake._create = create
    assert fake.operate("open my downloads") == "I opened the Downloads folder."
    assert requests[0]["tools"] == [{"type": "computer_toolset_20260801"}]
    first_image = requests[0]["messages"][0]["content"][0]
    assert first_image["source"]["data"] == "first"
    results = requests[1]["messages"][-1]["content"]
    assert results[0]["content"] == "OK"
    assert results[1]["content"][0]["source"]["data"] == "second"
    assert FakeMouse.log[0][0] == "click"


def test_a_model_without_the_toolset_falls_back_to_jarvis_screen_tools(monkeypatch):
    import anthropic

    def refuse(**kwargs):
        error = anthropic.BadRequestError.__new__(anthropic.BadRequestError)
        Exception.__init__(error, "claude-haiku-4-5 does not support tool types: computer_toolset_20260801")
        raise error

    monkeypatch.setattr(
        computer.screen, "capture", lambda width, grid=False: screen.Shot("x", 10, 10, 0, 0, 1.0)
    )
    fake = brain.AnthropicBrain.__new__(brain.AnthropicBrain)
    brain.Brain.__init__(fake)
    fake.vision_model = "claude-haiku-4-5"
    fake._create = refuse
    monkeypatch.setattr(brain.Brain, "operate", lambda self, task: f"fallback: {task}")
    assert fake.operate("tidy the desktop") == "fallback: tidy the desktop"


# ---- browsing ---------------------------------------------------------------------


def test_open_page_in_safari_opens_a_tab_and_reads_it(monkeypatch):
    scripts = []
    monkeypatch.setattr(browser, "config", Config(is_mac=True))
    monkeypatch.setattr(browser, "pick_browser", lambda: "Safari")
    monkeypatch.setattr(browser, "_osascript", lambda script, timeout=20: scripts.append(script) or "")
    monkeypatch.setattr(browser, "_wait_for_load", lambda b, seconds=10: None)
    monkeypatch.setattr(browser, "_page", lambda b: "PAGE")
    assert browser.open_page("bbc.com/news", new_tab=True) == "PAGE"
    assert 'make new tab with properties {URL:"https://bbc.com/news"}' in scripts[0]


def test_chrome_runs_page_scripts_in_the_active_tab(monkeypatch):
    scripts = []
    monkeypatch.setattr(browser, "_osascript", lambda script, timeout=20: scripts.append(script) or "ok")
    browser._run_js("Google Chrome", 'document.title + "x"')
    assert scripts[0] == (
        'tell application "Google Chrome" to execute active tab of front window '
        'javascript "document.title + \\"x\\""'
    )


def test_click_reports_an_item_that_is_gone(monkeypatch):
    monkeypatch.setattr(browser, "config", Config(is_mac=True))
    monkeypatch.setattr(browser, "pick_browser", lambda: "Safari")
    monkeypatch.setattr(browser, "_run_js", lambda b, js: "missing")
    with pytest.raises(RuntimeError, match="no item 7"):
        browser.click(7)


def test_browser_permission_errors_say_how_to_fix_them(monkeypatch):
    def failing(stderr):
        result = types.SimpleNamespace(returncode=1, stderr=stderr, stdout="")
        monkeypatch.setattr(browser.subprocess, "run", lambda *a, **k: result)

    failing("Safari got an error: You must enable 'Allow JavaScript from Apple Events' ...")
    with pytest.raises(RuntimeError, match="Develop > Allow JavaScript"):
        browser._osascript("x")
    failing("execution error: Not authorized to send Apple events to Safari. (-1743)")
    with pytest.raises(RuntimeError, match="Automation"):
        browser._osascript("x")


# ---- speech recognition --------------------------------------------------------------


def test_auto_picks_turbo_on_the_gpu_when_mlx_is_installed(monkeypatch):
    monkeypatch.setattr(audio, "mlx_available", lambda: True)
    assert audio.choose_model("auto") == ("mlx", "mlx-community/whisper-large-v3-turbo")
    monkeypatch.setattr(audio, "mlx_available", lambda: False)
    assert audio.choose_model("auto") == ("faster", "small.en")
    assert audio.choose_model("medium.en") == ("faster", "medium.en")
    assert audio.choose_model("mlx-community/whisper-small-mlx") == ("mlx", "mlx-community/whisper-small-mlx")


def test_mlx_transcription_passes_language_and_dictionary(monkeypatch):
    import numpy as np

    calls = []
    fake_mlx = types.SimpleNamespace(
        transcribe=lambda audio_in, **kw: calls.append(kw) or {"text": " Open Safari. "}
    )
    monkeypatch.setitem(sys.modules, "mlx_whisper", fake_mlx)
    monkeypatch.setattr(audio, "config", Config(whisper_model="mlx-community/whisper-large-v3-turbo", language="en"))
    transcriber = audio.Transcriber()
    text = transcriber.transcribe(np.zeros(16000, dtype=np.float32), "Kosha")
    assert text == "Open Safari."
    assert calls[0]["language"] == "en"
    assert calls[0]["initial_prompt"] == "Words that may come up: Kosha."
    assert calls[0]["path_or_hf_repo"] == "mlx-community/whisper-large-v3-turbo"


def test_recording_continues_briefly_after_the_key_is_let_go(monkeypatch):
    from jarvis import main

    events = []
    jarvis = main.Jarvis.__new__(main.Jarvis)
    jarvis.recorder = types.SimpleNamespace(recording=True, stop=lambda: events.append("stopped") or "AUDIO")
    jarvis.hud = QuietHUD()
    jarvis.mode, jarvis._job, jarvis._busy = "auto", 0, False
    monkeypatch.setattr(main.time, "sleep", lambda s: events.append(f"waited {s}"))
    monkeypatch.setattr(jarvis, "_run_job", lambda mode, audio_in, job: events.append(audio_in), raising=False)
    started = []
    monkeypatch.setattr(main.threading, "Thread", lambda target, args, daemon: types.SimpleNamespace(
        start=lambda: started.append((target, args))))
    jarvis.stop("auto")
    assert events == []  # nothing stops straight away
    target, args = started[0]
    target(*args)
    assert events == [f"waited {main.RECORDING_TAIL}", "stopped", "AUDIO"]
