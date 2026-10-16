import types

import pytest

from jarvis import brain, contact, main, tools
from jarvis.config import Config


def test_write_document_saves_opens_and_remembers(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    opened = []
    monkeypatch.setattr("subprocess.run", lambda cmd, **kw: opened.append(cmd))
    monkeypatch.setattr(tools, "config", Config(is_mac=True))
    monkeypatch.setattr(tools, "made_documents", [])
    result = tools.run_tool(
        "write_document", {"title": "Geo test: prep sheet!", "content": "- Plate tectonics"}
    )
    path = tmp_path / "Documents" / "Jarvis" / "Geo test prep sheet.txt"
    assert path.read_text() == "Geo test: prep sheet!\n\n- Plate tectonics\n"
    assert "Geo test prep sheet.txt" in result
    assert opened == [["open", str(path)]]
    assert tools.made_documents == [path]
    # A second one with the same title doesn't overwrite the first.
    tools.write_document("Geo test: prep sheet!", "v2")
    assert path.read_text().endswith("- Plate tectonics\n")
    assert len(list(path.parent.iterdir())) == 2


class FakeHUD:
    def __getattr__(self, name):
        return lambda *a, **k: None


def test_documents_made_from_the_phone_are_sent_there(tmp_path, monkeypatch):
    jarvis = main.Jarvis.__new__(main.Jarvis)
    jarvis.hud, jarvis._job, jarvis._busy = FakeHUD(), 1, True
    document = tmp_path / "Geo prep.txt"

    class Brain:
        def run_command(self, text):
            assert "write_document" in text
            tools.made_documents.append(document)
            return "I made you a geography prep sheet."

    jarvis.brain = Brain()
    monkeypatch.setattr(tools, "made_documents", [tmp_path / "older.txt"])
    monkeypatch.setattr(main.quick, "match", lambda text: None)
    files, texts = [], []
    monkeypatch.setattr(main.contact, "send_file", lambda path, msg: files.append((path, msg)))
    monkeypatch.setattr(main.contact, "text_me", lambda msg: texts.append(msg))
    jarvis._run_phone_job("make me a prep sheet for my geo test", 1)
    assert files == [(document, "I made you a geography prep sheet.")]
    assert texts == []


def test_send_file_puts_the_file_on_the_alerts_topic(tmp_path, monkeypatch):
    document = tmp_path / "Geo prep.txt"
    document.write_text("Rivers")
    monkeypatch.setattr(contact, "config", Config(ntfy_topic="alerts"))
    sent = []

    class Reply:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(contact.urllib.request, "urlopen", lambda r, timeout: sent.append(r) or Reply())
    assert contact.send_file(document, "Here's your sheet") == "Sent it to your phone."
    request = sent[0]
    assert request.get_method() == "PUT" and request.data == b"Rivers"
    assert request.full_url.startswith("https://ntfy.sh/alerts?")
    assert "filename=Geo+prep.txt" in request.full_url
    assert "message=Here%27s+your+sheet" in request.full_url


def test_a_service_error_in_place_of_a_reply_is_explained(monkeypatch):
    error_text = (
        "[ERROR: Agent failed (Function process_single_item_agent timed out after 90.0 "
        "seconds), API failed (API request returned None after all retries)]."
    )
    message = types.SimpleNamespace(content=error_text, tool_calls=None)
    response = types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])
    fake = brain.OpenAICompatibleBrain.__new__(brain.OpenAICompatibleBrain)
    fake._create = lambda **kw: response
    monkeypatch.setattr(brain, "config", Config(provider="nvidia"))
    with pytest.raises(RuntimeError, match="NVIDIA's servers gave up .*too long"):
        fake._step("system", [], [], "model", "medium")
