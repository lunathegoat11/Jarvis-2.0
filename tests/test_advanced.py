import json
import threading
import types
from datetime import datetime, timedelta

import pytest

from jarvis import brain, info, memory, timers, tools, voice
from jarvis.config import Config


# ---- memory -------------------------------------------------------------------


def test_memory_remembers_forgets_and_reaches_the_prompt(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "config", Config(data_dir=tmp_path))
    assert memory.prompt_section() == ""
    assert memory.remember("Lives in  Princeton, NJ") == "Got it, I'll remember that."
    assert memory.remember("lives in princeton, nj") == "I already knew that."
    memory.remember("Has a geography test on Friday")
    section = memory.prompt_section()
    assert "- Lives in Princeton, NJ" in section and "geography" in section
    assert memory.forget("geography") == "Forgotten."
    assert memory.forget("geography") == "I don't have anything saved about that."
    assert [f["text"] for f in memory.load()] == ["Lives in Princeton, NJ"]


def test_command_instructions_include_memories(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "config", Config(data_dir=tmp_path))
    memory.remember("Name is Shlok")
    fake = brain.Brain.__new__(brain.Brain)
    assert fake._command_system().endswith("- Name is Shlok")


def test_memory_tools_are_offered():
    names = {t["name"] for t in tools.command_tools(can_see_screen=False)}
    assert {"remember", "forget", "get_weather", "get_news", "set_timer", "remind_me",
            "list_timers", "cancel_timer"} <= names


# ---- weather and news -------------------------------------------------------


def _fake_web(monkeypatch, replies):
    asked = []

    def get(url, params=None):
        asked.append((url, params))
        for start, body in replies.items():
            if url.startswith(start):
                return body if isinstance(body, bytes) else json.dumps(body).encode()
        raise AssertionError(url)

    monkeypatch.setattr(info, "_get", get)
    return asked


GEOCODE = {
    "results": [
        {"name": "Princeton", "admin1": "Indiana", "country": "United States",
         "country_code": "US", "latitude": 38.3, "longitude": -87.5},
        {"name": "Princeton", "admin1": "New Jersey", "country": "United States",
         "country_code": "US", "latitude": 40.35, "longitude": -74.66},
    ]
}
FORECAST = {
    "current": {"temperature_2m": 54.2, "apparent_temperature": 50.6, "weather_code": 2,
                "wind_speed_10m": 8.4},
    "daily": {"time": ["d1", "d2", "d3"], "weather_code": [61, 0, 3],
              "temperature_2m_max": [61, 58, 55], "temperature_2m_min": [45, 40, 41],
              "precipitation_probability_max": [70, 0, 10]},
}


def test_weather_picks_the_right_place_and_us_units(monkeypatch):
    monkeypatch.setattr(info, "config", Config(location="", units="auto"))
    asked = _fake_web(monkeypatch, {info.GEOCODE_URL: GEOCODE, info.FORECAST_URL: FORECAST})
    report = info.weather("Princeton, NJ")
    assert asked[0][1]["name"] == "Princeton"
    forecast_params = asked[1][1]
    assert forecast_params["latitude"] == 40.35 and forecast_params["temperature_unit"] == "fahrenheit"
    assert report.startswith("Princeton, New Jersey, now: 54°F (feels like 51°F), partly cloudy")
    assert "Today: light rain, high 61°F, low 45°F, 70% chance of rain or snow." in report


def test_weather_without_a_place_asks_for_one(monkeypatch):
    monkeypatch.setattr(info, "config", Config(location=""))
    with pytest.raises(RuntimeError, match="don't know where you are"):
        info.weather("")


def test_news_lists_headlines(monkeypatch):
    rss = b"""<rss><channel>
      <item><title>Rover finds water</title><description>A big day.</description></item>
      <item><title>Markets calm</title></item>
      <item><title>Third story</title></item>
    </channel></rss>"""
    _fake_web(monkeypatch, {"https://feeds.bbci.co.uk/news/science": rss})
    assert info.news("science", 2) == (
        "Headlines from BBC News:\n- Rover finds water: A big day.\n- Markets calm"
    )


# ---- timers, reminders, briefing ----------------------------------------------


class Clock:
    def __init__(self, start: datetime):
        self.at = start

    def time(self):
        return self.at.timestamp()

    def now(self):
        return self.at


def _scheduler(tmp_path, clock, briefing=None):
    said = []
    scheduler = timers.Scheduler(
        said.append, briefing, path=tmp_path / "timers.json", clock=clock.time, now=clock.now
    )
    return scheduler, said


