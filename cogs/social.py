import random
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from utils import db, emoji_manager
from utils.colors import NEUTRAL
from utils.components import error_layout, footer_block

PROVIDERS = {
    "nekos_best": {
        "url": "https://nekos.best/api/v2/{action}",
        "parse": lambda d: (d.get("results") or [{}])[0].get("url"),
        "parse_anime": lambda d: (d.get("results") or [{}])[0].get("anime_name"),
    },
    "waifu_pics": {
        "url": "https://api.waifu.pics/sfw/{action}",
        "parse": lambda d: d.get("url"),
        "parse_anime": lambda d: None,
    },
    "otakugifs": {
        "url": "https://api.otakugifs.xyz/gif?reaction={action}",
        "parse": lambda d: d.get("url"),
        "parse_anime": lambda d: None,
    },
}

ACTION_MAP = {
    "hug": {"nekos_best": "hug", "waifu_pics": "hug", "otakugifs": "hug"},
    "kiss": {"nekos_best": "kiss", "waifu_pics": "kiss", "otakugifs": "kiss"},
    "slap": {"nekos_best": "slap", "waifu_pics": "slap", "otakugifs": "slap"},
    "pat": {"nekos_best": "pat", "waifu_pics": "pat", "otakugifs": "pat"},
    "cuddle": {"nekos_best": "cuddle", "waifu_pics": "cuddle", "otakugifs": "cuddle"},
    "poke": {"nekos_best": "poke", "waifu_pics": "poke", "otakugifs": "poke"},
    "tickle": {"nekos_best": "tickle", "otakugifs": "tickle"},
    "feed": {"nekos_best": "feed", "waifu_pics": "nom", "otakugifs": "feed"},
    "wave": {"nekos_best": "wave", "waifu_pics": "wave", "otakugifs": "wave"},
    "blush": {"nekos_best": "blush", "waifu_pics": "blush", "otakugifs": "blush"},
    "smile": {"nekos_best": "smile", "waifu_pics": "smile", "otakugifs": "smile"},
    "wink": {"nekos_best": "wink", "waifu_pics": "wink", "otakugifs": "wink"},
    "dance": {"nekos_best": "dance", "waifu_pics": "dance", "otakugifs": "dance"},
    "cry": {"nekos_best": "cry", "waifu_pics": "cry", "otakugifs": "cry"},
    "handhold": {"nekos_best": "handhold", "waifu_pics": "handhold", "otakugifs": "handhold"},
    "punch": {"nekos_best": "punch", "otakugifs": "punch"},
    "stare": {"nekos_best": "stare", "otakugifs": "stare"},
    "highfive": {"nekos_best": "highfive", "waifu_pics": "highfive", "otakugifs": "highfive"},
    "laugh": {"nekos_best": "laugh", "otakugifs": "laugh"},
    "pout": {"nekos_best": "pout", "otakugifs": "pout"},
    "shrug": {"nekos_best": "shrug", "otakugifs": "shrug"},
    "sleep": {"nekos_best": "sleep", "otakugifs": "sleep"},
    "yeet": {"nekos_best": "yeet", "waifu_pics": "yeet", "otakugifs": "yeet"},
    "bored": {"nekos_best": "bored", "otakugifs": "bored"},
    "shoot": {"nekos_best": "shoot", "otakugifs": "shoot"},
    "dodge": {"nekos_best": "dodge", "otakugifs": "run"},
    "hide": {"nekos_best": "lurk", "otakugifs": "lurk"},
    "scared": {"otakugifs": "surprised"},
    "kick": {"nekos_best": "kick", "waifu_pics": "kick", "otakugifs": "kick"},
    "bite": {"nekos_best": "bite", "waifu_pics": "bite", "otakugifs": "bite"},
    "lick": {"waifu_pics": "lick", "otakugifs": "lick"},
    "bully": {"waifu_pics": "bully", "otakugifs": "bully"},
    "smug": {"nekos_best": "smug", "waifu_pics": "smug", "otakugifs": "smug"},
    "happy": {"nekos_best": "happy", "waifu_pics": "happy", "otakugifs": "happy"},
    "cringe": {"waifu_pics": "cringe"},
    "think": {"nekos_best": "think"},
    "handshake": {"nekos_best": "handshake"},
}


