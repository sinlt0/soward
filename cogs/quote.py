import asyncio
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from utils import db, emoji_manager, quote_card
from utils.components import error_layout, success_layout, footer_block


async def is_premium_guild(guild_id: Optional[int]) -> bool:
    if not guild_id:
        return False
    row = await db.raw_fetchone("SELECT premium FROM guilds WHERE guild_id=?", (guild_id,))
    return bool(row["premium"]) if row else False


async def get_user_prefs(user_id: int) -> dict:
    font_key = quote_card.resolve_font_key(await db.get("quote_font", str(user_id)))
    accent_key = quote_card.resolve_accent_key(await db.get("quote_accent", str(user_id)))
    style_key = quote_card.resolve_style_key(font_key, await db.get("quote_style", str(user_id)))
    colorize = bool(await db.get("quote_colorize", str(user_id)))
    return {"font": font_key, "accent": accent_key, "style": style_key, "colorize": colorize}


async def set_user_font(user_id: int, font_key: str) -> None:
    await db.set("quote_font", str(user_id), font_key)


async def set_user_accent(user_id: int, accent_key: str) -> None:
    await db.set("quote_accent", str(user_id), accent_key)


async def set_user_style(user_id: int, style_key: str) -> None:
    await db.set("quote_style", str(user_id), style_key)


async def set_user_colorize(user_id: int, colorize: bool) -> None:
    await db.set("quote_colorize", str(user_id), colorize)


def _build_quote_view(cog: "Quote", target: discord.Message, requester: discord.abc.User, prefs: dict, is_premium: bool) -> discord.ui.LayoutView:
    e = emoji_manager.get
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=0x1A1A1D)
    container.add_item(discord.ui.TextDisplay(f"## {e('quote')} Quote"))
    container.add_item(discord.ui.Separator())
    gallery = discord.ui.MediaGallery()
    gallery.add_item(media="attachment://quote.png")
    container.add_item(gallery)
    container.add_item(discord.ui.Separator())
    container.add_item(FontSelectRow(cog, target, requester, prefs, is_premium))
    container.add_item(StyleSelectRow(cog, target, requester, prefs, is_premium))
    container.add_item(ColorSelectRow(cog, target, requester, prefs, is_premium))
    container.add_item(ToggleRow(cog, target, requester, prefs, is_premium))
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


async def _apply_change(interaction: discord.Interaction, cog: "Quote", target: discord.Message, requester: discord.abc.User, prefs: dict, is_premium: bool) -> None:
    await interaction.response.defer()
    file, error = await cog.build_quote_file(target, prefs)
    if error:
        return await interaction.followup.send(view=error_layout("Can't Make Quote", error), ephemeral=True)

    view = _build_quote_view(cog, target, requester, prefs, is_premium)
    await interaction.message.edit(attachments=[file], view=view)


class FontSelectRow(discord.ui.ActionRow):
    def __init__(self, cog: "Quote", target: discord.Message, requester: discord.abc.User, prefs: dict, is_premium: bool):
        options = []
        for key, style in quote_card.FONT_STYLES.items():
            label = style["label"] + (" (Premium)" if style["premium"] else "")
            options.append(discord.SelectOption(label=label, value=key, default=(key == prefs["font"])))

        super().__init__(discord.ui.Select(placeholder="Change font...", options=options, custom_id="quote:font_select"))
        self.cog = cog
        self.target = target
        self.requester = requester
        self.prefs = prefs
        self.is_premium = is_premium
        self.children[0].callback = self._on_select

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester.id:
            return await interaction.response.send_message("Only the person who requested this quote can change its style.", ephemeral=True)

        chosen = self.children[0].values[0]
        style = quote_card.FONT_STYLES[chosen]
        if style["premium"] and not self.is_premium:
            return await interaction.response.send_message(
                "That font is a premium-only style. Upgrade this server with `premium claim` to unlock it.", ephemeral=True
            )

        new_prefs = dict(self.prefs, font=chosen)
        new_prefs["style"] = quote_card.resolve_style_key(chosen, self.prefs["style"])
        await _apply_change(interaction, self.cog, self.target, self.requester, new_prefs, self.is_premium)


