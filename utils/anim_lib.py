import io
import math
import random
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from rpg import anims

W, H = 480, 270
FRAMES = 12
FRAME_MS = 80
WHITE = (255, 255, 255)
JADE = (110, 230, 160)
CASTER = (96, 188)
ENEMY = (376, 168)


def background(shake: float = 0.0, tint=(12, 14, 30)) -> Image.Image:
    base = Image.new("RGB", (W, H), tint)
    top = Image.new("RGB", (W, H), (34, 30, 66))
    mask = Image.linear_gradient("L").rotate(180).resize((W, H))
    canvas = Image.composite(top, base, mask).convert("RGBA")
    d = ImageDraw.Draw(canvas)
    d.rectangle((0, 214, W, H), fill=(10, 10, 22, 255))
    d.line((0, 214, W, 214), fill=(70, 70, 120, 255), width=1)
    return canvas


def figure(canvas: Image.Image, pos: tuple, color: tuple, scale: float = 1.0, foe: bool = False, hit: float = 0.0) -> None:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = pos
    s = scale
    shift = int(6 * hit)
    x += shift if foe else -shift
    d.ellipse((x - 14 * s, y - 72 * s, x + 14 * s, y - 44 * s), fill=color + (255,))
    d.polygon([(x - 8 * s, y - 46 * s), (x + 8 * s, y - 46 * s), (x + 30 * s, y + 24 * s), (x - 30 * s, y + 24 * s)], fill=color + (255,))
    if foe:
        d.polygon([(x - 12 * s, y - 70 * s), (x - 24 * s, y - 92 * s), (x - 4 * s, y - 66 * s)], fill=color + (255,))
        d.polygon([(x + 12 * s, y - 70 * s), (x + 24 * s, y - 92 * s), (x + 4 * s, y - 66 * s)], fill=color + (255,))
        d.ellipse((x - 9 * s, y - 62 * s, x - 3 * s, y - 56 * s), fill=(255, 70, 70, 255))
        d.ellipse((x + 3 * s, y - 62 * s, x + 9 * s, y - 56 * s), fill=(255, 70, 70, 255))
    canvas.alpha_composite(layer)
    if hit > 0:
        flash = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        mask = layer.split()[3].point(lambda v: int(v * 0.8 * hit))
        flash.paste((255, 255, 255, 255), (0, 0), mask)
        canvas.alpha_composite(flash)


def fx_layer() -> tuple:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    return layer, ImageDraw.Draw(layer)


def merge(canvas: Image.Image, layer: Image.Image, glow: int = 7, strength: float = 1.0) -> None:
    if glow:
        blurred = layer.filter(ImageFilter.GaussianBlur(glow))
        if strength != 1.0:
            blurred.putalpha(blurred.split()[3].point(lambda v: min(255, int(v * strength))))
        canvas.alpha_composite(blurred)
    canvas.alpha_composite(layer)


def rgba(color: tuple, alpha: float) -> tuple:
    return (color[0], color[1], color[2], max(0, min(255, int(255 * alpha))))


def ease(t: float) -> float:
    return 1 - (1 - t) ** 3


def flash(canvas: Image.Image, color: tuple, alpha: float) -> None:
    if alpha > 0:
        canvas.alpha_composite(Image.new("RGBA", (W, H), rgba(color, alpha)))


def ring(d: ImageDraw.ImageDraw, center: tuple, radius: float, color: tuple, alpha: float, width: int = 3) -> None:
    if radius > 0 and alpha > 0:
        d.ellipse((center[0] - radius, center[1] - radius * 0.55, center[0] + radius, center[1] + radius * 0.55), outline=rgba(color, alpha), width=width)


def circle(d: ImageDraw.ImageDraw, center: tuple, radius: float, color: tuple, alpha: float) -> None:
    if radius > 0 and alpha > 0:
        d.ellipse((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), fill=rgba(color, alpha))


def impact(canvas: Image.Image, t: float, start: float, c1: tuple, c2: tuple, size: float = 1.0) -> float:
    if t < start:
        return 0.0
    k = (t - start) / (1 - start)
    layer, d = fx_layer()
    for i in range(3):
        ring(d, (ENEMY[0], ENEMY[1] + 24), (30 + 90 * ease(k) - i * 18) * size, c1 if i != 1 else c2, 1 - k, 4 - i)
    circle(d, (ENEMY[0], ENEMY[1] - 10), 40 * size * (1 - k * 0.4), c2, 0.8 * (1 - k))
    merge(canvas, layer, 6)
    return 1 - k


