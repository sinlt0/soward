import asyncio
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import badges as store, emoji_manager, scheduler
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

NO_MENTIONS = discord.AllowedMentions.none()
USAGE = ("Use `badge create <name> | @role | <period starts> | <period ends> [| <claim until>]`\n"
         "Example: `badge create Valentine 2026 | @Valentine 2026 | 1 feb 2026 00:00 | 15 feb 2026 00:00 | in 14d`\n"
         "Members who joined before the period ended can claim the role permanently until the claim window closes. "
         "If you leave the claim time out, a period that has not ended yet can be claimed until it ends.")


def badge_layout(badge: dict, claimed: int) -> discord.ui.LayoutView:
    state = store.claim_state(badge, time.time())
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=0xEB459E if state == "open" else 0x95A5A6)
    lines = [f"## {badge['name']}", f"Were you part of the server during **{badge['name']}**? Claim <@&{badge['role_id']}> and keep it forever.",
             f"\n**Period:** <t:{int(badge['period_start'])}:D> to <t:{int(badge['period_end'])}:D>",
             f"**Claim until:** <t:{int(badge['claim_until'])}:F> (<t:{int(badge['claim_until'])}:R>)",
             f"**Claimed so far:** {claimed}"]
    if state == "closed":
        lines.append("\n**The claim window has closed.**")
    container.add_item(discord.ui.TextDisplay("\n".join(lines)))
    if state == "open":
        row = discord.ui.ActionRow()
        row.add_item(discord.ui.Button(label="Claim role", style=discord.ButtonStyle.success, custom_id=f"badge:claim:{badge['badge_id']}"))
        container.add_item(row)
    view.add_item(container)
    return view


