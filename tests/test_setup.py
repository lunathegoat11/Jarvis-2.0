import stat

import pytest

from jarvis.setup import write_settings


def test_nvidia_key_is_saved_privately_and_other_lines_kept(tmp_path):
    env = tmp_path / ".env"
    env.write_text("EMAIL_ADDRESS=me@gmail.com\nJARVIS_PROVIDER=ollama\nJARVIS_MODEL=gemma4:12b\n")
    write_settings("nvidia", "  nvapi-abc  ", path=env)
    lines = env.read_text().splitlines()
    assert "EMAIL_ADDRESS=me@gmail.com" in lines
    assert "JARVIS_PROVIDER=nvidia" in lines
    assert "NVIDIA_API_KEY=nvapi-abc" in lines
    assert not any(line.startswith("JARVIS_MODEL") for line in lines)  # back to NVIDIA's default
    assert stat.S_IMODE(env.stat().st_mode) == 0o600


def test_ollama_needs_a_model_not_a_key(tmp_path):
    env = tmp_path / ".env"
    with pytest.raises(ValueError, match="ollama list"):
        write_settings("ollama", path=env)
    write_settings("ollama", model="gemma4:12b", path=env)
    assert env.read_text() == "JARVIS_PROVIDER=ollama\nJARVIS_MODEL=gemma4:12b\n"


def test_missing_key_is_refused(tmp_path):
    with pytest.raises(ValueError, match="API key"):
        write_settings("anthropic", "", path=tmp_path / ".env")


def test_the_settings_screen_saves_checked_values(tmp_path, monkeypatch):
    from jarvis import config as settings
    from jarvis import setup
    from jarvis.config import Config

    monkeypatch.setattr(settings, "config", Config(ntfy_topic="", ntfy_reply_topic="", ntfy_macs_topic=""))
    monkeypatch.setattr(setup, "_changed", {})
    env = tmp_path / ".env"

    values = setup.set_app_setting("JARVIS_LOCATION", "  Princeton,\n NJ ", env)
    assert values["JARVIS_LOCATION"] == "Princeton, NJ"
    assert setup.set_app_setting("JARVIS_MAC_NAME", "The Old MacBook", env)["JARVIS_MAC_NAME"] == "old"
    with pytest.raises(ValueError):
        setup.set_app_setting("JARVIS_BRIEFING_TIME", "7am", env)
    with pytest.raises(ValueError):
        setup.set_app_setting("ANTHROPIC_API_KEY", "sk-anything", env)
    with pytest.raises(ValueError):
        setup.set_app_setting("NTFY_TOPIC", "short", env)
    setup.set_app_setting("JARVIS_BRIEFING_TIME", "07:30", env)

    alerts = setup.new_code("NTFY_TOPIC", env)["NTFY_TOPIC"]
    assert alerts.startswith("jarvis-alerts-") and len(alerts) > 30
    assert setup.new_code("NTFY_TOPIC", env)["NTFY_TOPIC"] == alerts  # kept, not replaced
    with pytest.raises(ValueError, match="its own code"):
        setup.set_app_setting("NTFY_MACS_TOPIC", alerts, env)
    macs_code = setup.new_code("NTFY_MACS_TOPIC", env)["NTFY_MACS_TOPIC"]
    assert macs_code.startswith("jarvis-macs-")

    saved = env.read_text().splitlines()
    assert "JARVIS_LOCATION=Princeton, NJ" in saved
    assert "JARVIS_MAC_NAME=old" in saved
    assert "JARVIS_BRIEFING_TIME=07:30" in saved
    assert f"NTFY_TOPIC={alerts}" in saved and f"NTFY_MACS_TOPIC={macs_code}" in saved
    setup.set_app_setting("JARVIS_LOCATION", "", env)
    assert not any(line.startswith("JARVIS_LOCATION") for line in env.read_text().splitlines())
