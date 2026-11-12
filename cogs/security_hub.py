import io
import re
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

import config
from utils import db, emoji_manager, guild_settings, postmortem, security, security_autosetup, security_cmds, threat
from utils import security_master
from utils import security_settings as settings
from utils import security_whitelist as whitelist
from utils.checks import has_guild_permission
from utils.components import ConfirmLayout, error_layout, info_layout, success_layout
from utils.converters import DurationConverter, format_duration
from utils.events_bus import LOG_EVENT, bus
from utils.security_access import LEVEL_NAMES, level_of, security_owner, security_staff


class WhitelistTarget:
    def __init__(self, target_id: int, kind: str, mention: str):
        self.id = target_id
        self.type = kind
        self.mention = mention


class WhitelistTargetConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> WhitelistTarget:
        for converter, kind in (
            (commands.MemberConverter, "user"),
            (commands.RoleConverter, "role"),
            (commands.GuildChannelConverter, "channel"),
        ):
            try:
                found = await converter().convert(ctx, argument)
            except commands.BadArgument:
                continue
            return WhitelistTarget(found.id, kind, found.mention)
        if argument.isdigit():
            number = int(argument)
            if ctx.guild.get_role(number):
                return WhitelistTarget(number, "role", f"<@&{number}>")
            if ctx.guild.get_channel(number):
                return WhitelistTarget(number, "channel", f"<#{number}>")
            return WhitelistTarget(number, "user", f"<@{number}>")
        raise commands.BadArgument(f"Could not find a member, role or channel called `{argument}`.")


class RuleTargetConverter(WhitelistTargetConverter):
    async def convert(self, ctx: commands.Context, argument: str) -> WhitelistTarget:
        if argument.lower() in ("server", "guild", "everyone", "all"):
            return WhitelistTarget(ctx.guild.id, "server", "the whole server")
        return await super().convert(ctx, argument)


def _rule_mention(row: dict) -> str:
    if row["target_type"] == "server":
        return "the whole server"
    return _mention(row)


