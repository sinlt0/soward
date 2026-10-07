import asyncio
import io
import math
import random

import aiohttp
import discord
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont

from utils import emoji_manager
from utils.components import error_layout, footer_block


def get_font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


SHIP_COMMENTS = {
    100: [
        "Perfect Match! A match made in heaven.",
        "Soulmates! The stars aligned for this one.",
        "Unbreakable bond. This is the real deal.",
    ],
    90: [
        "True Love! You two are meant to be.",
        "Absolutely inseparable. Wedding bells incoming.",
    ],
    75: [
        "Great Potential! A very strong connection.",
        "Sparks are flying between these two.",
    ],
    50: [
        "There's a chance! Definitely worth exploring.",
        "Could go either way, but why not try?",
    ],
    25: [
        "Might need work... but don't give up!",
        "A bit rocky, but stranger things have happened.",
    ],
    0: [
        "Not compatible. Probably better off as friends!",
        "Yeah... let's just say it's complicated.",
    ],
}


def get_ship_comment(rate: int, seed: int) -> str:
    for threshold in (100, 90, 75, 50, 25, 0):
        if rate >= threshold:
            options = SHIP_COMMENTS[threshold]
            return options[seed % len(options)]
    return SHIP_COMMENTS[0][0]


def make_circular_avatar(avatar_bytes: bytes, size: tuple[int, int]) -> Image.Image:
    img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
    img = img.resize(size, Image.Resampling.LANCZOS)

    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size[0], size[1]), fill=255)

    output = Image.new("RGBA", size, (0, 0, 0, 0))
    output.paste(img, (0, 0), mask=mask)
    return output


def get_heart_points(center_x: float, center_y: float, size: float) -> list[tuple[float, float]]:
    points = []
    steps = 100
    for i in range(steps):
        t = (i / steps) * 2 * math.pi
        x = 16 * (math.sin(t) ** 3)
        y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
        points.append((center_x + x * (size / 16), center_y + y * (size / 16)))
    return points


