import io
import math
import random
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from utils import cosmetics, pet_art

FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
W, H = 1000, 560


def font(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(FONT_DIR / f"Poppins-{weight}.ttf"), size)
    except OSError:
        try:
            return ImageFont.truetype("DejaVuSans-Bold.ttf" if weight == "Bold" else "DejaVuSans.ttf", size)
        except OSError:
            return ImageFont.load_default()


def gradient(size, c1, c2) -> Image.Image:
    w, h = size
    base = Image.new("RGB", (w, h), c1)
    top = Image.new("RGB", (w, h), c2)
    vertical = Image.linear_gradient("L").resize((w, h))
    horizontal = Image.linear_gradient("L").rotate(90).resize((w, h))
    mask = Image.blend(vertical, horizontal, 0.5)
    return Image.composite(top, base, mask)


def pattern_layer(kind: str, size, accent) -> Image.Image:
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    rng = random.Random(7)
    if kind == "dots":
        for x in range(20, w, 36):
            for y in range(20, h, 36):
                d.ellipse((x - 2, y - 2, x + 2, y + 2), fill=accent + (36,))
    elif kind == "stars":
        for _ in range(70):
            x, y, r = rng.randint(0, w), rng.randint(0, h), rng.choice((1, 1, 2, 3))
            d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 255, 255, rng.randint(50, 150)))
    elif kind == "waves":
        for row in range(8):
            y0 = 60 + row * 70
            points = [(x, y0 + 14 * math.sin(x / 55 + row)) for x in range(0, w + 10, 10)]
            d.line(points, fill=accent + (40,), width=3)
    elif kind == "petals":
        for _ in range(26):
            x, y = rng.randint(0, w), rng.randint(0, h)
            rx, ry = rng.randint(7, 14), rng.randint(4, 8)
            d.ellipse((x - rx, y - ry, x + rx, y + ry), fill=accent + (60,))
    elif kind == "grid":
        for x in range(0, w, 50):
            d.line([(x, 0), (x, h)], fill=accent + (26,), width=1)
        for y in range(0, h, 50):
            d.line([(0, y), (w, y)], fill=accent + (26,), width=1)
    return layer


def background(theme_key: str, size=(W, H)) -> tuple[Image.Image, tuple]:
    theme = cosmetics.THEMES.get(theme_key) or cosmetics.THEMES["graphite"]
    base = gradient(size, theme["bg"][0], theme["bg"][1]).convert("RGBA")
    base.alpha_composite(pattern_layer(theme["pattern"], size, theme["accent"]))
    return base, theme["accent"]


def panel(canvas: Image.Image, box, radius=28, fill=(255, 255, 255, 30), outline=(255, 255, 255, 60)) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)
    canvas.alpha_composite(layer)


def wrap(text: str, fnt, width: int, lines: int) -> list[str]:
    words, out, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if fnt.getlength(trial) <= width:
            line = trial
        else:
            if line:
                out.append(line)
            line = word
        if len(out) >= lines:
            break
    if line and len(out) < lines:
        out.append(line)
    if len(out) == lines and " ".join(out) != text:
        out[-1] = out[-1].rstrip(".,") + "..."
    return out


