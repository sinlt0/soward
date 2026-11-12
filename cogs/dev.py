import asyncio
import io
import os
import platform
import sys
import time
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import blacklist, db, dev_state, emoji_manager, prefix as prefix_utils, premium_limits, slash_sync
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import bus


def _setup_jishaku_env():
    os.environ.setdefault("JISHAKU_HIDE", "True")
    os.environ.setdefault("JISHAKU_NO_UNDERSCORE", "False")
    os.environ.setdefault("JISHAKU_NO_DM_TRACEBACK", "False")
    os.environ.setdefault("JISHAKU_RETAIN", "True")


PER_PAGE = 8
NONE = discord.AllowedMentions.none()


def clip(text, size: int) -> str:
    text = str(text)
    return text if len(text) <= size else text[: size - 1] + "…"


class ServerPages(discord.ui.LayoutView):
    def __init__(self, bot: commands.Bot, author_id: int, page: int = 0):
        super().__init__(timeout=180)
        self.bot = bot
        self.author_id = author_id
        self.page = page
        self.premium: dict = {}
        self.banned: set = set()

    def guilds(self) -> list:
        return sorted(self.bot.guilds, key=lambda g: (-(g.member_count or 0), g.id))

    def pages(self) -> int:
        return max(1, -(-len(self.bot.guilds) // PER_PAGE))

    async def render(self):
        self.page = max(0, min(self.page, self.pages() - 1))
        found = self.guilds()
        chunk = found[self.page * PER_PAGE:(self.page + 1) * PER_PAGE]
        flags = await asyncio.gather(*(premium_limits.is_premium(g.id) for g in chunk), return_exceptions=True)
        self.premium = {g.id: flag is True for g, flag in zip(chunk, flags)}
        self.banned = {g.id for g in chunk if await blacklist.is_guild_blacklisted(g.id)}
        self.clear_items()
        members = sum(g.member_count or 0 for g in found)
        container = discord.ui.Container(accent_color=0x00D4FF)
        container.add_item(discord.ui.TextDisplay(f"## Servers\n**{len(found)}** servers · **{members:,}** members · page **{self.page + 1}/{self.pages()}**"))
        if chunk:
            container.add_item(discord.ui.Separator())
            lines = []
            for index, guild in enumerate(chunk, start=self.page * PER_PAGE + 1):
                tag = " · Premium" if self.premium.get(guild.id) else ""
                banned = " · banned" if guild.id in self.banned else ""
                lines.append(f"**{index}. {clip(guild.name, 60)}**{tag}{banned}\nID `{guild.id}` · {guild.member_count or 0:,} members · owner `{guild.owner_id}`")
            container.add_item(discord.ui.TextDisplay("\n\n".join(lines)))
        else:
            container.add_item(discord.ui.TextDisplay("The bot is not in any servers."))
        row = discord.ui.ActionRow()
        last = self.pages() - 1
        for label, target, disabled in (("First", 0, self.page == 0), ("Previous", self.page - 1, self.page == 0), ("Next", self.page + 1, self.page >= last), ("Last", last, self.page >= last)):
            button = discord.ui.Button(label=label, style=discord.ButtonStyle.secondary if label in ("First", "Last") else discord.ButtonStyle.primary, disabled=disabled)
            button.callback = self.move(target)
            row.add_item(button)
        container.add_item(discord.ui.Separator())
        container.add_item(row)
        self.add_item(container)

    def move(self, target: int):
        async def callback(interaction: discord.Interaction):
            self.page = target
            await self.render()
            await interaction.response.edit_message(view=self)
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Only the person who ran this command can use these buttons.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        for item in self.walk_children():
            if isinstance(item, discord.ui.Button):
                item.disabled = True


class Dev(commands.Cog):
    category = "Dev"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_check(self, ctx: commands.Context) -> bool:
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="devguilds", aliases=["serverlist", "servers"], help="List every server the bot is in, paged. Usage: devguilds [page]")
    async def devguilds(self, ctx: commands.Context, page: int = 1):
        view = ServerPages(self.bot, ctx.author.id, max(0, page - 1))
        await view.render()
        await ctx.send(view=view, allowed_mentions=NONE)

    @commands.command(name="serverinvite", aliases=["devserverinvite"], help="Create an invite to a server the bot is in. Usage: serverinvite <server id> [hours] [uses]")
    async def serverinvite(self, ctx: commands.Context, guild_id: int, hours: float = 1, uses: int = 1):
        e = emoji_manager.get
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return await ctx.send(view=error_layout("Not Found", "The bot is not in that server."))
        if not 0 <= hours <= 168 or not 0 <= uses <= 100:
            return await ctx.send(view=error_layout("Invalid Options", "Hours can be 0 to 168 (0 never expires) and uses 0 to 100 (0 unlimited)."))
        me = guild.me
        candidates = [guild.system_channel, guild.rules_channel, guild.public_updates_channel] + list(guild.text_channels) + list(guild.voice_channels)
        for channel in candidates:
            if channel is None or me is None or not channel.permissions_for(me).create_instant_invite:
                continue
            try:
                invite = await channel.create_invite(max_age=int(hours * 3600), max_uses=uses, unique=True, reason=f"Requested by {ctx.author} ({ctx.author.id})")
            except discord.HTTPException:
                continue
            ends = "never expires" if not hours else f"expires in {hours:g} hour(s)"
            use_text = "unlimited uses" if not uses else f"{uses} use(s)"
            return await ctx.send(view=success_layout(f"{e('check')} Invite Created", f"**{clip(guild.name, 60)}**\n{invite.url}\n-# {ends}, {use_text}"), allowed_mentions=NONE)
        await ctx.send(view=error_layout("No Invite", "I need the Create Invite permission in at least one channel there."))

    @commands.command(name="serverban", aliases=["devserverban"], help="Ban a server from the bot and leave it. Usage: serverban <server id> [reason]")
    async def serverban(self, ctx: commands.Context, guild_id: int, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        guild = self.bot.get_guild(guild_id)
        label = f"{guild.name}: {reason}" if guild else reason
        await blacklist.add(guild_id, "guild", label[:200], ctx.author.id)
        left = ""
        if guild:
            try:
                await guild.leave()
                left = " The bot left the server."
            except discord.HTTPException:
                left = " I could not leave it, so commands are blocked there instead."
        await ctx.send(view=success_layout(f"{e('check')} Server Banned", f"Server `{guild_id}` is banned. The bot leaves if it is added again.{left}"))

    @commands.command(name="serverunban", aliases=["devserverunban"], help="Lift a server ban. Usage: serverunban <server id>")
    async def serverunban(self, ctx: commands.Context, guild_id: int):
        e = emoji_manager.get
        if await blacklist.remove(guild_id, "guild"):
            return await ctx.send(view=success_layout(f"{e('check')} Server Unbanned", f"Server `{guild_id}` can use the bot again."))
        await ctx.send(view=error_layout("Not Found", "That server is not banned."))

    @commands.command(name="botban", aliases=["devbotban"], help="Stop a user from using the bot. Usage: botban <user> [reason]")
    async def botban(self, ctx: commands.Context, user: discord.User, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        if user.id in config.ALL_PRIVILEGED_IDS or await self.bot.is_owner(user):
            return await ctx.send(view=error_layout("Blocked", "Owners and developers cannot be banned."))
        await blacklist.add(user.id, "user", reason[:200], ctx.author.id)
        await ctx.send(view=success_layout(f"{e('check')} User Banned", f"{user.mention} can no longer use the bot."), allowed_mentions=NONE)

    @commands.command(name="botunban", aliases=["devbotunban"], help="Let a banned user use the bot again. Usage: botunban <user>")
    async def botunban(self, ctx: commands.Context, user: discord.User):
        e = emoji_manager.get
        if await blacklist.remove(user.id, "user"):
            return await ctx.send(view=success_layout(f"{e('check')} User Unbanned", f"{user.mention} can use the bot again."), allowed_mentions=NONE)
        await ctx.send(view=error_layout("Not Found", "That user is not banned."), allowed_mentions=NONE)

    @commands.command(name="maintenance", aliases=["devmaintenance", "maint"], help="Pause the whole bot for everyone except owners and developers. Usage: maintenance [on|off] [reason]")
    async def maintenance(self, ctx: commands.Context, mode: Optional[str] = None, *, reason: str = ""):
        e = emoji_manager.get
        state = dev_state.maintenance
        if mode is None:
            if not state["on"]:
                return await ctx.send(view=info_layout(f"{e('info')} Maintenance", "Maintenance is **off**."))
            extra = f"\n**Reason:** {state['reason']}" if state["reason"] else ""
            return await ctx.send(view=info_layout(f"{e('info')} Maintenance", f"Maintenance is **on** since <t:{int(state['since'])}:R>.{extra}"))
        mode = mode.lower()
        if mode not in ("on", "off"):
            return await ctx.send(view=error_layout("Invalid Mode", "Use `maintenance on [reason]` or `maintenance off`."))
        await dev_state.set_maintenance(mode == "on", reason[:200])
        if mode == "on":
            return await ctx.send(view=success_layout(f"{e('check')} Maintenance On", "Commands and slash commands are paused for everyone except owners and developers."))
        await ctx.send(view=success_layout(f"{e('check')} Maintenance Off", "The bot is back to normal."))

    @commands.command(name="devserverinfo", aliases=["botserverinfo"], help="Show details about a server the bot is in. Usage: devserverinfo <server id>")
    async def serverinfo(self, ctx: commands.Context, guild_id: int):
        e = emoji_manager.get
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            return await ctx.send(view=error_layout("Not Found", "The bot is not in that server."))
        bots = sum(1 for m in guild.members if m.bot)
        premium = await premium_limits.is_premium(guild.id)
        banned = await blacklist.is_guild_blacklisted(guild.id)
        open_tickets = await db.raw_fetchone("SELECT COUNT(*) AS n FROM tickets WHERE guild_id=? AND status='open'", (guild.id,))
        lines = [
            f"**ID:** `{guild.id}`",
            f"**Owner:** <@{guild.owner_id}> (`{guild.owner_id}`)",
            f"**Members:** {guild.member_count or 0:,} ({bots} bots)",
            f"**Channels:** {len(guild.channels)} · **Roles:** {len(guild.roles)}",
            f"**Created:** <t:{int(guild.created_at.timestamp())}:D>",
            "**Joined:** " + (f"<t:{int(guild.me.joined_at.timestamp())}:R>" if guild.me and guild.me.joined_at else "unknown"),
            f"**Premium:** {'yes' if premium else 'no'} · **Banned:** {'yes' if banned else 'no'}",
            f"**Open tickets:** {int(open_tickets['n']) if open_tickets else 0}",
        ]
        await ctx.send(view=info_layout(f"{e('guild')} {clip(guild.name, 80)}", "\n".join(lines)), allowed_mentions=NONE)

    @commands.command(name="devuserinfo", aliases=["botuserinfo"], help="Show what the bot knows about a user. Usage: devuserinfo <user>")
    async def userinfo(self, ctx: commands.Context, user: discord.User):
        e = emoji_manager.get
        shared = [g for g in self.bot.guilds if g.get_member(user.id)]
        banned = await blacklist.is_user_blacklisted(user.id)
        reason = await db.raw_fetchone("SELECT reason FROM blacklist WHERE target_id=? AND target_type='user'", (user.id,))
        lines = [
            f"**ID:** `{user.id}`",
            f"**Created:** <t:{int(user.created_at.timestamp())}:D>",
            f"**Bot:** {'yes' if user.bot else 'no'}",
            f"**Owner or developer:** {'yes' if user.id in config.ALL_PRIVILEGED_IDS else 'no'}",
            f"**Global no-prefix:** {'yes' if await prefix_utils.is_global_no_prefix(user.id) else 'no'}",
            "**Banned from the bot:** " + (f"yes ({clip(reason['reason'], 80)})" if banned and reason and reason["reason"] else "yes" if banned else "no"),
            f"**Shared servers:** {len(shared)}",
        ]
        if shared:
            lines.append("\n".join(f"- {clip(g.name, 40)} `{g.id}`" for g in shared[:10]))
        await ctx.send(view=info_layout(f"{e('info')} {clip(str(user), 80)}", "\n".join(lines)), allowed_mentions=NONE)

    @commands.command(name="devstats", aliases=["stats"], help="Uptime, latency, server and member counts, memory and bans.")
    async def devstats(self, ctx: commands.Context):
        e = emoji_manager.get
        seconds = int(time.time() - getattr(self.bot, "start_time", time.time()))
        days, rest = divmod(seconds, 86400)
        hours, rest = divmod(rest, 3600)
        minutes = rest // 60
        members = sum(g.member_count or 0 for g in self.bot.guilds)
        flags = await asyncio.gather(*(premium_limits.is_premium(g.id) for g in self.bot.guilds), return_exceptions=True)
        paid = sum(1 for flag in flags if flag is True)
        users = await db.raw_fetchone("SELECT COUNT(*) AS n FROM blacklist WHERE target_type='user'")
        servers = await db.raw_fetchone("SELECT COUNT(*) AS n FROM blacklist WHERE target_type='guild'")
        memory = ""
        try:
            import resource
            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            memory = f"\n**Memory (peak):** {peak / (1048576 if sys.platform == 'darwin' else 1024):.0f} MB"
        except ImportError:
            pass
        lines = [
            f"**Uptime:** {days}d {hours}h {minutes}m",
            f"**Latency:** {self.bot.latency * 1000:.0f} ms",
            f"**Servers:** {len(self.bot.guilds)} ({paid} Premium)",
            f"**Members:** {members:,}",
            f"**Banned:** {int(users['n']) if users else 0} users, {int(servers['n']) if servers else 0} servers",
            f"**Maintenance:** {'on' if dev_state.maintenance['on'] else 'off'}",
            f"**Python:** {platform.python_version()} · **discord.py:** {discord.__version__}{memory}",
        ]
        await ctx.send(view=info_layout(f"{e('info')} Bot Stats", "\n".join(lines)))

    @commands.command(name="devreload", aliases=["reload"], help="Reload one cog or all of them. Usage: devreload <name|all>")
    async def devreload(self, ctx: commands.Context, name: str = "all"):
        e = emoji_manager.get
        loaded = sorted(self.bot.extensions)
        if name.lower() == "all":
            targets = [n for n in loaded if n != "jishaku"]
        else:
            targets = [n for n in loaded if n == name or n.split(".")[-1] == name]
            if not targets:
                return await ctx.send(view=error_layout("Not Found", f"No loaded cog called `{name}`. Loaded: " + ", ".join(f"`{n.split('.')[-1]}`" for n in loaded)[:1500]))
        done, failed = [], []
        for target in targets:
            try:
                await self.bot.reload_extension(target)
                done.append(target.split(".")[-1])
            except Exception as ex:
                failed.append(f"{target.split('.')[-1]}: {clip(ex, 100)}")
        body = f"**Reloaded:** {len(done)}" + (f" ({', '.join(done)})" if len(done) <= 8 else "")
        if failed:
            body += "\n\n**Failed:**\n" + "\n".join(f"`{f}`" for f in failed[:10])
        await ctx.send(view=success_layout(f"{e('check')} Reload Complete", body) if not failed else error_layout("Reload Completed With Errors", body))

    @commands.command(name="slashsync", aliases=["devslashsync"], help="Push the current slash commands to Discord right now.")
    async def slashsync(self, ctx: commands.Context):
        e = emoji_manager.get
        try:
            await slash_sync.sync(self.bot)
            await db.set("slash", "version", slash_sync.digest(self.bot))
        except discord.HTTPException as ex:
            return await ctx.send(view=error_layout("Sync Failed", clip(ex, 300)))
        await ctx.send(view=success_layout(f"{e('check')} Slash Commands Synced", f"{len(self.bot.tree.get_commands())} top-level commands are live."))

    @commands.command(name="devlogs", help="Send the last lines of the bot log as a file. Usage: devlogs [lines]")
    async def devlogs(self, ctx: commands.Context, lines: int = 100):
        lines = max(1, min(lines, 2000))
        try:
            with open("bot.log", "r", encoding="utf-8", errors="replace") as handle:
                tail = handle.readlines()[-lines:]
        except OSError:
            return await ctx.send(view=error_layout("No Logs", "There is no log file yet."))
        text = "".join(tail)
        for secret in (config.BOT_TOKEN,):
            if secret:
                text = text.replace(secret, "[token]")
        await ctx.send(file=discord.File(io.BytesIO(text.encode("utf-8")), filename="bot-log.txt"))

    @commands.command(name="devrestart", aliases=["restart"], help="Restart the bot process.")
    async def devrestart(self, ctx: commands.Context):
        e = emoji_manager.get
        await ctx.send(view=success_layout(f"{e('check')} Restarting", "The bot is restarting now."))
        await asyncio.sleep(1)
        try:
            await self.bot.close()
        except Exception:
            pass
        import logging
        logging.shutdown()
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except OSError:
            os._exit(1)

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
            body += f"\n\n-# Missing: set `ZYRO_DEV_LOG_*_WEBHOOK` / `ZYRO_DEV_STATS_WEBHOOK` in your `.env` for: {', '.join(missing)}"
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
            return await ctx.send(view=error_layout("Not Configured", "ZYRO_DEV_STATS_WEBHOOK is not set."))

        updater = getattr(self.bot, "_dev_stats_updater", None)
        if not updater:
            return await ctx.send(view=error_layout("Not Ready", "The stats updater hasn't initialized yet — try again shortly after startup."))

        ok, detail = await updater.update()
        if not ok:
            return await ctx.send(view=error_layout("Stats Update Failed", detail[:1500]))
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
