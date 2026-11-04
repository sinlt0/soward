import io
from typing import Optional

import discord
from discord.ext import commands
from PIL import Image

from utils import clans, coins, cosmetics, db, emoji_manager, family, pets, profile_card, profiles as store
from utils.components import ConfirmLayout, error_layout, info_layout, success_layout

NO_MENTIONS = discord.AllowedMentions.none()


class ProfileModal(discord.ui.Modal, title="Your profile"):
    def __init__(self, current: dict | None):
        super().__init__(timeout=600)
        current = current or {}
        self.bio = discord.ui.TextInput(label="About you", style=discord.TextStyle.paragraph, required=False, max_length=store.LIMITS["bio"], default=current.get("bio") or None)
        self.interests = discord.ui.TextInput(label="Interests (comma separated)", required=False, max_length=200, default=", ".join(current.get("interests") or []) or None)
        self.looking = discord.ui.TextInput(label="Looking for", required=False, max_length=store.LIMITS["looking_for"], default=current.get("looking_for") or None)
        self.relationship = discord.ui.TextInput(label="Relationship status", required=False, max_length=store.LIMITS["relationship"], default=current.get("relationship") or None)
        self.pronouns = discord.ui.TextInput(label="Pronouns", required=False, max_length=store.LIMITS["pronouns"], default=current.get("pronouns") or None)
        for item in (self.bio, self.interests, self.looking, self.relationship, self.pronouns):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await store.save(
            interaction.user.id, bio=str(self.bio.value), interests=store.parse_interests(str(self.interests.value)),
            looking_for=str(self.looking.value), relationship=str(self.relationship.value), pronouns=str(self.pronouns.value))
        await interaction.response.send_message(f"{emoji_manager.get('check')} Your profile was saved. Use `profile` to see it.", ephemeral=True)


class EditLayout(discord.ui.LayoutView):
    def __init__(self, owner: discord.abc.User, current: dict | None):
        super().__init__(timeout=300)
        self.owner = owner
        self.current = current
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay("## Edit your profile\nYour profile is global: it follows you to every server the bot is in, and anyone can look at it with `profile`. You can hide it any time with `profile hide`. Links are removed."))
        row = discord.ui.ActionRow()
        button = discord.ui.Button(label="Edit profile", style=discord.ButtonStyle.primary)
        button.callback = self.open
        row.add_item(button)
        container.add_item(row)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("This is not your profile.", ephemeral=True)
            return False
        return True

    async def open(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ProfileModal(await store.get(interaction.user.id)))


def normalize(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalpha())


def find_theme(text: str) -> Optional[str]:
    key = normalize(text)
    for theme_key, theme in cosmetics.THEMES.items():
        if key in (theme_key, normalize(theme["label"])):
            return theme_key
    return None


