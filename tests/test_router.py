import pytest

from jarvis.router import route


@pytest.mark.parametrize(
    "said, mode, text",
    [
        ("Type, see you at six.", "dictate", "see you at six."),
        ("type hey how's it going", "dictate", "hey how's it going"),
        ("Write: dear Mr. Smith, I'm sorry I missed class.", "dictate", "dear Mr. Smith, I'm sorry I missed class."),
        ("Jarvis, dictate this the meeting is moved to Friday", "dictate", "the meeting is moved to Friday"),
        ("Write an email to my teacher saying I'm sick.", "command", None),
        ("What's on my screen?", "ask", None),
        ("What does this error mean?", "ask", None),
        ("Summarize this page.", "ask", None),
        ("What am I looking at?", "ask", None),
        ("Explain this.", "ask", None),
        ("Use my screen to play the latest MrBeast video.", "command", None),
        ("Close this tab.", "command", None),
        ("Open YouTube.", "command", None),
        ("Play the latest MrBeast video.", "command", None),
        ("Check my email.", "command", None),
        ("Tell me a joke.", "command", None),
        ("What's the weather tomorrow?", "command", None),
    ],
)
def test_route(said, mode, text):
    got_mode, got_text = route(said)
    assert got_mode == mode
    assert got_text == (text if text is not None else said.strip())


@pytest.mark.parametrize(
    "said",
    [
        "Make this more formal.",
        "Fix the grammar.",
        "Translate this into Spanish.",
        "Rewrite it as bullet points.",
        "Jarvis, shorten this.",
        "Turn this into a haiku.",
    ],
)
def test_edit_requests(said):
    assert route(said) == ("edit", said)


def test_write_down_keeps_all_the_words():
    assert route("Write down milk, eggs and bread.") == ("dictate", "milk, eggs and bread.")
