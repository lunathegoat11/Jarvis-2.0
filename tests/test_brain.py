from types import SimpleNamespace as NS

from jarvis import brain


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        # Copy the history; Brain keeps appending to the same list.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.responses.pop(0)


def make_brain(responses, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test")
    b = brain.Brain()
    fake = FakeMessages(responses)
    b.client = NS(beta=NS(messages=fake))
    return b, fake


def test_command_runs_tool_then_replies(monkeypatch):
    ran = []
    monkeypatch.setattr(brain, "run_tool", lambda name, args: ran.append((name, args)) or "ok")
    tool_call = NS(type="tool_use", id="t1", name="open_app", input={"name": "Spotify"})
    b, fake = make_brain(
        [
            NS(stop_reason="tool_use", content=[tool_call]),
            NS(stop_reason="end_turn", content=[NS(type="text", text="Spotify is open.")]),
        ],
        monkeypatch,
    )

    assert b.run_command("open spotify") == "Spotify is open."
    assert ran == [("open_app", {"name": "Spotify"})]
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["tool_use_id"] == "t1" and result["content"] == "ok"
    assert fake.calls[0]["fallbacks"] == "default"


def test_failed_tool_is_reported_as_error(monkeypatch):
    def boom(name, args):
        raise RuntimeError("no such app")

    monkeypatch.setattr(brain, "run_tool", boom)
    tool_call = NS(type="tool_use", id="t1", name="open_app", input={"name": "Nope"})
    b, fake = make_brain(
        [
            NS(stop_reason="tool_use", content=[tool_call]),
            NS(stop_reason="end_turn", content=[NS(type="text", text="I couldn't find it.")]),
        ],
        monkeypatch,
    )

    b.run_command("open nope")
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True


def test_refusal_gets_a_spoken_reply(monkeypatch):
    b, _ = make_brain([NS(stop_reason="refusal", content=[])], monkeypatch)
    assert b.run_command("something") == "Sorry, I can't help with that one."
