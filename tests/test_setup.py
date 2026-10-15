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
