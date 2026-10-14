import pytest

from jarvis.holdkeys import FLAG_BITS, HoldTracker

FN, RIGHT_CMD, RIGHT_OPT, LEFT_SHIFT = 63, 54, 61, 56


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


@pytest.fixture
def setup():
    events = []
    clock = Clock()
    tracker = HoldTracker(
        {"fn": "dictate", "right_cmd": "ask", "right_option": "command"},
        start=lambda m: events.append(("start", m)),
        stop=lambda m: events.append(("stop", m)),
        cancel=lambda m: events.append(("cancel", m)),
        clock=clock,
    )
    return tracker, events, clock


def hold(tracker, clock, code, name, seconds):
    tracker.modifiers_changed(code, FLAG_BITS[name])
    clock.now += seconds
    tracker.modifiers_changed(code, 0)


def test_holding_each_key_runs_its_mode(setup):
    tracker, events, clock = setup
    hold(tracker, clock, FN, "fn", 2.0)
    hold(tracker, clock, RIGHT_CMD, "right_cmd", 1.5)
    hold(tracker, clock, RIGHT_OPT, "right_option", 1.0)
    assert events == [
        ("start", "dictate"), ("stop", "dictate"),
        ("start", "ask"), ("stop", "ask"),
        ("start", "command"), ("stop", "command"),
    ]


def test_a_quick_tap_is_thrown_away(setup):
    tracker, events, clock = setup
    hold(tracker, clock, FN, "fn", 0.1)
    assert events == [("start", "dictate"), ("cancel", "dictate")]


def test_a_shortcut_with_right_command_is_not_speech(setup):
    tracker, events, clock = setup
    tracker.modifiers_changed(RIGHT_CMD, FLAG_BITS["right_cmd"])
    tracker.key_pressed()  # the C of Cmd+C
    clock.now += 1.0
    tracker.modifiers_changed(RIGHT_CMD, 0)
    assert events == [("start", "ask"), ("cancel", "ask")]


def test_adding_another_modifier_cancels(setup):
    tracker, events, clock = setup
    tracker.modifiers_changed(RIGHT_OPT, FLAG_BITS["right_option"])
    tracker.modifiers_changed(LEFT_SHIFT, FLAG_BITS["right_option"] | 0x02)
    clock.now += 1.0
    tracker.modifiers_changed(RIGHT_OPT, 0)
    assert events[-1] == ("cancel", "command")


def test_left_command_does_nothing(setup):
    tracker, events, clock = setup
    tracker.modifiers_changed(55, 0x08 | (1 << 20))  # left Command down
    tracker.modifiers_changed(55, 0)
    assert events == []


def test_unknown_key_name_is_rejected():
    with pytest.raises(ValueError, match="right_cmd"):
        HoldTracker({"capslock": "dictate"}, print, print, print)