def test_timer_goes_off_once_and_survives_a_restart(tmp_path):
    clock = Clock(datetime(2026, 10, 16, 18, 0))
    scheduler, said = _scheduler(tmp_path, clock)
    assert scheduler.add_timer(600, "pasta") == "Timer set for 10 minutes for pasta."
    assert "in 10 minutes" in scheduler.pending()
    # Jarvis restarts: the timer is still there.
    scheduler, said = _scheduler(tmp_path, clock)
    clock.at += timedelta(minutes=9)
    scheduler.check()
    assert said == []
    clock.at += timedelta(minutes=1)
    scheduler.check()
    scheduler.check()
    assert said == ["Time's up for pasta."]
    assert scheduler.pending() == "No timers or reminders set."


def test_reminder_missed_while_off_says_when_it_was_due(tmp_path):
    clock = Clock(datetime(2026, 10, 16, 16, 0))
    scheduler, said = _scheduler(tmp_path, clock)
    assert scheduler.add_reminder("2026-10-16 17:00", "call grandma").startswith("I'll remind you")
    with pytest.raises(ValueError, match="already passed"):
        scheduler.add_reminder("2026-10-16 15:00", "too late")
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        scheduler.add_reminder("5pm", "bad format")
    clock.at = datetime(2026, 10, 16, 17, 30)
    scheduler.check()
    assert said == ["Reminder: call grandma (This was due at 17:00.)"]


def test_cancel_by_words_or_all(tmp_path):
    clock = Clock(datetime(2026, 10, 16, 18, 0))
    scheduler, _ = _scheduler(tmp_path, clock)
    scheduler.add_timer(60, "tea")
    scheduler.add_timer(120, "pasta")
    scheduler.add_timer(180, "")
    assert scheduler.cancel("pasta") == "Cancelled."
    assert scheduler.cancel("nothing like it") == "I couldn't find that timer or reminder."
    assert scheduler.cancel("all") == "Cancelled 2."


def test_briefing_runs_once_a_day_and_catches_up_after_sleep(tmp_path, monkeypatch):
    monkeypatch.setattr(timers, "config", Config(briefing_time="07:30"))
    clock = Clock(datetime(2026, 10, 16, 7, 0))
    briefings = []
    scheduler, _ = _scheduler(tmp_path, clock, briefing=lambda: briefings.append(clock.at))
    scheduler.check()
    assert briefings == []
    clock.at = datetime(2026, 10, 16, 8, 10)  # the Mac was asleep at 7:30
    scheduler.check()
    scheduler.check()
    assert len(briefings) == 1
    clock.at = datetime(2026, 10, 17, 11, 0)  # too late: wait for tomorrow
    scheduler.check()
    assert len(briefings) == 1
    clock.at = datetime(2026, 10, 18, 7, 30)
    scheduler.check()
    assert len(briefings) == 2


def test_timer_tools_use_the_running_scheduler(tmp_path, monkeypatch):
    clock = Clock(datetime(2026, 10, 16, 18, 0))
    scheduler, _ = _scheduler(tmp_path, clock)
    monkeypatch.setattr(timers, "_scheduler", scheduler)
    assert tools.run_tool("set_timer", {"seconds": 90, "label": ""}) == (
        "Timer set for 1 minute 30 seconds."
    )
    assert "Time's up. That was 1 minute 30 seconds." in tools.run_tool("list_timers", {})


# ---- streaming ------------------------------------------------------------------


def _spoken(pieces):
    out = []
    filt = brain.SpokenText(out.append)
    for piece in pieces:
        filt.feed(piece)
    filt.close()
    return "".join(out)


def test_spoken_text_skips_thinking_even_when_split_across_pieces():
    assert _spoken(["<thi", "nk>plan it</th", "ink>Hello", " there."]) == "Hello there."
    assert _spoken(["Sure. <think>x</think>Done."]) == "Sure. Done."
    assert _spoken(["5 < 6 is true."]) == "5 < 6 is true."


def test_spoken_text_holds_back_a_service_error():
    assert _spoken(["[ERR", "OR: Agent failed (timed out)]"]) == ""
    assert _spoken(["Hi"]) == "Hi"  # short replies still come through at the end


def test_speech_stream_says_sentences_as_they_complete(monkeypatch):
    said = []
    first_sentence_said = threading.Event()

    def speak(text):
        said.append(text)
        first_sentence_said.set()

    monkeypatch.setattr(voice, "engine", lambda: "system")
    monkeypatch.setattr(voice, "_speak_system", speak)
    started = []
    stream = voice.SpeechStream(on_start=lambda: started.append(True))
    stream.feed("It's **sunny** today. Hig")
    assert first_sentence_said.wait(2)  # said before the reply is finished
    assert said == ["It's sunny today."]
    stream.feed("h of 61.\n- Bring a jacket")
    stream.finish()
    assert said == ["It's sunny today.", "High of 61.", "Bring a jacket."]
    assert started == [True] and stream.spoke
    assert "Bring a jacket" in stream.heard


