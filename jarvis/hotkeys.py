"""Global hotkeys matched by physical key, not by the character typed.

pynput's GlobalHotKeys compares characters, and on a Mac holding Option
changes the character (Option+D types "∂"), so combinations with Option can
silently never fire. Matching the key code avoids that.
"""

from collections.abc import Callable

# macOS virtual key codes for an ANSI (US-style) keyboard.
MAC_KEY_CODES = {
    "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
    "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19,
    "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28, "0": 29, "o": 31,
    "u": 32, "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "n": 45, "m": 46,
    "space": 49,
}

MODIFIER_NAMES = {"ctrl", "alt", "shift", "cmd"}


def parse(combo: str) -> tuple[frozenset[str], str]:
    """'<ctrl>+<alt>+d' -> ({'ctrl', 'alt'}, 'd')."""
    parts = [p.strip().strip("<>").lower() for p in combo.split("+")]
    *modifiers, key = parts
    if key in MODIFIER_NAMES:
        raise ValueError(f"Hotkey {combo!r} has no key besides modifiers")
    unknown = set(modifiers) - MODIFIER_NAMES
    if unknown:
        raise ValueError(f"Unknown modifier in hotkey {combo!r}: {', '.join(sorted(unknown))}")
    return frozenset(modifiers), key


def key_matches(key, name: str, system: str) -> bool:
    """Whether a pynput key event is the key called `name` ('d', 'space', ...)."""
    vk = getattr(key, "vk", None)
    if system == "mac" and name in MAC_KEY_CODES:
        return vk == MAC_KEY_CODES[name]
    if system == "windows" and len(name) == 1 and name.isalnum():
        return vk == ord(name.upper())
    char = getattr(key, "char", None)
    if char is not None and char.lower() == name:
        return True
    return len(name) == 1 and vk == ord(name)


class HotkeyMatcher:
    """Feeds on key presses and releases; calls a binding when its combo is hit."""

    def __init__(
        self,
        bindings: dict[str, Callable[[], None]],
        system: str,
        modifier_of: Callable[[object], str | None],
    ):
        self.bindings = [(*parse(combo), action) for combo, action in bindings.items()]
        self.system = system
        self.modifier_of = modifier_of
        self.held: set[str] = set()

    def press(self, key) -> None:
        modifier = self.modifier_of(key)
        if modifier:
            self.held.add(modifier)
            return
        for modifiers, name, action in self.bindings:
            if self.held == modifiers and key_matches(key, name, self.system):
                action()

    def release(self, key) -> None:
        modifier = self.modifier_of(key)
        if modifier:
            self.held.discard(modifier)


def start_listener(bindings: dict[str, Callable[[], None]], system: str):
    """Starts listening in the background and returns the pynput listener."""
    from pynput import keyboard

    Key = keyboard.Key
    groups = {
        "ctrl": ("ctrl", "ctrl_l", "ctrl_r"),
        "alt": ("alt", "alt_l", "alt_r", "alt_gr"),
        "shift": ("shift", "shift_l", "shift_r"),
        "cmd": ("cmd", "cmd_l", "cmd_r"),
    }
    lookup = {
        getattr(Key, member): group
        for group, members in groups.items()
        for member in members
        if hasattr(Key, member)
    }

    def modifier_of(key):
        try:
            return lookup.get(key)
        except TypeError:  # unhashable key objects on some platforms
            return None

    matcher = HotkeyMatcher(bindings, system, modifier_of)
    listener = keyboard.Listener(on_press=matcher.press, on_release=matcher.release)
    listener.start()
    return listener
