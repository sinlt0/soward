import re
from typing import Optional

import discord

from utils import db, message_vars

EMBED_REF_PATTERN = re.compile(r"\{embed:([a-zA-Z0-9_\-]+)\}")

DEFAULT_COLOR = 0x2B2D31


def parse_color(value: Optional[str]) -> int:
    if not value:
        return DEFAULT_COLOR
    try:
        return int(value.lstrip("#"), 16)
    except (ValueError, AttributeError):
        return DEFAULT_COLOR


async def get_template(guild_id: int, name: str) -> Optional[dict]:
    row = await db.raw_fetchone(
        "SELECT * FROM embed_templates WHERE guild_id=? AND name=?", (guild_id, name.lower())
    )
    return dict(row) if row else None


async def get_fields(guild_id: int, name: str) -> list[dict]:
    rows = await db.raw_fetch(
        "SELECT * FROM embed_template_fields WHERE guild_id=? AND embed_name=? ORDER BY position ASC",
        (guild_id, name.lower()),
    )
    return [dict(r) for r in rows]


async def count_fields(guild_id: int, name: str) -> int:
    row = await db.raw_fetchone(
        "SELECT COUNT(*) as c FROM embed_template_fields WHERE guild_id=? AND embed_name=?", (guild_id, name.lower())
    )
    return row["c"] if row else 0


async def add_field(guild_id: int, name: str, field_name: str, field_value: str, inline: bool) -> bool:
    count = await count_fields(guild_id, name)
    if count >= 25:
        return False
    await db.raw_execute(
        "INSERT INTO embed_template_fields (guild_id, embed_name, position, field_name, field_value, inline)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (guild_id, name.lower(), count, field_name, field_value, int(inline)),
    )
    return True


async def remove_field(guild_id: int, name: str, position: int) -> bool:
    fields = await get_fields(guild_id, name)
    if not fields or position < 0 or position >= len(fields):
        return False

    await db.raw_execute(
        "DELETE FROM embed_template_fields WHERE guild_id=? AND embed_name=? AND position=?",
        (guild_id, name.lower(), position),
    )
    remaining = [f for f in fields if f["position"] != position]
    for new_pos, field in enumerate(remaining):
        if field["position"] != new_pos:
            await db.raw_execute(
                "UPDATE embed_template_fields SET position=? WHERE guild_id=? AND embed_name=? AND position=?",
                (new_pos, guild_id, name.lower(), field["position"]),
            )
    return True


async def clear_fields(guild_id: int, name: str) -> None:
    await db.raw_execute(
        "DELETE FROM embed_template_fields WHERE guild_id=? AND embed_name=?", (guild_id, name.lower())
    )


async def list_templates(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch(
        "SELECT * FROM embed_templates WHERE guild_id=? ORDER BY name ASC", (guild_id,)
    )
    return [dict(r) for r in rows]


async def count_templates(guild_id: int) -> int:
    row = await db.raw_fetchone("SELECT COUNT(*) as c FROM embed_templates WHERE guild_id=?", (guild_id,))
    return row["c"] if row else 0


async def get_template_cap(guild_id: int) -> int:
    from config import EMBED_TEMPLATE_MAX_FREE, EMBED_TEMPLATE_MAX_PREMIUM
    row = await db.raw_fetchone("SELECT premium FROM guilds WHERE guild_id=?", (guild_id,))
    is_premium = bool(row["premium"]) if row else False
    return EMBED_TEMPLATE_MAX_PREMIUM if is_premium else EMBED_TEMPLATE_MAX_FREE


def build_discord_embed(template: dict, var_map: Optional[dict] = None, fields: Optional[list[dict]] = None) -> discord.Embed:
    var_map = var_map or {}

    def sub(value: Optional[str]) -> Optional[str]:
        return message_vars.substitute(value, var_map) if value else value

    embed = discord.Embed(
        title=sub(template.get("title")),
        description=sub(template.get("description")),
        color=parse_color(template.get("color")),
        url=sub(template.get("title_url")) or None,
    )

    author_text = sub(template.get("author_text"))
    if author_text:
        embed.set_author(
            name=author_text,
            icon_url=sub(template.get("author_icon")) or None,
            url=sub(template.get("author_url")) or None,
        )

    footer_text = sub(template.get("footer_text"))
    if footer_text:
        embed.set_footer(text=footer_text, icon_url=sub(template.get("footer_icon")) or None)

    image_url = sub(template.get("image_url"))
    if image_url:
        embed.set_image(url=image_url)

    thumbnail_url = sub(template.get("thumbnail_url"))
    if thumbnail_url:
        embed.set_thumbnail(url=thumbnail_url)

    if template.get("use_timestamp"):
        embed.timestamp = discord.utils.utcnow()

    for field in (fields or []):
        embed.add_field(
            name=sub(field["field_name"]) or "\u200b",
            value=sub(field["field_value"]) or "\u200b",
            inline=bool(field["inline"]),
        )

    return embed


async def resolve_embed_refs(guild_id: int, text: str, var_map: Optional[dict] = None) -> tuple[Optional[str], list[discord.Embed]]:
    matches = EMBED_REF_PATTERN.findall(text)
    embeds: list[discord.Embed] = []

    for name in matches:
        template = await get_template(guild_id, name)
        if template:
            fields = await get_fields(guild_id, name)
            embeds.append(build_discord_embed(template, var_map, fields))

    remaining = EMBED_REF_PATTERN.sub("", text).strip()
    if remaining and var_map:
        remaining = message_vars.substitute(remaining, var_map)
    return (remaining or None), embeds


def has_embed_ref(text: str) -> bool:
    return bool(EMBED_REF_PATTERN.search(text))