class StyleSelectRow(discord.ui.ActionRow):
    def __init__(self, cog: "Quote", target: discord.Message, requester: discord.abc.User, prefs: dict, is_premium: bool):
        available = quote_card.available_styles(prefs["font"])
        options = [
            discord.SelectOption(label=quote_card.STYLE_LABELS[s], value=s, default=(s == prefs["style"]))
            for s in available
        ]

        super().__init__(discord.ui.Select(placeholder="Change weight/style...", options=options, custom_id="quote:style_select", disabled=(len(options) <= 1)))
        self.cog = cog
        self.target = target
        self.requester = requester
        self.prefs = prefs
        self.is_premium = is_premium
        self.children[0].callback = self._on_select

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester.id:
            return await interaction.response.send_message("Only the person who requested this quote can change its style.", ephemeral=True)

        chosen = self.children[0].values[0]
        new_prefs = dict(self.prefs, style=chosen)
        await _apply_change(interaction, self.cog, self.target, self.requester, new_prefs, self.is_premium)


class ColorSelectRow(discord.ui.ActionRow):
    def __init__(self, cog: "Quote", target: discord.Message, requester: discord.abc.User, prefs: dict, is_premium: bool):
        options = []
        for key, color in quote_card.ACCENT_COLORS.items():
            label = color["label"] + (" (Premium)" if color["premium"] else "")
            options.append(discord.SelectOption(label=label, value=key, default=(key == prefs["accent"])))

        super().__init__(discord.ui.Select(placeholder="Change accent color...", options=options, custom_id="quote:color_select"))
        self.cog = cog
        self.target = target
        self.requester = requester
        self.prefs = prefs
        self.is_premium = is_premium
        self.children[0].callback = self._on_select

    async def _on_select(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester.id:
            return await interaction.response.send_message("Only the person who requested this quote can change its style.", ephemeral=True)

        chosen = self.children[0].values[0]
        color = quote_card.ACCENT_COLORS[chosen]
        if color["premium"] and not self.is_premium:
            return await interaction.response.send_message(
                "That color is a premium-only accent. Upgrade this server with `premium claim` to unlock it.", ephemeral=True
            )

        new_prefs = dict(self.prefs, accent=chosen)
        await _apply_change(interaction, self.cog, self.target, self.requester, new_prefs, self.is_premium)


class ToggleRow(discord.ui.ActionRow):
    def __init__(self, cog: "Quote", target: discord.Message, requester: discord.abc.User, prefs: dict, is_premium: bool):
        colorize = prefs["colorize"]
        super().__init__(
            discord.ui.Button(
                label="Colorize Avatar" if not colorize else "Grayscale Avatar",
                style=discord.ButtonStyle.secondary,
                custom_id="quote:colorize_toggle",
            ),
        )
        self.cog = cog
        self.target = target
        self.requester = requester
        self.prefs = prefs
        self.is_premium = is_premium
        self.children[0].callback = self._on_toggle

    async def _on_toggle(self, interaction: discord.Interaction):
        if interaction.user.id != self.requester.id:
            return await interaction.response.send_message("Only the person who requested this quote can change its style.", ephemeral=True)

        new_prefs = dict(self.prefs, colorize=not self.prefs["colorize"])
        await _apply_change(interaction, self.cog, self.target, self.requester, new_prefs, self.is_premium)


class Quote(commands.Cog):
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Soward/1.0"})

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    async def resolve_target_message(self, ctx: commands.Context) -> Optional[discord.Message]:
        reference = ctx.message.reference
        if not reference:
            return None
        if isinstance(reference.resolved, discord.Message):
            return reference.resolved
        if reference.message_id:
            try:
                return await ctx.channel.fetch_message(reference.message_id)
            except discord.HTTPException:
                return None
        return None

    def _extract_text(self, target: discord.Message) -> Optional[str]:
        content = target.content.strip()
        if not content:
            if target.embeds and target.embeds[0].description:
                content = target.embeds[0].description.strip()
            elif target.attachments:
                content = "[attachment]"
            else:
                return None
        if len(content) > 400:
            content = content[:397] + "..."
        return content

    async def build_quote_file(self, target: discord.Message, prefs: dict) -> tuple[Optional[discord.File], Optional[str]]:
        content = self._extract_text(target)
        if content is None:
            return None, "That message doesn't have any text to quote."

        avatar_url = target.author.display_avatar.with_format("png").with_size(256).url
        try:
            async with self.session.get(avatar_url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status != 200:
                    return None, "Couldn't fetch that user's avatar."
                avatar_bytes = await resp.read()
        except aiohttp.ClientError:
            return None, "Couldn't fetch that user's avatar."

        accent_rgb = quote_card.ACCENT_COLORS[quote_card.resolve_accent_key(prefs["accent"])]["rgb"]
        buffer = await asyncio.to_thread(
            quote_card.render_quote_card,
            avatar_bytes, content, target.author.display_name,
            prefs["font"], accent_rgb, prefs["style"], prefs["colorize"],
        )
        return discord.File(buffer, filename="quote.png"), None

    async def send_quote(self, target: discord.Message, requester: discord.abc.User, guild_id: Optional[int], send_func) -> None:
        prefs = await get_user_prefs(requester.id)
        is_premium = await is_premium_guild(guild_id)

        if quote_card.is_premium_font(prefs["font"]) and not is_premium:
            prefs["font"] = quote_card.DEFAULT_FONT_KEY
            prefs["style"] = quote_card.resolve_style_key(prefs["font"], prefs["style"])
        if quote_card.is_premium_accent(prefs["accent"]) and not is_premium:
            prefs["accent"] = quote_card.DEFAULT_ACCENT_KEY

        file, error = await self.build_quote_file(target, prefs)
        if error:
            await send_func(view=error_layout("Can't Make Quote", error))
            return

        view = _build_quote_view(self, target, requester, prefs, is_premium)
        await send_func(file=file, view=view)

    @commands.command(name="makeaquote", aliases=["mcq", "quote"], help="Reply to a message with this command to turn it into a quote image.")
    @commands.guild_only()
    @commands.cooldown(1, 4.0, commands.BucketType.user)
    async def makeaquote(self, ctx: commands.Context):
        e = emoji_manager.get
        target = await self.resolve_target_message(ctx)
        if not target:
            return await ctx.send(view=error_layout(
                f"{e('quote')} Reply Required", "Reply to the message you want to quote, then run this command."
            ))
        if target.author.bot:
            return await ctx.send(view=error_layout("Can't Quote That", "You can't make a quote out of a bot's message."))

        await self.send_quote(target, ctx.author, ctx.guild.id if ctx.guild else None, ctx.send)

    @commands.command(name="quotefont", help="Set your default quote font. Run with no argument to see available fonts.")
    async def quotefont(self, ctx: commands.Context, font_key: Optional[str] = None):
        e = emoji_manager.get
        is_premium = await is_premium_guild(ctx.guild.id if ctx.guild else None)

        if font_key is None:
            prefs = await get_user_prefs(ctx.author.id)
            lines = []
            for key, style in quote_card.FONT_STYLES.items():
                marker = "✅" if key == prefs["font"] else "▫️"
                lock = " 🔒 Premium" if style["premium"] and not is_premium else (" (Premium)" if style["premium"] else "")
                lines.append(f"{marker} `{key}` — {style['label']}{lock}")
            return await ctx.send(view=success_layout(
                f"{e('quote')} Quote Fonts", "\n".join(lines) + "\n\nUse `quotefont <key>` to set your default."
            ))

        font_key = font_key.lower().strip()
        if font_key not in quote_card.FONT_STYLES:
            valid = ", ".join(f"`{k}`" for k in quote_card.FONT_STYLES)
            return await ctx.send(view=error_layout("Unknown Font", f"Valid fonts: {valid}"))

        style = quote_card.FONT_STYLES[font_key]
        if style["premium"] and not is_premium:
            return await ctx.send(view=error_layout(
                "Premium Font", f"`{style['label']}` is a premium-only font. Upgrade this server with `premium claim` to unlock it."
            ))

        await set_user_font(ctx.author.id, font_key)
        await ctx.send(view=success_layout(f"{e('check')} Font Set", f"Your quotes will now use **{style['label']}** by default."))

    @commands.command(name="quotestyle", help="Set your default quote weight/style (regular, italic, bold, bolditalic) where the font supports it.")
    async def quotestyle(self, ctx: commands.Context, style_key: Optional[str] = None):
        e = emoji_manager.get
        prefs = await get_user_prefs(ctx.author.id)

        if style_key is None:
            available = quote_card.available_styles(prefs["font"])
            lines = [f"{'✅' if s == prefs['style'] else '▫️'} `{s}` — {quote_card.STYLE_LABELS[s]}" for s in available]
            return await ctx.send(view=success_layout(
                f"{e('quote')} Quote Styles",
                f"Available for your current font (`{prefs['font']}`):\n" + "\n".join(lines) + "\n\nUse `quotestyle <key>` to set it.",
            ))

        style_key = style_key.lower().strip()
        available = quote_card.available_styles(prefs["font"])
        if style_key not in available:
            valid = ", ".join(f"`{s}`" for s in available)
            return await ctx.send(view=error_layout("Unavailable Style", f"Your current font (`{prefs['font']}`) only supports: {valid}"))

        await set_user_style(ctx.author.id, style_key)
        await ctx.send(view=success_layout(f"{e('check')} Style Set", f"Your quotes will now use **{quote_card.STYLE_LABELS[style_key]}** by default."))

    @commands.command(name="quotecolor", help="Set your default quote accent color. Run with no argument to see available colors.")
    async def quotecolor(self, ctx: commands.Context, accent_key: Optional[str] = None):
        e = emoji_manager.get
        is_premium = await is_premium_guild(ctx.guild.id if ctx.guild else None)

        if accent_key is None:
            prefs = await get_user_prefs(ctx.author.id)
            lines = []
            for key, color in quote_card.ACCENT_COLORS.items():
                marker = "✅" if key == prefs["accent"] else "▫️"
                lock = " 🔒 Premium" if color["premium"] and not is_premium else (" (Premium)" if color["premium"] else "")
                lines.append(f"{marker} `{key}` — {color['label']}{lock}")
            return await ctx.send(view=success_layout(
                f"{e('quote')} Quote Colors", "\n".join(lines) + "\n\nUse `quotecolor <key>` to set your default."
            ))

        accent_key = accent_key.lower().strip()
        if accent_key not in quote_card.ACCENT_COLORS:
            valid = ", ".join(f"`{k}`" for k in quote_card.ACCENT_COLORS)
            return await ctx.send(view=error_layout("Unknown Color", f"Valid colors: {valid}"))

        color = quote_card.ACCENT_COLORS[accent_key]
        if color["premium"] and not is_premium:
            return await ctx.send(view=error_layout(
                "Premium Color", f"`{color['label']}` is a premium-only accent. Upgrade this server with `premium claim` to unlock it."
            ))

        await set_user_accent(ctx.author.id, accent_key)
        await ctx.send(view=success_layout(f"{e('check')} Color Set", f"Your quotes will now use **{color['label']}** as the accent color."))

    @commands.command(name="quotecolorize", aliases=["quoteavatar"], help="Toggle whether your quote avatars are shown in color or grayscale by default.")
    async def quotecolorize(self, ctx: commands.Context):
        e = emoji_manager.get
        prefs = await get_user_prefs(ctx.author.id)
        new_value = not prefs["colorize"]
        await set_user_colorize(ctx.author.id, new_value)
        state = "color" if new_value else "grayscale"
        await ctx.send(view=success_layout(f"{e('check')} Avatar Style Set", f"Your quote avatars will now default to **{state}**."))

    @commands.Cog.listener("on_message")
    async def on_reply_mention(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if self.bot.user not in message.mentions:
            return
        if not message.reference:
            return

        reference = message.reference
        target = reference.resolved if isinstance(reference.resolved, discord.Message) else None
        if not target and reference.message_id:
            try:
                target = await message.channel.fetch_message(reference.message_id)
            except discord.HTTPException:
                return
        if not target or target.author.bot or target.id == message.id:
            return

        await self.send_quote(target, message.author, message.guild.id, message.channel.send)


async def setup(bot: commands.Bot):
    await bot.add_cog(Quote(bot))
