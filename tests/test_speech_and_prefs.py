import json

from jarvis import prefs
from jarvis.config import Config
from jarvis.voice import clean_for_speech


def test_markdown_is_not_read_aloud():
    text = (
        "**Sure!** Here's how:\n\n"
        "1. Open *Settings*\n"
        "2. Click [Display](https://apple.com/display)\n"
        "- Turn on `Dark mode` 🌙\n\n"
        "## Done\n"
        "More at https://support.apple.com/guide."
    )
    assert clean_for_speech(text) == (
        "Sure! Here's how: Open Settings. Click Display. Turn on Dark mode. Done. More at the link."
    )


def test_code_and_tables():
    assert clean_for_speech("Run this:\n```\nls -la\n```") == "Run this: (I've left the code out.)"
    assert clean_for_speech("| Plan | Price |\n|---|---|\n| Basic | $5 |") == "Plan, Price. Basic, $5."


def test_ordinary_text_is_untouched():
    plain = "It's 5:30 pm, and your next meeting is with Sam at 6."
    assert clean_for_speech(plain) == plain
    assert clean_for_speech("Use snake_case names like my_var.") == "Use snake_case names like my_var."


def test_links_can_be_kept_for_the_screen():
    assert clean_for_speech("See **https://x.com/a**", keep_links=True) == "See https://x.com/a."


def test_prefs_override_env_and_persist(tmp_path, monkeypatch):
    monkeypatch.setattr(prefs, "config", Config(data_dir=tmp_path, voice="bm_george", voice_speed=1.0))
    monkeypatch.setattr(prefs, "_values", None)
    monkeypatch.setitem(prefs.EDITABLE, "voice", lambda: "bm_george")
    assert prefs.get("voice") == "bm_george"
    prefs.set("voice", "bm_lewis")
    assert prefs.get("voice") == "bm_lewis"
    assert json.loads((tmp_path / "settings.json").read_text()) == {"voice": "bm_lewis"}
