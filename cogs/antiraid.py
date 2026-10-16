import datetime
import time
from collections import defaultdict, deque
from typing import Optional

import discord
from discord.ext import commands, tasks

import re

from utils import db, emoji_manager, guild_settings, security, threat
from utils import security_settings as settings
from utils import security_cmds
from utils.checks import has_guild_permission
from utils.converters import format_duration
from utils.security_access import security_owner, security_staff
from utils.events_bus import (
    ANTIRAID_JOIN_FLAGGED,
    ANTIRAID_RAID_MODE_STARTED,
    ANTIRAID_RAID_MODE_ENDED,
    ANTINUKE_INCIDENT,
    PANIC_MODE_STARTED,
    LOG_EVENT,
    bus,
)
import config

_join_windows: dict[int, deque] = defaultdict(lambda: deque(maxlen=250))
RAID_ACTION_CHOICES = ("kick", "ban", "timeout", "quarantine")
ACTION_RANK = {"none": 0, "timeout": 1, "quarantine": 2, "kick": 3, "ban": 4}
AD_NAME_PATTERN = re.compile(r"discord\.gg|discord\.com/invite|https?://|www\.|\.gg/|\.com/|free\s*nitro|nitro\s*gift", re.IGNORECASE)

class AntiRaid(commands.Cog):
    category = "Config"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.raid_mode_expiry_checker.start()
        bus.subscribe(ANTINUKE_INCIDENT, self._on_antinuke_incident)
        bus.subscribe(PANIC_MODE_STARTED, self._on_panic_mode_started)

    def cog_unload(self):
        self.raid_mode_expiry_checker.cancel()

    async def _on_antinuke_incident(self, *, guild_id: int, **kwargs):
        guild = self.bot.get_guild(guild_id)
        if not guild or not await self._is_enabled(guild_id):
            return
        if not await settings.get(guild_id, "antiraid", "follow_antinuke"):
            return
        await self.start_raid_mode(guild, triggered_by="antinuke_incident")

    async def _on_panic_mode_started(self, *, guild_id: int, triggered_by: str = "unknown", **kwargs):
        if triggered_by.startswith("antiraid:"):
            return
        guild = self.bot.get_guild(guild_id)
        if guild and await self._is_enabled(guild_id) and not await self._is_raid_mode(guild_id):
            await self.start_raid_mode(guild, triggered_by=triggered_by)

    async def _is_enabled(self, guild_id: int) -> bool:
        return await settings.get(guild_id, "antiraid", "enabled")

    async def _is_raid_mode(self, guild_id: int) -> bool:
        row = await db.raw_fetchone("SELECT raid_mode FROM antiraid_state WHERE guild_id=?", (guild_id,))
        return bool(row["raid_mode"]) if row else False

    async def _name_hit(self, guild_id: int, member: discord.Member) -> Optional[str]:
        patterns: list = await settings.get(guild_id, "antiraid", "name_filter")
        names = [member.name.lower(), (member.display_name or "").lower(), (getattr(member, "global_name", None) or "").lower()]
        for pattern in patterns:
            needle = str(pattern).lower().strip()
            if needle and any(needle in name for name in names):
                return needle
        return None

    def _suspicion_points(self, member: discord.Member) -> int:
        points = 0
        age_days = (time.time() - member.created_at.timestamp()) / 86400
        if age_days < 3:
            points += 2
        elif age_days < 7:
            points += 1
        if member.avatar is None:
            points += 1
        name = member.name
        if len(re.findall(r"\d", name)) >= 5 or re.search(r"\d{4,}$", name):
            points += 1
        digits = sum(c.isdigit() for c in name)
        if name and digits / len(name) > 0.4:
            points += 1
        public_flags = getattr(member, "public_flags", None)
        if age_days < 30 and public_flags is not None and not any(True for _, on in public_flags if on):
            points += 1
        if getattr(member, "global_name", None) is None and age_days < 14:
            points += 1
        return points

    async def _gate_action(self, guild_id: int, key: str) -> str:
        value = await settings.get(guild_id, "antiraid", f"{key}_action")
        if value == "default":
            return await settings.get(guild_id, "antiraid", "join_action")
        return value

    async def _evaluate_join(self, member: discord.Member) -> list[tuple[str, str]]:
        gid = member.guild.id
        found: list[tuple[str, str]] = []
        age_seconds = time.time() - member.created_at.timestamp()
        min_age = await settings.get(gid, "antiraid", "min_age_seconds")
        if await settings.get(gid, "antiraid", "gate_age_enabled") and min_age and age_seconds < min_age:
            found.append((f"account too new ({age_seconds / 3600:.1f}h old, minimum {min_age // 3600}h)", await self._gate_action(gid, "gate_age")))
        if await settings.get(gid, "antiraid", "gate_noavatar_enabled") and member.avatar is None:
            found.append(("no avatar", await self._gate_action(gid, "gate_noavatar")))
        if await settings.get(gid, "antiraid", "gate_name_enabled"):
            names = f"{member.name} {member.display_name or ''} {getattr(member, 'global_name', None) or ''}"
            if AD_NAME_PATTERN.search(names):
                found.append(("advertising name", await self._gate_action(gid, "gate_name")))
        hit = await self._name_hit(gid, member)
        if hit:
            found.append((f"name matches blocked pattern `{hit}`", await self._gate_action(gid, "name_filter")))
        if await settings.get(gid, "antiraid", "gate_suspicious_enabled"):
            needed = await settings.get(gid, "antiraid", "gate_suspicious_score")
            points = self._suspicion_points(member)
            if points >= needed:
                found.append((f"suspicious account (score {points})", await self._gate_action(gid, "gate_suspicious")))
        return found

    async def _notify_member(self, member: discord.Member, action: str, reason: str):
        gid = member.guild.id
        if not await settings.get(gid, "antiraid", "action_dm") or action == "none":
            return
        text = f"You were {'banned from' if action == 'ban' else 'removed from'} **{member.guild.name}** by its raid protection: {reason}."
        if await settings.get(gid, "antiraid", "gate_age_dm") and "account too new" in reason:
            minimum = await settings.get(gid, "antiraid", "min_age_seconds")
            text += f" Accounts must be at least {minimum // 86400} day(s) old to join."
        try:
            await member.send(text)
        except discord.HTTPException:
            pass

    async def _take_action(self, guild: discord.Guild, member: discord.Member, action: str, reason: str):
        await self._notify_member(member, action, reason)
        try:
            if action == "ban":
                await guild.ban(member, reason=f"AntiRaid: {reason}", delete_message_days=1)
            elif action == "kick":
                await member.kick(reason=f"AntiRaid: {reason}")
            elif action == "timeout":
                seconds = await settings.get(guild.id, "antiraid", "timeout_duration")
                until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
                await member.timeout(until, reason=f"AntiRaid: {reason}")
            elif action == "quarantine":
                await security.quarantine_member(guild, member, f"AntiRaid: {reason}", track_escalation=False)
        except discord.HTTPException:
            pass

        await db.raw_execute(
            "INSERT INTO raid_join_log (guild_id, user_id, joined_at, account_created_at, had_avatar, flagged, action_taken)"
            " VALUES (?, ?, ?, ?, ?, 1, ?)",
            (guild.id, member.id, time.time(), member.created_at.timestamp(), int(member.avatar is not None), action),
        )
        await threat.add(guild.id, "raid_join", f"{member.id}: {reason}")
        await bus.publish(ANTIRAID_JOIN_FLAGGED, guild_id=guild.id, user_id=member.id, reason=reason, action=action)
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="antiraid_action", user_id=member.id, reason=reason, action_taken=action)

    async def start_raid_mode(self, guild: discord.Guild, triggered_by: str = "automatic"):
        if await self._is_raid_mode(guild.id):
            return

        duration = await settings.get(guild.id, "antiraid", "raid_mode_duration")
        expires_at = time.time() + duration

        await db.raw_execute(
            "INSERT INTO antiraid_state (guild_id, raid_mode, raid_mode_started_at, raid_mode_expires_at, triggered_by)"
            " VALUES (?, 1, ?, ?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET"
            " raid_mode=1, raid_mode_started_at=excluded.raid_mode_started_at,"
            " raid_mode_expires_at=excluded.raid_mode_expires_at, triggered_by=excluded.triggered_by",
            (guild.id, time.time(), expires_at, triggered_by),
        )

        if not await security.is_panic_mode_active(guild.id):
            await security.trigger_panic_mode(guild.id, triggered_by=f"antiraid:{triggered_by}", duration_seconds=duration)

        await self._raise_verification(guild)
        swept = await self._sweep_recent_joins(guild)
        await threat.add(guild.id, "raid_mode", triggered_by)
        if await settings.get(guild.id, "security", "lockdown_on_raid"):
            lockdown = self.bot.get_cog("Lockdown")
            if lockdown is not None:
                await lockdown.start(guild, f"raid:{triggered_by}", None)

        await bus.publish(ANTIRAID_RAID_MODE_STARTED, guild_id=guild.id, triggered_by=triggered_by)
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="antiraid_raid_mode", active=True, triggered_by=triggered_by)

        alert_channel_id = await guild_settings.get(guild.id, "antiraid_alert_channel_id")
        if not alert_channel_id:
            alert_channel_id = await guild_settings.get(guild.id, "log_channel_id")
        if alert_channel_id:
            channel = guild.get_channel(int(alert_channel_id))
            if channel:
                e = emoji_manager.get
                try:
                    container = discord.ui.Container(accent_color=0xED4245)
                    container.add_item(discord.ui.TextDisplay(
                        f"## {e('panic')} Raid mode activated\n"
                        f"**Triggered by:** `{triggered_by}`\n"
                        f"**Duration:** {duration // 60}m\n"
                        f"**Auto-expires:** <t:{int(expires_at)}:R>\n"
                        f"**Swept recent joins:** {swept}\n\n"
                        "All new joins are now being scrutinized. Flagged members will be actioned automatically."
                    ))
                    view = discord.ui.LayoutView(timeout=None)
                    view.add_item(container)
                    await channel.send(view=view)
                except discord.HTTPException:
                    pass

    async def _raise_verification(self, guild: discord.Guild):
        if not await settings.get(guild.id, "antiraid", "raise_verification"):
            return
        if guild.me is None or not guild.me.guild_permissions.manage_guild:
            return
        if guild.verification_level >= discord.VerificationLevel.high:
            return
        await guild_settings.set(guild.id, "antiraid_prev_verification_level", guild.verification_level.value)
        try:
            await guild.edit(verification_level=discord.VerificationLevel.high, reason="AntiRaid: raid mode raised the verification level")
        except discord.HTTPException:
            await guild_settings.delete(guild.id, "antiraid_prev_verification_level")

    async def _restore_verification(self, guild: discord.Guild):
        previous = await guild_settings.get(guild.id, "antiraid_prev_verification_level")
        if previous is None:
            return
        await guild_settings.delete(guild.id, "antiraid_prev_verification_level")
        try:
            await guild.edit(verification_level=discord.VerificationLevel(int(previous)), reason="AntiRaid: raid mode ended")
        except (discord.HTTPException, ValueError):
            pass

    async def _sweep_recent_joins(self, guild: discord.Guild) -> int:
        if not await settings.get(guild.id, "antiraid", "sweep"):
            return 0
        window = await settings.get(guild.id, "antiraid", "join_velocity_window")
        action = await settings.get(guild.id, "antiraid", "raid_mode_action")
        now = time.time()
        swept = 0
        for joined_at, user_id, *_ in list(_join_windows[guild.id]):
            if now - joined_at > window * 2:
                continue
            member = guild.get_member(user_id)
            if member is None or member.bot or await security.is_exempt(guild.id, member, "antiraid"):
                continue
            await self._take_action(guild, member, action, "part of the join burst that started raid mode")
            swept += 1
        return swept

    async def end_raid_mode(self, guild: discord.Guild, ended_by: Optional[int] = None):
        await self._restore_verification(guild)
        await db.raw_execute(
            "UPDATE antiraid_state SET raid_mode=0, raid_mode_expires_at=NULL WHERE guild_id=?",
            (guild.id,),
        )
        if await security.is_panic_mode_active(guild.id):
            await security.end_panic_mode(guild.id, ended_by=str(ended_by) if ended_by else "antiraid")
        await bus.publish(ANTIRAID_RAID_MODE_ENDED, guild_id=guild.id, ended_by=ended_by)
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="antiraid_raid_mode", active=False, ended_by=ended_by)

    @tasks.loop(seconds=30)
    async def raid_mode_expiry_checker(self):
        now = time.time()
        rows = await db.raw_fetch(
            "SELECT guild_id FROM antiraid_state WHERE raid_mode=1 AND raid_mode_expires_at IS NOT NULL AND raid_mode_expires_at <= ?",
            (now,),
        )
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if guild:
                await self.end_raid_mode(guild)
        await db.raw_execute(
            "DELETE FROM raid_join_log WHERE joined_at < ?",
            (now - config.ANTIRAID_LOG_RETENTION_SECONDS,),
        )

    @raid_mode_expiry_checker.before_loop
    async def _before_raid_mode_expiry_checker(self):
        await self.bot.wait_until_ready()

    async def _log_clean_join(self, member: discord.Member):
        await db.raw_execute(
            "INSERT INTO raid_join_log (guild_id, user_id, joined_at, account_created_at, had_avatar, flagged)"
            " VALUES (?, ?, ?, ?, ?, 0)",
            (member.guild.id, member.id, time.time(), member.created_at.timestamp(), int(member.avatar is not None)),
        )

    async def _handle_bot_join(self, member: discord.Member):
        gid = member.guild.id
        if not await settings.get(gid, "antiraid", "gate_unverified_bots"):
            return
        flags = getattr(member, "public_flags", None)
        if flags is not None and getattr(flags, "verified_bot", False):
            return
        if await security.is_trusted(gid, member):
            return
        action = await settings.get(gid, "antiraid", "gate_unverified_bots_action")
        await self._take_action(member.guild, member, action, "unverified bot")

    def _cluster_hit(self, member: discord.Member, window: deque, spread: int, id_count: int, similar_count: int, check_ids: bool, check_names: bool) -> Optional[str]:
        created = member.created_at.timestamp()
        key = re.sub(r"\d+", "", member.name.lower())[:12]
        id_matches = 1
        name_matches = 1
        now = time.time()
        for joined_at, user_id, created_at, name_key in window:
            if user_id == member.id or now - joined_at > 600:
                continue
            if abs(created_at - created) <= spread:
                id_matches += 1
            if len(key) >= 3 and name_key == key:
                name_matches += 1
        if check_ids and id_matches >= id_count:
            return f"{id_matches} accounts created within {format_duration(spread)} of each other joined"
        if check_names and name_matches >= similar_count:
            return f"{name_matches} accounts with the name pattern `{key}` joined"
        return None

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = member.guild.id
        if not await self._is_enabled(guild_id):
            if not member.bot:
                await self._log_clean_join(member)
            return
        if member.bot:
            return await self._handle_bot_join(member)

        velocity_count = await settings.get(guild_id, "antiraid", "join_velocity_count")
        velocity_window = await settings.get(guild_id, "antiraid", "join_velocity_window")

        now = time.time()
        window = _join_windows[guild_id]
        recent_joins = 1 + sum(1 for t, *_ in window if now - t < velocity_window)
        in_raid_mode = await self._is_raid_mode(guild_id)

        trigger = None
        if not in_raid_mode:
            if recent_joins >= velocity_count:
                trigger = "join_velocity"
            else:
                cluster = self._cluster_hit(
                    member, window,
                    await settings.get(guild_id, "antiraid", "id_window"),
                    await settings.get(guild_id, "antiraid", "id_count"),
                    await settings.get(guild_id, "antiraid", "similar_count"),
                    bool(await settings.get(guild_id, "antiraid", "id_cluster")),
                    bool(await settings.get(guild_id, "antiraid", "similar_names")),
                )
                if cluster:
                    trigger = f"pattern:{cluster}"
        if trigger:
            await self.start_raid_mode(member.guild, triggered_by=trigger)
            in_raid_mode = True
        window.append((now, member.id, member.created_at.timestamp(), re.sub(r"\d+", "", member.name.lower())[:12]))

        findings = await self._evaluate_join(member)
        exempt = (in_raid_mode or findings) and await security.is_exempt(guild_id, member, "antiraid")
        if exempt:
            return await self._log_clean_join(member)

        action = "none"
        reasons = [reason for reason, _ in findings]
        for _, candidate in findings:
            if ACTION_RANK.get(candidate, 0) > ACTION_RANK.get(action, 0):
                action = candidate
        if in_raid_mode:
            target = await settings.get(guild_id, "antiraid", "raid_target")
            if target == "all" or findings:
                raid_action = await settings.get(guild_id, "antiraid", "raid_mode_action")
                if ACTION_RANK.get(raid_action, 0) > ACTION_RANK.get(action, 0):
                    action = raid_action
                if not reasons:
                    reasons = ["active raid mode"]
        if reasons:
            await self._take_action(member.guild, member, action, ", ".join(reasons))
        else:
            await self._log_clean_join(member)

    @commands.group(name="antiraid", aliases=["raid"], invoke_without_command=True, help='View or configure AntiRaid join protection.')
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def antiraid_group(self, ctx: commands.Context):
        from utils.security_panels import AntiRaidOverviewLayout
        view = await AntiRaidOverviewLayout.create(ctx.author.id, ctx.guild.id)
        await ctx.send(view=view)

    @antiraid_group.command(name="settings", aliases=["config", "options"], help="List every antiraid setting and its current value. Usage: settings [group|all]")
    @has_guild_permission("administrator")
    async def ar_cfg_settings(self, ctx: commands.Context, group: Optional[str] = None):
        await security_cmds.show_settings(ctx, "antiraid", group)

    @antiraid_group.command(name="get", help="Show one antiraid setting with its default. Usage: get <key>")
    @has_guild_permission("administrator")
    async def ar_cfg_get(self, ctx: commands.Context, key: str):
        await security_cmds.get_setting(ctx, "antiraid", key)

    @antiraid_group.command(name="set", help="Change an AntiRaid setting. Usage: set <key> <value>")
    @security_staff()
    async def ar_cfg_set(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.set_setting(ctx, "antiraid", key, value)

    @antiraid_group.command(name="reset", help="Reset one antiraid setting, or `all`, to its default. Usage: reset <key|all>")
    @security_owner()
    async def ar_cfg_reset(self, ctx: commands.Context, key: str):
        await security_cmds.reset_setting(ctx, "antiraid", key)

    @antiraid_group.command(name="add", help="Add an entry to an AntiRaid list setting. Usage: add <key> <value>")
    @security_staff()
    async def ar_cfg_add(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.list_edit(ctx, "antiraid", key, value, True)

    @antiraid_group.command(name="remove", help="Remove an entry from an AntiRaid list setting. Usage: remove <key> <value>")
    @security_staff()
    async def ar_cfg_remove(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.list_edit(ctx, "antiraid", key, value, False)

    @antiraid_group.command(name="list", help="Show the entries of an AntiRaid list setting. Usage: list <key>")
    @has_guild_permission("administrator")
    async def ar_cfg_list(self, ctx: commands.Context, key: str):
        await security_cmds.show_list(ctx, "antiraid", key)

    @antiraid_group.command(name="enable", help='Enable AntiRaid protection.')
    @security_staff()
    async def ar_enable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antiraid_enabled", True)
        await ctx.send(view=success_layout(f"{e('check')} AntiRaid enabled", "AntiRaid protection is now active."))

    @antiraid_group.command(name="disable", help='Disable AntiRaid protection.')
    @security_owner()
    async def ar_disable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antiraid_enabled", False)
        await ctx.send(view=success_layout(f"{e('check')} AntiRaid disabled", "AntiRaid protection is now disabled."))

    @antiraid_group.command(name="minage", help='Set the minimum account age in days for new joins.')
    @security_staff()
    async def ar_minage(self, ctx: commands.Context, days: int):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if not 0 <= days <= 365:
            return await ctx.send(view=error_layout("Invalid age", "Choose a number of days between 0 and 365."))
        await guild_settings.set(ctx.guild.id, "antiraid_min_age_seconds", days * 86400)
        await ctx.send(view=success_layout(f"{e('check')} Minimum age set", f"New accounts younger than **{days}d** will be flagged on join."))

    @antiraid_group.command(name="velocity", help='Set the join velocity trigger (count within window seconds).')
    @security_staff()
    async def ar_velocity(self, ctx: commands.Context, count: int, window_seconds: int = 10):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if not 2 <= count <= 200 or not 2 <= window_seconds <= 300:
            return await ctx.send(view=error_layout("Invalid velocity", "Joins must be 2-200 and the window 2-300 seconds."))
        await guild_settings.set(ctx.guild.id, "antiraid_join_velocity_count", count)
        await guild_settings.set(ctx.guild.id, "antiraid_join_velocity_window", window_seconds)
        await ctx.send(view=success_layout(f"{e('check')} Join velocity set", f"Raid mode triggers after **{count}** joins in **{window_seconds}s**."))

    @antiraid_group.command(name="action", help='Set the default action taken on flagged joins: kick, ban, timeout or quarantine.')
    @security_staff()
    async def ar_action(self, ctx: commands.Context, action: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        action = action.lower()
        if action not in RAID_ACTION_CHOICES:
            return await ctx.send(view=error_layout("Invalid action", f"Choose from {', '.join(f'`{a}`' for a in RAID_ACTION_CHOICES)}."))
        await guild_settings.set(ctx.guild.id, "antiraid_join_action", action)
        await ctx.send(view=success_layout(f"{e('check')} Action set", f"Flagged joins will be `{action}`ed."))

    @antiraid_group.command(name="raidaction", help="Set what happens to every join while raid mode is active: kick, ban, timeout or quarantine.")
    @security_staff()
    async def ar_raidaction(self, ctx: commands.Context, action: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        action = action.lower()
        if action not in RAID_ACTION_CHOICES:
            return await ctx.send(view=error_layout("Invalid action", "Choose from `kick`, `ban`, or `timeout`."))
        await guild_settings.set(ctx.guild.id, "antiraid_raid_mode_action", action)
        await ctx.send(view=success_layout(f"{e('check')} Raid action set", f"Joins during raid mode will be handled with `{action}`."))

    async def _toggle_setting(self, ctx: commands.Context, key: str, toggle: bool, title: str, on_text: str, off_text: str):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, key, toggle)
        await ctx.send(view=success_layout(f"{e('check')} {title} {'enabled' if toggle else 'disabled'}", on_text if toggle else off_text))

    @antiraid_group.command(name="sweep", help="Toggle actioning the burst of joins that started a raid.")
    @security_staff()
    async def ar_sweep(self, ctx: commands.Context, toggle: bool):
        await self._toggle_setting(
            ctx, "antiraid_sweep", toggle, "Raid sweep",
            "The accounts that joined in the burst that triggered raid mode are actioned too.",
            "Only joins after raid mode starts are actioned.",
        )

    @antiraid_group.command(name="raiseverification", aliases=["lockverify"], help="Toggle raising the server verification level during raid mode.")
    @security_staff()
    async def ar_raiseverification(self, ctx: commands.Context, toggle: bool):
        await self._toggle_setting(
            ctx, "antiraid_raise_verification", toggle, "Verification boost",
            "Discord's verification level is raised to High during raid mode and restored afterwards. Needs Manage Server.",
            "The server verification level is left alone during raid mode.",
        )

    @antiraid_group.command(name="follownuke", help="Toggle starting raid mode when AntiNuke detects an attack.")
    @security_staff()
    async def ar_follownuke(self, ctx: commands.Context, toggle: bool):
        await self._toggle_setting(
            ctx, "antiraid_follow_antinuke", toggle, "AntiNuke link",
            "An AntiNuke detection also starts raid mode.",
            "AntiNuke detections no longer start raid mode.",
        )

    @antiraid_group.command(name="namefilter", aliases=["names"], help="Flag joins whose username contains a pattern. Usage: namefilter <add|remove|list> [text]")
    @security_staff()
    async def ar_namefilter(self, ctx: commands.Context, action: str, *, text: Optional[str] = None):
        from utils.components import error_layout, info_layout, success_layout
        e = emoji_manager.get
        action = action.lower()
        current: list = await guild_settings.get(ctx.guild.id, "antiraid_name_filter", [])
        if action == "list":
            body = "\n".join(f"`{p}`" for p in current) or "No patterns set."
            return await ctx.send(view=info_layout(f"{e('antiraid')} Name filter", body))
        if action not in ("add", "remove") or not text:
            return await ctx.send(view=error_layout("Invalid usage", "Use `namefilter add <text>`, `namefilter remove <text>` or `namefilter list`."))
        needle = text.lower().strip()
        if action == "add":
            if len(needle) < 3 or len(needle) > 40:
                return await ctx.send(view=error_layout("Invalid pattern", "Patterns must be 3-40 characters."))
            if len(current) >= 50:
                return await ctx.send(view=error_layout("Too many patterns", "A server can have up to 50 patterns."))
            if needle not in current:
                current.append(needle)
            await guild_settings.set(ctx.guild.id, "antiraid_name_filter", current)
            return await ctx.send(view=success_layout(f"{e('check')} Pattern added", f"Joins with `{needle}` in their username will be flagged."))
        if needle not in current:
            return await ctx.send(view=error_layout("Not found", f"`{needle}` is not in the name filter."))
        current.remove(needle)
        await guild_settings.set(ctx.guild.id, "antiraid_name_filter", current)
        await ctx.send(view=success_layout(f"{e('check')} Pattern removed", f"`{needle}` removed from the name filter."))

    @antiraid_group.command(name="noavatar", aliases=["avatar"], help="Toggle flagging accounts with no avatar set (default profile picture).")
    @security_staff()
    async def ar_avatar(self, ctx: commands.Context, toggle: bool):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antiraid_gate_noavatar_enabled", toggle)
        state = "will" if toggle else "will not"
        await ctx.send(view=success_layout(f"{e('check')} Avatar filter updated", f"Accounts with no avatar {state} be flagged on join."))

    @antiraid_group.command(name="alertchannel", help='Set the channel for raid mode alerts.')
    @security_staff()
    async def ar_alertchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antiraid_alert_channel_id", channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Alert channel set", f"AntiRaid alerts will go to {channel.mention}."))

    @antiraid_group.command(name="raidmode", help='Manually toggle raid mode on or off.')
    @security_staff()
    @commands.guild_only()
    async def ar_raidmode(self, ctx: commands.Context):
        from utils.components import info_layout, success_layout
        e = emoji_manager.get
        if await self._is_raid_mode(ctx.guild.id):
            await self.end_raid_mode(ctx.guild, ended_by=ctx.author.id)
            await ctx.send(view=success_layout(f"{e('check')} Raid mode deactivated", "Server is back to normal join processing."))
        else:
            await self.start_raid_mode(ctx.guild, triggered_by=f"manual:{ctx.author.id}")
            await ctx.send(view=info_layout(f"{e('panic')} Raid mode activated", "All incoming joins will now be scrutinized and actioned."))

    @antiraid_group.command(name="status", help="View the current raid mode / panic mode state and what triggered it.")
    @commands.guild_only()
    async def ar_status(self, ctx: commands.Context):
        from utils.components import info_layout
        e = emoji_manager.get

        state_row = await db.raw_fetchone("SELECT * FROM antiraid_state WHERE guild_id=?", (ctx.guild.id,))
        panic_active = await security.is_panic_mode_active(ctx.guild.id)

        if not state_row or not state_row["raid_mode"]:
            body = f"**Raid mode:** Inactive\n**Server-wide panic mode:** {'Active' if panic_active else 'Inactive'}"
            if panic_active:
                body += "\n\n-# Panic mode is active from another security system (AutoMod or AntiNuke) even though AntiRaid's own raid mode isn't engaged."
            return await ctx.send(view=info_layout(f"{e('antiraid')} Raid Status", body))

        expires = state_row["raid_mode_expires_at"]
        body = (
            f"**Raid mode:** Active\n"
            f"**Triggered by:** `{state_row['triggered_by']}`\n"
            f"**Started:** <t:{int(state_row['raid_mode_started_at'])}:R>\n"
            f"**Auto-expires:** {'<t:' + str(int(expires)) + ':R>' if expires else 'Manual only'}\n"
            f"**Server-wide panic mode:** {'Active (shared with AutoMod/AntiNuke)' if panic_active else 'Inactive'}"
        )
        await ctx.send(view=info_layout(f"{e('panic')} Raid Status", body))

    @antiraid_group.command(name="logs", help='View recent flagged join events.')
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def ar_logs(self, ctx: commands.Context):
        from utils.components import info_layout
        e = emoji_manager.get
        rows = await db.raw_fetch(
            "SELECT user_id, action_taken, joined_at FROM raid_join_log"
            " WHERE guild_id=? AND flagged=1 ORDER BY joined_at DESC LIMIT 15",
            (ctx.guild.id,),
        )
        if not rows:
            return await ctx.send(view=info_layout(f"{e('antiraid')} No flagged joins", "No flagged join events logged for this server."))
        lines = [f"<@{r['user_id']}> — `{r['action_taken'] or 'no action'}` — <t:{int(r['joined_at'])}:R>" for r in rows]
        await ctx.send(view=info_layout(f"{e('antiraid')} Flagged join log", "\n".join(lines)))

async def setup(bot: commands.Bot):
    await bot.add_cog(AntiRaid(bot))
