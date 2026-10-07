import logging
import math

import discord
from discord.ext import commands

from utils import emoji_manager
from utils.components import footer_block
from utils.prefix import get_guild_prefix
import config

log = logging.getLogger("soward.events.mention_menu")


def _is_bare_mention(bot: commands.Bot, message: discord.Message) -> bool:
    if not message.content:
        return False
    if message.reference:
        return False
    stripped = message.content.strip()
    bot_id = bot.user.id
    return stripped in (f"<@{bot_id}>", f"<@!{bot_id}>")


class MentionMenuLinksRow(discord.ui.ActionRow):
    def __init__(self, bot: commands.Bot, prefix: str):
        invite_url = discord.utils.oauth_url(
            bot.user.id,
            permissions=discord.Permissions(administrator=True),
            scopes=("bot", "applications.commands"),
        )
        super().__init__(
            discord.ui.Button(label="Help", style=discord.ButtonStyle.secondary, custom_id="mentionmenu:help"),
            discord.ui.Button(label="Invite", style=discord.ButtonStyle.link, url=invite_url),
            discord.ui.Button(label="Owners & Devs", style=discord.ButtonStyle.secondary, custom_id="mentionmenu:owners"),
        )
        self.prefix = prefix
        self.children[0].callback = self._show_help
        self.children[2].callback = self._show_owners

    async def _show_help(self, interaction: discord.Interaction):
        await interaction.response.send_message(
            content=f"Use `{self.prefix}help` to see everything I can do.", ephemeral=True
        )

    async def _show_owners(self, interaction: discord.Interaction):
        from cogs.utility import _build_team_body
        e = emoji_manager.get
        body = await _build_team_body(interaction.client)
        view = discord.ui.LayoutView(timeout=60)
        container = discord.ui.Container(accent_color=0x5865F2)
        container.add_item(discord.ui.TextDisplay(f"## {e('soward')} Owners & Developers"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(body))
        view.add_item(container)
        await interaction.response.send_message(view=view, ephemeral=True)


def _build_mention_menu(bot: commands.Bot, prefix: str, guild: discord.Guild | None) -> discord.ui.LayoutView:
    e = emoji_manager.get
    view = discord.ui.LayoutView(timeout=120)
    container = discord.ui.Container(accent_color=0x5865F2)

    container.add_item(discord.ui.TextDisplay(
        f"## {e('soward')} Hey, I'm {config.BOT_NAME}!\n"
        f"My prefix here is `{prefix}` — try `{prefix}help` to see everything I can do."
    ))
    container.add_item(discord.ui.Separator())

    guild_count = len(bot.guilds)
    member_count = sum(g.member_count or 0 for g in bot.guilds)
    latency_ms = 0 if math.isnan(bot.latency) else round(bot.latency * 1000)

    container.add_item(discord.ui.TextDisplay(
        f"{e('guild')} **Servers:** `{guild_count:,}`\n"
        f"{e('members')} **Users:** `{member_count:,}`\n"
        f"{e('ping')} **Latency:** `{latency_ms}ms`"
    ))
    container.add_item(discord.ui.Separator())

    if guild is not None:
        container.add_item(discord.ui.TextDisplay(
            f"{e('settings')} **This server's prefix:** `{prefix}`\n"
            f"-# Change it anytime with `{prefix}prefix <new prefix>`"
        ))
    else:
        container.add_item(discord.ui.TextDisplay(
            f"{e('settings')} **Your prefix here:** `{prefix}`"
        ))
    container.add_item(discord.ui.Separator())

    container.add_item(MentionMenuLinksRow(bot, prefix))
    container.add_item(discord.ui.Separator())

    for item in footer_block():
        container.add_item(item)

    view.add_item(container)
    return view


def setup(bot: commands.Bot) -> None:
    @bot.listen("on_message")
    async def _on_bare_mention(message: discord.Message):
        if message.author.bot:
            return
        if not _is_bare_mention(bot, message):
            return

        prefix = await get_guild_prefix(message.guild.id) if message.guild else config.DEFAULT_PREFIX
        view = _build_mention_menu(bot, prefix, message.guild)

        try:
            await message.channel.send(view=view)
        except discord.HTTPException:
            log.warning("Failed to send mention menu in channel %s.", message.channel.id)
