import asyncio
import json
import secrets
import time
import uuid
from typing import Any, Optional

import discord

import config
from utils import db, embed_templates, guild_settings
from utils import nsfw as nsfw_util
from utils import security
from utils import security_settings as sec_settings
from utils import tickets as tickets_util

SNOWFLAKE_MIN = 10 ** 16
MAX_ROLES = 150
MAX_CHANNELS = 200
MAX_BYTES = 1_500_000
DROP = object()
PARTS = ("roles", "channels", "settings", "content")
CHANNEL_KINDS = ("text", "announcement", "voice", "stage", "forum")
SKIP_SETTING_PREFIXES = ("premium", "support_", "dashboard_", "automod_native_rules")
SKIP_SETTING_SUFFIXES = ("_message_id", "_webhook_url", "_webhook")
FOREIGN_SKIP_SETTINGS = {"security_lock", "antinuke_admin_bypass"}
TRIGGER_TYPES = tuple(config.GREETING_TRIGGER_TYPES)

TABLE_SPECS: dict[str, dict] = {
    "guild_leveling_config": {
        "cols": ["enabled", "xp_min", "xp_max", "text_cooldown_seconds", "voice_xp_per_minute", "voice_enabled",
                 "voice_require_unmuted", "voice_require_others", "role_stack_mode", "announce_mode", "announce_channel_id",
                 "announce_message", "weekly_reset_enabled", "monthly_reset_enabled", "top_role_id", "prestige_level_cap"],
        "opt": ["announce_channel_id", "top_role_id"], "key": ["guild_id"], "mode": "upsert",
    },
    "level_role_rewards": {"cols": ["level", "role_id"], "req": ["role_id"], "mode": "ignore"},
    "xp_multipliers": {
        "cols": ["scope_type", "scope_id", "multiplier", "label"], "req": ["scope_id"], "mode": "dedupe",
        "dedupe": ["scope_type", "scope_id"], "id_col": "multiplier_id",
    },
    "xp_no_xp_channels": {"cols": ["channel_id"], "req": ["channel_id"], "mode": "ignore"},
    "xp_no_xp_roles": {"cols": ["role_id"], "req": ["role_id"], "mode": "ignore"},
    "log_disabled_events": {"cols": ["event"], "mode": "ignore"},
    "antinuke_action_punishments": {"cols": ["action_type", "punishment"], "key": ["guild_id", "action_type"], "mode": "upsert"},
    "security_whitelist": {"cols": ["target_id", "target_type", "scope"], "req": ["target_id"], "mode": "ignore", "extra": {"added_by": None}},
    "ticket_settings": {"cols": ["log_channel_id", "max_open", "auto_close_hours"], "opt": ["log_channel_id"], "key": ["guild_id"], "mode": "upsert"},
    "jtc_hubs": {
        "cols": ["channel_id", "category_id", "name_template", "user_limit", "bitrate"], "req": ["channel_id"], "opt": ["category_id"],
        "key": ["channel_id"], "mode": "upsert", "extra": {"created_by": None, "created_at": 0},
    },
    "booster_config": {
        "cols": ["enabled", "tier_mode", "stack_mode", "base_role_id", "grace_hours", "custom_enabled", "custom_min", "allow_name", "allow_color",
                 "allow_icon", "allow_hoist", "allow_perms", "position_mode", "position_ref_id", "cooldown_hours", "name_filter", "max_name_len",
                 "remove_on_unboost", "restore_on_reboost"],
        "opt": ["base_role_id", "position_ref_id"], "key": ["guild_id"], "mode": "upsert",
    },
    "booster_tiers": {"cols": ["boosts", "role_id"], "req": ["role_id"], "key": ["guild_id", "boosts"], "mode": "upsert"},
    "guild_anime_daily_config": {
        "cols": ["enabled", "channel_id", "media_type", "genre_filter", "post_hour_utc", "post_minute_utc", "role_id", "nsfw"],
        "opt": ["channel_id", "role_id"], "key": ["guild_id"], "mode": "upsert",
    },
}

GREETING_COLS = ["trigger_type", "enabled", "channel_id", "message_text", "embed_name", "send_as_dm", "dm_fallback_to_channel",
                 "use_card", "card_layout", "card_background_url", "card_accent_color", "join_role_delay_seconds", "delete_after_seconds"]


def new_code() -> str:
    return secrets.token_hex(4).upper()


def is_code(value: str) -> bool:
    value = value.strip()
    return len(value) == 8 and all(c in "0123456789abcdefABCDEF" for c in value)


def _perm_names(perms: discord.Permissions) -> list[str]:
    return [name for name, value in perms if value]


def _valid_perm_names(names) -> list[str]:
    valid = discord.Permissions.VALID_FLAGS
    return [n for n in names if n in valid]


def _tok(kind: str, key: str) -> dict:
    return {f"${kind}": key}


def _overwrites_out(channel, role_keys: dict[int, str], default_role: discord.Role) -> dict:
    out = {}
    for target, overwrite in channel.overwrites.items():
        if target == default_role:
            key = "everyone"
        elif isinstance(target, discord.Role) and target.id in role_keys:
            key = role_keys[target.id]
        else:
            continue
        allow, deny = overwrite.pair()
        entry = {"allow": _perm_names(allow), "deny": _perm_names(deny)}
        if entry["allow"] or entry["deny"]:
            out[key] = entry
    return out


def _tokenise(value: Any, role_keys: dict[int, str], channel_keys: dict[int, str]) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in role_keys:
            return _tok("role", role_keys[value])
        if value in channel_keys:
            return _tok("channel", channel_keys[value])
        return value
    if isinstance(value, str) and value.isdigit() and len(value) >= 17:
        number = int(value)
        if number in role_keys:
            return _tok("role", role_keys[number])
        if number in channel_keys:
            return _tok("channel", channel_keys[number])
        return value
    if isinstance(value, list):
        return [_tokenise(v, role_keys, channel_keys) for v in value]
    if isinstance(value, dict):
        return {k: _tokenise(v, role_keys, channel_keys) for k, v in value.items()}
    return value


