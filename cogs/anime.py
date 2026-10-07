import datetime
import random
import time
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks

from utils import anilist_client, db, emoji_manager
from utils.checks import has_guild_permission
from utils.components import error_layout, footer_block, info_layout, success_layout


def _media_view(media: dict, footer_note: Optional[str] = None) -> discord.ui.LayoutView:
    e = emoji_manager.get
    title = anilist_client.display_title(media)
    description = anilist_client.clean_description(media)
    is_manga = media.get("type") == "MANGA"
    icon = e("manga") if is_manga else e("anime")

    score = media.get("averageScore")
    score_text = f"{score}%" if score is not None else "N/A"
    genres = ", ".join(media.get("genres") or []) or "Unknown"
    year = (media.get("startDate") or {}).get("year") or "Unknown"
    status = (media.get("status") or "UNKNOWN").replace("_", " ").title()

    if is_manga:
        length_label = "Chapters"
        length_value = media.get("chapters") or "Ongoing"
    else:
        length_label = "Episodes"
        length_value = media.get("episodes") or "Ongoing"

    cover = (media.get("coverImage") or {}).get("large")
    accent_hex = (media.get("coverImage") or {}).get("color")
    accent = int(accent_hex.lstrip("#"), 16) if accent_hex else 0x5865F2

    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=accent)

    section = discord.ui.Section(accessory=discord.ui.Thumbnail(media=cover)) if cover else None
    header_text = f"## {icon} {title}"
    if section:
        section.add_item(discord.ui.TextDisplay(header_text))
        container.add_item(section)
    else:
        container.add_item(discord.ui.TextDisplay(header_text))

    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(description))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(
        f"**Score:** {score_text} · **Status:** {status} · **{length_label}:** {length_value}\n"
        f"**Year:** {year} · **Genres:** {genres}"
    ))
    container.add_item(discord.ui.Separator())

    link_row = discord.ui.ActionRow(
        discord.ui.Button(label="View on AniList", style=discord.ButtonStyle.link, url=media.get("siteUrl") or "https://anilist.co")
    )
    container.add_item(link_row)

    if footer_note:
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {footer_note}"))

    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)

    view.add_item(container)
    return view


def _strip_nsfw_flag(text: str) -> tuple[str, bool]:
    stripped = text.strip()
    lowered = stripped.lower()
    if lowered.endswith(" nsfw") or lowered == "nsfw":
        return stripped[: -len("nsfw")].strip(), True
    return stripped, False


def _resolve_nsfw(requested: bool, channel: discord.abc.GuildChannel) -> tuple[bool, Optional[str]]:
    if not requested:
        return False, None
    is_nsfw = getattr(channel, "is_nsfw", lambda: False)()
    if not is_nsfw:
        return False, "NSFW results are only available in channels marked as NSFW in Discord's own channel settings."
    return True, None