class Social(commands.Cog):
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self._nb_categories: Optional[set] = None
        self._og_categories: Optional[set] = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Soward/1.0"})
        try:
            async with self.session.get("https://nekos.best/api/v2/endpoints", timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    self._nb_categories = set(data.keys())
        except Exception:
            pass
        try:
            async with self.session.get("https://api.otakugifs.xyz/gif/allreactions", timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    self._og_categories = {r.lower() for r in data.get("reactions", [])}
        except Exception:
            pass

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    def _result_layout(self, action: str, body: str, image_url: str, anime: Optional[str], stat_line: Optional[str], emoji_key: Optional[str] = None) -> discord.ui.LayoutView:
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=NEUTRAL)
        text = f"## {emoji_manager.get(emoji_key or action)} {action.capitalize()}\n{body}"
        if stat_line:
            text += f"\n{stat_line}"
        container.add_item(discord.ui.TextDisplay(text))
        container.add_item(discord.ui.Separator())
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media=image_url)
        container.add_item(gallery)
        if anime:
            container.add_item(discord.ui.TextDisplay(f"-# Anime: {anime}"))
        container.add_item(discord.ui.Separator())
        for item in footer_block():
            container.add_item(item)
        view.add_item(container)
        return view

    async def _fetch_interaction_gif(self, action: str):
        candidates = list(ACTION_MAP.get(action, {}).items())
        random.shuffle(candidates)
        for provider_key, provider_action in candidates:
            if provider_key == "nekos_best" and self._nb_categories is not None and provider_action not in self._nb_categories:
                continue
            if provider_key == "otakugifs" and self._og_categories is not None and provider_action not in self._og_categories:
                continue
            provider = PROVIDERS[provider_key]
            try:
                async with self.session.get(provider["url"].format(action=provider_action), timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    url = provider["parse"](data)
                    if not url:
                        continue
                    anime = provider["parse_anime"](data)
                    return url, anime
            except Exception:
                continue
        return None, None

    async def _do_interaction(self, ctx: commands.Context, target: Optional[discord.Member], action: str, verb: str, emoji_key: Optional[str] = None):
        if target is not None and target.id == ctx.author.id:
            return await ctx.send(view=error_layout(f"{emoji_manager.get(emoji_key or action)} Hold on", f"You can't {action} yourself!"))

        url, anime = await self._fetch_interaction_gif(action)
        if not url:
            return await ctx.send(view=error_layout(
                f"{emoji_manager.get('cross')} No luck",
                f"Couldn't fetch a `{action}` GIF right now — every provider was unavailable. Try again in a moment.",
            ))

        stat_line = None
        if target is not None:
            received_key = f"rec:{action}:{target.id}"
            ids = sorted((ctx.author.id, target.id))
            mutual_key = f"mut:{action}:{ids[0]}:{ids[1]}"
            received_count = (await db.get("social_stats", received_key) or 0) + 1
            await db.set("social_stats", received_key, received_count)
            mutual_count = (await db.get("social_stats", mutual_key) or 0) + 1
            await db.set("social_stats", mutual_key, mutual_count)
            body = f"**{ctx.author.display_name}** {verb} **{target.display_name}**!"
            stat_line = f"-# They've {action}ed each other {mutual_count}x · {target.display_name} has been {action}ed {received_count}x"
        else:
            body = f"**{ctx.author.display_name}** {verb}!"

        await ctx.send(view=self._result_layout(action, body, url, anime, stat_line, emoji_key))

    @commands.command(name="hug", help="Give someone a warm hug.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def hug(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "hug", "hugs")

    @commands.command(name="kiss", help="Give someone a sweet kiss.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def kiss(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "kiss", "kisses")

    @commands.command(name="slap", help="Slap someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def slap(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "slap", "slapped")

    @commands.command(name="pat", help="Give someone a gentle pat.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def pat(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "pat", "pats")

    @commands.command(name="cuddle", help="Cuddle with someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def cuddle(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "cuddle", "cuddles with")

    @commands.command(name="poke", help="Poke someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def poke(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "poke", "pokes")

    @commands.command(name="tickle", help="Tickle someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def tickle(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "tickle", "tickles")

    @commands.command(name="feed", help="Feed someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def feed(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "feed", "feeds")

    @commands.command(name="wave", help="Wave hello to someone or just wave.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def wave(self, ctx: commands.Context, target: discord.Member = None):
        verb = "waves at" if target else "waves"
        await self._do_interaction(ctx, target, "wave", verb)

    @commands.command(name="blush", help="Blush at someone or just blush.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def blush(self, ctx: commands.Context, target: discord.Member = None):
        verb = "blushes at" if target else "blushes"
        await self._do_interaction(ctx, target, "blush", verb)

    @commands.command(name="smile", help="Smile at someone or just smile.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def smile(self, ctx: commands.Context, target: discord.Member = None):
        verb = "smiles at" if target else "smiles"
        await self._do_interaction(ctx, target, "smile", verb)

    @commands.command(name="wink", help="Wink at someone or just wink.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def wink(self, ctx: commands.Context, target: discord.Member = None):
        verb = "winks at" if target else "winks"
        await self._do_interaction(ctx, target, "wink", verb)

    @commands.command(name="dance", help="Dance with someone or just dance.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def dance(self, ctx: commands.Context, target: discord.Member = None):
        verb = "dances with" if target else "is dancing"
        await self._do_interaction(ctx, target, "dance", verb)

    @commands.command(name="cry", help="Cry on someone's shoulder or just cry.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def cry(self, ctx: commands.Context, target: discord.Member = None):
        verb = "cries on" if target else "is crying"
        await self._do_interaction(ctx, target, "cry", verb)

    @commands.command(name="handhold", help="Hold someone's hand.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def handhold(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "handhold", "holds the hand of")

    @commands.command(name="punch", help="Punch someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def punch(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "punch", "punches")

    @commands.command(name="stare", help="Stare at someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def stare(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "stare", "stares at")

    @commands.command(name="highfive", help="Give someone a high five.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def highfive(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "highfive", "high-fives")

    @commands.command(name="laugh", help="Laugh at someone or just laugh.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def laugh(self, ctx: commands.Context, target: discord.Member = None):
        verb = "laughs at" if target else "laughs"
        await self._do_interaction(ctx, target, "laugh", verb)

    @commands.command(name="pout", help="Pout at someone or just pout.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def pout(self, ctx: commands.Context, target: discord.Member = None):
        verb = "pouts at" if target else "pouts"
        await self._do_interaction(ctx, target, "pout", verb)

    @commands.command(name="shrug", help="Shrug at someone or just shrug.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def shrug(self, ctx: commands.Context, target: discord.Member = None):
        verb = "shrugs at" if target else "shrugs"
        await self._do_interaction(ctx, target, "shrug", verb)

    @commands.command(name="sleep", help="Go to sleep.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def sleep(self, ctx: commands.Context):
        await self._do_interaction(ctx, None, "sleep", "is sleeping")

    @commands.command(name="yeet", help="Yeet someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def yeet(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "yeet", "yeeted")

    @commands.command(name="bored", help="Show how bored you are.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def bored(self, ctx: commands.Context):
        await self._do_interaction(ctx, None, "bored", "is bored")

    @commands.command(name="shoot", help="Shoot someone (virtually).")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def shoot_social(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "shoot", "shoots")

    @commands.command(name="dodge", help="Dodge an attack!")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def dodge_social(self, ctx: commands.Context, target: discord.Member = None):
        verb = "dodges an attack from" if target else "dodges"
        await self._do_interaction(ctx, target, "dodge", verb)

    @commands.command(name="hide", help="Hide from someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def hide_social(self, ctx: commands.Context, target: discord.Member = None):
        verb = "hides from" if target else "is hiding"
        await self._do_interaction(ctx, target, "hide", verb)

    @commands.command(name="scared", help="Show how scared you are.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def scared_social(self, ctx: commands.Context, target: discord.Member = None):
        verb = "is scared of" if target else "is scared"
        await self._do_interaction(ctx, target, "scared", verb)

    @commands.command(name="skick", help="Socially kick someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def skick_social(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "kick", "kicked", emoji_key="skick")

    @commands.command(name="bite", help="Bite someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def bite_social(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "bite", "bites")

    @commands.command(name="threaten", help="Threaten someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def threaten_social(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "shoot", "threatens", emoji_key="threaten")

    @commands.command(name="lick", help="Lick someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def lick_social(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "lick", "licks")

    @commands.command(name="glare", help="Glare at someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def glare_social(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "stare", "glares at", emoji_key="glare")

    @commands.command(name="bully", help="Bully someone (playfully).")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def bully_social(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "bully", "bullies")

    @commands.command(name="smug", help="Look smug.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def smug_social(self, ctx: commands.Context, target: discord.Member = None):
        verb = "smugs at" if target else "is acting smug"
        await self._do_interaction(ctx, target, "smug", verb)

    @commands.command(name="happy", help="Show how happy you are.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def happy_social(self, ctx: commands.Context):
        await self._do_interaction(ctx, None, "happy", "is happy")

    @commands.command(name="cringe", help="Show your cringe reaction.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def cringe_social(self, ctx: commands.Context, target: discord.Member = None):
        verb = "cringes at" if target else "cringes"
        await self._do_interaction(ctx, target, "cringe", verb)

    @commands.command(name="snuggle", help="Snuggle with someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def snuggle_social(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "cuddle", "snuggles with", emoji_key="snuggle")

    @commands.command(name="nom", help="Nom nom nom!")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def nom_social(self, ctx: commands.Context, target: discord.Member = None):
        verb = "noms on" if target else "noms"
        await self._do_interaction(ctx, target, "feed", verb, emoji_key="nom")

    @commands.command(name="angry", help="Show how angry you are.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def angry_social(self, ctx: commands.Context, target: discord.Member = None):
        verb = "is angry at" if target else "is angry"
        await self._do_interaction(ctx, target, "kick", verb, emoji_key="angry")

    @commands.command(name="sad", help="Show how sad you are.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def sad_social(self, ctx: commands.Context):
        await self._do_interaction(ctx, None, "cry", "is sad", emoji_key="sad")

    @commands.command(name="think", aliases=["thinking"], help="Show that you are thinking.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def think_social(self, ctx: commands.Context):
        await self._do_interaction(ctx, None, "think", "is thinking")

    @commands.command(name="confused", help="Show how confused you are.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def confused_social(self, ctx: commands.Context):
        await self._do_interaction(ctx, None, "think", "is confused", emoji_key="confused")

    @commands.command(name="handshake", help="Shake hands with someone.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def handshake_social(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "handshake", "shakes hands with")

    @commands.command(name="disgust", help="Show your disgust.")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def disgust_social(self, ctx: commands.Context, target: discord.Member = None):
        verb = "is disgusted by" if target else "is disgusted"
        await self._do_interaction(ctx, target, "stare", verb, emoji_key="disgust")

    @commands.command(name="scare", help="Scare someone!")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def scare_social(self, ctx: commands.Context, target: discord.Member):
        await self._do_interaction(ctx, target, "shoot", "scares", emoji_key="scare")


async def setup(bot: commands.Bot):
    await bot.add_cog(Social(bot))