def _resolve(value: Any, rmap: dict, cmap: dict) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        if "$role" in value:
            return rmap.get(value["$role"], DROP)
        if "$channel" in value:
            return cmap.get(value["$channel"], DROP)
        out = {}
        for k, v in value.items():
            resolved = _resolve(v, rmap, cmap)
            if resolved is not DROP:
                out[k] = resolved
        return out
    if isinstance(value, list):
        return [r for r in (_resolve(v, rmap, cmap) for v in value) if r is not DROP]
    if isinstance(value, int) and value >= SNOWFLAKE_MIN:
        return DROP
    if isinstance(value, str) and value.isdigit() and len(value) >= 17:
        return DROP
    return value


def _setting_allowed(key: str, foreign: bool) -> bool:
    if key.startswith(SKIP_SETTING_PREFIXES) or key.endswith(SKIP_SETTING_SUFFIXES):
        return False
    if foreign and key in FOREIGN_SKIP_SETTINGS:
        return False
    return True


async def snapshot(guild: discord.Guild) -> dict:
    roles = [r for r in sorted(guild.roles, key=lambda r: -r.position) if not r.is_default() and not r.managed][:MAX_ROLES]
    role_keys = {r.id: f"r{i + 1}" for i, r in enumerate(roles)}
    channel_keys: dict[int, str] = {}
    counter = 0

    def kind_of(ch) -> Optional[str]:
        if isinstance(ch, discord.TextChannel):
            return "announcement" if ch.is_news() else "text"
        if isinstance(ch, discord.VoiceChannel):
            return "voice"
        if isinstance(ch, discord.StageChannel):
            return "stage"
        if isinstance(ch, discord.ForumChannel):
            return "forum"
        return None

    def describe(ch, category_overwrites: bool) -> Optional[dict]:
        nonlocal counter
        kind = kind_of(ch)
        if kind is None or counter >= MAX_CHANNELS:
            return None
        counter += 1
        key = f"c{counter}"
        channel_keys[ch.id] = key
        entry = {"key": key, "name": ch.name, "type": kind}
        topic = getattr(ch, "topic", None)
        if topic:
            entry["topic"] = topic[:1024]
        slow = getattr(ch, "slowmode_delay", 0)
        if slow:
            entry["slowmode"] = slow
        limit = getattr(ch, "user_limit", 0)
        if limit:
            entry["user_limit"] = limit
        if category_overwrites and ch.permissions_synced:
            entry["overwrites"] = None
        else:
            entry["overwrites"] = _overwrites_out(ch, role_keys, guild.default_role)
            entry["merge"] = False
        return entry

    categories = []
    loose = [c for c in guild.channels if not isinstance(c, (discord.CategoryChannel, discord.Thread)) and c.category is None]
    if loose:
        entries = [d for d in (describe(c, False) for c in sorted(loose, key=lambda c: c.position)) if d]
        if entries:
            categories.append({"key": None, "name": None, "overwrites": {}, "channels": entries})
    for category in sorted(guild.categories, key=lambda c: c.position):
        ckey = f"g{len(categories) + 1}"
        channel_keys[category.id] = ckey
        entries = [d for d in (describe(c, True) for c in category.channels) if d]
        categories.append({
            "key": ckey, "name": category.name,
            "overwrites": _overwrites_out(category, role_keys, guild.default_role),
            "channels": entries,
        })

    role_specs = []
    for r in roles:
        role_specs.append({
            "key": role_keys[r.id], "name": r.name, "color": r.colour.value, "perms": r.permissions.value,
            "hoist": r.hoist, "mentionable": r.mentionable,
        })

    settings = {}
    for key, value in (await guild_settings.get_all(guild.id)).items():
        if _setting_allowed(key, False):
            settings[key] = _tokenise(value, role_keys, channel_keys)

    tables: dict[str, list] = {}
    for table, spec in TABLE_SPECS.items():
        rows = await db.raw_fetch(f"SELECT * FROM {table} WHERE guild_id=?", (guild.id,))
        out = []
        for row in rows:
            row = dict(row)
            item = {col: row.get(col) for col in spec["cols"]}
            ok = True
            for col in spec.get("req", []) + spec.get("opt", []):
                if item.get(col) is None:
                    continue
                tokenised = _tokenise(item[col], role_keys, channel_keys)
                if isinstance(tokenised, int) and tokenised >= SNOWFLAKE_MIN:
                    if col in spec.get("req", []):
                        ok = False
                    tokenised = None
                item[col] = tokenised
            if table == "security_whitelist" and item.get("target_type") == "user":
                ok = False
            if table == "xp_multipliers" and item.get("scope_type") not in ("role", "channel"):
                item["scope_id"] = None
                ok = True
            if ok:
                out.append(item)
        if out:
            tables[table] = out

    greetings = []
    for row in await db.raw_fetch("SELECT * FROM guild_greeting_config WHERE guild_id=?", (guild.id,)):
        row = dict(row)
        item = {col: row.get(col) for col in GREETING_COLS}
        item["channel_id"] = _tokenise(item["channel_id"], role_keys, channel_keys) if item["channel_id"] else None
        if isinstance(item["channel_id"], int):
            item["channel_id"] = None
        greetings.append(item)

    logs = {}
    for row in await db.raw_fetch("SELECT category, channel_id FROM log_channels WHERE guild_id=?", (guild.id,)):
        if row["channel_id"] in channel_keys:
            logs[row["category"]] = _tok("channel", channel_keys[row["channel_id"]])

    nsfw = None
    nsfw_role = await nsfw_util.get_role_id(guild.id)
    if nsfw_role in role_keys:
        nsfw = {
            "role": _tok("role", role_keys[nsfw_role]),
            "channels": [_tok("channel", channel_keys[c]) for c in await nsfw_util.get_channel_ids(guild.id) if c in channel_keys],
        }

    embeds = []
    for template in await embed_templates.list_templates(guild.id):
        fields = await embed_templates.get_fields(guild.id, template["name"])
        embeds.append({
            "name": template["name"],
            **{k: template.get(k) for k in ("title", "title_url", "description", "color", "author_text", "author_icon", "author_url",
                                            "footer_text", "footer_icon", "image_url", "thumbnail_url", "use_timestamp")},
            "fields": [{"name": f["field_name"], "value": f["field_value"], "inline": bool(f["inline"])} for f in fields],
        })

    panels = []
    for panel in await db.raw_fetch("SELECT * FROM reaction_role_panels WHERE guild_id=? AND message_id IS NOT NULL", (guild.id,)):
        panel = dict(panel)
        if panel["channel_id"] not in channel_keys:
            continue
        bindings = await db.raw_fetch("SELECT * FROM reaction_role_bindings WHERE panel_id=?", (panel["panel_id"],))
        roles_out = [
            {"emoji": b["emoji"], "role": _tok("role", role_keys[b["role_id"]]), "label": b["label"]}
            for b in bindings if b["role_id"] in role_keys
        ]
        if roles_out:
            panels.append({
                "channel": _tok("channel", channel_keys[panel["channel_id"]]), "embed": panel["embed_name"],
                "type": panel["panel_type"], "mode": panel["mode"], "max_roles": panel["max_roles"] or 0, "roles": roles_out,
            })

    ticket_specs = []
    for panel in await db.raw_fetch("SELECT * FROM ticket_panels WHERE guild_id=? AND message_id IS NOT NULL", (guild.id,)):
        panel = dict(panel)
        if panel["channel_id"] not in channel_keys:
            continue
        staff = [role_keys[r] for r in tickets_util.parse_ids(panel["staff_role_ids"]) if r in role_keys]
        if not staff:
            continue
        ticket_specs.append({
            "channel": channel_keys[panel["channel_id"]], "name": panel["name"], "staff": staff,
            "category": channel_keys.get(panel["category_id"]), "transcript": channel_keys.get(panel["transcript_channel_id"]),
            "welcome": panel["welcome_text"], "button": panel["button_label"], "questions": tickets_util.parse_list(panel["questions"]),
            "one_per_user": panel["one_per_user"], "ask_subject": panel["ask_subject"],
        })

    prefix_row = await db.raw_fetchone("SELECT prefix FROM guilds WHERE guild_id=?", (guild.id,))

    data = {
        "version": 1,
        "roles": role_specs,
        "categories": categories,
        "settings": settings,
        "tables": tables,
        "greetings": greetings,
        "logs": logs,
        "nsfw": nsfw,
        "embeds": embeds,
        "panels": panels,
        "tickets": ticket_specs,
        "prefix": prefix_row["prefix"] if prefix_row else None,
    }
    if len(json.dumps(data)) > MAX_BYTES:
        raise ValueError("This server is too large to save as a template. Remove unused channels or roles and try again.")
    return data


