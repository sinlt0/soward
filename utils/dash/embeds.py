from __future__ import annotations

import re
import time

import discord

from utils import db, embed_templates, message_vars
from utils.dash.base import (
    ActionContext, action, button, fld, need_bool, need_channel, need_text, row, section, table,
)

NAME_PATTERN = re.compile(r"[a-z0-9_\-]{1,50}")
COLOR_PATTERN = re.compile(r"#?[0-9a-fA-F]{6}")
NO_MENTIONS = discord.AllowedMentions.none()


def _name(values: dict) -> str:
    name = need_text(values, "name", "Name", maxlen=50).lower()
    if not NAME_PATTERN.fullmatch(name):
        raise ValueError("Names can only contain letters, numbers, underscores and hyphens.")
    return name


def _url(values: dict, key: str, label: str) -> str | None:
    text = need_text(values, key, label, maxlen=500, required=False)
    if not text:
        return None
    if not (text.startswith("http://") or text.startswith("https://") or "{" in text):
        raise ValueError(f"{label} must start with http:// or https://.")
    return text


def _color(values: dict) -> str | None:
    text = need_text(values, "color", "Color", maxlen=7, required=False)
    if not text:
        return None
    if not COLOR_PATTERN.fullmatch(text):
        raise ValueError("Color must be a hex code such as #5865F2.")
    return "#" + text.lstrip("#").upper()