def arc_slash(d, center, radius, start, end, color, alpha, width):
    d.arc((center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius), start, end, fill=rgba(color, alpha), width=width)


def m_slash(canvas, t, c1, c2, rng, o):
    count = o.get("count", 1)
    layer, d = fx_layer()
    for i in range(count):
        local = (t * (count + 0.6) - i * 0.55)
        if local <= 0 or local >= 1.2:
            continue
        k = min(1.0, local)
        angle = -35 + i * 48
        cx, cy = ENEMY[0] - 10, ENEMY[1] - 10
        sweep = 150 * ease(k)
        fade = 1 - max(0.0, local - 0.8) * 2.5
        for w, col, a in ((16, c1, 0.5), (8, c1, 0.9), (3, c2, 1.0)):
            arc_slash(d, (cx, cy), 70 + i * 6, angle, angle + sweep, col, a * fade, w)
    merge(canvas, layer, 6)
    impact(canvas, t, 0.35, c1, c2, 0.8)


def m_cleave(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    k = ease(min(1.0, t * 1.6))
    x0, y0, x1, y1 = ENEMY[0] - 150, 10, ENEMY[0] + 120, 250
    px, py = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
    fade = 1 - max(0.0, t - 0.55) * 2
    for w, col, a in ((44, c1, 0.4), (22, c1, 0.8), (7, c2, 1.0)):
        d.line([(x0, y0), (px, py)], fill=rgba(col, a * fade), width=w)
    if o.get("halo"):
        ring(d, (ENEMY[0], 60), 80 * k, c2, 0.8 * fade, 3)
    merge(canvas, layer, 10)
    if t > 0.5:
        flash(canvas, c2, 0.5 * (1 - (t - 0.5) * 2))
    impact(canvas, t, 0.45, c1, c2, 1.3 if o.get("big") else 1.1)


def m_blades(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    for i in range(o.get("count", 14)):
        delay = rng.uniform(0, 0.5)
        k = (t - delay) / 0.45
        if k <= 0 or k > 1.3:
            continue
        k = min(1.0, k)
        tx = ENEMY[0] + rng.uniform(-60, 60)
        ty = ENEMY[1] + rng.uniform(-50, 40)
        sx, sy = tx - 160, ty - 220
        x, y = sx + (tx - sx) * ease(k), sy + (ty - sy) * ease(k)
        dx, dy = (tx - sx), (ty - sy)
        norm = math.hypot(dx, dy)
        ux, uy = dx / norm, dy / norm
        d.line([(x - ux * 34, y - uy * 34), (x, y)], fill=rgba(c1, 0.9), width=4)
        d.line([(x - ux * 14, y - uy * 14), (x, y)], fill=rgba(c2, 1.0), width=2)
    merge(canvas, layer, 4)
    impact(canvas, t, 0.55, c1, c2, 1.0)


def m_beam(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    k = ease(min(1.0, t * 2))
    x1 = CASTER[0] + (ENEMY[0] - CASTER[0]) * k
    width = 18 + 10 * math.sin(t * 20)
    d.line([(CASTER[0] + 20, CASTER[1] - 40), (x1, ENEMY[1] - 20)], fill=rgba(c1, 0.9), width=int(width))
    d.line([(CASTER[0] + 20, CASTER[1] - 40), (x1, ENEMY[1] - 20)], fill=rgba(c2, 1.0), width=int(width / 3))
    merge(canvas, layer, 8)
    impact(canvas, t, 0.45, c1, c2)


def m_burst(canvas, t, c1, c2, rng, o):
    size = 0.7 if o.get("small") else 1.2
    layer, d = fx_layer()
    reach = ease(min(1.0, t * 2.2))
    if t < 0.5 and not o.get("small"):
        x = CASTER[0] + 30 + (ENEMY[0] - CASTER[0] - 60) * reach
        circle(d, (x, ENEMY[1] - 30), 22, c2, 0.9)
        d.line([(CASTER[0] + 20, ENEMY[1] - 30), (x, ENEMY[1] - 30)], fill=rgba(c1, 0.5), width=14)
    elif o.get("small") and t < 0.4:
        x = CASTER[0] + 30 + (ENEMY[0] - CASTER[0] - 80) * reach
        circle(d, (x, ENEMY[1] - 30), 14, c2, 0.9)
    merge(canvas, layer, 6)
    k = impact(canvas, t, 0.4 if not o.get("small") else 0.35, c1, c2, size)
    if o.get("cracks") and t > 0.45:
        layer, d = fx_layer()
        crack = ease((t - 0.45) / 0.55)
        for i in range(6):
            angle = math.radians(180 + i * 36 + rng.uniform(-8, 8))
            x1 = ENEMY[0] + math.cos(angle) * 120 * crack
            y1 = ENEMY[1] + 32 + abs(math.sin(angle)) * 24 * crack
            d.line([(ENEMY[0], ENEMY[1] + 32), (x1, y1)], fill=rgba(c1, 1 - crack * 0.5), width=3)
        merge(canvas, layer, 3)
    if o.get("double") and t > 0.55:
        impact(canvas, t - 0.15, 0.4, c2, c1, 0.8)


def m_quake(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    for i in range(7):
        k = max(0.0, min(1.0, (t - i * 0.07) / 0.5))
        x = CASTER[0] + 40 + (ENEMY[0] - CASTER[0] - 20) * ease(k) * (i + 1) / 7 * 1.0
        h = 36 * math.sin(k * math.pi)
        d.polygon([(x - 14, 214), (x, 214 - h * 1.8), (x + 14, 214)], fill=rgba(c1, 0.9))
    merge(canvas, layer, 3)
    impact(canvas, t, 0.5, c1, c2, 1.1)
    if t > 0.5:
        layer, d = fx_layer()
        for i in range(3):
            ang = (t * 12 + i * 2.1)
            cx, cy = ENEMY[0] + math.cos(ang) * 22, ENEMY[1] - 98 + math.sin(ang) * 8
            circle(d, (cx, cy), 6, c2, 0.9)
        merge(canvas, layer, 3)


def m_flame(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    count = 46 if o.get("big") else 28
    for i in range(count):
        life = rng.uniform(0.35, 0.6)
        delay = rng.uniform(0, 0.4)
        k = (t - delay) / life
        if k <= 0 or k >= 1:
            continue
        x = ENEMY[0] + rng.uniform(-40, 40) + math.sin(k * 6 + i) * 8
        y = ENEMY[1] + 36 - k * (110 if o.get("big") else 85)
        radius = (12 if o.get("big") else 9) * (1 - k * 0.7)
        col = c1 if k < 0.55 else c2
        circle(d, (x, y), radius, col, 1 - k * 0.6)
    if o.get("burst") and t < 0.4:
        x = CASTER[0] + 30 + (ENEMY[0] - CASTER[0] - 60) * ease(t / 0.4)
        circle(d, (x, ENEMY[1] - 24), 18, c2, 0.95)
    merge(canvas, layer, 6)


def m_bolt(canvas, t, c1, c2, rng, o):
    r = random.Random(int(t * 100))
    layer, d = fx_layer()
    pulses = (0.25, 0.4, 0.55)
    live = any(abs(t - p) < 0.06 for p in pulses)
    if live:
        pts = [(ENEMY[0] + r.uniform(-30, 30), -10)]
        for i in range(1, 8):
            pts.append((ENEMY[0] + r.uniform(-34, 34) * (1 - i / 9), i * 30))
        pts.append((ENEMY[0], ENEMY[1] - 10))
        d.line(pts, fill=rgba(c1, 0.9), width=12)
        d.line(pts, fill=rgba(c2, 1.0), width=4)
        flash(canvas, c1, 0.25)
    if o.get("seal") and t < 0.6:
        ring(d, (ENEMY[0], ENEMY[1] - 110), 50 * ease(min(1, t * 3)), c1, 0.9, 3)
        ring(d, (ENEMY[0], ENEMY[1] - 110), 32 * ease(min(1, t * 3)), c2, 0.9, 2)
    merge(canvas, layer, 8)
    impact(canvas, t, 0.55, c1, c2, 0.8)


def m_wave(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    for band in range(3):
        pts = []
        for x in range(0, W + 1, 12):
            k = x / W
            y = 150 + band * 22 + math.sin(k * 9 - t * 10 + band) * 14
            pts.append((x, y))
        reach = ease(min(1, t * 1.8))
        pts = [p for p in pts if p[0] < CASTER[0] + (W - CASTER[0]) * reach]
        if len(pts) > 1:
            d.line(pts, fill=rgba(c1 if band != 1 else c2, 0.85), width=10 - band * 2)
    merge(canvas, layer, 6)
    impact(canvas, t, 0.5, c1, c2)


def m_wind(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    for s in range(4):
        pts = []
        for i in range(40):
            k = i / 39
            ang = k * 7 + t * 9 + s * 1.57
            r = 12 + k * 70 * ease(min(1, t * 2))
            pts.append((ENEMY[0] + math.cos(ang) * r, ENEMY[1] - 30 + math.sin(ang) * r * 0.5 - k * 40))
        d.line(pts, fill=rgba(c1 if s % 2 else c2, 0.85), width=4)
    if o.get("blades"):
        for i in range(2):
            local = (t * 1.8 - i * 0.5)
            if 0 < local < 1:
                arc_slash(d, (ENEMY[0], ENEMY[1] - 10), 66, -50 + i * 60, -50 + i * 60 + 140 * ease(local), c2, 1 - local * 0.5, 7)
    merge(canvas, layer, 6)


def m_cloud(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    for i in range(16):
        ang = rng.uniform(0, 6.28)
        dist = rng.uniform(0, 70)
        k = ease(min(1.0, t * 1.5))
        x = ENEMY[0] + math.cos(ang) * dist * k + math.sin(t * 5 + i) * 5
        y = ENEMY[1] - 10 + math.sin(ang) * dist * 0.5 * k - t * 20
        circle(d, (x, y), 26 * k, c1 if i % 3 else c2, 0.28)
    for i in range(10):
        life = rng.uniform(0.3, 0.55)
        k = (t - rng.uniform(0, 0.4)) / life
        if 0 < k < 1:
            circle(d, (ENEMY[0] + rng.uniform(-50, 50), ENEMY[1] + 20 - k * 90), 5, c2, 0.9)
    merge(canvas, layer, 9, 1.2)
    if o.get("bones") and t > 0.3:
        layer, d = fx_layer()
        for i in range(5):
            x = ENEMY[0] - 40 + i * 20
            d.line([(x, ENEMY[1] - 70 + i % 2 * 6), (x + 6, ENEMY[1] - 40)], fill=rgba(c2, 0.9), width=4)
        merge(canvas, layer, 2)


def m_aura(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    big = o.get("big")
    for i in range(30 if big else 20):
        life = rng.uniform(0.4, 0.7)
        k = (t - rng.uniform(0, 0.35)) / life
        if k <= 0 or k >= 1:
            continue
        x = CASTER[0] + rng.uniform(-34, 34) + math.sin(k * 7 + i) * 6
        y = CASTER[1] + 20 - k * 120
        col = c1 if i % 2 else c2
        if o.get("notes"):
            d.text((x, y), "~", fill=rgba(col, 1 - k * 0.5))
        else:
            circle(d, (x, y), 4 + (3 if big else 0), col, 1 - k * 0.6)
    for i in range(2):
        k = (t * 1.4 - i * 0.4)
        if 0 < k < 1:
            ring(d, (CASTER[0], CASTER[1] + 20), 20 + 60 * ease(k), c1, 1 - k, 3)
    if o.get("swords"):
        for i in range(3):
            ang = t * 6 + i * 2.09
            x, y = CASTER[0] + math.cos(ang) * 40, CASTER[1] - 30 + math.sin(ang) * 14
            d.polygon([(x, y - 18), (x - 3, y + 6), (x + 3, y + 6)], fill=rgba(c2, 0.95))
    if o.get("flames"):
        for i in range(8):
            x = CASTER[0] + rng.uniform(-30, 30)
            circle(d, (x, CASTER[1] - 20 - rng.uniform(0, 60) * t), 7, c2, 0.5)
    merge(canvas, layer, 8)


def m_shield(canvas, t, c1, c2, rng, o):
    small = o.get("small")
    center = (CASTER[0], CASTER[1] - 26)
    layer, d = fx_layer()
    grow = ease(min(1.0, t * 3))
    r = (46 if small else 64) * grow
    d.ellipse((center[0] - r, center[1] - r * 1.1, center[0] + r, center[1] + r * 1.1), outline=rgba(c1, 0.95), width=4, fill=rgba(c1, 0.14))
    if o.get("hex"):
        pts = [(center[0] + math.cos(math.radians(60 * i + 30)) * r * 0.78, center[1] + math.sin(math.radians(60 * i + 30)) * r * 0.86) for i in range(6)]
        d.line(pts + [pts[0]], fill=rgba(c2, 0.9), width=3)
        for p in pts:
            d.line([center, p], fill=rgba(c2, 0.35), width=1)
    pulse = (t * 2.2) % 1
    ring(d, (center[0], center[1] + 24), r * (0.7 + 0.5 * pulse), c2, 0.8 * (1 - pulse), 2)
    if o.get("mirror") and t > 0.4:
        d.line([(center[0] - r, center[1] + r * 0.9), (center[0] + r, center[1] - r * 0.9)], fill=rgba(WHITE, 0.8), width=3)
    merge(canvas, layer, 7)


def m_drain(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    count = 28 if o.get("swarm") or o.get("souls") else 20
    for i in range(count):
        delay = rng.uniform(0, 0.4)
        k = (t - delay) / 0.5
        if k <= 0 or k >= 1:
            continue
        sx, sy = ENEMY[0] + rng.uniform(-30, 30), ENEMY[1] - rng.uniform(0, 70)
        tx, ty = CASTER[0], CASTER[1] - 40
        bend = math.sin(k * math.pi) * 40
        x = sx + (tx - sx) * ease(k)
        y = sy + (ty - sy) * ease(k) - bend
        col = c1 if i % 2 else c2
        if o.get("souls"):
            d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=rgba(col, 0.9))
            d.line([(x, y + 6), (x + 6, y + 16)], fill=rgba(col, 0.6), width=3)
        else:
            circle(d, (x, y), 5, col, 0.95)
    merge(canvas, layer, 6)
    impact(canvas, t, 0.2, c1, c2, 0.7)
    if t > 0.7:
        layer, d = fx_layer()
        ring(d, (CASTER[0], CASTER[1] + 20), 70 * (t - 0.7) / 0.3, JADE, 1 - (t - 0.7) / 0.3, 3)
        merge(canvas, layer, 5)


def m_rune(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    center = (ENEMY[0], ENEMY[1] + 32)
    grow = ease(min(1.0, t * 2.4))
    for r, w, spin in ((96, 3, 1.0), (70, 2, -1.4), (46, 2, 2.0)):
        rr = r * grow
        ring(d, center, rr, c1, 0.95, w)
        pts = []
        sides = 6 if r != 70 else 5
        for i in range(sides):
            ang = math.radians(360 / sides * i) + t * spin * 2
            pts.append((center[0] + math.cos(ang) * rr, center[1] + math.sin(ang) * rr * 0.55))
        d.line(pts + [pts[0]], fill=rgba(c2, 0.9), width=2)
    for i in range(14):
        life = rng.uniform(0.35, 0.6)
        k = (t - rng.uniform(0, 0.4)) / life
        if 0 < k < 1:
            ang = rng.uniform(0, 6.28)
            rad = rng.uniform(20, 90)
            x = center[0] + math.cos(ang) * rad * (1 - k * 0.8 if o.get("inward") else 1)
            y = center[1] + math.sin(ang) * rad * 0.5 - k * 90
            if o.get("spikes"):
                d.polygon([(x, y - 22 * k * 2), (x - 5, y), (x + 5, y)], fill=rgba(c1, 0.95))
            else:
                circle(d, (x, y), 4, c2, 0.9)
    if o.get("chains") and t > 0.4:
        for i in range(4):
            ang = math.radians(45 + i * 90)
            x1, y1 = center[0] + math.cos(ang) * 92, center[1] + math.sin(ang) * 50
            d.line([(x1, y1), (ENEMY[0], ENEMY[1] - 30)], fill=rgba(c2, 0.9), width=3)
    merge(canvas, layer, 6)


def m_net(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    drop = ease(min(1.0, t * 2.2))
    top = -20 + (ENEMY[1] - 110 + 20) * drop
    for i in range(-4, 5):
        d.line([(ENEMY[0] + i * 16, top), (ENEMY[0] + i * 26, top + 130)], fill=rgba(c1, 0.9), width=2)
    for j in range(7):
        y = top + j * 22
        d.line([(ENEMY[0] - 66 - j * 3, y), (ENEMY[0] + 66 + j * 3, y)], fill=rgba(c2, 0.8), width=2)
    merge(canvas, layer, 5)


def m_stars(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    points = [(ENEMY[0] + math.cos(math.radians(72 * i - 90)) * 80, ENEMY[1] - 30 + math.sin(math.radians(72 * i - 90)) * 70) for i in range(5)]
    reveal = min(5, int(t * 9))
    for i in range(reveal):
        circle(d, points[i], 8, c2, 1)
        if i > 0:
            d.line([points[i - 1], points[i]], fill=rgba(c1, 0.9), width=3)
    if reveal >= 5:
        d.line([points[4], points[0]], fill=rgba(c1, 0.9), width=3)
        star = [points[0], points[2], points[4], points[1], points[3], points[0]]
        d.line(star, fill=rgba(c2, 0.8), width=2)
    merge(canvas, layer, 6)
    if t > 0.65:
        flash(canvas, c2, 0.5 * (1 - (t - 0.65) / 0.35))
        impact(canvas, t, 0.65, c1, c2, 1.3)


def m_press(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    drop = ease(min(1.0, t * 2.4))
    y = -60 + (ENEMY[1] - 118 + 60) * drop
    d.rectangle((ENEMY[0] - 56, y, ENEMY[0] + 56, y + 74), fill=rgba(c1, 0.9), outline=rgba(c2, 1), width=4)
    for i in range(3):
        d.line([(ENEMY[0] - 40 + i * 40, y + 12), (ENEMY[0] - 40 + i * 40, y + 62)], fill=rgba(c2, 0.9), width=3)
    merge(canvas, layer, 6)
    impact(canvas, t, 0.5, c1, c2, 1.1)


def m_roar(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    src = CASTER if o.get("buff") else (CASTER[0] + 20, CASTER[1] - 30)
    for i in range(4):
        k = (t * 1.5 - i * 0.18)
        if 0 < k < 1:
            r = (30 + 260 * ease(k)) * (1.3 if o.get("big") else 1.0)
            d.arc((src[0] - r, src[1] - 30 - r * 0.7, src[0] + r, src[1] - 30 + r * 0.7), -50, 50, fill=rgba(c1 if i % 2 else c2, 1 - k), width=5)
    merge(canvas, layer, 5)
    if not o.get("buff"):
        impact(canvas, t, 0.5, c1, c2, 0.9)
    else:
        m_aura(canvas, t, c1, c2, rng, {})


def m_smoke(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    for i in range(22):
        k = ease(min(1.0, (t - rng.uniform(0, 0.15)) / 0.8))
        ang = rng.uniform(0, 6.28)
        dist = rng.uniform(0, 80 if o.get("bomb") else 55)
        x = CASTER[0] + math.cos(ang) * dist * k
        y = CASTER[1] - 20 + math.sin(ang) * dist * 0.6 * k - 10 * t
        circle(d, (x, y), 30 * k, c1 if i % 2 else c2, 0.32 * (1 - max(0, t - 0.6)))
    merge(canvas, layer, 10)
    if o.get("ghost") and t > 0.3:
        layer, d = fx_layer()
        d.ellipse((CASTER[0] - 18 + 60 * t, CASTER[1] - 80, CASTER[0] + 18 + 60 * t, CASTER[1] - 44), outline=rgba(c1, 0.6), width=3)
        merge(canvas, layer, 4)


def m_lotus(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    center = (CASTER[0], CASTER[1] + 10)
    bloom = ease(min(1.0, t * 2.2))
    for ring_i, (n, rad) in enumerate(((8, 62), (6, 44))):
        for i in range(n):
            ang = math.radians(360 / n * i + ring_i * 20)
            tip = (center[0] + math.cos(ang) * rad * bloom, center[1] - 24 + math.sin(ang) * rad * 0.7 * bloom)
            base1 = (center[0] + math.cos(ang + 0.35) * 14, center[1] - 24 + math.sin(ang + 0.35) * 8)
            base2 = (center[0] + math.cos(ang - 0.35) * 14, center[1] - 24 + math.sin(ang - 0.35) * 8)
            d.polygon([base1, tip, base2], fill=rgba(c1 if ring_i == 0 else c2, 0.75), outline=rgba(WHITE, 0.9))
    merge(canvas, layer, 6)


def m_swarm(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    count = 14 if o.get("few") else 46
    for i in range(count):
        phase = rng.uniform(0, 6.28)
        k = ease(min(1.0, t * 1.6))
        ang = phase + t * 9
        cx = CASTER[0] + 40 + (ENEMY[0] - CASTER[0] - 40) * k
        x = cx + math.cos(ang) * (26 + (i % 5) * 6)
        y = ENEMY[1] - 30 + math.sin(ang) * 20 + rng.uniform(-12, 12)
        circle(d, (x, y), 3, c1 if i % 3 else c2, 0.95)
    merge(canvas, layer, 4)
    impact(canvas, t, 0.55, c1, c2, 0.7)


def m_coins(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    for i in range(14):
        k = (t - rng.uniform(0, 0.3)) / 0.55
        if 0 < k < 1:
            x = CASTER[0] + 30 + (ENEMY[0] - CASTER[0] - 30) * ease(k) + rng.uniform(-10, 10)
            y = ENEMY[1] - 60 - math.sin(k * math.pi) * 70 + rng.uniform(-10, 10)
            width = abs(math.cos(k * 14)) * 9 + 1
            d.ellipse((x - width, y - 9, x + width, y + 9), fill=rgba(c1, 0.95), outline=rgba(c2, 1))
    merge(canvas, layer, 5)
    impact(canvas, t, 0.6, c1, c2, 1.2)


def m_claw(canvas, t, c1, c2, rng, o):
    count = o.get("count", 3)
    layer, d = fx_layer()
    k = ease(min(1.0, t * 2.2))
    fade = 1 - max(0.0, t - 0.55) * 2
    size = 1.25 if o.get("big") else 1.0
    for i in range(count):
        off = (i - (count - 1) / 2) * 24 * size
        x0, y0 = ENEMY[0] - 60 + off, ENEMY[1] - 110
        x1, y1 = ENEMY[0] + 40 + off, ENEMY[1] + 40
        px, py = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
        d.line([(x0, y0), (px, py)], fill=rgba(c1, 0.9 * fade), width=int(12 * size))
        d.line([(x0, y0), (px, py)], fill=rgba(c2, fade), width=3)
    merge(canvas, layer, 6)
    impact(canvas, t, 0.4, c1, c2, 0.9)


def m_bloom(canvas, t, c1, c2, rng, o):
    m_aura(canvas, t, c1, c2, rng, {})
    layer, d = fx_layer()
    for i in range(6):
        ang = math.radians(60 * i + t * 120)
        x, y = CASTER[0] + math.cos(ang) * 48, CASTER[1] - 30 + math.sin(ang) * 20
        circle(d, (x, y), 9, c2 if i % 2 else c1, 0.9)
    merge(canvas, layer, 5)


def m_totem(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    rise = ease(min(1.0, t * 2.4))
    x = CASTER[0] + 70
    top = 214 - 110 * rise
    d.rectangle((x - 16, top, x + 16, 214), fill=rgba(c1, 0.9), outline=rgba(c2, 1), width=3)
    d.ellipse((x - 10, top + 14, x + 10, top + 34), outline=rgba(c2, 1), width=3)
    d.line([(x - 12, top + 52), (x + 12, top + 52)], fill=rgba(c2, 1), width=3)
    merge(canvas, layer, 6)
    m_drain(canvas, max(0.0, t - 0.2) / 0.8, c1, c2, rng, {})


def m_execute(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    center = (ENEMY[0], ENEMY[1] - 30)
    if t < 0.45:
        r = 90 * (1 - ease(t / 0.45)) + 12
        d.ellipse((center[0] - r, center[1] - r, center[0] + r, center[1] + r), outline=rgba(c2, 0.95), width=3)
        d.line([(center[0] - r - 12, center[1]), (center[0] + r + 12, center[1])], fill=rgba(c2, 0.9), width=2)
        d.line([(center[0], center[1] - r - 12), (center[0], center[1] + r + 12)], fill=rgba(c2, 0.9), width=2)
    else:
        k = ease((t - 0.45) / 0.25)
        fade = 1 - max(0.0, t - 0.7) * 2.5
        sx = ENEMY[0] + (80 if o.get("behind") else -140)
        ex = sx + (-220 if o.get("behind") else 280) * k
        for w, col, a in ((26, c1, 0.5), (10, c1, 0.9), (4, WHITE, 1.0)):
            d.line([(sx, ENEMY[1] - 150), (ex, ENEMY[1] + 50)], fill=rgba(col, a * fade), width=w)
    merge(canvas, layer, 8)
    if t > 0.6:
        flash(canvas, c2, 0.45 * (1 - (t - 0.6) / 0.4))
        impact(canvas, t, 0.6, c1, c2, 1.0)


def m_foe(canvas, t, c1, c2, rng, o):
    layer, d = fx_layer()
    size = 1.3 if o.get("big") else 1.0
    k = ease(min(1.0, t * 2.0))
    fade = 1 - max(0.0, t - 0.55) * 2
    for i in range(3):
        x0, y0 = CASTER[0] + 50 + i * 14, CASTER[1] - 130
        x1, y1 = CASTER[0] - 50 + i * 14, CASTER[1] + 20
        px, py = x0 + (x1 - x0) * k, y0 + (y1 - y0) * k
        d.line([(x0, y0), (px, py)], fill=rgba(c1, 0.9 * fade), width=int(12 * size))
        d.line([(x0, y0), (px, py)], fill=rgba(c2, fade), width=3)
    merge(canvas, layer, 6)
    if t > 0.35:
        layer, d = fx_layer()
        j = (t - 0.35) / 0.65
        for i in range(3):
            ring(d, (CASTER[0], CASTER[1] + 24), (24 + 80 * ease(j) - i * 18) * size, c1, 1 - j, 4 - i)
        circle(d, (CASTER[0], CASTER[1] - 20), 34 * size * (1 - j * 0.4), c2, 0.7 * (1 - j))
        merge(canvas, layer, 6)
        flash(canvas, c1, 0.25 * (1 - j))


MOTIFS = {
    "slash": m_slash, "cleave": m_cleave, "blades": m_blades, "beam": m_beam, "burst": m_burst, "quake": m_quake, "flame": m_flame,
    "bolt": m_bolt, "wave": m_wave, "wind": m_wind, "cloud": m_cloud, "aura": m_aura, "shield": m_shield, "drain": m_drain, "rune": m_rune,
    "net": m_net, "stars": m_stars, "press": m_press, "roar": m_roar, "smoke": m_smoke, "lotus": m_lotus, "swarm": m_swarm, "coins": m_coins,
    "claw": m_claw, "bloom": m_bloom, "totem": m_totem, "execute": m_execute, "foe": m_foe,
}

FOE_COLOR = (62, 36, 58)
HERO_COLOR = (84, 132, 190)
SELF_MOTIFS = {"aura", "shield", "smoke", "lotus", "bloom"}


def render_frame(key: str, i: int) -> Image.Image:
    motif, c1, c2, opts = anims.SPECS[key]
    t = i / (FRAMES - 1)
    rng = random.Random(sum(ord(ch) for ch in key) * 977)
    foe_attack = motif == "foe"
    canvas = background()
    hero_hit = 0.0
    foe_hit = 0.0
    if foe_attack and 0.4 < t < 0.7:
        hero_hit = 1.0 - abs(t - 0.5) * 5
    if not foe_attack and motif not in SELF_MOTIFS and 0.4 < t < 0.75:
        foe_hit = 1.0 - abs(t - 0.52) * 4
    figure(canvas, ENEMY, FOE_COLOR, 1.15, foe=True, hit=max(0.0, foe_hit))
    figure(canvas, CASTER, HERO_COLOR, 1.0, hit=max(0.0, hero_hit))
    MOTIFS[motif](canvas, t, c1, c2, rng, opts)
    return canvas


def to_gif(frames: list) -> io.BytesIO:
    out = io.BytesIO()
    paletted = [frame.convert("RGB").convert("P", palette=Image.Palette.ADAPTIVE, colors=64) for frame in frames]
    paletted[0].save(out, format="GIF", save_all=True, append_images=paletted[1:], duration=FRAME_MS, loop=0, optimize=True, disposal=2)
    out.seek(0)
    return out


def render(key: str) -> io.BytesIO:
    return to_gif([render_frame(key, i) for i in range(FRAMES)])


def read_frames(source) -> list:
    image = Image.open(source)
    frames = []
    for index in range(getattr(image, "n_frames", 1)):
        image.seek(index)
        frames.append(image.convert("RGB"))
    return frames


@lru_cache(maxsize=160)
def compose(keys: tuple) -> bytes:
    present = [key for key in keys if anims.exists(key)]
    if not present:
        return b""
    if len(present) == 1:
        with open(anims.path(present[0]), "rb") as handle:
            return handle.read()
    frames = []
    for key in present:
        frames.extend(read_frames(anims.path(key)))
    return to_gif(frames).getvalue()
