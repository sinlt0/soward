import asyncio
import time
import uuid
from collections import defaultdict
from typing import Optional

import discord
from discord.ext import commands

from utils import db, emoji_manager, guild_settings, incident, security, threat
from utils import security_settings as settings
from utils import security_whitelist as whitelist
from utils import security_cmds
from utils.checks import has_guild_permission
from utils.security_access import LEVEL_OWNER, LEVEL_TRUSTED, level_of, security_owner, security_staff
from utils.events_bus import (
    ANTINUKE_INCIDENT,
    ANTINUKE_TRIGGERED,
    AUTOMOD_VIOLATION,
    LOG_EVENT,
    bus,
)
import config

_action_log: dict[tuple, list[float]] = defaultdict(list)
_seen_entries: dict[int, dict[int, float]] = defaultdict(dict)
_recent_punish: dict[tuple, float] = {}
_created: dict[tuple, list[tuple]] = defaultdict(list)
_deleted: dict[tuple, list[tuple]] = defaultdict(list)
_enforcing: set[tuple] = set()
_audit_gate: dict[tuple, float] = {}

ACTION_LABELS = {
    "vanity_change": "Vanity URL change",
    "invite_delete": "Invite delete",
    "quarantine_touch": "Quarantine tampering",
    "protected_role": "Protected role change",
    "channel_permission": "Dangerous channel permission",
    "channel_delete": "Channel delete",
    "channel_create": "Channel create",
    "channel_update": "Channel update",
    "role_delete": "Role delete",
    "role_create": "Role create",
    "role_update": "Role update",
    "ban": "Ban",
    "kick": "Kick",
    "prune": "Member prune",
    "webhook_create": "Webhook create",
    "webhook_delete": "Webhook delete",
    "emoji_change": "Emoji change",
    "sticker_change": "Sticker change",
    "bot_add": "Bot add",
    "permission_escalation": "Permission escalation",
    "guild_update": "Server settings change",
    "integration_change": "Integration change",
}

OVERWRITE_DANGEROUS = ("manage_channels", "manage_roles", "manage_webhooks", "mention_everyone")
VALID_PUNISHMENTS = ("ban", "kick", "kick_bot", "strip_roles", "quarantine")


def _track(guild_id: int, action: str, actor_id: int, window: int) -> tuple[int, int]:
    key = (guild_id, action, actor_id)
    now = time.time()
    stamps = [t for t in _action_log[key] if now - t < 3600]
    stamps.append(now)
    _action_log[key] = stamps
    return sum(1 for t in stamps if now - t < window), len(stamps)


def _claim(guild_id: int, entry_id: int) -> bool:
    seen = _seen_entries[guild_id]
    now = time.time()
    if len(seen) > 500:
        for key in [k for k, v in seen.items() if now - v > 300]:
            del seen[key]
    if entry_id in seen:
        return False
    seen[entry_id] = now
    return True


def _remember(store: dict, guild_id: int, actor_id: int, item: tuple) -> None:
    now = time.time()
    key = (guild_id, actor_id)
    store[key] = [i for i in store[key] if now - i[-1] < 3600]
    store[key].append(item)


def _prune_memory() -> None:
    now = time.time()
    for key in [k for k, v in _action_log.items() if not v or now - v[-1] > 600]:
        del _action_log[key]
    for key in [k for k, v in _recent_punish.items() if now - v > 600]:
        del _recent_punish[key]
    for store in (_created, _deleted):
        for key in [k for k, v in store.items() if not v or now - v[-1][-1] > 3600]:
            del store[key]
    for key in [k for k, v in _audit_gate.items() if now - v > 60]:
        del _audit_gate[key]


