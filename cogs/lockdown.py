import asyncio
import json
import secrets
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import db, emoji_manager, security
from utils import security_settings as settings
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import ANTINUKE_INCIDENT, LOG_EVENT, bus
from utils.security_access import security_owner, security_staff
from utils.security_cmds import chunked

LOCKABLE = (discord.TextChannel, discord.VoiceChannel, discord.StageChannel, discord.ForumChannel)
LOCK_FIELDS = ("send_messages", "add_reactions", "create_public_threads", "create_private_threads", "send_messages_in_threads", "connect", "speak")
PAUSE = 0.35


def _ago(ts: float) -> str:
    seconds = max(0, int(time.time() - ts))
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return f"{seconds}s ago"


def _overwrite_dump(overwrite: discord.PermissionOverwrite) -> list[int]:
    allow, deny = overwrite.pair()
    return [allow.value, deny.value]


def _snapshot_guild(guild: discord.Guild) -> dict:
    roles = [
        {
            "id": r.id, "name": r.name, "color": r.color.value, "hoist": r.hoist, "mentionable": r.mentionable,
            "permissions": r.permissions.value, "position": r.position,
        }
        for r in guild.roles if not r.is_default() and not r.managed
    ]
    channels = []
    for ch in sorted(guild.channels, key=lambda c: (c.position, c.id)):
        entry = {
            "id": ch.id, "name": ch.name, "type": ch.type.value, "position": ch.position,
            "parent": ch.category_id,
            "overwrites": [
                {"id": target.id, "kind": "role" if isinstance(target, discord.Role) else "member", "pair": _overwrite_dump(ow)}
                for target, ow in ch.overwrites.items()
            ],
        }
        if isinstance(ch, discord.TextChannel):
            entry.update(topic=ch.topic, nsfw=ch.nsfw, slowmode=ch.slowmode_delay)
        elif isinstance(ch, discord.VoiceChannel):
            entry.update(bitrate=min(ch.bitrate, 96000), user_limit=ch.user_limit)
        channels.append(entry)
    return {
        "name": guild.name, "verification": guild.verification_level.value,
        "default_perms": guild.default_role.permissions.value,
        "roles": roles, "channels": channels,
    }


async def _snapshot_full(guild: discord.Guild) -> dict:
    data = _snapshot_guild(guild)
    bans: list[int] = []
    try:
        async for entry in guild.bans(limit=1000):
            bans.append(entry.user.id)
    except discord.HTTPException:
        pass
    data["bans"] = bans
    data["settings"] = {
        "explicit_filter": guild.explicit_content_filter.value,
        "notifications": guild.default_notifications.value,
        "afk_timeout": guild.afk_timeout,
    }
    return data


