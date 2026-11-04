from datetime import datetime
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config
from utils import emoji_manager, lookups, reminders, scheduler, translate as translator
from utils.components import error_layout, info_layout

NO_MENTIONS = discord.AllowedMentions.none()
COOLDOWN = commands.cooldown(1, 5.0, commands.BucketType.user)


def unavailable(name: str) -> discord.ui.LayoutView:
    return error_layout("Service unavailable", f"The {name} service did not answer. Try again in a moment.")


class Lookups(commands.Cog):
    category = "Utility"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.menu = app_commands.ContextMenu(name="Translate message", callback=self.translate_menu)

    async def cog_load(self):
        self.bot.tree.add_command(self.menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.menu.name, type=self.menu.type)

    @commands.command(name="weather", aliases=["forecast"], help="Show the weather and a 3 day forecast. Usage: weather <city>")
    @COOLDOWN
    async def weather(self, ctx: commands.Context, *, city: str):
        e = emoji_manager.get
        async with ctx.typing():
            status, geo = await lookups.fetch_json("https://geocoding-api.open-meteo.com/v1/search", {"name": city[:80], "count": 1, "language": "en"}, ttl=3600)
            if status is None:
                return await ctx.send(view=unavailable("weather"))
            results = (geo or {}).get("results") or []
            if not results:
                return await ctx.send(view=error_layout("Place not found", "I could not find that place. Try the city name only."))
            place = results[0]
            status, data = await lookups.fetch_json("https://api.open-meteo.com/v1/forecast", {
                "latitude": place["latitude"], "longitude": place["longitude"], "timezone": "auto", "forecast_days": 4,
                "current": "temperature_2m,apparent_temperature,relative_humidity_2m,wind_speed_10m,weather_code",
                "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code"}, ttl=600)
        if status != 200 or not data or "current" not in data:
            return await ctx.send(view=unavailable("weather"))
        now = data["current"]
        name = ", ".join(x for x in (place.get("name"), place.get("admin1"), place.get("country")) if x)
        lines = [
            f"**{lookups.weather_text(now.get('weather_code'))}** · {lookups.temp(now.get('temperature_2m'))}",
            f"Feels like {lookups.temp(now.get('apparent_temperature'))} · Humidity {now.get('relative_humidity_2m')}% · Wind {now.get('wind_speed_10m')} km/h",
            "",
        ]
        daily = data.get("daily") or {}
        for i in range(1, min(4, len(daily.get("time", [])))):
            day = datetime.fromisoformat(daily["time"][i]).strftime("%a %d %b")
            rain = daily["precipitation_probability_max"][i]
            lines.append(f"`{day}` {lookups.weather_text(daily['weather_code'][i])} · {daily['temperature_2m_min'][i]:.0f} to {daily['temperature_2m_max'][i]:.0f}°C" + (f" · {rain}% rain" if rain is not None else ""))
        await ctx.send(view=info_layout(f"{e('info')} Weather in {name}", "\n".join(lines)))

    def message_text(self, message: discord.Message) -> str:
        parts = [message.content or ""]
        for embed in message.embeds:
            parts.extend(x for x in (embed.title, embed.description) if x)
            parts.extend(f"{field.name}: {field.value}" for field in embed.fields)
        return "\n".join(p for p in parts if p).strip()

    async def fetch_linked(self, ctx: commands.Context, link: tuple[str, int, int]):
        guild_ref, channel_id, message_id = link
        channel = self.bot.get_channel(channel_id)
        if channel is None or getattr(channel, "guild", None) is None:
            return None, "I cannot see that message. It has to be in a server I am in."
        member = channel.guild.get_member(ctx.author.id)
        if member is None:
            return None, "You are not in that server."
        perms = channel.permissions_for(member)
        if not (perms.view_channel and perms.read_message_history):
            return None, "You cannot read that channel."
        try:
            return await channel.fetch_message(message_id), None
        except discord.HTTPException:
            return None, "I could not load that message."

    async def replied_message(self, ctx: commands.Context) -> Optional[discord.Message]:
        reference = getattr(ctx.message, "reference", None)
        if reference is None or not getattr(reference, "message_id", None):
            return None
        if isinstance(reference.resolved, discord.Message):
            return reference.resolved
        channel = self.bot.get_channel(reference.channel_id) or ctx.channel
        try:
            return await channel.fetch_message(reference.message_id)
        except discord.HTTPException:
            return None

    async def send_translation(self, send, text: str, code: str, label: str, source: str):
        e = emoji_manager.get
        result = await translator.translate(text, code)
        if result is None:
            return await send(view=error_layout("Could not translate", "The translation services could not translate that right now. Try again in a moment or with a shorter text."))
        translated, detected, provider = result
        pages = translator.pages(translated)
        for index, page in enumerate(pages):
            footer = ""
            if index == len(pages) - 1:
                footer = f"\n-# {source}" + (f"Detected {detected.upper()} · " if detected else "") + f"via {provider}"
            title = f"{e('info')} Translation to {label}" + (f" ({index + 1}/{len(pages)})" if len(pages) > 1 else "")
            await send(view=info_layout(title, page + footer), allowed_mentions=NO_MENTIONS)

    @commands.command(name="translate", aliases=["tr"], help="Translate text, or a message by replying to it or pasting its link. Usage: translate [language] [text or message link]")
    @COOLDOWN
    async def translate(self, ctx: commands.Context, language: str = "en", *, text: str = ""):
        link = translator.find_link(language)
        if link is not None or (language and lookups.language_code(language) is None and not text):
            text = f"{language} {text}".strip()
            language = "en"
        code = lookups.language_code(language)
        if code is None:
            return await ctx.send(view=error_layout("Unknown language", "Use a language name like `spanish` or a code like `es`. Example: `translate french good morning`."))
        label = language.title() if len(language) > 2 else code.upper()
        source = ""
        link = translator.find_link(text)
        if link is not None:
            message, problem = await self.fetch_linked(ctx, link)
            if message is None:
                return await ctx.send(view=error_layout("Cannot use that message", problem))
            text, source = self.message_text(message), f"From {message.author.display_name} · "
        elif not text.strip():
            message = await self.replied_message(ctx)
            if message is None:
                return await ctx.send(view=error_layout("Nothing to translate", "Write some text, paste a message link, or reply to a message with `translate <language>`."))
            text, source = self.message_text(message), f"From {message.author.display_name} · "
        if not text.strip():
            return await ctx.send(view=error_layout("No text", "That message has no text I can translate."))
        if len(text) > config.TRANSLATE_MAX_CHARS:
            return await ctx.send(view=error_layout("Too long", f"That is more than {config.TRANSLATE_MAX_CHARS:,} characters. Translate it in parts."))
        async with ctx.typing():
            await self.send_translation(ctx.send, text, code, label, source)

    async def translate_menu(self, interaction: discord.Interaction, message: discord.Message):
        text = self.message_text(message)
        if not text:
            return await interaction.response.send_message("That message has no text I can translate.", ephemeral=True)
        if len(text) > config.TRANSLATE_MAX_CHARS:
            return await interaction.response.send_message("That message is too long to translate.", ephemeral=True)
        locale = str(interaction.locale).split("-")[0].lower()
        code = lookups.language_code(locale) or "en"
        await interaction.response.defer(ephemeral=True)

        async def send(**kwargs):
            await interaction.followup.send(ephemeral=True, **kwargs)

        await self.send_translation(send, text, code, code.upper(), f"From {message.author.display_name} · ")

    @commands.command(name="define", aliases=["dictionary", "dict", "meaning"], help="Look up a word in the dictionary. Usage: define <word>")
    @COOLDOWN
    async def define(self, ctx: commands.Context, *, word: str):
        e = emoji_manager.get
        word = word.strip().lower()
        if not word or len(word) > 40 or " " in word.strip():
            return await ctx.send(view=error_layout("One word please", "Give me a single English word, for example `define serendipity`."))
        async with ctx.typing():
            status, data = await lookups.fetch_json(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}", ttl=86400)
        if status == 404:
            return await ctx.send(view=error_layout("No definition", f"I could not find **{word}**."))
        if status != 200 or not isinstance(data, list) or not data:
            return await ctx.send(view=unavailable("dictionary"))
        entry = data[0]
        lines = []
        if entry.get("phonetic"):
            lines.append(f"`{entry['phonetic']}`")
        for meaning in entry.get("meanings", [])[:3]:
            lines.append(f"\n**{meaning.get('partOfSpeech', '').title()}**")
            for number, definition in enumerate(meaning.get("definitions", [])[:2], 1):
                lines.append(f"{number}. {definition.get('definition', '')}")
                if definition.get("example"):
                    lines.append(f"-# “{definition['example']}”")
        await ctx.send(view=info_layout(f"{e('info')} {entry.get('word', word)}", lookups.clip("\n".join(lines).strip(), 1800)), allowed_mentions=NO_MENTIONS)

    @commands.command(name="urban", aliases=["slang", "urbandictionary"], help="Look up slang on Urban Dictionary. Only works in age-restricted channels. Usage: urban <term>")
    @COOLDOWN
    async def urban(self, ctx: commands.Context, *, term: str):
        e = emoji_manager.get
        if ctx.guild is not None and not getattr(ctx.channel, "is_nsfw", lambda: False)():
            return await ctx.send(view=error_layout("Age-restricted channels only", "Urban Dictionary entries are user written and can be explicit, so this only works in age-restricted channels."))
        async with ctx.typing():
            status, data = await lookups.fetch_json("https://api.urbandictionary.com/v0/define", {"term": term[:80]}, ttl=3600)
        if status is None or not isinstance(data, dict):
            return await ctx.send(view=unavailable("Urban Dictionary"))
        items = data.get("list") or []
        if not items:
            return await ctx.send(view=error_layout("No entry", f"Nothing found for **{lookups.clip(term, 60)}**."))
        item = max(items[:5], key=lambda x: x.get("thumbs_up", 0) - x.get("thumbs_down", 0))
        body = lookups.clip(lookups.strip_brackets(item.get("definition", "")), 900)
        example = lookups.clip(lookups.strip_brackets(item.get("example", "")), 400)
        text = body + (f"\n\n*{example}*" if example else "") + f"\n\n-# Likes {item.get('thumbs_up', 0)} · Dislikes {item.get('thumbs_down', 0)}"
        await ctx.send(view=info_layout(f"{e('info')} {lookups.clip(item.get('word', term), 80)}", text), allowed_mentions=NO_MENTIONS)

    @commands.command(name="calc", aliases=["calculate", "math"], help="Calculate an expression. Usage: calc <expression>, for example calc (3+4)*5 or calc sqrt(144)")
    async def calc(self, ctx: commands.Context, *, expression: str):
        e = emoji_manager.get
        try:
            value = lookups.calculate(expression)
        except lookups.CalcError as error:
            return await ctx.send(view=error_layout("Cannot calculate", str(error)))
        await ctx.send(view=info_layout(f"{e('info')} Calculator", f"`{lookups.clip(expression, 150)}`\n= **{lookups.format_number(value)}**"), allowed_mentions=NO_MENTIONS)

    @commands.command(name="price", aliases=["coinprice"], help="Show a cryptocurrency price. Usage: price <coin> [currency], for example price btc or price eth eur")
    @COOLDOWN
    async def price(self, ctx: commands.Context, coin: str, currency: str = "usd"):
        e = emoji_manager.get
        coin_id = lookups.COINS.get(coin.lower())
        currency = currency.lower()
        if coin_id is None:
            return await ctx.send(view=error_layout("Unknown coin", "Try one of: " + ", ".join(f"`{k}`" for k in sorted(k for k in lookups.COINS if len(k) <= 5)) + "."))
        if not currency.isalpha() or len(currency) > 5:
            return await ctx.send(view=error_layout("Unknown currency", "Use a currency code like `usd`, `eur` or `bdt`."))
        async with ctx.typing():
            status, data = await lookups.fetch_json("https://api.coingecko.com/api/v3/simple/price", {
                "ids": coin_id, "vs_currencies": currency, "include_24hr_change": "true", "include_market_cap": "true"}, ttl=60)
        if status != 200 or not isinstance(data, dict):
            return await ctx.send(view=unavailable("price"))
        row = data.get(coin_id) or {}
        if currency not in row:
            return await ctx.send(view=error_layout("Unknown currency", f"`{currency}` is not supported."))
        change = row.get(f"{currency}_24h_change")
        lines = [f"**{lookups.money(row[currency])} {currency.upper()}**"]
        if change is not None:
            lines.append(f"24h: {change:+.2f}%")
        if row.get(f"{currency}_market_cap"):
            lines.append(f"Market cap: {lookups.money(row[f'{currency}_market_cap'])} {currency.upper()}")
        lines.append("-# Prices from CoinGecko, updated about every minute.")
        await ctx.send(view=info_layout(f"{e('info')} {coin_id.replace('-', ' ').title()} ({coin.upper()})", "\n".join(lines)))

    @commands.command(name="time", aliases=["clock", "localtime"], help="Show someone's local time or the time in a timezone. Usage: time [user|timezone]")
    async def time(self, ctx: commands.Context, *, target: str = ""):
        e = emoji_manager.get
        target = target.strip()
        user: Optional[discord.abc.User] = None
        zone = None
        label = ""
        if not target:
            user = ctx.author
        else:
            try:
                user = await commands.UserConverter().convert(ctx, target)
            except commands.BadArgument:
                zone = scheduler.parse_tz(target)
                if zone is None:
                    return await ctx.send(view=error_layout("Unknown user or timezone", "Mention someone, or use a timezone like `Asia/Dhaka` or `UTC+6`."))
                label = target
        note = ""
        if user is not None:
            name, zone = await reminders.get_timezone(user.id)
            label = user.display_name
            if not await reminders.has_timezone(user.id):
                note = "\n-# No timezone set, showing UTC." + (" Set yours with `remind tz <zone>`." if user.id == ctx.author.id else "")
            else:
                label = f"{label} ({name})"
        now = datetime.now(zone)
        await ctx.send(view=info_layout(f"{e('calendar')} {label}", f"**{now.strftime('%H:%M')}** · {now.strftime('%A, %d %B %Y')}{note}"), allowed_mentions=NO_MENTIONS)


async def setup(bot: commands.Bot):
    await bot.add_cog(Lookups(bot))
