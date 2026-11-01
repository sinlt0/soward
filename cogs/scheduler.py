import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import emoji_manager, scheduler as store
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

NO_MENTIONS = discord.AllowedMentions.none()
REMINDER = 3600
USAGE = "Use `event create <title> | <when> [| description]`.\nTimes: `tomorrow 8pm`, `fri 20:00`, `in 3h`, `2026-11-05 19:30`, `5 nov 7pm`, `05/11 18:00` (day first). Uses the server timezone (`event timezone`)."


def _tz(name: str):
    return store.parse_tz(name) or store.parse_tz("UTC")


def event_layout(event: dict, rsvps: dict[str, list[int]]) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    status = event["status"]
    color = {"scheduled": 0x5865F2, "started": 0x57F287}.get(status, 0x95A5A6)
    container = discord.ui.Container(accent_color=color)
    lines = [f"## {event['title']}"]
    if event.get("description"):
        lines.append(event["description"])
    start = int(event["starts_at"])
    when = f"<t:{start}:F> (<t:{start}:R>)"
    lines.append(f"\n**When:** {when}")
    lines.append(f"**Length:** {event['duration_minutes']} min" + (f" · repeats {event['repeat']}" if event.get("repeat") not in (None, "none", "") else ""))
    if event.get("voice_channel_id"):
        lines.append(f"**Where:** <#{event['voice_channel_id']}>")
    lines.append(f"**Host:** <@{event['creator_id']}>")
    capacity = int(event.get("capacity") or 0)
    going = rsvps["going"]
    lines.append(f"\n**Going ({len(going)}{'/' + str(capacity) if capacity else ''}):** " + (" ".join(f"<@{u}>" for u in going[:15]) + (f" +{len(going) - 15} more" if len(going) > 15 else "") if going else "nobody yet"))
    if rsvps["maybe"]:
        lines.append(f"**Maybe ({len(rsvps['maybe'])}):** " + " ".join(f"<@{u}>" for u in rsvps["maybe"][:10]))
    if rsvps["waitlist"]:
        lines.append(f"**Waitlist:** {len(rsvps['waitlist'])}")
    if status == "cancelled":
        lines.append("\n**This event was cancelled.**")
    elif status == "ended":
        lines.append("\n**This event has ended.**")
    lines.append(f"-# Event {event['event_id']}")
    container.add_item(discord.ui.TextDisplay("\n".join(lines)))
    if status in ("scheduled", "started"):
        row = discord.ui.ActionRow()
        for label, key, style in (("Going", "going", discord.ButtonStyle.success), ("Maybe", "maybe", discord.ButtonStyle.secondary), ("Can't go", "no", discord.ButtonStyle.danger)):
            row.add_item(discord.ui.Button(label=label, style=style, custom_id=f"ev:rsvp:{event['event_id']}:{key}"))
        container.add_item(row)
    view.add_item(container)
    return view


