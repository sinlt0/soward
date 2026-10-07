import json
import logging
import random
import time
import uuid
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import db, emoji_manager
from utils.checks import has_guild_permission
from utils.colors import ERROR, NEUTRAL, SUCCESS
from utils.components import ConfirmLayout, error_layout, footer_block, info_layout, success_layout
from utils.converters import DurationConverter, format_duration
import config

log = logging.getLogger("soward.giveaways")



def _layout(title: str, body: str, *, color: int = NEUTRAL) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


async def _resolve_giveaway(ctx: commands.Context, identifier: str) -> Optional[dict]:
    if identifier.isdigit():
        row = await db.raw_fetchone(
            "SELECT * FROM giveaways WHERE message_id=? AND guild_id=?", (int(identifier), ctx.guild.id)
        )
        if row:
            return row
    return await db.raw_fetchone(
        "SELECT * FROM giveaways WHERE giveaway_id=? AND guild_id=?", (identifier.upper(), ctx.guild.id)
    )


class GiveawayEntryRow(discord.ui.ActionRow):
    def __init__(self, giveaway_id: str):
        super().__init__(
            discord.ui.Button(label="Enter Giveaway", style=discord.ButtonStyle.success, custom_id=f"giveaway:enter:{giveaway_id}", emoji="🎉"),
        )
        self.giveaway_id = giveaway_id
        self.children[0].callback = self._enter

    async def _enter(self, interaction: discord.Interaction):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT * FROM giveaways WHERE giveaway_id=?", (self.giveaway_id,))
        if not row or row["ended"]:
            return await interaction.response.send_message(view=error_layout("Ended", "This giveaway has ended."), ephemeral=True)

        if row["required_role_id"]:
            role = interaction.guild.get_role(row["required_role_id"])
            if role and role not in interaction.user.roles:
                return await interaction.response.send_message(
                    view=error_layout("Missing Required Role", f"You need {role.mention} to enter this giveaway."), ephemeral=True
                )

        if row["min_account_age_days"]:
            account_age_days = (discord.utils.utcnow() - interaction.user.created_at).days
            if account_age_days < row["min_account_age_days"]:
                return await interaction.response.send_message(
                    view=error_layout("Account Too New", f"Your account must be at least **{row['min_account_age_days']}** day(s) old to enter."),
                    ephemeral=True,
                )

        existing = await db.raw_fetchone(
            "SELECT 1 FROM giveaway_entries WHERE giveaway_id=? AND user_id=?",
            (self.giveaway_id, interaction.user.id),
        )
        if existing:
            await db.raw_execute(
                "DELETE FROM giveaway_entries WHERE giveaway_id=? AND user_id=?",
                (self.giveaway_id, interaction.user.id),
            )
            return await interaction.response.send_message(
                view=_layout(f"{e('giveaway')} Entry Removed", "You have left the giveaway."), ephemeral=True
            )

        await db.raw_execute(
            "INSERT INTO giveaway_entries (giveaway_id, user_id) VALUES (?, ?)",
            (self.giveaway_id, interaction.user.id),
        )

        bonus_rows = await db.raw_fetch(
            "SELECT role_id, bonus_entries FROM giveaway_bonus_roles WHERE giveaway_id=?", (self.giveaway_id,)
        )
        total_entries = 1
        for b in bonus_rows:
            role = interaction.guild.get_role(b["role_id"])
            if role and role in interaction.user.roles:
                total_entries += b["bonus_entries"]

        body = "You have entered the giveaway. Good luck!"
        if total_entries > 1:
            body += f"\n\n**Your total entries:** `{total_entries}` (bonus role entries included)"
        await interaction.response.send_message(view=success_layout(f"{e('giveaway')} Entered!", body), ephemeral=True)


def build_giveaway_panel(giveaway_id: str, prize: str, body: str) -> discord.ui.LayoutView:
    e = emoji_manager.get
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=NEUTRAL)
    container.add_item(discord.ui.TextDisplay(f"## {e('giveaway')} {prize}\n{body}"))
    container.add_item(discord.ui.Separator())
    container.add_item(GiveawayEntryRow(giveaway_id))
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