class Lockdown(commands.Cog):
    category = "Config"
    submodule = "Security"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._locks: dict[int, asyncio.Lock] = {}
        self._quiet_until: dict[int, float] = {}
        self.expiry_loop.start()
        self.backup_loop.start()
        bus.subscribe(ANTINUKE_INCIDENT, self._on_nuke)

    def cog_unload(self):
        bus.unsubscribe(ANTINUKE_INCIDENT, self._on_nuke)
        self.expiry_loop.cancel()
        self.backup_loop.cancel()

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    async def is_active(self, guild_id: int) -> bool:
        row = await db.raw_fetchone("SELECT active FROM security_lockdown WHERE guild_id=?", (guild_id,))
        return bool(row and row["active"])

    async def start(self, guild: discord.Guild, reason: str, actor_id: Optional[int], duration: Optional[int] = None) -> int:
        async with self._lock(guild.id):
            if await self.is_active(guild.id):
                return 0
            skip = set(await settings.get(guild.id, "security", "lockdown_skip_channels") or [])
            length = duration or int(await settings.get(guild.id, "security", "lockdown_duration"))
            default = guild.default_role
            saved: list[dict] = []
            locked = 0
            now = time.time()
            await db.raw_execute(
                "INSERT INTO security_lockdown (guild_id, active, started_at, expires_at, started_by, saved) VALUES (?, 1, ?, ?, ?, '[]')"
                " ON CONFLICT(guild_id) DO UPDATE SET active=1, started_at=excluded.started_at, expires_at=excluded.expires_at,"
                " started_by=excluded.started_by, saved='[]'",
                (guild.id, now, now + length, str(actor_id) if actor_id else reason),
            )
            for channel in guild.channels:
                if not isinstance(channel, LOCKABLE) or channel.id in skip:
                    continue
                me = guild.me
                if me is None or not channel.permissions_for(me).manage_roles:
                    continue
                overwrite = channel.overwrites_for(default)
                before = {f: getattr(overwrite, f) for f in LOCK_FIELDS}
                if isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                    changes = {f: False for f in ("connect", "speak")}
                else:
                    changes = {f: False for f in LOCK_FIELDS if f not in ("connect", "speak")}
                saved.append({"id": channel.id, "before": {k: before[k] for k in changes}})
                overwrite.update(**changes)
                try:
                    await channel.set_permissions(default, overwrite=overwrite, reason=f"Soward lockdown: {reason}")
                    locked += 1
                except (discord.Forbidden, discord.HTTPException):
                    saved.pop()
                await asyncio.sleep(PAUSE)
            await db.raw_execute("UPDATE security_lockdown SET saved=? WHERE guild_id=?", (json.dumps(saved), guild.id))
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="server_lockdown", active=True, actor_id=actor_id, detail=f"{reason} · {locked} channels locked")
        return locked

    async def end(self, guild: discord.Guild, ended_by: Optional[int] = None, reason: str = "lifted") -> int:
        async with self._lock(guild.id):
            row = await db.raw_fetchone("SELECT * FROM security_lockdown WHERE guild_id=?", (guild.id,))
            if not row or not row["active"]:
                return -1
            await db.raw_execute("UPDATE security_lockdown SET active=0 WHERE guild_id=?", (guild.id,))
            restored = 0
            for entry in json.loads(row["saved"] or "[]"):
                channel = guild.get_channel(entry["id"])
                if channel is None:
                    continue
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.update(**entry["before"])
                try:
                    if overwrite.is_empty():
                        await channel.set_permissions(guild.default_role, overwrite=None, reason=f"Soward lockdown {reason}")
                    else:
                        await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=f"Soward lockdown {reason}")
                    restored += 1
                except (discord.Forbidden, discord.HTTPException):
                    pass
                await asyncio.sleep(PAUSE)
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="server_lockdown", active=False, actor_id=ended_by, detail=f"{reason} · {restored} channels restored")
        return restored

    @tasks.loop(seconds=30)
    async def expiry_loop(self):
        rows = await db.raw_fetch("SELECT guild_id FROM security_lockdown WHERE active=1 AND expires_at IS NOT NULL AND expires_at<=?", (time.time(),))
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if guild is None:
                await db.raw_execute("UPDATE security_lockdown SET active=0 WHERE guild_id=?", (row["guild_id"],))
                continue
            try:
                await self.end(guild, None, "expired")
            except Exception:
                continue

    @expiry_loop.before_loop
    async def _before_expiry(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=10)
    async def backup_loop(self):
        for guild in list(self.bot.guilds):
            try:
                if not await settings.get(guild.id, "security", "auto_backup"):
                    continue
                interval = int(await settings.get(guild.id, "security", "backup_interval_hours")) * 3600
                last = await db.raw_fetchone("SELECT MAX(created_at) AS t FROM security_backups WHERE guild_id=? AND auto=1", (guild.id,))
                if last and last["t"] and time.time() - last["t"] < interval:
                    continue
                if self._quiet_until.get(guild.id, 0) > time.time():
                    continue
                await self.create_backup(guild, "automatic", None, auto=True)
            except Exception:
                continue

    @backup_loop.before_loop
    async def _before_backup(self):
        await self.bot.wait_until_ready()

    async def create_backup(self, guild: discord.Guild, label: str, created_by: Optional[int], auto: bool = False) -> str:
        backup_id = secrets.token_hex(4)
        await db.raw_execute(
            "INSERT INTO security_backups (backup_id, guild_id, label, created_by, auto, data) VALUES (?, ?, ?, ?, ?, ?)",
            (backup_id, guild.id, label[:60], created_by, 1 if auto else 0, json.dumps(await _snapshot_full(guild))),
        )
        if auto:
            keep = int(await settings.get(guild.id, "security", "backup_keep"))
            stale = await db.raw_fetch(
                "SELECT backup_id FROM security_backups WHERE guild_id=? AND auto=1 ORDER BY created_at DESC LIMIT -1 OFFSET ?", (guild.id, keep)
            )
            for row in stale:
                await db.raw_execute("DELETE FROM security_backups WHERE backup_id=?", (row["backup_id"],))
        else:
            manual = await db.raw_fetch(
                "SELECT backup_id FROM security_backups WHERE guild_id=? AND auto=0 ORDER BY created_at DESC LIMIT -1 OFFSET 25", (guild.id,)
            )
            for row in manual:
                await db.raw_execute("DELETE FROM security_backups WHERE backup_id=?", (row["backup_id"],))
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="security_backup", actor_id=created_by, detail=f"Backup `{backup_id}` created ({label}).")
        return backup_id

    async def _on_nuke(self, *, guild_id: int, **_):
        self._quiet_until[guild_id] = time.time() + 3600
        guild = self.bot.get_guild(guild_id)
        if guild is None or not await settings.get(guild_id, "antinuke", "restore_from_backup"):
            return
        row = await db.raw_fetchone("SELECT * FROM security_backups WHERE guild_id=? ORDER BY created_at DESC LIMIT 1", (guild_id,))
        if row is None:
            return
        data = json.loads(row["data"])
        roles, _, _ = await self._restore_roles(guild, data, False)
        channels, _ = await self._restore_channels(guild, data)
        banned = await self._restore_bans(guild, data)
        await bus.publish(
            LOG_EVENT, guild_id=guild_id, action="security_backup", actor_id=None,
            detail=f"Auto-restored `{row['backup_id']}` after an AntiNuke incident: {roles} roles, {channels} channels, {banned} bans.",
        )

    async def _restore_bans(self, guild: discord.Guild, data: dict) -> int:
        wanted = set(data.get("bans", []))
        if not wanted:
            return 0
        try:
            current = {entry.user.id async for entry in guild.bans(limit=None)}
        except discord.HTTPException:
            return 0
        restored = 0
        for user_id in wanted - current:
            try:
                await guild.ban(discord.Object(id=user_id), reason="Backup restore: ban was missing")
                restored += 1
            except discord.HTTPException:
                continue
            await asyncio.sleep(PAUSE)
        return restored

    async def _restore_settings(self, guild: discord.Guild, data: dict) -> bool:
        saved = data.get("settings")
        if not saved:
            return False
        try:
            await guild.edit(
                name=data.get("name", guild.name),
                verification_level=discord.VerificationLevel(data.get("verification", guild.verification_level.value)),
                explicit_content_filter=discord.ContentFilter(saved["explicit_filter"]),
                default_notifications=discord.NotificationLevel(saved["notifications"]),
                afk_timeout=saved["afk_timeout"],
                reason="Backup restore: server settings",
            )
        except (discord.HTTPException, ValueError, KeyError):
            return False
        return True

    async def _find_backup(self, guild_id: int, backup_id: str) -> Optional[dict]:
        return await db.raw_fetchone("SELECT * FROM security_backups WHERE guild_id=? AND backup_id=?", (guild_id, backup_id.lower()))

    async def _restore_roles(self, guild: discord.Guild, data: dict, repair: bool) -> tuple[int, int, int]:
        created = repaired = failed = 0
        me = guild.me
        top = me.top_role.position if me else 0
        by_id = {r.id: r for r in guild.roles}
        by_name = {r.name: r for r in guild.roles}
        for entry in sorted(data["roles"], key=lambda r: r["position"]):
            existing = by_id.get(entry["id"]) or by_name.get(entry["name"])
            perms = discord.Permissions(entry["permissions"])
            try:
                if existing is None:
                    role = await guild.create_role(
                        name=entry["name"], permissions=perms, colour=discord.Colour(entry["color"]),
                        hoist=entry["hoist"], mentionable=entry["mentionable"], reason="Soward backup restore",
                    )
                    by_id[role.id] = role
                    by_name[role.name] = role
                    entry["_new"] = role.id
                    created += 1
                elif repair and existing.position < top and not existing.managed:
                    await existing.edit(
                        permissions=perms, colour=discord.Colour(entry["color"]), hoist=entry["hoist"],
                        mentionable=entry["mentionable"], reason="Soward backup restore",
                    )
                    repaired += 1
            except (discord.Forbidden, discord.HTTPException):
                failed += 1
            await asyncio.sleep(PAUSE)
        return created, repaired, failed

    def _map_role(self, guild: discord.Guild, data: dict, old_id: int) -> Optional[discord.Role]:
        role = guild.get_role(old_id)
        if role is not None:
            return role
        for entry in data["roles"]:
            if entry["id"] == old_id:
                return discord.utils.get(guild.roles, name=entry["name"])
        return None

    def _overwrites(self, guild: discord.Guild, data: dict, entry: dict) -> dict:
        out = {}
        for item in entry["overwrites"]:
            if item["kind"] == "role":
                target = guild.default_role if item["id"] == guild.id else self._map_role(guild, data, item["id"])
            else:
                target = guild.get_member(item["id"])
            if target is None:
                continue
            allow, deny = item["pair"]
            out[target] = discord.PermissionOverwrite.from_pair(discord.Permissions(allow), discord.Permissions(deny))
        return out

    async def _restore_channels(self, guild: discord.Guild, data: dict) -> tuple[int, int]:
        created = failed = 0
        existing = {c.id for c in guild.channels}
        names = {(c.name, c.type.value) for c in guild.channels}
        new_parents: dict[int, discord.CategoryChannel] = {}
        ordered = sorted(data["channels"], key=lambda c: (0 if c["type"] == discord.ChannelType.category.value else 1, c["position"]))
        for entry in ordered:
            if entry["id"] in existing or (entry["name"], entry["type"]) in names:
                continue
            kind = discord.ChannelType(entry["type"])
            parent = guild.get_channel(entry["parent"]) if entry["parent"] else None
            if parent is None and entry["parent"]:
                parent = new_parents.get(entry["parent"])
            overwrites = self._overwrites(guild, data, entry)
            try:
                if kind is discord.ChannelType.category:
                    made = await guild.create_category(entry["name"], overwrites=overwrites, reason="Soward backup restore")
                    new_parents[entry["id"]] = made
                elif kind is discord.ChannelType.text:
                    await guild.create_text_channel(
                        entry["name"], category=parent, overwrites=overwrites, topic=entry.get("topic"),
                        nsfw=entry.get("nsfw", False), slowmode_delay=entry.get("slowmode", 0), reason="Soward backup restore",
                    )
                elif kind is discord.ChannelType.voice:
                    await guild.create_voice_channel(
                        entry["name"], category=parent, overwrites=overwrites, bitrate=entry.get("bitrate", 64000),
                        user_limit=entry.get("user_limit", 0), reason="Soward backup restore",
                    )
                else:
                    continue
                created += 1
            except (discord.Forbidden, discord.HTTPException):
                failed += 1
            await asyncio.sleep(PAUSE)
        return created, failed

    @commands.group(name="serverlock", aliases=["panic", "slock"], invoke_without_command=True, help="Lock every channel in the server during an attack.")
    @commands.guild_only()
    @security_staff()
    async def serverlock_group(self, ctx: commands.Context):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT * FROM security_lockdown WHERE guild_id=?", (ctx.guild.id,))
        if row and row["active"]:
            left = max(0, int(row["expires_at"] - time.time())) if row["expires_at"] else 0
            body = f"Lockdown is **active**. Lifts automatically in about {left // 60}m."
        else:
            body = "Lockdown is **inactive**."
        body += "\n\n`serverlock on [reason]` · `serverlock off` · `serverlock duration <time>` · `serverlock skip add|remove|list <channel>` · `serverlock auto nuke|raid <on/off>`"
        await ctx.send(view=info_layout(f"{e('lock')} Server Lockdown", body))

    @serverlock_group.command(name="on", aliases=["start", "enable"], help="Deny messages, reactions, threads and voice for everyone in every channel.")
    @security_staff()
    async def serverlock_on(self, ctx: commands.Context, *, reason: str = "Manual lockdown"):
        e = emoji_manager.get
        if await self.is_active(ctx.guild.id):
            return await ctx.send(view=error_layout("Already locked", "The server is already in lockdown. Use `serverlock off` to lift it."))
        note = await ctx.send(view=info_layout(f"{e('lock')} Locking server", "Locking channels. This takes a moment on large servers."))
        count = await self.start(ctx.guild, reason, ctx.author.id)
        await note.edit(view=success_layout(f"{e('lock')} Server locked", f"**{count}** channels locked. It lifts automatically after the lockdown length, or run `serverlock off`."))

    @serverlock_group.command(name="off", aliases=["stop", "end", "disable"], help="Lift the lockdown and restore every channel.")
    @security_staff()
    async def serverlock_off(self, ctx: commands.Context):
        e = emoji_manager.get
        note = await ctx.send(view=info_layout(f"{e('unlock')} Lifting lockdown", "Restoring channel permissions."))
        restored = await self.end(ctx.guild, ctx.author.id, "lifted by staff")
        if restored < 0:
            return await note.edit(view=error_layout("Not locked", "The server is not in lockdown."))
        await note.edit(view=success_layout(f"{e('unlock')} Lockdown lifted", f"**{restored}** channels restored."))

    @serverlock_group.command(name="duration", help="Set how long a lockdown lasts, like 30m or 2h.")
    @security_staff()
    async def serverlock_duration(self, ctx: commands.Context, length: str):
        from utils.security_cmds import set_setting
        await set_setting(ctx, "security", "lockdown_duration", length)

    @serverlock_group.command(name="auto", help="Automatically lock the server after an AntiNuke trigger or when raid mode starts.")
    @security_staff()
    async def serverlock_auto(self, ctx: commands.Context, trigger: str, toggle: bool):
        from utils.security_cmds import set_setting
        trigger = trigger.lower()
        if trigger not in ("nuke", "raid"):
            return await ctx.send(view=error_layout("Unknown trigger", "Use `nuke` or `raid`."))
        await set_setting(ctx, "security", f"lockdown_on_{trigger}", "on" if toggle else "off")

    @serverlock_group.command(name="skip", help="Manage channels a lockdown leaves open.")
    @security_staff()
    async def serverlock_skip(self, ctx: commands.Context, action: str = "list", channel: Optional[discord.abc.GuildChannel] = None):
        from utils.security_cmds import list_edit, show_list
        if action.lower() == "list":
            return await show_list(ctx, "security", "lockdown_skip_channels")
        if channel is None:
            return await ctx.send(view=error_layout("Missing channel", "Give the channel to add or remove."))
        if action.lower() not in ("add", "remove"):
            return await ctx.send(view=error_layout("Unknown action", "Use `add`, `remove` or `list`."))
        await list_edit(ctx, "security", "lockdown_skip_channels", str(channel.id), action.lower() == "add")

    @commands.group(name="backup", aliases=["sbackup"], invoke_without_command=True, help="Back up and restore the server's roles and channels.")
    @commands.guild_only()
    @security_staff()
    async def backup_group(self, ctx: commands.Context):
        e = emoji_manager.get
        body = (
            "Snapshots keep roles, role permissions, categories, channels and their permission overwrites.\n\n"
            "`backup create [label]` · `backup list` · `backup info <id>` · `backup restore <id> [roles|channels|all] [repair]` · `backup delete <id>` · `backup auto <on/off>`"
        )
        await ctx.send(view=info_layout(f"{e('shield')} Server Backups", body))

    @backup_group.command(name="create", aliases=["new", "make"], help="Take a snapshot of the server now.")
    @security_staff()
    async def backup_create(self, ctx: commands.Context, *, label: str = "manual"):
        e = emoji_manager.get
        backup_id = await self.create_backup(ctx.guild, label, ctx.author.id)
        await ctx.send(view=success_layout(f"{e('check')} Backup created", f"Backup `{backup_id}` saved ({len(ctx.guild.roles) - 1} roles, {len(ctx.guild.channels)} channels)."))

    @backup_group.command(name="list", help="List saved backups.")
    @security_staff()
    async def backup_list(self, ctx: commands.Context):
        rows = await db.raw_fetch("SELECT backup_id, label, created_at, auto FROM security_backups WHERE guild_id=? ORDER BY created_at DESC LIMIT 30", (ctx.guild.id,))
        if not rows:
            return await ctx.send(view=info_layout("Server Backups", "No backups yet. Run `backup create`."))
        await chunked(ctx, "Server Backups", [f"`{r['backup_id']}` · {r['label'] or 'backup'}{' (auto)' if r['auto'] else ''} · {_ago(r['created_at'])}" for r in rows])

    @backup_group.command(name="info", help="Show what a backup contains.")
    @security_staff()
    async def backup_info(self, ctx: commands.Context, backup_id: str):
        row = await self._find_backup(ctx.guild.id, backup_id)
        if row is None:
            return await ctx.send(view=error_layout("Not found", "No backup with that id."))
        data = json.loads(row["data"])
        kinds = {}
        for ch in data["channels"]:
            name = discord.ChannelType(ch["type"]).name
            kinds[name] = kinds.get(name, 0) + 1
        lines = [f"**Label:** {row['label']} · **Taken:** {_ago(row['created_at'])}", f"**Roles:** {len(data['roles'])}", "**Channels:** " + (", ".join(f"{v} {k}" for k, v in kinds.items()) or "none")]
        await ctx.send(view=info_layout(f"Backup {row['backup_id']}", "\n".join(lines)))

    @backup_group.command(name="restore", help="Recreate what is missing. Usage: restore <id> [roles|channels|bans|settings|all] [repair]")
    @security_owner()
    async def backup_restore(self, ctx: commands.Context, backup_id: str, what: str = "all", repair: Optional[str] = None):
        e = emoji_manager.get
        what = what.lower()
        if what not in ("roles", "channels", "bans", "settings", "all"):
            return await ctx.send(view=error_layout("Unknown part", "Use `roles`, `channels`, `bans`, `settings` or `all`."))
        row = await self._find_backup(ctx.guild.id, backup_id)
        if row is None:
            return await ctx.send(view=error_layout("Not found", "No backup with that id."))
        data = json.loads(row["data"])
        note = await ctx.send(view=info_layout(f"{e('shield')} Restoring", "Recreating what is missing. Nothing existing is deleted."))
        lines = []
        if what in ("roles", "all"):
            made, fixed, bad = await self._restore_roles(ctx.guild, data, (repair or "").lower() == "repair")
            lines.append(f"Roles: {made} created, {fixed} repaired, {bad} failed")
        if what in ("channels", "all"):
            made, bad = await self._restore_channels(ctx.guild, data)
            lines.append(f"Channels: {made} created, {bad} failed")
        if what in ("bans", "all"):
            lines.append(f"Bans: {await self._restore_bans(ctx.guild, data)} restored")
        if what in ("settings", "all"):
            lines.append("Server settings: " + ("restored" if await self._restore_settings(ctx.guild, data) else "not restored"))
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_backup", actor_id=ctx.author.id, detail=f"Restored `{row['backup_id']}` ({what}). " + " · ".join(lines))
        await note.edit(view=success_layout(f"{e('check')} Restore finished", "\n".join(lines) + "\n\n-# Members' role assignments are not restored."))

    @backup_group.command(name="delete", aliases=["remove"], help="Delete a backup.")
    @security_staff()
    async def backup_delete(self, ctx: commands.Context, backup_id: str):
        e = emoji_manager.get
        row = await self._find_backup(ctx.guild.id, backup_id)
        if row is None:
            return await ctx.send(view=error_layout("Not found", "No backup with that id."))
        await db.raw_execute("DELETE FROM security_backups WHERE backup_id=?", (row["backup_id"],))
        await ctx.send(view=success_layout(f"{e('check')} Backup deleted", f"`{row['backup_id']}` removed."))

    @backup_group.command(name="auto", help="Turn automatic scheduled backups on or off.")
    @security_staff()
    async def backup_auto(self, ctx: commands.Context, toggle: bool):
        from utils.security_cmds import set_setting
        await set_setting(ctx, "security", "auto_backup", "on" if toggle else "off")

    @commands.command(name="securitycheck", aliases=["seccheck", "secaudit"], help="Scan the server for risky permissions, roles and bots.")
    @commands.guild_only()
    @security_staff()
    async def securitycheck(self, ctx: commands.Context):
        e = emoji_manager.get
        guild = ctx.guild
        me = guild.me
        issues: list[tuple[int, str]] = []
        everyone = guild.default_role.permissions
        risky = security.dangerous_permissions(everyone)
        if risky:
            issues.append((3, f"@everyone has dangerous permissions: {', '.join(risky)}"))
        if everyone.mention_everyone:
            issues.append((2, "@everyone can mention @everyone and @here"))
        if everyone.create_instant_invite:
            issues.append((1, "@everyone can create invites"))
        if guild.verification_level < discord.VerificationLevel.medium:
            issues.append((2, f"Discord verification level is {guild.verification_level.name}, raise it to medium or higher"))
        if guild.explicit_content_filter is discord.ContentFilter.disabled:
            issues.append((1, "Explicit media filter is off"))
        if guild.mfa_level is discord.MFALevel.disabled:
            issues.append((2, "2FA is not required for moderation actions, the owner can turn it on in server settings"))
        admins = [r for r in guild.roles if r.permissions.administrator and not r.managed and not r.is_default()]
        if len(admins) > 2:
            issues.append((2, f"{len(admins)} roles grant Administrator"))
        for role in admins:
            humans = [m for m in role.members if not m.bot]
            if len(humans) > 5:
                issues.append((2, f"{role.mention} grants Administrator to {len(humans)} members"))
        for role in guild.roles:
            if role.is_default() or role.managed:
                continue
            if me and role >= me.top_role and security.dangerous_permissions(role.permissions):
                issues.append((2, f"{role.mention} has dangerous permissions and sits above Soward, so it cannot be controlled"))
        bots = [m for m in guild.members if m.bot and m.id != guild.me.id and m.guild_permissions.administrator]
        if bots:
            issues.append((2, f"{len(bots)} bots hold Administrator: {', '.join(b.mention for b in bots[:8])}"))
        if me and not me.guild_permissions.administrator:
            needed = [p for p in ("ban_members", "kick_members", "manage_roles", "manage_channels", "view_audit_log", "manage_guild", "manage_webhooks", "moderate_members") if not getattr(me.guild_permissions, p)]
            if needed:
                issues.append((3, f"Soward is missing permissions: {', '.join(needed)}"))
        if me and guild.roles and me.top_role.position < max(r.position for r in guild.roles) - 3:
            issues.append((1, "Move Soward's role higher so it can act on more roles"))
        if not await settings.get(guild.id, "antinuke", "enabled"):
            issues.append((3, "AntiNuke is off"))
        if not await settings.get(guild.id, "antiraid", "enabled"):
            issues.append((2, "AntiRaid is off"))
        if not await settings.get(guild.id, "automod", "enabled"):
            issues.append((1, "AutoMod is off"))
        if not await settings.get(guild.id, "verification", "level"):
            issues.append((1, "Verification is off"))
        if await settings.get(guild.id, "antinuke", "admin_bypass"):
            issues.append((2, "Administrator bypass is on, a hacked admin account would not be stopped"))
        qrole = await security._quarantine_role(guild)
        if qrole is None:
            issues.append((1, "No quarantine role is set, flagged members are timed out instead"))
        elif qrole.permissions.value:
            issues.append((2, f"{qrole.mention} should have no permissions"))
        if not await settings.get(guild.id, "security", "log_channel_id"):
            issues.append((1, "No security log channel is set"))
        if not await db.raw_fetchone("SELECT 1 FROM security_backups WHERE guild_id=?", (guild.id,)):
            issues.append((1, "No backup exists, run `backup create`"))
        if not await settings.get(guild.id, "security", "lock"):
            issues.append((2, "Tier lock is off, any Administrator can change security settings"))
        score = max(0, 100 - sum({1: 3, 2: 7, 3: 14}[s] for s, _ in issues))
        names = {3: "Critical", 2: "Warning", 1: "Advice"}
        issues.sort(key=lambda item: -item[0])
        lines = [f"**Score: {score}/100**"]
        lines += [f"**{names[sev]}** · {text}" for sev, text in issues] or ["No problems found."]
        await chunked(ctx, f"{e('shield')} Security Check", lines)


async def setup(bot: commands.Bot):
    await bot.add_cog(Lockdown(bot))