class AntiNuke(commands.Cog):
    category = "Config"
    submodule = "Security"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bus.subscribe(AUTOMOD_VIOLATION, self._on_automod_violation)

    async def _on_automod_violation(self, *, guild_id: int, violation_type: str, incident_state: int, **kwargs):
        if violation_type in ("raid_join", "mass_mention", "spam") and incident_state >= config.INCIDENT_STATES["elevated"]:
            await incident.escalate(guild_id)
            await bus.publish(
                ANTINUKE_INCIDENT,
                guild_id=guild_id,
                trigger="automod_escalation",
                violation_type=violation_type,
            )

    async def _is_trusted(self, guild: discord.Guild, actor_id: int) -> bool:
        member = guild.get_member(actor_id)
        if member is None:
            return await security.is_trusted_id(guild.id, actor_id, guild.owner_id)
        return await security.is_trusted(guild.id, member)

    async def _get_threshold(self, guild_id: int, action: str) -> int:
        limit = int(await settings.get(guild_id, "antinuke", f"threshold_{action}"))
        if threat.is_beast(guild_id):
            return max(1, limit // 2)
        return limit

    async def _get_hourly(self, guild_id: int, action: str) -> int:
        return int(await settings.get(guild_id, "antinuke", f"hourly_{action}"))

    async def _action_enabled(self, guild_id: int, action: str) -> bool:
        return bool(await settings.get(guild_id, "antinuke", f"enabled_{action}"))

    async def _get_window(self, guild_id: int) -> int:
        return int(await settings.get(guild_id, "antinuke", "window"))

    async def _is_enabled(self, guild_id: int) -> bool:
        return await guild_settings.get(guild_id, "antinuke_enabled", False)

    async def _is_strict_mode(self, guild_id: int) -> bool:
        if threat.is_beast(guild_id):
            return True
        return bool(await settings.get(guild_id, "antinuke", "strict_mode"))

    async def _watches_quarantined(self, guild_id: int) -> bool:
        return bool(await settings.get(guild_id, "antinuke", "watch_quarantined"))

    async def _ready(self, guild: discord.Guild) -> bool:
        if guild.me is None or not guild.me.guild_permissions.view_audit_log:
            return False
        return await self._is_enabled(guild.id)

    async def _entries(self, guild: discord.Guild, action: discord.AuditLogAction, *, target_id: Optional[int] = None, limit: int = 6, retry: bool = True) -> list:
        max_age = config.ANTINUKE_AUDIT_MAX_AGE_SECONDS
        found = []
        for attempt in range(2 if retry else 1):
            if attempt:
                await asyncio.sleep(1.0)
            try:
                async for entry in guild.audit_logs(limit=limit, action=action):
                    if (discord.utils.utcnow() - entry.created_at).total_seconds() > max_age:
                        break
                    if target_id is not None and getattr(entry.target, "id", None) != target_id:
                        continue
                    if entry.user is None or entry.user.id == self.bot.user.id:
                        continue
                    if not _claim(guild.id, entry.id):
                        continue
                    found.append(entry)
            except discord.HTTPException:
                return found
            if found or target_id is None:
                break
        return found

    async def _fetch_actor(self, guild: discord.Guild, actor_id: int) -> Optional[discord.Member]:
        member = guild.get_member(actor_id)
        if member is not None:
            return member
        try:
            return await guild.fetch_member(actor_id)
        except discord.HTTPException:
            return None

    async def _apply_punishment(self, guild: discord.Guild, actor: discord.Member, punishment: str, reason: str) -> str:
        try:
            if punishment == "ban":
                await guild.ban(actor, reason=reason, delete_message_days=0)
                return "ban"
            if punishment == "kick" or (punishment == "kick_bot" and actor.bot):
                await actor.kick(reason=reason)
                return "kick"
            if punishment == "quarantine":
                await security.quarantine_member(guild, actor, reason)
                return "quarantine"
        except discord.HTTPException:
            pass
        if await security.strip_member(guild, actor, reason):
            return "strip_roles" if punishment in ("strip_roles", "kick_bot") else f"{punishment} (fell back to strip_roles)"
        return f"{punishment} (failed)"

    async def _punish_actor(self, guild: discord.Guild, actor_id: int, action: str, reason: str, count: int, threshold: int):
        key = (guild.id, actor_id)
        now = time.time()
        if now - _recent_punish.get(key, 0) < int(await settings.get(guild.id, "antinuke", "punish_cooldown")):
            return
        _recent_punish[key] = now
        if len(_recent_punish) > 200:
            _prune_memory()

        detail = f"{ACTION_LABELS.get(action, action)} threshold exceeded ({count}/{threshold}) — {reason}"
        punishment = await security.get_action_punishment(guild.id, action)
        multiplier = await security.get_offense_multiplier(guild.id, actor_id)
        if multiplier >= 3 and punishment in ("kick", "strip_roles", "quarantine"):
            punishment = "ban"
        audit_reason = f"AntiNuke: {detail}" + (f" (repeat offender x{multiplier})" if multiplier > 1 else "")

        actor = await self._fetch_actor(guild, actor_id)
        if actor is None:
            try:
                await guild.ban(discord.Object(id=actor_id), reason=audit_reason)
                applied = "ban"
            except discord.HTTPException:
                applied = "ban (failed)"
        else:
            applied = await self._apply_punishment(guild, actor, punishment, audit_reason)

        await self._rollback(guild, actor_id)
        await incident.escalate(guild.id, actor_id)
        await threat.add(guild.id, "antinuke", f"{action} by {actor_id}")
        if await settings.get(guild.id, "security", "lockdown_on_nuke"):
            lockdown = self.bot.get_cog("Lockdown")
            if lockdown is not None:
                await lockdown.start(guild, f"antinuke:{actor_id}", None)

        log_id = str(uuid.uuid4())[:8].upper()
        await db.raw_execute(
            "INSERT INTO antinuke_log (log_id, guild_id, actor_id, action, detail, punishment, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (log_id, guild.id, actor_id, action, detail, applied, time.time()),
        )

        await bus.publish(ANTINUKE_INCIDENT, guild_id=guild.id, actor_id=actor_id, reason=detail, punishment=applied)
        await bus.publish(ANTINUKE_TRIGGERED, guild_id=guild.id, actor_id=actor_id, action=action, reason=detail, punishment=applied)
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="antinuke_triggered", actor_id=actor_id, reason=detail, punishment=applied)
        await self._alert(guild, actor_id, action, detail, applied, log_id)

    async def _alert(self, guild: discord.Guild, actor_id: int, action: str, detail: str, applied: str, log_id: str):
        e = emoji_manager.get
        container = discord.ui.Container(accent_color=0xED4245)
        container.add_item(discord.ui.TextDisplay(
            f"## {e('panic')} AntiNuke triggered\n"
            f"**Actor:** <@{actor_id}> (`{actor_id}`)\n"
            f"**Trigger:** {ACTION_LABELS.get(action, action)}\n"
            f"**Detail:** {detail}\n"
            f"**Response:** `{applied}`\n"
            f"**Case:** `{log_id}`"
        ))
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(container)

        channel_id = None
        for module, key in (("antinuke", "alert_channel_id"), ("security", "alert_channel_id"), ("antiraid", "alert_channel_id"), ("security", "log_channel_id")):
            channel_id = await settings.get(guild.id, module, key)
            if channel_id:
                break
        if not channel_id:
            channel_id = await guild_settings.get(guild.id, "log_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if channel is not None:
            role_id = await settings.get(guild.id, "security", "alert_role_id")
            role = guild.get_role(int(role_id)) if role_id else None
            try:
                await channel.send(
                    content=role.mention if role else None, view=view,
                    allowed_mentions=discord.AllowedMentions(roles=[role]) if role else discord.AllowedMentions.none(),
                )
            except discord.HTTPException:
                pass

        if await settings.get(guild.id, "antinuke", "alert_owner") and await settings.get(guild.id, "security", "alert_owner"):
            owner = guild.owner
            if owner is None:
                try:
                    owner = await guild.fetch_member(guild.owner_id)
                except discord.HTTPException:
                    owner = None
            if owner is not None:
                dm = discord.ui.LayoutView(timeout=None)
                card = discord.ui.Container(accent_color=0xED4245)
                card.add_item(discord.ui.TextDisplay(
                    f"## {e('panic')} AntiNuke triggered in {guild.name}\n"
                    f"**Actor:** <@{actor_id}> (`{actor_id}`)\n"
                    f"**Trigger:** {ACTION_LABELS.get(action, action)}\n"
                    f"**Response:** `{applied}`\n"
                    f"**Case:** `{log_id}`"
                ))
                dm.add_item(card)
                try:
                    await owner.send(view=dm)
                except discord.HTTPException:
                    pass

    async def _rollback(self, guild: discord.Guild, actor_id: int):
        if not await settings.get(guild.id, "antinuke", "restore"):
            return
        key = (guild.id, actor_id)
        window = int(await settings.get(guild.id, "antinuke", "rollback_window"))
        now = time.time()
        created = [i for i in _created.pop(key, []) if now - i[-1] < window]
        deleted = [i for i in _deleted.pop(key, []) if now - i[-1] < window]

        for kind, object_id, _ in created:
            target = guild.get_channel(object_id) if kind == "channel" else guild.get_role(object_id)
            if target is None:
                continue
            try:
                await target.delete(reason="AntiNuke: rolled back an object created by a flagged member")
            except discord.HTTPException:
                pass

        deleted.sort(key=lambda i: (0 if i[0] == "role" else 1, getattr(i[1], "position", 0)))
        for kind, obj, _ in deleted:
            try:
                if kind == "channel":
                    clone = await obj.clone(reason="AntiNuke: restored a channel deleted by a flagged member")
                    try:
                        await clone.edit(position=obj.position)
                    except discord.HTTPException:
                        pass
                else:
                    restored = await guild.create_role(
                        name=obj.name, permissions=obj.permissions, colour=obj.colour,
                        hoist=obj.hoist, mentionable=obj.mentionable,
                        reason="AntiNuke: restored a role deleted by a flagged member",
                    )
                    try:
                        await restored.edit(position=obj.position)
                    except discord.HTTPException:
                        pass
            except discord.HTTPException:
                pass

    async def _rollback_if_punished(self, guild: discord.Guild, actor_id: int):
        cooldown = int(await settings.get(guild.id, "antinuke", "punish_cooldown"))
        if time.time() - _recent_punish.get((guild.id, actor_id), 0) < cooldown:
            await self._rollback(guild, actor_id)

    async def _check_action(self, guild: discord.Guild, actor_id: int, action: str, detail: str = "", *, immediate: bool = False) -> bool:
        if not await self._is_enabled(guild.id):
            return False
        if not await self._action_enabled(guild.id, action):
            return False
        watched = await security.is_quarantined(guild.id, actor_id) and await self._watches_quarantined(guild.id)
        if not watched and await self._is_trusted(guild, actor_id):
            return False

        window = await self._get_window(guild.id)
        short, hourly = _track(guild.id, action, actor_id, window)
        threshold = 1 if (immediate or watched) else await self._get_threshold(guild.id, action)
        hourly_limit = await self._get_hourly(guild.id, action)
        if short >= threshold:
            await self._punish_actor(guild, actor_id, action, detail, short, threshold)
            return True
        if hourly_limit and hourly >= hourly_limit:
            await self._punish_actor(guild, actor_id, action, f"{detail} (hourly limit)", hourly, hourly_limit)
            return True
        return False

    async def _process(self, guild: discord.Guild, action_type: discord.AuditLogAction, action: str, detail: str, *, target_id: Optional[int] = None, retry: bool = True) -> list:
        if not await self._ready(guild):
            return []
        results = []
        for entry in await self._entries(guild, action_type, target_id=target_id, retry=retry):
            triggered = await self._check_action(guild, entry.user.id, action, detail)
            results.append((entry, triggered))
        return results

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        for entry, _ in await self._process(guild, discord.AuditLogAction.channel_delete, "channel_delete", f"#{channel.name}", target_id=channel.id):
            _remember(_deleted, guild.id, entry.user.id, ("channel", channel, time.time()))
            await self._rollback_if_punished(guild, entry.user.id)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        for entry, _ in await self._process(guild, discord.AuditLogAction.channel_create, "channel_create", f"#{channel.name}", target_id=channel.id):
            _remember(_created, guild.id, entry.user.id, ("channel", channel.id, time.time()))
            await self._rollback_if_punished(guild, entry.user.id)

    async def _revert_overwrites(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> list[str]:
        default = after.guild.default_role
        old = before.overwrites_for(default)
        new = after.overwrites_for(default)
        gained = [p for p in OVERWRITE_DANGEROUS if getattr(new, p, None) is True and getattr(old, p, None) is not True]
        if gained:
            try:
                await after.set_permissions(default, overwrite=old, reason="AntiNuke: reverted a dangerous @everyone permission")
            except discord.HTTPException:
                pass
        return gained

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        guild = after.guild
        if not await self._ready(guild):
            return
        gained = []
        if await settings.get(guild.id, "antinuke", "monitor_overwrites"):
            default = guild.default_role
            old = before.overwrites_for(default)
            new = after.overwrites_for(default)
            gained = [p for p in OVERWRITE_DANGEROUS if getattr(new, p, None) is True and getattr(old, p, None) is not True]
        for entry in await self._entries(guild, discord.AuditLogAction.channel_update, target_id=after.id):
            actor_id = entry.user.id
            if gained and not (await self._is_trusted(guild, actor_id) and not await security.is_quarantined(guild.id, actor_id)):
                await self._check_action(guild, actor_id, "channel_permission", f"gave @everyone {', '.join(gained)} in #{after.name}", immediate=True)
                await self._revert_overwrites(before, after)
            await self._check_action(guild, actor_id, "channel_update", f"#{after.name}")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        guild = role.guild
        for entry, _ in await self._process(guild, discord.AuditLogAction.role_delete, "role_delete", f"@{role.name}", target_id=role.id):
            _remember(_deleted, guild.id, entry.user.id, ("role", role, time.time()))
            await self._rollback_if_punished(guild, entry.user.id)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        guild = role.guild
        for entry, _ in await self._process(guild, discord.AuditLogAction.role_create, "role_create", f"@{role.name}", target_id=role.id):
            _remember(_created, guild.id, entry.user.id, ("role", role.id, time.time()))
            await self._rollback_if_punished(guild, entry.user.id)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if before.permissions == after.permissions:
            return
        guild = after.guild
        if not await self._ready(guild):
            return
        added = [p for p in config.ANTINUKE_DANGEROUS_PERMISSIONS if getattr(after.permissions, p, False) and not getattr(before.permissions, p, False)]
        strict = await self._is_strict_mode(guild.id)
        public = after.is_default() and bool(await settings.get(guild.id, "antinuke", "protect_everyone"))
        for entry in await self._entries(guild, discord.AuditLogAction.role_update, target_id=after.id):
            actor_id = entry.user.id
            if await self._is_trusted(guild, actor_id) and not await security.is_quarantined(guild.id, actor_id):
                continue
            if added:
                triggered = await self._check_action(guild, actor_id, "permission_escalation", f"granted {', '.join(added)} to @{after.name}", immediate=strict or public)
                if triggered or strict or public:
                    try:
                        await after.edit(permissions=before.permissions, reason="AntiNuke: reverted a dangerous permission grant")
                    except discord.HTTPException:
                        pass
            await self._check_action(guild, actor_id, "role_update", f"@{after.name} permissions changed")

    async def _may_touch_quarantine(self, guild: discord.Guild, actor_id: int) -> bool:
        if actor_id == guild.owner_id or actor_id in config.ALL_PRIVILEGED_IDS:
            return True
        if await security.get_permit_tier(guild.id, actor_id) == config.SECURITY_TIER_EXTRA_OWNER:
            return True
        member = guild.get_member(actor_id)
        if member is not None:
            return await whitelist.is_whitelisted(guild.id, ("quarantine",), member)
        return actor_id in await whitelist.user_ids_for(guild.id, "quarantine")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        before_ids = {r.id for r in before.roles}
        after_ids = {r.id for r in after.roles}
        if before_ids == after_ids:
            return
        guild = after.guild
        key = (guild.id, after.id)
        if await security.is_quarantined(guild.id, after.id):
            if key in _enforcing:
                return
            _enforcing.add(key)
            try:
                if await self._ready(guild) and await settings.get(guild.id, "antinuke", "quarantine_hold"):
                    for entry in await self._entries(guild, discord.AuditLogAction.member_role_update, target_id=after.id):
                        if await self._may_touch_quarantine(guild, entry.user.id):
                            continue
                        await self._check_action(guild, entry.user.id, "quarantine_touch", f"changed the roles of quarantined member {after}", immediate=True)
                await security.enforce_quarantine(guild, after, "Quarantine: roles are locked until released")
            finally:
                _enforcing.discard(key)
            return
        if not await self._ready(guild):
            return
        changed_ids = before_ids ^ after_ids
        protected = {int(r) for r in await settings.get(guild.id, "security", "protected_roles")}
        touched = [guild.get_role(i) for i in changed_ids & protected]
        touched = [r for r in touched if r is not None]
        added_dangerous = [r for r in after.roles if r.id in after_ids - before_ids and not r.managed and security.dangerous_permissions(r.permissions)]
        if not touched and not added_dangerous:
            return
        strict = await self._is_strict_mode(guild.id)
        for entry in await self._entries(guild, discord.AuditLogAction.member_role_update, target_id=after.id):
            actor_id = entry.user.id
            if await self._is_trusted(guild, actor_id) and not await security.is_quarantined(guild.id, actor_id):
                continue
            if touched:
                names = ", ".join(f"@{r.name}" for r in touched)
                await self._check_action(guild, actor_id, "protected_role", f"changed protected roles ({names}) on {after}", immediate=True)
                regained = [r for r in touched if r.id in before_ids and r.id not in after_ids]
                removed = [r for r in touched if r.id not in before_ids and r.id in after_ids]
                try:
                    if regained:
                        await after.add_roles(*regained, reason="AntiNuke: restored a protected role")
                    if removed:
                        await after.remove_roles(*removed, reason="AntiNuke: removed a protected role given by an untrusted member")
                except discord.HTTPException:
                    pass
            if added_dangerous:
                names = ", ".join(f"@{r.name}" for r in added_dangerous)
                triggered = await self._check_action(guild, actor_id, "permission_escalation", f"gave {names} to {after}", immediate=strict)
                if triggered or strict:
                    try:
                        await after.remove_roles(*added_dangerous, reason="AntiNuke: reverted a dangerous role grant")
                    except discord.HTTPException:
                        pass

    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        guild_ref = getattr(invite, "guild", None)
        guild = self.bot.get_guild(guild_ref.id) if guild_ref is not None else None
        if guild is None:
            return
        await self._process(guild, discord.AuditLogAction.invite_delete, "invite_delete", f"invite {getattr(invite, 'code', '')}", retry=False)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        await self._process(guild, discord.AuditLogAction.ban, "ban", str(user), target_id=user.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        if not await self._ready(guild):
            return
        await self._process(guild, discord.AuditLogAction.kick, "kick", str(member), target_id=member.id, retry=False)
        now = time.time()
        if now - _audit_gate.get((guild.id, "prune"), 0) < 3:
            return
        _audit_gate[(guild.id, "prune")] = now
        for entry in await self._entries(guild, discord.AuditLogAction.member_prune, retry=False, limit=3):
            removed = getattr(entry.extra, "members_removed", 0) or 0
            await self._check_action(guild, entry.user.id, "prune", f"pruned {removed} members")

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        guild = channel.guild
        if not await self._ready(guild):
            return
        for action_type, action in ((discord.AuditLogAction.webhook_create, "webhook_create"), (discord.AuditLogAction.webhook_delete, "webhook_delete")):
            for entry in await self._entries(guild, action_type, retry=False):
                triggered = await self._check_action(guild, entry.user.id, action, f"#{channel.name}")
                if triggered and action == "webhook_create":
                    try:
                        for hook in await channel.webhooks():
                            if hook.user is not None and hook.user.id == entry.user.id:
                                await hook.delete(reason="AntiNuke: removed a webhook created by a flagged member")
                    except (discord.HTTPException, AttributeError):
                        pass

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        for action_type in (discord.AuditLogAction.emoji_create, discord.AuditLogAction.emoji_delete, discord.AuditLogAction.emoji_update):
            await self._process(guild, action_type, "emoji_change", "emoji changed", retry=False)

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before, after):
        for action_type in (discord.AuditLogAction.sticker_create, discord.AuditLogAction.sticker_delete, discord.AuditLogAction.sticker_update):
            await self._process(guild, action_type, "sticker_change", "sticker changed", retry=False)

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        watched = ("name", "icon", "verification_level", "explicit_content_filter", "mfa_level", "banner", "splash")
        changed = [attr for attr in watched if getattr(before, attr, None) != getattr(after, attr, None)]
        vanity = before.vanity_url_code != after.vanity_url_code
        if not changed and not vanity:
            return
        if not await self._ready(after):
            return
        for entry in await self._entries(after, discord.AuditLogAction.guild_update):
            triggered = False
            if vanity:
                triggered = await self._check_action(after, entry.user.id, "vanity_change", "vanity URL changed", immediate=True) or triggered
            if changed:
                triggered = await self._check_action(after, entry.user.id, "guild_update", f"changed {', '.join(changed)}") or triggered
            if triggered and changed:
                try:
                    await after.edit(
                        name=before.name,
                        verification_level=before.verification_level,
                        explicit_content_filter=before.explicit_content_filter,
                        reason="AntiNuke: reverted a server change by a flagged member",
                    )
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_guild_integrations_update(self, guild: discord.Guild):
        for action_type in (discord.AuditLogAction.integration_create, discord.AuditLogAction.integration_update, discord.AuditLogAction.integration_delete):
            await self._process(guild, action_type, "integration_change", "integration changed", retry=False)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if await security.is_quarantined(guild.id, member.id):
            await security.enforce_quarantine(guild, member, "Quarantine: still active after rejoining")
            return
        if not member.bot or not await self._ready(guild):
            return
        block = await settings.get(guild.id, "antinuke", "bot_add_block")
        for entry in await self._entries(guild, discord.AuditLogAction.bot_add, target_id=member.id):
            actor_id = entry.user.id
            actor_trusted = await self._is_trusted(guild, actor_id) and not await security.is_quarantined(guild.id, actor_id)
            await self._check_action(guild, actor_id, "bot_add", str(member))
            if block and not actor_trusted and not await security.is_trusted(guild.id, member):
                try:
                    await member.kick(reason="AntiNuke: bot added by an untrusted member")
                except discord.HTTPException:
                    pass

    @commands.group(name="antinuke", aliases=["an"], invoke_without_command=True, help='View or configure AntiNuke protection.')
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def antinuke_group(self, ctx: commands.Context):
        from utils.security_panels import AntiNukeOverviewLayout
        view = await AntiNukeOverviewLayout.create(self, ctx.author.id, ctx.guild.id)
        await ctx.send(view=view)

    @antinuke_group.command(name="settings", aliases=["config", "options"], help="List every antinuke setting and its current value. Usage: settings [group|all]")
    @has_guild_permission("administrator")
    async def an_cfg_settings(self, ctx: commands.Context, group: Optional[str] = None):
        await security_cmds.show_settings(ctx, "antinuke", group)

    @antinuke_group.command(name="get", help="Show one antinuke setting with its default. Usage: get <key>")
    @has_guild_permission("administrator")
    async def an_cfg_get(self, ctx: commands.Context, key: str):
        await security_cmds.get_setting(ctx, "antinuke", key)

    @antinuke_group.command(name="set", help="Change an AntiNuke setting. Usage: set <key> <value>")
    @security_staff()
    async def an_cfg_set(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.set_setting(ctx, "antinuke", key, value)

    @antinuke_group.command(name="reset", help="Reset one antinuke setting, or `all`, to its default. Usage: reset <key|all>")
    @security_owner()
    async def an_cfg_reset(self, ctx: commands.Context, key: str):
        await security_cmds.reset_setting(ctx, "antinuke", key)

    @antinuke_group.command(name="add", help="Add an entry to an AntiNuke list setting. Usage: add <key> <value>")
    @security_staff()
    async def an_cfg_add(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.list_edit(ctx, "antinuke", key, value, True)

    @antinuke_group.command(name="remove", help="Remove an entry from an AntiNuke list setting. Usage: remove <key> <value>")
    @security_staff()
    async def an_cfg_remove(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.list_edit(ctx, "antinuke", key, value, False)

    @antinuke_group.command(name="list", help="Show the entries of an AntiNuke list setting. Usage: list <key>")
    @has_guild_permission("administrator")
    async def an_cfg_list(self, ctx: commands.Context, key: str):
        await security_cmds.show_list(ctx, "antinuke", key)

    @antinuke_group.command(name="enable", help='Enable AntiNuke protection.')
    @security_owner()
    async def an_enable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antinuke_enabled", True)
        await ctx.send(view=success_layout(f"{e('check')} AntiNuke enabled", "AntiNuke protection is now active."))

    @antinuke_group.command(name="disable", help='Disable AntiNuke protection.')
    @security_owner()
    async def an_disable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antinuke_enabled", False)
        await ctx.send(view=success_layout(f"{e('check')} AntiNuke disabled", "AntiNuke protection is now disabled."))

    @antinuke_group.command(name="strict", help='Toggle strict mode — punish any dangerous permission grant instantly.')
    @security_staff()
    async def an_strict(self, ctx: commands.Context, toggle: bool):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antinuke_strict_mode", toggle)
        state = "enabled" if toggle else "disabled"
        await ctx.send(view=success_layout(
            f"{e('check')} Strict mode {state}",
            f"Strict mode is now {state}. While enabled, granting a dangerous permission to any role is punished immediately, regardless of threshold.",
        ))

    @antinuke_group.command(name="punishment", help='Set the punishment: ban, kick, strip_roles, or quarantine.')
    @security_staff()
    async def an_punishment(self, ctx: commands.Context, punishment: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        valid = ("ban", "kick", "strip_roles", "quarantine")
        if punishment not in valid:
            return await ctx.send(view=error_layout("Invalid punishment", f"Choose from: {', '.join(f'`{v}`' for v in valid)}"))
        await guild_settings.set(ctx.guild.id, "antinuke_punishment", punishment)
        await ctx.send(view=success_layout(f"{e('check')} Punishment set", f"AntiNuke punishment set to `{punishment}`."))

    @antinuke_group.command(name="punishmentaction", aliases=["punishfor"], help="Set a punishment override for a specific action type (e.g. harsher for mass-ban than a single role edit).")
    @security_staff()
    async def an_punishment_action(self, ctx: commands.Context, action: str, punishment: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        valid_punishments = VALID_PUNISHMENTS
        if action not in ACTION_LABELS and action not in config.ANTINUKE_PER_ACTION_PUNISHMENT_DEFAULT:
            return await ctx.send(view=error_layout("Invalid action", f"Valid actions: {', '.join(ACTION_LABELS.keys())}"))
        if punishment not in valid_punishments:
            return await ctx.send(view=error_layout("Invalid punishment", f"Choose from: {', '.join(f'`{v}`' for v in valid_punishments)}"))

        await security.set_action_punishment(ctx.guild.id, action, punishment)
        await ctx.send(view=success_layout(
            f"{e('check')} Action Punishment Set",
            f"`{ACTION_LABELS.get(action, action)}` will now trigger `{punishment}` (overriding the general punishment setting).",
        ))

    @antinuke_group.command(name="removepunishmentaction", help="Remove a per-action punishment override, reverting to the general setting.")
    @security_staff()
    async def an_remove_punishment_action(self, ctx: commands.Context, action: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        removed = await security.clear_action_punishment(ctx.guild.id, action)
        if removed:
            await ctx.send(view=success_layout(f"{e('check')} Override Removed", f"`{ACTION_LABELS.get(action, action)}` now uses the general punishment setting."))
        else:
            await ctx.send(view=error_layout("Not Found", f"No override configured for `{action}`."))

    @antinuke_group.command(name="punishmentactions", aliases=["listpunishments"], help="List all per-action punishment overrides for this server.")
    async def an_list_punishment_actions(self, ctx: commands.Context):
        from utils.components import info_layout
        e = emoji_manager.get
        rows = await db.raw_fetch("SELECT * FROM antinuke_action_punishments WHERE guild_id=?", (ctx.guild.id,))
        if not rows:
            defaults = "\n".join(f"`{ACTION_LABELS.get(k, k)}` → `{v}` (default)" for k, v in config.ANTINUKE_PER_ACTION_PUNISHMENT_DEFAULT.items())
            return await ctx.send(view=info_layout(f"{e('shield')} Punishment Overrides", f"No custom overrides set. Defaults:\n{defaults}"))
        lines = [f"`{ACTION_LABELS.get(r['action_type'], r['action_type'])}` → `{r['punishment']}`" for r in rows]
        await ctx.send(view=info_layout(f"{e('shield')} Punishment Overrides", "\n".join(lines)))

    @antinuke_group.command(name="threshold", help="Set how many of an action are allowed inside the short window.")
    @security_staff()
    async def an_threshold(self, ctx: commands.Context, action: str, value: int):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if action not in config.ANTINUKE_DEFAULT_THRESHOLDS:
            return await ctx.send(view=error_layout("Invalid action", f"Valid actions: {', '.join(config.ANTINUKE_DEFAULT_THRESHOLDS.keys())}"))
        await guild_settings.set(ctx.guild.id, f"antinuke_threshold_{action}", max(1, min(100, value)))
        await ctx.send(view=success_layout(f"{e('check')} Limit updated", f"`{action}` limit set to **{max(1, min(100, value))}**."))

    @antinuke_group.command(name="hourly", help="Set how many of an action are allowed per hour. 0 turns the hourly limit off.")
    @security_staff()
    async def an_hourly(self, ctx: commands.Context, action: str, value: int):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if action not in config.ANTINUKE_DEFAULT_THRESHOLDS:
            return await ctx.send(view=error_layout("Invalid action", f"Valid actions: {', '.join(config.ANTINUKE_DEFAULT_THRESHOLDS.keys())}"))
        value = max(0, min(1000, value))
        await guild_settings.set(ctx.guild.id, f"antinuke_hourly_{action}", value)
        await ctx.send(view=success_layout(f"{e('check')} Hourly limit updated", f"`{action}` hourly limit is **{value or 'off'}**."))

    @antinuke_group.command(name="limits", help="Show the short and hourly limit of every monitored action.")
    @security_staff()
    async def an_limits(self, ctx: commands.Context):
        from utils.components import info_layout
        e = emoji_manager.get
        lines = []
        for name, default in config.ANTINUKE_DEFAULT_THRESHOLDS.items():
            short = await guild_settings.get(ctx.guild.id, f"antinuke_threshold_{name}", default)
            hourly = await guild_settings.get(ctx.guild.id, f"antinuke_hourly_{name}", 0)
            lines.append(f"`{name}` · {short} per window · {hourly or 'no'} per hour")
        await ctx.send(view=info_layout(f"{e('shield')} AntiNuke Limits", "\n".join(lines)))

    @antinuke_group.command(name="quarantinerole", help='Set the role used to quarantine flagged members.')
    @security_staff()
    async def an_quarantinerole(self, ctx: commands.Context, role: discord.Role):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antinuke_quarantine_role_id", role.id)
        await ctx.send(view=success_layout(
            f"{e('check')} Quarantine role set",
            f"{role.mention} will be used to quarantine flagged actors. Make sure this role has no permissions and is denied access everywhere.",
        ))

    @antinuke_group.command(name="trust", aliases=["whitelist"], help="Add or remove a trusted member who bypasses AntiNuke.")
    @security_owner()
    async def an_trust(self, ctx: commands.Context, action: str, target: discord.Member):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if action == "add":
            await security.add_trusted(ctx.guild.id, target.id, ctx.author.id)
            await ctx.send(view=success_layout(f"{e('trust')} Trusted", f"{target.mention} now bypasses AntiNuke."))
        elif action == "remove":
            await security.remove_trusted(ctx.guild.id, target.id)
            await ctx.send(view=success_layout(f"{e('check')} Removed", f"{target.mention} removed from the trust list."))
        else:
            await ctx.send(view=error_layout("Invalid action", "Use `add` or `remove`."))

    async def _toggle_setting(self, ctx: commands.Context, key: str, toggle: bool, title: str, on_text: str, off_text: str):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, key, toggle)
        await ctx.send(view=success_layout(f"{e('check')} {title} {'enabled' if toggle else 'disabled'}", on_text if toggle else off_text))

    @antinuke_group.command(name="window", help="Set how many seconds actions are counted over for thresholds (3-120).")
    @security_staff()
    async def an_window(self, ctx: commands.Context, seconds: int):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if not 3 <= seconds <= 120:
            return await ctx.send(view=error_layout("Invalid window", "Choose a value between 3 and 120 seconds."))
        await guild_settings.set(ctx.guild.id, "antinuke_window", seconds)
        await ctx.send(view=success_layout(f"{e('check')} Window updated", f"Actions are now counted over **{seconds}s**."))

    @antinuke_group.command(name="restore", help="Toggle automatic restore of channels and roles a flagged member deleted, and rollback of what they created.")
    @security_staff()
    async def an_restore(self, ctx: commands.Context, toggle: bool):
        await self._toggle_setting(
            ctx, "antinuke_restore", toggle, "Auto restore",
            "Channels and roles deleted by a flagged member are recreated, and objects they created are removed.",
            "Flagged members' changes are no longer rolled back.",
        )

    @antinuke_group.command(name="adminbypass", help="Toggle whether members with Administrator skip AntiNuke without being trusted. Off is safest.")
    @security_owner()
    async def an_adminbypass(self, ctx: commands.Context, toggle: bool):
        await self._toggle_setting(
            ctx, "antinuke_admin_bypass", toggle, "Administrator bypass",
            "Members with Administrator now skip AntiNuke. A compromised admin account will not be stopped.",
            "Only the owner, Extra Owners, Trusted Admins and trusted members skip AntiNuke. Everyone else is monitored, administrators included.",
        )

    @antinuke_group.command(name="botblock", help="Toggle kicking bots added by untrusted members.")
    @security_staff()
    async def an_botblock(self, ctx: commands.Context, toggle: bool):
        await self._toggle_setting(
            ctx, "antinuke_bot_add_block", toggle, "Bot add block",
            "Bots added by untrusted members are kicked right away. Trust a bot first to allow it.",
            "Bots added by untrusted members are only counted, not removed.",
        )

    @antinuke_group.command(name="ownerdm", help="Toggle direct message alerts to the server owner when AntiNuke triggers.")
    @security_staff()
    async def an_ownerdm(self, ctx: commands.Context, toggle: bool):
        await self._toggle_setting(
            ctx, "antinuke_alert_owner", toggle, "Owner alerts",
            "The server owner receives a direct message whenever AntiNuke acts.",
            "The server owner no longer receives direct messages from AntiNuke.",
        )

    @antinuke_group.command(name="alertchannel", help="Set the channel AntiNuke alerts are posted in.")
    @security_staff()
    async def an_alertchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antinuke_alert_channel_id", channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Alert channel set", f"AntiNuke alerts will be posted in {channel.mention}."))

    @antinuke_group.command(name="trusted", aliases=["trustlist"], help="List trusted members who bypass AntiNuke.")
    @has_guild_permission("administrator")
    async def an_trusted(self, ctx: commands.Context):
        from utils.components import info_layout
        e = emoji_manager.get
        rows = await security.list_trusted(ctx.guild.id)
        bypass = await guild_settings.get(ctx.guild.id, "antinuke_admin_bypass", config.ANTINUKE_ADMIN_BYPASS_DEFAULT)
        body = "\n".join(f"<@{r['target_id']}>" for r in rows) or "No trusted members."
        body += f"\n\n-# Administrator bypass is **{'on' if bypass else 'off'}**."
        await ctx.send(view=info_layout(f"{e('trust')} Trusted members", body))

    @antinuke_group.command(name="logs", aliases=["cases"], help="View recent AntiNuke detections.")
    @has_guild_permission("administrator")
    async def an_logs(self, ctx: commands.Context):
        from utils.components import info_layout
        e = emoji_manager.get
        rows = await db.raw_fetch(
            "SELECT log_id, actor_id, action, punishment, created_at FROM antinuke_log WHERE guild_id=? ORDER BY created_at DESC LIMIT 10",
            (ctx.guild.id,),
        )
        if not rows:
            return await ctx.send(view=info_layout(f"{e('shield')} AntiNuke log", "Nothing has been detected yet."))
        lines = [
            f"`{r['log_id']}` <@{r['actor_id']}> — {ACTION_LABELS.get(r['action'], r['action'])} → `{r['punishment']}` — <t:{int(r['created_at'])}:R>"
            for r in rows
        ]
        await ctx.send(view=info_layout(f"{e('shield')} AntiNuke log", "\n".join(lines)))

    @commands.command(name="extraowner", aliases=["eo"], help="Grant or revoke Extra Owner — full control, second only to the real server owner. Only the server owner can manage this tier.")
    @commands.guild_only()
    async def extraowner_cmd(self, ctx: commands.Context, action: str, target: discord.Member):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        action = action.lower()

        if action == "add":
            ok, message = await security.grant_permit_tier(ctx.guild, ctx.author.id, target.id, config.SECURITY_TIER_EXTRA_OWNER)
        elif action == "remove":
            ok, message = await security.revoke_permit_tier(ctx.guild, ctx.author.id, target.id)
        else:
            return await ctx.send(view=error_layout("Invalid action", "Use `add` or `remove`."))

        if ok:
            await ctx.send(view=success_layout(f"{e('crown')} Extra Owner", f"{target.mention} — {message}"))
        else:
            await ctx.send(view=error_layout("Not Allowed", message))

    @commands.command(name="trustedadmin", aliases=["ta"], help="Grant or revoke Trusted Admin — can manage basic security settings. The owner or an Extra Owner can manage this tier.")
    @commands.guild_only()
    async def trustedadmin_cmd(self, ctx: commands.Context, action: str, target: discord.Member):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        action = action.lower()

        if action == "add":
            ok, message = await security.grant_permit_tier(ctx.guild, ctx.author.id, target.id, config.SECURITY_TIER_TRUSTED_ADMIN)
        elif action == "remove":
            ok, message = await security.revoke_permit_tier(ctx.guild, ctx.author.id, target.id)
        else:
            return await ctx.send(view=error_layout("Invalid action", "Use `add` or `remove`."))

        if ok:
            await ctx.send(view=success_layout(f"{e('shield')} Trusted Admin", f"{target.mention} — {message}"))
        else:
            await ctx.send(view=error_layout("Not Allowed", message))

    @commands.command(name="permits", aliases=["securitytiers"], help="List every Extra Owner and Trusted Admin in this server.")
    @commands.guild_only()
    async def permits_cmd(self, ctx: commands.Context):
        from utils.components import info_layout
        e = emoji_manager.get
        rows = await security.list_permit_tiers(ctx.guild.id)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('shield')} Permit Tiers", "No Extra Owners or Trusted Admins configured.\nOnly the server owner can grant these — see `extraowner add @member` and `trustedadmin add @member`."))

        extra_owners = [r for r in rows if r["tier"] == config.SECURITY_TIER_EXTRA_OWNER]
        trusted_admins = [r for r in rows if r["tier"] == config.SECURITY_TIER_TRUSTED_ADMIN]

        body_lines = [f"**Server Owner:** <@{ctx.guild.owner_id}> (always full control)"]
        body_lines.append(f"\n**Extra Owners** (`{len(extra_owners)}/{config.SECURITY_TIER_MAX_PER_TIER}`):")
        body_lines.append("\n".join(f"<@{r['user_id']}>" for r in extra_owners) or "None")
        body_lines.append(f"\n**Trusted Admins** (`{len(trusted_admins)}/{config.SECURITY_TIER_MAX_PER_TIER}`):")
        body_lines.append("\n".join(f"<@{r['user_id']}>" for r in trusted_admins) or "None")
        body_lines.append("\n-# The server owner and Extra Owners can release quarantined members. Trusted Admins cannot.")

        await ctx.send(view=info_layout(f"{e('shield')} Permit Tiers", "\n".join(body_lines)))

    @antinuke_group.command(name="incident", help='View or change the server incident state.')
    @security_staff()
    async def an_incident(self, ctx: commands.Context, action: str):
        from utils.components import error_layout, info_layout, success_layout
        e = emoji_manager.get
        current = await incident.get_state(ctx.guild.id)
        state_names = {v: k for k, v in config.INCIDENT_STATES.items()}

        if action == "reset":
            await incident.reset(ctx.guild.id, ctx.author.id)
            await ctx.send(view=success_layout(f"{e('normal')} Incident reset", "Server incident state reset to **normal**."))
        elif action == "elevate":
            new = await incident.escalate(ctx.guild.id, ctx.author.id)
            await ctx.send(view=info_layout(f"{e('elevated')} State escalated", f"Incident state is now **{state_names.get(new, new)}**."))
        elif action == "status":
            await ctx.send(view=info_layout(f"{e('incident')} Incident state", f"Current state: **{state_names.get(current, current)}**"))
        else:
            await ctx.send(view=error_layout("Invalid action", "Use `reset`, `elevate`, or `status`."))

    @commands.command(name="quarantine", help='Quarantine a member, stripping their roles.')
    @security_staff()
    @commands.guild_only()
    async def quarantine_cmd(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Manually quarantined"):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        actor_level = await level_of(ctx.guild, ctx.author)
        blocked = None
        if member.id == ctx.author.id or member.id == ctx.guild.me.id or member.id == ctx.guild.owner_id:
            blocked = "That member cannot be quarantined."
        elif member.id in config.ALL_PRIVILEGED_IDS or await level_of(ctx.guild, member) >= max(actor_level, LEVEL_TRUSTED):
            blocked = "You cannot quarantine someone at or above your security tier."
        elif ctx.author.id != ctx.guild.owner_id and member.top_role >= ctx.author.top_role:
            blocked = "You cannot quarantine someone with a higher or equal role."
        elif member.top_role >= ctx.guild.me.top_role:
            blocked = "Their top role is at or above mine, so I cannot strip their roles."
        if blocked:
            return await ctx.send(view=error_layout(f"{e('cross')} Not Allowed", blocked))
        ok = await security.quarantine_member(ctx.guild, member, reason, by=ctx.author.id)
        if ok:
            await ctx.send(view=success_layout(f"{e('quarantine')} Quarantined", f"{member.mention} has been quarantined.\n**Reason:** {reason}"))
        else:
            await ctx.send(view=error_layout(f"{e('cross')} Already quarantined", f"{member.mention} is already quarantined."))

    @commands.command(name="release", help='Release a quarantined member and restore their roles. Server owner and Extra Owners only.')
    @commands.guild_only()
    async def release_cmd(self, ctx: commands.Context, member: discord.Member):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get

        if await level_of(ctx.guild, ctx.author) < LEVEL_OWNER:
            return await ctx.send(view=error_layout(
                f"{e('cross')} Owner Only",
                "Only the server owner or an Extra Owner can release a quarantined member.",
            ))
        if member.id == ctx.author.id or await security.is_quarantined(ctx.guild.id, ctx.author.id):
            return await ctx.send(view=error_layout(
                f"{e('cross')} Not Allowed",
                "You cannot release yourself, and quarantined members cannot release anyone.",
            ))

        ok = await security.release_member(ctx.guild, member.id, by=ctx.author.id)
        if ok:
            await ctx.send(view=success_layout(f"{e('check')} Released", f"{member.mention} has been released from quarantine and had their roles restored."))
        else:
            await ctx.send(view=error_layout(f"{e('cross')} Not quarantined", f"{member.mention} is not currently quarantined."))

    @commands.command(name="quarantinelist", aliases=["qlist"], help='List all currently quarantined members.')
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def quarantine_list(self, ctx: commands.Context):
        from utils.components import info_layout
        e = emoji_manager.get
        rows = await db.raw_fetch(
            "SELECT user_id, reason, quarantined_at FROM quarantine WHERE guild_id=? AND released_at IS NULL",
            (ctx.guild.id,),
        )
        if not rows:
            return await ctx.send(view=info_layout(f"{e('quarantine')} Quarantine list", "No members are currently quarantined."))
        lines = [f"<@{r['user_id']}> — {r['reason'] or 'No reason'} — <t:{int(r['quarantined_at'])}:R>" for r in rows]
        await ctx.send(view=info_layout(f"{e('quarantine')} Quarantine list", "\n".join(lines)))

async def setup(bot: commands.Bot):
    await bot.add_cog(AntiNuke(bot))