class Scheduler(commands.Cog):
    category = "Utility"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    async def refresh(self, guild: discord.Guild, event: dict) -> None:
        if not event.get("channel_id") or not event.get("message_id"):
            return
        channel = guild.get_channel(event["channel_id"])
        if channel is None:
            return
        try:
            message = await channel.fetch_message(event["message_id"])
            await message.edit(view=event_layout(event, await store.rsvps(event["event_id"])), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass

    async def publish(self, guild: discord.Guild, event: dict, channel: discord.abc.Messageable) -> None:
        message = await channel.send(view=event_layout(event, await store.rsvps(event["event_id"])), allowed_mentions=NO_MENTIONS)
        await store.update(event["event_id"], message_id=message.id, channel_id=message.channel.id)

    def _mentions(self, guild: discord.Guild, event: dict, cfg: dict, going: list[int]) -> tuple[str, discord.AllowedMentions]:
        role_id = event.get("role_id") or cfg.get("role")
        role = guild.get_role(int(role_id)) if role_id else None
        users = [u for u in going[:40]]
        text = (role.mention + " " if role else "") + " ".join(f"<@{u}>" for u in users)
        return text.strip(), discord.AllowedMentions(roles=[role] if role else [], users=[discord.Object(id=u) for u in users])

    @tasks.loop(seconds=30)
    async def loop(self):
        now = time.time()
        for event in await store.live_events():
            guild = self.bot.get_guild(event["guild_id"])
            if guild is None:
                continue
            channel = guild.get_channel(event["channel_id"]) if event.get("channel_id") else None
            cfg = await store.get_config(guild.id)
            starts = event["starts_at"]
            ends = starts + event["duration_minutes"] * 60
            if event["status"] == "scheduled" and event["reminded"] < 1 and starts - REMINDER <= now < starts:
                await store.update(event["event_id"], reminded=1)
                if channel is not None:
                    going = (await store.rsvps(event["event_id"]))["going"]
                    text, allowed = self._mentions(guild, event, cfg, going)
                    try:
                        await channel.send(f"{text}\n**{event['title']}** starts <t:{int(starts)}:R>.".strip(), allowed_mentions=allowed)
                    except discord.HTTPException:
                        pass
            if event["status"] == "scheduled" and now >= starts:
                if event["reminded"] < 2 and channel is not None and now < ends:
                    going = (await store.rsvps(event["event_id"]))["going"]
                    text, allowed = self._mentions(guild, event, cfg, going)
                    where = f" Join <#{event['voice_channel_id']}>." if event.get("voice_channel_id") else ""
                    try:
                        await channel.send(f"{text}\n**{event['title']}** is starting now.{where}".strip(), allowed_mentions=allowed)
                    except discord.HTTPException:
                        pass
                step = store.REPEATS.get(event.get("repeat") or "none", 0)
                if step:
                    nxt = starts + step
                    while nxt + event["duration_minutes"] * 60 <= now:
                        nxt += step
                    await store.update(event["event_id"], starts_at=nxt, reminded=0)
                    event["starts_at"], event["reminded"] = nxt, 0
                else:
                    await store.update(event["event_id"], status="started", reminded=2)
                    event["status"] = "started"
                await self.refresh(guild, event)
            elif event["status"] == "started" and now >= ends:
                await store.update(event["event_id"], status="ended")
                event["status"] = "ended"
                await self.refresh(guild, event)
                if channel is not None:
                    data = await store.rsvps(event["event_id"])
                    try:
                        await channel.send(f"**{event['title']}** has ended. {len(data['going'])} member(s) signed up. Thanks for coming!", allowed_mentions=NO_MENTIONS, delete_after=600)
                    except discord.HTTPException:
                        pass

    @loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if not custom_id.startswith("ev:rsvp:"):
            return
        parts = custom_id.split(":")
        if len(parts) != 4 or parts[3] not in ("going", "maybe", "no"):
            return
        event = await store.get(interaction.guild.id, parts[2])
        if event is None or event["status"] not in ("scheduled", "started"):
            return await interaction.response.send_message("This event is no longer open.", ephemeral=True)
        if parts[3] == "going" and event.get("role_id") and not any(r.id == int(event["role_id"]) for r in interaction.user.roles):
            return await interaction.response.send_message("This event is for members with a specific role.", ephemeral=True)
        result = await store.rsvp(event, interaction.user.id, parts[3])
        await interaction.response.defer(ephemeral=True)
        text = {"going": "You are going.", "maybe": "Marked as maybe.", "no": "Marked as not going.", "waitlist": "The event is full, so you are on the waitlist. You move up if someone leaves."}[result]
        await interaction.followup.send(text, ephemeral=True)
        promoted_event = await store.get(interaction.guild.id, event["event_id"])
        await self.refresh(interaction.guild, promoted_event or event)

    async def _find(self, ctx: commands.Context, event_id: str) -> Optional[dict]:
        event = await store.get(ctx.guild.id, event_id)
        if event is None:
            await ctx.send(view=error_layout("Not found", "No event with that id. Use `event list`."))
        return event

    @commands.group(name="event", aliases=["events"], invoke_without_command=True, help="Scheduled events with RSVPs.")
    @commands.guild_only()
    async def event(self, ctx: commands.Context):
        await self.event_list(ctx)

    @event.command(name="list", aliases=["upcoming"], help="Upcoming events.")
    async def event_list(self, ctx: commands.Context):
        rows = await store.upcoming(ctx.guild.id)
        if not rows:
            return await ctx.send(view=info_layout("Events", "Nothing is scheduled."))
        lines = [f"`{r['event_id']}` **{r['title']}** · <t:{int(r['starts_at'])}:F> (<t:{int(r['starts_at'])}:R>)" for r in rows]
        await ctx.send(view=info_layout("Upcoming events", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @event.command(name="info", aliases=["show"], help="Show one event.")
    async def event_info(self, ctx: commands.Context, event_id: str):
        event = await self._find(ctx, event_id)
        if event:
            await ctx.send(view=event_layout(event, await store.rsvps(event["event_id"])), allowed_mentions=NO_MENTIONS)

    @event.command(name="create", aliases=["new", "add"], help="Create an event. Usage: event create <title> | <when> [| description]")
    @has_guild_permission("manage_events")
    async def event_create(self, ctx: commands.Context, *, details: str = ""):
        parts = [p.strip() for p in details.split("|")]
        if len(parts) < 2 or not parts[0] or not parts[1]:
            return await ctx.send(view=error_layout("Missing details", USAGE))
        cfg = await store.get_config(ctx.guild.id)
        tz = _tz(cfg["timezone"])
        starts = store.parse_when(parts[1], time.time(), tz)
        if starts is None:
            return await ctx.send(view=error_layout("I could not read that time", USAGE))
        if starts < time.time() + 60:
            return await ctx.send(view=error_layout("That time has passed", "Pick a time in the future."))
        if starts > time.time() + 365 * 86400:
            return await ctx.send(view=error_layout("Too far away", "Events can be at most a year ahead."))
        channel = ctx.guild.get_channel(int(cfg["channel"])) if cfg["channel"] else ctx.channel
        channel = channel or ctx.channel
        description = parts[2] if len(parts) > 2 else ""
        event_id = await store.create(ctx.guild.id, ctx.author.id, parts[0], description, starts, channel.id)
        event = await store.get(ctx.guild.id, event_id)
        try:
            await self.publish(ctx.guild, event, channel)
        except discord.HTTPException:
            await store.update(event_id, status="cancelled")
            return await ctx.send(view=error_layout("Could not post", f"I cannot send messages in {channel.mention}."))
        if channel.id != ctx.channel.id:
            await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Event created", f"Posted in {channel.mention} with id `{event_id}`."))

    @event.command(name="cancel", aliases=["delete"], help="Cancel an event.")
    @has_guild_permission("manage_events")
    async def event_cancel(self, ctx: commands.Context, event_id: str):
        event = await self._find(ctx, event_id)
        if not event:
            return
        await store.update(event["event_id"], status="cancelled")
        event["status"] = "cancelled"
        await self.refresh(ctx.guild, event)
        data = await store.rsvps(event["event_id"])
        channel = ctx.guild.get_channel(event["channel_id"]) if event.get("channel_id") else None
        if channel is not None and data["going"]:
            try:
                await channel.send(" ".join(f"<@{u}>" for u in data["going"][:40]) + f"\n**{event['title']}** was cancelled.", allowed_mentions=discord.AllowedMentions(users=[discord.Object(id=u) for u in data["going"][:40]]))
            except discord.HTTPException:
                pass
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Event", "The event was cancelled and the people who were going were told."))

    @event.command(name="time", aliases=["reschedule"], help="Change when an event starts. Usage: event time <id> <when>")
    @has_guild_permission("manage_events")
    async def event_time(self, ctx: commands.Context, event_id: str, *, when: str):
        event = await self._find(ctx, event_id)
        if not event:
            return
        tz = _tz((await store.get_config(ctx.guild.id))["timezone"])
        starts = store.parse_when(when, time.time(), tz)
        if starts is None or starts < time.time() + 60:
            return await ctx.send(view=error_layout("Invalid time", USAGE))
        await store.update(event["event_id"], starts_at=starts, reminded=0, status="scheduled")
        event = await store.get(ctx.guild.id, event["event_id"])
        await self.refresh(ctx.guild, event)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Event", f"Now starts <t:{int(starts)}:F>."))

    @event.command(name="repeat", help="Repeat an event: none, daily or weekly.")
    @has_guild_permission("manage_events")
    async def event_repeat(self, ctx: commands.Context, event_id: str, mode: str):
        mode = mode.lower()
        if mode not in store.REPEATS:
            return await ctx.send(view=error_layout("Invalid", "Use `none`, `daily` or `weekly`."))
        event = await self._find(ctx, event_id)
        if not event:
            return
        await store.update(event["event_id"], repeat=mode)
        await self.refresh(ctx.guild, await store.get(ctx.guild.id, event["event_id"]))
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Event", f"Repeat is **{mode}**."))

    @event.command(name="capacity", aliases=["limit"], help="Limit how many can attend (0 = unlimited).")
    @has_guild_permission("manage_events")
    async def event_capacity(self, ctx: commands.Context, event_id: str, amount: int):
        if not 0 <= amount <= 1000:
            return await ctx.send(view=error_layout("Invalid number", "Use 0 to 1000."))
        event = await self._find(ctx, event_id)
        if not event:
            return
        await store.update(event["event_id"], capacity=amount)
        event = await store.get(ctx.guild.id, event["event_id"])
        while await store.promote(event):
            pass
        await self.refresh(ctx.guild, event)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Event", "Capacity: " + (f"**{amount}**" if amount else "unlimited") + "."))

    @event.command(name="duration", help="Length in minutes.")
    @has_guild_permission("manage_events")
    async def event_duration(self, ctx: commands.Context, event_id: str, minutes: int):
        if not 5 <= minutes <= 1440:
            return await ctx.send(view=error_layout("Invalid number", "Use 5 to 1440."))
        event = await self._find(ctx, event_id)
        if not event:
            return
        await store.update(event["event_id"], duration_minutes=minutes)
        await self.refresh(ctx.guild, await store.get(ctx.guild.id, event["event_id"]))
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Event", f"Length: **{minutes}** minutes."))

    @event.command(name="voice", help="Voice channel where the event happens.")
    @has_guild_permission("manage_events")
    async def event_voice(self, ctx: commands.Context, event_id: str, channel: discord.VoiceChannel | discord.StageChannel):
        event = await self._find(ctx, event_id)
        if not event:
            return
        await store.update(event["event_id"], voice_channel_id=channel.id)
        await self.refresh(ctx.guild, await store.get(ctx.guild.id, event["event_id"]))
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Event", f"Happens in {channel.mention}."), allowed_mentions=NO_MENTIONS)

    @event.command(name="role", help="Role pinged for this event, only members with it can RSVP going.")
    @has_guild_permission("manage_events")
    async def event_role(self, ctx: commands.Context, event_id: str, role: Optional[discord.Role] = None):
        event = await self._find(ctx, event_id)
        if not event:
            return
        await store.update(event["event_id"], role_id=role.id if role else None)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Event", f"Role: {role.mention}." if role else "Role cleared."), allowed_mentions=NO_MENTIONS)

    @event.command(name="who", help="Everyone who answered.")
    @has_guild_permission("manage_events")
    async def event_who(self, ctx: commands.Context, event_id: str):
        event = await self._find(ctx, event_id)
        if not event:
            return
        data = await store.rsvps(event["event_id"])
        body = "\n".join(f"**{k.title()} ({len(v)}):** " + (" ".join(f"<@{u}>" for u in v[:40]) or "-") for k, v in data.items() if k != "no")
        await ctx.send(view=info_layout(event["title"], body), allowed_mentions=NO_MENTIONS)

    @event.command(name="channel", help="Default channel where events are posted.")
    @has_guild_permission("manage_guild")
    async def event_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await store.set_config(ctx.guild.id, "channel", channel.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Events", f"Events are posted in {channel.mention}."))

    @event.command(name="pingrole", help="Default role pinged for reminders.")
    @has_guild_permission("manage_guild")
    async def event_pingrole(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        await store.set_config(ctx.guild.id, "role", role.id if role else None)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Events", f"Reminders ping {role.mention}." if role else "Reminders no longer ping a role."), allowed_mentions=NO_MENTIONS)

    @event.command(name="timezone", aliases=["tz"], help="Timezone used when reading times, e.g. Asia/Dhaka or UTC+6.")
    @has_guild_permission("manage_guild")
    async def event_timezone(self, ctx: commands.Context, *, zone: str):
        if store.parse_tz(zone) is None:
            return await ctx.send(view=error_layout("Unknown timezone", "Use a name like `Europe/Berlin` or an offset like `UTC+6`."))
        await store.set_config(ctx.guild.id, "timezone", zone.strip())
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Events", f"Times are read in **{zone.strip()}**."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Scheduler(bot))
