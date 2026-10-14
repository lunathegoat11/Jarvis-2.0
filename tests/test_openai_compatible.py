import json
import pathlib
import subprocess
import sys
from types import SimpleNamespace as NS

from jarvis import brain


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def reply(content=None, tool_calls=None):
    message = NS(content=content, tool_calls=tool_calls, refusal=None)
    return NS(choices=[NS(message=message)])


def call(id, name, args):
    return NS(id=id, function=NS(name=name, arguments=args))


def make_brain(responses):
    b = brain.Brain.__new__(brain.OpenAICompatibleBrain)
    brain.Brain.__init__(b)
    fake = FakeCompletions(responses)
    b.client = NS(chat=NS(completions=fake))
    return b, fake


def test_command_runs_tool_then_replies(monkeypatch):
    ran = []
    monkeypatch.setattr(brain, "run_tool", lambda name, args: ran.append((name, args)) or "ok")
    b, fake = make_brain(
        [
            reply(tool_calls=[call("c1", "open_url", json.dumps({"url": "youtube.com"}))]),
            reply(content="YouTube is open."),
        ]
    )

    assert b.run_command("open youtube") == "YouTube is open."
    assert ran == [("open_url", {"url": "youtube.com"})]
    second = fake.calls[1]["messages"]
    assert second[0]["role"] == "system"
    assert second[-2]["tool_calls"][0]["id"] == "c1"
    assert second[-1] == {"role": "tool", "tool_call_id": "c1", "content": "ok"}
    tool_names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
    assert "web_search" not in tool_names


def test_bad_tool_arguments_are_reported(monkeypatch):
    monkeypatch.setattr(brain, "run_tool", lambda name, args: "should not run")
    b, fake = make_brain(
        [
            reply(tool_calls=[call("c1", "open_url", "{not json")]),
            reply(content="Sorry, that didn't work."),
        ]
    )

    b.run_command("open something")
    assert "not valid JSON" in fake.calls[1]["messages"][-1]["content"]


def test_screenshot_sent_as_data_url():
    b, fake = make_brain([reply(content="It's a spreadsheet.")])
    assert b.ask_about_screen("what is this", "QUJD") == "It's a spreadsheet."
    parts = fake.calls[0]["messages"][1]["content"]
    assert parts[1]["image_url"]["url"] == "data:image/png;base64,QUJD"


ROOT = str(pathlib.Path(__file__).resolve().parents[1])


def config_under(env, tmp_path):
    # Run outside the repo so a real .env there can't change the result.
    code = "from jarvis.config import config as c; print(c.provider, c.base_url, c.api_key, c.model, c.vision_model)"
    clean = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PYTHONPATH": ROOT, **env}
    out = subprocess.run(
        [sys.executable, "-c", code], env=clean, cwd=tmp_path, capture_output=True, text=True, check=True
    )
    return out.stdout.split()


def test_nvidia_preset(tmp_path):
    assert config_under({"JARVIS_PROVIDER": "nvidia", "NVIDIA_API_KEY": "nv-key"}, tmp_path) == [
        "nvidia",
        "https://integrate.api.nvidia.com/v1",
        "nv-key",
        "meta/llama-3.3-70b-instruct",
        "meta/llama-3.2-90b-vision-instruct",
    ]


def test_model_override_also_sets_vision_model_for_custom(tmp_path):
    provider, base_url, key, model, vision = config_under(
        {
            "JARVIS_PROVIDER": "custom",
            "JARVIS_BASE_URL": "https://example.com/v1",
            "JARVIS_API_KEY": "k",
            "JARVIS_MODEL": "some/model",
        },
        tmp_path,
    )
    assert (base_url, key, model, vision) == ("https://example.com/v1", "k", "some/model", "some/model")
