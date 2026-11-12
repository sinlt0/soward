import io
import math
import random
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter

from utils.profile_card import circle_avatar, font

W, H = 720, 400
FRAMES = 8
FRAME_MS = 110

BOLT_STYLE = {
    "splitting": {"width": 3, "forks": 4, "color": (170, 200, 255), "jitter": 46},
    "crushing": {"width": 11, "forks": 0, "color": (255, 214, 140), "jitter": 22},
    "piercing": {"width": 2, "forks": 0, "color": (255, 255, 255), "jitter": 10},
}


def sky(seed: int, flash: float, tint=(14, 16, 40)) -> Image.Image:
    rng = random.Random(seed)
    base = Image.new("RGB", (W, H), tint)
    top = Image.new("RGB", (W, H), (60, 44, 98))
    mask = Image.linear_gradient("L").rotate(180).resize((W, H))
    canvas = Image.composite(top, base, mask).convert("RGBA")
    clouds = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(clouds)
    for _ in range(14):
        x, y = rng.randint(-60, W), rng.randint(-30, 150)
        rx, ry = rng.randint(90, 190), rng.randint(26, 60)
        shade = rng.randint(18, 46)
        d.ellipse((x - rx, y - ry, x + rx, y + ry), fill=(shade, shade, shade + 22, 190))
    canvas.alpha_composite(clouds.filter(ImageFilter.GaussianBlur(18)))
    if flash > 0:
        canvas.alpha_composite(Image.new("RGBA", (W, H), (200, 210, 255, int(120 * flash))))
    return canvas


def bolt_path(rng: random.Random, x0: float, y0: float, x1: float, y1: float, jitter: float, steps: int = 9) -> list:
    points = [(x0, y0)]
    for i in range(1, steps):
        t = i / steps
        points.append((x0 + (x1 - x0) * t + rng.uniform(-jitter, jitter), y0 + (y1 - y0) * t))
    points.append((x1, y1))
    return points


def draw_bolt(canvas: Image.Image, kind: str, frame: int, seed: int, target: tuple, intensity: float = 1.0) -> None:
    style = BOLT_STYLE[kind]
    rng = random.Random(seed * 31 + frame)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d, g = ImageDraw.Draw(layer), ImageDraw.Draw(glow)
    color = style["color"]
    alpha = int(255 * intensity)
    start_x = target[0] + rng.uniform(-70, 70)
    main = bolt_path(rng, start_x, -10, target[0], target[1], style["jitter"])
    paths = [(main, style["width"])]
    for _ in range(style["forks"]):
        pivot = rng.randint(2, len(main) - 3)
        px, py = main[pivot]
        paths.append((bolt_path(rng, px, py, px + rng.uniform(-150, 150), py + rng.uniform(70, 150), style["jitter"] * 0.6, 4), max(1, style["width"] - 1)))
    for points, width in paths:
        g.line(points, fill=color + (alpha,), width=width + 10)
        d.line(points, fill=(255, 255, 255, alpha), width=width)
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(9)))
    canvas.alpha_composite(layer)
    if kind == "crushing":
        pressure = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(pressure).ellipse((target[0] - 90, target[1] - 26, target[0] + 90, target[1] + 26), outline=color + (int(160 * intensity),), width=4)
        canvas.alpha_composite(pressure)