def _fields(values: dict) -> list[tuple[str, str, bool]]:
    raw = values.get("fields")
    lines = raw if isinstance(raw, list) else str(raw or "").splitlines()
    out = []
    for line in lines:
        text = str(line).strip()
        if not text:
            continue
        parts = [p.strip() for p in text.split("|")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Field line needs a name and a value separated by |: {text[:40]}")
        inline = len(parts) > 2 and parts[2].lower() in ("inline", "yes", "true", "1", "on")
        if len(parts[0]) > 256:
            raise ValueError("Field names must be 256 characters or fewer.")
        if len(parts[1]) > 1024:
            raise ValueError("Field values must be 1024 characters or fewer.")
        out.append((parts[0], parts[1], inline))
    if len(out) > 25:
        raise ValueError("An embed can have at most 25 fields.")
    return out


def _template(values: dict, name: str) -> dict:
    title = need_text(values, "title", "Title", maxlen=256, required=False)
    description = need_text(values, "description", "Description", maxlen=4000, required=False)
    footer = need_text(values, "footer_text", "Footer", maxlen=2048, required=False)
    author = need_text(values, "author_text", "Author", maxlen=256, required=False)
    fields = _fields(values)
    image = _url(values, "image_url", "Image URL")
    thumbnail = _url(values, "thumbnail_url", "Thumbnail URL")
    if not (title or description or author or footer or image or thumbnail or fields):
        raise ValueError("Add at least a title, description, field or image.")
    return {
        "name": name, "title": title or None, "title_url": _url(values, "title_url", "Title URL"),
        "description": description or None, "color": _color(values), "author_text": author or None,
        "author_icon": _url(values, "author_icon", "Author icon URL"), "author_url": _url(values, "author_url", "Author URL"),
        "footer_text": footer or None, "footer_icon": _url(values, "footer_icon", "Footer icon URL"),
        "image_url": image, "thumbnail_url": thumbnail, "use_timestamp": int(need_bool(values, "timestamp")),
        "fields": fields,
    }


def _form(include_name: bool) -> list:
    out = []
    if include_name:
        out.append(fld("name", "Name", "text", maxlen=50, help="Used as {embed:name} in messages and greetings. Letters, numbers, - and _ only."))
    out.extend([
        fld("title", "Title", "text", maxlen=256),
        fld("title_url", "Title link", "text", maxlen=500, placeholder="https://"),
        fld("description", "Description", "textarea", maxlen=4000, help="Supports the same placeholders as the embed command."),
        fld("color", "Color", "text", maxlen=7, placeholder="#5865F2"),
        fld("author_text", "Author name", "text", maxlen=256),
        fld("author_icon", "Author icon URL", "text", maxlen=500),
        fld("author_url", "Author link", "text", maxlen=500),
        fld("footer_text", "Footer text", "text", maxlen=2048),
        fld("footer_icon", "Footer icon URL", "text", maxlen=500),
        fld("image_url", "Image URL", "text", maxlen=500),
        fld("thumbnail_url", "Thumbnail URL", "text", maxlen=500),
        fld("timestamp", "Show timestamp", "bool"),
        fld("fields", "Fields", "lines", help="One per line as: name | value | inline. Add inline at the end to place it beside others. Up to 25.", maxlen=1400),
    ])
    return out


async def _existing(ctx: ActionContext, payload: dict) -> dict:
    found = await embed_templates.get_template(ctx.guild.id, str(payload.get("id") or ""))
    if found is None:
        raise ValueError("That embed no longer exists.")
    return found


async def _write(ctx: ActionContext, template: dict) -> None:
    from cogs.embeds import _persist_template
    await _persist_template(ctx.guild.id, ctx.user_id, template)
    await embed_templates.clear_fields(ctx.guild.id, template["name"])
    for name, value, inline in template["fields"]:
        await embed_templates.add_field(ctx.guild.id, template["name"], name, value, inline)


def _line(f: dict) -> str:
    return f"{f['field_name']} | {f['field_value']}" + (" | inline" if f["inline"] else "")


@section("embeds")
async def embeds_section(guild: discord.Guild) -> dict:
    found = await embed_templates.list_templates(guild.id)
    cap = await embed_templates.get_template_cap(guild.id)
    rows = []
    for t in found:
        fields = await embed_templates.get_fields(guild.id, t["name"])
        values = {
            "title": t["title"] or "", "title_url": t["title_url"] or "", "description": t["description"] or "",
            "color": t["color"] or "", "author_text": t["author_text"] or "", "author_icon": t["author_icon"] or "",
            "author_url": t["author_url"] or "", "footer_text": t["footer_text"] or "", "footer_icon": t["footer_icon"] or "",
            "image_url": t["image_url"] or "", "thumbnail_url": t["thumbnail_url"] or "",
            "timestamp": bool(t["use_timestamp"]), "fields": [_line(f) for f in fields],
        }
        rows.append(row(
            t["name"],
            [t["name"], (t["title"] or t["description"] or "")[:60], len(fields), "{embed:" + t["name"] + "}"],
            [
                button("embed_edit", "Edit", _form(False), title=f"Edit {t['name']}", prefill=True, submit="Save"),
                button("embed_send", "Send", [
                    fld("channel", "Channel", "channel", help="Posts the embed here. Placeholders are filled in for you."),
                ], title=f"Send {t['name']}", submit="Send"),
                button("embed_duplicate", "Copy", [fld("new_name", "New name", "text", maxlen=50)], title=f"Copy {t['name']}", submit="Copy"),
                button("embed_rename", "Rename", [fld("new_name", "New name", "text", value=t["name"], maxlen=50)], title=f"Rename {t['name']}", submit="Rename"),
                button("embed_delete", "Delete", style="danger", confirm=f"Delete the embed {t['name']}? Messages using {{embed:{t['name']}}} will stop showing it."),
            ],
            values,
        ))
    return table(
        "templates", f"Embeds ({len(found)}/{cap})", ["Name", "Preview", "Fields", "Use it as"], rows,
        "No embeds yet. Create one to reuse it in greetings, custom commands and panels.",
        description="Reusable embed templates. Placeholders such as {user} and {server} are filled in when the embed is sent.",
        buttons=[button("embed_create", "Create embed", _form(True), style="primary", title="Create embed", submit="Create")],
    )


@action("embeds", "embed_create")
async def embed_create(ctx: ActionContext, payload: dict) -> list:
    values = payload.get("values") or {}
    name = _name(values)
    template = _template(values, name)
    if await embed_templates.get_template(ctx.guild.id, name):
        raise ValueError("An embed with that name already exists.")
    if await embed_templates.count_templates(ctx.guild.id) >= await embed_templates.get_template_cap(ctx.guild.id):
        raise ValueError("This server has reached its embed limit. Premium raises it.")
    now = time.time()
    await db.raw_execute(
        "INSERT INTO embed_templates (guild_id, name, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (ctx.guild.id, name, ctx.user_id, now, now),
    )
    await _write(ctx, template)
    return [f"Created embed {name}"]


@action("embeds", "embed_edit")
async def embed_edit(ctx: ActionContext, payload: dict) -> list:
    found = await _existing(ctx, payload)
    await _write(ctx, _template(payload.get("values") or {}, found["name"]))
    return [f"Updated embed {found['name']}"]


@action("embeds", "embed_delete")
async def embed_delete(ctx: ActionContext, payload: dict) -> list:
    found = await _existing(ctx, payload)
    await embed_templates.clear_fields(ctx.guild.id, found["name"])
    await db.raw_execute("DELETE FROM embed_templates WHERE guild_id=? AND name=?", (ctx.guild.id, found["name"]))
    await db.raw_execute("UPDATE guild_greeting_config SET embed_name=NULL WHERE guild_id=? AND embed_name=?", (ctx.guild.id, found["name"]))
    return [f"Deleted embed {found['name']}"]


@action("embeds", "embed_duplicate")
async def embed_duplicate(ctx: ActionContext, payload: dict) -> list:
    found = await _existing(ctx, payload)
    new_name = _name({"name": (payload.get("values") or {}).get("new_name")})
    if await embed_templates.get_template(ctx.guild.id, new_name):
        raise ValueError("An embed with that name already exists.")
    if await embed_templates.count_templates(ctx.guild.id) >= await embed_templates.get_template_cap(ctx.guild.id):
        raise ValueError("This server has reached its embed limit. Premium raises it.")
    from cogs.embeds import _persist_template
    await _persist_template(ctx.guild.id, ctx.user_id, dict(found) | {"name": new_name})
    for f in await embed_templates.get_fields(ctx.guild.id, found["name"]):
        await embed_templates.add_field(ctx.guild.id, new_name, f["field_name"], f["field_value"], bool(f["inline"]))
    return [f"Copied embed {found['name']} to {new_name}"]


@action("embeds", "embed_rename")
async def embed_rename(ctx: ActionContext, payload: dict) -> list:
    found = await _existing(ctx, payload)
    new_name = _name({"name": (payload.get("values") or {}).get("new_name")})
    if new_name == found["name"]:
        raise ValueError("That is already its name.")
    if await embed_templates.get_template(ctx.guild.id, new_name):
        raise ValueError("An embed with that name already exists.")
    await db.raw_execute("UPDATE embed_templates SET name=? WHERE guild_id=? AND name=?", (new_name, ctx.guild.id, found["name"]))
    await db.raw_execute("UPDATE embed_template_fields SET embed_name=? WHERE guild_id=? AND embed_name=?", (new_name, ctx.guild.id, found["name"]))
    await db.raw_execute("UPDATE guild_greeting_config SET embed_name=? WHERE guild_id=? AND embed_name=?", (new_name, ctx.guild.id, found["name"]))
    return [f"Renamed embed {found['name']} to {new_name}"]


@action("embeds", "embed_send")
async def embed_send(ctx: ActionContext, payload: dict) -> list:
    found = await _existing(ctx, payload)
    channel = need_channel(ctx.guild, payload.get("values") or {}, "channel", "Channel")
    perms = channel.permissions_for(ctx.guild.me)
    if not (perms.send_messages and perms.embed_links):
        raise ValueError(f"I need Send Messages and Embed Links in #{channel.name}.")
    member = ctx.guild.get_member(ctx.user_id) or ctx.guild.me
    var_map = message_vars.build_base_variables(member, ctx.guild, channel)
    fields = await embed_templates.get_fields(ctx.guild.id, found["name"])
    try:
        await channel.send(embed=embed_templates.build_discord_embed(found, var_map, fields), allowed_mentions=NO_MENTIONS)
    except discord.HTTPException:
        raise ValueError("Discord rejected the embed. Check that image and link URLs are valid.")
    return [f"Sent embed {found['name']} to #{channel.name}"]
