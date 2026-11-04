import asyncio

import discord


async def resolve(bot, ids) -> tuple[dict[int, str], dict[int, str]]:
    names: dict[int, str] = {}
    usernames: dict[int, str] = {}
    gate = asyncio.Semaphore(8)

    async def one(user_id: int):
        user = bot.get_user(user_id)
        if user is None:
            async with gate:
                try:
                    user = await bot.fetch_user(user_id)
                except discord.HTTPException:
                    return
        names[user_id] = user.display_name
        usernames[user_id] = user.name

    await asyncio.gather(*(one(i) for i in ids))
    return names, usernames
