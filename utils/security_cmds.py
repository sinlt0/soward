import json
from typing import Optional

import discord
from discord.ext import commands

from utils import automod_filters as filters
from utils import emoji_manager, guild_settings
from utils import security_settings as settings
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import LOG_EVENT, bus
from utils.security_access import LEVEL_OWNER, level_of

CHUNK = 3300
LIST_KINDS = ("words", "domains", "roles", "channels")


async def _fail(ctx: commands.Context, title: str, body: str):
    e = emoji_manager.get
    await ctx.send(view=error_layout(f"{e('cross')} {title}", body))


def _resolve(module: str, key: str) -> Optional[settings.Setting]:
    return settings.find(module, key.replace("-", "_"))


async def _announce(ctx: commands.Context, setting: settings.Setting, old, new):
    await bus.publish(
        LOG_EVENT, guild_id=ctx.guild.id, action="security_change", actor_id=ctx.author.id,
        detail=f"**{setting.module}.{setting.key}**: {settings.display(setting, old)} → {settings.display(setting, new)}",
    )


async def _chunked(ctx: commands.Context, title: str, lines: list[str]):
    pages, current, size = [], [], 0
    for line in lines:
        if size + len(line) + 1 > CHUNK and current:
            pages.append(current)
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        pages.append(current)
    for index, page in enumerate(pages):
        suffix = f" ({index + 1}/{len(pages)})" if len(pages) > 1 else ""
        await ctx.send(view=info_layout(f"{title}{suffix}", "\n".join(page)))


async def show_settings(ctx: commands.Context, module: str, group: Optional[str] = None):
    e = emoji_manager.get
    entries = settings.module_settings(module)
    groups: dict[str, list[settings.Setting]] = {}
    for entry in entries:
        groups.setdefault(entry.group, []).append(entry)
    title = f"{e('shield')} {settings.MODULE_TITLES[module]} settings"
    if group is None:
        lines = [f"**{name}** — {len(items)} setting(s) · `settings {name.lower()}`" for name, items in groups.items()]
        lines.append("\nUse `settings all` to list everything, `get <key>` for one value and `set <key> <value>` to change it.")
        return await ctx.send(view=info_layout(title, "\n".join(lines)))
    wanted = group.lower()
    selected = [i for name, items in groups.items() if wanted in ("all", name.lower()) for i in items]
    if not selected:
        return await _fail(ctx, "Unknown group", f"Groups: {', '.join(f'`{n.lower()}`' for n in groups)}, or `all`.")
    lines = []
    for item in selected:
        value = await guild_settings.get(ctx.guild.id, item.store, item.default)
        marker = "" if value == item.default else " ✎"
        lines.append(f"`{item.key}` — {item.label}: **{settings.display(item, value)}**{marker}")
    await _chunked(ctx, title, lines)


async def get_setting(ctx: commands.Context, module: str, key: str):
    e = emoji_manager.get
    setting = _resolve(module, key)
    if setting is None:
        return await _fail(ctx, "Unknown setting", f"No setting named `{key}`. Run `settings` to list them.")
    value = await guild_settings.get(ctx.guild.id, setting.store, setting.default)
    body = f"**Current:** {settings.display(setting, value)}\n**Default:** {settings.display(setting, setting.default)}"
    if setting.help:
        body += f"\n\n{setting.help}"
    if setting.kind == "choice":
        body += f"\n**Choices:** {', '.join(f'`{c}`' for c in setting.choices)}"
    await ctx.send(view=info_layout(f"{e('shield')} {setting.label}", body))


async def _parse(ctx: commands.Context, setting: settings.Setting, raw: str):
    if setting.kind == "role":
        if raw.strip().lower() in ("off", "none", "clear", "reset"):
            return None
        return (await commands.RoleConverter().convert(ctx, raw)).id
    if setting.kind == "channel":
        if raw.strip().lower() in ("off", "none", "clear", "reset"):
            return None
        return (await commands.GuildChannelConverter().convert(ctx, raw)).id
    return settings.parse_scalar(setting, raw)