def validate(data: Any) -> dict:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise ValueError("This template uses a format Soward does not understand.")
    roles = data.get("roles") or []
    categories = data.get("categories") or []
    if not isinstance(roles, list) or not isinstance(categories, list):
        raise ValueError("This template is damaged.")
    if len(roles) > MAX_ROLES:
        raise ValueError("This template has too many roles.")
    total = 0
    for cat in categories:
        if not isinstance(cat, dict) or not isinstance(cat.get("channels", []), list):
            raise ValueError("This template is damaged.")
        total += len(cat.get("channels", [])) + (1 if cat.get("name") else 0)
    if total > MAX_CHANNELS + 50:
        raise ValueError("This template has too many channels.")
    for spec in roles:
        if not isinstance(spec, dict) or not isinstance(spec.get("name"), str) or not spec.get("key"):
            raise ValueError("This template is damaged.")
    for cat in categories:
        for ch in cat.get("channels", []):
            if not isinstance(ch, dict) or ch.get("type") not in CHANNEL_KINDS or not isinstance(ch.get("name"), str) or not ch.get("key"):
                raise ValueError("This template is damaged.")
    return data


def summary_counts(data: dict) -> dict:
    channels = sum(len(c.get("channels", [])) for c in data.get("categories", []))
    return {
        "roles": len(data.get("roles", [])),
        "categories": len([c for c in data.get("categories", []) if c.get("name")]),
        "channels": channels,
        "settings": len(data.get("settings", {})) + sum(len(v) for v in data.get("tables", {}).values()) + len(data.get("greetings", [])),
        "embeds": len(data.get("embeds", [])),
        "panels": len(data.get("panels", [])) + len(data.get("tickets", [])),
        "messages": len(data.get("messages", [])),
    }


def _merge_overwrites(base: dict, extra: dict) -> dict:
    out = {}
    for key in set(base) | set(extra):
        b = base.get(key, {"allow": [], "deny": []})
        x = extra.get(key, {"allow": [], "deny": []})
        allow = (set(b.get("allow", [])) | set(x.get("allow", []))) - set(x.get("deny", []))
        deny = (set(b.get("deny", [])) - set(x.get("allow", []))) | set(x.get("deny", []))
        out[key] = {"allow": sorted(allow), "deny": sorted(deny)}
    return out


def _build_overwrites(guild: discord.Guild, spec: dict, rmap: dict) -> dict:
    out = {}
    for key, entry in (spec or {}).items():
        if key == "everyone":
            target = guild.default_role
        else:
            role_id = rmap.get(key)
            target = guild.get_role(role_id) if role_id else None
        if target is None:
            continue
        allow = _valid_perm_names(entry.get("allow", []))
        deny = _valid_perm_names(entry.get("deny", []))
        overwrite = discord.PermissionOverwrite()
        for name in allow:
            setattr(overwrite, name, True)
        for name in deny:
            setattr(overwrite, name, False)
        out[target] = overwrite
    return out


class Report:
    def __init__(self):
        self.lines: list[str] = []
        self.failed: list[str] = []
        self.rmap: dict[str, int] = {}
        self.cmap: dict[str, int] = {}
        self.counts = {"kicked_bots": 0, "deleted_channels": 0, "deleted_roles": 0, "roles": 0, "roles_reused": 0, "channels": 0, "channels_reused": 0, "settings": 0, "embeds": 0, "panels": 0, "messages": 0}

    def ok(self, line: str):
        self.lines.append(line)

    def fail(self, line: str):
        self.failed.append(line)

    def merge(self, other: "Report"):
        for key, value in other.counts.items():
            self.counts[key] = self.counts.get(key, 0) + value
        self.lines = other.lines + self.lines
        self.failed = other.failed + self.failed


