import asyncio
import datetime
import time
from collections import defaultdict, deque
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import db, emoji_manager, guild_settings, security
from utils.checks import has_guild_permission
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

_join_windows: dict[int, deque] = defaultdict(lambda: deque(maxlen=200))

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
        if guild and await self._is_enabled(guild_id):
            await self.start_raid_mode(guild, triggered_by="antinuke_incident")

    async def _on_panic_mode_started(self, *, guild_id: int, triggered_by: str = "unknown", **kwargs):
        if triggered_by.startswith("antiraid:"):
            return
        guild = self.bot.get_guild(guild_id)
        if guild and await self._is_enabled(guild_id) and not await self._is_raid_mode(guild_id):
            await self.start_raid_mode(guild, triggered_by=triggered_by)

    async def _is_enabled(self, guild_id: int) -> bool:
        return await guild_settings.get(guild_id, "antiraid_enabled", config.ANTIRAID_ENABLED_DEFAULT)

    async def _is_raid_mode(self, guild_id: int) -> bool:
        row = await db.raw_fetchone("SELECT raid_mode FROM antiraid_state WHERE guild_id=?", (guild_id,))
        return bool(row["raid_mode"]) if row else False

    async def _get_setting(self, guild_id: int, key: str, default):
        return await guild_settings.get(guild_id, f"antiraid_{key}", default)

    def _is_suspicious_join(self, member: discord.Member, min_age_s: int, flag_no_avatar: bool) -> tuple[bool, list[str]]:
        reasons = []
        now = time.time()
        account_age_s = now - member.created_at.timestamp()
        if account_age_s < min_age_s:
            age_h = account_age_s / 3600
            reasons.append(f"account too new ({age_h:.1f}h old, min {min_age_s // 3600}h)")
        if flag_no_avatar and member.avatar is None:
            reasons.append("no avatar")
        return bool(reasons), reasons

    async def _take_action(self, guild: discord.Guild, member: discord.Member, action: str, reason: str):
        try:
            if action == "ban":
                await guild.ban(member, reason=f"AntiRaid: {reason}", delete_message_days=1)
            elif action == "kick":
                await member.kick(reason=f"AntiRaid: {reason}")
            elif action == "timeout":
                until = discord.utils.utcnow() + datetime.timedelta(hours=1)
                await member.timeout(until, reason=f"AntiRaid: {reason}")
        except discord.HTTPException:
            pass

        await db.raw_execute(
            "INSERT INTO raid_join_log (guild_id, user_id, joined_at, account_created_at, had_avatar, flagged, action_taken)"
            " VALUES (?, ?, ?, ?, ?, 1, ?)",
            (guild.id, member.id, time.time(), member.created_at.timestamp(), int(member.avatar is not None), action),
        )
        await bus.publish(ANTIRAID_JOIN_FLAGGED, guild_id=guild.id, user_id=member.id, reason=reason, action=action)
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="antiraid_action", user_id=member.id, reason=reason, action_taken=action)

    async def start_raid_mode(self, guild: discord.Guild, triggered_by: str = "automatic"):
        if await self._is_raid_mode(guild.id):
            return

        duration = await guild_settings.get(guild.id, "antiraid_raid_mode_duration", config.ANTIRAID_RAID_MODE_DURATION_SECONDS)
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
                        f"**Auto-expires:** <t:{int(expires_at)}:R>\n\n"
                        "All new joins are now being scrutinized. Flagged members will be actioned automatically."
                    ))
                    view = discord.ui.LayoutView(timeout=None)
                    view.add_item(container)
                    await channel.send(view=view)
                except discord.HTTPException:
                    pass

    async def end_raid_mode(self, guild: discord.Guild, ended_by: Optional[int] = None):
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

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        guild_id = member.guild.id

        if not await self._is_enabled(guild_id):
            await db.raw_execute(
                "INSERT INTO raid_join_log (guild_id, user_id, joined_at, account_created_at, had_avatar, flagged)"
                " VALUES (?, ?, ?, ?, ?, 0)",
                (guild_id, member.id, time.time(), member.created_at.timestamp(), int(member.avatar is not None)),
            )
            return

        min_age = await self._get_setting(guild_id, "min_age_seconds", config.ANTIRAID_MIN_ACCOUNT_AGE_SECONDS)
        flag_no_avatar = await self._get_setting(guild_id, "flag_no_avatar", config.ANTIRAID_FLAG_NO_AVATAR)
        velocity_count = await self._get_setting(guild_id, "join_velocity_count", config.ANTIRAID_JOIN_VELOCITY_COUNT)
        velocity_window = await self._get_setting(guild_id, "join_velocity_window", config.ANTIRAID_JOIN_VELOCITY_WINDOW_SECONDS)

        now = time.time()
        window = _join_windows[guild_id]
        window.append(now)
        recent_joins = sum(1 for t in window if now - t < velocity_window)

        in_raid_mode = await self._is_raid_mode(guild_id)

        if not in_raid_mode and recent_joins >= velocity_count:
            await self.start_raid_mode(member.guild, triggered_by="join_velocity")
            in_raid_mode = True

        suspicious, reasons = self._is_suspicious_join(member, min_age, flag_no_avatar)

        if (in_raid_mode or suspicious) and await security.is_trusted(guild_id, member):
            await db.raw_execute(
                "INSERT INTO raid_join_log (guild_id, user_id, joined_at, account_created_at, had_avatar, flagged)"
                " VALUES (?, ?, ?, ?, ?, 0)",
                (guild_id, member.id, time.time(), member.created_at.timestamp(), int(member.avatar is not None)),
            )
            return

        if in_raid_mode or suspicious:
            action = await self._get_setting(guild_id, "join_action", config.ANTIRAID_JOIN_ACTION)
            if in_raid_mode:
                action = await self._get_setting(guild_id, "raid_mode_action", config.ANTIRAID_RAID_MODE_ACTION)
            reason_text = ", ".join(reasons) if reasons else "active raid mode"
            await self._take_action(member.guild, member, action, reason_text)
        else:
            await db.raw_execute(
                "INSERT INTO raid_join_log (guild_id, user_id, joined_at, account_created_at, had_avatar, flagged)"
                " VALUES (?, ?, ?, ?, ?, 0)",
                (guild_id, member.id, time.time(), member.created_at.timestamp(), int(member.avatar is not None)),
            )

    @commands.group(name="antiraid", aliases=["raid"], invoke_without_command=True, help='View or configure AntiRaid join protection.')
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def antiraid_group(self, ctx: commands.Context):
        from utils.security_panels import AntiRaidOverviewLayout
        view = await AntiRaidOverviewLayout.create(ctx.author.id, ctx.guild.id)
        await ctx.send(view=view)

    @antiraid_group.command(name="enable", help='Enable AntiRaid protection.')
    @has_guild_permission("administrator")
    async def ar_enable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antiraid_enabled", True)
        await ctx.send(view=success_layout(f"{e('check')} AntiRaid enabled", "AntiRaid protection is now active."))

    @antiraid_group.command(name="disable", help='Disable AntiRaid protection.')
    @has_guild_permission("administrator")
    async def ar_disable(self, ctx: commands.Context):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antiraid_enabled", False)
        await ctx.send(view=success_layout(f"{e('check')} AntiRaid disabled", "AntiRaid protection is now disabled."))

    @antiraid_group.command(name="minage", help='Set the minimum account age in days for new joins.')
    @has_guild_permission("administrator")
    async def ar_minage(self, ctx: commands.Context, days: int):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antiraid_min_age_seconds", days * 86400)
        await ctx.send(view=success_layout(f"{e('check')} Minimum age set", f"New accounts younger than **{days}d** will be flagged on join."))

    @antiraid_group.command(name="velocity", help='Set the join velocity trigger (count within window seconds).')
    @has_guild_permission("administrator")
    async def ar_velocity(self, ctx: commands.Context, count: int, window_seconds: int = 10):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antiraid_join_velocity_count", count)
        await guild_settings.set(ctx.guild.id, "antiraid_join_velocity_window", window_seconds)
        await ctx.send(view=success_layout(f"{e('check')} Join velocity set", f"Raid mode triggers after **{count}** joins in **{window_seconds}s**."))

    @antiraid_group.command(name="action", help='Set the action taken on flagged joins: kick, ban, or timeout.')
    @has_guild_permission("administrator")
    async def ar_action(self, ctx: commands.Context, action: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if action not in ("kick", "ban", "timeout"):
            return await ctx.send(view=error_layout("Invalid action", "Choose from `kick`, `ban`, or `timeout`."))
        await guild_settings.set(ctx.guild.id, "antiraid_join_action", action)
        await ctx.send(view=success_layout(f"{e('check')} Action set", f"Flagged joins will be `{action}`ed."))

    @antiraid_group.command(name="noavatar", aliases=["avatar"], help="Toggle flagging accounts with no avatar set (default profile picture).")
    @has_guild_permission("administrator")
    async def ar_avatar(self, ctx: commands.Context, toggle: bool):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antiraid_flag_no_avatar", toggle)
        state = "will" if toggle else "will not"
        await ctx.send(view=success_layout(f"{e('check')} Avatar filter updated", f"Accounts with no avatar {state} be flagged on join."))

    @antiraid_group.command(name="alertchannel", help='Set the channel for raid mode alerts.')
    @has_guild_permission("administrator")
    async def ar_alertchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "antiraid_alert_channel_id", channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Alert channel set", f"AntiRaid alerts will go to {channel.mention}."))

    @antiraid_group.command(name="raidmode", help='Manually toggle raid mode on or off.')
    @has_guild_permission("administrator")
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
