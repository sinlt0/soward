import time
import uuid
from collections import defaultdict
from typing import Optional

import discord
from discord.ext import commands

from utils import db, emoji_manager, guild_settings, incident, security
from utils.checks import has_guild_permission
from utils.events_bus import (
    ANTINUKE_INCIDENT,
    ANTINUKE_QUARANTINED,
    ANTINUKE_RELEASED,
    ANTINUKE_TRIGGERED,
    AUTOMOD_VIOLATION,
    AUTOROLE_STRIP,
    LOG_EVENT,
    bus,
)
import config

_action_log: dict[tuple, list[float]] = defaultdict(list)

ACTION_LABELS = {
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

def _track(guild_id: int, action: str, actor_id: int, window: int) -> int:
    key = (guild_id, action, actor_id)
    now = time.time()
    _action_log[key] = [t for t in _action_log[key] if now - t < window]
    _action_log[key].append(now)
    return len(_action_log[key])

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

    async def _is_trusted(self, guild_id: int, actor_id: int) -> bool:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return False
        member = guild.get_member(actor_id)
        if not member:
            return actor_id in config.ALL_PRIVILEGED_IDS
        return await security.is_trusted(guild_id, member)

    async def _get_threshold(self, guild_id: int, action: str) -> int:
        return await guild_settings.get(
            guild_id,
            f"antinuke_threshold_{action}",
            config.ANTINUKE_DEFAULT_THRESHOLDS.get(action, 3),
        )

    async def _get_punishment(self, guild_id: int) -> str:
        return await guild_settings.get(guild_id, "antinuke_punishment", config.ANTINUKE_DEFAULT_PUNISHMENT)

    async def _is_enabled(self, guild_id: int) -> bool:
        return await guild_settings.get(guild_id, "antinuke_enabled", False)

    async def _is_strict_mode(self, guild_id: int) -> bool:
        return await guild_settings.get(guild_id, "antinuke_strict_mode", config.ANTINUKE_STRICT_MODE_DEFAULT)

    async def _watches_quarantined(self, guild_id: int) -> bool:
        return await guild_settings.get(guild_id, "antinuke_watch_quarantined", config.ANTINUKE_WATCH_QUARANTINED_DEFAULT)

    async def _punish_actor(self, guild: discord.Guild, actor: discord.Member, action: str, reason: str, count: int, threshold: int):
        punishment = await security.get_action_punishment(guild.id, action)
        detail = f"{ACTION_LABELS.get(action, action)} threshold exceeded ({count}/{threshold}) — {reason}"
        multiplier = await security.get_offense_multiplier(guild.id, actor.id)

        if punishment == "ban" or (punishment == "kick" and multiplier >= 3):
            try:
                await guild.ban(actor, reason=f"AntiNuke: {detail} (repeat offender x{multiplier})" if multiplier > 1 else f"AntiNuke: {detail}")
            except discord.HTTPException:
                pass
            punishment = "ban"
        elif punishment == "kick":
            try:
                await actor.kick(reason=f"AntiNuke: {detail}")
            except discord.HTTPException:
                pass
        elif punishment == "kick_bot" and actor.bot:
            try:
                await actor.kick(reason=f"AntiNuke: {detail}")
            except discord.HTTPException:
                pass
        elif punishment == "quarantine":
            await security.quarantine_member(guild, actor, f"AntiNuke: {detail}")
        else:
            await bus.publish(AUTOROLE_STRIP, guild_id=guild.id, user_id=actor.id, reason=f"AntiNuke: {detail}")

        await incident.escalate(guild.id, actor.id)

        log_id = str(uuid.uuid4())[:8].upper()
        await db.raw_execute(
            "INSERT INTO antinuke_log (log_id, guild_id, actor_id, action, detail, punishment, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (log_id, guild.id, actor.id, action, detail, punishment, time.time()),
        )

        await bus.publish(ANTINUKE_INCIDENT, guild_id=guild.id, actor_id=actor.id, reason=detail, punishment=punishment)
        await bus.publish(ANTINUKE_TRIGGERED, guild_id=guild.id, actor_id=actor.id, action=action, reason=detail, punishment=punishment)
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="antinuke_triggered", actor_id=actor.id, reason=detail, punishment=punishment)

    async def _check_action(self, guild: discord.Guild, actor_id: int, action: str, detail: str = "") -> bool:
        if await self._is_trusted(guild.id, actor_id):
            return False
        if not await self._is_enabled(guild.id):
            return False

        threshold = await self._get_threshold(guild.id, action)
        count = _track(guild.id, action, actor_id, config.ANTINUKE_THRESHOLD_WINDOW_SECONDS)

        if count >= threshold:
            member = guild.get_member(actor_id)
            if member:
                await self._punish_actor(guild, member, action, detail, count, threshold)
            return True
        return False

    async def _check_strict_permission_grant(self, guild: discord.Guild, actor_id: int, role: discord.Role):
        if not await self._is_strict_mode(guild.id):
            return
        if await self._is_trusted(guild.id, actor_id):
            return

        dangerous = any(getattr(role.permissions, perm, False) for perm in config.ANTINUKE_DANGEROUS_PERMISSIONS)
        if not dangerous:
            return

        member = guild.get_member(actor_id)
        if member:
            await self._punish_actor(guild, member, "permission_escalation", f"granted dangerous permission to @{role.name}", 1, 1)
            try:
                await role.edit(permissions=discord.Permissions.none(), reason="AntiNuke strict mode: reverted dangerous permission grant")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if not channel.guild.me.guild_permissions.view_audit_log:
            return
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_delete):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(channel.guild, entry.user.id, "channel_delete", f"#{channel.name}")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        if not channel.guild.me.guild_permissions.view_audit_log:
            return
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_create):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(channel.guild, entry.user.id, "channel_create", f"#{channel.name}")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        if not after.guild.me.guild_permissions.view_audit_log:
            return
        async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.channel_update):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(after.guild, entry.user.id, "channel_update", f"#{after.name}")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        if not role.guild.me.guild_permissions.view_audit_log:
            return
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_delete):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(role.guild, entry.user.id, "role_delete", f"@{role.name}")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        if not role.guild.me.guild_permissions.view_audit_log:
            return
        async for entry in role.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_create):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(role.guild, entry.user.id, "role_create", f"@{role.name}")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        if not after.guild.me.guild_permissions.view_audit_log:
            return
        if before.permissions != after.permissions:
            async for entry in after.guild.audit_logs(limit=1, action=discord.AuditLogAction.role_update):
                if entry.user and entry.user.id != self.bot.user.id:
                    await self._check_strict_permission_grant(after.guild, entry.user.id, after)
                    await self._check_action(after.guild, entry.user.id, "role_update", f"@{after.name} permissions changed")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if not guild.me.guild_permissions.view_audit_log:
            return
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.ban):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(guild, entry.user.id, "ban", str(user))

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        if await security.is_quarantined(guild.id, member.id):
            return
        if not guild.me.guild_permissions.view_audit_log:
            return

        if await self._watches_quarantined(guild.id):
            async for entry in guild.audit_logs(limit=3, action=discord.AuditLogAction.kick):
                if entry.target and entry.target.id == member.id and entry.user:
                    if entry.user.id != self.bot.user.id and await security.is_quarantined(guild.id, entry.target.id):
                        await self._check_action(guild, entry.user.id, "kick", f"interacted with quarantined member {member}")
                        return

        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
            if entry.target and entry.target.id == member.id and entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(guild, entry.user.id, "kick", str(member))

    @commands.Cog.listener()
    async def on_webhooks_update(self, channel: discord.abc.GuildChannel):
        if not channel.guild.me.guild_permissions.view_audit_log:
            return
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_create):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(channel.guild, entry.user.id, "webhook_create")
        async for entry in channel.guild.audit_logs(limit=1, action=discord.AuditLogAction.webhook_delete):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(channel.guild, entry.user.id, "webhook_delete")

    @commands.Cog.listener()
    async def on_guild_emojis_update(self, guild: discord.Guild, before, after):
        if not guild.me.guild_permissions.view_audit_log:
            return
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.emoji_create):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(guild, entry.user.id, "emoji_change", "emoji created")

    @commands.Cog.listener()
    async def on_guild_stickers_update(self, guild: discord.Guild, before, after):
        if not guild.me.guild_permissions.view_audit_log:
            return
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.sticker_create):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(guild, entry.user.id, "sticker_change", "sticker created")

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        if not after.me.guild_permissions.view_audit_log:
            return
        if before.icon != after.icon or before.name != after.name or before.vanity_url_code != after.vanity_url_code:
            async for entry in after.audit_logs(limit=1, action=discord.AuditLogAction.guild_update):
                if entry.user and entry.user.id != self.bot.user.id:
                    await self._check_action(after, entry.user.id, "guild_update", "server settings changed")

    @commands.Cog.listener()
    async def on_integration_update(self, integration: discord.Integration):
        guild = integration.guild
        if not guild or not guild.me.guild_permissions.view_audit_log:
            return
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.integration_update):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(guild, entry.user.id, "integration_change")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if not member.bot:
            return
        guild = member.guild
        if not guild.me.guild_permissions.view_audit_log:
            return
        async for entry in guild.audit_logs(limit=1, action=discord.AuditLogAction.bot_add):
            if entry.user and entry.user.id != self.bot.user.id:
                await self._check_action(guild, entry.user.id, "bot_add", str(member))

    @commands.group(name="antinuke", aliases=["an"], invoke_without_command=True, help='View or configure AntiNuke protection.')
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def antinuke_group(self, ctx: commands.Context):
        from utils.security_panels import AntiNukeOverviewLayout
        view = await AntiNukeOverviewLayout.create(self, ctx.author.id, ctx.guild.id)
        await ctx.send(view=view)

    @antinuke_group.command(name="enable", help='Enable AntiNuke protection.')
    @has_guild_permission("administrator")
    async def an_enable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antinuke_enabled", True)
        await ctx.send(view=success_layout(f"{e('check')} AntiNuke enabled", "AntiNuke protection is now active."))

    @antinuke_group.command(name="disable", help='Disable AntiNuke protection.')
    @has_guild_permission("administrator")
    async def an_disable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antinuke_enabled", False)
        await ctx.send(view=success_layout(f"{e('check')} AntiNuke disabled", "AntiNuke protection is now disabled."))

    @antinuke_group.command(name="strict", help='Toggle strict mode — punish any dangerous permission grant instantly.')
    @has_guild_permission("administrator")
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
    @has_guild_permission("administrator")
    async def an_punishment(self, ctx: commands.Context, punishment: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        valid = ("ban", "kick", "strip_roles", "quarantine")
        if punishment not in valid:
            return await ctx.send(view=error_layout("Invalid punishment", f"Choose from: {', '.join(f'`{v}`' for v in valid)}"))
        await guild_settings.set(ctx.guild.id, "antinuke_punishment", punishment)
        await ctx.send(view=success_layout(f"{e('check')} Punishment set", f"AntiNuke punishment set to `{punishment}`."))

    @antinuke_group.command(name="punishmentaction", aliases=["punishfor"], help="Set a punishment override for a specific action type (e.g. harsher for mass-ban than a single role edit).")
    @has_guild_permission("administrator")
    async def an_punishment_action(self, ctx: commands.Context, action: str, punishment: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        valid_punishments = ("ban", "kick", "kick_bot", "strip_roles", "quarantine")
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
    @has_guild_permission("administrator")
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

    @antinuke_group.command(name="threshold", help='Set the action threshold within the detection window.')
    @has_guild_permission("administrator")
    async def an_threshold(self, ctx: commands.Context, action: str, value: int):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if action not in config.ANTINUKE_DEFAULT_THRESHOLDS:
            return await ctx.send(view=error_layout("Invalid action", f"Valid actions: {', '.join(config.ANTINUKE_DEFAULT_THRESHOLDS.keys())}"))
        await guild_settings.set(ctx.guild.id, f"antinuke_threshold_{action}", max(1, value))
        await ctx.send(view=success_layout(f"{e('check')} Threshold updated", f"`{action}` threshold set to **{value}**."))

    @antinuke_group.command(name="quarantinerole", help='Set the role used to quarantine flagged members.')
    @has_guild_permission("administrator")
    async def an_quarantinerole(self, ctx: commands.Context, role: discord.Role):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antinuke_quarantine_role_id", role.id)
        await ctx.send(view=success_layout(
            f"{e('check')} Quarantine role set",
            f"{role.mention} will be used to quarantine flagged actors. Make sure this role has no permissions and is denied access everywhere.",
        ))

    @antinuke_group.command(name="trust", aliases=["whitelist"], help='Add or remove a trusted member who bypasses AntiNuke.')
    @has_guild_permission("administrator")
    async def an_trust(self, ctx: commands.Context, action: str, target: discord.Member):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if action == "add":
            await db.raw_execute(
                "INSERT OR IGNORE INTO antinuke_whitelist (guild_id, target_id, added_by) VALUES (?, ?, ?)",
                (ctx.guild.id, target.id, ctx.author.id),
            )
            await ctx.send(view=success_layout(f"{e('trust')} Trusted", f"{target.mention} is now trusted and bypasses AntiNuke entirely."))
        elif action == "remove":
            await db.raw_execute(
                "DELETE FROM antinuke_whitelist WHERE guild_id=? AND target_id=?",
                (ctx.guild.id, target.id),
            )
            await ctx.send(view=success_layout(f"{e('check')} Removed", f"{target.mention} removed from the trust list."))
        else:
            await ctx.send(view=error_layout("Invalid action", "Use `add` or `remove`."))

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

        body_lines = [f"**Server Owner:** <@{ctx.guild.owner_id}> (always full control, including quarantine release)"]
        body_lines.append(f"\n**Extra Owners** (`{len(extra_owners)}/{config.SECURITY_TIER_MAX_PER_TIER}`):")
        body_lines.append("\n".join(f"<@{r['user_id']}>" for r in extra_owners) or "None")
        body_lines.append(f"\n**Trusted Admins** (`{len(trusted_admins)}/{config.SECURITY_TIER_MAX_PER_TIER}`):")
        body_lines.append("\n".join(f"<@{r['user_id']}>" for r in trusted_admins) or "None")
        body_lines.append("\n-# Note: only the real server owner can release a quarantined member, regardless of tier.")

        await ctx.send(view=info_layout(f"{e('shield')} Permit Tiers", "\n".join(body_lines)))

    @antinuke_group.command(name="incident", help='View or change the server incident state.')
    @has_guild_permission("administrator")
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
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def quarantine_cmd(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Manually quarantined"):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        ok = await security.quarantine_member(ctx.guild, member, reason, by=ctx.author.id)
        if ok:
            await ctx.send(view=success_layout(f"{e('quarantine')} Quarantined", f"{member.mention} has been quarantined.\n**Reason:** {reason}"))
        else:
            await ctx.send(view=error_layout(f"{e('cross')} Already quarantined", f"{member.mention} is already quarantined."))

    @commands.command(name="release", help='Release a quarantined member and restore their roles. Only the real server owner can do this.')
    @commands.guild_only()
    async def release_cmd(self, ctx: commands.Context, member: discord.Member):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get

        if not await security.is_real_owner(ctx.guild, ctx.author.id):
            return await ctx.send(view=error_layout(
                f"{e('cross')} Owner Only",
                "Only the server owner can release a quarantined member — this is intentional and cannot be delegated, even to Extra Owners or administrators.",
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