async def _apply_roles(guild: discord.Guild, specs: list, foreign: bool, rmap: dict, report: Report):
    me = guild.me
    existing = {r.name.lower(): r for r in guild.roles if not r.is_default() and not r.managed}
    created: list[discord.Role] = []
    for spec in specs:
        found = existing.get(spec["name"].lower())
        if found is not None:
            rmap[spec["key"]] = found.id
            report.counts["roles_reused"] += 1
            continue
        if len(guild.roles) + len(created) >= 245:
            report.fail(f"Role limit reached, skipped **{spec['name']}**")
            continue
        raw = spec.get("perms", 0)
        perms = discord.Permissions(raw) if isinstance(raw, int) else discord.Permissions(**{n: True for n in _valid_perm_names(raw)})
        if foreign:
            for name in security.dangerous_permissions(perms):
                setattr(perms, name, False)
        if not me.guild_permissions.administrator:
            perms = discord.Permissions(perms.value & me.guild_permissions.value)
        try:
            role = await guild.create_role(
                name=spec["name"][:100], colour=discord.Colour(int(spec.get("color", 0) or 0)), hoist=bool(spec.get("hoist")),
                mentionable=bool(spec.get("mentionable")), permissions=perms, reason="Soward server template",
            )
        except discord.HTTPException as exc:
            report.fail(f"Role **{spec['name']}**: {str(exc)[:80]}")
            continue
        created.append(role)
        rmap[spec["key"]] = role.id
        report.counts["roles"] += 1
        await asyncio.sleep(0.3)
    if created:
        top = me.top_role.position
        base = max(1, top - len(created))
        order = {}
        for index, role in enumerate(reversed(created)):
            order[role] = min(top - 1, base + index) if top > 1 else 1
        try:
            await guild.edit_role_positions(positions=order, reason="Soward server template")
        except discord.HTTPException:
            report.fail("Roles were created but could not be moved into order. Drag them into place in Server Settings")


def _norm_name(name: str, kind: str) -> str:
    return name.lower().replace(" ", "-") if kind in ("text", "announcement", "forum") else name


async def _apply_channels(guild: discord.Guild, categories: list, rmap: dict, cmap: dict, report: Report):
    existing_categories = {c.name.lower(): c for c in guild.categories}
    for cat in categories:
        category = None
        cat_ow = cat.get("overwrites") or {}
        if cat.get("name"):
            category = existing_categories.get(cat["name"].lower())
            if category is None:
                try:
                    category = await guild.create_category(
                        cat["name"][:100], overwrites=_build_overwrites(guild, cat_ow, rmap), reason="Soward server template",
                    )
                    existing_categories[cat["name"].lower()] = category
                    await asyncio.sleep(0.3)
                except discord.HTTPException as exc:
                    report.fail(f"Category **{cat['name']}**: {str(exc)[:80]}")
                    continue
            if cat.get("key"):
                cmap[cat["key"]] = category.id
        for ch in cat.get("channels", []):
            kind = ch["type"]
            wanted = _norm_name(ch["name"], kind)
            match = None
            pool = category.channels if category is not None else [c for c in guild.channels if c.category is None]
            for candidate in pool:
                if candidate.name == wanted:
                    match = candidate
                    break
            if match is not None:
                cmap[ch["key"]] = match.id
                report.counts["channels_reused"] += 1
                continue
            if len(guild.channels) + report.counts["channels"] >= 495:
                report.fail(f"Channel limit reached, skipped **{ch['name']}**")
                continue
            own = ch.get("overwrites")
            if own is None:
                spec = cat_ow
            elif ch.get("merge", True):
                spec = _merge_overwrites(cat_ow, own)
            else:
                spec = own
            overwrites = _build_overwrites(guild, spec, rmap)
            topic = (ch.get("topic") or None)
            slow = int(ch.get("slowmode") or 0)
            reason = "Soward server template"
            created = None
            try:
                if kind in ("text", "announcement"):
                    try:
                        created = await guild.create_text_channel(
                            ch["name"][:100], category=category, topic=topic, slowmode_delay=slow, overwrites=overwrites,
                            news=(kind == "announcement"), reason=reason,
                        )
                    except discord.HTTPException:
                        if kind != "announcement":
                            raise
                        created = await guild.create_text_channel(
                            ch["name"][:100], category=category, topic=topic, slowmode_delay=slow, overwrites=overwrites, reason=reason,
                        )
                elif kind == "voice":
                    created = await guild.create_voice_channel(
                        ch["name"][:100], category=category, user_limit=int(ch.get("user_limit") or 0), overwrites=overwrites, reason=reason,
                    )
                elif kind == "stage":
                    try:
                        created = await guild.create_stage_channel(ch["name"][:100], category=category, overwrites=overwrites, reason=reason)
                    except discord.HTTPException:
                        created = await guild.create_voice_channel(ch["name"][:100], category=category, overwrites=overwrites, reason=reason)
                elif kind == "forum":
                    try:
                        created = await guild.create_forum(ch["name"][:100], category=category, topic=topic, overwrites=overwrites, reason=reason)
                    except discord.HTTPException:
                        created = await guild.create_text_channel(
                            ch["name"][:100], category=category, topic=topic, overwrites=overwrites, reason=reason,
                        )
            except discord.HTTPException as exc:
                report.fail(f"Channel **{ch['name']}**: {str(exc)[:80]}")
                continue
            cmap[ch["key"]] = created.id
            report.counts["channels"] += 1
            await asyncio.sleep(0.35)


