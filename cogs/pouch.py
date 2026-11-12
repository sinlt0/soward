from typing import Optional

from discord.ext import commands

from rpg import stones, engine as cult, gear, pouch
from utils import coins, emoji_manager
from utils.components import error_layout, info_layout, success_layout

KINDS = {"herb": "herb", "herbs": "herb", "herb pouch": "herb", "material": "material", "materials": "material", "ore": "material", "mats": "material", "material pouch": "material"}


def usage_bar(used: int, cap: int) -> str:
    filled = 0 if cap <= 0 else min(10, int(10 * used / cap))
    return "[" + "#" * filled + "-" * (10 - filled) + "]"


def pouch_lines(info: dict) -> list[str]:
    lines = []
    for kind, data in info.items():
        spec = gear.POUCHES[kind]
        nxt = gear.POUCH_TIERS[data["tier"]] if data["tier"] < len(gear.POUCH_TIERS) else None
        line = f"**{gear.pouch_name(kind, data['tier'])}** ({spec['zh']}) · holds {spec['holds']}\n{usage_bar(data['used'], data['cap'])} {data['used']}/{data['cap']}"
        if nxt:
            need = f"{nxt['materials']} {gear.MATERIALS[spec['material']]['name']}" + (f", {nxt['shards']} Rift Shards" if nxt["shards"] else "")
            line += f"\n-# Next: {nxt['name']} ({nxt['cap']} space) for {stones.fmt(nxt['coins'])}, {need}"
        else:
            line += "\n-# Fully upgraded"
        lines.append(line)
    return lines


class Pouch(commands.Cog):
    category = "Cultivation"
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def need_character(self, ctx: commands.Context) -> Optional[dict]:
        character = await cult.get(ctx.author.id)
        if character is None or not character["path"]:
            await ctx.send(view=error_layout("Not awakened", "You have not awakened yet. Use `cultivate awaken` to begin."))
            return None
        return character

    @commands.group(name="pouch", aliases=["pouches", "storage"], invoke_without_command=True, help="See your storage pouches. They hold your herbs and materials.")
    async def pouch(self, ctx: commands.Context):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        info = await pouch.usage(ctx.author.id)
        lines = pouch_lines(info)
        lines.append(f"\n-# Herbs and materials only fit in pouches. When one is full, new finds are sold automatically at shop value. Upgrade with `{ctx.clean_prefix}pouch upgrade <herb|material>`, free space with `{ctx.clean_prefix}pouch sell <item> [amount|all]`.")
        await ctx.send(view=info_layout(f"{e('epill')} Storage pouches", "\n".join(lines)))

    @pouch.command(name="upgrade", aliases=["buy", "improve"], help="Upgrade a pouch. Usage: pouch upgrade <herb|material>")
    async def upgrade(self, ctx: commands.Context, *, kind: str = ""):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        key = KINDS.get(kind.strip().lower())
        if key is None:
            return await ctx.send(view=error_layout("Which pouch?", f"Use `{ctx.clean_prefix}pouch upgrade herb` or `{ctx.clean_prefix}pouch upgrade material`."))
        result = await pouch.upgrade(ctx.author.id, key)
        if not result["ok"]:
            reasons = {
                "max": ("Fully upgraded", "That pouch is already the best there is."),
                "materials": ("Missing materials", f"You need **{result.get('need', 0)} {gear.MATERIALS[result.get('material', 'spirit_fiber')]['name']}**. Gather fiber with `{ctx.clean_prefix}world gather herbs` and hides with `{ctx.clean_prefix}world gather hunt`."),
                "coins": ("Not enough spirit stones", f"This upgrade costs **{stones.fmt(result.get('cost', 0))}**."),
            }
            title, body = reasons.get(result["reason"], ("Cannot upgrade", "That did not work."))
            return await ctx.send(view=error_layout(title, body))
        step = result["step"]
        await ctx.send(view=success_layout(f"{e('epill')} Pouch upgraded", f"You now carry a **{gear.pouch_name(key, result['tier'])}** with space for **{step['cap']}**."))

    @pouch.command(name="sell", aliases=["dump", "vendor"], help="Sell herbs or materials to the shop. Usage: pouch sell <item> [amount|all]")
    async def sell(self, ctx: commands.Context, *, rest: str = ""):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        words = rest.split()
        amount: Optional[int] = None
        if words and words[-1].lower() == "all":
            words = words[:-1]
            amount = 0
        elif words and words[-1].isdigit():
            amount = int(words[-1])
            words = words[:-1]
        key = pouch.find(" ".join(words)) if words else None
        if key is None or not gear.pool(key):
            return await ctx.send(view=error_layout("Unknown item", f"Use a herb or material name, like `{ctx.clean_prefix}pouch sell ember root 5`."))
        have = (await cult.inventory(ctx.author.id)).get(key, 0)
        qty = 1 if amount is None else (have if amount == 0 else amount)
        if qty <= 0 or have < qty:
            return await ctx.send(view=error_layout("You do not have that", f"You hold **{have}** {gear.MATERIALS[key]['name']}."))
        result = await pouch.sell(ctx.author.id, key, qty)
        if not result["ok"]:
            return await ctx.send(view=error_layout("You do not have that", "Check your bag with `cultivate bag`."))
        await ctx.send(view=success_layout(f"{e('ecoin')} Sold", f"You sold **{result['qty']} {gear.MATERIALS[key]['name']}** for **{stones.fmt(result['coins'])}**."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Pouch(bot))
