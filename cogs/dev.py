import os
import time

import discord
from discord.ext import commands

import config
from utils import blacklist, db, emoji_manager
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import bus


def _setup_jishaku_env():
    os.environ.setdefault("JISHAKU_HIDE", "True")
    os.environ.setdefault("JISHAKU_NO_UNDERSCORE", "False")
    os.environ.setdefault("JISHAKU_NO_DM_TRACEBACK", "False")
    os.environ.setdefault("JISHAKU_RETAIN", "True")


class Dev(commands.Cog):
    category = "Dev"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="devguilds", help="List every guild the bot is in with member counts.")
    async def devguilds(self, ctx: commands.Context):
        e = emoji_manager.get
        lines = [
            f"**{g.name}** — `{g.id}`\n-# {g.member_count:,} members · owner <@{g.owner_id}>"
            for g in sorted(self.bot.guilds, key=lambda g: g.member_count or 0, reverse=True)[:20]
        ]
        body = "\n\n".join(lines) or "Not in any guilds."
        if len(self.bot.guilds) > 20:
            body += f"\n\n...and {len(self.bot.guilds) - 20} more"
        await ctx.send(view=info_layout(f"{e('guild')} Guilds ({len(self.bot.guilds)})", body))

    @commands.command(name="devstatus", help="Show internal bot diagnostics — DB mode, event bus, cache sizes.")
    async def devstatus(self, ctx: commands.Context):
        e = emoji_manager.get
        db_mode = "MongoDB (row-level mirror) + SQLite (primary write target)" if db.is_mongo_available() else "SQLite only (MongoDB unavailable)"
        subscriber_counts = {topic: len(handlers) for topic, handlers in bus._listeners.items()} if hasattr(bus, "_listeners") else {}
        bus_lines = "\n".join(f"`{topic}`: {count}" for topic, count in subscriber_counts.items()) or "No introspectable subscribers."

        backup_info = await db.get_last_backup_info()
        if backup_info and backup_info.get("saved_at"):
            backup_line = f"<t:{int(backup_info['saved_at'])}:R> ({backup_info.get('size_bytes', 0):,} mirrored doc(s))"
        else:
            backup_line = "No sync on record."

        body = (
            f"**Database:** {db_mode}\n"
            f"**Last MongoDB sync:** {backup_line}\n"
            f"**Guilds:** `{len(self.bot.guilds)}`\n"
            f"**Cogs loaded:** `{len(self.bot.cogs)}`\n"
            f"**Commands registered:** `{len(set(self.bot.walk_commands()))}`\n"
            f"**Gateway latency:** `{round(self.bot.latency * 1000)}ms`\n\n"
            f"**Event bus subscribers:**\n{bus_lines}"
        )
        await ctx.send(view=info_layout(f"{e('settings')} Dev Status", body))

    @commands.command(name="devcogs", help="List all loaded cogs and their command counts.")
    async def devcogs(self, ctx: commands.Context):
        e = emoji_manager.get
        lines = []
        for name, cog in sorted(self.bot.cogs.items()):
            cmd_count = len(cog.get_commands())
            lines.append(f"**{name}** — `{cmd_count}` command(s)")
        await ctx.send(view=info_layout(f"{e('settings')} Loaded Cogs ({len(self.bot.cogs)})", "\n".join(lines)))

    @commands.command(name="devemit", help="Manually publish an event to the internal event bus for testing. Usage: devemit <topic> guild_id=123 key=value...")
    async def devemit(self, ctx: commands.Context, topic: str, *, kwargs_str: str = ""):
        e = emoji_manager.get
        kwargs = {}
        for pair in kwargs_str.split():
            if "=" not in pair:
                continue
            key, _, value = pair.partition("=")
            if value.isdigit():
                value = int(value)
            kwargs[key] = value

        if "guild_id" not in kwargs and ctx.guild:
            kwargs["guild_id"] = ctx.guild.id

        start = time.perf_counter()
        await bus.publish(topic, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000

        await ctx.send(view=success_layout(
            f"{e('check')} Event Published",
            f"**Topic:** `{topic}`\n**Kwargs:** `{kwargs}`\n**Handler time:** `{elapsed:.1f}ms`",
        ))

    @commands.command(name="devsql", help="Run a raw read-only SQL query against the SQLite database. SELECT only.")
    async def devsql(self, ctx: commands.Context, *, query: str):
        e = emoji_manager.get
        query = query.strip().strip("`")
        if not query.lower().startswith("select"):
            return await ctx.send(view=error_layout("Blocked", "Only `SELECT` queries are allowed through this command."))

        try:
            rows = await db.raw_fetch(query)
        except Exception as ex:
            return await ctx.send(view=error_layout("Query Failed", f"```\n{ex}\n```"))

        if not rows:
            return await ctx.send(view=info_layout(f"{e('info')} Query Result", "No rows returned."))

        preview = rows[:10]
        lines = [dict(r) for r in preview]
        body = "\n".join(f"`{line}`" for line in lines)
        if len(rows) > 10:
            body += f"\n\n...and {len(rows) - 10} more row(s)"
        await ctx.send(view=info_layout(f"{e('info')} Query Result ({len(rows)} row(s))", body[:3800]))


    @commands.command(name="devblacklist", aliases=["devbl"], help="Blacklist a user or guild from using the bot. Usage: devblacklist <user|guild> <id> [reason]")
    async def devblacklist(self, ctx: commands.Context, target_type: str, target_id: int, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        target_type = target_type.lower()
        if target_type not in ("user", "guild"):
            return await ctx.send(view=error_layout("Invalid Type", "Use `user` or `guild` as the target type."))

        if target_type == "user" and target_id in config.ALL_PRIVILEGED_IDS:
            return await ctx.send(view=error_layout("Blocked", "Cannot blacklist a bot owner or developer."))

        await blacklist.add(target_id, target_type, reason, ctx.author.id)
        await ctx.send(view=success_layout(
            f"{e('check')} Blacklisted",
            f"**Type:** `{target_type}`\n**ID:** `{target_id}`\n**Reason:** {reason}",
        ))

        if target_type == "guild":
            guild = self.bot.get_guild(target_id)
            if guild:
                await guild.leave()

    @commands.command(name="devunblacklist", aliases=["devunbl"], help="Remove a user or guild from the blacklist. Usage: devunblacklist <user|guild> <id>")
    async def devunblacklist(self, ctx: commands.Context, target_type: str, target_id: int):
        e = emoji_manager.get
        target_type = target_type.lower()
        if target_type not in ("user", "guild"):
            return await ctx.send(view=error_layout("Invalid Type", "Use `user` or `guild` as the target type."))

        removed = await blacklist.remove(target_id, target_type)
        if removed:
            await ctx.send(view=success_layout(f"{e('check')} Unblacklisted", f"`{target_type}` `{target_id}` removed from the blacklist."))
        else:
            await ctx.send(view=error_layout("Not Found", f"`{target_type}` `{target_id}` is not blacklisted."))

    @commands.command(name="devblacklisted", help="List all currently blacklisted users and guilds.")
    async def devblacklisted(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await db.raw_fetch("SELECT * FROM blacklist ORDER BY created_at DESC")
        if not rows:
            return await ctx.send(view=info_layout(f"{e('info')} Blacklist", "No users or guilds are currently blacklisted."))

        lines = [
            f"`{r['target_type']}` `{r['target_id']}` — {r['reason'] or 'No reason'}\n-# by <@{r['blacklisted_by']}> · <t:{int(r['created_at'])}:R>"
            for r in rows[:15]
        ]
        body = "\n\n".join(lines)
        if len(rows) > 15:
            body += f"\n\n...and {len(rows) - 15} more"
        await ctx.send(view=info_layout(f"{e('info')} Blacklist ({len(rows)})", body))

    @commands.command(name="devleaveguild", help="Force the bot to leave a guild by ID.")
    async def devleaveguild(self, ctx: commands.Context, guild_id: int):
        e = emoji_manager.get
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await ctx.send(view=error_layout("Not Found", f"Not currently in a guild with ID `{guild_id}`."))
        name = guild.name
        await guild.leave()
        await ctx.send(view=success_layout(f"{e('check')} Left Guild", f"Left **{name}** (`{guild_id}`)."))

    @commands.command(name="devconfig", help="Dump non-sensitive runtime config values.")
    async def devconfig(self, ctx: commands.Context):
        e = emoji_manager.get
        body = (
            f"**Bot name:** `{config.BOT_NAME}`\n"
            f"**Version:** `{config.BOT_VERSION}`\n"
            f"**Owner IDs:** {', '.join(f'`{i}`' for i in config.OWNER_IDS)}\n"
            f"**Dev IDs:** {', '.join(f'`{i}`' for i in config.DEV_IDS)}\n"
            f"**Lavalink nodes:** `{len(config.LAVALINK_NODES)}` configured\n"
            f"**Log categories:** {', '.join(f'`{c}`' for c in config.LOG_CATEGORIES)}\n"
            f"**Hidden help categories:** {', '.join(f'`{c}`' for c in config.HELP_HIDDEN_CATEGORIES)}"
        )
        await ctx.send(view=info_layout(f"{e('settings')} Runtime Config", body))

    @commands.command(name="devwebhooks", help="Check which dev logging webhooks are configured (does not reveal URLs).")
    async def devwebhooks(self, ctx: commands.Context):
        e = emoji_manager.get
        checks = {
            "Commands": config.DEV_LOG_COMMANDS_WEBHOOK_URL,
            "Lifecycle": config.DEV_LOG_LIFECYCLE_WEBHOOK_URL,
            "Errors": config.DEV_LOG_ERRORS_WEBHOOK_URL,
            "Guilds": config.DEV_LOG_GUILDS_WEBHOOK_URL,
            "Stats": config.DEV_STATS_WEBHOOK_URL,
        }
        lines = [f"{'✅' if url else '❌'} **{name}**" for name, url in checks.items()]
        missing = [name for name, url in checks.items() if not url]
        body = "\n".join(lines)
        if missing:
            body += f"\n\n-# Missing: set `SOWARD_DEV_LOG_*_WEBHOOK` / `SOWARD_DEV_STATS_WEBHOOK` in your `.env` for: {', '.join(missing)}"
        await ctx.send(view=info_layout(f"{e('settings')} Dev Logging Webhooks", body))

    @commands.command(name="devtables", help="List all SQLite tables with row counts.")
    async def devtables(self, ctx: commands.Context):
        e = emoji_manager.get
        tables = await db.raw_fetch("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        lines = []
        for t in tables:
            count_row = await db.raw_fetchone(f"SELECT COUNT(*) as c FROM {t['name']}")
            lines.append(f"`{t['name']}` — {count_row['c']:,} row(s)")
        await ctx.send(view=info_layout(f"{e('info')} Database Tables ({len(tables)})", "\n".join(lines)))

    @commands.command(name="devstatsimage", aliases=["devstatsnow"], help="Force an immediate DB stats image update in the dev server, without waiting for the next 5-minute tick.")
    async def devstatsimage(self, ctx: commands.Context):
        e = emoji_manager.get
        if not config.DEV_STATS_WEBHOOK_URL:
            return await ctx.send(view=error_layout("Not Configured", "SOWARD_DEV_STATS_WEBHOOK is not set."))

        updater = getattr(self.bot, "_dev_stats_updater", None)
        if not updater:
            return await ctx.send(view=error_layout("Not Ready", "The stats updater hasn't initialized yet — try again shortly after startup."))

        await updater.update()
        await ctx.send(view=success_layout(f"{e('check')} Stats Updated", "DB stats image refreshed in the dev server."))

    @commands.command(name="devbackup", aliases=["devsync"], help="Force an immediate SQLite → MongoDB row-level sync.")
    async def devbackup(self, ctx: commands.Context):
        e = emoji_manager.get
        if not db.is_mongo_available():
            return await ctx.send(view=error_layout("MongoDB Unavailable", "Cannot sync — MongoDB is not currently connected."))

        from utils import mongo_sync
        results = await mongo_sync.sync_all_tables()
        upserted = sum(r.get("upserted", 0) for r in results.values())
        deleted = sum(r.get("deleted", 0) for r in results.values())
        failed = [t for t, r in results.items() if not r.get("synced")]

        body = f"**Tables synced:** `{len(results) - len(failed)}/{len(results)}`\n**Rows upserted:** `{upserted}`\n**Rows deleted:** `{deleted}`"
        if failed:
            body += f"\n\n**Failed:** {', '.join(f'`{t}`' for t in failed[:10])}"
        await ctx.send(view=success_layout(f"{e('check')} Sync Complete", body) if not failed else error_layout("Sync Completed With Errors", body))

    @commands.command(name="devreloadall", help="Reload every currently loaded cog at once.")
    async def devreloadall(self, ctx: commands.Context):
        e = emoji_manager.get
        reloaded, failed = [], []
        for ext in list(self.bot.extensions.keys()):
            if ext == "jishaku":
                continue
            try:
                await self.bot.reload_extension(ext)
                reloaded.append(ext)
            except Exception as ex:
                failed.append(f"{ext}: {ex}")

        body = f"**Reloaded:** `{len(reloaded)}`"
        if failed:
            body += "\n\n**Failed:**\n" + "\n".join(f"`{f}`" for f in failed[:10])
        await ctx.send(view=success_layout(f"{e('check')} Reload Complete", body) if not failed else error_layout("Reload Completed With Errors", body))

    @commands.command(name="devperms", help="Show the bot's permissions in the current guild/channel.")
    @commands.guild_only()
    async def devperms(self, ctx: commands.Context):
        e = emoji_manager.get
        guild_perms = ctx.guild.me.guild_permissions
        channel_perms = ctx.channel.permissions_for(ctx.guild.me)

        dangerous_or_key = [
            "administrator", "manage_guild", "manage_roles", "manage_channels", "manage_webhooks",
            "ban_members", "kick_members", "moderate_members", "manage_messages", "view_audit_log",
            "mention_everyone", "manage_nicknames",
        ]
        lines = [f"`{p.replace('_', ' ').title()}`: {'✅' if getattr(guild_perms, p, False) else '❌'}" for p in dangerous_or_key]
        body = "\n".join(lines) + f"\n\n**This channel — Send Messages:** {'✅' if channel_perms.send_messages else '❌'}"
        await ctx.send(view=info_layout(f"{e('settings')} Bot Permissions", body))

    @commands.command(name="devinvite", help="Get an invite link with the bot's required permissions.")
    async def devinvite(self, ctx: commands.Context):
        e = emoji_manager.get
        perms = discord.Permissions(
            administrator=True,
        )
        url = discord.utils.oauth_url(self.bot.user.id, permissions=perms, scopes=("bot", "applications.commands"))
        await ctx.send(view=info_layout(f"{e('info')} Invite Link", f"[Click here to invite {config.BOT_NAME}]({url})"))

    @commands.command(name="devshutdown", aliases=["devkill"], help="Gracefully shut down the bot process.")
    async def devshutdown(self, ctx: commands.Context):
        e = emoji_manager.get
        await ctx.send(view=success_layout(f"{e('check')} Shutting Down", "The bot is shutting down now."))
        await self.bot.close()

    @commands.command(name="devsend", help="Force-send a message to any channel by ID. Usage: devsend <channel_id> <message>")
    async def devsend(self, ctx: commands.Context, channel_id: int, *, content: str):
        e = emoji_manager.get
        channel = self.bot.get_channel(channel_id)
        if not channel:
            return await ctx.send(view=error_layout("Not Found", f"No accessible channel with ID `{channel_id}`."))
        try:
            await channel.send(content)
        except discord.HTTPException as ex:
            return await ctx.send(view=error_layout("Send Failed", str(ex)))
        await ctx.send(view=success_layout(f"{e('check')} Sent", f"Message sent to {channel.mention} in **{channel.guild.name}**."))


async def setup(bot: commands.Bot):
    _setup_jishaku_env()
    try:
        import jishaku  # noqa: F401
    except ImportError:
        raise RuntimeError(
            "jishaku is not installed. Run: pip install jishaku --break-system-packages"
        )

    if "jishaku" not in bot.extensions:
        await bot.load_extension("jishaku")

    await bot.add_cog(Dev(bot))