async def _apply_settings(guild: discord.Guild, data: dict, foreign: bool, rmap: dict, cmap: dict, actor_id: int, report: Report):
    for key, value in (data.get("settings") or {}).items():
        if not _setting_allowed(key, foreign):
            continue
        resolved = _resolve(value, rmap, cmap)
        if resolved is DROP or (isinstance(value, list) and value and not resolved):
            continue
        await guild_settings.set(guild.id, key, resolved)
        report.counts["settings"] += 1

    prefix = data.get("prefix")
    if isinstance(prefix, str) and 0 < len(prefix) <= 5:
        await db.raw_execute(
            "INSERT INTO guilds (guild_id, prefix) VALUES (?, ?) ON CONFLICT(guild_id) DO UPDATE SET prefix=excluded.prefix",
            (guild.id, prefix),
        )

    for table, rows in (data.get("tables") or {}).items():
        spec = TABLE_SPECS.get(table)
        if spec is None or not isinstance(rows, list):
            continue
        for row in rows:
            values = {}
            skip = False
            for col in spec["cols"]:
                raw = row.get(col)
                if col in spec.get("req", []) or col in spec.get("opt", []):
                    if raw is None:
                        values[col] = None
                        continue
                    resolved = _resolve(raw, rmap, cmap)
                    if resolved is DROP:
                        if col in spec.get("req", []):
                            skip = True
                            break
                        resolved = None
                    values[col] = resolved
                elif col in row:
                    values[col] = raw
            if skip:
                continue
            if table == "xp_multipliers" and values.get("scope_type") not in ("role", "channel"):
                values["scope_id"] = None
            if table == "guild_anime_daily_config" and not values.get("channel_id"):
                values["enabled"] = 0
                values["nsfw"] = 0
            if table == "guild_leveling_config" and values.get("announce_mode") == "channel" and not values.get("announce_channel_id"):
                values["announce_mode"] = "off"
            await _write_row(guild.id, table, spec, values, actor_id)
            report.counts["settings"] += 1

    for item in data.get("greetings") or []:
        trigger = item.get("trigger_type")
        if trigger not in TRIGGER_TYPES:
            continue
        channel_id = _resolve(item.get("channel_id"), rmap, cmap) if item.get("channel_id") else None
        if channel_id is DROP:
            channel_id = None
        fields = {k: item.get(k) for k in GREETING_COLS if k != "trigger_type"}
        fields["channel_id"] = channel_id
        if channel_id is None and not fields.get("send_as_dm"):
            fields["enabled"] = 0
        from utils import greeting_config
        await greeting_config.set_config_fields(guild.id, trigger, **fields)
        report.counts["settings"] += 1


async def _write_row(guild_id: int, table: str, spec: dict, values: dict, actor_id: int):
    cols = list(values.keys())
    params = [values[c] for c in cols]
    names = ["guild_id"] + cols
    marks = ", ".join("?" for _ in names)
    args = [guild_id] + params
    extra = spec.get("extra") or {}
    for col, val in extra.items():
        names.append(col)
        args.append(actor_id if val is None else val)
        marks += ", ?"
    mode = spec["mode"]
    if mode == "upsert":
        keys = spec["key"]
        updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in keys)
        await db.raw_execute(
            f"INSERT INTO {table} ({', '.join(names)}) VALUES ({marks}) ON CONFLICT({', '.join(keys)}) DO UPDATE SET {updates}",
            tuple(args),
        )
    elif mode == "dedupe":
        conds = " AND ".join(f"{c} IS ?" for c in spec["dedupe"])
        probe = await db.raw_fetchone(
            f"SELECT 1 FROM {table} WHERE guild_id=? AND {conds}", (guild_id, *[values[c] for c in spec["dedupe"]]),
        )
        if probe:
            return
        names.insert(0, spec["id_col"])
        args.insert(0, str(uuid.uuid4())[:8])
        await db.raw_execute(f"INSERT INTO {table} ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})", tuple(args))
    else:
        await db.raw_execute(f"INSERT OR IGNORE INTO {table} ({', '.join(names)}) VALUES ({marks})", tuple(args))


async def _apply_nsfw(guild: discord.Guild, data: dict, rmap: dict, cmap: dict, report: Report):
    block = data.get("nsfw")
    if not block:
        return
    role_id = _resolve(block.get("role"), rmap, cmap)
    role = guild.get_role(role_id) if role_id is not DROP else None
    if role is None:
        return
    channel_ids = [c for c in (_resolve(t, rmap, cmap) for t in block.get("channels", [])) if c is not DROP]
    async with nsfw_util.guild_lock(guild.id):
        await nsfw_util.set_role_id(guild.id, role.id)
        ids = await nsfw_util.get_channel_ids(guild.id)
        snapshots = await nsfw_util.get_snapshots(guild.id)
        for cid in channel_ids:
            channel = guild.get_channel(cid)
            if channel is None or cid in ids:
                continue
            try:
                await nsfw_util.lock_channel(channel, role, snapshots, "Soward server template")
            except discord.HTTPException as exc:
                report.fail(f"NSFW lock on <#{cid}>: {str(exc)[:80]}")
                continue
            ids.append(cid)
            await asyncio.sleep(0.35)
        await nsfw_util.save_channels(guild.id, ids, snapshots)
    report.ok(f"NSFW role and {len(channel_ids)} NSFW channel(s) restored")


async def _apply_logs(bot, guild: discord.Guild, data: dict, rmap: dict, cmap: dict, report: Report):
    cog = bot.get_cog("Logging")
    if cog is None:
        return
    flags = data.get("flags") or {}
    if flags.get("logging"):
        try:
            await cog.provision_channels(guild)
            report.ok("Created the log channels")
        except discord.HTTPException as exc:
            report.fail(f"Log channels: {str(exc)[:80]}")
        return
    for category, token in (data.get("logs") or {}).items():
        if category not in config.LOG_CATEGORIES:
            continue
        channel_id = _resolve(token, rmap, cmap)
        channel = guild.get_channel(channel_id) if channel_id is not DROP else None
        if channel is None:
            continue
        try:
            webhook = await channel.create_webhook(name=f"{config.BOT_NAME} Logs")
        except discord.HTTPException:
            continue
        await db.raw_execute(
            "INSERT INTO log_channels (guild_id, category, channel_id, webhook_url) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(guild_id, category) DO UPDATE SET channel_id=excluded.channel_id, webhook_url=excluded.webhook_url",
            (guild.id, category, channel.id, webhook.url),
        )
        cog._webhook_cache.pop((guild.id, category), None)
        await asyncio.sleep(0.3)


