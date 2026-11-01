import io
import json
import time

import discord
from discord.ext import commands, tasks

import config
from utils import deep_backups as store, emoji_manager, premium_limits, server_templates as engine
from utils.colors import NEUTRAL
from utils.components import ConfirmLayout, error_layout, info_layout, success_layout
from utils.events_bus import LOG_EVENT, bus
from utils.security_access import security_owner

PART_NAMES = {"roles": "roles", "channels": "channels", "settings": "settings", "content": "content", "all": "all"}


def _ago(ts: float) -> str:
    seconds = max(0, int(time.time() - ts))
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return f"{seconds}s ago"


class DeepBackup(commands.Cog):
    category = "Server"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.busy: set[int] = set()
        self.auto.start()

    def cog_unload(self):
        self.auto.cancel()

    def _blocked(self, guild_id: int) -> bool:
        templates = self.bot.get_cog("ServerTemplates")
        return guild_id in self.busy or (templates is not None and guild_id in templates.running)

    async def _take(self, guild: discord.Guild, label: str, created_by, auto: bool) -> str:
        data = await engine.snapshot(guild)
        data["meta"] = {"name": label, "source": guild.name}
        counts = engine.summary_counts(data)
        backup_id = await store.save(guild.id, data, label, created_by, auto, counts)
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="security_backup", actor_id=created_by, detail=f"Deep backup `{backup_id}` created ({label}).")
        return backup_id

    @tasks.loop(minutes=15)
    async def auto(self):
        for guild in list(self.bot.guilds):
            try:
                cfg = await store.get_config(guild.id)
                if not cfg["enabled"] or not await premium_limits.is_premium(guild.id) or self._blocked(guild.id):
                    continue
                hours = max(config.DEEP_BACKUP_MIN_HOURS, int(cfg["hours"]))
                if time.time() - await store.last_auto(guild.id) < hours * 3600:
                    continue
                self.busy.add(guild.id)
                try:
                    await self._take(guild, "automatic", None, True)
                finally:
                    self.busy.discard(guild.id)
            except Exception:
                continue

    @auto.before_loop
    async def _before_auto(self):
        await self.bot.wait_until_ready()

    @commands.group(name="deepbackup", aliases=["dbackup", "fullbackup"], invoke_without_command=True, help="Full server backups with settings and one-command restore (Premium).")
    @commands.guild_only()
    @security_owner()
    async def deepbackup(self, ctx: commands.Context):
        e = emoji_manager.get
        cfg = await store.get_config(ctx.guild.id)
        state = f"on, every {max(config.DEEP_BACKUP_MIN_HOURS, int(cfg['hours']))}h" if cfg["enabled"] else "off"
        body = (
            "Saves roles, channels, permissions **and** Soward's settings, embeds, panels and custom commands. Restoring puts them back without deleting anything extra.\n\n"
            "`deepbackup create [label]` · `deepbackup list` · `deepbackup info <id>` · `deepbackup restore <id> [roles|channels|settings|content|all]`\n"
            "`deepbackup auto <on|off> [hours]` · `deepbackup export <id>` · `deepbackup delete <id>`\n\n"
            f"**Automatic:** {state} (newest {config.DEEP_BACKUP_KEEP} kept)\n"
            "Members, messages and bans are not saved. For roles and channels only, the free `backup` command also works."
        )
        await ctx.send(view=info_layout(f"{e('shield')} Deep Backups", body))

    @deepbackup.command(name="create", aliases=["new", "make"], help="Take a full backup now. Usage: deepbackup create [label]")
    @security_owner()
    @commands.cooldown(1, 60, commands.BucketType.guild)
    async def create(self, ctx: commands.Context, *, label: str = "manual"):
        if not await premium_limits.gate(ctx, "Deep backups"):
            return
        if self._blocked(ctx.guild.id):
            return await ctx.send(view=error_layout("Busy", "A backup or template is already running on this server."))
        self.busy.add(ctx.guild.id)
        try:
            async with ctx.typing():
                try:
                    backup_id = await self._take(ctx.guild, label, ctx.author.id, False)
                except ValueError as exc:
                    return await ctx.send(view=error_layout("Too large", str(exc)))
        finally:
            self.busy.discard(ctx.guild.id)
        row = await store.find(ctx.guild.id, backup_id)
        await ctx.send(view=success_layout("Deep backup saved", f"`{backup_id}` · {store.describe_counts(json.loads(row['counts']))}\nRestore it with `deepbackup restore {backup_id}`."))

    @deepbackup.command(name="list", aliases=["all"], help="List deep backups.")
    @security_owner()
    async def list_backups(self, ctx: commands.Context):
        rows = await store.listing(ctx.guild.id)
        if not rows:
            return await ctx.send(view=info_layout("Deep Backups", "No backups yet. Run `deepbackup create`."))
        lines = [f"`{r['backup_id']}` · {r['label'] or 'backup'}{' (auto)' if r['auto'] else ''} · {_ago(r['created_at'])}" for r in rows]
        await ctx.send(view=info_layout("Deep Backups", "\n".join(lines)))

    @deepbackup.command(name="info", help="Show what a backup holds. Usage: deepbackup info <id>")
    @security_owner()
    async def info(self, ctx: commands.Context, backup_id: str):
        row = await store.find(ctx.guild.id, backup_id)
        if row is None:
            return await ctx.send(view=error_layout("Not found", "No deep backup with that id."))
        await ctx.send(view=info_layout(f"Deep backup {row['backup_id']}", f"**Label:** {row['label'] or 'backup'}\n**Taken:** <t:{int(row['created_at'])}:F> ({_ago(row['created_at'])})\n**Holds:** {store.describe_counts(json.loads(row['counts']))}"))

    @deepbackup.command(name="auto", aliases=["schedule"], help="Turn automatic backups on or off. Usage: deepbackup auto <on|off> [hours]")
    @security_owner()
    async def set_auto(self, ctx: commands.Context, mode: str, hours: int = 24):
        mode = mode.lower()
        if mode not in ("on", "off"):
            return await ctx.send(view=error_layout("Invalid", "Use `on` or `off`."))
        if mode == "on":
            if not await premium_limits.gate(ctx, "Automatic deep backups"):
                return
            if not config.DEEP_BACKUP_MIN_HOURS <= hours <= 168:
                return await ctx.send(view=error_layout("Invalid interval", f"Choose from {config.DEEP_BACKUP_MIN_HOURS} to 168 hours."))
            await store.set_config(ctx.guild.id, "hours", hours)
        await store.set_config(ctx.guild.id, "enabled", mode == "on")
        await ctx.send(view=success_layout("Automatic backups", f"Automatic deep backups are **{mode}**" + (f", every {hours}h. The newest {config.DEEP_BACKUP_KEEP} are kept." if mode == "on" else ".")))

    @deepbackup.command(name="export", aliases=["download"], help="Download a backup as JSON. Usage: deepbackup export <id>")
    @security_owner()
    async def export(self, ctx: commands.Context, backup_id: str):
        row = await store.find(ctx.guild.id, backup_id)
        if row is None:
            return await ctx.send(view=error_layout("Not found", "No deep backup with that id."))
        data = json.dumps(store.load(row)).encode()
        await ctx.send(file=discord.File(io.BytesIO(data), filename=f"deepbackup-{row['backup_id']}.json"))

    @deepbackup.command(name="delete", aliases=["remove"], help="Delete a backup. Usage: deepbackup delete <id>")
    @security_owner()
    async def delete(self, ctx: commands.Context, backup_id: str):
        row = await store.find(ctx.guild.id, backup_id)
        if row is None:
            return await ctx.send(view=error_layout("Not found", "No deep backup with that id."))
        await store.delete(row["backup_id"])
        await ctx.send(view=success_layout("Backup deleted", f"`{row['backup_id']}` was removed."))

    @deepbackup.command(name="restore", aliases=["apply"], help="Restore a backup. Usage: deepbackup restore <id> [roles|channels|settings|content|all]")
    @security_owner()
    async def restore(self, ctx: commands.Context, backup_id: str, *parts: str):
        if not await premium_limits.gate(ctx, "Restoring deep backups"):
            return
        chosen = {PART_NAMES.get(p.lower()) for p in parts} if parts else {"all"}
        if None in chosen:
            return await ctx.send(view=error_layout("Unknown part", "Use `roles`, `channels`, `settings`, `content` or `all`."))
        wanted = set(engine.PARTS) if "all" in chosen else chosen
        row = await store.find(ctx.guild.id, backup_id)
        if row is None:
            return await ctx.send(view=error_layout("Not found", "No deep backup with that id."))
        if self._blocked(ctx.guild.id):
            return await ctx.send(view=error_layout("Busy", "A backup or template is already running on this server."))
        try:
            data = engine.validate(store.load(row))
        except (ValueError, json.JSONDecodeError):
            return await ctx.send(view=error_layout("Backup damaged", "This backup could not be read."))
        body = (
            f"Restore `{row['backup_id']}` from {_ago(row['created_at'])} ({store.describe_counts(json.loads(row['counts']))}).\n"
            f"**Parts:** {', '.join(sorted(wanted))}\n\n"
            "Roles and channels that were deleted are created again and ones that still exist are updated to match. Nothing extra is deleted. "
            "A safety backup of the current server is taken first."
        )
        confirm = ConfirmLayout("Restore deep backup", body, author_id=ctx.author.id, color=NEUTRAL, timeout=90.0)
        message = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await message.edit(view=error_layout("Cancelled", "Nothing was changed."))
        self.busy.add(ctx.guild.id)
        try:
            await message.edit(view=info_layout("Restoring", "Taking a safety backup, then restoring. Large servers take a few minutes."))
            try:
                safety = await self._take(ctx.guild, "before restore", ctx.author.id, False)
            except ValueError as exc:
                return await message.edit(view=error_layout("Safety backup failed", f"Nothing was changed: {str(exc)[:150]}"))
            report = engine.Report()
            try:
                await engine.apply(self.bot, ctx.guild, data, actor_id=ctx.author.id, parts=wanted, foreign=False, report=report, refresh=True)
            except engine.Stalled:
                return await message.edit(view=error_layout("Paused by rate limit", f"Discord stopped answering. Run the restore again to continue; existing items are reused. Safety backup: `{safety}`."))
            except Exception as exc:
                return await message.edit(view=error_layout("Restore failed", f"Stopped part-way: {str(exc)[:200]}\nSafety backup: `{safety}`."))
        finally:
            self.busy.discard(ctx.guild.id)
        k = report.counts
        lines = [
            f"Roles created: **{k['roles']}** ({k['roles_reused']} reused, {k['roles_updated']} updated)",
            f"Channels created: **{k['channels']}** ({k['channels_reused']} reused, {k['channels_updated']} updated)",
            f"Settings restored: **{k['settings']}** · embeds **{k['embeds']}** · panels **{k['panels']}** · commands **{k['commands']}**",
            f"Safety backup of the previous state: `{safety}`",
        ]
        if report.failed:
            lines.append("\n**Skipped**\n" + "\n".join(report.failed[:10]))
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_backup", actor_id=ctx.author.id, detail=f"Deep backup `{row['backup_id']}` restored.")
        await message.edit(view=success_layout("Restore finished", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(DeepBackup(bot))