def hud(canvas: Image.Image, state: dict, name: str, avatar: Optional[Image.Image], ring=(205, 214, 255)) -> None:
    d = ImageDraw.Draw(canvas)
    total = state["waves"]
    pip = 22
    start = (W - (total * (pip + 6) - 6)) // 2
    for i in range(total):
        done = i < state["wave"]
        current = i == state["wave"] and not state["done"]
        fill = (255, 214, 120, 255) if done else (200, 210, 255, 255) if current else (60, 62, 84, 255)
        x = start + i * (pip + 6)
        d.rounded_rectangle((x, 18, x + pip, 30), radius=5, fill=fill)
    d.text((W // 2, 50), f"Tribulation {state['tier']} · wave {min(state['wave'] + 1, total)} of {total}", font=font(15, "Medium"), fill=(226, 230, 255, 255), anchor="mm")
    portrait = circle_avatar(avatar, 92, ring)
    canvas.alpha_composite(portrait, (W // 2 - portrait.width // 2, H - portrait.height - 54))
    frac = max(0.0, state["hp"] / max(1, state["max"]))
    x0, x1, y0 = 40, W - 40, H - 34
    d.rounded_rectangle((x0, y0, x1, y0 + 14), radius=7, fill=(0, 0, 0, 120))
    if frac > 0:
        color = (96, 214, 140) if frac > 0.5 else (240, 196, 80) if frac > 0.25 else (240, 90, 90)
        d.rounded_rectangle((x0, y0, x0 + max(14, int((x1 - x0) * frac)), y0 + 14), radius=7, fill=color + (255,))
    d.text((x0, y0 - 10), name, font=font(14, "Medium"), fill=(226, 230, 255, 255), anchor="lb")
    d.text((x1, y0 - 10), f"{max(0, state['hp']):,} / {state['max']:,}", font=font(14), fill=(226, 230, 255, 255), anchor="rb")


def to_gif(frames: list) -> io.BytesIO:
    out = io.BytesIO()
    paletted = [frame.convert("RGB").convert("P", palette=Image.Palette.ADAPTIVE, colors=128) for frame in frames]
    paletted[0].save(out, format="GIF", save_all=True, append_images=paletted[1:], duration=FRAME_MS, loop=0, optimize=False, disposal=2)
    out.seek(0)
    return out


def render_wave(state: dict, name: str, avatar: Optional[Image.Image]) -> io.BytesIO:
    seed = state["tier"] * 100 + state["wave"]
    target = (W // 2, H - 150)
    frames = []
    shown = state["omen"]
    for i in range(FRAMES):
        flash = 0.75 if i in (2, 3) else 0.18 if i in (1, 4) else 0.0
        canvas = sky(seed, flash)
        if i >= 1:
            draw_bolt(canvas, shown, i, seed, target, 1.0 if i in (2, 3, 5) else 0.45)
        hud(canvas, state, name, avatar)
        frames.append(canvas)
    return to_gif(frames)


def render_strike(state: dict, name: str, avatar: Optional[Image.Image], result: dict) -> io.BytesIO:
    seed = state["tier"] * 100 + max(0, state["wave"] - 1) + 7
    target = (W // 2, H - 150)
    right = result["tag"] == "right"
    frames = []
    for i in range(FRAMES):
        canvas = sky(seed, 0.9 if i in (1, 2) else 0.1)
        draw_bolt(canvas, result["bolt"], i, seed, target, 1.0 if i < 6 else 0.3)
        shield = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        radius = 70 + (i * 7 if right else 0)
        ring = (140, 230, 190) if right else (255, 110, 110)
        ImageDraw.Draw(shield).ellipse((target[0] - radius, target[1] - radius, target[0] + radius, target[1] + radius), outline=ring + (190,), width=4)
        canvas.alpha_composite(shield.filter(ImageFilter.GaussianBlur(1)))
        hud(canvas, state, name, avatar, ring=ring)
        d = ImageDraw.Draw(canvas)
        d.text((W // 2, 78), "-" + f"{result['damage']:,}", font=font(30, "Bold"), fill=(255, 255, 255, 255 if i < 7 else 180), anchor="mm")
        frames.append(canvas)
    return to_gif(frames)


def render_result(won: bool, tier: int, name: str, avatar: Optional[Image.Image], label: str = "") -> io.BytesIO:
    frames = []
    for i in range(FRAMES + 4):
        t = i / (FRAMES + 3)
        if won:
            canvas = sky(3, 0.0, tint=(46, 34, 20))
            glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            g = ImageDraw.Draw(glow)
            cx, cy = W // 2, H // 2 - 10
            for ring in range(4):
                r = int(40 + t * 260 - ring * 36)
                if r > 0:
                    g.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(255, 218, 120, max(0, 210 - ring * 50)), width=6 - ring)
            for beam in range(12):
                angle = beam * math.pi / 6 + t * 0.6
                g.line([(cx, cy), (cx + math.cos(angle) * 460, cy + math.sin(angle) * 460)], fill=(255, 226, 150, 70), width=10)
            canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(5)))
            portrait = circle_avatar(avatar, 110, (255, 218, 120))
            canvas.alpha_composite(portrait, (cx - portrait.width // 2, cy - portrait.height // 2))
            d = ImageDraw.Draw(canvas)
            d.text((W // 2, H - 74), (label or "Transcendent").upper(), font=font(34, "Bold"), fill=(255, 232, 170, 255), anchor="mm")
            d.text((W // 2, H - 36), f"{name} defied the heavens", font=font(17, "Medium"), fill=(255, 244, 214, 255), anchor="mm")
        else:
            canvas = sky(5, 0.8 if i < 3 else 0.0, tint=(30, 8, 12))
            draw_bolt(canvas, "crushing", i, 11, (W // 2, H // 2), 1.0 if i < 4 else 0.0)
            portrait = circle_avatar(avatar, 110, (150, 60, 66))
            shade = Image.new("RGBA", portrait.size, (0, 0, 0, int(160 * t)))
            portrait.alpha_composite(shade)
            canvas.alpha_composite(portrait, (W // 2 - portrait.width // 2, H // 2 - portrait.height // 2))
            d = ImageDraw.Draw(canvas)
            d.text((W // 2, H - 74), "THE HEAVENS HOLD", font=font(32, "Bold"), fill=(255, 150, 150, 255), anchor="mm")
            d.text((W // 2, H - 36), f"{name} was struck down", font=font(17, "Medium"), fill=(255, 220, 220, 255), anchor="mm")
        frames.append(canvas)
    return to_gif(frames)


def join(*sources) -> io.BytesIO:
    frames = []
    for source in sources:
        image = Image.open(source)
        for index in range(getattr(image, "n_frames", 1)):
            image.seek(index)
            frames.append(image.convert("RGB"))
    return to_gif(frames)


def render_round(state: dict, name: str, avatar: Optional[Image.Image], result: Optional[dict]) -> io.BytesIO:
    second = render_wave(state, name, avatar)
    if not result:
        return second
    return join(render_strike(state, name, avatar, result), second)


def render_final(state: dict, name: str, avatar: Optional[Image.Image], result: Optional[dict], label: str = "") -> io.BytesIO:
    ending = render_result(state["done"] == "win", state["tier"], name, avatar, label)
    if not result:
        return ending
    return join(render_strike(state, name, avatar, result), ending)
