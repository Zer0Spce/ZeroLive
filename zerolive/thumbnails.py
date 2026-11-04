"""Create original event graphics when source pages have no usable artwork."""
from __future__ import annotations

from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 640, 360
BASE = "https://raw.githubusercontent.com/Zer0Spce/ZeroLive/main/assets/thumbnails"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(FONT, size)
    except OSError:
        return ImageFont.load_default()


def fit_text(draw: ImageDraw.ImageDraw, text: str, width: int, max_size: int = 38) -> ImageFont.ImageFont:
    for size in range(max_size, 15, -2):
        current = font(size)
        if draw.textbbox((0, 0), text, font=current)[2] <= width:
            return current
    return font(16)


def draw_center(draw: ImageDraw.ImageDraw, text: str, center_x: int, y: int,
                max_width: int, size: int = 38) -> None:
    f = fit_text(draw, text, max_width, size)
    box = draw.textbbox((0, 0), text, font=f)
    draw.text((center_x - (box[2] - box[0]) // 2, y), text,
              font=f, fill="#FFFFFF", stroke_width=1, stroke_fill="#06101F")


def create_thumbnail(title: str, category: str, key: str, directory: Path) -> str:
    """Generate a 640x360 PNG and return a public URL; use only for missing art."""
    directory.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-z0-9]+", "", key.lower()) or "liveevent"
    dest = directory / f"{slug}.png"
    if dest.exists():
        return f"{BASE}/{dest.name}"
    im = Image.new("RGB", (WIDTH, HEIGHT), (12, 24, 53))
    pixels = im.load()
    for y in range(HEIGHT):
        for x in range(WIDTH):
            pixels[x, y] = (int(8 + 14 * x / WIDTH),
                            int(48 - 20 * y / HEIGHT + 7 * x / WIDTH),
                            int(77 + 19 * y / HEIGHT))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((24, 20, 616, 340), radius=23, outline=(98, 143, 183), width=2)
    draw.rounded_rectangle((46, 40, 250, 79), radius=14, fill="#1B9C9A")
    draw.text((59, 49), (category or "LIVE SPORTS").upper()[:19], font=font(17), fill="white")
    draw.line((46, 306, 594, 306), fill="#4FD2CD", width=3)
    draw.text((48, 316), "LIVE EVENT", fill="#D0EBF1", font=font(13))
    parts = re.split(r"\s+vs\.?\s+", title, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        left, right = parts
    else:
        left, right = title, ""
    if right:
        draw_center(draw, left.upper(), 176, 163, 230, 36)
        draw_center(draw, "VS", 320, 163, 52, 26)
        draw_center(draw, right.upper(), 464, 163, 230, 36)
    else:
        words = title.split()
        if len(words) > 5:
            midpoint = len(words) // 2
            draw_center(draw, " ".join(words[:midpoint]).upper(), 320, 147, 530, 44)
            draw_center(draw, " ".join(words[midpoint:]).upper(), 320, 204, 530, 44)
        else:
            draw_center(draw, title.upper(), 320, 165, 530, 44)
    im.save(dest, "PNG", optimize=True)
    return f"{BASE}/{dest.name}"