def test_speech_stream_goes_quiet_when_stopped(monkeypatch):
    said = []
    monkeypatch.setattr(voice, "engine", lambda: "system")
    monkeypatch.setattr(voice, "_speak_system", said.append)
    stream = voice.SpeechStream()
    voice.stop()
    stream.feed("You should not hear this. Or this.")
    stream.finish()
    assert said == []


def _chunk(content=None, tool_calls=None):
    delta = types.SimpleNamespace(content=content, tool_calls=tool_calls, refusal=None)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(delta=delta)])


def _tool_piece(index, id=None, name=None, arguments=None):
    return types.SimpleNamespace(
        index=index, id=id, function=types.SimpleNamespace(name=name, arguments=arguments)
    )


def test_openai_style_stream_is_spoken_and_reassembled(monkeypatch):
    fake = brain.OpenAICompatibleBrain.__new__(brain.OpenAICompatibleBrain)
    chunks = [
        _chunk("<think>hmm</think>Checking "),
        _chunk("the weather."),
        _chunk(tool_calls=[_tool_piece(0, id="c1", name="get_weather", arguments='{"pla')]),
        _chunk(tool_calls=[_tool_piece(0, arguments='ce": ""}')]),
    ]
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return iter(chunks)

    fake._create = create
    monkeypatch.setattr(brain, "config", Config(provider="nvidia"))
    heard = []
    step = fake._step("system", [], [], "model", "medium", on_text=heard.append)
    assert requests[0]["stream"] is True
    assert "".join(heard) == "Checking the weather."
    assert step.text == "Checking the weather."
    assert [(c.id, c.name, c.args) for c in step.calls] == [("c1", "get_weather", {"place": ""})]
    assert step.assistant["tool_calls"][0]["function"]["arguments"] == '{"place": ""}'


def test_claude_stream_passes_text_and_keeps_the_full_reply(monkeypatch):
    final = types.SimpleNamespace(
        content=[types.SimpleNamespace(type="text", text="Hello there.")],
        stop_reason="end_turn",
    )

    class Stream:
        text_stream = iter(["Hello ", "there."])

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return final

    asked = []

    class Messages:
        def stream(self, **kwargs):
            asked.append(kwargs)
            return Stream()

    fake = brain.AnthropicBrain.__new__(brain.AnthropicBrain)
    fake.client = types.SimpleNamespace(beta=types.SimpleNamespace(messages=Messages()))
    heard = []
    step = fake._step("system", [], [], "claude-sonnet-5-5", "medium", on_text=heard.append)
    assert heard == ["Hello ", "there."] and step.text == "Hello there."
    assert asked[0]["fallbacks"] == "default" and asked[0]["model"] == "claude-sonnet-5-5"


# ---- the voice path ---------------------------------------------------------------


def _jarvis_for(monkeypatch, brain_obj, quick_reply=None):
    import numpy as np

    from jarvis import main

    class HUD:
        def __init__(self):
            self.calls = []

        def __getattr__(self, name):
            return lambda *a, **k: self.calls.append(name)

    jarvis = main.Jarvis.__new__(main.Jarvis)
    jarvis.hud, jarvis.brain, jarvis._job, jarvis._busy = HUD(), brain_obj, 0, True
    jarvis.transcriber = types.SimpleNamespace(transcribe=lambda audio, vocab: "what's the weather")
    monkeypatch.setattr(main.router, "route", lambda text: ("command", text))
    monkeypatch.setattr(main.prefs, "get", lambda key, default=None: True if key == "speak_replies" else "")
    monkeypatch.setattr(
        main.quick, "match", lambda text: types.SimpleNamespace(action="x") if quick_reply else None
    )
    monkeypatch.setattr(main.quick, "run", lambda q: quick_reply)
    streamed, spoken_whole = [], []
    monkeypatch.setattr(voice, "engine", lambda: "system")
    monkeypatch.setattr(voice, "_speak_system", streamed.append)
    monkeypatch.setattr(main.desktop, "speak", spoken_whole.append)
    audio = np.full(16000, 0.2, dtype=np.float32)
    return jarvis, audio, streamed, spoken_whole


def test_a_streamed_reply_is_spoken_once_as_it_arrives(monkeypatch):
    class Brain:
        model = "m"

        def run_command(self, text, on_text=None):
            on_text("It's 54 degrees. ")
            on_text("Bring a jacket.")
            return "It's 54 degrees. Bring a jacket."

    jarvis, audio, streamed, whole = _jarvis_for(monkeypatch, Brain())
    jarvis.handle("auto", audio)
    assert streamed == ["It's 54 degrees.", "Bring a jacket."]
    assert whole == []


def test_a_reply_that_wasnt_streamed_is_still_spoken(monkeypatch):
    jarvis, audio, streamed, whole = _jarvis_for(monkeypatch, object(), quick_reply="Opened Safari.")
    jarvis.handle("auto", audio)
    assert streamed == [] and whole == ["Opened Safari."]
