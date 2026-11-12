import time
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import coins, cosmetics, emoji_manager, pets, profile_card, profiles
from utils.components import ConfirmLayout, error_layout, info_layout, success_layout

NO_MENTIONS = discord.AllowedMentions.none()


def normalize(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalpha())


def find(catalog: dict, text: str) -> Optional[str]:
    key = normalize(text)
    for item_key, item in catalog.items():
        if key in (item_key, normalize(item["label"])):
            return item_key
    return None


class Pets(commands.Cog):
    category = "Utility"
    submodule = "User Utilities"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last_gain: dict[int, float] = {}
        self.daily: dict[int, tuple[int, int]] = {}

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context):
        user = ctx.author
        if user.bot:
            return
        now = time.time()
        if now - self.last_gain.get(user.id, 0) < config.PET_XP_COOLDOWN:
            return
        day = int(now // 86400)
        stored_day, gained = self.daily.get(user.id, (day, 0))
        if stored_day != day:
            gained = 0
        if gained >= config.PET_DAILY_XP_CAP:
            return
        pet = await pets.add_xp(user.id, config.PET_XP_PER_COMMAND)
        if pet is None:
            return
        self.last_gain[user.id] = now
        self.daily[user.id] = (day, gained + config.PET_XP_PER_COMMAND)
        if pet.get("grew"):
            e = emoji_manager.get
            stage = cosmetics.stage_name(pet["xp"])
            try:
                await ctx.send(view=success_layout(f"{e('star')} {pet['name']} grew up!", f"{user.mention}, your {cosmetics.SPECIES[pet['species']]['label'].lower()} is now **{stage}**. See it with `pet`."), allowed_mentions=discord.AllowedMentions(users=[user]))
            except discord.HTTPException:
                pass

    async def send_pet(self, ctx: commands.Context, pet: dict, owner: discord.abc.User):
        look = await cosmetics.get(owner.id)
        buffer = profile_card.render_pet(pet, look["theme"], owner.display_name)
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=0x2B2D31)
        container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://pet.png")))
        view.add_item(container)
        await ctx.send(view=view, file=discord.File(buffer, "pet.png"), allowed_mentions=NO_MENTIONS)

    @commands.group(name="pet", aliases=["pets"], invoke_without_command=True, help="Show your pet or someone else's. Usage: pet [user]")
    async def pet_group(self, ctx: commands.Context, user: Optional[discord.User] = None):
        target = user or ctx.author
        pet = await pets.active(target.id)
        if pet is None:
            who = "You have" if target.id == ctx.author.id else f"{target.display_name} has"
            return await ctx.send(view=info_layout("No pet yet", f"{who} no pet. Adopt a free one with `pet adopt kitten`, `pet adopt puppy` or `pet adopt chick`."))
        async with ctx.typing():
            await self.send_pet(ctx, pet, target)

    @pet_group.command(name="adopt", aliases=["get"], help="Adopt a pet. Usage: pet adopt <species> [name]")
    async def pet_adopt(self, ctx: commands.Context, species: str, *, name: str = ""):
        e = emoji_manager.get
        key = find(cosmetics.SPECIES, species)
        if key is None:
            options = ", ".join(f"`{k}`" + ("" if v["price"] == 0 else f" ({coins.fmt(v['price'])})") for k, v in cosmetics.SPECIES.items())
            return await ctx.send(view=error_layout("Unknown species", f"Choose one of: {options}."))
        spec = cosmetics.SPECIES[key]
        owned = await pets.all_of(ctx.author.id)
        if len(owned) >= config.PET_LIMIT:
            return await ctx.send(view=error_layout("No room", f"You can have up to {config.PET_LIMIT} pets. Release one with `pet release <name>`."))
        name = profiles.clean(name, config.PET_NAME_MAX) or spec["label"]
        if any(p["name"].lower() == name.lower() for p in owned):
            return await ctx.send(view=error_layout("Name in use", "You already have a pet with that name."))
        if spec["price"] > 0:
            view = ConfirmLayout("Adopt pet", f"Adopt a **{spec['label']}** named **{name}** for **{coins.fmt(spec['price'])}** coins?", author_id=ctx.author.id, timeout=30.0)
            message = await ctx.send(view=view)
            await view.wait()
            if view.value is not True:
                return
            if not await coins.spend(ctx.author.id, spec["price"]):
                return await message.edit(view=error_layout("Not enough coins", f"You have **{coins.fmt(await coins.balance(ctx.author.id))}** coins."))
        pet = await pets.adopt(ctx.author.id, key, name)
        await self.send_pet(ctx, pet, ctx.author)
        await ctx.send(view=success_layout(f"{e('check')} Adopted", f"**{name}** joined you. It grows a little every time you use the bot."))

    @pet_group.command(name="list", aliases=["all", "mine"], help="List your pets.")
    async def pet_list(self, ctx: commands.Context):
        e = emoji_manager.get
        owned = await pets.all_of(ctx.author.id)
        if not owned:
            return await ctx.send(view=info_layout("Your pets", "You have no pets. Use `pet adopt <species>`."))
        lines = []
        for pet in owned:
            mark = f"{e('star')} " if pet["active"] else ""
            lines.append(f"{mark}**{pet['name']}** · {cosmetics.stage_name(pet['xp'])} {cosmetics.SPECIES[pet['species']]['label']} · {pet['xp']:,} xp")
        lines.append(f"\n-# {len(owned)}/{config.PET_LIMIT} pets. Only the starred pet grows. Change it with `pet switch <name>`.")
        await ctx.send(view=info_layout("Your pets", "\n".join(lines)))

    @pet_group.command(name="switch", aliases=["use", "select"], help="Choose which pet grows and shows on your profile. Usage: pet switch <name>")
    async def pet_switch(self, ctx: commands.Context, *, name: str):
        pet = await pets.find(ctx.author.id, name)
        if pet is None:
            return await ctx.send(view=error_layout("Not found", "You have no pet with that name. See `pet list`."))
        await pets.set_active(ctx.author.id, pet["pet_id"])
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Switched", f"**{pet['name']}** is now your active pet."))

    @pet_group.command(name="rename", help="Rename your active pet. Usage: pet rename <name>")
    async def pet_rename(self, ctx: commands.Context, *, name: str):
        pet = await pets.active(ctx.author.id)
        if pet is None:
            return await ctx.send(view=error_layout("No pet", "Adopt one first with `pet adopt`."))
        name = profiles.clean(name, config.PET_NAME_MAX)
        if not name:
            return await ctx.send(view=error_layout("Invalid name", "Give the pet a name."))
        await pets.rename(pet["pet_id"], name)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Renamed", f"Your pet is now called **{name}**."))

    @pet_group.command(name="release", help="Say goodbye to a pet. Usage: pet release <name>")
    async def pet_release(self, ctx: commands.Context, *, name: str):
        pet = await pets.find(ctx.author.id, name)
        if pet is None:
            return await ctx.send(view=error_layout("Not found", "You have no pet with that name."))
        view = ConfirmLayout("Release pet", f"Release **{pet['name']}**? Its growth is lost and coins are not refunded.", author_id=ctx.author.id, timeout=30.0)
        message = await ctx.send(view=view)
        await view.wait()
        if view.value is not True:
            return
        await pets.release(ctx.author.id, pet["pet_id"])
        await message.edit(view=success_layout("Released", f"**{pet['name']}** went off to explore."))

    @pet_group.command(name="shop", aliases=["store"], help="See pet species and outfits for sale.")
    async def pet_shop(self, ctx: commands.Context):
        e = emoji_manager.get
        owned = await cosmetics.owned_ids(ctx.author.id)
        species = [f"`{k}` · {v['label']} · " + ("free" if v["price"] == 0 else f"{coins.fmt(v['price'])} coins") for k, v in cosmetics.SPECIES.items()]
        outfits = []
        for key, item in cosmetics.OUTFITS.items():
            state = "free" if item["price"] == 0 else "owned" if f"outfit:{key}" in owned else f"{coins.fmt(item['price'])} coins"
            outfits.append(f"`{key}` · {item['label']} · {state}")
        body = "**Species** (`pet adopt <species>`)\n" + "\n".join(species) + "\n\n**Outfits** (`pet outfit buy <name>`)\n" + "\n".join(outfits)
        await ctx.send(view=info_layout(f"{e('ecoin')} Pet shop", body))

    @pet_group.group(name="outfit", aliases=["wear", "outfits"], invoke_without_command=True, help="Dress your active pet. Usage: pet outfit <name|none>")
    async def pet_outfit(self, ctx: commands.Context, *, name: str = ""):
        pet = await pets.active(ctx.author.id)
        if pet is None:
            return await ctx.send(view=error_layout("No pet", "Adopt one first with `pet adopt`."))
        if not name:
            return await self.pet_shop(ctx)
        if normalize(name) in ("none", "nothing", "off", "remove"):
            await pets.wear(pet["pet_id"], "")
            return await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Outfit", f"**{pet['name']}** took the outfit off."))
        key = find(cosmetics.OUTFITS, name)
        if key is None:
            return await ctx.send(view=error_layout("Unknown outfit", "See the outfits with `pet shop`."))
        item = cosmetics.OUTFITS[key]
        if not await cosmetics.owns(ctx.author.id, f"outfit:{key}", item["price"]):
            return await ctx.send(view=error_layout("Not owned", f"Buy it first with `pet outfit buy {key}` ({coins.fmt(item['price'])} coins)."))
        await pets.wear(pet["pet_id"], key)
        pet["outfit"] = key
        await self.send_pet(ctx, pet, ctx.author)

    @pet_outfit.command(name="buy", help="Buy an outfit with coins. Usage: pet outfit buy <name>")
    async def outfit_buy(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        key = find(cosmetics.OUTFITS, name)
        if key is None:
            return await ctx.send(view=error_layout("Unknown outfit", "See the outfits with `pet shop`."))
        item = cosmetics.OUTFITS[key]
        if await cosmetics.owns(ctx.author.id, f"outfit:{key}", item["price"]):
            return await ctx.send(view=error_layout("Already yours", f"Put it on with `pet outfit {key}`."))
        view = ConfirmLayout("Buy outfit", f"Buy the **{item['label']}** for **{coins.fmt(item['price'])}** coins?", author_id=ctx.author.id, timeout=30.0)
        message = await ctx.send(view=view)
        await view.wait()
        if view.value is not True:
            return
        if not await coins.spend(ctx.author.id, item["price"]):
            return await message.edit(view=error_layout("Not enough coins", f"You have **{coins.fmt(await coins.balance(ctx.author.id))}** coins."))
        await cosmetics.grant(ctx.author.id, f"outfit:{key}")
        pet = await pets.active(ctx.author.id)
        if pet:
            await pets.wear(pet["pet_id"], key)
        await message.edit(view=success_layout(f"{e('check')} Outfit bought", f"The **{item['label']}** is yours" + (f" and **{pet['name']}** is wearing it." if pet else ". Adopt a pet to wear it.")))


async def setup(bot: commands.Bot):
    await bot.add_cog(Pets(bot))
