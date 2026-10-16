"""Jarvis learning from corrections, from tasks that worked, and from habits."""

import types
from datetime import datetime, timedelta

from jarvis import brain, habits, memory, tools


# ---- lessons and skills -------------------------------------------------------------


def test_lessons_and_skills_are_kept_and_shown_to_the_ai():
    tools.run_tool("remember", {"fact": "Name is Shlok"})
    assert tools.run_tool(
        "learn_lesson", {"lesson": "'My email' means Gmail in Chrome, not the Mail app"}
    ) == "Lesson learned."
    tools.run_tool("save_skill", {
        "task": "play a YouTube video",
        "steps": "1. browse_open youtube.com/results?search_query=<words> 2. browse_click the first video",
    })
    section = memory.prompt_section()
    assert "- Name is Shlok" in section
    assert "Lessons you've learned" in section and "Gmail in Chrome" in section
    assert "- To play a YouTube video: 1. browse_open" in section


def test_saving_a_skill_again_replaces_its_steps():
    memory.save_skill("Play a YouTube video", "old steps")
    memory.save_skill("play a youtube video", "new steps")
    skills = [e for e in memory.load() if e["kind"] == "skill"]
    assert [s["text"] for s in skills] == ["new steps"]


def test_forget_covers_lessons_and_skills():
    memory.remember("Use Chrome for school sites", kind="lesson")
    memory.save_skill("check my grades", "1. browse_open the school portal")
    assert memory.forget("chrome") == "Forgotten."
    assert memory.forget("grades") == "Forgotten."
    assert memory.load() == []


def test_old_memory_files_without_kinds_still_load(private_data):
    private_data.mkdir(parents=True, exist_ok=True)
    (private_data / "memory.json").write_text('[{"text": "Lives in Princeton", "saved": "2026-10-16"}]')
    assert memory.load()[0]["kind"] == "fact"
    assert "- Lives in Princeton" in memory.prompt_section()


def test_misheard_words_go_into_the_dictionary(monkeypatch):
    from jarvis import prefs

    added = []
    monkeypatch.setattr(prefs, "add_words", lambda words: added.extend(words) or "")
    assert tools.run_tool("add_to_dictionary", {"words": ["Kosha", "Mr. Lee"]}) == "Added to the dictionary."
    assert added == ["Kosha", "Mr. Lee"]


def test_the_command_loop_notes_which_tools_it_used(monkeypatch):
    steps = [
        brain.Step(text="", calls=[brain.Call("1", "get_weather", {"place": ""})], assistant={}),
        brain.Step(text="Sunny.", calls=[], assistant={}),
    ]
    fake = brain.Brain.__new__(brain.Brain)
    brain.Brain.__init__(fake)
    fake.model = fake.vision_model = "m"
    fake._user = lambda text, image=None: [{"role": "user", "content": text}]
    fake._results = lambda results, image=None, note="": []
    fake._step = lambda *a, **k: steps.pop(0)
    monkeypatch.setattr(brain.Brain, "_run_command_tool", lambda self, call: ("54F", False))
    assert fake.run_command("weather?") == "Sunny."
    assert fake.last_calls == [("get_weather", {"place": ""})]


# ---- habits ----------------------------------------------------------------------------


def test_requests_are_grouped_by_what_jarvis_did():
    assert habits.signature([("get_weather", {"place": "Princeton"})], "what's the weather") == "get_weather"
    assert habits.signature([("open_app", {"name": "Spotify"})], "open spotify") == "open_app:spotify"
    assert habits.signature(
        [("remember", {"fact": "x"}), ("browse_open", {"url": "https://www.youtube.com/watch?v=1"})], "x"
    ) == "browse_open:youtube.com"
    assert habits.signature([], "Tell me a joke!") == "say:tell me a joke"


def _log(days_and_times, calls, said):
    start = datetime(2026, 10, 1)
    for day, hhmm in days_and_times:
        hour, minute = map(int, hhmm.split(":"))
        habits.record(said, calls, when=start + timedelta(days=day, hours=hour, minutes=minute))


