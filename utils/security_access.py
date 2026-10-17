import discord
from discord.ext import commands

import config
from utils import guild_settings, security

LEVEL_NONE = 0
LEVEL_ADMIN = 1
LEVEL_TRUSTED = 2
LEVEL_OWNER = 3

LEVEL_NAMES = {
    LEVEL_NONE: "no access",
    LEVEL_ADMIN: "Administrator",
    LEVEL_TRUSTED: "Trusted Admin",
    LEVEL_OWNER: "Owner or Extra Owner",
}


async def level_of(guild: discord.Guild, member: discord.abc.User) -> int:
    if member.id in config.ALL_PRIVILEGED_IDS or member.id == guild.owner_id:
        return LEVEL_OWNER
    tier = await security.get_permit_tier(guild.id, member.id)
    if tier == config.SECURITY_TIER_EXTRA_OWNER:
        return LEVEL_OWNER
    if tier == config.SECURITY_TIER_TRUSTED_ADMIN:
        return LEVEL_TRUSTED
    if await security.is_quarantined(guild.id, member.id):
        return LEVEL_NONE
    perms = getattr(member, "guild_permissions", None)
    if perms is not None and perms.administrator:
        locked = await guild_settings.get(guild.id, "security_lock", config.SECURITY_LOCK_DEFAULT)
        return LEVEL_ADMIN if locked else LEVEL_TRUSTED
    return LEVEL_NONE


def security_access(required: int = LEVEL_TRUSTED):
    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        have = await level_of(ctx.guild, ctx.author)
        if have >= required:
            return True
        needed = LEVEL_NAMES[required]
        if required == LEVEL_OWNER:
            raise commands.CheckFailure("Only the server owner or an Extra Owner can do this.")
        raise commands.CheckFailure(
            f"Only the server owner, an Extra Owner or a Trusted Admin can change security settings. "
            f"The server owner can allow Administrators with `security lock off`. Required: {needed}."
        )

    return commands.check(predicate)


def security_owner():
    return security_access(LEVEL_OWNER)


def security_staff():
    return security_access(LEVEL_TRUSTED)