async def set_setting(ctx: commands.Context, module: str, key: str, raw: str):
    e = emoji_manager.get
    setting = _resolve(module, key)
    if setting is None:
        return await _fail(ctx, "Unknown setting", f"No setting named `{key}`. Run `settings` to list them.")
    if setting.kind in LIST_KINDS:
        return await _fail(ctx, "List setting", f"`{setting.key}` is a list. Use `add {setting.key} <value>` and `remove {setting.key} <value>`.")
    if setting.critical and await level_of(ctx.guild, ctx.author) < LEVEL_OWNER:
        return await _fail(ctx, "Owner only", "Only the server owner or an Extra Owner can change this setting.")
    try:
        value = await _parse(ctx, setting, raw)
    except commands.BadArgument:
        return await _fail(ctx, "Invalid value", f"Could not understand `{raw}` for {setting.label}.")
    except ValueError as exc:
        return await _fail(ctx, "Invalid value", str(exc))
    old = await guild_settings.get(ctx.guild.id, setting.store, setting.default)
    await settings.put(ctx.guild.id, setting, value)
    await _announce(ctx, setting, old, value)
    await ctx.send(view=success_layout(
        f"{e('check')} {setting.label}", f"{settings.display(setting, old)} → **{settings.display(setting, value)}**",
    ))


async def reset_setting(ctx: commands.Context, module: str, key: str):
    e = emoji_manager.get
    if await level_of(ctx.guild, ctx.author) < LEVEL_OWNER:
        return await _fail(ctx, "Owner only", "Only the server owner or an Extra Owner can reset settings.")
    if key.lower() == "all":
        count = 0
        for setting in settings.module_settings(module):
            if await guild_settings.get(ctx.guild.id, setting.store, setting.default) != setting.default:
                await settings.reset(ctx.guild.id, setting)
                count += 1
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_change", actor_id=ctx.author.id, detail=f"Reset {count} {module} setting(s) to defaults.")
        return await ctx.send(view=success_layout(f"{e('check')} Settings reset", f"{count} {settings.MODULE_TITLES[module]} setting(s) returned to their defaults."))
    setting = _resolve(module, key)
    if setting is None:
        return await _fail(ctx, "Unknown setting", f"No setting named `{key}`.")
    old = await guild_settings.get(ctx.guild.id, setting.store, setting.default)
    await settings.reset(ctx.guild.id, setting)
    await _announce(ctx, setting, old, setting.default)
    await ctx.send(view=success_layout(f"{e('check')} Setting reset", f"{setting.label} is back to **{settings.display(setting, setting.default)}**."))


async def _list_value(ctx: commands.Context, setting: settings.Setting, raw: str):
    if setting.kind == "roles":
        return (await commands.RoleConverter().convert(ctx, raw)).id
    if setting.kind == "channels":
        return (await commands.GuildChannelConverter().convert(ctx, raw)).id
    if setting.kind == "domains":
        cleaned = filters.clean_domain(raw)
        if "." not in cleaned or len(cleaned) > 100:
            raise ValueError("Give a domain such as `example.com`.")
        return cleaned
    text = raw.strip().lower()
    if not 2 <= len(text) <= 100:
        raise ValueError("Entries must be 2-100 characters.")
    return text


