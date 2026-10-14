import pytest

from jarvis import quick
from jarvis.quick import Quick, match


@pytest.mark.parametrize(
    "said, action, args",
    [
        ("Open a new tab.", "new_tab", {}),
        ("Jarvis, can you open a new tab please?", "new_tab", {}),
        ("new tab", "new_tab", {}),
        ("Close this tab.", "browser_key", {"keys": "cmd+w"}),
        ("Reopen the last closed tab", "browser_key", {"keys": "cmd+shift+t"}),
        ("Go back.", "browser_key", {"keys": "cmd+["}),
        ("Refresh the page", "browser_key", {"keys": "cmd+r"}),
        ("Search for best pizza near me", "search", {"query": "best pizza near me", "site": "google"}),
        ("Search YouTube for lofi beats", "search", {"query": "lofi beats", "site": "youtube"}),
        ("Play Bohemian Rhapsody on YouTube.", "search", {"query": "bohemian rhapsody", "site": "youtube"}),
        ("Open YouTube", "open", {"target": "youtube"}),
        ("Open Spotify.", "open", {"target": "spotify"}),
        ("Go to bbc.co.uk", "open", {"target": "bbc co uk"}),
        ("Pause the music", "media", {"action": "play_pause"}),
        ("Skip this song", "media", {"action": "next"}),
        ("Volume up", "volume", {"change": 10}),
        ("Set the volume to 30%", "volume", {"level": 30}),
        ("Mute", "volume", {"mute": True}),
        ("What time is it?", "time", {}),
        ("What’s the date today?", "date", {}),
        ("Remember that my locker code is 4512", "save_note", {"text": "my locker code is 4512"}),
    ],
)
def test_matches(said, action, args):
    result = match(said)
    assert result is not None, said
    assert result.action == action
    for key, value in args.items():
        assert result.args[key] == value


@pytest.mark.parametrize(
    "said",
    [
        "Open a new tab and go to YouTube",
        "Open the document I was working on yesterday",
        "Write an email to my teacher saying I'm sick",
        "Stop",
        "How tall is Mount Everest?",
    ],
)
def test_harder_requests_go_to_the_ai(said):
    assert match(said) is None


def test_open_prefers_websites_then_apps(monkeypatch):
    opened = []
    monkeypatch.setattr(quick.desktop, "open_url", lambda url: opened.append(("url", url)))
    monkeypatch.setattr(quick.desktop, "open_app", lambda name: opened.append(("app", name)))

    quick.run(Quick("open", {"target": "youtube"}))
    quick.run(Quick("open", {"target": "spotify"}))
    quick.run(Quick("open", {"target": "nytimes", "site_only": True}))
    assert opened == [("url", "youtube.com"), ("app", "spotify"), ("url", "nytimes.com")]


def test_missing_app_is_reported(monkeypatch):
    def fail(name):
        raise RuntimeError("not found")

    monkeypatch.setattr(quick.desktop, "open_app", fail)
    assert quick.run(Quick("open", {"target": "zzz"})) == "I couldn't find an app called zzz."


def test_browser_shortcut_needs_a_browser_in_front(monkeypatch):
    monkeypatch.setattr(quick.desktop, "browser_shortcut", lambda keys: "not_browser:Notes")
    reply = quick.run(Quick("browser_key", {"keys": "cmd+w", "done": "Closed the tab."}))
    assert "Notes" in reply
