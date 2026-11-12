import io
import math
import random

from PIL import Image, ImageDraw, ImageFilter

from rpg import calamity, elements
from utils.profile_card import font

RANK_COLOR = {"elite": (190, 200, 225), "lord": (255, 205, 110), "calamity": (255, 90, 110)}
RANK_NAME = {"elite": "WARDEN", "lord": "LORD", "calamity": "CALAMITY"}


def panel(boss: dict, w: int, h: int) -> Image.Image:
    rng = random.Random(boss["look"])
    color = elements.ELEMENTS[boss["element"]]["color"]
    rank = RANK_COLOR[boss["rank"]]
    canvas = Image.new("RGBA", (w, h), (12, 13, 28, 255))
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    cx, cy = w // 2, int(h * 0.52)
    for i, r in enumerate(range(int(h * 0.62), 10, -14)):
        g.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color + (10 + i * 3,))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(canvas)
    for _ in range(26):
        x, y = rng.randint(0, w), rng.randint(0, h)
        r = rng.choice((1, 1, 2))
        d.ellipse((x - r, y - r, x + r, y + r), fill=color + (rng.randint(70, 170),))
    size = h * (0.30 + 0.05 * ["elite", "lord", "calamity"].index(boss["rank"]))
    body = (cx - size * 0.9, cy - size * 0.35, cx + size * 0.9, cy + size * 0.75)
    dark = tuple(int(c * 0.25) for c in color)
    mid = tuple(int(c * 0.5) for c in color)
    legs = 3 + rng.randint(0, 2)
    for i in range(legs):
        x = body[0] + (body[2] - body[0]) * (i + 0.5) / legs
        d.polygon([(x - 8, body[3] - 14), (x + 8, body[3] - 14), (x + rng.randint(-14, 14), body[3] + size * 0.28)], fill=dark + (255,))
    d.ellipse(body, fill=mid + (255,), outline=color + (255,), width=2)
    for i in range(5):
        x = body[0] + (body[2] - body[0]) * (i + 1) / 6
        d.arc((x - 18, body[1] + 6, x + 18, body[1] + 46), 200, 340, fill=color + (200,), width=2)
    head = (cx - size * 0.42, cy - size * 0.95, cx + size * 0.42, cy - size * 0.1)
    d.ellipse(head, fill=dark + (255,), outline=color + (255,), width=2)
    horns = 2 + boss["look"] % 4
    for i in range(horns):
        t = (i + 0.5) / horns
        x = head[0] + (head[2] - head[0]) * t
        lean = (t - 0.5) * 2
        d.polygon([(x - 6, head[1] + 8), (x + 6, head[1] + 8), (x + lean * 22, head[1] - size * (0.28 + 0.1 * rng.random()))], fill=rank + (255,))
    ey = (head[1] + head[3]) / 2 - 4
    for sx in (-1, 1):
        ex = cx + sx * size * 0.17
        d.ellipse((ex - 9, ey - 5, ex + 9, ey + 5), fill=rank + (255,))
        d.ellipse((ex - 2, ey - 4, ex + 2, ey + 4), fill=(10, 10, 20, 255))
    if boss["element"] == "fire":
        for i in range(7):
            x = cx - size * 0.9 + i * size * 0.3
            d.polygon([(x, body[1] + 4), (x + 10, body[1] - 20 - rng.randint(0, 16)), (x + 20, body[1] + 4)], fill=(255, 150, 60, 200))
    elif boss["element"] == "thunder":
        for _ in range(3):
            x = rng.randint(int(w * 0.1), int(w * 0.9))
            pts = [(x, 4)]
            for k in range(1, 5):
                pts.append((x + rng.randint(-16, 16), 4 + k * h * 0.1))
            d.line(pts, fill=(235, 225, 255, 230), width=2)
    elif boss["element"] == "water":
        for k in range(4):
            y = int(h * 0.82) + k * 6
            d.arc((8, y, w - 8, y + 18), 0, 180, fill=color + (150,), width=2)
    elif boss["element"] == "wood":
        for k in range(5):
            x = 16 + k * (w - 32) / 4
            d.line((x, h, x + rng.randint(-12, 12), h - 40 - rng.randint(0, 30)), fill=color + (190,), width=3)
    elif boss["element"] == "earth":
        for k in range(5):
            x = 12 + k * (w - 24) / 4
            d.polygon([(x, h), (x + 14, h - 30 - rng.randint(0, 22)), (x + 28, h)], fill=color + (160,))
    else:
        for k in range(6):
            x = rng.randint(10, w - 10)
            d.line((x, 0, x - 10, h), fill=color + (60,), width=1)
    return canvas


def caption(canvas: Image.Image, boss: dict, slot_label: str) -> None:
    w, h = canvas.size
    d = ImageDraw.Draw(canvas)
    rank = RANK_COLOR[boss["rank"]]
    shade = Image.new("RGBA", (w, 54), (6, 7, 16, 210))
    canvas.alpha_composite(shade, (0, h - 54))
    title = boss["name"]
    face = font(15, "Bold")
    while d.textlength(title, font=face) > w - 24 and len(title) > 8:
        title = title[:-2].rstrip()
    if title != boss["name"]:
        title += "…"
    d.text((12, h - 40), title, font=face, fill=(240, 242, 255, 255), anchor="lm")
    elem = elements.ELEMENTS[boss["element"]]
    weak = elements.ELEMENTS[calamity.weakness(boss)]
    line = f"{elem['name']} · weak to {weak['name']} · {calamity.affix_text(boss)}"
    small = font(11)
    while d.textlength(line, font=small) > w - 24 and len(line) > 10:
        line = line[:-2].rstrip()
    d.text((12, h - 18), line, font=small, fill=(190, 196, 225, 255), anchor="lm")
    d.rounded_rectangle((10, 10, 10 + 20 + len(RANK_NAME[boss["rank"]]) * 8, 32), 6, fill=(8, 9, 20, 220), outline=rank + (255,))
    d.text((20, 21), RANK_NAME[boss["rank"]], font=font(11, "Bold"), fill=rank + (255,), anchor="lm")
    d.text((w - 12, 21), slot_label, font=font(12, "Medium"), fill=(200, 206, 235, 255), anchor="rm")


def render_portrait(boss: dict) -> bytes:
    canvas = panel(boss, 480, 270)
    caption(canvas, boss, "")
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()


def render_board(bosses: list, done: dict) -> bytes:
    pw, ph = 360, 210
    canvas = Image.new("RGBA", (pw * 2 + 6, ph * 2 + 6), (6, 7, 16, 255))
    for i, boss in enumerate(bosses[:4]):
        tile = panel(boss, pw, ph)
        slot = boss["slot"]
        status = "DEFEATED" if done.get(slot) else "SPENT" if slot in done else "OPEN"
        if slot in done:
            tile.alpha_composite(Image.new("RGBA", (pw, ph), (0, 0, 0, 110)))
        caption(tile, boss, status)
        canvas.alpha_composite(tile, ((i % 2) * (pw + 6), (i // 2) * (ph + 6)))
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "PNG", optimize=True)
    return out.getvalue()
