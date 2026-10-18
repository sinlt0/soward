import datetime
import time
from typing import Optional

import discord

from utils import cases
from utils import security_settings as settings
from utils.events_bus import LOG_EVENT, bus


async def active_count(guild_id: int, user_id: int) -> int:
    window = await settings.get(guild_id, "automod", "warn_window")
    cutoff = time.time() - window
    return sum(1 for warn in await cases.get_warns(guild_id, user_id) if warn["created_at"] >= cutoff)


async def apply(guild: discord.Guild, member: discord.Member) -> Optional[str]:
    gid = guild.id
    if not await settings.get(gid, "automod", "warn_ladder_enabled"):
        return None
    if member.id == guild.owner_id or member.top_role >= guild.me.top_role:
        return None
    count = await active_count(gid, member.id)
    steps = (
        ("ban", await settings.get(gid, "automod", "warn_ban_at")),
        ("kick", await settings.get(gid, "automod", "warn_kick_at")),
        ("timeout", await settings.get(gid, "automod", "warn_timeout_at")),
    )
    action = next((name for name, at in steps if at and count == at), None)
    if action is None:
        return None
    reason = f"Warning ladder: {count} warnings in the window"
    try:
        if action == "ban":
            await guild.ban(member, reason=reason, delete_message_days=0)
        elif action == "kick":
            await member.kick(reason=reason)
        else:
            seconds = await settings.get(gid, "automod", "warn_timeout_duration")
            await member.timeout(discord.utils.utcnow() + datetime.timedelta(seconds=seconds), reason=reason)
    except discord.HTTPException:
        return None
    await bus.publish(LOG_EVENT, guild_id=gid, action="warn_ladder", user_id=member.id, moderator_id=guild.me.id, reason=f"{reason} ({action})", case_id="N/A")
    return action
