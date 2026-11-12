import discord
from discord.ext import commands


def known_guild(ctx: commands.Context):
    guild = ctx.guild
    if guild is None or ctx.bot.get_guild(guild.id) is None:
        return None
    return guild


def is_user_install(interaction: discord.Interaction) -> bool:
    return interaction.is_user_integration()
