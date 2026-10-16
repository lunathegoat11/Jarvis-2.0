"""Claude's computer-use toolset (computer_toolset_20260801), carried out on
this computer.

Claude is trained to aim with this toolset, so with Claude, screen control
uses it instead of Jarvis's own simpler screen tools (screen.py), which
other providers still use. Claude asks for actions like left_click or type,
often several in one turn, with coordinates in the pixels of the latest
screenshot Jarvis sent it.
"""

import time

from . import desktop, screen

TOOLSET = {"type": "computer_toolset_20260801"}

# Claude names keys the way Linux's xdotool does ("Return", "ctrl+s",
# "super+Tab"); these are the pynput names for them. On a Mac, "super",
# "cmd" and "meta" all mean Command.
KEY_ALIASES = {
    "return": "enter", "enter": "enter", "kp_enter": "enter", "tab": "tab",
    "escape": "esc", "esc": "esc", "backspace": "backspace", "delete": "delete",
    "space": "space", "up": "up", "down": "down", "left": "left", "right": "right",
    "home": "home", "end": "end", "page_up": "page_up", "prior": "page_up",
    "page_down": "page_down", "next": "page_down", "ctrl": "ctrl", "control": "ctrl",
    "alt": "alt", "option": "alt", "shift": "shift", "super": "cmd", "cmd": "cmd",
    "command": "cmd", "meta": "cmd", "win": "cmd", "caps_lock": "caps_lock",
    **{f"f{n}": f"f{n}" for n in range(1, 13)},
}

HALTED = "Not executed: an earlier computer action in this turn failed."


def parse_keys(combo: str) -> list:
    """'ctrl+shift+t' -> pynput keys, in the order to press them."""
    from pynput.keyboard import Key

    keys = []
    for part in (p.strip() for p in combo.split("+")):
        if not part:
            continue
        alias = KEY_ALIASES.get(part.lower().replace(" ", "_"))
        if alias:
            keys.append(getattr(Key, alias))
        elif len(part) == 1:
            keys.append(part.lower() if len(keys) else part)
        else:
            raise ValueError(f"Unknown key: {part}")
    if not keys:
        raise ValueError("No keys given.")
    return keys


class Computer:
    """Carries out the toolset's actions, and keeps the latest screenshot so
    Claude's coordinates can be turned into screen positions."""

    def __init__(self, hud, width: int):
        self.hud = hud
        self.width = width
        self.shot: screen.Shot | None = None

    def screenshot(self) -> screen.Shot:
        self.shot = screen.capture(self.width, grid=False)
        return self.shot

    def _point(self, coordinate) -> tuple[float, float]:
        if self.shot is None:
            self.screenshot()
        x, y = coordinate
        return self.shot.to_screen(x, y)

    def run(self, name: str, args: dict):
        """Carries out one action. Returns text, or an image as base64 PNG
        (wrapped in a dict) for screenshot and zoom. Raises on failure."""
        from pynput.mouse import Button, Controller

        mouse = Controller()
        if name == "screenshot":
            return {"image": self.screenshot().png_b64}
        if name == "zoom":
            if self.shot is None:
                self.screenshot()
            return {"image": screen.zoom(self.shot, args["region"], self.width)}
        if name == "cursor_position":
            if self.shot is None:
                self.screenshot()
            px, py = mouse.position
            x = round((px - self.shot.left) / self.shot.scale)
            y = round((py - self.shot.top) / self.shot.scale)
            return f"X={x}, Y={y}"
        if name == "mouse_move":
            mouse.position = self._point(args["coordinate"])
            return "OK"
        if name in ("left_click", "right_click", "middle_click", "double_click", "triple_click"):
            if args.get("coordinate"):
                x, y = self._point(args["coordinate"])
                self.hud.pointer(x, y, click=True)
                time.sleep(0.3)  # let the pointer arrive so the user can see the target
                mouse.position = (x, y)
                time.sleep(0.05)
            button = {"right_click": Button.right, "middle_click": Button.middle}.get(
                name, Button.left
            )
            count = {"double_click": 2, "triple_click": 3}.get(name, 1)
            self._with_modifiers(args.get("text"), lambda: mouse.click(button, count))
            return "OK"
        if name == "left_click_drag":
            start = self._point(args["start_coordinate"])
            end = self._point(args["coordinate"])

            def drag():
                mouse.position = start
                mouse.press(Button.left)
                for i in range(1, 11):  # move in steps so apps see a drag
                    mouse.position = (
                        start[0] + (end[0] - start[0]) * i / 10,
                        start[1] + (end[1] - start[1]) * i / 10,
                    )
                    time.sleep(0.02)
                mouse.release(Button.left)

            self._with_modifiers(args.get("text"), drag)
            return "OK"
        if name == "left_mouse_down":
            mouse.press(Button.left)
            return "OK"
        if name == "left_mouse_up":
            mouse.release(Button.left)
            return "OK"
        if name == "scroll":
            if args.get("coordinate"):
                mouse.position = self._point(args["coordinate"])
            amount = max(1, min(30, int(args.get("scroll_amount", 3))))
            dx, dy = {
                "up": (0, amount), "down": (0, -amount),
                "left": (-amount, 0), "right": (amount, 0),
            }[args["scroll_direction"]]
            self._with_modifiers(args.get("text"), lambda: mouse.scroll(dx, dy))
            return "OK"
        if name == "type":
            desktop.paste_text(args["text"])
            return "OK"
        if name == "key":
            keys = parse_keys(args["text"])
            repeat = max(1, min(100, int(args.get("repeat", 1))))
            desktop.on_main_thread(lambda: [self._tap(keys) for _ in range(repeat)])
            return "OK"
        if name == "hold_key":
            keys = parse_keys(args["text"])
            seconds = max(0.0, min(10.0, float(args.get("duration", 1))))
            desktop.on_main_thread(self._hold, keys, seconds)
            return "OK"
        if name == "wait":
            time.sleep(max(0.0, min(10.0, float(args.get("duration", 1)))))
            return "OK"
        raise ValueError(f"Unknown computer action: {name}")

    @staticmethod
    def _tap(keys) -> None:
        from pynput.keyboard import Controller

        keyboard = Controller()
        *held, last = keys
        for key in held:
            keyboard.press(key)
        keyboard.press(last)
        keyboard.release(last)
        for key in reversed(held):
            keyboard.release(key)

    @staticmethod
    def _hold(keys, seconds: float) -> None:
        from pynput.keyboard import Controller

        keyboard = Controller()
        for key in keys:
            keyboard.press(key)
        time.sleep(seconds)
        for key in reversed(keys):
            keyboard.release(key)

    @staticmethod
    def _with_modifiers(modifiers: str | None, action) -> None:
        """Runs a mouse action with modifier keys held, e.g. shift-click."""
        if not modifiers:
            action()
            return
        keys = parse_keys(modifiers)

        def run():
            from pynput.keyboard import Controller

            keyboard = Controller()
            for key in keys:
                keyboard.press(key)
            try:
                action()
            finally:
                for key in reversed(keys):
                    keyboard.release(key)

        desktop.on_main_thread(run)