def test_a_habit_needs_three_days_at_about_the_same_time():
    now = datetime(2026, 10, 10, 12, 0)
    _log([(1, "07:55"), (2, "08:10")], [("get_weather", {})], "what's the weather")
    assert habits.find(now) == []
    _log([(4, "08:20")], [("get_weather", {})], "do I need a coat")
    found = habits.find(now)
    assert len(found) == 1
    assert found[0]["did"] == "get_weather" and found[0]["time"] == "08:10"
    assert found[0]["said"] == "do I need a coat"  # the latest words
    # Something done at scattered times isn't a habit.
    _log([(1, "09:00"), (2, "13:00"), (3, "20:00")], [("open_app", {"name": "Notes"})], "open notes")
    assert [h["did"] for h in habits.find(now)] == ["get_weather"]
    assert 'Around 08:10: "do I need a coat"' in habits.prompt_section()


def test_one_odd_day_does_not_hide_a_habit():
    _log([(1, "16:00"), (2, "16:20"), (3, "16:05"), (4, "22:00")],
         [("open_app", {"name": "Spotify"})], "open spotify")
    found = habits.find(datetime(2026, 10, 10))
    assert found[0]["time"] == "16:05" and found[0]["days"] == 3


def test_a_habit_is_offered_once_around_its_time_unless_already_done():
    _log([(1, "08:00"), (2, "08:00"), (3, "08:00")], [("get_weather", {})], "what's the weather")
    assert habits.due_suggestion(datetime(2026, 10, 9, 7, 30)) is None  # too early
    offered = habits.due_suggestion(datetime(2026, 10, 9, 8, 2))
    assert offered["said"] == "what's the weather"
    assert habits.due_suggestion(datetime(2026, 10, 9, 8, 5)) is None  # once a day
    # Already done today: no offer.
    _log([(9, "07:58")], [("get_weather", {})], "weather")
    assert habits.due_suggestion(datetime(2026, 10, 10, 8, 2)) is None


def test_stop_suggesting_a_habit():
    _log([(1, "08:00"), (2, "08:00"), (3, "08:00")], [("get_weather", {})], "what's the weather")
    assert habits.stop_suggesting("pizza") == "I haven't noticed a habit like that."
    assert habits.stop_suggesting("weather") == "OK, I won't suggest that any more."
    assert habits.find() == []


def test_yes_means_yes():
    assert habits.is_yes("Yes.") and habits.is_yes("sure thing!") and habits.is_yes("Go ahead")
    assert not habits.is_yes("yes, but open Safari first")


# ---- the offer, end to end ----------------------------------------------------------------


def test_offering_a_habit_and_saying_yes_does_it(monkeypatch):
    import numpy as np

    from jarvis import main

    class HUD:
        def __getattr__(self, name):
            return lambda *a, **k: None

    jarvis = main.Jarvis.__new__(main.Jarvis)
    jarvis.hud, jarvis._job, jarvis._busy, jarvis.offer = HUD(), 0, False, None
    jarvis.recorder = types.SimpleNamespace(recording=False)
    monkeypatch.setattr(main.config.__class__, "habit_suggestions", True, raising=False)
    said = []
    monkeypatch.setattr(jarvis, "announce", lambda text, to_phone=True: said.append((text, to_phone)),
                        raising=False)
    monkeypatch.setattr(main.habits, "due_suggestion", lambda: {"said": "what's the weather"})
    jarvis.offer_habit()
    assert said == [('You usually ask me "what\'s the weather" around now. Want me to? Just say yes.', False)]

    commands = []

    class Brain:
        model = "m"
        last_calls = [("get_weather", {})]

        def run_command(self, text, on_text=None):
            commands.append(text)
            return "It's sunny."

    jarvis.brain = Brain()
    jarvis.transcriber = types.SimpleNamespace(transcribe=lambda audio, vocab: "Yes please.")
    monkeypatch.setattr(main.router, "route", lambda text: ("dictate", text))  # must be skipped
    monkeypatch.setattr(main.prefs, "get", lambda key, default=None: False if key == "speak_replies" else "")
    monkeypatch.setattr(main.quick, "match", lambda text: None)
    jarvis.handle("auto", np.full(16000, 0.2, dtype=np.float32))
    assert commands == ["what's the weather"]
    assert jarvis.offer is None
    assert habits._entries()[-1]["did"] == "get_weather"
