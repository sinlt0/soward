import uuid
from typing import Optional

import discord
from discord.ext import commands, tasks

import config
from utils import booster as bst
from utils import db, emoji_manager, guild_settings
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

ONOFF = {"on": 1, "off": 0, "enable": 1, "disable": 0, "yes": 1, "no": 0, "true": 1, "false": 0}
ALLOW_KEYS = {"name": "allow_name", "color": "allow_color", "colour": "allow_color", "icon": "allow_icon", "hoist": "allow_hoist", "display": "allow_hoist", "perms": "allow_perms", "permissions": "allow_perms"}


def _flag(value: str) -> int:
    key = value.lower()
    if key not in ONOFF:
        raise commands.BadArgument("Use `on` or `off`.")
    return ONOFF[key]


def _yn(value) -> str:
    return "on" if value else "off"


class Booster(commands.Cog):
    category = "Engagement"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.sweep.start()

    async def cog_unload(self):
        self.sweep.cancel()

    @tasks.loop(seconds=config.BOOSTER_SWEEP_SECONDS)
    async def sweep(self):
        rows = await db.raw_fetch("SELECT guild_id FROM booster_config WHERE enabled=1")
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if guild is None:
                continue
            cfg = await bst.get_cfg(guild.id)
            tiers = await bst.list_tiers(guild.id)
            seen = set()
            for member in guild.premium_subscribers:
                seen.add(member.id)
                await bst.sync_member(guild, member, cfg, tiers)
            for record in await db.raw_fetch("SELECT user_id FROM booster_members WHERE guild_id=?", (guild.id,)):
                if record["user_id"] in seen:
                    continue
                member = guild.get_member(record["user_id"])
                if member is None:
                    await bst.drop_member(guild, record["user_id"])
                else:
                    await bst.sync_member(guild, member, cfg, tiers)

    @sweep.before_loop
    async def _before_sweep(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.type not in bst.BOOST_TYPES or not isinstance(message.author, discord.Member):
            return
        cfg = await bst.get_cfg(message.guild.id)
        if not cfg["enabled"]:
            return
        content = (message.content or "").strip()
        amount = int(content) if content.isdigit() and 0 < int(content) <= 20 else 1
        await bst.add_boosts(message.guild.id, message.author, amount)
        await bst.sync_member(message.guild, message.author, cfg)
        await bst.restore_custom(message.guild, message.author, cfg)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if (before.premium_since is None) == (after.premium_since is None):
            return
        cfg = await bst.get_cfg(after.guild.id)
        if not cfg["enabled"]:
            return
        await bst.sync_member(after.guild, after, cfg)
        if after.premium_since is not None:
            await bst.restore_custom(after.guild, after, cfg)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.premium_since is None:
            return
        cfg = await bst.get_cfg(member.guild.id)
        if cfg["enabled"]:
            await bst.sync_member(member.guild, member, cfg)
            await bst.restore_custom(member.guild, member, cfg)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = await bst.get_cfg(member.guild.id)
        if cfg["enabled"]:
            await bst.drop_member(member.guild, member.id)

    async def _role_ok(self, ctx: commands.Context, role: discord.Role) -> bool:
        if role.is_default() or role.managed or role >= ctx.guild.me.top_role:
            await ctx.send(view=error_layout("Role not usable", "Pick a normal role that is below Soward's top role."))
            return False
        return True

    @commands.group(name="booster", aliases=["boosters", "boosterperks"], invoke_without_command=True, help="Booster tier roles and custom booster roles.")
    @commands.guild_only()
    async def booster_group(self, ctx: commands.Context):
        cfg = await bst.get_cfg(ctx.guild.id)
        e = emoji_manager.get
        record = await bst.get_record(ctx.guild.id, ctx.author.id)
        lines = []
        if ctx.author.premium_since is not None:
            value = bst.metric(cfg, record, ctx.author)
            lines.append(f"You are boosting since <t:{int(ctx.author.premium_since.timestamp())}:D>. Your tier counter: **{value} {bst.metric_label(cfg)}**.")
            _, role = await bst.get_custom(ctx.guild, ctx.author.id)
            if cfg["custom_enabled"]:
                lines.append(f"Custom role: {role.mention}" if role else "You can make a custom role with `booster role create <name> [colour]`.")
        else:
            lines.append("You are not boosting this server right now.")
        tiers = await bst.list_tiers(ctx.guild.id)
        if tiers and cfg["enabled"]:
            lines.append("\n**Tiers**\n" + "\n".join(f"{t['boosts']}+ {bst.metric_label(cfg)}: <@&{t['role_id']}>" for t in tiers))
        if not cfg["enabled"]:
            lines.append("Booster perks are not turned on yet. Admins can start with `booster setup`.")
        admin = ctx.author.guild_permissions.manage_guild
        lines.append("\n`booster role` manage your custom role" + ("\n`booster settings` admin settings" if admin else ""))
        await ctx.send(view=info_layout(f"{e('star')} Booster perks", "\n".join(lines)))

    @booster_group.command(name="setup", help="Turn on booster perks with a starter set of tier roles.")
    @has_guild_permission("manage_guild")
    async def b_setup(self, ctx: commands.Context):
        me = ctx.guild.me.guild_permissions
        if not me.manage_roles:
            return await ctx.send(view=error_layout("Missing permission", "Soward needs Manage Roles."))
        tiers = await bst.list_tiers(ctx.guild.id)
        made = []
        if not tiers:
            for boosts, name, color in config.BOOSTER_PRESET_TIERS:
                try:
                    role = await ctx.guild.create_role(name=name, colour=discord.Colour(color), reason="Soward booster setup")
                except discord.HTTPException as exc:
                    return await ctx.send(view=error_layout("Could not create roles", str(exc)[:150]))
                try:
                    await role.edit(position=await bst.target_position(ctx.guild, await bst.get_cfg(ctx.guild.id)))
                except discord.HTTPException:
                    pass
                await db.raw_execute("INSERT OR REPLACE INTO booster_tiers (guild_id, boosts, role_id) VALUES (?, ?, ?)", (ctx.guild.id, boosts, role.id))
                made.append(f"{boosts}+ boosts: {role.mention}")
        await bst.set_cfg(ctx.guild.id, enabled=1)
        body = "Booster perks are on. " + ("Created tiers:\n" + "\n".join(made) if made else "Your existing tiers were kept.")
        body += "\n\nNext: `booster backfill` to count past boosts, `booster custom on` for custom roles, `booster settings` to review everything."
        await ctx.send(view=success_layout("Booster perks ready", body))
        await self.sync_all(ctx.guild)

    async def sync_all(self, guild: discord.Guild) -> int:
        cfg = await bst.get_cfg(guild.id)
        tiers = await bst.list_tiers(guild.id)
        done = 0
        for member in guild.premium_subscribers:
            await bst.sync_member(guild, member, cfg, tiers)
            done += 1
        return done

    @booster_group.command(name="settings", aliases=["config"], help="Show booster settings.")
    @has_guild_permission("manage_guild")
    async def b_settings(self, ctx: commands.Context):
        c = await bst.get_cfg(ctx.guild.id)
        ref = ctx.guild.get_role(c["position_ref_id"]) if c["position_ref_id"] else None
        base = ctx.guild.get_role(c["base_role_id"]) if c["base_role_id"] else None
        blocked = await bst.blocked_words(ctx.guild.id)
        body = (
            f"**Perks:** {_yn(c['enabled'])}\n**Tier by:** {c['tier_mode']} ({'boost count' if c['tier_mode'] == 'count' else 'days boosting'})\n"
            f"**Stack roles:** {c['stack_mode']}\n**Booster role for everyone:** {base.mention if base else 'none'}\n"
            f"**Grace after unboost:** {c['grace_hours']} h\n**Remove custom role on unboost:** {_yn(c['remove_on_unboost'])}, restore on reboost: {_yn(c['restore_on_reboost'])}\n\n"
            f"**Custom roles:** {_yn(c['custom_enabled'])}, needs {c['custom_min']} {bst.metric_label(c)}\n"
            f"Members may change: name {_yn(c['allow_name'])}, colour {_yn(c['allow_color'])}, icon {_yn(c['allow_icon'])}, "
            f"display separately {_yn(c['allow_hoist'])}, permissions {_yn(c['allow_perms'])}\n"
            f"Position: **{c['position_mode']}** {ref.mention if ref else (base.mention if base else 'the Server Booster role')}\n"
            f"Edit cooldown: {c['cooldown_hours']} h, max name length: {c['max_name_len']}, name filter: {_yn(c['name_filter'])} ({len(blocked)} blocked words)"
        )
        await ctx.send(view=info_layout("Booster settings", body))

    @booster_group.command(name="toggle", help="Turn booster perks on or off. Usage: booster toggle <on|off>")
    @has_guild_permission("manage_guild")
    async def b_toggle(self, ctx: commands.Context, state: str):
        value = _flag(state)
        await bst.set_cfg(ctx.guild.id, enabled=value)
        await ctx.send(view=success_layout("Updated", f"Booster perks are **{_yn(value)}**."))
        if value:
            await self.sync_all(ctx.guild)

    @booster_group.command(name="mode", help="Tier by boost count or days boosting. Usage: booster mode <count|days>")
    @has_guild_permission("manage_guild")
    async def b_mode(self, ctx: commands.Context, mode: str):
        mode = mode.lower()
        if mode not in ("count", "days"):
            return await ctx.send(view=error_layout("Invalid", "Use `count` or `days`."))
        await bst.set_cfg(ctx.guild.id, tier_mode=mode)
        note = "Tier numbers now mean days of boosting." if mode == "days" else "Tier numbers now mean boosts."
        await ctx.send(view=success_layout("Updated", f"{note} Review your tiers with `booster tier list`."))
        await self.sync_all(ctx.guild)

    @booster_group.command(name="stack", help="Give only the highest tier role or every tier reached. Usage: booster stack <highest|all>")
    @has_guild_permission("manage_guild")
    async def b_stack(self, ctx: commands.Context, mode: str):
        mode = mode.lower()
        if mode not in ("highest", "all"):
            return await ctx.send(view=error_layout("Invalid", "Use `highest` or `all`."))
        await bst.set_cfg(ctx.guild.id, stack_mode=mode)
        await ctx.send(view=success_layout("Updated", f"Members get **{mode}** tier role(s)."))
        await self.sync_all(ctx.guild)

    @booster_group.command(name="base", help="A role every booster gets. Usage: booster base <@role|off>")
    @has_guild_permission("manage_guild")
    async def b_base(self, ctx: commands.Context, role: Optional[discord.Role] = None, *, text: Optional[str] = None):
        if role is None:
            if (text or "").lower() != "off":
                return await ctx.send(view=error_layout("Invalid", "Mention a role or say `off`."))
            await bst.set_cfg(ctx.guild.id, base_role_id=None)
            return await ctx.send(view=success_layout("Updated", "No shared booster role."))
        if not await self._role_ok(ctx, role):
            return
        await bst.set_cfg(ctx.guild.id, base_role_id=role.id)
        await ctx.send(view=success_layout("Updated", f"Every booster gets {role.mention}."))
        await self.sync_all(ctx.guild)

    @booster_group.command(name="grace", help="Hours to keep roles after a boost ends. Usage: booster grace <0-168>")
    @has_guild_permission("manage_guild")
    async def b_grace(self, ctx: commands.Context, hours: int):
        if not 0 <= hours <= 168:
            return await ctx.send(view=error_layout("Invalid", "Use 0 to 168 hours."))
        await bst.set_cfg(ctx.guild.id, grace_hours=hours)
        await ctx.send(view=success_layout("Updated", f"Roles stay for **{hours} h** after a boost ends." if hours else "Roles are removed as soon as a boost ends."))

    @booster_group.command(name="keep", help="Keep or remove custom roles after unboost. Usage: booster keep <remove|keep> [restore on|off]")
    @has_guild_permission("manage_guild")
    async def b_keep(self, ctx: commands.Context, action: str, restore: Optional[str] = None):
        action = action.lower()
        if action not in ("remove", "keep"):
            return await ctx.send(view=error_layout("Invalid", "Use `remove` or `keep`."))
        fields = {"remove_on_unboost": 1 if action == "remove" else 0}
        if restore is not None:
            fields["restore_on_reboost"] = _flag(restore)
        await bst.set_cfg(ctx.guild.id, **fields)
        await ctx.send(view=success_layout("Updated", f"Custom roles are **{'deleted' if action == 'remove' else 'kept'}** when a boost ends."))

    @booster_group.group(name="tier", invoke_without_command=True, help="Manage tier roles.")
    @has_guild_permission("manage_guild")
    async def b_tier(self, ctx: commands.Context):
        cfg = await bst.get_cfg(ctx.guild.id)
        tiers = await bst.list_tiers(ctx.guild.id)
        body = "\n".join(f"{t['boosts']}+ {bst.metric_label(cfg)}: <@&{t['role_id']}>" for t in tiers) or "No tiers yet."
        body += "\n\n`booster tier add <number> <@role>` | `tier create <number> <name> [colour]` | `tier remove <number>` | `tier xp <number> <multiplier>`"
        await ctx.send(view=info_layout("Booster tiers", body))

    @b_tier.command(name="list")
    @has_guild_permission("manage_guild")
    async def b_tier_list(self, ctx: commands.Context):
        await self.b_tier.callback(self, ctx)

    async def _save_tier(self, ctx: commands.Context, number: int, role: discord.Role):
        if number < 1 or number > 9999:
            return await ctx.send(view=error_layout("Invalid", "Use a number from 1 to 9999."))
        tiers = await bst.list_tiers(ctx.guild.id)
        if len(tiers) >= config.BOOSTER_MAX_TIERS and not any(t["boosts"] == number for t in tiers):
            return await ctx.send(view=error_layout("Limit reached", f"A server can have {config.BOOSTER_MAX_TIERS} tiers."))
        await db.raw_execute("INSERT OR REPLACE INTO booster_tiers (guild_id, boosts, role_id) VALUES (?, ?, ?)", (ctx.guild.id, number, role.id))
        cfg = await bst.get_cfg(ctx.guild.id)
        await ctx.send(view=success_layout("Tier saved", f"**{number}+ {bst.metric_label(cfg)}** gives {role.mention}."))
        await self.sync_all(ctx.guild)

    @b_tier.command(name="add", help="Use an existing role. Usage: booster tier add <number> <@role>")
    @has_guild_permission("manage_guild")
    async def b_tier_add(self, ctx: commands.Context, number: int, role: discord.Role):
        if await self._role_ok(ctx, role):
            await self._save_tier(ctx, number, role)

    @b_tier.command(name="create", help="Create the role too. Usage: booster tier create <number> <name> [colour]")
    @has_guild_permission("manage_guild")
    async def b_tier_create(self, ctx: commands.Context, number: int, name: str, colour: Optional[str] = None):
        try:
            color = bst.parse_color(colour) if colour else 0xF1C40F
        except bst.BoosterError as exc:
            return await ctx.send(view=error_layout("Invalid colour", str(exc)))
        if not ctx.guild.me.guild_permissions.manage_roles:
            return await ctx.send(view=error_layout("Missing permission", "Soward needs Manage Roles."))
        try:
            role = await ctx.guild.create_role(name=name[:100], colour=discord.Colour(color), reason="Soward booster tier")
        except discord.HTTPException as exc:
            return await ctx.send(view=error_layout("Could not create the role", str(exc)[:150]))
        await self._save_tier(ctx, number, role)

    @b_tier.command(name="remove", aliases=["delete"], help="Remove a tier. Usage: booster tier remove <number>")
    @has_guild_permission("manage_guild")
    async def b_tier_remove(self, ctx: commands.Context, number: int):
        row = await db.raw_fetchone("SELECT role_id FROM booster_tiers WHERE guild_id=? AND boosts=?", (ctx.guild.id, number))
        if not row:
            return await ctx.send(view=error_layout("Not found", "There is no tier with that number."))
        await db.raw_execute("DELETE FROM booster_tiers WHERE guild_id=? AND boosts=?", (ctx.guild.id, number))
        await db.raw_execute("DELETE FROM xp_multipliers WHERE guild_id=? AND scope_type='role' AND scope_id=? AND label='booster'", (ctx.guild.id, row["role_id"]))
        await ctx.send(view=success_layout("Tier removed", f"The role <@&{row['role_id']}> was not deleted and members keep it until you remove it."))

    @b_tier.command(name="xp", help="XP multiplier for a tier. Usage: booster tier xp <number> <multiplier, 1 to remove>")
    @has_guild_permission("manage_guild")
    async def b_tier_xp(self, ctx: commands.Context, number: int, multiplier: float):
        row = await db.raw_fetchone("SELECT role_id FROM booster_tiers WHERE guild_id=? AND boosts=?", (ctx.guild.id, number))
        if not row:
            return await ctx.send(view=error_layout("Not found", "There is no tier with that number."))
        if not 1.0 <= multiplier <= 10.0:
            return await ctx.send(view=error_layout("Invalid", "Use 1 to 10. A value of 1 removes the bonus."))
        await db.raw_execute("DELETE FROM xp_multipliers WHERE guild_id=? AND scope_type='role' AND scope_id=? AND label='booster'", (ctx.guild.id, row["role_id"]))
        if multiplier > 1.0:
            await db.raw_execute(
                "INSERT INTO xp_multipliers (multiplier_id, guild_id, scope_type, scope_id, multiplier, label) VALUES (?, ?, 'role', ?, ?, 'booster')",
                (str(uuid.uuid4())[:8], ctx.guild.id, row["role_id"], multiplier),
            )
        await ctx.send(view=success_layout("XP bonus saved", f"<@&{row['role_id']}> earns **{multiplier:g}x** XP." if multiplier > 1 else "The XP bonus was removed."))

    @booster_group.command(name="set", help="Set a member's boost count. Usage: booster set <@member> <count>")
    @has_guild_permission("manage_guild")
    async def b_set(self, ctx: commands.Context, member: discord.Member, count: int):
        if member.premium_since is None:
            return await ctx.send(view=error_layout("Not boosting", f"{member.mention} is not boosting right now."))
        await bst.set_count(ctx.guild.id, member, count)
        await bst.sync_member(ctx.guild, member)
        await ctx.send(view=success_layout("Count saved", f"{member.mention} is now counted as **{max(1, min(count, config.BOOSTER_MAX_COUNT))}** boost(s)."))

    @booster_group.command(name="check", help="See a member's booster data. Usage: booster check <@member>")
    @has_guild_permission("manage_guild")
    async def b_check(self, ctx: commands.Context, member: discord.Member):
        cfg = await bst.get_cfg(ctx.guild.id)
        record = await bst.get_record(ctx.guild.id, member.id)
        _, role = await bst.get_custom(ctx.guild, member.id)
        body = (
            f"Boosting: {'since <t:' + str(int(member.premium_since.timestamp())) + ':D>' if member.premium_since else 'no'}\n"
            f"Counted boosts: {record['boost_count'] if record else 0}\nTier value: {bst.metric(cfg, record, member)} {bst.metric_label(cfg)}\n"
            f"Custom role: {role.mention if role else 'none'}"
        )
        await ctx.send(view=info_layout(f"Booster: {member.display_name}", body))

    @booster_group.command(name="list", help="List current boosters.")
    @has_guild_permission("manage_guild")
    async def b_list(self, ctx: commands.Context):
        cfg = await bst.get_cfg(ctx.guild.id)
        rows = []
        for member in sorted(ctx.guild.premium_subscribers, key=lambda m: m.premium_since):
            record = await bst.get_record(ctx.guild.id, member.id)
            rows.append(f"{member.mention} {bst.metric(cfg, record, member)} {bst.metric_label(cfg)}")
        body = "\n".join(rows[:40]) or "Nobody is boosting."
        if len(rows) > 40:
            body += f"\n...and {len(rows) - 40} more"
        await ctx.send(view=info_layout(f"Boosters ({len(rows)})", body))

    @booster_group.command(name="backfill", help="Count past boosts from the system channel's boost messages.")
    @has_guild_permission("manage_guild")
    @commands.cooldown(1, 120, commands.BucketType.guild)
    async def b_backfill(self, ctx: commands.Context):
        channel = ctx.guild.system_channel
        if channel is None or not channel.permissions_for(ctx.guild.me).read_message_history:
            return await ctx.send(view=error_layout("No system channel", "Discord posts boost messages in the system channel. Set one in Server Settings and give Soward access, or use `booster set`."))
        since = {m.id: m.premium_since for m in ctx.guild.premium_subscribers}
        counts: dict[int, int] = {}
        scanned = 0
        async with ctx.typing():
            async for message in channel.history(limit=config.BOOSTER_BACKFILL_LIMIT):
                scanned += 1
                if message.type not in bst.BOOST_TYPES or message.author.id not in since:
                    continue
                if message.created_at < since[message.author.id]:
                    continue
                content = (message.content or "").strip()
                counts[message.author.id] = counts.get(message.author.id, 0) + (int(content) if content.isdigit() and 0 < int(content) <= 20 else 1)
        for user_id, total in counts.items():
            member = ctx.guild.get_member(user_id)
            if member is not None:
                await bst.set_count(ctx.guild.id, member, total)
        await self.sync_all(ctx.guild)
        await ctx.send(view=success_layout("Backfill done", (
            f"Read {scanned} messages and updated **{len(counts)}** boosters. Discord does not expose how many boosts a member gives, "
            "so this counts boost messages since each member started boosting. Fix any member with `booster set`."
        )))

    @booster_group.command(name="sync", help="Recheck every booster's roles.")
    @has_guild_permission("manage_guild")
    async def b_sync(self, ctx: commands.Context):
        total = await self.sync_all(ctx.guild)
        await ctx.send(view=success_layout("Synced", f"Checked **{total}** boosters."))

    @booster_group.group(name="custom", invoke_without_command=True, help="Settings for custom booster roles.")
    @has_guild_permission("manage_guild")
    async def b_custom(self, ctx: commands.Context):
        body = (
            "`booster custom on|off` turn custom roles on or off\n`booster custom min <number>` boosts (or days) needed\n"
            "`booster custom allow <name|color|icon|hoist|perms> <on|off>` what members may change\n"
            "`booster custom position <above|below> [@role]` where new roles are created\n`booster custom reposition` move existing roles\n"
            "`booster custom cooldown <hours>` | `booster custom maxname <1-100>` | `booster custom filter <on|off>`\n"
            "`booster custom blocked add|remove|list <word>`"
        )
        await ctx.send(view=info_layout("Custom booster roles", body))

    @b_custom.command(name="on", aliases=["enable"])
    @has_guild_permission("manage_guild")
    async def bc_on(self, ctx: commands.Context):
        await bst.set_cfg(ctx.guild.id, custom_enabled=1)
        await ctx.send(view=success_layout("Updated", "Boosters can now create a custom role with `booster role create`."))

    @b_custom.command(name="off", aliases=["disable"])
    @has_guild_permission("manage_guild")
    async def bc_off(self, ctx: commands.Context):
        await bst.set_cfg(ctx.guild.id, custom_enabled=0)
        await ctx.send(view=success_layout("Updated", "Custom booster roles are off. Existing roles stay until their owner stops boosting."))

    @b_custom.command(name="min")
    @has_guild_permission("manage_guild")
    async def bc_min(self, ctx: commands.Context, number: int):
        if not 1 <= number <= 9999:
            return await ctx.send(view=error_layout("Invalid", "Use 1 to 9999."))
        await bst.set_cfg(ctx.guild.id, custom_min=number)
        await ctx.send(view=success_layout("Updated", f"A custom role needs **{number}** boosts (or days in days mode)."))

    @b_custom.command(name="allow")
    @has_guild_permission("manage_guild")
    async def bc_allow(self, ctx: commands.Context, setting: str, state: str):
        column = ALLOW_KEYS.get(setting.lower())
        if column is None:
            return await ctx.send(view=error_layout("Unknown setting", "Use `name`, `color`, `icon`, `hoist` or `perms`."))
        value = _flag(state)
        await bst.set_cfg(ctx.guild.id, **{column: value})
        await ctx.send(view=success_layout("Updated", f"Members {'can' if value else 'cannot'} change **{setting.lower()}**."))

    @b_custom.command(name="position")
    @has_guild_permission("manage_guild")
    async def bc_position(self, ctx: commands.Context, mode: str, role: Optional[discord.Role] = None):
        mode = mode.lower()
        if mode not in ("above", "below"):
            return await ctx.send(view=error_layout("Invalid", "Use `above` or `below`, then the role to place around."))
        if role is not None and role >= ctx.guild.me.top_role:
            return await ctx.send(view=error_layout("Role too high", "Soward cannot place roles around a role at or above its own."))
        fields = {"position_mode": mode}
        if role is not None:
            fields["position_ref_id"] = role.id
        await bst.set_cfg(ctx.guild.id, **fields)
        cfg = await bst.get_cfg(ctx.guild.id)
        ref = ctx.guild.get_role(cfg["position_ref_id"]) if cfg["position_ref_id"] else None
        await ctx.send(view=success_layout("Updated", f"New custom roles go **{mode}** {ref.mention if ref else 'the booster role'}. Run `booster custom reposition` to move existing ones."))

    @b_custom.command(name="reposition")
    @has_guild_permission("manage_guild")
    async def bc_reposition(self, ctx: commands.Context):
        moved = await bst.reposition_all(ctx.guild, await bst.get_cfg(ctx.guild.id))
        await ctx.send(view=success_layout("Done", f"Moved **{moved}** custom roles."))

    @b_custom.command(name="cooldown")
    @has_guild_permission("manage_guild")
    async def bc_cooldown(self, ctx: commands.Context, hours: int):
        if not 0 <= hours <= 720:
            return await ctx.send(view=error_layout("Invalid", "Use 0 to 720 hours."))
        await bst.set_cfg(ctx.guild.id, cooldown_hours=hours)
        await ctx.send(view=success_layout("Updated", f"Members can edit their role every **{hours} h**."))

    @b_custom.command(name="maxname")
    @has_guild_permission("manage_guild")
    async def bc_maxname(self, ctx: commands.Context, length: int):
        if not 1 <= length <= 100:
            return await ctx.send(view=error_layout("Invalid", "Use 1 to 100."))
        await bst.set_cfg(ctx.guild.id, max_name_len=length)
        await ctx.send(view=success_layout("Updated", f"Role names can be up to **{length}** characters."))

    @b_custom.command(name="filter")
    @has_guild_permission("manage_guild")
    async def bc_filter(self, ctx: commands.Context, state: str):
        value = _flag(state)
        await bst.set_cfg(ctx.guild.id, name_filter=value)
        await ctx.send(view=success_layout("Updated", f"The blocked word filter is **{_yn(value)}**."))

    @b_custom.command(name="blocked")
    @has_guild_permission("manage_guild")
    async def bc_blocked(self, ctx: commands.Context, action: str, *, word: Optional[str] = None):
        words = await bst.blocked_words(ctx.guild.id)
        action = action.lower()
        if action == "list":
            return await ctx.send(view=info_layout("Blocked words", ", ".join(f"`{w}`" for w in words) or "None yet."))
        if not word:
            return await ctx.send(view=error_layout("Missing word", "Add the word after the action."))
        word = word.lower().strip()[:40]
        if action == "add":
            if word not in words and len(words) < 100:
                words.append(word)
        elif action == "remove":
            words = [w for w in words if w != word]
        else:
            return await ctx.send(view=error_layout("Invalid", "Use `add`, `remove` or `list`."))
        await guild_settings.set(ctx.guild.id, bst.BLOCKED_KEY, words)
        await ctx.send(view=success_layout("Updated", f"The filter has **{len(words)}** words."))

    @booster_group.group(name="role", aliases=["customrole", "cr"], invoke_without_command=True, help="Manage your custom booster role.")
    @commands.guild_only()
    async def b_role(self, ctx: commands.Context):
        cfg = await bst.get_cfg(ctx.guild.id)
        record, role = await bst.get_custom(ctx.guild, ctx.author.id)
        lines = []
        if role is not None:
            lines.append(f"Your role: {role.mention}")
            can = [n for n, k in (("name", "allow_name"), ("colour", "allow_color"), ("icon", "allow_icon"), ("hoist", "allow_hoist"), ("perms", "allow_perms")) if cfg[k]]
            lines.append("You can change: " + ", ".join(can))
        else:
            lines.append("You do not have a custom role yet.")
        lines.append(
            "\n`booster role create <name> [colour]`\n`booster role name <name>` `booster role color <colour>`\n"
            "`booster role icon` (attach an image) `booster role icon remove`\n"
            "`booster role hoist <on|off>` `booster role perms [permissions]`\n`booster role delete`"
        )
        await ctx.send(view=info_layout("Custom booster role", "\n".join(lines)))

    async def _mine(self, ctx: commands.Context, need_role: bool = True):
        cfg = await bst.get_cfg(ctx.guild.id)
        record = await bst.get_record(ctx.guild.id, ctx.author.id)
        problem = bst.eligible(cfg, ctx.author, record)
        if problem:
            raise bst.BoosterError(problem)
        saved, role = await bst.get_custom(ctx.guild, ctx.author.id)
        if need_role and role is None:
            raise bst.BoosterError("You do not have a custom role yet. Use `booster role create <name> [colour]`.")
        return cfg, saved, role

    async def _run(self, ctx: commands.Context, work):
        try:
            message = await work()
        except bst.BoosterError as exc:
            return await ctx.send(view=error_layout("Not allowed", str(exc)))
        except discord.HTTPException as exc:
            return await ctx.send(view=error_layout("Discord refused", str(exc)[:180]))
        await ctx.send(view=success_layout("Done", message))

    @b_role.command(name="create", help="Create your role. Usage: booster role create <name> [colour]")
    async def br_create(self, ctx: commands.Context, name: str, colour: Optional[str] = None):
        async def work():
            cfg, saved, role = await self._mine(ctx, need_role=False)
            if role is not None:
                raise bst.BoosterError(f"You already have {role.mention}. Edit it instead.")
            if not ctx.guild.me.guild_permissions.manage_roles:
                raise bst.BoosterError("Soward is missing Manage Roles.")
            color = bst.parse_color(colour) if colour else 0
            if colour and not cfg["allow_color"]:
                raise bst.BoosterError("Choosing a role colour is turned off on this server.")
            created = await bst.create_custom(ctx.guild, ctx.author, cfg, name, color)
            return f"Your role {created.mention} is ready."
        await self._run(ctx, work)

    @b_role.command(name="name", aliases=["rename"], help="Rename your role.")
    async def br_name(self, ctx: commands.Context, *, name: str):
        async def work():
            cfg, saved, role = await self._mine(ctx)
            await bst.edit_custom(ctx.guild, ctx.author, cfg, role, saved, name=name)
            return f"Your role is now **{role.name}**."
        await self._run(ctx, work)

    @b_role.command(name="color", aliases=["colour"], help="Change your role colour.")
    async def br_color(self, ctx: commands.Context, colour: str):
        async def work():
            cfg, saved, role = await self._mine(ctx)
            await bst.edit_custom(ctx.guild, ctx.author, cfg, role, saved, color=bst.parse_color(colour))
            return "Your role colour was updated."
        await self._run(ctx, work)

    @b_role.command(name="icon", help="Set your role icon from an attached image, or `remove`.")
    async def br_icon(self, ctx: commands.Context, action: Optional[str] = None):
        async def work():
            cfg, saved, role = await self._mine(ctx)
            if action and action.lower() == "remove":
                await bst.edit_custom(ctx.guild, ctx.author, cfg, role, saved, clear_icon=True)
                return "Your role icon was removed."
            if not ctx.message.attachments:
                raise bst.BoosterError("Attach a PNG or JPG image to the message, or use `booster role icon remove`.")
            attachment = ctx.message.attachments[0]
            if not (attachment.content_type or "").startswith(("image/png", "image/jpeg")):
                raise bst.BoosterError("The icon must be a PNG or JPG image.")
            if attachment.size > config.BOOSTER_ICON_MAX_BYTES:
                raise bst.BoosterError("The icon must be under 256 KB.")
            await bst.edit_custom(ctx.guild, ctx.author, cfg, role, saved, icon=await attachment.read())
            return "Your role icon was updated."
        await self._run(ctx, work)

    @b_role.command(name="hoist", aliases=["display"], help="Show your role separately in the member list. Usage: booster role hoist <on|off>")
    async def br_hoist(self, ctx: commands.Context, state: str):
        async def work():
            cfg, saved, role = await self._mine(ctx)
            value = bool(_flag(state))
            await bst.edit_custom(ctx.guild, ctx.author, cfg, role, saved, hoist=value)
            return "Your role is now shown separately." if value else "Your role is no longer shown separately."
        await self._run(ctx, work)

    @b_role.command(name="perms", aliases=["permissions"], help="Pick the permissions your role has. Usage: booster role perms [names]")
    async def br_perms(self, ctx: commands.Context, *names: str):
        async def work():
            cfg, saved, role = await self._mine(ctx)
            if not names:
                allowed = ", ".join(f"`{n}`" for n in config.BOOSTER_SAFE_PERMS)
                have = ", ".join(f"`{n}`" for n in bst.perm_names(role.permissions.value)) or "none"
                raise bst.BoosterError(f"Current: {have}\nAvailable: {allowed}\nUse `booster role perms <names>` to set them, or `booster role perms none`.")
            chosen = [] if names[0].lower() == "none" else [n.lower() for n in names]
            unknown = [n for n in chosen if n not in config.BOOSTER_SAFE_PERMS]
            if unknown:
                raise bst.BoosterError("Not available: " + ", ".join(f"`{n}`" for n in unknown))
            await bst.edit_custom(ctx.guild, ctx.author, cfg, role, saved, perms=chosen)
            return "Your role permissions were updated."
        await self._run(ctx, work)

    @b_role.command(name="delete", aliases=["remove"], help="Delete your custom role.")
    async def br_delete(self, ctx: commands.Context):
        async def work():
            saved, role = await bst.get_custom(ctx.guild, ctx.author.id)
            if saved is None or role is None:
                raise bst.BoosterError("You do not have a custom role.")
            await bst.delete_custom(ctx.guild, ctx.author.id, keep_settings=False)
            return "Your custom role was deleted."
        await self._run(ctx, work)


async def setup(bot: commands.Bot):
    await bot.add_cog(Booster(bot))