def circle_avatar(image: Optional[Image.Image], size: int, ring) -> Image.Image:
    out = Image.new("RGBA", (size + 16, size + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.ellipse((0, 0, size + 15, size + 15), fill=ring + (255,))
    if image is None:
        inner = Image.new("RGBA", (size, size), (70, 72, 80, 255))
    else:
        inner = ImageOps.fit(image.convert("RGBA"), (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    out.paste(inner, (8, 8), mask)
    return out


def pill(canvas, x, y, text, color, fnt) -> int:
    width = int(fnt.getlength(text)) + 30
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((x, y, x + width, y + 34), radius=17, fill=color + (60,), outline=color + (230,), width=2)
    d.ellipse((x + 11, y + 12, x + 21, y + 22), fill=color + (255,))
    d.text((x + 28, y + 5), text, font=fnt, fill=(255, 255, 255, 255))
    canvas.alpha_composite(layer)
    return width + 10


def bar(canvas, box, fraction: float, color) -> None:
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=(y1 - y0) // 2, fill=(0, 0, 0, 90))
    fraction = max(0.0, min(1.0, fraction))
    fill_w = max(int((x1 - x0) * fraction), y1 - y0) if fraction > 0 else 0
    if fill_w > 0:
        d.rounded_rectangle((x0, y0, x0 + fill_w, y1), radius=(y1 - y0) // 2, fill=color + (255,))
    canvas.alpha_composite(layer)


def pet_block(canvas, pet: Optional[dict], box, accent) -> None:
    x0, y0, x1, y1 = box
    cx = (x0 + x1) // 2
    d = ImageDraw.Draw(canvas)
    if pet is None:
        d.ellipse((cx - 70, y0 + 60, cx + 70, y0 + 230), outline=accent + (160,), width=4)
        d.text((cx, y0 + 145), "?", font=font(64, "Bold"), fill=accent + (200,), anchor="mm")
        d.text((cx, y0 + 270), "No pet yet", font=font(22, "Bold"), fill=(255, 255, 255, 255), anchor="mm")
        d.text((cx, y0 + 304), "Use pet adopt", font=font(18), fill=(225, 225, 232, 255), anchor="mm")
        return
    image = pet_art.render(pet["species"], pet["xp"], pet.get("outfit", ""), 310)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((cx - 90, y0 + 292, cx + 90, y0 + 318), fill=(0, 0, 0, 70))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)))
    canvas.alpha_composite(image, (cx - 155, y0 + 10))
    d.text((cx, y0 + 338), pet["name"], font=font(26, "Bold"), fill=(255, 255, 255, 255), anchor="mm")
    stage = cosmetics.stage_name(pet["xp"])
    done, need, ceiling = cosmetics.stage_progress(pet["xp"])
    d.text((cx, y0 + 370), f"{stage} {cosmetics.SPECIES[pet['species']]['label']}", font=font(18), fill=accent + (255,), anchor="mm")
    bar(canvas, (x0 + 30, y0 + 392, x1 - 30, y0 + 408), (done / need) if need else 1.0, accent)
    note = f"{pet['xp']:,} / {ceiling:,} xp" if ceiling else f"{pet['xp']:,} xp · max stage"
    d.text((cx, y0 + 428), note, font=font(15), fill=(215, 215, 224, 255), anchor="mm")


def render_profile(data: dict) -> io.BytesIO:
    canvas, accent = background(data.get("theme", "graphite"))
    panel(canvas, (28, 28, 640, 532))
    panel(canvas, (660, 28, 972, 532))
    d = ImageDraw.Draw(canvas)
    avatar = circle_avatar(data.get("avatar"), 132, accent)
    canvas.alpha_composite(avatar, (56, 56))
    name = data["name"]
    name_font = font(38, "Bold")
    while name_font.getlength(name) > 400 and name_font.size > 22:
        name_font = font(name_font.size - 2, "Bold")
    d.text((222, 70), name, font=name_font, fill=(255, 255, 255, 255))
    cult = data.get("cultivation")
    extra = data.get("title") or data.get("pronouns") or ""
    subtitle = " · ".join(bit for bit in ((cult or {}).get("title", ""), extra) if bit)
    if subtitle:
        d.text((222, 70 + name_font.size + 10), subtitle, font=font(20, "Medium"), fill=accent + (255,))
    stats = []
    stats.append(cult["realm"] if cult else "Not cultivating yet")
    stats.append(f"{data.get('coins', 0):,} coins")
    if data.get("diamonds"):
        stats.append(f"{data['diamonds']:,} diamonds")
    line = "  ·  ".join(stats)
    stat_font = font(18)
    while stat_font.getlength(line) > 400 and stat_font.size > 12:
        stat_font = font(stat_font.size - 1)
    d.text((222, 150), line, font=stat_font, fill=(225, 225, 232, 255))
    if cult:
        detail = "  ·  ".join(bit for bit in (f"{cult['path']} Path", cult["way"], cult["race"], f"{cult['titles']} titles") if bit)
        detail_font = font(15)
        while detail_font.getlength(detail) > 400 and detail_font.size > 11:
            detail_font = font(detail_font.size - 1)
        d.text((222, 182), detail, font=detail_font, fill=accent + (255,))
    x, y = 56, 224
    badge_font = font(16, "Medium")
    shown = data.get("badges", [])
    if shown:
        for key in shown:
            label, color = cosmetics.BADGE_STYLES[key]
            if key == "clan" and data.get("clan"):
                label = data["clan"]
            step = int(badge_font.getlength(label)) + 40
            if x + step > 620:
                x, y = 56, y + 42
            x += pill(canvas, x, y, label, color, badge_font)
    else:
        d.text((x, y + 4), "No badges yet", font=font(16), fill=(200, 200, 210, 255))
    y = max(y + 56, 288)
    family_bits = []
    if data.get("partners"):
        family_bits.append("Married to " + ", ".join(data["partners"][:2]))
    if data.get("children"):
        family_bits.append(f"{data['children']} child" + ("ren" if data["children"] != 1 else ""))
    if data.get("parent"):
        family_bits.append(f"Child of {data['parent']}")
    d.text((56, y), "  ·  ".join(family_bits) if family_bits else "No family yet", font=font(17), fill=(225, 225, 232, 255))
    y += 38
    bio = data.get("bio") or ""
    if bio:
        for line in wrap(bio, font(18), 540, 3):
            d.text((56, y), line, font=font(18), fill=(245, 245, 250, 255))
            y += 28
    else:
        d.text((56, y), "No bio yet. Use profile edit.", font=font(18), fill=(190, 190, 200, 255))
        y += 28
    interests = data.get("interests") or []
    if interests:
        text = " · ".join(interests[:6])
        d.text((56, 494), text if font(16).getlength(text) < 560 else text[:60] + "...", font=font(16), fill=accent + (255,))
    pet_block(canvas, data.get("pet"), (660, 28, 972, 532), accent)
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "PNG")
    out.seek(0)
    return out


def render_pet(pet: dict, theme: str, owner_name: str) -> io.BytesIO:
    size = (640, 460)
    canvas, accent = background(theme, size)
    panel(canvas, (20, 20, 620, 440))
    d = ImageDraw.Draw(canvas)
    image = pet_art.render(pet["species"], pet["xp"], pet.get("outfit", ""), 340)
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse((90, 350, 270, 376), fill=(0, 0, 0, 70))
    canvas.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(6)))
    canvas.alpha_composite(image, (30, 48))
    d.text((390, 70), pet["name"], font=font(34, "Bold"), fill=(255, 255, 255, 255), anchor="lm")
    d.text((390, 112), f"{cosmetics.stage_name(pet['xp'])} {cosmetics.SPECIES[pet['species']]['label']}", font=font(20, "Medium"), fill=accent + (255,), anchor="lm")
    d.text((390, 150), f"Owner: {owner_name}", font=font(16), fill=(225, 225, 232, 255), anchor="lm")
    outfit = cosmetics.OUTFITS.get(pet.get("outfit") or "")
    d.text((390, 180), f"Wearing: {outfit['label'] if outfit else 'nothing'}", font=font(16), fill=(225, 225, 232, 255), anchor="lm")
    done, need, ceiling = cosmetics.stage_progress(pet["xp"])
    bar(canvas, (390, 250, 590, 268), (done / need) if need else 1.0, accent)
    note = f"{pet['xp']:,} / {ceiling:,} xp to next stage" if ceiling else f"{pet['xp']:,} xp · fully grown"
    d.text((390, 292), note, font=font(15), fill=(215, 215, 224, 255), anchor="lm")
    d.text((390, 340), "Grows when you use the bot", font=font(15), fill=(190, 190, 200, 255), anchor="lm")
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "PNG")
    out.seek(0)
    return out