class Badges(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    async def refresh(self, guild: discord.Guild, badge: dict) -> None:
        if not badge.get("channel_id") or not badge.get("message_id"):
            return
        channel = guild.get_channel(badge["channel_id"])
        if channel is None:
            return
        try:
            message = await channel.fetch_message(badge["message_id"])
            await message.edit(view=badge_layout(badge, await store.claim_count(badge["badge_id"])), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass

    @tasks.loop(minutes=1)
    async def loop(self):
        for badge in await store.open_overdue(time.time()):
            await store.update(badge["badge_id"], closed=1)
            badge["closed"] = 1
            guild = self.bot.get_guild(badge["guild_id"])
            if guild is not None:
                await self.refresh(guild, badge)

    @loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await store.drop_role(role.guild.id, role.id)

    def _role_problem(self, guild: discord.Guild, role: discord.Role) -> Optional[str]:
        if role.is_default() or role.managed:
            return "That role cannot be used."
        if role >= guild.me.top_role:
            return "That role is at or above my top role."
        if role.permissions.administrator or role.permissions.manage_guild or role.permissions.manage_roles:
            return "That role carries dangerous permissions."
        return None

    async def give(self, guild: discord.Guild, member: discord.Member, badge: dict, reason: str) -> str:
        role = guild.get_role(badge["role_id"])
        if role is None:
            return "missing"
        if await store.claimed(badge["badge_id"], member.id):
            return "claimed"
        if not store.eligible(member.joined_at.timestamp() if member.joined_at else None, badge):
            return "ineligible"
        if role not in member.roles:
            try:
                await member.add_roles(role, reason=reason)
            except discord.HTTPException:
                return "failed"
        await store.record(badge["badge_id"], member.id)
        return "given"

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if not custom_id.startswith("badge:claim:"):
            return
        guild, member = interaction.guild, interaction.user
        badge = await store.get(guild.id, custom_id.split(":", 2)[2])
        if badge is None or guild.get_role(badge["role_id"]) is None:
            return await interaction.response.send_message("This badge no longer exists.", ephemeral=True)
        if store.claim_state(badge, time.time()) != "open":
            return await interaction.response.send_message("The claim window has closed.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        result = await self.give(guild, member, badge, f"Commemorative role {badge['name']}")
        text = {
            "given": f"You got <@&{badge['role_id']}>. It is yours permanently.",
            "claimed": "You already claimed this one.",
            "ineligible": f"You joined after this period ended (<t:{int(badge['period_end'])}:D>), so you cannot claim it.",
            "failed": "I could not give you the role. Tell a moderator.",
            "missing": "This badge no longer exists.",
        }[result]
        await interaction.followup.send(text, ephemeral=True)
        if result == "given":
            await self.refresh(guild, badge)

    @commands.group(name="badge", aliases=["badges", "memento"], invoke_without_command=True, help="Permanent roles for members who were here during a period.")
    @commands.guild_only()
    @has_guild_permission("manage_roles")
    async def badge(self, ctx: commands.Context):
        await ctx.send(view=info_layout("Commemorative roles", USAGE + "\n\n`badge panel <id> [#channel]` · `badge grant <id>` · `badge list` · `badge extend <id> <when>` · `badge delete <id>`"))

    @badge.command(name="create", help="Create a commemorative role. See `badge` for the format.")
    @has_guild_permission("manage_roles")
    async def badge_create(self, ctx: commands.Context, *, details: str = ""):
        parts = [p.strip() for p in details.split("|")]
        if len(parts) not in (4, 5) or not all(parts):
            return await ctx.send(view=error_layout("Missing details", USAGE))
        try:
            role = await commands.RoleConverter().convert(ctx, parts[1])
        except commands.BadArgument:
            return await ctx.send(view=error_layout("Unknown role", "Mention the role or use its exact name. Create it first, then run this again."))
        problem = self._role_problem(ctx.guild, role)
        if problem:
            return await ctx.send(view=error_layout("Cannot use that role", problem))
        tz = scheduler.parse_tz((await scheduler.get_config(ctx.guild.id))["timezone"]) or scheduler.parse_tz("UTC")
        now = time.time()
        start = scheduler.parse_when(parts[2], now, tz)
        end = scheduler.parse_when(parts[3], now, tz)
        if start is None or end is None or end <= start:
            return await ctx.send(view=error_layout("I could not read the period", "Give both dates with the year, for example `1 feb 2026 00:00` and `15 feb 2026 00:00`. The end must be after the start."))
        if len(parts) == 5:
            claim = scheduler.parse_when(parts[4], now, tz)
        else:
            claim = end if end > now else None
        if claim is None or claim <= now:
            return await ctx.send(view=error_layout("Claim window needed", "That period is over, so add when claiming closes as a fifth part, for example `| in 14d`."))
        badge_id = await store.create(ctx.guild.id, parts[0], role.id, start, end, claim, ctx.author.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Commemorative role", f"`{badge_id}` · **{parts[0]}** · {role.mention}\nPeriod <t:{int(start)}:D> to <t:{int(end)}:D>. Claiming closes <t:{int(claim)}:F>.\nPost the claim panel with `badge panel {badge_id}`, or give it to everyone eligible with `badge grant {badge_id}`."), allowed_mentions=NO_MENTIONS)

    @badge.command(name="panel", help="Post the claim panel.")
    @has_guild_permission("manage_roles")
    async def badge_panel(self, ctx: commands.Context, badge_id: str, channel: Optional[discord.TextChannel] = None):
        badge = await store.get(ctx.guild.id, badge_id)
        if badge is None:
            return await ctx.send(view=error_layout("Not found", "No badge with that id. Use `badge list`."))
        channel = channel or ctx.channel
        try:
            message = await channel.send(view=badge_layout(badge, await store.claim_count(badge["badge_id"])), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            return await ctx.send(view=error_layout("Could not post", f"I cannot send messages in {channel.mention}."))
        await store.update(badge["badge_id"], channel_id=channel.id, message_id=message.id)

    @badge.command(name="grant", help="Give the role to every member who was here during the period, right now.")
    @has_guild_permission("administrator")
    async def badge_grant(self, ctx: commands.Context, badge_id: str):
        badge = await store.get(ctx.guild.id, badge_id)
        if badge is None:
            return await ctx.send(view=error_layout("Not found", "No badge with that id."))
        targets = [m for m in ctx.guild.members if not m.bot and store.eligible(m.joined_at.timestamp() if m.joined_at else None, badge)]
        if not targets:
            return await ctx.send(view=info_layout("Nobody eligible", "No current member joined before this period ended."))
        await ctx.send(view=info_layout("Granting", f"Giving the role to **{len(targets)}** member(s). This takes about {int(len(targets) * 0.6) // 60 + 1} minute(s)."))
        counts = {"given": 0, "claimed": 0, "failed": 0, "ineligible": 0, "missing": 0}
        for member in targets:
            result = await self.give(ctx.guild, member, badge, f"Commemorative role {badge['name']} granted by {ctx.author}")
            counts[result] += 1
            if result == "missing":
                break
            await asyncio.sleep(0.6)
        await self.refresh(ctx.guild, badge)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Done", f"Given: **{counts['given']}** · already had it: **{counts['claimed']}** · failed: **{counts['failed']}**."))

    @badge.command(name="list", help="List commemorative roles.")
    async def badge_list(self, ctx: commands.Context):
        rows = await store.listing(ctx.guild.id)
        if not rows:
            return await ctx.send(view=info_layout("Commemorative roles", "None yet."))
        lines = [f"`{r['badge_id']}` **{r['name']}** · <@&{r['role_id']}> · {store.claim_state(r, time.time())} · {await store.claim_count(r['badge_id'])} claimed" for r in rows]
        await ctx.send(view=info_layout("Commemorative roles", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @badge.command(name="extend", help="Reopen claiming until a new time. Usage: badge extend <id> <when>")
    @has_guild_permission("manage_roles")
    async def badge_extend(self, ctx: commands.Context, badge_id: str, *, when: str):
        badge = await store.get(ctx.guild.id, badge_id)
        if badge is None:
            return await ctx.send(view=error_layout("Not found", "No badge with that id."))
        tz = scheduler.parse_tz((await scheduler.get_config(ctx.guild.id))["timezone"]) or scheduler.parse_tz("UTC")
        claim = scheduler.parse_when(when, time.time(), tz)
        if claim is None or claim <= time.time():
            return await ctx.send(view=error_layout("Invalid time", "Use a future time like `in 7d` or `1 mar 2026 00:00`."))
        await store.update(badge["badge_id"], claim_until=claim, closed=0)
        badge.update(claim_until=claim, closed=0)
        await self.refresh(ctx.guild, badge)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Commemorative role", f"Claiming is open until <t:{int(claim)}:F>."))

    @badge.command(name="delete", help="Delete a badge. Members keep the role.")
    @has_guild_permission("manage_roles")
    async def badge_delete(self, ctx: commands.Context, badge_id: str):
        badge = await store.get(ctx.guild.id, badge_id)
        if badge is None:
            return await ctx.send(view=error_layout("Not found", "No badge with that id."))
        await store.delete(badge["badge_id"])
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Commemorative role", "Deleted. Members who already have the role keep it."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Badges(bot))
