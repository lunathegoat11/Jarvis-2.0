import pytest

from jarvis import voice
from jarvis.config import Config


def test_split_sentences():
    assert voice.split_sentences("Done. It's playing now! Anything else?") == [
        "Done.", "It's playing now!", "Anything else?",
    ]


@pytest.mark.parametrize(
    "engine, name, installed, expected",
    [
        ("auto", "", True, "kokoro"),
        ("auto", "", False, "system"),
        ("auto", "Daniel", True, "system"),  # a macOS voice name
        ("auto", "bm_lewis", True, "kokoro"),
        ("system", "", True, "system"),
        ("kokoro", "", False, "kokoro"),
    ],
)
def test_engine_choice(monkeypatch, engine, name, installed, expected):
    monkeypatch.setattr(voice, "config", Config(voice_engine=engine, voice=name))
    monkeypatch.setattr(voice, "kokoro_installed", lambda: installed)
    assert voice.engine() == expected


def test_kokoro_failure_falls_back_to_system_voice(monkeypatch):
    monkeypatch.setattr(voice, "config", Config(voice_engine="kokoro", speak_replies=True))
    spoken = []

    def broken(text):
        raise RuntimeError("no model")

    monkeypatch.setattr(voice, "_speak_kokoro", broken)
    monkeypatch.setattr(voice, "_speak_system", spoken.append)
    voice.speak("Hello.")
    assert spoken == ["Hello."]
