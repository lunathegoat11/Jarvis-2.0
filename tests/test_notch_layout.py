from jarvis.notch_layout import CARD_MAX_BODY_HEIGHT, CARD_WIDTH, EAR, NO_NOTCH_SIZE, card_frame, island_frames
from jarvis.hud import reply_seconds


def test_island_grows_sideways_out_of_the_notch():
    # A 1470x956 point screen with a 180x32 notch.
    collapsed, expanded = island_frames(0, 1470, 956, 180, 32)
    assert collapsed == (645, 924, 180, 32)
    assert expanded == (645 - EAR, 924, 180 + 2 * EAR, 32)


def test_screen_without_notch_gets_a_small_pill():
    collapsed, _ = island_frames(0, 1920, 1080, 0, 0)
    assert collapsed[2:] == NO_NOTCH_SIZE
    assert collapsed[1] == 1080 - NO_NOTCH_SIZE[1]


def test_card_hangs_below_and_is_centered():
    x, y, w, h = card_frame(0, 1470, 924, 16, 40)
    assert w == CARD_WIDTH and x == (1470 - CARD_WIDTH) / 2
    assert y + h < 924


def test_card_body_height_is_capped():
    _, _, _, tall = card_frame(0, 1470, 924, 16, 5000)
    _, _, _, capped = card_frame(0, 1470, 924, 16, CARD_MAX_BODY_HEIGHT)
    assert tall == capped


def test_reply_seconds_bounds():
    assert reply_seconds("ok") == 4.0
    assert reply_seconds("word " * 1000) == 15.0