def create_ship_card(avatar1_bytes: bytes, avatar2_bytes: bytes, user1_name: str, user2_name: str, rate: int, seed: int) -> io.BytesIO:
    card_width, card_height = 700, 320

    bg_color = (35, 37, 42)
    card = Image.new("RGBA", (card_width, card_height), bg_color)
    draw = ImageDraw.Draw(card)

    panel_color = (26, 27, 30)
    draw.rounded_rectangle([20, 20, card_width - 20, card_height - 20], radius=20, fill=panel_color)

    avatar_size = (140, 140)
    av1 = make_circular_avatar(avatar_bytes=avatar1_bytes, size=avatar_size)
    av2 = make_circular_avatar(avatar_bytes=avatar2_bytes, size=avatar_size)

    av1_x, av1_y = 60, 50
    av2_x, av2_y = card_width - 60 - avatar_size[0], 50
    card.paste(av1, (av1_x, av1_y), mask=av1)
    card.paste(av2, (av2_x, av2_y), mask=av2)

    border_color = (235, 45, 75) if rate >= 70 else (100, 100, 110)
    draw.ellipse([av1_x - 4, av1_y - 4, av1_x + avatar_size[0] + 4, av1_y + avatar_size[1] + 4], outline=border_color, width=5)
    draw.ellipse([av2_x - 4, av2_y - 4, av2_x + avatar_size[0] + 4, av2_y + avatar_size[1] + 4], outline=border_color, width=5)

    center_x = card_width // 2
    heart_y = 120
    heart_points = get_heart_points(center_x=center_x, center_y=heart_y, size=3.5)

    min_y = min(heart_points, key=lambda p: p[1])[1]
    max_y = max(heart_points, key=lambda p: p[1])[1]
    total_heart_height = max_y - min_y

    draw.polygon(heart_points, fill=(50, 50, 55))

    red_layer = Image.new("RGBA", (card_width, card_height), (0, 0, 0, 0))
    red_draw = ImageDraw.Draw(red_layer)
    red_draw.polygon(heart_points, fill=(235, 45, 75))

    mask_layer = Image.new("L", (card_width, card_height), 0)
    mask_draw = ImageDraw.Draw(mask_layer)

    fill_cutoff_y = max_y - (total_heart_height * (rate / 100.0))
    mask_draw.rectangle([0, fill_cutoff_y, card_width, max_y + 10], fill=255)

    card.paste(red_layer, (0, 0), mask=mask_layer)

    font_large = get_font(42)
    font_names = get_font(22)
    font_comment = get_font(20)

    rate_text = f"{rate}%"
    text_bbox = draw.textbbox((0, 0), rate_text, font=font_large)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]

    text_x = center_x - (text_w / 2)
    text_y = heart_y - (text_h / 2)

    for offset_x in (-2, 0, 2):
        for offset_y in (-2, 0, 2):
            draw.text((text_x + offset_x, text_y + offset_y), rate_text, fill=(20, 20, 20), font=font_large)
    draw.text((text_x, text_y), rate_text, fill=(255, 255, 255), font=font_large)

    def draw_centered_text(x, y, text, font, fill):
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        draw.text((x - (w // 2), y), text, fill=fill, font=font)

    draw_centered_text(av1_x + (avatar_size[0] // 2), av1_y + avatar_size[1] + 15, user1_name[:12], font_names, (220, 220, 220))
    draw_centered_text(av2_x + (avatar_size[0] // 2), av2_y + avatar_size[1] + 15, user2_name[:12], font_names, (220, 220, 220))

    comment = get_ship_comment(rate, seed)
    draw_centered_text(center_x, card_height - 60, comment, font_comment, (255, 215, 0) if rate >= 75 else (200, 200, 200))

    buffer = io.BytesIO()
    card.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


class Ship(commands.Cog):
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: aiohttp.ClientSession | None = None
        self.ship_cache: dict[tuple[int, int], int] = {}

    async def cog_load(self):
        self.session = aiohttp.ClientSession()
        self.reset_ship_cache.start()

    def cog_unload(self):
        self.reset_ship_cache.cancel()
        if self.session:
            self.bot.loop.create_task(self.session.close())

    @tasks.loop(hours=12)
    async def reset_ship_cache(self):
        self.ship_cache.clear()

    async def fetch_avatar_bytes(self, user: discord.abc.User) -> bytes:
        avatar_url = user.display_avatar.with_format("png").with_size(256).url
        async with self.session.get(avatar_url) as resp:
            return await resp.read()

    def get_ship_rate(self, user1_id: int, user2_id: int) -> tuple[int, int]:
        pair = tuple(sorted([user1_id, user2_id]))
        seed = sum(pair)
        rng = random.Random(seed)

        if rng.random() < 0.02:
            return 100, seed

        base_rate = rng.randint(10, 80)
        times_shipped = self.ship_cache.get(pair, 0)
        bonus = times_shipped * 6
        self.ship_cache[pair] = times_shipped + 1

        return min(99, base_rate + bonus), seed

    @commands.command(name="ship", help="Ship two members together and see their compatibility.")
    @commands.guild_only()
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def ship(self, ctx: commands.Context, user1: discord.Member, user2: discord.Member = None):
        e = emoji_manager.get
        if user2 is None:
            user2 = user1
            user1 = ctx.author

        if user1.id == user2.id:
            return await ctx.send(view=error_layout(
                "Can't Ship That", f"{e('heart')} You can't ship someone with themselves — self-love counts differently!"
            ))

        rate, seed = self.get_ship_rate(user1.id, user2.id)

        av1_bytes, av2_bytes = await asyncio.gather(
            self.fetch_avatar_bytes(user1),
            self.fetch_avatar_bytes(user2),
        )

        buffer = await asyncio.to_thread(
            create_ship_card, av1_bytes, av2_bytes, user1.display_name, user2.display_name, rate, seed
        )

        filled = round(rate / 10)
        bar = "❤️" * filled + "🤍" * (10 - filled)

        accent = 0xEB2D4B if rate >= 50 else 0x5A5D63
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=accent)
        container.add_item(discord.ui.TextDisplay(
            f"## {e('heart')} {user1.display_name} x {user2.display_name}"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f"**Match Rating:** {rate}%\n{bar}\n*{get_ship_comment(rate, seed)}*"
        ))
        container.add_item(discord.ui.Separator())
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media="attachment://ship-card.png")
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())
        for item in footer_block():
            container.add_item(item)
        view.add_item(container)

        await ctx.send(file=discord.File(buffer, filename="ship-card.png"), view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Ship(bot))
