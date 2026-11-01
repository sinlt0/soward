import discord
from discord.ext import commands

from utils import emoji_manager, size_gate
from utils.components import error_layout, info_layout, success_layout


class SizeGate(commands.Cog):
    category = "Utility"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="sizegate", invoke_without_command=True, help="See whether heavy features are available in this server.")
    @commands.guild_only()
    async def sizegate(self, ctx: commands.Context):
        count = ctx.guild.member_count or 0
        forced = await size_gate.overridden(ctx.guild.id)
        if count >= size_gate.MIN_MEMBERS:
            text = f"This server has **{count}** members, so member timeline and smart slowmode are available."
        elif forced:
            text = f"This server has **{count}** members. Member timeline and smart slowmode were switched on by the bot team."
        else:
            text = f"This server has **{count}** members. Member timeline and smart slowmode need **{size_gate.MIN_MEMBERS}**. The bot owner or a developer can switch them on."
        await ctx.send(view=info_layout("Large server features", text))

    @sizegate.command(name="on", help="Bot team only: allow heavy features in a small server. Usage: sizegate on [server_id]")
    async def sizegate_on(self, ctx: commands.Context, guild_id: int = 0):
        await self._toggle(ctx, guild_id, True)

    @sizegate.command(name="off", help="Bot team only: remove the override. Usage: sizegate off [server_id]")
    async def sizegate_off(self, ctx: commands.Context, guild_id: int = 0):
        await self._toggle(ctx, guild_id, False)

    async def _toggle(self, ctx: commands.Context, guild_id: int, value: bool):
        if not size_gate.is_privileged(ctx.author.id):
            return await ctx.send(view=error_layout("Not allowed", "Only the bot owner and developers can change this."))
        target = self.bot.get_guild(guild_id) if guild_id else ctx.guild
        if target is None:
            return await ctx.send(view=error_layout("Unknown server", "I am not in that server."))
        await size_gate.set_override(target.id, value)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Large server features", f"**{target.name}**: override is **{'on' if value else 'off'}**."))


async def setup(bot: commands.Bot):
    await bot.add_cog(SizeGate(bot))