async def _apply_content(bot, guild: discord.Guild, data: dict, rmap: dict, cmap: dict, actor_id: int, report: Report):
    cap = await embed_templates.get_template_cap(guild.id)
    used = await embed_templates.count_templates(guild.id)
    for spec in data.get("embeds") or []:
        name = str(spec.get("name", ""))[:60].lower()
        if not name:
            continue
        exists = await embed_templates.get_template(guild.id, name)
        if exists and not spec.get("overwrite"):
            continue
        if not exists:
            if used >= cap:
                report.fail(f"Embed **{name}**: embed template limit reached")
                continue
            used += 1
        now = time.time()
        await db.raw_execute(
            "INSERT INTO embed_templates (guild_id, name, title, title_url, description, color, author_text, author_icon, author_url,"
            " footer_text, footer_icon, image_url, thumbnail_url, use_timestamp, created_by, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id, name) DO UPDATE SET title=excluded.title, title_url=excluded.title_url, description=excluded.description,"
            " color=excluded.color, author_text=excluded.author_text, author_icon=excluded.author_icon, author_url=excluded.author_url,"
            " footer_text=excluded.footer_text, footer_icon=excluded.footer_icon, image_url=excluded.image_url,"
            " thumbnail_url=excluded.thumbnail_url, use_timestamp=excluded.use_timestamp, updated_at=excluded.updated_at",
            (guild.id, name, spec.get("title"), spec.get("title_url"), spec.get("description"), spec.get("color"),
             spec.get("author_text"), spec.get("author_icon"), spec.get("author_url"), spec.get("footer_text"),
             spec.get("footer_icon"), spec.get("image_url"), spec.get("thumbnail_url"), int(spec.get("use_timestamp") or 0),
             actor_id, now, now),
        )
        await embed_templates.clear_fields(guild.id, name)
        for field in (spec.get("fields") or [])[:25]:
            await embed_templates.add_field(guild.id, name, str(field.get("name", ""))[:256], str(field.get("value", ""))[:1024], bool(field.get("inline")))
        report.counts["embeds"] += 1

    for message in data.get("messages") or []:
        channel = _channel(guild, message.get("channel"), cmap)
        name = str(message.get("embed", "")).lower()
        if channel is None or not name:
            continue
        template = await embed_templates.get_template(guild.id, name)
        if template is None:
            continue
        try:
            recent = [m async for m in channel.history(limit=15) if m.author.id == guild.me.id and m.embeds]
        except discord.HTTPException:
            recent = []
        if any((m.embeds[0].title or "") == (template.get("title") or "") for m in recent):
            continue
        fields = await embed_templates.get_fields(guild.id, name)
        from utils import message_vars
        var_map = message_vars.build_base_variables(guild.me, guild, channel)
        embed = embed_templates.build_discord_embed(template, var_map, fields)
        try:
            sent = await channel.send(embed=embed)
            if message.get("pin"):
                try:
                    await sent.pin()
                except discord.HTTPException:
                    pass
            report.counts["messages"] += 1
        except discord.HTTPException as exc:
            report.fail(f"Message in {channel.mention}: {str(exc)[:80]}")
        await asyncio.sleep(0.4)

    cog = bot.get_cog("ReactionRoles")
    if cog is not None:
        existing = await db.raw_fetch("SELECT embed_name, channel_id FROM reaction_role_panels WHERE guild_id=?", (guild.id,))
        taken = {(r["embed_name"], r["channel_id"]) for r in existing}
        for panel in data.get("panels") or []:
            channel = _channel(guild, panel.get("channel"), cmap)
            if channel is None:
                continue
            embed_name = (panel.get("embed") or "").lower() or None
            if (embed_name, channel.id) in taken:
                continue
            bindings = []
            for item in panel.get("roles", []):
                role_id = _resolve(item.get("role"), rmap, cmap)
                if role_id is DROP or guild.get_role(role_id) is None:
                    continue
                bindings.append({"emoji": item["emoji"], "role_id": role_id, "label": item.get("label")})
            if not bindings:
                continue
            ptype = panel.get("type") if panel.get("type") in ("reaction", "select", "button") else "button"
            try:
                await cog.create_panel(
                    guild, channel, creator_id=actor_id, embed_name=embed_name, panel_type=ptype,
                    mode=panel.get("mode") or "normal", max_roles=int(panel.get("max_roles") or 0), bindings=bindings,
                )
                report.counts["panels"] += 1
            except discord.HTTPException as exc:
                report.fail(f"Role panel in {channel.mention}: {str(exc)[:80]}")
            await asyncio.sleep(0.4)

    tickets = tickets_util
    from cogs.tickets import build_panel_view
    for item in data.get("tickets") or []:
        channel = _channel(guild, item.get("channel"), cmap)
        name = str(item.get("name", "Support"))[:60]
        if channel is None or await tickets.find_panel(guild.id, name):
            continue
        if len(await tickets.list_panels(guild.id)) >= await tickets.limit_for(guild.id, "panels"):
            report.fail("Ticket panel skipped: panel limit reached")
            continue
        staff = [r for r in (_resolve(_tok("role", k), rmap, cmap) for k in item.get("staff", [])) if r is not DROP]
        if not staff:
            continue
        panel_id = await tickets.create_panel(guild.id, name)
        fields = {"staff_role_ids": json.dumps(staff)}
        category_id = cmap.get(item.get("category"))
        if category_id:
            fields["category_id"] = category_id
        if item.get("welcome"):
            fields["welcome_text"] = item["welcome"]
        transcript = _resolve(_tok("channel", item["transcript"]), rmap, cmap) if item.get("transcript") else DROP
        if transcript is not DROP:
            fields["transcript_channel_id"] = transcript
        if item.get("button"):
            fields["button_label"] = str(item["button"])[:80]
        questions = [q for q in (item.get("questions") or []) if isinstance(q, str)][:await tickets.limit_for(guild.id, "questions")]
        if questions:
            fields["questions"] = json.dumps(questions)
        if item.get("one_per_user") is not None:
            fields["one_per_user"] = int(bool(item["one_per_user"]))
        if item.get("ask_subject") is not None:
            fields["ask_subject"] = int(bool(item["ask_subject"]))
        await tickets.update_panel(panel_id, **fields)
        panel = await tickets.find_panel(guild.id, panel_id)
        try:
            message = await channel.send(view=build_panel_view(panel))
            await tickets.update_panel(panel_id, channel_id=channel.id, message_id=message.id)
            report.counts["panels"] += 1
        except discord.HTTPException as exc:
            report.fail(f"Ticket panel: {str(exc)[:80]}")


def _channel(guild: discord.Guild, token, cmap: dict):
    if isinstance(token, str):
        token = _tok("channel", token)
    if not token:
        return None
    channel_id = _resolve(token, {}, cmap)
    if channel_id is DROP:
        return None
    channel = guild.get_channel(channel_id)
    return channel if isinstance(channel, discord.TextChannel) else None


