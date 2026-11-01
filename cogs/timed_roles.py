import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import db, emoji_manager, scheduler, timed_roles as store
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.converters import DurationConverter, format_duration
from utils.events_bus import LOG_EVENT, bus

NO_MENTIONS = discord.AllowedMentions.none()
MAX_SECONDS = 5 * 365 * 86400


def season_layout(season: dict) -> discord.ui.LayoutView:
    state = store.window_state(season, time.time())
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color={"open": 0x57F287, "upcoming": 0xFEE75C}.get(state, 0x95A5A6))
    lines = [f"## {season['name']}", f"Claim <@&{season['role_id']}> while the season is open. It is removed automatically when the season ends.",
             f"\n**Opens:** <t:{int(season['starts_at'])}:F>\n**Ends:** <t:{int(season['ends_at'])}:F> (<t:{int(season['ends_at'])}:R>)"]
    if season["yearly"]:
        lines.append("-# Comes back every year")
    if state == "ended":
        lines.append("\n**This season has ended.**")
    elif state == "upcoming":
        lines.append("\n**Not open yet.**")
    container.add_item(discord.ui.TextDisplay("\n".join(lines)))
    if state != "ended":
        row = discord.ui.ActionRow()
        row.add_item(discord.ui.Button(label="Claim role", style=discord.ButtonStyle.success, custom_id=f"season:claim:{season['season_id']}"))
        row.add_item(discord.ui.Button(label="Give it back", style=discord.ButtonStyle.secondary, custom_id=f"season:drop:{season['season_id']}"))
        container.add_item(row)
    view.add_item(container)
    return view


