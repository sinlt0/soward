import io
import textwrap

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps

CARD_WIDTH = 1000
CARD_HEIGHT = 400
AVATAR_SIZE = 180


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _circular_avatar(avatar_bytes: bytes, size: int) -> Image.Image:
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    avatar = ImageOps.fit(avatar, (size, size), method=Image.Resampling.LANCZOS)

    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)

    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(avatar, (0, 0), mask=mask)
    return output


def _background(background_bytes: bytes | None, accent_rgb: tuple[int, int, int]) -> Image.Image:
    if background_bytes:
        bg = Image.open(io.BytesIO(background_bytes)).convert("RGB")
        bg = ImageOps.fit(bg, (CARD_WIDTH, CARD_HEIGHT), method=Image.Resampling.LANCZOS)
        overlay = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (10, 10, 12, 140))
        bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
        return bg

    bg = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (18, 18, 22))
    draw = ImageDraw.Draw(bg)
    for x in range(CARD_WIDTH):
        blend = x / CARD_WIDTH
        r = int(18 + (accent_rgb[0] - 18) * blend * 0.25)
        g = int(18 + (accent_rgb[1] - 18) * blend * 0.25)
        b = int(22 + (accent_rgb[2] - 22) * blend * 0.25)
        draw.line([(x, 0), (x, CARD_HEIGHT)], fill=(r, g, b))
    return bg


def _wrap_fit(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    avg_char_width = draw.textlength("abcdefghij", font=font) / 10
    wrap_width = max(10, int(max_width / max(avg_char_width, 1)))
    return textwrap.wrap(text, width=wrap_width) or [text]


def _fit_title_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_lines: int, start_size: int = 40) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    size = start_size
    min_size = 18
    while size >= min_size:
        font = _load_font(size, bold=True)
        lines = _wrap_fit(draw, text, font, max_width)
        if len(lines) <= max_lines:
            return font, lines
        size -= 2
    font = _load_font(min_size, bold=True)
    lines = _wrap_fit(draw, text, font, max_width)
    return font, lines[:max_lines]


def render_greeting_card(
    avatar_bytes: bytes,
    display_name: str,
    title_text: str,
    subtitle_text: str,
    layout: str = "classic",
    accent_rgb: tuple[int, int, int] = (127, 179, 213),
    background_bytes: bytes | None = None,
) -> io.BytesIO:
    card = _background(background_bytes, accent_rgb)
    draw = ImageDraw.Draw(card)
    avatar = _circular_avatar(avatar_bytes, AVATAR_SIZE)

    text_max_width = CARD_WIDTH - 500 if layout in ("left", "right") else CARD_WIDTH - 120
    max_title_lines = 2 if layout in ("left", "right") else 2
    title_font, title_lines = _fit_title_font(draw, title_text, text_max_width, max_title_lines)

    subtitle_font = _load_font(20)
    subtitle_lines = _wrap_fit(draw, subtitle_text, subtitle_font, text_max_width)[:2]

    if layout == "left":
        avatar_x, avatar_y = 60, (CARD_HEIGHT - AVATAR_SIZE) // 2
        text_x = avatar_x + AVATAR_SIZE + 50
        text_align_right = False
    elif layout == "right":
        avatar_x, avatar_y = CARD_WIDTH - AVATAR_SIZE - 60, (CARD_HEIGHT - AVATAR_SIZE) // 2
        text_x = None
        text_align_right = True
    elif layout == "banner":
        avatar_x, avatar_y = (CARD_WIDTH - AVATAR_SIZE) // 2, 30
        text_x = None
        text_align_right = None
    else:
        avatar_x, avatar_y = (CARD_WIDTH - AVATAR_SIZE) // 2, 40
        text_x = None
        text_align_right = None

    draw.ellipse(
        [avatar_x - 5, avatar_y - 5, avatar_x + AVATAR_SIZE + 5, avatar_y + AVATAR_SIZE + 5],
        outline=accent_rgb, width=5,
    )
    card.paste(avatar, (avatar_x, avatar_y), mask=avatar)

    line_height = title_font.size + 12
    subtitle_line_height = subtitle_font.size + 8
    text_block_height = (len(title_lines) * line_height) + (len(subtitle_lines) * subtitle_line_height) + 10

    def draw_block(x_center_or_left: int, y_start: int, align: str):
        y = min(y_start, CARD_HEIGHT - text_block_height - 20)
        y = max(y, 10)
        for line in title_lines:
            w = draw.textlength(line, font=title_font)
            x = x_center_or_left if align == "left" else (x_center_or_left - w if align == "right" else x_center_or_left - w / 2)
            draw.text((x, y), line, font=title_font, fill=(240, 240, 245))
            y += line_height
        for line in subtitle_lines:
            w = draw.textlength(line, font=subtitle_font)
            x = x_center_or_left if align == "left" else (x_center_or_left - w if align == "right" else x_center_or_left - w / 2)
            draw.text((x, y), line, font=subtitle_font, fill=(190, 190, 196))
            y += subtitle_line_height

    if layout == "left":
        draw_block(text_x, avatar_y + 10, "left")
    elif layout == "right":
        draw_block(avatar_x - 50, avatar_y + 10, "right")
    else:
        draw_block(CARD_WIDTH // 2, avatar_y + AVATAR_SIZE + 30, "center")

    buffer = io.BytesIO()
    card.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
