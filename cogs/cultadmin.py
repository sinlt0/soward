from typing import Optional

import discord
from discord.ext import commands

from cogs.cultivation import NO_PINGS
from rpg import admin, chapters, engine as cult, gear, races, settings, ways
from utils import coins, emoji_manager
from utils.checks import is_owner
from utils.components import error_layout, info_layout, success_layout


class CultAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="cultadmin", aliases=["cadmin", "ca"], invoke_without_command=True, hidden=True, help="Owner tools for cultivation accounts.")
    @is_owner()
    async def cultadmin(self, ctx: commands.Context):
        e = emoji_manager.get
        realms = ", ".join(f"`{i}` {info['name']}" for i, info in enumerate(settings.REALMS))
        await ctx.send(view=info_layout(f"{e('ecult')} Cultivation owner tools", (
            "`cultadmin max <user> [path] [way]` gives a fully maxed account.\n"
            "`cultadmin realm <user> <realm> [stage] [qi]` sets the realm, stage and qi.\n"
            "`cultadmin path <user> <path>`, `way <user> <way>`, `race <user> <race>`\n"
            "`cultadmin root <user> <rarity> <element> <quality>`\n"
            "`cultadmin item <user> <item> [amount]` gives an item, pill, material or gear.\n"
            "`cultadmin chapter <user> <0-16>` jumps their main story to that chapter.\n"
            "`cultadmin show <user>` prints their numbers.\n\n"
            f"**Realms:** {realms}\n"
            "**Stages:** a number, a stage name, or `peak`.")))

    async def need_target(self, ctx: commands.Context, user: discord.User) -> bool:
        if user.bot:
            await ctx.send(view=error_layout("Not a cultivator", "Bots do not cultivate."))
            return False
        return True

    @cultadmin.command(name="max", aliases=["maxed", "full"], help="Give someone a fully maxed account. Usage: cultadmin max <user> [path] [way]")
    async def ca_max(self, ctx: commands.Context, user: discord.User, path: Optional[str] = None, way: Optional[str] = None):
        e = emoji_manager.get
        if not await self.need_target(ctx, user):
            return
        if path and path.lower() not in settings.PATHS:
            return await ctx.send(view=error_layout("Unknown path", "Paths: " + ", ".join(f"`{p}`" for p in settings.PATHS)))
        if way and way.lower() not in ways.WAYS:
            return await ctx.send(view=error_layout("Unknown way", "Ways: " + ", ".join(f"`{w}`" for w in ways.WAYS)))
        character = await admin.max_account(user.id, path.lower() if path else None, way.lower() if way else None)
        await ctx.send(view=success_layout(f"{e('ecult')} Maxed", (
            f"{user.mention} is now **{cult.stage_name(character)}** on the **{cult.path_info(character)['name']}** path, with the best gear refined to +5 and enchanted, "
            f"{admin.MAX_MATERIALS} of every material, {admin.MAX_PILLS} of every pill, all bonds, every relic, every title and the whole main story.")), allowed_mentions=NO_PINGS)

    @cultadmin.command(name="realm", aliases=["level", "stage", "setrealm"], help="Set a realm, stage and qi. Usage: cultadmin realm <user> <realm> [stage] [qi]")
    async def ca_realm(self, ctx: commands.Context, user: discord.User, realm: str, stage: str = "1", qi: Optional[int] = None):
        e = emoji_manager.get
        if not await self.need_target(ctx, user):
            return
        index = admin.realm_index(realm)
        if index is None:
            return await ctx.send(view=error_layout("Unknown realm", "Use a number from 0 or a realm name. Run `cultadmin` to list them."))
        position = admin.stage_index(index, stage)
        if position is None:
            return await ctx.send(view=error_layout("Unknown stage", f"That realm has {len(settings.REALMS[index]['stages'])} stages. Use a number, a name or `peak`."))
        character = await admin.set_progress(user.id, index, position, qi)
        await ctx.send(view=success_layout(f"{e('ecult')} Realm set", f"{user.mention} is now **{cult.stage_name(character)}** with **{coins.fmt(character['qi'])}** qi."), allowed_mentions=NO_PINGS)

    @cultadmin.command(name="path", help="Set someone's path. Usage: cultadmin path <user> <path>")
    async def ca_path(self, ctx: commands.Context, user: discord.User, path: str):
        if not await self.need_target(ctx, user):
            return
        if not await admin.set_path(user.id, path.lower()):
            return await ctx.send(view=error_layout("Unknown path", "Paths: " + ", ".join(f"`{p}`" for p in settings.PATHS)))
        await ctx.send(view=success_layout("Path set", f"{user.mention} now walks the **{settings.PATHS[path.lower()]['name']}** path."), allowed_mentions=NO_PINGS)

    @cultadmin.command(name="way", help="Set someone's way. Usage: cultadmin way <user> <way>")
    async def ca_way(self, ctx: commands.Context, user: discord.User, way: str):
        if not await self.need_target(ctx, user):
            return
        if not await admin.set_way(user.id, way.lower()):
            return await ctx.send(view=error_layout("Unknown way", "Ways: " + ", ".join(f"`{w}`" for w in ways.WAYS)))
        await ctx.send(view=success_layout("Way set", f"{user.mention} now follows the **{ways.WAYS[way.lower()]['name']}** way."), allowed_mentions=NO_PINGS)

    @cultadmin.command(name="race", help="Set someone's race. Usage: cultadmin race <user> <race>")
    async def ca_race(self, ctx: commands.Context, user: discord.User, race: str):
        if not await self.need_target(ctx, user):
            return
        if not await admin.set_race(user.id, race.lower()):
            return await ctx.send(view=error_layout("Unknown race", "Races: " + ", ".join(f"`{r}`" for r in races.RACES)))
        await ctx.send(view=success_layout("Race set", f"{user.mention} is now **{races.RACES[race.lower()]['name']}**."), allowed_mentions=NO_PINGS)

    @cultadmin.command(name="root", help="Set a spiritual root. Usage: cultadmin root <user> <common|rare|legendary> <element> <mortal|spirit|earth|heaven>")
    async def ca_root(self, ctx: commands.Context, user: discord.User, rarity: str, element: str, quality: str):
        if not await self.need_target(ctx, user):
            return
        if not await admin.set_root(user.id, rarity.lower(), element, quality):
            names = "; ".join(f"{key}: {', '.join(info['names'])}" for key, info in settings.ROOTS.items())
            return await ctx.send(view=error_layout("Bad root", f"{names}\nQualities: " + ", ".join(q["name"] for q in settings.QUALITIES)))
        await ctx.send(view=success_layout("Root set", f"{user.mention}'s spiritual root was changed."), allowed_mentions=NO_PINGS)

    @cultadmin.command(name="item", aliases=["give", "grant"], help="Give an item. Usage: cultadmin item <user> <item> [amount]")
    async def ca_item(self, ctx: commands.Context, user: discord.User, item: str, amount: int = 1):
        if not await self.need_target(ctx, user):
            return
        key = item.lower().replace("-", "_")
        for table in (settings.ITEMS, settings.BREWS, gear.MATERIALS):
            match = next((k for k, v in table.items() if key == k or key == v["name"].lower().replace(" ", "_")), None)
            if match:
                key = match
                break
        if gear.parse(key) is None and not admin.item_valid(key):
            found = gear.find(item.replace("_", " "))
            if found:
                key = found
        if amount > 1000 or not await admin.give_item(user.id, key, amount):
            return await ctx.send(view=error_layout("Cannot give that", "Use an item key such as `qi_pill`, `beast_core`, `vigor_pill` or `weapon_3`, and an amount from 1 to 1000."))
        await ctx.send(view=success_layout("Given", f"Gave **{amount}** `{key}` to {user.mention}."), allowed_mentions=NO_PINGS)

    @cultadmin.command(name="chapter", aliases=["story"], help="Jump someone's main story. Usage: cultadmin chapter <user> <number>")
    async def ca_chapter(self, ctx: commands.Context, user: discord.User, number: int):
        if not await self.need_target(ctx, user):
            return
        if not 0 <= number <= chapters.TOTAL:
            return await ctx.send(view=error_layout("Bad chapter", f"Use a number from 0 to {chapters.TOTAL}. Zero restarts the story, {chapters.TOTAL} finishes it."))
        now = await admin.set_chapter(user.id, number)
        await ctx.send(view=success_layout("Story set", f"{user.mention} has finished **{now}** of {chapters.TOTAL} chapters."), allowed_mentions=NO_PINGS)

    @cultadmin.command(name="show", aliases=["info", "view"], help="Show someone's raw cultivation numbers. Usage: cultadmin show <user>")
    async def ca_show(self, ctx: commands.Context, user: discord.User):
        character = await cult.get(user.id)
        if character is None:
            return await ctx.send(view=error_layout("No character", "They have not awakened."))
        keys = ("race", "way", "path", "rarity", "root", "quality", "realm", "stage", "qi", "bonds", "safe", "weapon", "armor", "charm", "weapon_r", "armor_r", "charm_r", "weapon_e", "armor_e", "charm_e", "title")
        lines = [f"`{key}` = {character.get(key)!r}" for key in keys]
        await ctx.send(view=info_layout(f"{user.display_name}", "\n".join(lines)), allowed_mentions=NO_PINGS)


async def setup(bot: commands.Bot):
    await bot.add_cog(CultAdmin(bot))