class TimedRoles(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    async def expire(self, row: dict) -> None:
        guild = self.bot.get_guild(row["guild_id"])
        if guild is None:
            return
        await store.remove(row["guild_id"], row["user_id"], row["role_id"])
        member = guild.get_member(row["user_id"])
        role = guild.get_role(row["role_id"])
        if member is None or role is None or role not in member.roles:
            return
        try:
            await member.remove_roles(role, reason="Timed role expired")
        except discord.HTTPException:
            return
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="role_remove", user_id=member.id, moderator_id=None, reason=f"Timed role {role.name} expired")

    async def advance_seasons(self) -> None:
        now = time.time()
        for season in await store.seasons():
            if season["ends_at"] > now:
                continue
            guild = self.bot.get_guild(season["guild_id"])
            if guild is None:
                continue
            if season["yearly"]:
                start, end = store.next_year(season["starts_at"]), store.next_year(season["ends_at"])
                while end <= now:
                    start, end = store.next_year(start), store.next_year(end)
                await store.update_season(season["season_id"], starts_at=start, ends_at=end)
                season.update(starts_at=start, ends_at=end)
                await self.refresh_season(guild, season)

    async def refresh_season(self, guild: discord.Guild, season: dict) -> None:
        if not season.get("channel_id") or not season.get("message_id"):
            return
        channel = guild.get_channel(season["channel_id"])
        if channel is None:
            return
        try:
            message = await channel.fetch_message(season["message_id"])
            await message.edit(view=season_layout(season), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass

    @tasks.loop(seconds=30)
    async def loop(self):
        for row in await store.due(time.time()):
            await self.expire(row)
        await self.advance_seasons()

    @loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        now = time.time()
        for row in await store.for_member(member.guild.id, member.id):
            if row["expires_at"] <= now:
                await store.remove(member.guild.id, member.id, row["role_id"])
                continue
            role = member.guild.get_role(row["role_id"])
            if role is None or role >= member.guild.me.top_role:
                continue
            try:
                await member.add_roles(role, reason="Timed role restored after rejoining")
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await store.drop_role(role.guild.id, role.id)
        for season in await store.seasons(role.guild.id):
            if season["role_id"] == role.id:
                await store.delete_season(season["season_id"])

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if not custom_id.startswith("season:"):
            return
        parts = custom_id.split(":")
        if len(parts) != 3 or parts[1] not in ("claim", "drop"):
            return
        guild, member = interaction.guild, interaction.user
        season = await store.get_season(guild.id, parts[2])
        role = guild.get_role(season["role_id"]) if season else None
        if season is None or role is None:
            return await interaction.response.send_message("This season no longer exists.", ephemeral=True)
        if parts[1] == "drop":
            await store.remove(guild.id, member.id, role.id)
            try:
                await member.remove_roles(role, reason="Seasonal role returned")
            except discord.HTTPException:
                pass
            return await interaction.response.send_message("The role was removed.", ephemeral=True)
        state = store.window_state(season, time.time())
        if state != "open":
            return await interaction.response.send_message("This season is not open." if state == "ended" else f"This season opens <t:{int(season['starts_at'])}:R>.", ephemeral=True)
        if role.managed or role >= guild.me.top_role or role.permissions.administrator or role.permissions.manage_guild:
            return await interaction.response.send_message("I cannot hand out that role.", ephemeral=True)
        try:
            await member.add_roles(role, reason=f"Seasonal role {season['name']}")
        except discord.HTTPException:
            return await interaction.response.send_message("I could not give you the role.", ephemeral=True)
        await store.grant(guild.id, member.id, role.id, season["ends_at"], None, f"Season {season['name']}", season["season_id"])
        await interaction.response.send_message(f"You got {role.mention} until <t:{int(season['ends_at'])}:F>.", ephemeral=True)

    @commands.group(name="temprole", aliases=["timedrole"], invoke_without_command=True, help="Give roles that expire automatically.")
    @commands.guild_only()
    @has_guild_permission("manage_roles")
    async def temprole(self, ctx: commands.Context):
        await ctx.send(view=info_layout("Timed roles", "`temprole add @member @role <duration> [reason]` · `temprole extend @member @role <duration>` · `temprole remove @member @role` · `temprole list [@member]`\nDurations like `7d`, `12h`, `2w`."))

    @temprole.command(name="add", help="Give a role for a limited time. Usage: temprole add <member> <role> <duration> [reason]")
    @has_guild_permission("manage_roles")
    async def temprole_add(self, ctx: commands.Context, member: discord.Member, role: discord.Role, duration: DurationConverter, *, reason: str = ""):
        if not 60 <= duration <= MAX_SECONDS:
            return await ctx.send(view=error_layout("Invalid duration", "Use between 1 minute and 5 years."))
        moderation = self.bot.get_cog("Moderation")
        problem = await moderation._role_problem(ctx, member, role, adding=True) if moderation else None
        if problem:
            return await ctx.send(view=error_layout("Cannot assign", problem), allowed_mentions=NO_MENTIONS)
        if role not in member.roles:
            try:
                await member.add_roles(role, reason=f"Timed role by {ctx.author}")
            except discord.HTTPException:
                return await ctx.send(view=error_layout("Failed", "I could not give that role. Check my permissions."))
        expires = time.time() + duration
        await store.grant(ctx.guild.id, member.id, role.id, expires, ctx.author.id, reason)
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="role_add", user_id=member.id, moderator_id=ctx.author.id, reason=f"Gave {role.name} for {format_duration(duration)}")
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Timed role", f"{member.mention} has {role.mention} until <t:{int(expires)}:F> (<t:{int(expires)}:R>)."), allowed_mentions=NO_MENTIONS)

    @temprole.command(name="extend", help="Add time to a timed role.")
    @has_guild_permission("manage_roles")
    async def temprole_extend(self, ctx: commands.Context, member: discord.Member, role: discord.Role, duration: DurationConverter):
        row = await store.get(ctx.guild.id, member.id, role.id)
        if row is None:
            return await ctx.send(view=error_layout("Not timed", "That member has no timed role like that."))
        if duration < 60 or row["expires_at"] + duration > time.time() + MAX_SECONDS:
            return await ctx.send(view=error_layout("Invalid duration", "Use at least 1 minute, at most 5 years in total."))
        expires = row["expires_at"] + duration
        await store.grant(ctx.guild.id, member.id, role.id, expires, ctx.author.id, row["reason"] or "", row.get("season_id"))
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Timed role", f"Now ends <t:{int(expires)}:F> (<t:{int(expires)}:R>)."))

    @temprole.command(name="remove", aliases=["end"], help="End a timed role now.")
    @has_guild_permission("manage_roles")
    async def temprole_remove(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        row = await store.get(ctx.guild.id, member.id, role.id)
        if row is None:
            return await ctx.send(view=error_layout("Not timed", "That member has no timed role like that."))
        moderation = self.bot.get_cog("Moderation")
        problem = await moderation._role_problem(ctx, member, role, adding=False) if moderation else None
        if problem:
            return await ctx.send(view=error_layout("Cannot remove", problem), allowed_mentions=NO_MENTIONS)
        await store.remove(ctx.guild.id, member.id, role.id)
        if role in member.roles:
            try:
                await member.remove_roles(role, reason=f"Timed role ended by {ctx.author}")
            except discord.HTTPException:
                pass
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Timed role", f"Removed {role.mention} from {member.mention}."), allowed_mentions=NO_MENTIONS)

    @temprole.command(name="list", help="List timed roles in the server or for one member.")
    async def temprole_list(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        rows = await store.for_member(ctx.guild.id, member.id) if member else await store.listing(ctx.guild.id)
        if not rows:
            return await ctx.send(view=info_layout("Timed roles", "None right now."))
        lines = [f"<@{r['user_id']}> · <@&{r['role_id']}> · ends <t:{int(r['expires_at'])}:R>" for r in rows]
        await ctx.send(view=info_layout("Timed roles", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @commands.group(name="season", aliases=["seasonal"], invoke_without_command=True, help="Seasonal roles members can claim while a season is open.")
    @commands.guild_only()
    @has_guild_permission("manage_roles")
    async def season(self, ctx: commands.Context):
        await ctx.send(view=info_layout("Seasonal roles", "`season create <name> | @role | <opens> | <ends>` · `season panel <id> [#channel]` · `season list` · `season yearly <id> on|off` · `season delete <id>`\nA season role is removed from everyone when it ends."))

    @season.command(name="create", help="Create a season. Usage: season create <name> | <role> | <opens> | <ends>")
    @has_guild_permission("manage_roles")
    async def season_create(self, ctx: commands.Context, *, details: str = ""):
        parts = [p.strip() for p in details.split("|")]
        if len(parts) != 4 or not all(parts):
            return await ctx.send(view=error_layout("Missing details", "Use `season create Winter | @Snowflake | 1 dec 00:00 | 1 jan 00:00`. Times use the server timezone (`event timezone`)."))
        try:
            role = await commands.RoleConverter().convert(ctx, parts[1])
        except commands.BadArgument:
            return await ctx.send(view=error_layout("Unknown role", "Mention the role or use its name."))
        if role.managed or role >= ctx.guild.me.top_role or role.permissions.administrator or role.permissions.manage_guild:
            return await ctx.send(view=error_layout("Cannot use that role", "It is managed, above my top role or carries dangerous permissions."))
        tz = scheduler.parse_tz((await scheduler.get_config(ctx.guild.id))["timezone"]) or scheduler.parse_tz("UTC")
        now = time.time()
        start = scheduler.parse_when(parts[2], now - 3600, tz)
        end = scheduler.parse_when(parts[3], now, tz)
        if start is None or end is None:
            return await ctx.send(view=error_layout("I could not read the times", "Try `1 dec 00:00`, `2026-12-01 00:00` or `in 3d`."))
        if start > end:
            start_dt = start
            end = scheduler.parse_when(parts[3], start_dt, tz)
        if end is None or end <= start or end <= now:
            return await ctx.send(view=error_layout("Invalid window", "The end must be after the start and in the future."))
        season_id = await store.create_season(ctx.guild.id, parts[0], role.id, start, end, ctx.author.id, False)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Season created", f"`{season_id}` · **{parts[0]}** · {role.mention}\nOpens <t:{int(start)}:F>, ends <t:{int(end)}:F>.\nPost the claim panel with `season panel {season_id}`."), allowed_mentions=NO_MENTIONS)

    @season.command(name="panel", help="Post the claim panel.")
    @has_guild_permission("manage_roles")
    async def season_panel(self, ctx: commands.Context, season_id: str, channel: Optional[discord.TextChannel] = None):
        season = await store.get_season(ctx.guild.id, season_id)
        if season is None:
            return await ctx.send(view=error_layout("Not found", "No season with that id. Use `season list`."))
        channel = channel or ctx.channel
        try:
            message = await channel.send(view=season_layout(season), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            return await ctx.send(view=error_layout("Could not post", f"I cannot send messages in {channel.mention}."))
        await store.update_season(season["season_id"], channel_id=channel.id, message_id=message.id)

    @season.command(name="list", help="List seasons.")
    @has_guild_permission("manage_roles")
    async def season_list(self, ctx: commands.Context):
        rows = await store.seasons(ctx.guild.id)
        if not rows:
            return await ctx.send(view=info_layout("Seasons", "None yet."))
        lines = [f"`{r['season_id']}` **{r['name']}** · <@&{r['role_id']}> · {store.window_state(r, time.time())} · <t:{int(r['starts_at'])}:d> to <t:{int(r['ends_at'])}:d>" + (" · yearly" if r["yearly"] else "") for r in rows]
        await ctx.send(view=info_layout("Seasons", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @season.command(name="yearly", help="Repeat the season every year.")
    @has_guild_permission("manage_roles")
    async def season_yearly(self, ctx: commands.Context, season_id: str, toggle: bool):
        season = await store.get_season(ctx.guild.id, season_id)
        if season is None:
            return await ctx.send(view=error_layout("Not found", "No season with that id."))
        await store.update_season(season["season_id"], yearly=1 if toggle else 0)
        season["yearly"] = 1 if toggle else 0
        await self.refresh_season(ctx.guild, season)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Season", f"Yearly repeat is **{'on' if toggle else 'off'}**."))

    @season.command(name="delete", help="Delete a season and take the role back from everyone who claimed it.")
    @has_guild_permission("manage_roles")
    async def season_delete(self, ctx: commands.Context, season_id: str):
        season = await store.get_season(ctx.guild.id, season_id)
        if season is None:
            return await ctx.send(view=error_layout("Not found", "No season with that id."))
        rows = await db.raw_fetch("SELECT * FROM timed_roles WHERE guild_id=? AND season_id=?", (ctx.guild.id, season["season_id"]))
        for row in rows:
            await self.expire({**dict(row), "expires_at": 0})
        await store.delete_season(season["season_id"])
        season["ends_at"] = 0
        await self.refresh_season(ctx.guild, season)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Season", f"Deleted. Removed the role from **{len(rows)}** member(s)."))


async def setup(bot: commands.Bot):
    await bot.add_cog(TimedRoles(bot))
