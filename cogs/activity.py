import discord
from discord.ext import commands

import config
from utils import emoji_manager
from utils.colors import NEUTRAL
from utils.components import error_layout

LAUNCH_ID = "mact:launch"


def launch_view(launchable: bool = True) -> discord.ui.LayoutView:
    e = emoji_manager.get
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=NEUTRAL)
    container.add_item(discord.ui.TextDisplay(
        f"## {e('music_note')} {config.BOT_NAME} Music\n"
        "A full music app that runs inside Discord. Search songs, build playlists, like tracks and keep a queue. "
        "While you listen, your Discord status shows **Listening to** the song with its cover art.\n\n"
        "It works in servers, in voice channels and in DMs, and your library follows your account."
    ))
    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="Open Music", style=discord.ButtonStyle.success, custom_id=LAUNCH_ID, disabled=not launchable))
    container.add_item(row)
    view.add_item(container)
    return view


def games_view(launchable: bool = True) -> discord.ui.LayoutView:
    e = emoji_manager.get
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=NEUTRAL)
    container.add_item(discord.ui.TextDisplay(
        f"## {e('trophy')} {config.BOT_NAME} Games\n"
        "Play chess with friends inside Discord. Open the app, pick **Games** in the side bar, create a room and anyone in the session can join or watch.\n\n"
        "It works in servers, in voice channels and in DMs."
    ))
    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="Open Games", style=discord.ButtonStyle.success, custom_id=LAUNCH_ID, disabled=not launchable))
    container.add_item(row)
    view.add_item(container)
    return view


class MusicActivity(commands.Cog):
    category = "Music"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(launch_view())

    @commands.command(name="musicapp", aliases=["activity", "player", "webplayer"], help="Open the music app that runs inside Discord.")
    async def musicapp(self, ctx: commands.Context):
        if not config.ACTIVITY_MUSIC:
            return await ctx.send(view=error_layout("Not available", "The music app is turned off on this bot."))
        await ctx.send(view=launch_view())

    @commands.command(name="activities", help="Open the apps that run inside Discord.")
    async def activities(self, ctx: commands.Context):
        if not config.ACTIVITY_ENABLED:
            return await ctx.send(view=error_layout("Not available", "The apps are turned off on this bot."))
        e = emoji_manager.get
        names = []
        if config.ACTIVITY_MUSIC:
            names.append(f"{e('music_note')} **Music**: search songs, playlists and a Listening status")
        if config.ACTIVITY_GAMES:
            names.append(f"{e('trophy')} **Games**: " + ", ".join(name.title() for name, on in config.ACTIVITY_GAME_LIST.items() if on))
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(f"## {config.BOT_NAME} Apps\n" + "\n".join(names)))
        row = discord.ui.ActionRow()
        row.add_item(discord.ui.Button(label="Open Apps", style=discord.ButtonStyle.success, custom_id=LAUNCH_ID))
        container.add_item(row)
        view.add_item(container)
        await ctx.send(view=view)

    @commands.command(name="gamesapp", aliases=["chess", "playchess", "gamehub"], help="Open the games app that runs inside Discord.")
    async def gamesapp(self, ctx: commands.Context):
        if not config.ACTIVITY_GAMES:
            return await ctx.send(view=error_layout("Not available", "The games app is turned off on this bot."))
        await ctx.send(view=games_view())

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component:
            return
        if str((interaction.data or {}).get("custom_id", "")) != LAUNCH_ID:
            return
        if not config.ACTIVITY_ENABLED:
            return await interaction.response.send_message("The music app is turned off on this bot.", ephemeral=True)
        try:
            await interaction.response.launch_activity()
        except (AttributeError, discord.HTTPException):
            await interaction.response.send_message("Open the App Launcher in a voice channel, a text channel or a DM and pick the music app.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MusicActivity(bot))
