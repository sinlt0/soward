import json
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

import config
from utils import embed_templates, emoji_manager, main_role, premium_limits, schedule_actions as store, scheduler
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import LOG_EVENT, bus

NO_MENTIONS = discord.AllowedMentions.none()
WHEN = "Times: `tomorrow 8pm`, `fri 20:00`, `in 3h`, `2026-11-05 19:30`. Add `repeat daily`, `repeat weekly` or `repeat 6h` at the end to repeat. Uses the server timezone (`event timezone`)."


class ScheduleActions(commands.Cog):
    category = "Utility"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.runner.start()

    def cog_unload(self):
        self.runner.cancel()

    async def _when(self, ctx: commands.Context, text: str):
        base, repeat = store.split_repeat(text)
        if repeat is None:
            await ctx.send(view=error_layout("Invalid repeat", f"Repeat must be `daily`, `weekly`, `hourly` or an interval of at least {config.SCHEDULE_MIN_REPEAT // 60} minutes like `6h`."))
            return None
        tz, _ = await store.tz_for(ctx.guild.id)
        run_at = scheduler.parse_when(base, time.time(), tz)
        if run_at is None or run_at <= time.time():
            await ctx.send(view=error_layout("Invalid time", "That time is missing or already passed.\n" + WHEN))
            return None
        return run_at, repeat

    async def _room(self, ctx: commands.Context) -> bool:
        if not await premium_limits.gate(ctx, "Scheduled actions"):
            return False
        if await store.count(ctx.guild.id) >= config.SCHEDULE_MAX_ACTIONS:
            await ctx.send(view=error_layout("Limit reached", f"A server can hold {config.SCHEDULE_MAX_ACTIONS} scheduled actions. Cancel one with `schedule cancel <id>`."))
            return False
        return True

    async def _saved(self, ctx: commands.Context, kind: str, run_at: float, repeat: int, payload: dict):
        action_id = await store.create(ctx.guild.id, ctx.author.id, kind, run_at, repeat, payload)
        row = {"kind": kind, "payload": json.dumps(payload)}
        again = f" and then {store.every(repeat)}" if repeat else ""
        await ctx.send(view=success_layout("Scheduled", f"`{action_id}` will {store.describe(row)} <t:{int(run_at)}:F> (<t:{int(run_at)}:R>){again}."), allowed_mentions=NO_MENTIONS)

    @commands.group(name="schedule", aliases=["scheduled", "sched"], invoke_without_command=True, help="Schedule announcements, locks and role changes (Premium).")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def schedule(self, ctx: commands.Context):
        e = emoji_manager.get
        used = await store.count(ctx.guild.id)
        body = (
            "Run things later, or on a repeat, without being online.\n\n"
            "`schedule say <#channel> <message> | <when>` Post a message or `{embed:name}`\n"
            "`schedule lock <#channel> <when>` · `schedule unlock <#channel> <when>`\n"
            "`schedule role add|remove <@role> <@member> <when>`\n"
            "`schedule list` · `schedule info <id>` · `schedule cancel <id>`\n\n"
            f"{WHEN}\n-# {used}/{config.SCHEDULE_MAX_ACTIONS} used"
        )
        await ctx.send(view=info_layout(f"{e('calendar')} Scheduled Actions", body))

    @schedule.command(name="say", aliases=["post", "announce"], help="Post a message later. Usage: schedule say <#channel> <message> | <when>")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def say(self, ctx: commands.Context, channel: discord.TextChannel, *, text: str):
        if not await self._room(ctx):
            return
        if "|" not in text:
            return await ctx.send(view=error_layout("Missing time", "Separate the message and the time with `|`.\n" + WHEN))
        message, _, when = text.rpartition("|")
        message = message.strip()
        if not message or len(message) > 1900:
            return await ctx.send(view=error_layout("Invalid message", "The message must be 1 to 1900 characters."))
        if not channel.permissions_for(ctx.author).send_messages:
            return await ctx.send(view=error_layout("No access", "You cannot send messages in that channel."))
        parsed = await self._when(ctx, when)
        if parsed is None:
            return
        await self._saved(ctx, "say", parsed[0], parsed[1], {"channel_id": channel.id, "text": message})

    async def _lock(self, ctx: commands.Context, kind: str, channel: discord.TextChannel, when: str):
        if not await self._room(ctx):
            return
        if not channel.permissions_for(ctx.author).manage_channels:
            return await ctx.send(view=error_layout("No access", "You need Manage Channel on that channel."))
        parsed = await self._when(ctx, when)
        if parsed is None:
            return
        await self._saved(ctx, kind, parsed[0], parsed[1], {"channel_id": channel.id})

    @schedule.command(name="lock", help="Lock a channel later. Usage: schedule lock <#channel> <when>")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def lock(self, ctx: commands.Context, channel: discord.TextChannel, *, when: str):
        await self._lock(ctx, "lock", channel, when)

    @schedule.command(name="unlock", help="Unlock a channel later. Usage: schedule unlock <#channel> <when>")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def unlock(self, ctx: commands.Context, channel: discord.TextChannel, *, when: str):
        await self._lock(ctx, "unlock", channel, when)

    @schedule.command(name="role", help="Give or remove a role later. Usage: schedule role <add|remove> <@role> <@member> <when>")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def role(self, ctx: commands.Context, mode: str, role: discord.Role, member: discord.Member, *, when: str):
        mode = mode.lower()
        if mode not in ("add", "remove"):
            return await ctx.send(view=error_layout("Invalid", "Use `add` or `remove`."))
        if not await self._room(ctx):
            return
        if not ctx.author.guild_permissions.manage_roles and ctx.author.id != ctx.guild.owner_id:
            return await ctx.send(view=error_layout("No access", "You need Manage Roles."))
        if ctx.author.id != ctx.guild.owner_id and role >= ctx.author.top_role:
            return await ctx.send(view=error_layout("Role too high", "You can only schedule roles below your own highest role."))
        if role.is_default() or role.managed or role >= ctx.guild.me.top_role:
            return await ctx.send(view=error_layout("Cannot manage role", "Zyro cannot assign that role."))
        parsed = await self._when(ctx, when)
        if parsed is None:
            return
        await self._saved(ctx, f"role_{mode}", parsed[0], parsed[1], {"role_id": role.id, "user_id": member.id})

    @schedule.command(name="list", aliases=["all"], help="List scheduled actions.")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def list_actions(self, ctx: commands.Context):
        rows = await store.listing(ctx.guild.id)
        if not rows:
            return await ctx.send(view=info_layout("Scheduled Actions", "Nothing is scheduled. See `schedule` for the commands."))
        lines = []
        for r in rows[:25]:
            again = f" · {store.every(int(r['repeat_seconds']))}" if r["repeat_seconds"] else ""
            lines.append(f"`{r['action_id']}` <t:{int(r['run_at'])}:R> · {store.describe(r)}{again}")
        note = "" if await premium_limits.is_premium(ctx.guild.id) else "\n\nPremium has ended on this server, so these are paused until it is renewed."
        await ctx.send(view=info_layout("Scheduled Actions", "\n".join(lines) + note), allowed_mentions=NO_MENTIONS)

    @schedule.command(name="info", help="Show one scheduled action. Usage: schedule info <id>")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def info(self, ctx: commands.Context, action_id: str):
        row = await store.get(ctx.guild.id, action_id)
        if row is None:
            return await ctx.send(view=error_layout("Not found", "No scheduled action with that id."))
        lines = [
            f"**Will:** {store.describe(row)}",
            f"**Next run:** <t:{int(row['run_at'])}:F> (<t:{int(row['run_at'])}:R>)",
            f"**Repeats:** {store.every(int(row['repeat_seconds'])) if row['repeat_seconds'] else 'no'}",
            f"**Created by:** <@{row['created_by']}>",
            f"**Runs so far:** {row['runs']}",
        ]
        if row["last_error"]:
            lines.append(f"**Last problem:** {row['last_error']}")
        await ctx.send(view=info_layout(f"Scheduled {row['action_id']}", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @schedule.command(name="cancel", aliases=["delete", "remove"], help="Cancel a scheduled action. Usage: schedule cancel <id>")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def cancel(self, ctx: commands.Context, action_id: str):
        row = await store.get(ctx.guild.id, action_id)
        if row is None:
            return await ctx.send(view=error_layout("Not found", "No scheduled action with that id."))
        await store.delete(row["action_id"])
        await ctx.send(view=success_layout("Cancelled", f"`{row['action_id']}` was removed."))

    async def _execute(self, guild: discord.Guild, row: dict) -> Optional[str]:
        payload = json.loads(row["payload"] or "{}")
        kind = row["kind"]
        if kind in ("say", "lock", "unlock"):
            channel = guild.get_channel(int(payload.get("channel_id", 0)))
            if not isinstance(channel, discord.TextChannel):
                return "The channel no longer exists."
            if kind == "say":
                text, embeds = await embed_templates.resolve_embed_refs(guild.id, payload.get("text", ""), None)
                if not text and not embeds:
                    return "The message is empty."
                await channel.send(content=text, embeds=embeds[:10], allowed_mentions=discord.AllowedMentions(roles=True, users=True, everyone=False))
                return None
            target = await main_role.get(guild)
            overwrite = channel.overwrites_for(target)
            overwrite.send_messages = False if kind == "lock" else None
            await channel.set_permissions(target, overwrite=overwrite, reason=f"Scheduled {kind} ({row['action_id']})")
            return None
        role = guild.get_role(int(payload.get("role_id", 0)))
        member = guild.get_member(int(payload.get("user_id", 0)))
        if role is None or member is None:
            return "The role or member no longer exists."
        if role >= guild.me.top_role:
            return "The role is above Zyro's highest role."
        if kind == "role_add":
            await member.add_roles(role, reason=f"Scheduled action {row['action_id']}")
        else:
            await member.remove_roles(role, reason=f"Scheduled action {row['action_id']}")
        return None

    @tasks.loop(seconds=30)
    async def runner(self):
        now = time.time()
        for row in await store.due(now):
            guild = self.bot.get_guild(int(row["guild_id"]))
            if guild is None or not await premium_limits.is_premium(guild.id):
                if int(row["repeat_seconds"] or 0) and now - float(row["run_at"]) > store.GRACE:
                    await store.finish(row, now, "Skipped because Premium is not active.")
                continue
            if now - float(row["run_at"]) > store.GRACE:
                await store.finish(row, now, "Missed because the bot was offline.")
                continue
            try:
                error = await self._execute(guild, row)
            except discord.HTTPException as exc:
                error = f"Discord refused: {str(exc)[:100]}"
            except Exception as exc:
                error = f"Failed: {type(exc).__name__}"
            await bus.publish(LOG_EVENT, guild_id=guild.id, action="scheduled_action", actor_id=row["created_by"], detail=f"{row['action_id']} {row['kind']}" + (f" failed: {error}" if error else " ran"))
            await store.finish(row, now, error)

    @runner.before_loop
    async def _before_runner(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(ScheduleActions(bot))
