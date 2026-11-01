import discord
from discord.ext import commands

from utils import size_gate, timeline
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout

NO_MENTIONS = discord.AllowedMentions.none()


class Timeline(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="history", aliases=["timeline", "memberlog"], help="Everything staff know about a member in one list. Servers with 500+ members.")
    @commands.guild_only()
    @has_guild_permission("manage_messages")
    async def history(self, ctx: commands.Context, member: discord.Member | discord.User):
        if not await size_gate.allowed(ctx.guild):
            return await ctx.send(view=info_layout("Member timeline", size_gate.blocked_text(ctx.guild, "Member timeline")))
        events = await timeline.collect(ctx.guild.id, member.id)
        lines = [f"<t:{int(ts)}:d> {text}" for ts, text in events]
        facts = [f"**Account created:** <t:{int(member.created_at.timestamp())}:D>"]
        if isinstance(member, discord.Member) and member.joined_at:
            facts.append(f"**Joined:** <t:{int(member.joined_at.timestamp())}:D>")
        body = "\n".join(facts) + "\n\n" + ("\n".join(lines) if lines else "Nothing on record.")
        await ctx.send(view=info_layout(f"Timeline · {member}", body[:3800]), allowed_mentions=NO_MENTIONS)


async def setup(bot: commands.Bot):
    await bot.add_cog(Timeline(bot))
