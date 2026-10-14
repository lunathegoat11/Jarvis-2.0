"""Where the notch panel and glass card go on screen.

Kept apart from notch.py, which needs macOS, so it can be tested anywhere.
Rectangles are (x, y, width, height) in macOS screen points, where y grows
upwards from the bottom of the screen.
"""

# Width added on each side of the notch while Jarvis is active.
EAR = 84
CARD_WIDTH = 380
CARD_GAP = 8
CARD_PADDING = 16
CARD_MAX_BODY_HEIGHT = 260

# Size used on screens without a notch, such as an external display.
NO_NOTCH_SIZE = (120, 28)


def island_frames(screen_x, screen_w, screen_top, notch_w, notch_h):
    """Returns (collapsed, expanded) frames for the black notch panel.

    Collapsed is exactly the notch, so the panel can appear to grow out of it.
    """
    if notch_w <= 0 or notch_h <= 0:
        notch_w, notch_h = NO_NOTCH_SIZE
    center = screen_x + screen_w / 2
    y = screen_top - notch_h
    collapsed = (center - notch_w / 2, y, notch_w, notch_h)
    width = notch_w + 2 * EAR
    expanded = (center - width / 2, y, width, notch_h)
    return collapsed, expanded


def card_frame(screen_x, screen_w, island_bottom, title_h, body_h):
    """Frame of the glass card that hangs below the notch panel."""
    body_h = min(body_h, CARD_MAX_BODY_HEIGHT)
    height = CARD_PADDING + title_h + 6 + body_h + CARD_PADDING
    x = screen_x + (screen_w - CARD_WIDTH) / 2
    return (x, island_bottom - CARD_GAP - height, CARD_WIDTH, height)
