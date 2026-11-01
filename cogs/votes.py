import logging
import time

import aiohttp
import discord
from discord.ext import commands, tasks

import config
from utils import coins as coin_store, emoji_manager, prefix as prefix_utils, votes
from utils.components import info_layout, success_layout

log = logging.getLogger("soward.votes")


def remaining(seconds: float) -> str:
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes = rest // 60
    return f"{hours}h {minutes}m" if hours else f"{minutes}m"


class Votes(commands.Cog):
    category = "Utility"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session = None

    async def cog_load(self):
        if config.VOTE_DBL_TOKEN:
            self.post_stats.start()

    async def cog_unload(self):
        self.post_stats.cancel()
        if self.session is not None:
            await self.session.close()

    async def send_stats(self) -> int:
        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        payload = {
            "guilds": len(self.bot.guilds),
            "users": sum(g.member_count or 0 for g in self.bot.guilds),
            "voice_connections": len(self.bot.voice_clients),
        }
        url = f"https://discordbotlist.com/api/v1/bots/{self.bot.user.id}/stats"
        async with self.session.post(url, json=payload, headers={"Authorization": config.VOTE_DBL_TOKEN}) as resp:
            return resp.status

    @tasks.loop(minutes=config.VOTE_STATS_MINUTES)
    async def post_stats(self):
        try:
            status = await self.send_stats()
            if status >= 400:
                log.warning("discordbotlist stats post failed with status %s", status)
        except Exception:
            log.warning("discordbotlist stats post failed", exc_info=True)

    @post_stats.before_loop
    async def before_post_stats(self):
        await self.bot.wait_until_ready()

    def vote_links(self) -> list[str]:
        links = []
        if config.VOTE_DBL_SECRET and self.bot.user:
            links.append(f"[discordbotlist.com](https://discordbotlist.com/bots/{self.bot.user.id}/upvote)")
        return links

    async def handle_vote(self, user_id: int, source: str) -> None:
        row = await votes.record(user_id, source)
        prefix_utils.grant_vote_no_prefix(user_id, row["np_until"])
        reward = int(config.VOTE_COINS.get(source, 0))
        if reward:
            await coin_store.add(user_id, reward)
        e = emoji_manager.get
        user = self.bot.get_user(user_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(user_id)
            except discord.HTTPException:
                return
        body = (
            f"{e('star')} Thanks for voting for Soward.\n"
            + (f"{e('coin')} **+{coin_store.fmt(reward)}** coins.\n" if reward else "")
            + f"You now have **global no-prefix** for **{config.VOTE_NP_HOURS} hours**.\n"
            f"Votes: **{row['total']}** · Streak: **{row['streak']}**"
        )
        try:
            await user.send(view=success_layout("Vote received", body))
        except discord.HTTPException:
            pass

    @commands.command(name="vote", help="Vote for Soward and get global no-prefix for a while.")
    async def vote(self, ctx: commands.Context):
        e = emoji_manager.get
        links = self.vote_links()
        if not links:
            return await ctx.send(view=info_layout("Vote", "Voting is not set up yet."))
        row = await votes.get(ctx.author.id)
        lines = [f"{e('gift')} Vote on {' or '.join(links)} to get **{coin_store.fmt(max(config.VOTE_COINS.values(), default=0))}** coins and **global no-prefix** for **{config.VOTE_NP_HOURS} hours**. You can vote again every 12 hours."]
        if row:
            now = time.time()
            lines.append(f"\nYour votes: **{row['total']}** · Streak: **{row['streak']}**")
            if row["np_until"] > now:
                lines.append(f"No-prefix left: **{remaining(row['np_until'] - now)}**")
        await ctx.send(view=info_layout("Vote for Soward", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Votes(bot))
