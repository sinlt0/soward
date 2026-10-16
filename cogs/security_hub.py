from typing import Optional

import discord
from discord.ext import commands

import config
from utils import db, emoji_manager, security, security_cmds, threat
from utils import security_settings as settings
from utils import security_whitelist as whitelist
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
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


def _mention(row: dict) -> str:
    return {"user": f"<@{row['target_id']}>", "role": f"<@&{row['target_id']}>", "channel": f"<#{row['target_id']}>"}[row["target_type"]]


class SecurityHub(commands.Cog):
    category = "Config"
    submodule = "Security"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _status_line(self, guild: discord.Guild) -> str:
        e = emoji_manager.get
        on, off = "🟢", "🔴"
        lines = []
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

    @security_group.command(name="lock", help="Turn the tier lock on or off. On means only the owner, Extra Owners and Trusted Admins can change security settings.")
    @security_owner()
    async def security_lock(self, ctx: commands.Context, toggle: bool):
        e = emoji_manager.get
        await settings.put(ctx.guild.id, settings.find("security", "lock"), toggle)
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_change", actor_id=ctx.author.id, detail=f"Tier lock turned {'on' if toggle else 'off'}.")
        text = "Only the owner, Extra Owners and Trusted Admins can change security settings." if toggle else "Administrators can now change security settings. Critical switches stay owner-only."
        await ctx.send(view=success_layout(f"{e('check')} Tier lock {'on' if toggle else 'off'}", text))

    @security_group.command(name="preset", aliases=["presets"], help="Apply a protection preset: relaxed, balanced, strict or paranoid. Run without a name to compare them.")
    @security_owner()
    async def security_preset(self, ctx: commands.Context, name: Optional[str] = None):
        e = emoji_manager.get
        if name is None:
            body = (
                "**relaxed** — light limits, administrators bypass AntiNuke, gentle raid actions.\n"
                "**balanced** — sensible defaults: restore on, bot-add block, 10-join raid trigger, scam link filter.\n"
                "**strict** — low limits, strict mode, name and suspicious-account gates, invite blocking, account age for verification.\n"
                "**paranoid** — minimum limits, ban on violation, captcha verification, automatic backups and lockdown after an attack.\n\n"
                "Apply one with `security preset <name>`. You can tune anything afterwards, and `security export` saves a copy first."
            )
            return await ctx.send(view=info_layout(f"{e('shield')} Security presets", body))
        await security_cmds.apply_preset(ctx, name)

    @security_group.command(name="export", help="Download every changed security setting as a JSON file.")
    @security_owner()
    async def security_export(self, ctx: commands.Context):
        await security_cmds.export_settings(ctx)

    @security_group.command(name="import", help="Restore security settings from an export. Attach the JSON file to the message.")
    @security_owner()
    async def security_import(self, ctx: commands.Context):
        await security_cmds.import_settings(ctx)

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

    @whitelist_group.command(name="add", help="Whitelist a member, role or channel. Usage: whitelist add <target> [scopes...]  (default: all)")
    @security_owner()
    async def whitelist_add(self, ctx: commands.Context, target: WhitelistTargetConverter, *scopes: str):
        e = emoji_manager.get
        try:
            names = _scopes(scopes)
            added = [s for s in names if await whitelist.add(ctx.guild.id, target.id, target.type, s, ctx.author.id)]
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot whitelist", str(exc)))
        if not added:
            return await ctx.send(view=error_layout(f"{e('cross')} Already whitelisted", f"{target.mention} already has those scopes."))
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="security_whitelist", actor_id=ctx.author.id, detail=f"Whitelisted {target.mention} for {', '.join(added)}.")
        await ctx.send(view=success_layout(f"{e('trust')} Whitelisted", f"{target.mention} is now exempt from: {', '.join(f'`{s}`' for s in added)}."))

    @whitelist_group.command(name="remove", aliases=["delete"], help="Remove a whitelist entry. Usage: whitelist remove <target> [scopes...]  (default: every scope)")
    @security_owner()
    async def whitelist_remove(self, ctx: commands.Context, target: WhitelistTargetConverter, *scopes: str):
        e = emoji_manager.get
        try:
            names = _scopes(scopes) if scopes else [None]
        except ValueError as exc:
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot remove", str(exc)))
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

    @whitelist_group.command(name="scopes", help="Explain every whitelist scope.")
    @security_staff()
    async def whitelist_scopes(self, ctx: commands.Context):
        e = emoji_manager.get
        lines = [f"`{name}` — {text}" for name, text in whitelist.SCOPES.items()]
        await ctx.send(view=info_layout(f"{e('trust')} Whitelist scopes", "\n".join(lines) + "\n\nChannels and categories whitelist everything inside them. Roles apply to every member holding them."))

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
