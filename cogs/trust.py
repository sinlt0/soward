import discord
from discord.ext import commands

from utils import emoji_manager, trust
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

NO_MENTIONS = discord.AllowedMentions.none()


class Trust(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="trust", invoke_without_command=True, help="Show a member's trust score. Staff only.")
    @commands.guild_only()
    @has_guild_permission("manage_messages")
    async def trust(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        score, parts = await trust.gather(ctx.guild, member)
        rows = "\n".join(f"{'+' if v > 0 else ''}{v}  {name}" for name, v in parts)
        notes = await trust.adjustments(ctx.guild.id, member.id, 3)
        extra = ""
        if notes:
            extra = "\n\n**Recent adjustments**\n" + "\n".join(f"{n['delta']:+d} by <@{n['moderator_id']}>: {n['reason']}" for n in notes)
        e = emoji_manager.get
        await ctx.send(view=info_layout(f"{e('shield')} Trust · {member.display_name}", f"## {score}/100 · {trust.tier(score)}\n```\n{rows}\n```{extra}"), allowed_mentions=NO_MENTIONS)

    @trust.command(name="adjust", help="Add or remove trust points. Usage: trust adjust <member> <-50..50> <reason>")
    @has_guild_permission("moderate_members")
    async def trust_adjust(self, ctx: commands.Context, member: discord.Member, delta: int, *, reason: str):
        if not -50 <= delta <= 50 or delta == 0:
            return await ctx.send(view=error_layout("Invalid amount", "Use a number from -50 to 50, not 0."))
        await trust.adjust(ctx.guild.id, member.id, delta, reason, ctx.author.id)
        score, _ = await trust.gather(ctx.guild, member)
        await ctx.send(view=success_layout("Trust adjusted", f"{member.mention} is now **{score}/100** ({trust.tier(score)})."), allowed_mentions=NO_MENTIONS)

    @trust.command(name="low", help="Show the lowest-trust members among those who joined most recently.")
    @has_guild_permission("manage_messages")
    async def trust_low(self, ctx: commands.Context, limit: int = 10):
        limit = max(3, min(25, limit))
        pool = sorted((m for m in ctx.guild.members if not m.bot and m.joined_at), key=lambda m: m.joined_at, reverse=True)[:150]
        scored = []
        for m in pool:
            score, _ = await trust.gather(ctx.guild, m)
            scored.append((score, m))
        scored.sort(key=lambda x: x[0])
        lines = [f"`{s:>3}` {m.mention} · {trust.tier(s)}" for s, m in scored[:limit]]
        await ctx.send(view=info_layout("Lowest trust (150 newest members)", "\n".join(lines) or "No members."), allowed_mentions=NO_MENTIONS)


async def setup(bot: commands.Bot):
    await bot.add_cog(Trust(bot))
