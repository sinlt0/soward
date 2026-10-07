import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

CARD_WIDTH = 1200
CARD_HEIGHT = 630
AVATAR_ZONE_WIDTH = 480

FONTS_DIR = Path(__file__).parent.parent / "assets" / "fonts"

STYLE_REGULAR = "regular"
STYLE_ITALIC = "italic"
STYLE_BOLD = "bold"
STYLE_BOLDITALIC = "bolditalic"

FONT_STYLES = {
    "classic": {
        "label": "Classic Serif",
        "premium": False,
        "system": True,
        "weights": {
            STYLE_REGULAR: "DejaVuSerif.ttf",
            STYLE_ITALIC: "DejaVuSerif-Italic.ttf",
            STYLE_BOLD: "DejaVuSerif-Bold.ttf",
            STYLE_BOLDITALIC: "DejaVuSerif-BoldItalic.ttf",
        },
    },
    "playfair": {
        "label": "Playfair Display",
        "premium": False,
        "system": False,
        "weights": {
            STYLE_REGULAR: "PlayfairDisplay-Regular.ttf",
            STYLE_ITALIC: "PlayfairDisplay-Italic.ttf",
            STYLE_BOLD: "PlayfairDisplay-Bold.ttf",
            STYLE_BOLDITALIC: "PlayfairDisplay-BoldItalic.ttf",
        },
    },
    "garamond": {
        "label": "EB Garamond",
        "premium": False,
        "system": False,
        "weights": {
            STYLE_REGULAR: "EBGaramond-Regular.ttf",
            STYLE_ITALIC: "EBGaramond-Italic.ttf",
            STYLE_BOLD: "EBGaramond-Bold.ttf",
            STYLE_BOLDITALIC: "EBGaramond-BoldItalic.ttf",
        },
    },
    "cormorant": {
        "label": "Cormorant Garamond",
        "premium": True,
        "system": False,
        "weights": {
            STYLE_REGULAR: "CormorantGaramond-Regular.ttf",
            STYLE_ITALIC: "CormorantGaramond-Italic.ttf",
            STYLE_BOLD: "CormorantGaramond-SemiBold.ttf",
            STYLE_BOLDITALIC: "CormorantGaramond-BoldItalic.ttf",
        },
    },
    "baskerville": {
        "label": "Libre Baskerville",
        "premium": True,
        "system": False,
        "weights": {
            STYLE_REGULAR: "LibreBaskerville-Regular.ttf",
            STYLE_ITALIC: "LibreBaskerville-Italic.ttf",
            STYLE_BOLD: "LibreBaskerville-Bold.ttf",
            STYLE_BOLDITALIC: "LibreBaskerville-BoldItalic.ttf",
        },
    },
    "typewriter": {
        "label": "Special Elite",
        "premium": True,
        "system": False,
        "weights": {
            STYLE_REGULAR: "SpecialElite-Regular.ttf",
        },
    },
    "handwritten": {
        "label": "Caveat",
        "premium": True,
        "system": False,
        "weights": {
            STYLE_REGULAR: "Caveat-Regular.ttf",
            STYLE_BOLD: "Caveat-Bold.ttf",
        },
    },
    "bebas": {
        "label": "Bebas Neue",
        "premium": True,
        "system": False,
        "weights": {
            STYLE_REGULAR: "BebasNeue-Regular.ttf",
        },
    },
}

DEFAULT_FONT_KEY = "classic"
DEFAULT_STYLE_KEY = STYLE_ITALIC

STYLE_LABELS = {
    STYLE_REGULAR: "Regular",
    STYLE_ITALIC: "Italic",
    STYLE_BOLD: "Bold",
    STYLE_BOLDITALIC: "Bold Italic",
}

ACCENT_COLORS = {
    "gray": {"label": "Classic Gray", "premium": False, "rgb": (150, 150, 155)},
    "gold": {"label": "Gold", "premium": False, "rgb": (198, 160, 90)},
    "rose": {"label": "Rose", "premium": False, "rgb": (210, 120, 130)},
    "sapphire": {"label": "Sapphire", "premium": True, "rgb": (100, 140, 210)},
    "emerald": {"label": "Emerald", "premium": True, "rgb": (95, 180, 140)},
    "violet": {"label": "Violet", "premium": True, "rgb": (155, 120, 210)},
}

DEFAULT_ACCENT_KEY = "gray"


def is_premium_accent(accent_key: str) -> bool:
    color = ACCENT_COLORS.get(accent_key)
    return bool(color and color["premium"])


def resolve_accent_key(requested: str | None) -> str:
    if requested and requested in ACCENT_COLORS:
        return requested
    return DEFAULT_ACCENT_KEY


def is_premium_font(font_key: str) -> bool:
    style = FONT_STYLES.get(font_key)
    return bool(style and style["premium"])


def resolve_font_key(requested: str | None) -> str:
    if requested and requested in FONT_STYLES:
        return requested
    return DEFAULT_FONT_KEY


def available_styles(font_key: str) -> list[str]:
    style = FONT_STYLES.get(font_key, FONT_STYLES[DEFAULT_FONT_KEY])
    return list(style["weights"].keys())


def resolve_style_key(font_key: str, requested: str | None) -> str:
    styles = available_styles(font_key)
    if requested and requested in styles:
        return requested
    if DEFAULT_STYLE_KEY in styles:
        return DEFAULT_STYLE_KEY
    return styles[0]


def _load_font(filename: str, is_system: bool, size: int) -> ImageFont.FreeTypeFont:
    try:
        if is_system:
            return ImageFont.truetype(filename, size)
        return ImageFont.truetype(str(FONTS_DIR / filename), size)
    except OSError:
        return ImageFont.load_default()


