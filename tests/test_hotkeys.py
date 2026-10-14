from types import SimpleNamespace as NS

import pytest

from jarvis.hotkeys import HotkeyMatcher, key_matches, parse


def test_parse():
    assert parse("<ctrl>+<alt>+d") == (frozenset({"ctrl", "alt"}), "d")
    assert parse("<cmd>+<shift>+<space>") == (frozenset({"cmd", "shift"}), "space")
    with pytest.raises(ValueError):
        parse("<ctrl>+<alt>")
    with pytest.raises(ValueError):
        parse("<hyper>+d")


def test_mac_matches_by_key_code_even_when_option_changes_the_character():
    option_d = NS(vk=2, char="∂")
    assert key_matches(option_d, "d", "mac")
    assert not key_matches(NS(vk=0, char="d"), "d", "mac")


def test_windows_matches_control_characters_by_key_code():
    ctrl_d = NS(vk=0x44, char="\x04")
    assert key_matches(ctrl_d, "d", "windows")


def test_matcher_needs_exactly_the_right_modifiers():
    fired = []
    mods = {"CTRL": "ctrl", "ALT": "alt", "SHIFT": "shift"}
    matcher = HotkeyMatcher(
        {"<ctrl>+<alt>+d": lambda: fired.append("d")},
        "mac",
        lambda key: mods.get(key) if isinstance(key, str) else None,
    )
    d = NS(vk=2, char="∂")

    matcher.press("CTRL")
    matcher.press(d)
    assert fired == []  # Alt not held yet

    matcher.press("ALT")
    matcher.press(d)
    assert fired == ["d"]

    matcher.press("SHIFT")
    matcher.press(d)
    assert fired == ["d"]  # an extra modifier doesn't count

    matcher.release("SHIFT")
    matcher.release("ALT")
    matcher.press(d)
    assert fired == ["d"]