class PollVoteRow(discord.ui.ActionRow):
    def __init__(self, poll_id: str, options: list[str]):
        super().__init__(
            discord.ui.Select(
                placeholder="Cast your vote...",
                options=[discord.SelectOption(label=opt[:100], value=opt[:100]) for opt in options[:25]],
                custom_id=f"poll:vote:{poll_id}",
            ),
        )
        self.poll_id = poll_id
        self.children[0].callback = self._vote

    async def _vote(self, interaction: discord.Interaction):
        e = emoji_manager.get
        choice = interaction.data["values"][0]

        row = await db.raw_fetchone("SELECT * FROM polls WHERE poll_id=?", (self.poll_id,))
        if not row or row["ended"]:
            return await interaction.response.send_message(view=error_layout("Ended", "This poll has ended."), ephemeral=True)

        votes = json.loads(row["votes"])
        votes[str(interaction.user.id)] = choice
        await db.raw_execute("UPDATE polls SET votes=? WHERE poll_id=?", (json.dumps(votes), self.poll_id))
        await interaction.response.send_message(view=success_layout(f"{e('check')} Vote Recorded", f"You voted for **{choice}**."), ephemeral=True)


def build_poll_panel(poll_id: str, question: str, options: list[str]) -> discord.ui.LayoutView:
    e = emoji_manager.get
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=NEUTRAL)
    container.add_item(discord.ui.TextDisplay(f"## {e('poll')} {question}\nSelect an option below to vote."))
    container.add_item(discord.ui.Separator())
    container.add_item(PollVoteRow(poll_id, options))
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