async def _apply_flags(bot, guild: discord.Guild, data: dict, foreign: bool, rmap: dict, cmap: dict, report: Report):
    flags = data.get("flags") or {}
    preset = flags.get("security_preset")
    if preset in sec_settings.PRESETS and not foreign:
        changed = await sec_settings.apply_preset(guild.id, preset, skip=("verification",))
        report.ok(f"Applied the `{preset}` security preset ({len(changed)} setting(s))")
    panel_channel = _channel(guild, flags.get("verification_panel"), cmap)
    if panel_channel is not None and await guild_settings.get(guild.id, "verification_level", 0):
        from cogs.verification import VerificationPanelLayout
        try:
            message = await panel_channel.send(view=VerificationPanelLayout(guild.name))
            await guild_settings.set(guild.id, "verification_channel_id", panel_channel.id)
            await guild_settings.set(guild.id, "verification_panel_message_id", message.id)
            report.ok(f"Posted the verification panel in {panel_channel.mention}")
        except discord.HTTPException as exc:
            report.fail(f"Verification panel: {str(exc)[:80]}")


async def _protected_channels(guild: discord.Guild) -> set[int]:
    from utils import tickets
    protected = {guild.rules_channel.id if guild.rules_channel else 0, guild.public_updates_channel.id if guild.public_updates_channel else 0}
    protected |= await tickets.open_channel_ids()
    rows = await db.raw_fetch("SELECT channel_id FROM log_channels WHERE guild_id=?", (guild.id,))
    protected |= {r["channel_id"] for r in rows}
    return protected


async def _protected_roles(guild: discord.Guild) -> set[int]:
    protected = {guild.me.top_role.id}
    quarantine = await guild_settings.get(guild.id, "antinuke_quarantine_role_id")
    if quarantine:
        protected.add(int(quarantine))
    return protected


def _clean_names(data: dict) -> tuple[set[str], set[tuple]]:
    roles = {r["name"].lower() for r in data.get("roles", [])}
    channels = set()
    for cat in data.get("categories", []):
        cname = (cat.get("name") or "").lower()
        for ch in cat.get("channels", []):
            channels.add((cname, _norm_name(ch["name"], ch["type"])))
    return roles, channels


async def clean_targets(guild: discord.Guild, keep_roles: set, keep_channels: set, skip_channel_id: int = 0) -> tuple[list, list, list]:
    protected = await _protected_channels(guild)
    protected_roles = await _protected_roles(guild)
    channels = [c for c in guild.channels if not isinstance(c, (discord.CategoryChannel, discord.Thread))
                and c.id not in keep_channels and c.id not in protected and c.id != skip_channel_id]
    categories = [c for c in guild.categories if c.id not in keep_channels and c.id not in protected]
    top = guild.me.top_role.position
    roles = [r for r in guild.roles if not r.is_default() and not r.managed and r.position < top
             and r.id not in keep_roles and r.id not in protected_roles]
    return channels, categories, roles


async def predict_clean(guild: discord.Guild, data: dict, parts: set) -> tuple[int, int]:
    role_names, channel_names = _clean_names(data)
    keep_roles = {r.id for r in guild.roles if r.name.lower() in role_names}
    keep_channels = set()
    for ch in guild.channels:
        if isinstance(ch, discord.CategoryChannel):
            if any(cn == ch.name.lower() for cn, _ in channel_names):
                keep_channels.add(ch.id)
        elif isinstance(ch, discord.Thread):
            continue
        else:
            cname = ch.category.name.lower() if ch.category else ""
            if (cname, ch.name) in channel_names:
                keep_channels.add(ch.id)
    channels, categories, roles = await clean_targets(guild, keep_roles, keep_channels)
    return (len(channels) + len(categories)) if "channels" in parts else 0, len(roles) if "roles" in parts else 0


async def clean(guild: discord.Guild, report: Report, parts: set, skip_channel_id: int = 0) -> None:
    keep_roles = set(report.rmap.values())
    keep_channels = set(report.cmap.values())
    channels, categories, roles = await clean_targets(guild, keep_roles, keep_channels, skip_channel_id)
    if "channels" in parts:
        gone: set[int] = set()
        for channel in channels:
            try:
                await channel.delete(reason="Soward server template clean")
                gone.add(channel.id)
                report.counts["deleted_channels"] += 1
            except discord.HTTPException as exc:
                report.fail(f"Could not delete #{channel.name}: {str(exc)[:60]}")
            await asyncio.sleep(0.4)
        for category in categories:
            if any(c.id not in gone for c in category.channels):
                continue
            try:
                await category.delete(reason="Soward server template clean")
                report.counts["deleted_channels"] += 1
            except discord.HTTPException as exc:
                report.fail(f"Could not delete {category.name}: {str(exc)[:60]}")
            await asyncio.sleep(0.4)
    if "roles" in parts:
        for role in roles:
            try:
                await role.delete(reason="Soward server template clean")
                report.counts["deleted_roles"] += 1
            except discord.HTTPException as exc:
                report.fail(f"Could not delete role {role.name}: {str(exc)[:60]}")
            await asyncio.sleep(0.4)


SCRUB_TABLES = (
    ("level_role_rewards", "role_id"), ("xp_no_xp_channels", "channel_id"), ("xp_no_xp_roles", "role_id"),
    ("security_whitelist", "target_id"), ("xp_multipliers", "scope_id"),
)


def _refs(value: Any, gone: set) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value in gone
    if isinstance(value, str) and value.isdigit() and len(value) >= 17:
        return int(value) in gone
    if isinstance(value, list):
        return any(_refs(v, gone) for v in value)
    if isinstance(value, dict):
        return any(_refs(v, gone) for v in value.values())
    return False


