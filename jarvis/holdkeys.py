"""Hold-to-talk on a Mac: hold fn, right Command or right Option to talk,
let go to send.

Single modifier keys can't be caught by ordinary hotkey code, so this reads
macOS's "modifier keys changed" events directly. Those carry a key code and
the full set of modifier flags, including bits that tell left from right.

So that normal shortcuts still work, a hold is thrown away if another key is
pressed while it's down (right Command + C stays a copy), or if it's let go
too quickly to have been speech.
"""

import time
from collections.abc import Callable

# Key codes from macOS's Events.h. The fn/Globe key reports 63; some
# keyboards report 179 for Globe.
KEY_CODES = {
    "fn": (63, 179),
    "right_cmd": (54,),
    "right_option": (61,),
    "right_ctrl": (62,),
    "right_shift": (60,),
}

# Bits in the event's modifier flags that are set while each key is down.
FLAG_BITS = {
    "fn": 1 << 23,  # NSEventModifierFlagFunction
    "right_cmd": 0x10,  # NX_DEVICERCMDKEYMASK
    "right_option": 0x40,  # NX_DEVICERALTKEYMASK
    "right_ctrl": 0x2000,  # NX_DEVICERCTLKEYMASK
    "right_shift": 0x04,  # NX_DEVICERSHIFTKEYMASK
}

# Holds shorter than this are taps, not speech.
MIN_HOLD_SECONDS = 0.3


class HoldTracker:
    """Turns raw modifier events into start / stop / cancel calls."""

    def __init__(
        self,
        bindings: dict[str, str],
        start: Callable[[str], None],
        stop: Callable[[str], None],
        cancel: Callable[[str], None],
        clock: Callable[[], float] = time.monotonic,
    ):
        unknown = set(bindings) - set(KEY_CODES)
        if unknown:
            raise ValueError(
                f"Unknown hold key(s): {', '.join(sorted(unknown))}. "
                f"Choose from: {', '.join(KEY_CODES)}"
            )
        self.bindings = bindings  # key name -> mode
        self.start, self.stop, self.cancel = start, stop, cancel
        self.clock = clock
        self.active: str | None = None  # key name being held
        self.started_at = 0.0
        self.spoiled = False

    def _key_for_code(self, code: int) -> str | None:
        for name in self.bindings:
            if code in KEY_CODES[name]:
                return name
        return None

    def modifiers_changed(self, code: int, flags: int) -> None:
        name = self._key_for_code(code)
        if name is None:
            # Another modifier joined in, e.g. right Command + Shift.
            if self.active:
                self.spoiled = True
            return
        down = bool(flags & FLAG_BITS[name])
        if down and self.active is None:
            self.active = name
            self.started_at = self.clock()
            self.spoiled = False
            self.start(self.bindings[name])
        elif not down and self.active == name:
            mode = self.bindings[name]
            held_for = self.clock() - self.started_at
            self.active = None
            if self.spoiled or held_for < MIN_HOLD_SECONDS:
                self.cancel(mode)
            else:
                self.stop(mode)
        elif down and self.active and self.active != name:
            # Two Jarvis keys at once; treat the second like any other key.
            self.spoiled = True

    def key_pressed(self) -> None:
        """Any ordinary key went down."""
        if self.active:
            self.spoiled = True


ESCAPE_KEY_CODE = 53


def install(tracker: HoldTracker, on_escape: Callable[[], None] | None = None) -> list:
    """Starts watching the keyboard on macOS. Needs the AppKit run loop.

    Returns the monitor objects; keep them alive for as long as Jarvis runs.
    """
    from AppKit import NSEvent, NSEventMaskFlagsChanged, NSEventMaskKeyDown

    def on_flags(event):
        tracker.modifiers_changed(event.keyCode(), int(event.modifierFlags()))

    def on_key(event):
        tracker.key_pressed()
        if on_escape and event.keyCode() == ESCAPE_KEY_CODE:
            on_escape()

    def local(handler):
        def wrapped(event):
            handler(event)
            return event

        return wrapped

    return [
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSEventMaskFlagsChanged, on_flags),
        NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(NSEventMaskKeyDown, on_key),
        # Global monitors skip Jarvis's own events; local ones cover those.
        NSEvent.addLocalMonitorForEventsMatchingMask_handler_(NSEventMaskFlagsChanged, local(on_flags)),
        NSEvent.addLocalMonitorForEventsMatchingMask_handler_(NSEventMaskKeyDown, local(on_key)),
    ]
