import hashlib
import json

import discord


def serialize(bot) -> list[dict]:
    out = []
    for command in bot.tree.get_commands():
        try:
            out.append(command.to_dict(bot.tree))
        except TypeError:
            out.append(command.to_dict())
    return out


def digest(bot) -> str:
    return hashlib.sha1(json.dumps(serialize(bot), sort_keys=True, default=str).encode()).hexdigest()


async def sync(bot) -> None:
    app_id = bot.application_id
    existing = await bot.http.get_global_commands(app_id)
    keep = [c for c in existing if c.get("type") == 4]
    await bot.http.bulk_upsert_global_commands(app_id, serialize(bot) + keep)
