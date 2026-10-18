import json
import threading

import pytest

from jarvis import macs, tools
from jarvis.config import Config

TOPIC = "jarvis-macs-abcdefghijklmnopqrstuvwx"


@pytest.fixture
def main_mac(monkeypatch, private_data):
    monkeypatch.setattr(macs, "config", Config(
        data_dir=private_data, mac_name="Main", ntfy_macs_topic=TOPIC, ntfy_topic="alerts",
    ))
    sent = []
    monkeypatch.setattr(macs, "_publish", sent.append)
    monkeypatch.setattr(macs, "_pending", {})
    monkeypatch.setattr(macs, "_on_late", None)
    return sent


def test_names_are_matched_loosely():
    assert macs.name_of("the old MacBook") == "old"
    assert macs.name_of("Main Mac") == "main"
    assert macs.name_of("my mac") == ""


def test_needs_a_name_and_its_own_topic(monkeypatch):
    monkeypatch.setattr(macs, "config", Config(mac_name="main", ntfy_macs_topic=TOPIC, ntfy_topic="alerts"))
    assert macs.configured()
    monkeypatch.setattr(macs, "config", Config(mac_name="main", ntfy_macs_topic="alerts", ntfy_topic="alerts"))
    assert not macs.configured()
    monkeypatch.setattr(macs, "config", Config(mac_name="", ntfy_macs_topic=TOPIC))
    assert not macs.configured()


def answer_from_old_mac(sent, reply="Opened YouTube."):
    """Plays the other Mac: waits for the job, then says got it and done."""
    def run():
        while not sent:
            threading.Event().wait(0.01)
        job = sent[0]
        for message in (
            {"kind": "got", "id": job["id"], "from": "old", "to": "main"},
            {"kind": "done", "id": job["id"], "from": "old", "to": "main", "reply": reply},
        ):
            macs._handle(json.dumps(message), on_task=None, log=print)

    thread = threading.Thread(target=run)
    thread.start()
    return thread


def test_asks_the_other_mac_and_returns_its_answer(main_mac):
    thread = answer_from_old_mac(main_mac)
    result = macs.ask("the old Mac", "open YouTube")
    thread.join()
    assert main_mac[0]["kind"] == "task"
    assert main_mac[0]["to"] == "old" and main_mac[0]["from"] == "main"
    assert main_mac[0]["task"] == "open YouTube"
    assert result == 'The "old" Mac said: Opened YouTube.'
    assert macs._pending == {}
    assert macs.known() == ["old"]


def test_says_so_when_no_mac_answers(main_mac):
    with pytest.raises(RuntimeError, match="didn't answer"):
        macs.ask("old", "open YouTube", got_seconds=0.01)


def test_a_late_answer_goes_to_the_phone(main_mac, monkeypatch):
    late = []
    monkeypatch.setattr(macs, "_on_late", late.append)
    with pytest.raises(RuntimeError):
        macs.ask("old", "open YouTube", got_seconds=0.01)
    job = main_mac[0]["id"]
    macs._handle(json.dumps({"kind": "done", "id": job, "from": "old", "to": "main", "reply": "Done."}), None, print)
    assert late == ["From the old Mac: Done."]
    assert macs._pending == {}


def test_a_slow_job_is_answered_later(main_mac):
    def got_only():
        while not main_mac:
            threading.Event().wait(0.01)
        macs._handle(json.dumps({"kind": "got", "id": main_mac[0]["id"], "from": "old", "to": "main"}), None, print)

    thread = threading.Thread(target=got_only)
    thread.start()
    result = macs.ask("old", "write my essay", done_seconds=0.05)
    thread.join()
    assert "still working on it" in result


def test_this_mac_is_done_here_and_jobs_are_not_passed_on_twice(main_mac):
    assert "this Mac" in macs.ask("main mac", "open Spotify")
    with macs.passed_on():
        with pytest.raises(RuntimeError, match="can't be passed on"):
            macs.ask("old", "open Spotify")
    assert main_mac == []


def test_runs_jobs_meant_for_it_and_ignores_the_rest(main_mac):
    tasks = []
    on_task = lambda task, replies: tasks.append((task, replies))  # noqa: E731
    macs._handle(json.dumps({"kind": "task", "id": "j1", "from": "old", "to": "the main mac", "task": "open Notes"}), on_task, print)
    macs._handle(json.dumps({"kind": "task", "id": "j2", "from": "old", "to": "kitchen", "task": "open Notes"}), on_task, print)
    macs._handle(json.dumps({"kind": "task", "id": "j3", "from": "main", "to": "main", "task": "loop"}), on_task, print)
    macs._handle("not json at all", on_task, print)
    assert [t for t, _ in tasks] == ["open Notes"]
    assert main_mac == [{"kind": "got", "id": "j1", "from": "main", "to": "old"}]

    replies = tasks[0][1]
    assert replies.from_mac == "old"
    replies.text("Opened Notes.")
    assert main_mac[-1] == {"kind": "done", "id": "j1", "from": "main", "to": "old", "reply": "Opened Notes."}


def test_answers_hello_and_remembers_who_said_it(main_mac):
    macs._handle(json.dumps({"kind": "hello", "from": "old"}), None, print)
    assert main_mac == [{"kind": "here", "from": "main"}]
    assert macs.known() == ["old"]
    assert '"main"' in macs.prompt_section() and '"old"' in macs.prompt_section()


def test_the_tool_is_offered_only_when_set_up(main_mac, monkeypatch):
    names = [t["name"] for t in tools.command_tools(can_see_screen=False)]
    assert "other_mac" in names
    monkeypatch.setattr(macs, "config", Config(mac_name="", ntfy_macs_topic=""))
    names = [t["name"] for t in tools.command_tools(can_see_screen=False)]
    assert "other_mac" not in names


def test_setup_makes_a_code_and_the_other_mac_pastes_it(tmp_path, monkeypatch):
    from jarvis import config as settings

    env = tmp_path / ".env"
    monkeypatch.setattr(settings, "USER_ENV", env)
    monkeypatch.setattr(macs, "config", Config(ntfy_macs_topic=""))
    copied = []
    assert macs.setup(["Main"], clipboard_out=copied.append, out=lambda *a: None) == 0
    code = copied[0]
    assert code.startswith("jarvis-macs-")
    assert f"JARVIS_MAC_NAME=main\nNTFY_MACS_TOPIC={code}\n" == env.read_text()

    other = tmp_path / "other.env"
    monkeypatch.setattr(settings, "USER_ENV", other)
    assert macs.setup(["old", "--paste"], clipboard_in=lambda: "hello", out=lambda *a: None) == 1
    assert macs.setup(["old", "--paste"], clipboard_in=lambda: code + "\n", out=lambda *a: None) == 0
    assert other.read_text() == f"JARVIS_MAC_NAME=old\nNTFY_MACS_TOPIC={code}\n"
