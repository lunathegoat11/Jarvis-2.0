import json

import pytest

from jarvis import tools
from jarvis.config import Config


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "config", Config(data_dir=tmp_path))
    return tmp_path


def test_notes_round_trip(data_dir):
    assert tools.run_tool("list_notes", {}) == "No notes saved yet."
    assert tools.run_tool("save_note", {"text": "buy milk"}) == "Saved."
    assert "buy milk" in tools.run_tool("list_notes", {})
    saved = json.loads((data_dir / "notes.json").read_text())
    assert saved[0]["text"] == "buy milk"


def test_unknown_tool_raises():
    with pytest.raises(ValueError):
        tools.run_tool("format_hard_drive", {})


def test_custom_tools_are_strict():
    for tool in tools.TOOLS:
        if "input_schema" in tool:
            assert tool["strict"] is True
            assert tool["input_schema"]["additionalProperties"] is False
