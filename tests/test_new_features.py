from datetime import datetime

import pytest

from jarvis import macapps, prefs, quick
from jarvis.config import Config


def test_dictionary_words_are_added_once(tmp_path, monkeypatch):
    monkeypatch.setattr(prefs, "config", Config(data_dir=tmp_path))
    monkeypatch.setattr(prefs, "_values", None)
    monkeypatch.setitem(prefs.EDITABLE, "vocabulary", lambda: "Kosha")
    assert prefs.add_words(["Kai", "kosha", "PyObjC"]) == "Kosha, Kai, PyObjC"


def test_add_to_dictionary_by_voice(tmp_path, monkeypatch):
    added = []
    monkeypatch.setattr(prefs, "add_words", lambda words: added.extend(words) or "")
    q = quick.match("Add Kai and Brokering to my dictionary.")
    assert q.action == "add_words"
    assert quick.run(q) == "Added to your dictionary."
    assert added == ["Kai", "Brokering"]


def test_open_my_email_goes_to_the_ai():
    assert quick.match("Open my email") is None
    assert quick.match("Open the YouTube website").args["target"] == "the youtube website"


def test_calendar_dates_are_built_without_the_locale():
    script = macapps._date_script("d", datetime(2026, 10, 31, 15, 5))
    assert "set day of d to 1\n" in script  # avoids overflow when changing month
    assert "set month of d to 10" in script and "set day of d to 31" in script
    assert "set hours of d to 15" in script and "set minutes of d to 5" in script


def test_when_parsing():
    assert macapps.parse_when("2026-10-31 15:05") == datetime(2026, 10, 31, 15, 5)
    with pytest.raises(ValueError):
        macapps.parse_when("next Friday")


def test_applescript_strings_are_escaped():
    assert macapps._quote('Say "hi" \\ bye') == '"Say \\"hi\\" \\\\ bye"'


def test_events_need_confirmation(monkeypatch):
    from jarvis import tools

    called = []
    monkeypatch.setattr(macapps, "add_event", lambda *a: called.append(a) or "Added.")
    args = {"title": "Dentist", "start": "2026-10-31 15:00", "duration_minutes": 30}
    assert "confirm" in tools.run_tool("add_calendar_event", {**args, "confirmed": False})
    assert called == []
    assert tools.run_tool("add_calendar_event", {**args, "confirmed": True}) == "Added."


def test_garbled_env_numbers_fall_back_instead_of_crashing(monkeypatch):
    # A stray or mangled value in .env (e.g. from editing it by hand) must not
    # stop Jarvis from starting: the number falls back to its default.
    import importlib

    from jarvis import config as config_module

    monkeypatch.setenv("JARVIS_VOICE_SPEED", "fast")
    monkeypatch.setenv("JARVIS_SCREEN_WIDTH", "")
    monkeypatch.setenv("JARVIS_MAX_SCREEN_STEPS", "lots ")
    reloaded = importlib.reload(config_module)
    try:
        assert reloaded.config.voice_speed == 1.0
        assert reloaded.config.screen_control_width == 1280
        assert reloaded.config.max_screen_steps == 25
    finally:
        for name in ("JARVIS_VOICE_SPEED", "JARVIS_SCREEN_WIDTH", "JARVIS_MAX_SCREEN_STEPS"):
            monkeypatch.delenv(name, raising=False)
        importlib.reload(config_module)
