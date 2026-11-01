import config
from utils import guild_settings

MIN_MEMBERS = 500
KEY = "size_gate_override"


async def overridden(guild_id: int) -> bool:
    return bool(await guild_settings.get(guild_id, KEY, False))


async def set_override(guild_id: int, value: bool) -> None:
    if value:
        await guild_settings.set(guild_id, KEY, True)
    else:
        await guild_settings.delete(guild_id, KEY)


async def allowed(guild) -> bool:
    if (guild.member_count or 0) >= MIN_MEMBERS:
        return True
    return await overridden(guild.id)


def is_privileged(user_id: int) -> bool:
    return user_id in config.ALL_PRIVILEGED_IDS


def blocked_text(guild, feature: str) -> str:
    return (f"**{feature}** is only available in servers with **{MIN_MEMBERS}+ members** because it watches a lot of activity. "
            f"This server has **{guild.member_count or 0}**. The bot owner or a developer can switch it on for you if you need it.")
