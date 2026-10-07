import logging

import discord
from discord.ext import commands

from utils import embeds, emoji_manager

log = logging.getLogger("soward.events.errors")

def setup(bot: commands.Bot) -> None:
    @bot.listen("on_command_error")
    async def _handle_command_error(ctx: commands.Context, error: commands.CommandError):
        try:
            await _dispatch_error(ctx, error)
        except Exception:
            log.error("Error handler itself failed while handling '%s'", error, exc_info=True)

    async def _dispatch_error(ctx: commands.Context, error: commands.CommandError):
        e = emoji_manager.get

        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.MissingPermissions):
            missing = ", ".join(f"`{p}`" for p in error.missing_permissions)
            return await ctx.send(embed=embeds.error(f"{e('cross')} Missing Permissions", f"You need {missing} to use this command."))

        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(f"`{p}`" for p in error.missing_permissions)
            return await ctx.send(embed=embeds.error(f"{e('cross')} Missing Permissions", f"I need {missing} to do that."))

        if isinstance(error, commands.CheckFailure):
            return await ctx.send(embed=embeds.error(f"{e('cross')} Permission Denied", str(error) or "You cannot use this command."))

        if isinstance(error, commands.MissingRequiredArgument):
            return await ctx.send(embed=embeds.error(f"{e('cross')} Missing Argument", f"Missing required argument: `{error.param.name}`."))

        if isinstance(error, commands.BadArgument):
            return await ctx.send(embed=embeds.error(f"{e('cross')} Invalid Argument", str(error)))

        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.send(embed=embeds.error(f"{e('cross')} Cooldown", f"Try again in **{error.retry_after:.1f}s**."))

        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.send(embed=embeds.error(f"{e('cross')} Server Only", "This command can only be used in a server."))

        if isinstance(error, commands.MemberNotFound) or isinstance(error, commands.UserNotFound):
            return await ctx.send(embed=embeds.error(f"{e('cross')} Not Found", str(error)))

        log.error("Unhandled command error in '%s': %s", ctx.command, error, exc_info=error)
        from utils import loggers
        await loggers.log_error(ctx.bot, f"Command: {ctx.command.qualified_name if ctx.command else 'unknown'}", error)
        await ctx.send(embed=embeds.error(f"{e('cross')} Unexpected Error", "Something went wrong while running that command."))