def _font_for(font_key: str, style_key: str, size: int) -> ImageFont.FreeTypeFont:
    style = FONT_STYLES[font_key]
    weights = style["weights"]
    filename = weights.get(style_key) or weights.get(DEFAULT_STYLE_KEY) or next(iter(weights.values()))
    return _load_font(filename, style["system"], size)


def _accent_font(font_key: str, size: int) -> ImageFont.FreeTypeFont:
    style = FONT_STYLES[font_key]
    weights = style["weights"]
    filename = weights.get(STYLE_BOLD) or weights.get(STYLE_REGULAR) or next(iter(weights.values()))
    return _load_font(filename, style["system"], size)


def _process_avatar(avatar_bytes: bytes, colorize: bool) -> Image.Image:
    avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGB")
    avatar = ImageOps.fit(avatar, (AVATAR_ZONE_WIDTH, CARD_HEIGHT), method=Image.Resampling.LANCZOS)

    if not colorize:
        avatar = ImageOps.grayscale(avatar).convert("RGB")
        avatar = ImageEnhance.Contrast(avatar).enhance(1.35)
        avatar = ImageEnhance.Brightness(avatar).enhance(0.9)

    return avatar


def _apply_gradient_fade(avatar: Image.Image) -> Image.Image:
    gradient = Image.new("L", (AVATAR_ZONE_WIDTH, CARD_HEIGHT), 0)
    gradient_draw = ImageDraw.Draw(gradient)
    fade_start = int(AVATAR_ZONE_WIDTH * 0.45)
    for x in range(AVATAR_ZONE_WIDTH):
        if x < fade_start:
            alpha = 0
        else:
            progress = (x - fade_start) / (AVATAR_ZONE_WIDTH - fade_start)
            alpha = int(255 * (progress ** 0.8))
        gradient_draw.line([(x, 0), (x, CARD_HEIGHT)], fill=alpha)

    black = Image.new("RGB", (AVATAR_ZONE_WIDTH, CARD_HEIGHT), (0, 0, 0))
    return Image.composite(black, avatar, gradient)


def _fit_quote_text(draw: ImageDraw.ImageDraw, font_key: str, style_key: str, text: str, max_width: int, max_height: int) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    size = 64
    min_size = 24
    while size >= min_size:
        font = _font_for(font_key, style_key, size)
        avg_char_width = draw.textlength("abcdefghijklmnopqrstuvwxyz", font=font) / 26
        wrap_width = max(10, int(max_width / max(avg_char_width, 1)))
        lines = textwrap.wrap(text, width=wrap_width, break_long_words=False, break_on_hyphens=False) or [text]

        line_height = size * 1.3
        total_height = line_height * len(lines)

        widest_line = max((draw.textlength(line, font=font) for line in lines), default=0)

        if total_height <= max_height and widest_line <= max_width and len(lines) <= 7:
            return font, lines

        size -= 3

    font = _font_for(font_key, style_key, min_size)
    avg_char_width = draw.textlength("abcdefghijklmnopqrstuvwxyz", font=font) / 26
    wrap_width = max(10, int(max_width / max(avg_char_width, 1)))
    lines = textwrap.wrap(text, width=wrap_width, break_long_words=False, break_on_hyphens=False) or [text]
    return font, lines


def _draw_text_with_shadow(draw: ImageDraw.ImageDraw, position: tuple[float, float], text: str, font: ImageFont.FreeTypeFont, fill: tuple[int, int, int]) -> None:
    x, y = position
    draw.text((x + 2, y + 3), text, font=font, fill=(0, 0, 0))
    draw.text((x, y), text, font=font, fill=fill)


def render_quote_card(
    avatar_bytes: bytes,
    quote_text: str,
    author_name: str,
    font_key: str = DEFAULT_FONT_KEY,
    accent_rgb: tuple[int, int, int] = (150, 150, 155),
    style_key: str | None = None,
    colorize_avatar: bool = False,
) -> io.BytesIO:
    font_key = resolve_font_key(font_key)
    style_key = resolve_style_key(font_key, style_key)

    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (8, 8, 10))

    avatar = _process_avatar(avatar_bytes, colorize_avatar)
    avatar = _apply_gradient_fade(avatar)
    card.paste(avatar, (0, 0))

    draw = ImageDraw.Draw(card)

    text_zone_x = AVATAR_ZONE_WIDTH - 40
    text_zone_width = CARD_WIDTH - text_zone_x - 70

    mark_height = 90
    footer_height = 70
    vertical_margin = 60
    text_zone_max_height = CARD_HEIGHT - mark_height - footer_height - (vertical_margin * 2)

    quote_font, lines = _fit_quote_text(draw, font_key, style_key, quote_text, text_zone_width, text_zone_max_height)
    line_height = quote_font.size * 1.3
    total_text_height = line_height * len(lines)

    block_height = mark_height + total_text_height + footer_height
    block_start_y = max(vertical_margin, (CARD_HEIGHT - block_height) / 2)

    mark_font = _accent_font(font_key, 84)
    mark_y = block_start_y
    _draw_text_with_shadow(draw, (text_zone_x - 4, mark_y), "\u201c", mark_font, accent_rgb)

    y = block_start_y + mark_height
    for line in lines:
        _draw_text_with_shadow(draw, (text_zone_x, y), line, quote_font, (238, 238, 240))
        y += line_height

    divider_y = min(y + 14, CARD_HEIGHT - footer_height + 6)
    draw.line([(text_zone_x, divider_y), (text_zone_x + 60, divider_y)], fill=accent_rgb, width=2)

    name_font = _accent_font(font_key, 27)
    name_y = min(divider_y + 14, CARD_HEIGHT - 44)
    _draw_text_with_shadow(draw, (text_zone_x, name_y), author_name, name_font, accent_rgb)

    buffer = io.BytesIO()
    card.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer
