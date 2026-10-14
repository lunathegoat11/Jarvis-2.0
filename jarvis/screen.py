"""Seeing the screen and using the mouse, for tasks like "play the latest
MrBeast video" that need looking and clicking.

The AI is shown a scaled-down screenshot with a light coordinate grid drawn
on it (open models aim much better with one) and answers in that image's
pixels. Shot.to_screen() turns those into real screen points for the mouse.
"""

import base64
import io
import time
from dataclasses import dataclass

from . import desktop
from .config import config


@dataclass
class Shot:
    png_b64: str
    width: int  # size of the image the AI sees
    height: int
    left: float  # where the screen starts, in points
    top: float
    scale: float  # screen points per image pixel

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        x = min(max(x, 0), self.width - 1)
        y = min(max(y, 0), self.height - 1)
        return self.left + x * self.scale, self.top + y * self.scale


def draw_grid(image, step: int = 100):
    """Faint lines every `step` pixels, numbered along the top and left."""
    from PIL import ImageDraw

    image = image.convert("RGB")
    draw = ImageDraw.Draw(image, "RGBA")
    for x in range(step, image.width, step):
        draw.line([(x, 0), (x, image.height)], fill=(255, 0, 255, 60), width=1)
        draw.rectangle([(x + 1, 0), (x + 32, 12)], fill=(0, 0, 0, 160))
        draw.text((x + 3, 0), str(x), fill=(255, 255, 255, 255))
    for y in range(step, image.height, step):
        draw.line([(0, y), (image.width, y)], fill=(255, 0, 255, 60), width=1)
        draw.rectangle([(0, y + 1), (27, y + 13)], fill=(0, 0, 0, 160))
        draw.text((2, y + 1), str(y), fill=(255, 255, 255, 255))
    return image


def capture(width: int | None = None, grid: bool | None = None) -> Shot:
    import mss
    from PIL import Image

    width = width or config.screenshot_width
    grid = config.screen_grid if grid is None else grid
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        raw = sct.grab(monitor)
        image = Image.frombytes("RGB", raw.size, raw.rgb)

    # The monitor's width is in screen points; the grab may be in Retina
    # pixels, so scale from points to the image the AI will see.
    target_w = min(width, image.width)
    target_h = round(image.height * target_w / image.width)
    image = image.resize((target_w, target_h))
    if grid:
        image = draw_grid(image)

    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return Shot(
        png_b64=base64.standard_b64encode(buffer.getvalue()).decode("ascii"),
        width=target_w,
        height=target_h,
        left=monitor["left"],
        top=monitor["top"],
        scale=monitor["width"] / target_w,
    )


def _schema(properties: dict) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


SCREEN_TOOLS = [
    {
        "name": "click",
        "description": "Click at a point in the latest screenshot (its pixel coordinates).",
        "strict": True,
        "input_schema": _schema(
            {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "button": {"type": "string", "enum": ["left", "right"]},
                "double": {"type": "boolean"},
            }
        ),
    },
    {
        "name": "scroll",
        "description": "Scroll with the mouse over a point. amount is how far, 1 (a little) to 15 (a lot).",
        "strict": True,
        "input_schema": _schema(
            {
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "direction": {"type": "string", "enum": ["up", "down"]},
                "amount": {"type": "integer"},
            }
        ),
    },
    {
        "name": "type_text",
        "description": "Type text into whatever is focused. Click the field first.",
        "strict": True,
        "input_schema": _schema({"text": {"type": "string"}}),
    },
    {
        "name": "press_keys",
        "description": "Press a shortcut like 'enter', 'cmd+l', 'cmd+t' or 'esc'.",
        "strict": True,
        "input_schema": _schema({"keys": {"type": "string"}}),
    },
    {
        "name": "open_url",
        "description": "Open a web address in the browser. Often quicker than clicking around.",
        "strict": True,
        "input_schema": _schema({"url": {"type": "string"}}),
    },
    {
        "name": "wait",
        "description": "Wait for something to load, in seconds (up to 5).",
        "strict": True,
        "input_schema": _schema({"seconds": {"type": "number"}}),
    },
    {
        "name": "done",
        "description": (
            "Finish. Give a one-sentence summary to say to the user: what you did, "
            "or why you stopped."
        ),
        "strict": True,
        "input_schema": _schema({"summary": {"type": "string"}}),
    },
]


def run_screen_tool(name: str, args: dict, shot: Shot, hud) -> str:
    """Carries out one action. Raises on failure."""
    from pynput.mouse import Button, Controller

    if name in ("click", "scroll"):
        x, y = shot.to_screen(args["x"], args["y"])
        hud.pointer(x, y, click=name == "click")
        time.sleep(0.45)  # let the pointer arrive so the user can see the target
        mouse = Controller()
        mouse.position = (x, y)
        time.sleep(0.05)
        if name == "click":
            button = Button.right if args["button"] == "right" else Button.left
            mouse.click(button, 2 if args["double"] else 1)
            return f"Clicked at ({args['x']}, {args['y']})."
        amount = max(1, min(15, int(args["amount"])))
        mouse.scroll(0, -amount if args["direction"] == "down" else amount)
        return f"Scrolled {args['direction']}."
    if name == "type_text":
        desktop.paste_text(args["text"])
        return "Typed it."
    if name == "press_keys":
        desktop.press_keys(args["keys"])
        return f"Pressed {args['keys']}."
    if name == "open_url":
        desktop.open_url(args["url"])
        time.sleep(1.5)
        return f"Opened {args['url']}."
    if name == "wait":
        time.sleep(max(0.0, min(5.0, float(args["seconds"]))))
        return "Waited."
    raise ValueError(f"Unknown screen action: {name}")