class Profiles(commands.Cog):
    category = "Profile"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def display_name(self, user_id: int) -> str:
        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                return "someone"
        return user.display_name

    async def card_data(self, user: discord.abc.User, guild: Optional[discord.Guild], theme: Optional[str] = None) -> dict:
        data = await store.get(user.id) or {}
        look = await cosmetics.get(user.id)
        avatar = None
        try:
            avatar = Image.open(io.BytesIO(await user.display_avatar.replace(size=256, format="png").read()))
        except (discord.HTTPException, OSError):
            pass
        level = None
        if guild is not None:
            xp = await db.raw_fetchone("SELECT level FROM member_xp WHERE guild_id=? AND user_id=?", (guild.id, user.id))
            level = xp["level"] if xp else 0
        partner_ids = await family.partners(user.id)
        parent_id = await family.parent_of(user.id)
        member = await clans.membership(user.id)
        clan = await clans.get(member["clan_id"]) if member else None
        return {
            "name": user.display_name,
            "avatar": avatar,
            "theme": theme or look["theme"],
            "title": look["title"],
            "pronouns": data.get("pronouns") or "",
            "bio": data.get("bio") or "",
            "interests": data.get("interests") or [],
            "level": level,
            "coins": await coins.balance(user.id),
            "diamonds": await coins.diamonds(user.id),
            "badges": await cosmetics.badges(user.id),
            "clan": clan["name"] if clan else "",
            "partners": [await self.display_name(i) for i in partner_ids[:2]],
            "children": len(await family.children_of(user.id)),
            "parent": await self.display_name(parent_id) if parent_id else "",
            "pet": await pets.active(user.id),
        }

    async def send_card(self, ctx: commands.Context, data: dict):
        buffer = profile_card.render_profile(data)
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=0x2B2D31)
        container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://profile.png")))
        view.add_item(container)
        await ctx.send(view=view, file=discord.File(buffer, "profile.png"), allowed_mentions=NO_MENTIONS)

    @commands.group(name="profile", aliases=["card"], invoke_without_command=True, help="Show a profile card. Usage: profile [user]")
    async def profile(self, ctx: commands.Context, user: Optional[discord.User] = None):
        target = user or ctx.author
        if ctx.guild is not None:
            target = ctx.guild.get_member(target.id) or target
        saved = await store.get(target.id)
        if saved and saved["hidden"] and target.id != ctx.author.id:
            return await ctx.send(view=info_layout("Private profile", f"{target.display_name} keeps their profile private."))
        async with ctx.typing():
            data = await self.card_data(target, ctx.guild)
        await self.send_card(ctx, data)

    @profile.command(name="edit", aliases=["set", "create"], help="Create or edit your profile.")
    async def profile_edit(self, ctx: commands.Context):
        await ctx.send(view=EditLayout(ctx.author, await store.get(ctx.author.id)))

    @profile.command(name="hide", help="Hide your profile from other people.")
    async def profile_hide(self, ctx: commands.Context):
        if not await store.set_hidden(ctx.author.id, True):
            return await ctx.send(view=error_layout("No profile", "Create one first with `profile edit`."))
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Profile", "Your profile is hidden. You will also be skipped by matchmaking."))

    @profile.command(name="show", help="Show your profile to other people again.")
    async def profile_show(self, ctx: commands.Context):
        if not await store.set_hidden(ctx.author.id, False):
            return await ctx.send(view=error_layout("No profile", "Create one first with `profile edit`."))
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Profile", "Your profile is visible again."))

    @profile.command(name="clear", aliases=["delete"], help="Delete your profile text.")
    async def profile_clear(self, ctx: commands.Context):
        await store.clear(ctx.author.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Profile", "Your profile text was deleted. Your themes, pets and badges are kept."))

    @profile.command(name="title", help="Set the line under your name. Usage: profile title [text]")
    async def profile_title(self, ctx: commands.Context, *, text: str = ""):
        text = store.clean(text, 24)
        await cosmetics.set_title(ctx.author.id, text)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Title", f"Your title is now **{text}**." if text else "Your title was removed."))

    @profile.group(name="theme", aliases=["themes"], invoke_without_command=True, help="See profile themes and the one you use.")
    async def profile_theme(self, ctx: commands.Context):
        e = emoji_manager.get
        look = await cosmetics.get(ctx.author.id)
        owned = await cosmetics.owned_ids(ctx.author.id)
        lines = []
        for key, theme in cosmetics.THEMES.items():
            if key == look["theme"]:
                state = "in use"
            elif theme["price"] == 0 or f"theme:{key}" in owned:
                state = "owned"
            else:
                state = f"{coins.fmt(theme['price'])} coins"
            lines.append(f"`{key}` · {theme['label']} · {state}")
        lines.append("\nUse `profile theme preview <name>`, `profile theme buy <name>` or `profile theme set <name>`.")
        await ctx.send(view=info_layout(f"{e('star')} Profile themes", "\n".join(lines)))

    async def theme_arg(self, ctx: commands.Context, name: str) -> Optional[str]:
        key = find_theme(name)
        if key is None:
            await ctx.send(view=error_layout("Unknown theme", "That theme does not exist. See them with `profile theme`."))
        return key

    @profile_theme.command(name="preview", help="See your profile card in a theme. Usage: profile theme preview <name>")
    async def theme_preview(self, ctx: commands.Context, *, name: str):
        key = await self.theme_arg(ctx, name)
        if key is None:
            return
        member = ctx.guild.get_member(ctx.author.id) if ctx.guild else None
        async with ctx.typing():
            data = await self.card_data(member or ctx.author, ctx.guild, theme=key)
        await self.send_card(ctx, data)

    @profile_theme.command(name="buy", help="Buy a theme with coins. Usage: profile theme buy <name>")
    async def theme_buy(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        key = await self.theme_arg(ctx, name)
        if key is None:
            return
        theme = cosmetics.THEMES[key]
        if await cosmetics.owns(ctx.author.id, f"theme:{key}", theme["price"]):
            return await ctx.send(view=error_layout("Already yours", "You already own that theme. Use `profile theme set <name>`."))
        view = ConfirmLayout("Buy theme", f"Buy **{theme['label']}** for **{coins.fmt(theme['price'])}** coins?", author_id=ctx.author.id, timeout=30.0)
        message = await ctx.send(view=view)
        await view.wait()
        if view.value is not True:
            return
        if not await coins.spend(ctx.author.id, theme["price"]):
            return await message.edit(view=error_layout("Not enough coins", f"You have **{coins.fmt(await coins.balance(ctx.author.id))}** coins."))
        await cosmetics.grant(ctx.author.id, f"theme:{key}")
        await cosmetics.set_theme(ctx.author.id, key)
        await message.edit(view=success_layout(f"{e('check')} Theme bought", f"**{theme['label']}** is yours and now in use."))

    @profile_theme.command(name="set", aliases=["use", "equip"], help="Use a theme you own. Usage: profile theme set <name>")
    async def theme_set(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        key = await self.theme_arg(ctx, name)
        if key is None:
            return
        theme = cosmetics.THEMES[key]
        if not await cosmetics.owns(ctx.author.id, f"theme:{key}", theme["price"]):
            return await ctx.send(view=error_layout("Not owned", f"Buy it first with `profile theme buy {key}` ({coins.fmt(theme['price'])} coins)."))
        await cosmetics.set_theme(ctx.author.id, key)
        await ctx.send(view=success_layout(f"{e('check')} Theme set", f"Your profile now uses **{theme['label']}**."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Profiles(bot))
