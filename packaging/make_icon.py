"""Draws Jarvis's app icon (the orb on a dark rounded square).

Run once to regenerate packaging/icon.png and packaging/Jarvis.icns:
    python packaging/make_icon.py
"""

import math
import random
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

SIZE = 1024
HERE = Path(__file__).parent


def orb_layer(scale: int) -> Image.Image:
    random.seed(7)
    n, size = 260, SIZE * scale
    cx = cy = size / 2
    radius = size * 0.25
    rot_y, rot_x = 0.6, 0.35
    golden = math.pi * (3 - math.sqrt(5))
    points = []
    for i in range(n):
        y = 1 - (i / (n - 1)) * 2
        r = math.sqrt(1 - y * y)
        x, z = math.cos(golden * i) * r, math.sin(golden * i) * r
        x1, z1 = x * math.cos(rot_y) - z * math.sin(rot_y), x * math.sin(rot_y) + z * math.cos(rot_y)
        y1, z2 = y * math.cos(rot_x) - z1 * math.sin(rot_x), y * math.sin(rot_x) + z1 * math.cos(rot_x)
        p = 2.6 / (2.6 + z2)
        points.append((cx + x1 * radius * p, cy + y1 * radius * p, z2, random.random() < 0.12))

    layer = Image.new("RGB", (size, size), (0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for i, (x, y, z, _) in enumerate(points):
        near = sorted(range(n), key=lambda j: (points[j][0] - x) ** 2 + (points[j][1] - y) ** 2)[1:4]
        for j in near:
            depth = max(0.0, (2 - (z + points[j][2]) / 2) / 3)
            shade = int(150 * depth)
            draw.line([(x, y), points[j][:2]], fill=(shade, int(shade * 0.66), int(shade * 0.27)), width=scale)
    for x, y, z, hot in points:
        depth = (1.6 - z) / 2.6
        r = (2.6 if hot else 1.6) * (0.6 + depth) * scale * 2
        color = (255, 225, 160) if hot else (255, 181, 71)
        color = tuple(int(c * min(1, depth + 0.15)) for c in color)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    return layer


def main():
    scale = 2
    big = SIZE * scale
    base = Image.new("RGB", (big, big), (4, 6, 10))
    glow = Image.new("RGB", (big, big), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([big * 0.18, big * 0.18, big * 0.82, big * 0.82], fill=(120, 72, 22))
    glow = glow.filter(ImageFilter.GaussianBlur(big * 0.12))
    orb = orb_layer(scale)
    bloom = orb.filter(ImageFilter.GaussianBlur(10 * scale))
    image = ImageChops.add(ImageChops.add(ImageChops.add(base, glow), bloom), orb)
    image = image.resize((SIZE, SIZE), Image.LANCZOS)

    # macOS icon shape: rounded square with a margin.
    mask = Image.new("L", (SIZE, SIZE), 0)
    inset = int(SIZE * 0.09)
    ImageDraw.Draw(mask).rounded_rectangle(
        [inset, inset, SIZE - inset, SIZE - inset], radius=int(SIZE * 0.2), fill=255
    )
    icon = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    icon.paste(image, (0, 0), mask)
    icon.save(HERE / "icon.png")
    icon.save(HERE / "Jarvis.icns")
    print("Wrote icon.png and Jarvis.icns")


if __name__ == "__main__":
    main()
