import logging

from discord.ext import commands

import config
from utils import emoji_manager, ipc_server
from utils.checks import has_guild_permission, is_owner
from utils.components import info_layout, success_layout

log = logging.getLogger("soward.dashboard")


def _link() -> str:
    return config.DASHBOARD_URL or "Set `SOWARD_DASHBOARD_URL` to show the link."


class Dashboard(commands.Cog):
    category = "Config"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="dashboard", aliases=["dash", "web"], invoke_without_command=True, help="Open the web dashboard and see whether it is on.")
    @commands.guild_only()
    async def dashboard(self, ctx: commands.Context):
        e = emoji_manager.get
        global_on = await ipc_server.global_enabled()
        server_on = await ipc_server.guild_enabled(ctx.guild.id)
        if not config.DASHBOARD_ADDON_ENABLED:
            state = "Disabled in addons.py (the web server is not running)"
        elif not global_on:
            state = "Off for every server (bot owner setting)"
        else:
            state = "On for this server" if server_on else "Off for this server"
        body = (
            f"**Status:** {state}\n"
            f"**Link:** {_link()}\n\n"
            "Sign in with Discord. You need Manage Server to change settings.\n"
            "-# `dashboard on` and `dashboard off` switch access for this server."
        )
        await ctx.send(view=info_layout(f"{e('settings')} Web Dashboard", body))

    @dashboard.command(name="on", aliases=["enable"], help="Allow the web dashboard to manage this server.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def dashboard_on(self, ctx: commands.Context):
        e = emoji_manager.get
        await ipc_server.set_guild_enabled(ctx.guild.id, True)
        await ipc_server.record_audit(ctx.guild.id, ctx.author.id, str(ctx.author), "server", "Dashboard access: on (from Discord)")
        await ctx.send(view=success_layout(f"{e('check')} Dashboard on", f"Members with Manage Server can now sign in at {_link()}"))

    @dashboard.command(name="off", aliases=["disable"], help="Block the web dashboard from managing this server.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def dashboard_off(self, ctx: commands.Context):
        e = emoji_manager.get
        await ipc_server.set_guild_enabled(ctx.guild.id, False)
        await ipc_server.record_audit(ctx.guild.id, ctx.author.id, str(ctx.author), "server", "Dashboard access: off (from Discord)")
        await ctx.send(view=success_layout(f"{e('check')} Dashboard off", "Nobody can change this server from the web dashboard until you run `dashboard on`."))

    @dashboard.group(name="global", invoke_without_command=True, help="Owner only: turn the whole dashboard on or off.")
    @is_owner()
    async def dashboard_global(self, ctx: commands.Context):
        e = emoji_manager.get
        state = "on" if await ipc_server.global_enabled() else "off"
        await ctx.send(view=info_layout(f"{e('settings')} Dashboard (global)", f"The dashboard is **{state}** for every server.\n-# `dashboard global on` or `dashboard global off`"))

    @dashboard_global.command(name="on", help="Owner only: turn the dashboard on for every server.")
    @is_owner()
    async def dashboard_global_on(self, ctx: commands.Context):
        e = emoji_manager.get
        await ipc_server.set_global_enabled(True)
        await ctx.send(view=success_layout(f"{e('check')} Dashboard on", "The dashboard is on for every server."))

    @dashboard_global.command(name="off", help="Owner only: turn the dashboard off for every server.")
    @is_owner()
    async def dashboard_global_off(self, ctx: commands.Context):
        e = emoji_manager.get
        await ipc_server.set_global_enabled(False)
        await ctx.send(view=success_layout(f"{e('check')} Dashboard off", "Server pages are closed for everyone except bot owners. The public site stays up."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Dashboard(bot))
