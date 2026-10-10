import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

import discord
from discord.ext import commands

import config
from utils import blacklist, db, emoji_manager, loader, prefix as prefix_utils
import secrets

from utils import dashboard_proc, ipc_server

BASE_DIR = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("soward.main")

from utils import console_capture
console_capture.install()

def _print_banner():
    banner = f"""
╔══════════════════════════════════════════════╗
║                                                ║
║   {config.BOT_NAME} — v{config.BOT_VERSION}                            
║   Prefix-only Discord bot                     ║
║   Loader-based architecture                   ║
║                                                ║
╚══════════════════════════════════════════════╝
"""
    print(banner)

class SowardBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(
            command_prefix=prefix_utils.get_prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            allowed_mentions=discord.AllowedMentions(everyone=False, users=False, roles=False, replied_user=True),
        )

    async def setup_hook(self) -> None:
        log.info("Running setup_hook: initializing database layer...")
        try:
            await db.init(self.loop)
        except Exception:
            log.error("Database initialization failed — continuing on SQLite only.", exc_info=True)

        log.info("Loading EmojiManager...")
        try:
            emoji_manager.load_all(BASE_DIR / "emoji")
        except Exception:
            log.error("EmojiManager failed to load one or more files — emoji lookups may return blank.", exc_info=True)

        log.info("Preloading utils package...")
        loader.preload_utils(BASE_DIR / "utils")
        
        
        log.info("Loading event listener modules...")
        events_loaded, events_failed = loader.load_events(self, BASE_DIR / "events")

        log.info("Loading cogs...")
        cogs_loaded, cogs_failed = await loader.load_cogs(self, BASE_DIR / "cogs")

        log.info(
            "Setup complete. %d cog(s) active, %d command(s) registered. %d cog(s) and %d event module(s) failed to load.",
            len(self.cogs),
            len(set(self.walk_commands())),
            len(cogs_failed),
            len(events_failed),
        )
        if cogs_failed or events_failed:
            log.warning(
                "Bot is starting in a DEGRADED state — some features are unavailable. "
                "Check the errors above and fix the listed files; everything else will keep running normally."
            )

    async def close(self) -> None:
        log.info("Bot is closing — flushing final SQLite backup to MongoDB...")
        try:
            from utils import loggers
            await loggers.log_shutdown(self)
        except Exception:
            log.error("Failed to send shutdown log.", exc_info=True)
        try:
            await db.close()
        except Exception:
            log.error("Error during final database backup.", exc_info=True)
        try:
            from utils import loggers
            await loggers.close()
        except Exception:
            pass
        await super().close()


    async def on_error(self, event_method: str, *args, **kwargs):
        log.error("Unhandled exception in event listener '%s'", event_method, exc_info=True)

    async def is_owner(self, user: discord.User) -> bool:
        if user.id in config.ALL_PRIVILEGED_IDS:
            return True
        return await super().is_owner(user)

    async def on_ready(self):
        log.info("=" * 50)
        log.info("%s is online as %s (%d)", config.BOT_NAME, self.user, self.user.id)
        log.info("Connected to %d guild(s).", len(self.guilds))
        log.info("MongoDB primary available: %s", db.is_mongo_available())
        log.info("=" * 50)

        from utils import loggers
        webhook_status = {
            "commands": bool(config.DEV_LOG_COMMANDS_WEBHOOK_URL),
            "lifecycle": bool(config.DEV_LOG_LIFECYCLE_WEBHOOK_URL),
            "errors": bool(config.DEV_LOG_ERRORS_WEBHOOK_URL),
            "guilds": bool(config.DEV_LOG_GUILDS_WEBHOOK_URL),
            "stats": bool(config.DEV_STATS_WEBHOOK_URL),
        }
        configured = [k for k, v in webhook_status.items() if v]
        missing = [k for k, v in webhook_status.items() if not v]
        if configured:
            log.info("Dev logging webhooks configured: %s", ", ".join(configured))
        if missing:
            log.warning(
                "Dev logging webhooks NOT configured (will silently skip): %s — "
                "set these in your .env if you want them.", ", ".join(missing)
            )

        await loggers.log_ready(self)

        if not hasattr(self, "_dev_stats_updater"):
            self._dev_stats_updater = loggers.DevStatsUpdater(self)
            self._dev_stats_task = self.loop.create_task(self._dev_stats_loop())

    async def _dev_stats_loop(self):
        from utils import loggers
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                await self._dev_stats_updater.update()
            except Exception:
                log.error("DevStatsUpdater loop iteration failed.", exc_info=True)
            await asyncio.sleep(config.DEV_STATS_UPDATE_INTERVAL)

    async def on_command(self, ctx: commands.Context):
        from utils import loggers
        await loggers.log_command(ctx)

    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if await blacklist.is_user_blacklisted(message.author.id):
            return
        if message.guild and await blacklist.is_guild_blacklisted(message.guild.id):
            return
        await self.process_commands(message)

    async def on_guild_join(self, guild: discord.Guild):
        if await blacklist.is_guild_blacklisted(guild.id):
            log.warning("Auto-leaving blacklisted guild %s (%d)", guild.name, guild.id)
            await guild.leave()

async def main():
    _print_banner()

    if not config.BOT_TOKEN:
        log.critical("SOWARD_TOKEN environment variable is not set. Cannot start.")
        sys.exit(1)

    bot = SowardBot()

    async with bot:
        secret = secrets.token_urlsafe(32)
        ipc_runner = None
        dashboard = None
        if config.DASHBOARD_ADDON_ENABLED:
            try:
                ipc_runner = await ipc_server.start_ipc(bot, secret)
                dashboard = dashboard_proc.DashboardProcess(
                    secret, config.DASHBOARD_PORT, ipc_server.socket_path(), ipc_server.uses_unix_socket(),
                    int(os.getenv("SOWARD_IPC_PORT", config.DASHBOARD_IPC_FALLBACK_PORT)),
                )
                await dashboard.start()
            except OSError as ex:
                log.warning("Could not start the dashboard: %s", ex)
        else:
            log.info("Dashboard addon is disabled in addons.py.")

        try:
            await bot.start(config.BOT_TOKEN)
        except discord.LoginFailure:
            log.critical("Login failed — the bot token is invalid or has been reset. Cannot start.")
            sys.exit(1)
        finally:
            if dashboard is not None:
                await dashboard.stop()
            if ipc_runner is not None:
                await ipc_runner.cleanup()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Shutdown requested via KeyboardInterrupt.")
    except SystemExit:
        raise
    except Exception:
        log.critical("Unhandled exception escaped main() — bot is shutting down.", exc_info=True)
