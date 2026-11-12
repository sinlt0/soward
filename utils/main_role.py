import discord

from utils import security_settings as settings


async def get(guild: discord.Guild) -> discord.Role:
    for module, key in (("security", "main_role_id"), ("verification", "role_id")):
        value = await settings.get(guild.id, module, key)
        if value:
            role = guild.get_role(int(value))
            if role is not None:
                return role
    return guild.default_role


async def label(guild: discord.Guild) -> str:
    role = await get(guild)
    return "@everyone" if role.is_default() else role.mention