class Anime(commands.Cog):
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Soward/1.0"})
        self.daily_poster.start()

    async def cog_unload(self):
        self.daily_poster.cancel()
        if self.session:
            await self.session.close()

    @commands.command(name="animesearch", aliases=["as"], help="Search for an anime by name. Usage: animesearch <title> [nsfw]")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def animesearch(self, ctx: commands.Context, *, title: str):
        e = emoji_manager.get
        title, nsfw_requested = _strip_nsfw_flag(title)
        allow_adult, error = _resolve_nsfw(nsfw_requested, ctx.channel)
        if error:
            return await ctx.send(view=error_layout("Can't Do That", error))

        results = await anilist_client.search_media(self.session, title, "ANIME", 1, None if allow_adult else False)
        if not results:
            return await ctx.send(view=error_layout(f"{e('anime')} Not Found", f"No anime found matching `{title}`."))
        await ctx.send(view=_media_view(results[0]))

    @commands.command(name="mangasearch", aliases=["ms"], help="Search for a manga or manhwa by name. Usage: mangasearch <title> [nsfw]")
    @commands.cooldown(1, 3.0, commands.BucketType.user)
    async def mangasearch(self, ctx: commands.Context, *, title: str):
        e = emoji_manager.get
        title, nsfw_requested = _strip_nsfw_flag(title)
        allow_adult, error = _resolve_nsfw(nsfw_requested, ctx.channel)
        if error:
            return await ctx.send(view=error_layout("Can't Do That", error))

        results = await anilist_client.search_media(self.session, title, "MANGA", 1, None if allow_adult else False)
        if not results:
            return await ctx.send(view=error_layout(f"{e('manga')} Not Found", f"No manga found matching `{title}`."))
        await ctx.send(view=_media_view(results[0]))

    @commands.command(name="animerecommend", aliases=["arec"], help="Get anime recommendations similar to a title. Usage: animerecommend <title> [nsfw]")
    @commands.cooldown(1, 4.0, commands.BucketType.user)
    async def animerecommend(self, ctx: commands.Context, *, title: str):
        e = emoji_manager.get
        title, nsfw_requested = _strip_nsfw_flag(title)
        allow_adult, error = _resolve_nsfw(nsfw_requested, ctx.channel)
        if error:
            return await ctx.send(view=error_layout("Can't Do That", error))

        results = await anilist_client.search_media(self.session, title, "ANIME", 1, None if allow_adult else False)
        if not results:
            return await ctx.send(view=error_layout(f"{e('anime')} Not Found", f"No anime found matching `{title}`."))

        base = results[0]
        recs = await anilist_client.get_recommendations_for(self.session, base["id"])
        if not allow_adult:
            recs = [r for r in recs if not r.get("isAdult")]
        if not recs:
            return await ctx.send(view=error_layout(f"{e('anime')} No Recommendations", f"AniList doesn't have recommendations for **{anilist_client.display_title(base)}** yet."))

        pick = recs[0]
        note = f"Recommended because you liked {anilist_client.display_title(base)}"
        await ctx.send(view=_media_view(pick, footer_note=note))

    @commands.command(name="animerandom", aliases=["arandom", "randomanime"], help="Get a random anime, optionally filtered by genre. Usage: animerandom [genre] [nsfw]")
    @commands.cooldown(1, 4.0, commands.BucketType.user)
    async def animerandom(self, ctx: commands.Context, *, genre: Optional[str] = None):
        e = emoji_manager.get
        nsfw_requested = False
        if genre:
            genre, nsfw_requested = _strip_nsfw_flag(genre)
        allow_adult, error = _resolve_nsfw(nsfw_requested, ctx.channel)
        if error:
            return await ctx.send(view=error_layout("Can't Do That", error))

        if genre and genre.title() not in anilist_client.GENRES:
            valid = ", ".join(f"`{g}`" for g in anilist_client.GENRES)
            return await ctx.send(view=error_layout("Unknown Genre", f"Valid genres: {valid}"))

        media = await anilist_client.discover_random(self.session, "ANIME", genre.title() if genre else None, is_adult=(None if allow_adult else False))
        if not media:
            return await ctx.send(view=error_layout(f"{e('anime')} No Results", "Couldn't find anything for that genre right now."))
        await ctx.send(view=_media_view(media))

    @commands.command(name="mangarandom", aliases=["mrandom", "randommanga"], help="Get a random manga/manhwa, optionally filtered by genre. Usage: mangarandom [genre] [nsfw]")
    @commands.cooldown(1, 4.0, commands.BucketType.user)
    async def mangarandom(self, ctx: commands.Context, *, genre: Optional[str] = None):
        e = emoji_manager.get
        nsfw_requested = False
        if genre:
            genre, nsfw_requested = _strip_nsfw_flag(genre)
        allow_adult, error = _resolve_nsfw(nsfw_requested, ctx.channel)
        if error:
            return await ctx.send(view=error_layout("Can't Do That", error))

        if genre and genre.title() not in anilist_client.GENRES:
            valid = ", ".join(f"`{g}`" for g in anilist_client.GENRES)
            return await ctx.send(view=error_layout("Unknown Genre", f"Valid genres: {valid}"))

        media = await anilist_client.discover_random(self.session, "MANGA", genre.title() if genre else None, is_adult=(None if allow_adult else False))
        if not media:
            return await ctx.send(view=error_layout(f"{e('manga')} No Results", "Couldn't find anything for that genre right now."))
        await ctx.send(view=_media_view(media))

    @commands.command(name="trending", help="Show the 5 most trending anime right now.")
    @commands.cooldown(1, 4.0, commands.BucketType.user)
    async def trending(self, ctx: commands.Context):
        e = emoji_manager.get
        results = await anilist_client.get_trending(self.session, "ANIME", 5)
        if not results:
            return await ctx.send(view=error_layout(f"{e('anime')} No Results", "Couldn't fetch trending anime right now."))

        lines = [f"**{i}.** {anilist_client.display_title(m)} — {m.get('averageScore') or 'N/A'}%" for i, m in enumerate(results, 1)]
        await ctx.send(view=info_layout(f"{e('anime')} Trending Anime", "\n".join(lines)))

    @commands.group(name="animedaily", invoke_without_command=True, help="Configure the daily anime/manga recommendation for this server.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def animedaily_group(self, ctx: commands.Context):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT * FROM guild_anime_daily_config WHERE guild_id=?", (ctx.guild.id,))
        if not row or not row["enabled"]:
            body = (
                "Daily recommendations are **disabled**.\n\n"
                "Set up with `animedaily channel #channel`, then `animedaily enable`."
            )
            return await ctx.send(view=info_layout(f"{e('anime')} Daily Recommendations", body))

        channel = ctx.guild.get_channel(row["channel_id"]) if row["channel_id"] else None
        ping_role_text = f"<@&{row['role_id']}>" if row["role_id"] else "None"
        body = (
            f"**Status:** Enabled\n"
            f"**Channel:** {channel.mention if channel else 'Not set'}\n"
            f"**Type:** {row['media_type'].title()}\n"
            f"**Genre filter:** {row['genre_filter'] or 'Any'}\n"
            f"**Post time:** {row['post_hour_utc']:02d}:{(row['post_minute_utc'] or 0):02d} UTC\n"
            f"**Ping role:** {ping_role_text}"
        )
        await ctx.send(view=info_layout(f"{e('anime')} Daily Recommendations", body))

    @animedaily_group.command(name="channel", help="Set the channel for daily recommendations.")
    @has_guild_permission("manage_guild")
    async def animedaily_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        e = emoji_manager.get
        await db.raw_execute(
            "INSERT INTO guild_anime_daily_config (guild_id, channel_id) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id",
            (ctx.guild.id, channel.id),
        )
        await ctx.send(view=success_layout(f"{e('check')} Channel Set", f"Daily recommendations will post in {channel.mention}."))

    @animedaily_group.command(name="enable", help="Enable daily recommendations.")
    @has_guild_permission("manage_guild")
    async def animedaily_enable(self, ctx: commands.Context):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT channel_id FROM guild_anime_daily_config WHERE guild_id=?", (ctx.guild.id,))
        if not row or not row["channel_id"]:
            return await ctx.send(view=error_layout("No Channel Set", "Set a channel first with `animedaily channel #channel`."))

        await db.raw_execute(
            "INSERT INTO guild_anime_daily_config (guild_id, enabled) VALUES (?, 1)"
            " ON CONFLICT(guild_id) DO UPDATE SET enabled=1",
            (ctx.guild.id,),
        )
        await ctx.send(view=success_layout(f"{e('check')} Enabled", "Daily anime/manga recommendations are now active."))

    @animedaily_group.command(name="disable", help="Disable daily recommendations.")
    @has_guild_permission("manage_guild")
    async def animedaily_disable(self, ctx: commands.Context):
        e = emoji_manager.get
        await db.raw_execute(
            "INSERT INTO guild_anime_daily_config (guild_id, enabled) VALUES (?, 0)"
            " ON CONFLICT(guild_id) DO UPDATE SET enabled=0",
            (ctx.guild.id,),
        )
        await ctx.send(view=success_layout(f"{e('check')} Disabled", "Daily recommendations have been turned off."))

    @animedaily_group.command(name="type", help="Set whether daily recommendations are anime or manga. Usage: animedaily type <anime|manga>")
    @has_guild_permission("manage_guild")
    async def animedaily_type(self, ctx: commands.Context, media_type: str):
        e = emoji_manager.get
        media_type = media_type.upper()
        if media_type not in ("ANIME", "MANGA"):
            return await ctx.send(view=error_layout("Invalid Type", "Use `anime` or `manga`."))

        await db.raw_execute(
            "INSERT INTO guild_anime_daily_config (guild_id, media_type) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET media_type=excluded.media_type",
            (ctx.guild.id, media_type),
        )
        await ctx.send(view=success_layout(f"{e('check')} Type Set", f"Daily recommendations will now be **{media_type.title()}**."))

    @animedaily_group.command(name="genre", help="Set a genre filter for daily recommendations, or 'any' to clear it.")
    @has_guild_permission("manage_guild")
    async def animedaily_genre(self, ctx: commands.Context, *, genre: str):
        e = emoji_manager.get
        if genre.lower() == "any":
            await db.raw_execute(
                "INSERT INTO guild_anime_daily_config (guild_id, genre_filter) VALUES (?, NULL)"
                " ON CONFLICT(guild_id) DO UPDATE SET genre_filter=NULL",
                (ctx.guild.id,),
            )
            return await ctx.send(view=success_layout(f"{e('check')} Genre Cleared", "Daily recommendations will now use any genre."))

        if genre.title() not in anilist_client.GENRES:
            valid = ", ".join(f"`{g}`" for g in anilist_client.GENRES)
            return await ctx.send(view=error_layout("Unknown Genre", f"Valid genres: {valid}"))

        await db.raw_execute(
            "INSERT INTO guild_anime_daily_config (guild_id, genre_filter) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET genre_filter=excluded.genre_filter",
            (ctx.guild.id, genre.title()),
        )
        await ctx.send(view=success_layout(f"{e('check')} Genre Set", f"Daily recommendations will now be filtered to **{genre.title()}**."))

    @animedaily_group.command(name="time", help="Set the time (UTC) daily recommendations post at. Usage: animedaily time <HH:MM or HH>, e.g. 9:40 or 14")
    @has_guild_permission("manage_guild")
    async def animedaily_time(self, ctx: commands.Context, time_str: str):
        e = emoji_manager.get

        if ":" in time_str:
            parts = time_str.split(":", 1)
            if len(parts) != 2 or not parts[0].strip().lstrip("-").isdigit() or not parts[1].strip().isdigit():
                return await ctx.send(view=error_layout("Invalid Time", "Use the format `HH:MM`, e.g. `9:40` or `14:05`."))
            hour, minute = int(parts[0]), int(parts[1])
        else:
            if not time_str.strip().lstrip("-").isdigit():
                return await ctx.send(view=error_layout("Invalid Time", "Use the format `HH:MM`, e.g. `9:40`, or just an hour like `14`."))
            hour, minute = int(time_str), 0

        if not (0 <= hour <= 23):
            return await ctx.send(view=error_layout("Invalid Hour", "Hour must be between 0 and 23 (UTC)."))
        if not (0 <= minute <= 59):
            return await ctx.send(view=error_layout("Invalid Minute", "Minute must be between 0 and 59."))

        await db.raw_execute(
            "INSERT INTO guild_anime_daily_config (guild_id, post_hour_utc, post_minute_utc) VALUES (?, ?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET post_hour_utc=excluded.post_hour_utc, post_minute_utc=excluded.post_minute_utc",
            (ctx.guild.id, hour, minute),
        )
        await ctx.send(view=success_layout(f"{e('check')} Time Set", f"Daily recommendations will post at **{hour:02d}:{minute:02d} UTC**."))

    @animedaily_group.command(name="role", help="Set a role to ping when a daily recommendation posts, or 'none' to clear it.")
    @has_guild_permission("manage_guild")
    async def animedaily_role(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        e = emoji_manager.get
        role_id = role.id if role else None
        await db.raw_execute(
            "INSERT INTO guild_anime_daily_config (guild_id, role_id) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET role_id=excluded.role_id",
            (ctx.guild.id, role_id),
        )
        if role:
            await ctx.send(view=success_layout(f"{e('check')} Ping Role Set", f"{role.mention} will be pinged for daily recommendations."))
        else:
            await ctx.send(view=success_layout(f"{e('check')} Ping Role Cleared", "Daily recommendations will no longer ping a role."))

    @animedaily_group.command(name="nsfw", help="Toggle whether daily recommendations can include adult (18+) content. Requires the configured channel to be marked NSFW.")
    @has_guild_permission("manage_guild")
    async def animedaily_nsfw(self, ctx: commands.Context):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT channel_id, nsfw FROM guild_anime_daily_config WHERE guild_id=?", (ctx.guild.id,))
        if not row or not row["channel_id"]:
            return await ctx.send(view=error_layout("No Channel Set", "Set a channel first with `animedaily channel #channel`."))

        channel = ctx.guild.get_channel(row["channel_id"])
        new_value = not row["nsfw"]

        if new_value:
            if not channel or not channel.is_nsfw():
                return await ctx.send(view=error_layout(
                    "Channel Not NSFW",
                    f"{channel.mention if channel else 'The configured channel'} must be marked as NSFW in Discord's channel settings before daily recommendations can include adult content.",
                ))

        await db.raw_execute(
            "INSERT INTO guild_anime_daily_config (guild_id, nsfw) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET nsfw=excluded.nsfw",
            (ctx.guild.id, int(new_value)),
        )
        state = "may now include" if new_value else "will no longer include"
        await ctx.send(view=success_layout(f"{e('check')} NSFW Setting Updated", f"Daily recommendations {state} adult (18+) content."))

    @tasks.loop(minutes=15)
    async def daily_poster(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

        configs = await db.raw_fetch(
            "SELECT * FROM guild_anime_daily_config WHERE enabled=1 AND channel_id IS NOT NULL",
        )

        for config_row in configs:
            post_hour = config_row["post_hour_utc"]
            post_minute = config_row["post_minute_utc"] or 0
            target_minutes = (post_hour * 60) + post_minute
            now_minutes = (now.hour * 60) + now.minute
            if now_minutes < target_minutes:
                continue

            last_posted = config_row["last_posted_at"]
            if last_posted and last_posted >= today_start:
                continue

            guild = self.bot.get_guild(config_row["guild_id"])
            if not guild:
                continue
            channel = guild.get_channel(config_row["channel_id"])
            if not channel:
                continue

            allow_adult = bool(config_row["nsfw"]) and channel.is_nsfw()

            media = await anilist_client.discover_random(
                self.session, config_row["media_type"], config_row["genre_filter"],
                is_adult=(None if allow_adult else False),
            )
            if not media:
                continue

            recent = await db.raw_fetch(
                "SELECT media_id FROM anime_daily_history WHERE guild_id=? ORDER BY posted_at DESC LIMIT 20",
                (config_row["guild_id"],),
            )
            recent_ids = {r["media_id"] for r in recent}
            attempts = 0
            while media and media["id"] in recent_ids and attempts < 5:
                media = await anilist_client.discover_random(
                    self.session, config_row["media_type"], config_row["genre_filter"],
                    is_adult=(None if allow_adult else False),
                )
                attempts += 1

            if not media:
                continue

            content = f"<@&{config_row['role_id']}>" if config_row["role_id"] else None
            try:
                if content:
                    await channel.send(content=content, allowed_mentions=discord.AllowedMentions(roles=True))
                await channel.send(view=_media_view(media, footer_note="Today's recommendation"))
            except discord.HTTPException:
                continue

            await db.raw_execute(
                "INSERT INTO anime_daily_history (guild_id, media_id, posted_at) VALUES (?, ?, ?)",
                (config_row["guild_id"], media["id"], time.time()),
            )
            await db.raw_execute(
                "UPDATE guild_anime_daily_config SET last_posted_at=? WHERE guild_id=?",
                (time.time(), config_row["guild_id"]),
            )

    @daily_poster.before_loop
    async def _before_daily_poster(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Anime(bot))