async def _scrub(guild_id: int, channel_ids: set, role_ids: set):
    gone = channel_ids | role_ids
    await db.raw_execute("DELETE FROM log_channels WHERE guild_id=?", (guild_id,))
    await db.raw_execute("DELETE FROM reaction_role_bindings WHERE panel_id IN (SELECT panel_id FROM reaction_role_panels WHERE guild_id=?)", (guild_id,))
    await db.raw_execute("DELETE FROM reaction_role_panels WHERE guild_id=?", (guild_id,))
    await db.raw_execute("DELETE FROM ticket_panels WHERE guild_id=?", (guild_id,))
    await db.raw_execute("DELETE FROM nsfw_channels WHERE guild_id=?", (guild_id,))
    await db.raw_execute("DELETE FROM jtc_channels WHERE guild_id=?", (guild_id,))
    await db.raw_execute("DELETE FROM jtc_hubs WHERE guild_id=?", (guild_id,))
    await db.raw_execute("DELETE FROM booster_tiers WHERE guild_id=?", (guild_id,))
    await db.raw_execute("UPDATE booster_roles SET role_id=NULL WHERE guild_id=?", (guild_id,))
    await db.raw_execute("UPDATE booster_config SET base_role_id=NULL, position_ref_id=NULL WHERE guild_id=?", (guild_id,))
    ids = list(gone)
    for table, column in SCRUB_TABLES:
        for start in range(0, len(ids), 400):
            chunk = ids[start:start + 400]
            await db.raw_execute(f"DELETE FROM {table} WHERE guild_id=? AND {column} IN ({','.join('?' for _ in chunk)})", (guild_id, *chunk))
    for start in range(0, len(ids), 400):
        chunk = ids[start:start + 400]
        await db.raw_execute(
            f"UPDATE guild_greeting_config SET channel_id=NULL, enabled=0 WHERE guild_id=? AND channel_id IN ({','.join('?' for _ in chunk)})",
            (guild_id, *chunk),
        )
    for key, value in (await guild_settings.get_all(guild_id)).items():
        if _refs(value, gone):
            await guild_settings.delete(guild_id, key)


def predict_full(guild: discord.Guild) -> tuple[int, int, int]:
    bots = [m for m in guild.members if m.bot and m.id != guild.me.id]
    keep = {guild.rules_channel.id if guild.rules_channel else 0, guild.public_updates_channel.id if guild.public_updates_channel else 0}
    channels = [c for c in guild.channels if not isinstance(c, discord.Thread) and c.id not in keep]
    top = guild.me.top_role.position
    roles = [r for r in guild.roles if not r.is_default() and not r.managed and r.position < top]
    return len(bots), len(channels), len(roles)


async def full_clean(guild: discord.Guild, report: Report, skip_channel_id: int = 0):
    for member in list(guild.members):
        if not member.bot or member.id == guild.me.id:
            continue
        try:
            await member.kick(reason="Soward full template clean")
            report.counts["kicked_bots"] += 1
        except discord.HTTPException as exc:
            report.fail(f"Could not kick {member.name}: {str(exc)[:60]}")
        await asyncio.sleep(0.5)
    await asyncio.sleep(2)
    keep = {guild.rules_channel.id if guild.rules_channel else 0, guild.public_updates_channel.id if guild.public_updates_channel else 0, skip_channel_id}
    gone_channels: set[int] = set()
    ordered = [c for c in guild.channels if not isinstance(c, (discord.CategoryChannel, discord.Thread))] + list(guild.categories)
    for channel in ordered:
        if channel.id in keep:
            continue
        try:
            await channel.delete(reason="Soward full template clean")
            gone_channels.add(channel.id)
            report.counts["deleted_channels"] += 1
        except discord.HTTPException as exc:
            report.fail(f"Could not delete {channel.name}: {str(exc)[:60]}")
        await asyncio.sleep(0.4)
    top = guild.me.top_role.position
    gone_roles: set[int] = set()
    for role in list(guild.roles):
        if role.is_default() or role.managed or role.position >= top:
            continue
        try:
            await role.delete(reason="Soward full template clean")
            gone_roles.add(role.id)
            report.counts["deleted_roles"] += 1
        except discord.HTTPException as exc:
            report.fail(f"Could not delete role {role.name}: {str(exc)[:60]}")
        await asyncio.sleep(0.4)
    await _scrub(guild.id, gone_channels, gone_roles)
    await guild_settings.delete(guild.id, "antinuke_quarantine_role_id")


async def _ensure_quarantine(guild: discord.Guild, report: Report):
    from utils import security_autosetup
    role_id = await guild_settings.get(guild.id, "antinuke_quarantine_role_id")
    role = guild.get_role(int(role_id)) if role_id else None
    if role is None:
        role = next((r for r in guild.roles if r.name.lower() == "quarantined" and not r.managed), None)
    created = False
    if role is None:
        try:
            role = await guild.create_role(name="Quarantined", permissions=discord.Permissions.none(), colour=discord.Colour(0x607D8B), reason="Soward server template")
        except discord.HTTPException as exc:
            report.fail(f"Quarantine role: {str(exc)[:80]}")
            return
        created = True
        try:
            await role.edit(position=max(1, guild.me.top_role.position - 1))
        except discord.HTTPException:
            pass
    await guild_settings.set(guild.id, "antinuke_quarantine_role_id", role.id)
    locked = await security_autosetup._lock_channels(guild, role)
    report.ok(f"{'Created' if created else 'Linked'} the Quarantined role and hid {locked} channel(s) or categories from it")


async def apply(bot, guild: discord.Guild, data: dict, *, actor_id: int, parts: set, foreign: bool) -> Report:
    report = Report()
    rmap: dict[str, int] = {}
    cmap: dict[str, int] = {}

    if "roles" in parts:
        await _apply_roles(guild, data.get("roles", []), foreign, rmap, report)
    else:
        existing = {r.name.lower(): r for r in guild.roles if not r.is_default() and not r.managed}
        for spec in data.get("roles", []):
            found = existing.get(spec["name"].lower())
            if found:
                rmap[spec["key"]] = found.id
    if "channels" in parts:
        await _apply_channels(guild, data.get("categories", []), rmap, cmap, report)
    else:
        by_name = {}
        for ch in guild.channels:
            by_name.setdefault(ch.name, ch.id)
        for cat in data.get("categories", []):
            for ch in cat.get("channels", []):
                found = by_name.get(_norm_name(ch["name"], ch["type"]))
                if found:
                    cmap[ch["key"]] = found

    if "settings" in parts:
        await _apply_settings(guild, data, foreign, rmap, cmap, actor_id, report)
        await _apply_nsfw(guild, data, rmap, cmap, report)
        await _apply_logs(bot, guild, data, rmap, cmap, report)
        await _apply_flags(bot, guild, data, foreign, rmap, cmap, report)
    if "content" in parts:
        await _apply_content(bot, guild, data, rmap, cmap, actor_id, report)
    if "roles" in parts and (data.get("flags") or {}).get("quarantine", True):
        await _ensure_quarantine(guild, report)
    report.rmap = rmap
    report.cmap = cmap
    return report