def _scopes(tokens: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for token in tokens:
        for part in token.lower().replace(",", " ").split():
            part = "all" if part in ("everything", "total", "global") else part
            if part not in whitelist.SCOPES:
                raise ValueError(f"`{part}` is not a whitelist scope. Run `whitelist scopes` to see them.")
            if part not in out:
                out.append(part)
    return out or ["all"]


DRY_WORDS = ("preview", "dry", "dryrun", "plan")


def _strip_dry(tokens) -> tuple[list[str], bool]:
    kept = [t for t in tokens if t.lower() not in DRY_WORDS]
    return kept, len(kept) != len(tokens)


def _until(expires: Optional[float]) -> str:
    return f" until <t:{int(expires)}:f>" if expires else ""


def _mention(row: dict) -> str:
    return {"user": f"<@{row['target_id']}>", "role": f"<@&{row['target_id']}>", "channel": f"<#{row['target_id']}>"}[row["target_type"]]


class SecurityHub(commands.Cog):
    category = "Config"
    submodule = "Security"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_report: dict[int, float] = {}
        self.maintenance_loop.start()

    def cog_unload(self):
        self.maintenance_loop.cancel()

    @tasks.loop(seconds=60)
    async def maintenance_loop(self):
        try:
            await postmortem.sweep(self.bot)
            await whitelist.flush_usage()
            for row in await whitelist.purge_expired():
                guild = self.bot.get_guild(row["guild_id"])
                if guild is None:
                    continue
                label = row.get("scope", "")
                await bus.publish(
                    LOG_EVENT, guild_id=guild.id, action="security_whitelist", actor_id=None,
                    detail=f"Whitelist entry expired and was removed: <@{row['target_id']}> `{label}`.",
                )
            await self._weekly_reports()
            await self._master_expiry()
        except Exception:
            pass

    @maintenance_loop.before_loop
    async def _before_maintenance(self):
        await self.bot.wait_until_ready()

    async def _master_expiry(self):
        for guild in list(self.bot.guilds):
            if await security_master.expired(guild.id) is not None:
                await security_master.enable(guild.id)
                await bus.publish(LOG_EVENT, guild_id=guild.id, action="security_change", actor_id=None, detail="Security was switched back on automatically because the pause ended.")
            if await security_master.expired(guild.id, "verification") is not None:
                await security_master.enable(guild.id, "verification")
                await bus.publish(LOG_EVENT, guild_id=guild.id, action="security_change", actor_id=None, detail="Verification was switched back on automatically because the pause ended.")

    async def _weekly_reports(self):
        now = time.time()
        for guild in list(self.bot.guilds):
            last = self._last_report.get(guild.id)
            if last is None:
                last = float(await guild_settings.get(guild.id, "security_whitelist_report_at", 0) or 0)
                self._last_report[guild.id] = last
            if last and now - last < 7 * 86400:
                continue
            self._last_report[guild.id] = now
            await guild_settings.set(guild.id, "security_whitelist_report_at", now)
            if not last:
                continue
            if not await settings.get(guild.id, "security", "whitelist_report"):
                continue
            body = await self._audit_text(guild, only_findings=True)
            if body is None:
                continue
            channel = await postmortem._target_channel(guild)
            if channel is None:
                continue
            try:
                await channel.send(view=info_layout("Weekly whitelist report", body))
            except discord.HTTPException:
                continue

    async def _audit_text(self, guild: discord.Guild, only_findings: bool = False) -> Optional[str]:
        stale_days = int(await settings.get(guild.id, "security", "whitelist_stale_days"))
        report = await whitelist.audit(guild.id, stale_days)
        dead = []
        for table in ("security_whitelist", "security_whitelist_rules"):
            for row in await db.raw_fetch(f"SELECT target_id, target_type, scope FROM {table} WHERE guild_id=?", (guild.id,)):
                kind, tid = row["target_type"], int(row["target_id"])
                missing = (kind == "role" and guild.get_role(tid) is None) or (kind == "channel" and guild.get_channel(tid) is None) or (kind == "user" and guild.get_member(tid) is None)
                if missing:
                    dead.append({"target_id": tid, "target_type": kind, "scope": row["scope"], "table": table})
        if only_findings and not any(report.values()) and not dead:
            return None

        def line(entry: dict) -> str:
            kind = entry["target_type"]
            who = {"user": f"<@{entry['target_id']}>", "role": f"<@&{entry['target_id']}>", "channel": f"<#{entry['target_id']}>"}.get(kind, f"server `{entry['target_id']}`")
            scope = entry["scope"] + (f" `{entry['value']}`" if entry.get("value") else "")
            used = entry.get("last_used")
            when = f"last used <t:{int(used)}:R>" if used else f"never used, added <t:{int(entry.get('added_at') or time.time())}:R>"
            expiry = f" · expires <t:{int(entry['expires_at'])}:R>" if entry.get("expires_at") else ""
            return f"- {who} · `{scope}` · {when}{expiry}"

        sections = [f"Entries count as stale after **{stale_days}** days without use."]
        for key, title in (("unused", "Never used"), ("stale", "Stale"), ("expiring", "Expiring within 7 days")):
            items = report[key]
            if items:
                sections.append(f"\n**{title} ({len(items)})**\n" + "\n".join(line(i) for i in items[:12]) + (f"\n-# and {len(items) - 12} more" if len(items) > 12 else ""))
        if dead:
            sections.append(f"\n**Pointing at something that no longer exists ({len(dead)})**\n" + "\n".join(f"- `{d['target_type']}` `{d['target_id']}` · `{d['scope']}`" for d in dead[:12]))
        if len(sections) == 1:
            sections.append("\nNothing needs attention.")
        sections.append("\n-# Remove entries with `whitelist remove` or `whitelist revoke`, or set an expiry with `whitelist expire`.")
        return "\n".join(sections)[:3800]

    async def _status_line(self, guild: discord.Guild) -> str:
        e = emoji_manager.get
        on, off = "🟢", "🔴"
        lines = []
        paused = await security_master.state(guild.id) if await security_master.is_off(guild.id) else None
        if paused:
            return f"⏸️ **Security is paused** until <t:{int(paused['until'])}:f> (<t:{int(paused['until'])}:R>). Your settings are kept. Use `security enable` to switch it back on now."
        for module, label in (("antinuke", "AntiNuke"), ("antiraid", "AntiRaid"), ("automod", "AutoMod")):
            enabled = await settings.get(guild.id, module, "enabled")
            lines.append(f"{on if enabled else off} **{label}**")
        level = await settings.get(guild.id, "verification", "level")
        name = settings.display(settings.find("verification", "level"), level)
        lines.append(f"{on if level else off} **Verification:** {name}")
        return " · ".join(lines)

    @commands.group(name="security", aliases=["sec"], invoke_without_command=True, help="Overview of every security system, your access level and the active protections.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def security_group(self, ctx: commands.Context):
        e = emoji_manager.get
        guild = ctx.guild
        locked = await settings.get(guild.id, "security", "lock")
        level = await level_of(guild, ctx.author)
        tiers = await security.list_permit_tiers(guild.id)
        extra = sum(1 for t in tiers if t["tier"] == config.SECURITY_TIER_EXTRA_OWNER)
        trusted = sum(1 for t in tiers if t["tier"] == config.SECURITY_TIER_TRUSTED_ADMIN)
        wl = await db.raw_fetchone("SELECT COUNT(*) AS c FROM security_whitelist WHERE guild_id=?", (guild.id,))
        quarantined = await db.raw_fetchone("SELECT COUNT(*) AS c FROM quarantine WHERE guild_id=? AND released_at IS NULL", (guild.id,))
        lockdown = await db.raw_fetchone("SELECT active, expires_at FROM security_lockdown WHERE guild_id=?", (guild.id,))
        score = await threat.score(guild.id)
        threshold = await settings.get(guild.id, "security", "threat_threshold")
        panic = await security.is_panic_mode_active(guild.id)
        body = (
            f"{await self._status_line(guild)}\n\n"
            f"**Your access:** {LEVEL_NAMES[level]}\n"
            f"**Tier lock:** {'on — only the owner, Extra Owners and Trusted Admins can change settings' if locked else 'off — Administrators can change settings'}\n"
            f"**Extra Owners:** {extra}/{config.SECURITY_TIER_MAX_PER_TIER} · **Trusted Admins:** {trusted}/{config.SECURITY_TIER_MAX_PER_TIER}\n"
            f"**Whitelist entries:** {wl['c'] if wl else 0} · **Quarantined:** {quarantined['c'] if quarantined else 0}\n"
            f"**Threat score:** {score:.1f}/{threshold}{' · Beast Mode active' if threat.is_beast(guild.id) else ''}\n"
            f"**Panic mode:** {'active' if panic else 'inactive'} · **Lockdown:** {'active' if lockdown and lockdown['active'] else 'inactive'}\n\n"
            "`security preset` · `security settings` · `whitelist` · `antinuke` · `antiraid` · `automod` · `verification` · `lockdown` · `securitycheck`"
        )
        await ctx.send(view=info_layout(f"{e('shield')} Security center", body))

    @security_group.command(name="disable", aliases=["pause", "off"], help="Pause every security system for a while and keep all settings. Usage: security disable [duration] [reason]. Default 2h, at most 7d.")
    @security_owner()
    async def security_disable(self, ctx: commands.Context, *, details: str = ""):
        e = emoji_manager.get
        seconds = security_master.DEFAULT_SECONDS
        reason = details.strip()
        first = reason.split(" ", 1)[0] if reason else ""
        if first and re.fullmatch(r"(?:\d+[smhdw])+", first.lower()):
            seconds = await DurationConverter().convert(ctx, first)
            reason = reason[len(first):].strip()
        if seconds < 300 or seconds > security_master.MAX_SECONDS:
            return await ctx.send(view=error_layout("Invalid duration", "Use between 5 minutes and 7 days. Security always switches back on by itself when the time is up."))
        if await security_master.is_off(ctx.guild.id):
            return await ctx.send(view=error_layout("Already paused", "Security is already paused. Use `security enable` to switch it back on."))
        confirm = ConfirmLayout(
            f"{e('warn')} Pause all security?",
            f"AntiNuke, AntiRaid, AutoMod, join verification and ban evasion alerts will stop acting for **{format_duration(seconds)}**. "
            "Your settings, whitelist and permit tiers are kept, and members already quarantined stay quarantined. "
            "Security switches back on by itself when the time is up.",
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "Security stays on."))
        current = await security_master.disable(ctx.guild.id, ctx.author.id, reason or "no reason given", seconds)
        ended_raid = False
        raid = self.bot.get_cog("AntiRaid")
        if raid is not None and await raid._is_raid_mode(ctx.guild.id):
            await raid.end_raid_mode(ctx.guild, ended_by=ctx.author.id)
            ended_raid = True
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_change", actor_id=ctx.author.id, detail=f"All security paused until <t:{int(current['until'])}:f>. Reason: {current['reason']}")
        note = "\nRaid mode was active and has been ended." if ended_raid else ""
        await msg.edit(view=success_layout(f"{e('check')} Security paused", (
            f"Back on automatically <t:{int(current['until'])}:R>. Add the accounts you expect to the whitelist now, then run `security enable`.{note}")))

    @security_group.command(name="enable", aliases=["resume", "on"], help="Switch security back on with all your settings exactly as they were.")
    @security_owner()
    async def security_enable(self, ctx: commands.Context):
        e = emoji_manager.get
        if not await security_master.is_off(ctx.guild.id):
            return await ctx.send(view=info_layout("Security is on", "Nothing was paused."))
        current = await security_master.enable(ctx.guild.id)
        paused_for = int(time.time() - current["at"]) if current else 0
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_change", actor_id=ctx.author.id, detail=f"Security switched back on after {format_duration(paused_for)}.")
        await ctx.send(view=success_layout(f"{e('check')} Security is on again", f"Everything works with the settings you had. It was paused for **{format_duration(paused_for)}**."))

    @security_group.command(name="lock", help="Turn the tier lock on or off. On means only the owner, Extra Owners and Trusted Admins can change security settings.")
    @security_owner()
    async def security_lock(self, ctx: commands.Context, toggle: bool):
        e = emoji_manager.get
        await settings.put(ctx.guild.id, settings.find("security", "lock"), toggle)
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_change", actor_id=ctx.author.id, detail=f"Tier lock turned {'on' if toggle else 'off'}.")
        text = "Only the owner, Extra Owners and Trusted Admins can change security settings." if toggle else "Administrators can now change security settings. Critical switches stay owner-only."
        await ctx.send(view=success_layout(f"{e('check')} Tier lock {'on' if toggle else 'off'}", text))

    @security_group.command(name="setup", aliases=["autosetup", "auto"], help="Scan the server and set up security automatically. Add `preview` to see the plan only, or a preset name (relaxed, balanced, strict, paranoid) to choose the level yourself.")
    @security_owner()
    @commands.guild_only()
    async def security_setup(self, ctx: commands.Context, mode: Optional[str] = None):
        e = emoji_manager.get
        word = (mode or "").lower()
        preview = word in ("preview", "plan", "dry", "dryrun")
        force = word if word in settings.PRESETS else ""
        if word and not preview and not force:
            return await ctx.send(view=error_layout("Unknown option", "Use `security setup`, `security setup preview`, or `security setup <relaxed|balanced|strict|paranoid>`."))
        async with ctx.typing():
            analysis = await security_autosetup.analyse(ctx.guild)
            plan = await security_autosetup.build_plan(ctx.guild, analysis, force)
        body = security_autosetup.summary(analysis, plan)
        if preview:
            await ctx.send(view=info_layout(f"{e('shield')} Security setup preview", body + "\n\n-# Run `security setup` to apply this."))
            return await security_cmds.chunked(ctx, f"{e('info')} Recommendations", plan["recommendations"]) if plan["recommendations"] else None

        confirm = ConfirmLayout(f"{e('shield')} Security setup", body, author_id=ctx.author.id, timeout=120.0)
        message = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await message.edit(view=error_layout("Cancelled", "Nothing was changed."))

        await message.edit(view=info_layout(f"{e('shield')} Setting up security", "Applying changes. This can take a minute on large servers."))
        try:
            done, failed, before = await security_autosetup.apply(self.bot, ctx.guild, ctx.author.id, plan)
        except Exception as exc:
            return await message.edit(view=error_layout("Setup failed", f"Stopped part-way: {exc}"))
        lines = [f"- {line}" for line in done] + [f"- **Failed:** {line}" for line in failed]
        await message.edit(view=success_layout(f"{e('check')} Security setup complete", "\n".join(lines)[:3500]))
        if plan["recommendations"]:
            await security_cmds.chunked(ctx, f"{e('info')} Recommended next steps", [f"- {line}" for line in plan["recommendations"]])
        await ctx.send(
            content="Your settings before setup. Run `security import` with this file attached to put your earlier custom values back.",
            file=discord.File(io.BytesIO(before.encode()), filename=f"zyro-security-before-{ctx.guild.id}.json"),
        )

    @security_group.command(name="preset", aliases=["presets"], help="Apply a protection preset: relaxed, balanced, strict or paranoid. Run without a name to compare them.")
    @security_owner()
    async def security_preset(self, ctx: commands.Context, name: Optional[str] = None, mode: Optional[str] = None):
        e = emoji_manager.get
        if name is None:
            body = (
                "**relaxed** — light limits, administrators bypass AntiNuke, gentle raid actions.\n"
                "**balanced** — sensible defaults: restore on, bot-add block, 10-join raid trigger, scam link filter.\n"
                "**strict** — low limits, strict mode, name and suspicious-account gates, invite blocking, account age for verification.\n"
                "**paranoid** — minimum limits, ban on violation, captcha verification, automatic backups and lockdown after an attack.\n\n"
                "Apply one with `security preset <name>`. You can tune anything afterwards, and `security export` saves a copy first."
            )
            return await ctx.send(view=info_layout(f"{e('shield')} Security presets", body + "\nAdd `preview` to see exactly what a preset would change first."))
        if name.lower() in DRY_WORDS:
            return await ctx.send(view=error_layout("Name a preset", "Use `security preset <name> preview`."))
        await security_cmds.apply_preset(ctx, name, (mode or "").lower() in DRY_WORDS or name.lower() in DRY_WORDS)

    @commands.command(name="postmortem", aliases=["incidents", "incident"], help="Read what happened during past raids and attacks. Usage: postmortem [id|end]")
    @security_staff()
    @commands.guild_only()
    async def postmortem_cmd(self, ctx: commands.Context, target: Optional[str] = None):
        e = emoji_manager.get
        if target and target.lower() in ("end", "close", "finish"):
            data = await postmortem.finish(ctx.guild)
            if data is None:
                return await ctx.send(view=error_layout("Nothing open", "There is no incident being tracked right now."))
            return await ctx.send(view=postmortem.render(data))
        if target:
            data = await postmortem.load(ctx.guild.id, target)
            if data is None:
                return await ctx.send(view=error_layout("Not found", "No incident with that id."))
            return await ctx.send(view=postmortem.render(data))
        rows = await postmortem.history(ctx.guild.id)
        live = "An incident is being tracked right now. `postmortem end` closes it and posts the summary.\n\n" if postmortem.is_open(ctx.guild.id) else ""
        if not rows:
            return await ctx.send(view=info_layout(f"{e('shield')} Incidents", live + "No finished incidents on record."))
        lines = [f"`{r['incident_id']}` · {r['kind']} · <t:{int(r['started_at'])}:R> · lasted {postmortem._span(r['ended_at'] - r['started_at'])}" for r in rows]
        await security_cmds.chunked(ctx, f"{e('shield')} Incidents", [live.strip()] + lines if live else lines)

    @security_group.command(name="export", help="Download every changed security setting as a JSON file.")
    @security_owner()
    async def security_export(self, ctx: commands.Context):
        await security_cmds.export_settings(ctx)

    @security_group.command(name="import", help="Restore security settings from an export. Attach the JSON file to the message.")
    @security_owner()
    async def security_import(self, ctx: commands.Context, mode: Optional[str] = None):
        await security_cmds.import_settings(ctx, (mode or "").lower() in DRY_WORDS)

    @security_group.command(name="log", help="Set the channel every security action is posted to.")
    @security_staff()
    async def security_log(self, ctx: commands.Context, channel: discord.TextChannel):
        await security_cmds.set_setting(ctx, "security", "log_channel_id", str(channel.id))

    @security_group.command(name="alerts", help="Set the alert channel and optionally the role pinged for serious detections.")
    @security_staff()
    async def security_alerts(self, ctx: commands.Context, channel: discord.TextChannel, role: Optional[discord.Role] = None):
        await security_cmds.set_setting(ctx, "security", "alert_channel_id", str(channel.id))
        if role is not None:
            await security_cmds.set_setting(ctx, "security", "alert_role_id", str(role.id))

    @security_group.command(name="threat", help="Show the current threat score and what raised it.")
    @has_guild_permission("administrator")
    async def security_threat(self, ctx: commands.Context):
        e = emoji_manager.get
        score = await threat.score(ctx.guild.id)
        threshold = await settings.get(ctx.guild.id, "security", "threat_threshold")
        events = await threat.recent(ctx.guild.id, 10)
        lines = [f"<t:{int(ts)}:R> +{points:g} — {reason}" for ts, points, reason in reversed(events)] or ["No recent detections."]
        head = f"**Score:** {score:.1f}/{threshold}\n**Beast Mode:** {'active' if threat.is_beast(ctx.guild.id) else 'inactive'}\n\n"
        await ctx.send(view=info_layout(f"{e('heat')} Threat score", head + "\n".join(lines)))

    @security_group.command(name="beast", help="Turn off Beast Mode early. Usage: beast off")
    @security_staff()
    async def security_beast(self, ctx: commands.Context, state: str = "off"):
        e = emoji_manager.get
        if state.lower() != "off":
            return await ctx.send(view=error_layout("Invalid usage", "Beast Mode turns on by itself when the threat score is reached. Use `security beast off` to end it."))
        ended = threat.deactivate(ctx.guild.id)
        security.restore_raid_relief(ctx.guild.id)
        text = "Beast Mode ended. Limits are back to normal." if ended else "Beast Mode was not active."
        await ctx.send(view=success_layout(f"{e('check')} Beast Mode", text))

    @security_group.command(name="settings", aliases=["config", "options"], help="List the security core settings. Usage: settings [group|all]")
    @has_guild_permission("administrator")
    async def sec_cfg_settings(self, ctx: commands.Context, group: Optional[str] = None):
        await security_cmds.show_settings(ctx, "security", group)

    @security_group.command(name="get", help="Show one security core setting. Usage: get <key>")
    @has_guild_permission("administrator")
    async def sec_cfg_get(self, ctx: commands.Context, key: str):
        await security_cmds.get_setting(ctx, "security", key)

    @security_group.command(name="set", help="Change a setting in any security module. Usage: set <module> <key> <value>  (module: security, antinuke, antiraid, automod, verification)")
    @security_staff()
    async def sec_cfg_set(self, ctx: commands.Context, module: str, key: str, *, value: str):
        module = module.lower()
        if module not in settings.MODULES:
            return await ctx.send(view=error_layout("Unknown module", f"Choose from: {', '.join(f'`{m}`' for m in settings.MODULES)}"))
        await security_cmds.set_setting(ctx, module, key, value)

    @security_group.command(name="reset", help="Reset a security module setting, or `all`. Usage: reset <module> <key|all>")
    @security_owner()
    async def sec_cfg_reset(self, ctx: commands.Context, module: str, key: str):
        module = module.lower()
        if module not in settings.MODULES:
            return await ctx.send(view=error_layout("Unknown module", f"Choose from: {', '.join(f'`{m}`' for m in settings.MODULES)}"))
        await security_cmds.reset_setting(ctx, module, key)

    @security_group.command(name="add", help="Add to a security core list setting. Usage: add <key> <value>")
    @security_staff()
    async def sec_cfg_add(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.list_edit(ctx, "security", key, value, True)

    @security_group.command(name="remove", help="Remove from a security core list setting. Usage: remove <key> <value>")
    @security_staff()
    async def sec_cfg_remove(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.list_edit(ctx, "security", key, value, False)

    @commands.group(name="whitelist", aliases=["wl"], invoke_without_command=True, help="Exempt members, roles or channels from security systems. Run without arguments to list entries.")
    @security_staff()
    @commands.guild_only()
    async def whitelist_group(self, ctx: commands.Context):
        await self._send_list(ctx, None)

    async def _send_list(self, ctx: commands.Context, scope: Optional[str]):
        e = emoji_manager.get
        rows = await whitelist.list_entries(ctx.guild.id, scope)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('trust')} Whitelist", "Nothing is whitelisted.\nAdd entries with `whitelist add <member|role|channel> [scopes]`."))
        grouped: dict[tuple, list[str]] = {}
        for row in rows:
            grouped.setdefault((row["target_id"], row["target_type"]), []).append(row["scope"])
        lines = [f"{_mention({'target_id': tid, 'target_type': kind})} — {', '.join(f'`{s}`' for s in sorted(scopes))}" for (tid, kind), scopes in grouped.items()]
        await security_cmds._chunked(ctx, f"{e('trust')} Whitelist{f' · {scope}' if scope else ''}", lines)

    @whitelist_group.command(name="add", help="Whitelist a member, role or channel. Usage: whitelist add <target> [scopes...] [duration like 7d] [preview]  (default: all)")
    @security_owner()
    async def whitelist_add(self, ctx: commands.Context, target: WhitelistTargetConverter, *scopes: str):
        e = emoji_manager.get
        tokens, dry = _strip_dry(scopes)
        tokens, expires = whitelist.split_expiry(tokens)
        try:
            names = _scopes(tuple(tokens))
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot whitelist", str(exc)))
        if dry:
            current = {row["scope"] for row in await whitelist.list_entries(ctx.guild.id) if row["target_id"] == target.id}
            fresh = [n for n in names if n not in current]
            lines = [f"{target.mention} would be exempt from: {', '.join(f'`{n}`' for n in fresh) or 'nothing new'}{_until(expires)}."]
            if current & set(names):
                lines.append(f"Already present, unchanged: {', '.join(f'`{n}`' for n in names if n in current)}.")
            lines.append("**Effect**\n" + "\n".join(f"`{n}` — {whitelist.SCOPES[n]}" for n in fresh))
            if "all" in fresh or "antinuke" in fresh:
                lines.append("\n-# This lets them act without AntiNuke limits. Prefer `whitelist action` with specific actions.")
            lines.append("-# Preview only. Nothing was changed.")
            return await ctx.send(view=info_layout(f"{e('shield')} Whitelist preview", "\n".join(lines)))
        try:
            added = [s for s in names if await whitelist.add(ctx.guild.id, target.id, target.type, s, ctx.author.id, expires)]
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot whitelist", str(exc)))
        if not added:
            return await ctx.send(view=error_layout(f"{e('cross')} Already whitelisted", f"{target.mention} already has those scopes."))
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_whitelist", actor_id=ctx.author.id, detail=f"Whitelisted {target.mention} for {', '.join(added)}{_until(expires)}.")
        await ctx.send(view=success_layout(f"{e('trust')} Whitelisted", f"{target.mention} is now exempt from: {', '.join(f'`{s}`' for s in added)}{_until(expires)}."))

    @whitelist_group.command(name="remove", aliases=["delete"], help="Remove a whitelist entry. Usage: whitelist remove <target> [scopes...]  (default: every scope)")
    @security_owner()
    async def whitelist_remove(self, ctx: commands.Context, target: WhitelistTargetConverter, *scopes: str):
        e = emoji_manager.get
        tokens, dry = _strip_dry(scopes)
        try:
            names = _scopes(tuple(tokens)) if tokens else [None]
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot remove", str(exc)))
        if dry:
            rows = [row for row in await whitelist.list_entries(ctx.guild.id) if row["target_id"] == target.id and (names == [None] or row["scope"] in names)]
            shown = ", ".join(f"`{row['scope']}`" for row in rows) or "nothing"
            return await ctx.send(view=info_layout(f"{e('shield')} Whitelist preview", f"{target.mention} would lose: {shown}.\n\n-# Preview only. Nothing was changed."))
        removed = sum([await whitelist.remove(ctx.guild.id, target.id, s) for s in names])
        if not removed:
            return await ctx.send(view=error_layout(f"{e('cross')} Not found", f"{target.mention} has no matching whitelist entry."))
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_whitelist", actor_id=ctx.author.id, detail=f"Removed {removed} whitelist entr{'y' if removed == 1 else 'ies'} for {target.mention}.")
        await ctx.send(view=success_layout(f"{e('check')} Removed", f"{removed} entr{'y' if removed == 1 else 'ies'} removed for {target.mention}."))

    @whitelist_group.command(name="list", aliases=["show"], help="List whitelist entries, optionally for one scope.")
    @security_staff()
    async def whitelist_list(self, ctx: commands.Context, scope: Optional[str] = None):
        if scope is not None and scope.lower() not in whitelist.SCOPES:
            return await ctx.send(view=error_layout("Unknown scope", "Run `whitelist scopes` to see the scopes."))
        await self._send_list(ctx, scope.lower() if scope else None)

    async def _rule_add(self, ctx: commands.Context, target: WhitelistTarget, scope: str, values: list[str], label: str, expires: Optional[float] = None, dry: bool = False):
        e = emoji_manager.get
        if dry:
            existing = {row["value"] for row in await whitelist.rule_list(ctx.guild.id, scope) if row["target_id"] == target.id}
            fresh = [v for v in values if v not in existing]
            shown = ", ".join(f"`{v}`" for v in fresh) or "nothing new"
            return await ctx.send(view=info_layout(f"{e('shield')} Whitelist preview", f"{target.mention} would be allowed {label}: {shown}{_until(expires)}.\n\n-# Preview only. Nothing was changed."))
        try:
            added = [v for v in values if await whitelist.rule_add(ctx.guild.id, target.id, target.type, scope, v, ctx.author.id, expires)]
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot whitelist", str(exc)))
        if not added:
            return await ctx.send(view=error_layout(f"{e('cross')} Already whitelisted", f"{target.mention} already has that rule."))
        shown = ", ".join(f"`{v}`" for v in added)
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_whitelist", actor_id=ctx.author.id, detail=f"Added {label} rule for {target.mention}: {shown}{_until(expires)}.")
        await ctx.send(view=success_layout(f"{e('trust')} Rule added", f"{target.mention}: {label} {shown}{_until(expires)}."))

    @whitelist_group.command(name="action", aliases=["actions"], help="Let a member or role perform AntiNuke actions. Usage: whitelist action <member|role> <actions or groups...>  e.g. whitelist action @Mod channel_create")
    @security_owner()
    async def whitelist_action(self, ctx: commands.Context, target: RuleTargetConverter, *actions: str):
        e = emoji_manager.get
        if target.type not in ("user", "role"):
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot whitelist", "Action rules need a member or a role."))
        tokens, dry = _strip_dry(actions)
        tokens, expires = whitelist.split_expiry(tokens)
        try:
            names = whitelist.resolve_actions(tokens)
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot whitelist", str(exc)))
        if dry:
            held = {row["scope"] for row in await whitelist.rule_list(ctx.guild.id) if row["target_id"] == target.id and row["scope"].startswith("antinuke.")}
            fresh = [n for n in names if f"antinuke.{n}" not in held]
            after = sorted(a.split(".", 1)[1] for a in held | {f"antinuke.{n}" for n in names})
            body = (
                f"{target.mention} would be allowed to: {', '.join(f'`{n}`' for n in fresh) or 'nothing new'}{_until(expires)}.\n"
                f"Allowed afterwards: {', '.join(f'`{a}`' for a in after)}.\n"
                "Every other AntiNuke action stays limited for them.\n\n-# Preview only. Nothing was changed."
            )
            return await ctx.send(view=info_layout(f"{e('shield')} Whitelist preview", body))
        try:
            added = [n for n in names if await whitelist.rule_add(ctx.guild.id, target.id, target.type, f"antinuke.{n}", "", ctx.author.id, expires)]
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot whitelist", str(exc)))
        if not added:
            return await ctx.send(view=error_layout(f"{e('cross')} Already whitelisted", f"{target.mention} already has those actions."))
        shown = ", ".join(f"`{n}`" for n in added)
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_whitelist", actor_id=ctx.author.id, detail=f"Allowed {target.mention} to perform: {', '.join(added)}{_until(expires)}.")
        await ctx.send(view=success_layout(f"{e('trust')} Actions allowed", f"{target.mention} is no longer limited by AntiNuke for: {shown}{_until(expires)}. Everything else is still watched."))

    @whitelist_group.command(name="invite", aliases=["invites"], help="Allow a specific invite. Usage: whitelist invite <member|role|channel|server> <invite link, code or server ID>")
    @security_owner()
    async def whitelist_invite(self, ctx: commands.Context, target: RuleTargetConverter, *, invite: str):
        await self._rule_values(ctx, target, "automod.invite", invite, "invite")

    @whitelist_group.command(name="link", aliases=["domain"], help="Allow a specific domain. Usage: whitelist link <member|role|channel|server> <domain>")
    @security_owner()
    async def whitelist_link(self, ctx: commands.Context, target: RuleTargetConverter, *, domain: str):
        await self._rule_values(ctx, target, "automod.link", domain, "domain")

    @whitelist_group.command(name="word", aliases=["words"], help="Allow a specific banned word. Usage: whitelist word <member|role|channel|server> <word>")
    @security_owner()
    async def whitelist_word(self, ctx: commands.Context, target: RuleTargetConverter, *, word: str):
        await self._rule_values(ctx, target, "automod.word", word, "word")

    async def _rule_values(self, ctx: commands.Context, target: WhitelistTarget, scope: str, raw: str, label: str):
        e = emoji_manager.get
        tokens, dry = _strip_dry(raw.replace(",", " ").split())
        tokens, expires = whitelist.split_expiry(tokens)
        try:
            values = [whitelist.normalize_rule_value(scope, part) for part in tokens]
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot whitelist", str(exc)))
        await self._rule_add(ctx, target, scope, list(dict.fromkeys(values)), label, expires, dry)

    @whitelist_group.command(name="rules", help="List granular whitelist rules, optionally for one scope.")
    @security_staff()
    async def whitelist_rules(self, ctx: commands.Context, scope: Optional[str] = None):
        e = emoji_manager.get
        try:
            resolved = whitelist.resolve_rule_scope(scope) if scope else None
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Unknown scope", str(exc)))
        rows = await whitelist.rule_list(ctx.guild.id, resolved)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('trust')} Granular rules", "No granular rules yet.\nSee `whitelist scopes` for what you can allow."))
        grouped: dict[tuple, list[str]] = {}
        for row in rows:
            grouped.setdefault((row["scope"], row["target_id"], row["target_type"]), []).append(row["value"])
        lines = []
        for (rule_scope, tid, kind), values in grouped.items():
            who = _rule_mention({"target_id": tid, "target_type": kind})
            detail = f" — {', '.join(f'`{v}`' for v in values if v)}" if any(values) else ""
            lines.append(f"{who} · {whitelist.rule_scope_label(rule_scope)}{detail}")
        await security_cmds._chunked(ctx, f"{e('trust')} Granular rules", lines)

    @whitelist_group.command(name="revoke", help="Remove granular rules. Usage: whitelist revoke <member|role|channel|server> <scope> [value]")
    @security_owner()
    async def whitelist_revoke(self, ctx: commands.Context, target: RuleTargetConverter, scope: str, *, value: Optional[str] = None):
        e = emoji_manager.get
        dry = False
        if value:
            kept, dry = _strip_dry(value.split())
            value = " ".join(kept) or None
        try:
            resolved = whitelist.resolve_rule_scope(scope)
            cleaned = whitelist.normalize_rule_value(resolved, value) if value else None
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot remove", str(exc)))
        if dry:
            rows = [r for r in await whitelist.rule_list(ctx.guild.id, resolved) if r["target_id"] == target.id and (cleaned is None or r["value"] == cleaned)]
            shown = ", ".join(f"`{r['value'] or resolved}`" for r in rows) or "nothing"
            return await ctx.send(view=info_layout(f"{e('shield')} Whitelist preview", f"{target.mention} would lose: {shown}.\n\n-# Preview only. Nothing was changed."))
        removed = await whitelist.rule_remove(ctx.guild.id, target.id, resolved, cleaned)
        if not removed:
            return await ctx.send(view=error_layout(f"{e('cross')} Not found", f"{target.mention} has no matching rule."))
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_whitelist", actor_id=ctx.author.id, detail=f"Removed {removed} granular rule(s) for {target.mention}.")
        await ctx.send(view=success_layout(f"{e('check')} Removed", f"{removed} rule(s) removed for {target.mention}."))

    @whitelist_group.command(name="clearrules", help="Remove every granular rule, or every rule for one scope.")
    @security_owner()
    async def whitelist_clearrules(self, ctx: commands.Context, scope: Optional[str] = None):
        e = emoji_manager.get
        try:
            resolved = whitelist.resolve_rule_scope(scope) if scope else None
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Unknown scope", str(exc)))
        count = await whitelist.rule_clear(ctx.guild.id, resolved)
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_whitelist", actor_id=ctx.author.id, detail=f"Cleared {count} granular whitelist rule(s).")
        await ctx.send(view=success_layout(f"{e('check')} Rules cleared", f"{count} rule(s) removed."))

    @whitelist_group.command(name="expire", aliases=["expiry"], help="Set or clear an expiry on everything a target is whitelisted for. Usage: whitelist expire <target> <7d|never>")
    @security_owner()
    async def whitelist_expire(self, ctx: commands.Context, target: RuleTargetConverter, length: str):
        e = emoji_manager.get
        if length.lower() in ("never", "none", "off", "clear"):
            expires = None
        else:
            expires = whitelist.parse_expiry(length)
            if expires is None:
                return await ctx.send(view=error_layout(f"{e('cross')} Invalid length", "Use a length like `12h`, `7d` or `4w`, or `never` to clear it."))
        changed = await whitelist.set_expiry(ctx.guild.id, target.id, expires)
        if not changed:
            return await ctx.send(view=error_layout(f"{e('cross')} Not found", f"{target.mention} has no whitelist entries."))
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_whitelist", actor_id=ctx.author.id, detail=f"Set expiry for {changed} entr{'y' if changed == 1 else 'ies'} on {target.mention}{_until(expires) or ': never'}.")
        await ctx.send(view=success_layout(f"{e('check')} Expiry set", f"{changed} entr{'y' if changed == 1 else 'ies'} for {target.mention} " + (f"expire{'s' if changed == 1 else ''}{_until(expires)}." if expires else "no longer expire.")))

    @whitelist_group.command(name="audit", aliases=["report"], help="List whitelist entries that were never used, are stale, expire soon or point at something deleted.")
    @security_staff()
    async def whitelist_audit(self, ctx: commands.Context):
        e = emoji_manager.get
        body = await self._audit_text(ctx.guild)
        await ctx.send(view=info_layout(f"{e('trust')} Whitelist audit", body))

    @whitelist_group.command(name="scopes", help="Explain every whitelist scope.")
    @security_staff()
    async def whitelist_scopes(self, ctx: commands.Context):
        e = emoji_manager.get
        lines = [f"`{name}` — {text}" for name, text in whitelist.SCOPES.items()]
        groups = "\n".join(f"`{name}` — {', '.join(items)}" for name, items in whitelist.ACTION_GROUPS.items())
        granular = (
            "\n\n**Granular rules**\n"
            "`whitelist action <member|role> <actions or groups>` lets them do only those AntiNuke actions, for example `channel_create` without `channel_delete`.\n"
            f"Actions: {', '.join(f'`{a}`' for a in whitelist.ACTION_KEYS)}\n**Groups**\n{groups}\n"
            "`whitelist invite <target> <link, code or server ID>` allows one invite or every invite to one server.\n"
            "`whitelist link <target> <domain>` allows one domain. Scam and phishing filters still apply.\n"
            "`whitelist word <target> <word>` allows one banned word.\n"
            "For invite, link and word rules the target can be a member, role, channel, category or `server`. "
            "`whitelist rules`, `whitelist revoke` and `whitelist clearrules` manage them."
        )
        await ctx.send(view=info_layout(f"{e('trust')} Whitelist scopes", "\n".join(lines) + "\n\nChannels and categories whitelist everything inside them. Roles apply to every member holding them." + granular))

    @whitelist_group.command(name="clear", help="Remove every whitelist entry, or every entry for one scope.")
    @security_owner()
    async def whitelist_clear(self, ctx: commands.Context, scope: Optional[str] = None):
        e = emoji_manager.get
        if scope is not None and scope.lower() not in whitelist.SCOPES:
            return await ctx.send(view=error_layout("Unknown scope", "Run `whitelist scopes` to see the scopes."))
        count = await whitelist.clear(ctx.guild.id, scope.lower() if scope else None)
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_whitelist", actor_id=ctx.author.id, detail=f"Cleared {count} whitelist entr{'y' if count == 1 else 'ies'}.")
        await ctx.send(view=success_layout(f"{e('check')} Whitelist cleared", f"{count} entr{'y' if count == 1 else 'ies'} removed."))


async def setup(bot: commands.Bot):
    await bot.add_cog(SecurityHub(bot))
