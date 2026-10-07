import random
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from utils import emoji_manager
from utils.components import error_layout, footer_block

API_BASE = "https://api.truthordarebot.xyz/v1"
VALID_RATINGS = ("pg", "pg13", "r")


class ToDRefreshRow(discord.ui.ActionRow):
    def __init__(self, cog: "TruthOrDare", mode: str, rating: str):
        super().__init__(
            discord.ui.Button(label="Another one", style=discord.ButtonStyle.primary, custom_id="tod:another"),
        )
        self.cog = cog
        self.mode = mode
        self.rating = rating
        self.children[0].callback = self._another

    async def _another(self, interaction: discord.Interaction):
        question, error = await self.cog.fetch_question(self.mode, self.rating)
        if error:
            return await interaction.response.send_message(view=error_layout("Request Failed", error), ephemeral=True)

        view = self.cog.build_result_view(self.mode, self.rating, question, interaction.user)
        await interaction.response.edit_message(view=view)


class TruthOrDare(commands.Cog):
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Soward/1.0"})

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    async def fetch_question(self, mode: str, rating: str) -> tuple[Optional[str], Optional[str]]:
        try:
            async with self.session.get(
                f"{API_BASE}/{mode}", params={"rating": rating}, timeout=aiohttp.ClientTimeout(total=6)
            ) as resp:
                if resp.status != 200:
                    return None, f"The Truth or Dare API returned an error (`{resp.status}`). Try again shortly."
                data = await resp.json()
        except aiohttp.ClientError:
            return None, "Couldn't reach the Truth or Dare API. Try again shortly."
        except Exception:
            return None, "Something went wrong fetching a question. Try again shortly."

        question = data.get("question")
        if not question:
            return None, "The API didn't return a question. Try again."
        return question, None

    def build_result_view(self, mode: str, rating: str, question: str, author: discord.abc.User) -> discord.ui.LayoutView:
        e = emoji_manager.get
        icon = e("truth") if mode == "truth" else e("dare")
        accent = 0x5865F2 if mode == "truth" else 0xED4245

        view = discord.ui.LayoutView(timeout=120)
        container = discord.ui.Container(accent_color=accent)
        container.add_item(discord.ui.TextDisplay(f"## {icon} {mode.capitalize()}"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(question))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# Rating: `{rating}` · Requested by {author.mention}"))
        container.add_item(discord.ui.Separator())
        container.add_item(ToDRefreshRow(self, mode, rating))
        container.add_item(discord.ui.Separator())
        for item in footer_block():
            container.add_item(item)
        view.add_item(container)
        return view

    def _resolve_rating(self, requested: Optional[str], channel: discord.abc.GuildChannel) -> tuple[Optional[str], Optional[str]]:
        if requested is None:
            return "pg13", None

        requested = requested.lower()
        if requested not in VALID_RATINGS:
            return None, f"Invalid rating `{requested}`. Choose from: {', '.join(f'`{r}`' for r in VALID_RATINGS)}"

        if requested == "r":
            is_nsfw = getattr(channel, "is_nsfw", lambda: False)()
            if not is_nsfw:
                return None, "The `r` rating is only available in channels marked as NSFW in Discord's own channel settings."

        return requested, None

    @commands.command(name="truth", help="Get a random truth question. Usage: truth [pg|pg13|r]")
    @commands.guild_only()
    @commands.cooldown(1, 2.0, commands.BucketType.user)
    async def truth(self, ctx: commands.Context, rating: Optional[str] = None):
        resolved_rating, error = self._resolve_rating(rating, ctx.channel)
        if error:
            return await ctx.send(view=error_layout("Can't Do That", error))

        question, error = await self.fetch_question("truth", resolved_rating)
        if error:
            return await ctx.send(view=error_layout("Request Failed", error))

        await ctx.send(view=self.build_result_view("truth", resolved_rating, question, ctx.author))

    @commands.command(name="dare", help="Get a random dare. Usage: dare [pg|pg13|r]")
    @commands.guild_only()
    @commands.cooldown(1, 2.0, commands.BucketType.user)
    async def dare(self, ctx: commands.Context, rating: Optional[str] = None):
        resolved_rating, error = self._resolve_rating(rating, ctx.channel)
        if error:
            return await ctx.send(view=error_layout("Can't Do That", error))

        question, error = await self.fetch_question("dare", resolved_rating)
        if error:
            return await ctx.send(view=error_layout("Request Failed", error))

        await ctx.send(view=self.build_result_view("dare", resolved_rating, question, ctx.author))

    @commands.command(name="tod", aliases=["truthordare"], help="Get a random truth or dare question. Usage: tod [pg|pg13|r]")
    @commands.guild_only()
    @commands.cooldown(1, 2.0, commands.BucketType.user)
    async def tod(self, ctx: commands.Context, rating: Optional[str] = None):
        resolved_rating, error = self._resolve_rating(rating, ctx.channel)
        if error:
            return await ctx.send(view=error_layout("Can't Do That", error))

        mode = random.choice(("truth", "dare"))
        question, error = await self.fetch_question(mode, resolved_rating)
        if error:
            return await ctx.send(view=error_layout("Request Failed", error))

        await ctx.send(view=self.build_result_view(mode, resolved_rating, question, ctx.author))


async def setup(bot: commands.Bot):
    await bot.add_cog(TruthOrDare(bot))
