import time

import config
from utils import db
from utils.components import error_layout


async def is_premium(guild_id: int) -> bool:
    row = await db.raw_fetchone("SELECT premium, premium_expires_at FROM guilds WHERE guild_id=?", (guild_id,))
    if not row or not row["premium"]:
        return False
    expires = row["premium_expires_at"]
    return expires is None or expires > time.time()


def tiers(key: str) -> tuple[int, int]:
    free, premium, _ = config.PREMIUM_LIMITS[key]
    return free, premium


async def get(guild_id: int, key: str) -> int:
    free, premium = tiers(key)
    return premium if await is_premium(guild_id) else free


LIST_KEYS = {
    "antiraid.name_filter": "antiraid_patterns",
    "automod.banned_words": "automod_words",
    "automod.link_blocklist": "automod_domains",
    "automod.link_allowlist": "automod_domains",
    "automod.exempt_channels": "automod_exempt",
    "automod.exempt_roles": "automod_exempt",
}


async def list_cap(guild_id: int, setting) -> int:
    key = LIST_KEYS.get(setting.path)
    if key is None:
        return int(setting.hi or 100)
    return await get(guild_id, key)


async def hint(guild_id: int, key: str) -> str:
    free, premium = tiers(key)
    if await is_premium(guild_id):
        return ""
    return f" Premium raises this to {premium}."


async def gate(ctx, feature: str) -> bool:
    if await is_premium(ctx.guild.id):
        return True
    await ctx.send(view=error_layout("Premium feature", f"{feature} is a Premium feature. Run `{ctx.clean_prefix}premium` to see how to unlock it, or `{ctx.clean_prefix}premium buy` to pay with crypto."))
    return False