class Giveaways(commands.Cog):
    category = "Engagement"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.giveaway_checker.start()
        self.poll_checker.start()

    async def cog_load(self):
        giveaway_rows = await db.raw_fetch("SELECT giveaway_id, prize FROM giveaways WHERE ended=0")
        for row in giveaway_rows:
            try:
                panel = discord.ui.LayoutView(timeout=None)
                container = discord.ui.Container(accent_color=NEUTRAL)
                container.add_item(discord.ui.TextDisplay(f"## {row['prize']}"))
                container.add_item(GiveawayEntryRow(row["giveaway_id"]))
                panel.add_item(container)
                self.bot.add_view(panel)
            except Exception:
                pass

        poll_rows = await db.raw_fetch("SELECT poll_id, options FROM polls WHERE ended=0")
        for row in poll_rows:
            try:
                options = json.loads(row["options"])
                panel = discord.ui.LayoutView(timeout=None)
                container = discord.ui.Container(accent_color=NEUTRAL)
                container.add_item(PollVoteRow(row["poll_id"], options))
                panel.add_item(container)
                self.bot.add_view(panel)
            except Exception:
                pass

    def cog_unload(self):
        self.giveaway_checker.cancel()
        self.poll_checker.cancel()

    def _get_weighted_entries(self, user_ids: list[int], guild: discord.Guild, giveaway_id: str, bonus_rows: list) -> list[int]:
        if not bonus_rows:
            return user_ids
        weighted = []
        for user_id in user_ids:
            member = guild.get_member(user_id)
            weight = 1
            if member:
                for b in bonus_rows:
                    role = guild.get_role(b["role_id"])
                    if role and role in member.roles:
                        weight += b["bonus_entries"]
            weighted.extend([user_id] * weight)
        return weighted

    async def _end_giveaway(self, row):
        e = emoji_manager.get
        guild = self.bot.get_guild(row["guild_id"])
        channel = guild.get_channel(row["channel_id"]) if guild else None

        entries = await db.raw_fetch("SELECT user_id FROM giveaway_entries WHERE giveaway_id=?", (row["giveaway_id"],))
        user_ids = [r["user_id"] for r in entries]

        bonus_rows = await db.raw_fetch(
            "SELECT role_id, bonus_entries FROM giveaway_bonus_roles WHERE giveaway_id=?", (row["giveaway_id"],)
        )

        await db.raw_execute("UPDATE giveaways SET ended=1 WHERE giveaway_id=?", (row["giveaway_id"],))

        if not channel:
            return

        if not user_ids:
            view = error_layout(f"{e('giveaway')} Giveaway Ended", f"**{row['prize']}**\n\nNo one entered this giveaway.")
            try:
                await channel.send(view=view)
            except discord.HTTPException:
                pass
            return

        weighted_pool = self._get_weighted_entries(user_ids, guild, row["giveaway_id"], bonus_rows) if guild else user_ids
        winner_count = min(row["winner_count"], len(set(user_ids)))
        winners = []
        pool = list(weighted_pool)
        while len(winners) < winner_count and pool:
            pick = random.choice(pool)
            if pick not in winners:
                winners.append(pick)
            pool = [u for u in pool if u != pick]

        winner_mentions = ", ".join(f"<@{w}>" for w in winners)

        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=SUCCESS)
        container.add_item(discord.ui.TextDisplay(
            f"## {e('giveaway')} Giveaway Ended!\n{winner_mentions}"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f"**Prize:** {row['prize']}\n**Winner(s):** {winner_mentions}\n**Total entries:** `{len(user_ids)}`"
        ))
        container.add_item(discord.ui.Separator())
        for item in footer_block():
            container.add_item(item)
        view.add_item(container)

        try:
            await channel.send(view=view, allowed_mentions=discord.AllowedMentions(users=True))
        except discord.HTTPException as ex:
            log.error("Failed to announce giveaway winner for %s: %s", row["giveaway_id"], ex)

        if row["message_id"]:
            try:
                msg = await channel.fetch_message(row["message_id"])
                ended_view = _layout(f"{e('giveaway')} Giveaway Ended", f"**Prize:** {row['prize']}\n**Winner(s):** {winner_mentions}")
                await msg.edit(view=ended_view)
            except discord.HTTPException:
                pass

    @tasks.loop(seconds=config.GIVEAWAY_CHECK_INTERVAL)
    async def giveaway_checker(self):
        now = time.time()
        rows = await db.raw_fetch("SELECT * FROM giveaways WHERE ended=0 AND ends_at <= ?", (now,))
        for row in rows:
            await self._end_giveaway(row)

    @giveaway_checker.before_loop
    async def _before_giveaway_checker(self):
        await self.bot.wait_until_ready()

    async def _end_poll(self, row):
        e = emoji_manager.get
        guild = self.bot.get_guild(row["guild_id"])
        channel = guild.get_channel(row["channel_id"]) if guild else None
        await db.raw_execute("UPDATE polls SET ended=1 WHERE poll_id=?", (row["poll_id"],))

        if not channel:
            return

        options = json.loads(row["options"])
        votes = json.loads(row["votes"])
        results = self._format_poll_results(options, votes)

        view = _layout(f"{e('poll')} Poll Ended", f"**{row['question']}**\n\n{results}")
        try:
            if row["message_id"]:
                try:
                    msg = await channel.fetch_message(row["message_id"])
                    await msg.edit(view=view)
                except discord.HTTPException:
                    await channel.send(view=view)
            else:
                await channel.send(view=view)
        except discord.HTTPException:
            pass

    @tasks.loop(seconds=config.GIVEAWAY_CHECK_INTERVAL)
    async def poll_checker(self):
        now = time.time()
        rows = await db.raw_fetch("SELECT * FROM polls WHERE ended=0 AND ends_at IS NOT NULL AND ends_at <= ?", (now,))
        for row in rows:
            await self._end_poll(row)

    @poll_checker.before_loop
    async def _before_poll_checker(self):
        await self.bot.wait_until_ready()

    def _format_poll_results(self, options: list, votes: dict) -> str:
        counts = {opt: 0 for opt in options}
        for voted_option in votes.values():
            if voted_option in counts:
                counts[voted_option] += 1
        total = sum(counts.values())
        lines = []
        for opt in options:
            count = counts[opt]
            pct = (count / total * 100) if total else 0
            bar_len = int(pct / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(f"**{opt}**\n`{bar}` {count} votes ({pct:.0f}%)")
        return "\n\n".join(lines)

    @commands.group(name="giveaway", aliases=["gstart"], invoke_without_command=True, help="Start a timed giveaway. Usage: giveaway start <duration> <winners> <prize>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def giveaway(self, ctx: commands.Context, duration: Optional[DurationConverter] = None, winners: Optional[int] = None, *, prize: Optional[str] = None):
        e = emoji_manager.get
        if duration is None or winners is None or prize is None:
            return await ctx.send(view=error_layout(
                "Missing Arguments",
                "Usage: `giveaway start <duration> <winners> <prize>`\nExample: `giveaway start 10m 1 Nitro`",
            ))
        await self._start_giveaway(ctx, duration, winners, prize)

    @giveaway.command(name="start", help="Start a timed giveaway. Usage: giveaway start <duration> <winners> <prize>")
    @has_guild_permission("manage_guild")
    async def giveaway_start(self, ctx: commands.Context, duration: DurationConverter, winners: int, *, prize: str):
        await self._start_giveaway(ctx, duration, winners, prize)

    async def _start_giveaway(self, ctx: commands.Context, duration: int, winners: int, prize: str):
        e = emoji_manager.get
        if winners < 1:
            return await ctx.send(view=error_layout("Invalid", "Winner count must be at least 1."))

        giveaway_id = str(uuid.uuid4())[:8].upper()
        ends_at = time.time() + duration

        body = (
            f"Click the button below to enter!\n\n"
            f"**Winners:** {winners}\n**Ends:** <t:{int(ends_at)}:R>\n**Hosted by:** {ctx.author.mention}\n\n"
            f"-# Use the message ID of this giveaway with `gend`, `greroll`, or `ginfo`."
        )
        panel = build_giveaway_panel(giveaway_id, prize, body)
        msg = await ctx.send(view=panel)

        await db.raw_execute(
            "INSERT INTO giveaways (giveaway_id, guild_id, channel_id, message_id, prize, winner_count, ends_at, host_id, ended)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (giveaway_id, ctx.guild.id, ctx.channel.id, msg.id, prize, winners, ends_at, ctx.author.id),
        )
        await ctx.send(view=success_layout(
            f"{e('check')} Giveaway Started",
            f"**Message ID:** `{msg.id}`\nUse this ID with `grequire`, `gbonus`, `gend`, `greroll`, or `ginfo`.",
        ), delete_after=30)

    @commands.command(name="grequire", help="Require a role to enter a giveaway. Usage: grequire <message_id> <role>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def grequire(self, ctx: commands.Context, message_id: str, role: Optional[discord.Role] = None):
        e = emoji_manager.get
        row = await _resolve_giveaway(ctx, message_id)
        if not row or row["ended"]:
            return await ctx.send(view=error_layout("Not Found", "No active giveaway found with that message ID."))

        role_id = role.id if role else None
        await db.raw_execute("UPDATE giveaways SET required_role_id=? WHERE giveaway_id=?", (role_id, row["giveaway_id"]))

        if role:
            await ctx.send(view=success_layout(f"{e('check')} Requirement Set", f"Entrants must now have {role.mention} to join **{row['prize']}**."))
        else:
            await ctx.send(view=success_layout(f"{e('check')} Requirement Removed", f"Role requirement removed from **{row['prize']}**."))

    @commands.command(name="gbonus", help="Give a role bonus entries (chance multiplier). Usage: gbonus <message_id> <role> <extra_entries>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def gbonus(self, ctx: commands.Context, message_id: str, role: discord.Role, extra_entries: int):
        e = emoji_manager.get
        row = await _resolve_giveaway(ctx, message_id)
        if not row or row["ended"]:
            return await ctx.send(view=error_layout("Not Found", "No active giveaway found with that message ID."))

        if extra_entries < 0:
            return await ctx.send(view=error_layout("Invalid", "Extra entries must be 0 or greater."))

        if extra_entries == 0:
            await db.raw_execute(
                "DELETE FROM giveaway_bonus_roles WHERE giveaway_id=? AND role_id=?", (row["giveaway_id"], role.id)
            )
            return await ctx.send(view=success_layout(f"{e('check')} Bonus Removed", f"Removed bonus entries for {role.mention}."))

        await db.raw_execute(
            "INSERT INTO giveaway_bonus_roles (giveaway_id, role_id, bonus_entries) VALUES (?, ?, ?)"
            " ON CONFLICT(giveaway_id, role_id) DO UPDATE SET bonus_entries=excluded.bonus_entries",
            (row["giveaway_id"], role.id, extra_entries),
        )
        await ctx.send(view=success_layout(
            f"{e('check')} Bonus Entries Set",
            f"Members with {role.mention} now get **+{extra_entries}** extra entries (total `{extra_entries + 1}`x chance) in **{row['prize']}**.",
        ))

    @commands.command(name="gminage", help="Set a minimum account age to enter a giveaway. Usage: gminage <message_id> <days>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def gminage(self, ctx: commands.Context, message_id: str, days: int):
        e = emoji_manager.get
        row = await _resolve_giveaway(ctx, message_id)
        if not row or row["ended"]:
            return await ctx.send(view=error_layout("Not Found", "No active giveaway found with that message ID."))

        days = max(0, days)
        await db.raw_execute("UPDATE giveaways SET min_account_age_days=? WHERE giveaway_id=?", (days, row["giveaway_id"]))
        if days:
            await ctx.send(view=success_layout(f"{e('check')} Minimum Age Set", f"Accounts must be at least **{days}** day(s) old to enter **{row['prize']}**."))
        else:
            await ctx.send(view=success_layout(f"{e('check')} Minimum Age Removed", f"Account age requirement removed from **{row['prize']}**."))

    @commands.command(name="greroll", help="Reroll the winner of a completed giveaway. Usage: greroll <message_id>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def greroll(self, ctx: commands.Context, message_id: str):
        e = emoji_manager.get
        row = await _resolve_giveaway(ctx, message_id)
        if not row:
            return await ctx.send(view=error_layout(f"{e('cross')} Not Found", "No giveaway found with that message ID."))

        entries = await db.raw_fetch("SELECT user_id FROM giveaway_entries WHERE giveaway_id=?", (row["giveaway_id"],))
        user_ids = [r["user_id"] for r in entries]
        if not user_ids:
            return await ctx.send(view=error_layout(f"{e('cross')} No Entries", "No one entered this giveaway."))

        bonus_rows = await db.raw_fetch(
            "SELECT role_id, bonus_entries FROM giveaway_bonus_roles WHERE giveaway_id=?", (row["giveaway_id"],)
        )
        weighted_pool = self._get_weighted_entries(user_ids, ctx.guild, row["giveaway_id"], bonus_rows)
        new_winner = random.choice(weighted_pool)

        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=SUCCESS)
        container.add_item(discord.ui.TextDisplay(f"## {e('giveaway')} Reroll!\n<@{new_winner}>"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"New winner for **{row['prize']}**: <@{new_winner}>"))
        container.add_item(discord.ui.Separator())
        for item in footer_block():
            container.add_item(item)
        view.add_item(container)

        await ctx.send(view=view, allowed_mentions=discord.AllowedMentions(users=True))

    @commands.command(name="gend", help="End a giveaway early. Usage: gend <message_id>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def gend(self, ctx: commands.Context, message_id: str):
        e = emoji_manager.get
        row = await _resolve_giveaway(ctx, message_id)
        if not row or row["ended"]:
            return await ctx.send(view=error_layout(f"{e('cross')} Not Found", "No active giveaway found with that message ID."))
        await self._end_giveaway(row)
        await ctx.send(view=success_layout(f"{e('check')} Giveaway Ended", "The giveaway has been ended early."))

    @commands.command(name="gcancel", help="Cancel a giveaway without picking a winner. Usage: gcancel <message_id>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def gcancel(self, ctx: commands.Context, message_id: str):
        e = emoji_manager.get
        row = await _resolve_giveaway(ctx, message_id)
        if not row or row["ended"]:
            return await ctx.send(view=error_layout(f"{e('cross')} Not Found", "No active giveaway found with that message ID."))

        confirm = ConfirmLayout(
            f"{e('cross')} Confirm Cancel",
            f"Cancel giveaway for **{row['prize']}** without picking a winner?",
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "Giveaway was not cancelled."))

        await db.raw_execute("UPDATE giveaways SET ended=1 WHERE giveaway_id=?", (row["giveaway_id"],))
        guild = ctx.guild
        channel = guild.get_channel(row["channel_id"])
        if channel and row["message_id"]:
            try:
                gmsg = await channel.fetch_message(row["message_id"])
                await gmsg.edit(view=_layout(f"{e('cross')} Giveaway Cancelled", f"**{row['prize']}**\n\nThis giveaway was cancelled by a moderator.", color=ERROR))
            except discord.HTTPException:
                pass
        await msg.edit(view=success_layout(f"{e('check')} Cancelled", "The giveaway has been cancelled."))

    @commands.command(name="ginfo", help="View full details about a giveaway. Usage: ginfo <message_id>")
    @commands.guild_only()
    async def ginfo(self, ctx: commands.Context, message_id: str):
        e = emoji_manager.get
        row = await _resolve_giveaway(ctx, message_id)
        if not row:
            return await ctx.send(view=error_layout(f"{e('cross')} Not Found", "No giveaway found with that message ID."))

        entries = await db.raw_fetchone("SELECT COUNT(*) as c FROM giveaway_entries WHERE giveaway_id=?", (row["giveaway_id"],))
        entry_count = entries["c"] if entries else 0

        bonus_rows = await db.raw_fetch(
            "SELECT role_id, bonus_entries FROM giveaway_bonus_roles WHERE giveaway_id=?", (row["giveaway_id"],)
        )
        bonus_text = ", ".join(f"<@&{b['role_id']}> (+{b['bonus_entries']})" for b in bonus_rows) or "None"
        required_text = f"<@&{row['required_role_id']}>" if row["required_role_id"] else "None"
        status = "🔴 Ended" if row["ended"] else "🟢 Active"

        body = (
            f"**Status:** {status}\n"
            f"**Message ID:** `{row['message_id']}`\n"
            f"**Host:** <@{row['host_id']}>\n"
            f"**Winners:** `{row['winner_count']}`\n"
            f"**Entries:** `{entry_count}`\n"
            f"**Ends:** <t:{int(row['ends_at'])}:R>\n"
            f"**Required Role:** {required_text}\n"
            f"**Minimum Account Age:** `{row['min_account_age_days']}` day(s)\n"
            f"**Bonus Roles:** {bonus_text}"
        )
        await ctx.send(view=info_layout(f"{e('giveaway')} {row['prize']}", body))

    @commands.command(name="glist", help="List all active giveaways in this server.")
    @commands.guild_only()
    async def glist(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await db.raw_fetch("SELECT * FROM giveaways WHERE guild_id=? AND ended=0 ORDER BY ends_at ASC", (ctx.guild.id,))
        if not rows:
            return await ctx.send(view=info_layout(f"{e('giveaway')} Active Giveaways", "No active giveaways in this server."))

        lines = [
            f"**{r['prize']}**\n-# Message ID: `{r['message_id']}` · Ends <t:{int(r['ends_at'])}:R> · `{r['winner_count']}` winner(s)"
            for r in rows[:10]
        ]
        await ctx.send(view=info_layout(f"{e('giveaway')} Active Giveaways ({len(rows)})", "\n\n".join(lines)))

    @commands.command(name="gentries", help="View who has entered a giveaway. Usage: gentries <message_id>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def gentries(self, ctx: commands.Context, message_id: str):
        e = emoji_manager.get
        row = await _resolve_giveaway(ctx, message_id)
        if not row:
            return await ctx.send(view=error_layout(f"{e('cross')} Not Found", "No giveaway found with that message ID."))

        entries = await db.raw_fetch("SELECT user_id FROM giveaway_entries WHERE giveaway_id=?", (row["giveaway_id"],))
        if not entries:
            return await ctx.send(view=info_layout(f"{e('members')} Entries", f"No one has entered **{row['prize']}** yet."))

        lines = [f"<@{r['user_id']}>" for r in entries[:30]]
        extra = f"\n\n...and {len(entries) - 30} more" if len(entries) > 30 else ""
        await ctx.send(view=info_layout(f"{e('members')} Entries for {row['prize']} ({len(entries)})", ", ".join(lines) + extra))

    @commands.command(name="poll", help="Create a poll with up to 10 options separated by |.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def poll(self, ctx: commands.Context, question: str, *, options: str):
        e = emoji_manager.get
        option_list = [o.strip() for o in options.split("|") if o.strip()]
        if len(option_list) < 2 or len(option_list) > 10:
            return await ctx.send(view=error_layout("Invalid Options", "Provide 2-10 options separated by `|`."))

        poll_id = str(uuid.uuid4())[:8].upper()
        panel = build_poll_panel(poll_id, question, option_list)
        msg = await ctx.send(view=panel)

        await db.raw_execute(
            "INSERT INTO polls (poll_id, guild_id, channel_id, message_id, question, options, votes, ends_at, ended)"
            " VALUES (?, ?, ?, ?, ?, ?, '{}', NULL, 0)",
            (poll_id, ctx.guild.id, ctx.channel.id, msg.id, question, json.dumps(option_list)),
        )

    @commands.command(name="pollresults", help="View the current results of a poll. Usage: pollresults <message_id>")
    @commands.guild_only()
    async def pollresults(self, ctx: commands.Context, message_id: str):
        e = emoji_manager.get
        if message_id.isdigit():
            row = await db.raw_fetchone("SELECT * FROM polls WHERE message_id=? AND guild_id=?", (int(message_id), ctx.guild.id))
        else:
            row = await db.raw_fetchone("SELECT * FROM polls WHERE poll_id=? AND guild_id=?", (message_id.upper(), ctx.guild.id))

        if not row:
            return await ctx.send(view=error_layout(f"{e('cross')} Not Found", "No poll found with that message ID."))

        options = json.loads(row["options"])
        votes = json.loads(row["votes"])
        results = self._format_poll_results(options, votes)
        await ctx.send(view=info_layout(f"{e('poll')} {row['question']}", results))


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaways(bot))