async def list_edit(ctx: commands.Context, module: str, key: str, raw: str, add: bool):
    e = emoji_manager.get
    setting = _resolve(module, key)
    if setting is None:
        return await _fail(ctx, "Unknown setting", f"No setting named `{key}`.")
    if setting.kind not in LIST_KINDS:
        return await _fail(ctx, "Not a list", f"`{setting.key}` is not a list. Use `set {setting.key} <value>`.")
    try:
        value = await _list_value(ctx, setting, raw)
    except commands.BadArgument:
        return await _fail(ctx, "Invalid value", f"Could not understand `{raw}`.")
    except ValueError as exc:
        return await _fail(ctx, "Invalid value", str(exc))
    current = list(await guild_settings.get(ctx.guild.id, setting.store, setting.default))
    if add:
        if value in current:
            return await _fail(ctx, "Already there", "That entry is already in the list.")
        if len(current) >= int(setting.hi or 100):
            return await _fail(ctx, "List full", f"This list can hold up to {int(setting.hi or 100)} entries.")
        current.append(value)
    else:
        if value not in current:
            return await _fail(ctx, "Not found", "That entry is not in the list.")
        current.remove(value)
    await settings.put(ctx.guild.id, setting, current)
    await bus.publish(
        LOG_EVENT, guild_id=ctx.guild.id, action="security_change", actor_id=ctx.author.id,
        detail=f"**{setting.module}.{setting.key}** {'added' if add else 'removed'} `{value}`",
    )
    await ctx.send(view=success_layout(f"{e('check')} {setting.label}", f"{'Added to' if add else 'Removed from'} the list. It now has **{len(current)}** entr{'y' if len(current) == 1 else 'ies'}."))


async def show_list(ctx: commands.Context, module: str, key: str):
    e = emoji_manager.get
    setting = _resolve(module, key)
    if setting is None or setting.kind not in LIST_KINDS:
        return await _fail(ctx, "Unknown list", f"`{key}` is not a list setting.")
    current = await guild_settings.get(ctx.guild.id, setting.store, setting.default)
    if setting.kind == "roles":
        lines = [f"<@&{v}>" for v in current]
    elif setting.kind == "channels":
        lines = [f"<#{v}>" for v in current]
    else:
        lines = [f"`{v}`" for v in current]
    await _chunked(ctx, f"{e('shield')} {setting.label}", lines or ["Nothing in this list yet."])


async def apply_preset(ctx: commands.Context, name: str):
    e = emoji_manager.get
    name = name.lower()
    if name not in settings.PRESETS:
        return await _fail(ctx, "Unknown preset", f"Choose from: {', '.join(f'`{n}`' for n in settings.PRESETS)}")
    changed = await settings.apply_preset(ctx.guild.id, name)
    await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_change", actor_id=ctx.author.id, detail=f"Applied the **{name}** preset ({len(changed)} change(s)).")
    body = "\n".join(changed[:25]) or "Everything already matched this preset."
    if len(changed) > 25:
        body += f"\n…and {len(changed) - 25} more."
    await ctx.send(view=success_layout(f"{e('check')} {name.title()} preset applied", body))


async def export_settings(ctx: commands.Context):
    import io
    payload = await settings.export_json(ctx.guild.id)
    await ctx.send(file=discord.File(io.BytesIO(payload.encode()), filename=f"soward-security-{ctx.guild.id}.json"))


async def import_settings(ctx: commands.Context):
    e = emoji_manager.get
    if not ctx.message.attachments:
        return await _fail(ctx, "Attach a file", "Attach a security export `.json` to the command message.")
    attachment = ctx.message.attachments[0]
    if attachment.size > 200_000:
        return await _fail(ctx, "File too large", "Security exports are small. This file is too large.")
    try:
        payload = json.loads((await attachment.read()).decode())
        clean = settings.validate_import(payload)
    except (ValueError, UnicodeDecodeError, TypeError) as exc:
        return await _fail(ctx, "Invalid file", str(exc))
    for path, value in clean.items():
        await settings.put(ctx.guild.id, settings._REGISTRY[path], value)
    await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_change", actor_id=ctx.author.id, detail=f"Imported {len(clean)} setting(s) from a file.")
    await ctx.send(view=success_layout(f"{e('check')} Settings imported", f"{len(clean)} setting(s) were applied."))

chunked = _chunked
