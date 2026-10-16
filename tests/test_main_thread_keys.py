import sys
import threading
import types

import pytest

from jarvis import desktop
from jarvis.config import Config


def _fake_mac_loop(monkeypatch):
    """Pretends to be a Mac with the AppKit loop running on a 'main' thread."""
    handed = []

    def call_after(fn):
        handed.append(fn)
        threading.Thread(target=fn).start()

    app = types.SimpleNamespace(isRunning=lambda: True)
    monkeypatch.setitem(sys.modules, "AppKit", types.SimpleNamespace(NSApp=lambda: app))
    helper = types.SimpleNamespace(callAfter=call_after)
    monkeypatch.setitem(sys.modules, "PyObjCTools", types.SimpleNamespace(AppHelper=helper))
    monkeypatch.setitem(sys.modules, "PyObjCTools.AppHelper", helper)
    monkeypatch.setattr(desktop, "config", Config(is_mac=True))
    return handed


def _from_background(fn):
    outcome = {}

    def run():
        try:
            outcome["value"] = fn()
        except Exception as error:
            outcome["error"] = error

    worker = threading.Thread(target=run)
    worker.start()
    worker.join(5)
    return outcome


def test_key_presses_from_a_background_thread_go_to_the_main_loop(monkeypatch):
    handed = _fake_mac_loop(monkeypatch)
    outcome = _from_background(lambda: desktop.on_main_thread(lambda a, b: a + b, 2, 3))
    assert outcome == {"value": 5}
    assert len(handed) == 1


def test_errors_still_reach_the_caller(monkeypatch):
    _fake_mac_loop(monkeypatch)

    def broken():
        raise ValueError("Unknown key: hyper")

    outcome = _from_background(lambda: desktop.on_main_thread(broken))
    assert isinstance(outcome["error"], ValueError)


def test_runs_directly_when_not_on_a_mac(monkeypatch):
    monkeypatch.setattr(desktop, "config", Config(is_mac=False))
    assert desktop.on_main_thread(lambda: threading.current_thread()) is threading.current_thread()


def test_press_keys_uses_the_main_thread(monkeypatch):
    keyboard = types.SimpleNamespace(
        Controller=object,
        Key=types.SimpleNamespace(cmd="cmd", ctrl="ctrl", alt="alt", shift="shift", enter="enter",
                                  esc="esc", tab="tab", space="space", backspace="backspace",
                                  left="left", right="right", up="up", down="down"),
    )
    monkeypatch.setitem(sys.modules, "pynput", types.SimpleNamespace(keyboard=keyboard))
    monkeypatch.setitem(sys.modules, "pynput.keyboard", keyboard)
    sent = []
    monkeypatch.setattr(desktop, "on_main_thread", lambda fn, *a: sent.append(fn))
    monkeypatch.setattr(desktop.time, "sleep", lambda s: None)
    desktop.press_keys("cmd+shift+n")
    assert len(sent) == 1
