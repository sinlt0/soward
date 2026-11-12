import json
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands, tasks

import config
from utils import db
from utils.components import info_layout

SOURCE = Path(__file__).resolve().parent.parent / "dashboard" / "content" / "changelog.json"
NO_MENTIONS = discord.AllowedMentions.none()


def load_entries() -> list:
    try:
        with open(SOURCE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    return [row for row in data if isinstance(row, dict) and row.get("version")]


def pending(entries: list, posted: Optional[str]) -> list:
    if not entries:
        return []
    versions = [str(row["version"]) for row in entries]
    if posted in versions:
        fresh = entries[: versions.index(posted)]
    else:
        fresh = entries[:1]
    return list(reversed(fresh[: config.CHANGELOG_MAX_POSTS]))


def render(entry: dict) -> tuple:
    title = f"{config.BOT_NAME} {entry['version']}"
    if entry.get("title"):
        title += f"  ·  {entry['title']}"
    lines = "\n".join(f"- {item}" for item in entry.get("items", []))
    date = f"\n\n-# Released {entry['date']}" if entry.get("date") else ""
    return title, (lines + date)[:3800]


class ChangelogSync(commands.Cog):
    category = "Utility"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.watcher.start()

    def cog_unload(self):
        self.watcher.cancel()

    async def _channel(self) -> Optional[discord.abc.Messageable]:
        if not config.CHANGELOG_CHANNEL_ID:
            return None
        channel = self.bot.get_channel(config.CHANGELOG_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(config.CHANGELOG_CHANNEL_ID)
            except discord.HTTPException:
                return None
        return channel if hasattr(channel, "send") else None

    async def sync(self) -> int:
        entries = load_entries()
        if not entries:
            return 0
        state = await db.get("dev", "changelog_posted")
        posted = str(state.get("version")) if isinstance(state, dict) and state.get("version") else None
        fresh = pending(entries, posted)
        if not fresh:
            return 0
        channel = await self._channel()
        if channel is None:
            return 0
        sent = 0
        for entry in fresh:
            title, body = render(entry)
            try:
                message = await channel.send(view=info_layout(title, body), allowed_mentions=NO_MENTIONS)
            except discord.HTTPException:
                break
            sent += 1
            await db.set("dev", "changelog_posted", {"version": str(entry["version"])})
            if getattr(channel, "is_news", None) and channel.is_news():
                try:
                    await message.publish()
                except discord.HTTPException:
                    pass
        return sent

    @tasks.loop(minutes=config.CHANGELOG_CHECK_MINUTES)
    async def watcher(self):
        await self.sync()

    @watcher.before_loop
    async def _before_watcher(self):
        await self.bot.wait_until_ready()

    @watcher.error
    async def _watcher_error(self, error: BaseException):
        if not self.watcher.is_running():
            self.watcher.restart()


async def setup(bot: commands.Bot):
    await bot.add_cog(ChangelogSync(bot))
