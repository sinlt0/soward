import asyncio
import datetime
import time
import uuid
from typing import Optional, Union

import discord
from discord.ext import commands, tasks

import config
from utils import cases, db, emoji_manager
from utils.checks import has_guild_permission
from utils.colors import NEUTRAL, SUCCESS
from utils.components import ConfirmLayout, error_layout, footer_block, info_layout, success_layout
from utils.converters import DurationConverter, MemberOrIdConverter, format_duration
from utils.events_bus import LOG_EVENT, MOD_ACTION, bus


def _case_body(fields: dict) -> str:
    lines = []
    for label, value in fields.items():
        if value is not None:
            lines.append(f"**{label}:** {value}")
    return "\n".join(lines)


def _mod_layout(title: str, fields: dict, *, color: int = None) -> discord.ui.LayoutView:
    from utils.colors import SUCCESS
    from utils.components import footer_block
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color or SUCCESS)
    container.add_item(discord.ui.TextDisplay(f"## {title}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(_case_body(fields)))
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


def _humanize_perm(name: str) -> str:
    return name.replace("_", " ").title()


def _all_permission_nodes() -> list[str]:
    return sorted(discord.Permissions.VALID_FLAGS.keys())


PERM_PAGE_SIZE = 10


class PermissionListPageRow(discord.ui.ActionRow):
    def __init__(self, layout: "PermissionListLayout"):
        super().__init__(
            discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary, custom_id="fakeperm:plist:prev"),
            discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="fakeperm:plist:next"),
        )
        self.layout_ref = layout
        self.children[0].callback = self._prev
        self.children[1].callback = self._next

    async def _prev(self, interaction: discord.Interaction):
        self.layout_ref.page = max(0, self.layout_ref.page - 1)
        self.layout_ref._render()
        await interaction.response.edit_message(view=self.layout_ref)

    async def _next(self, interaction: discord.Interaction):
        self.layout_ref.page = min(self.layout_ref.max_page, self.layout_ref.page + 1)
        self.layout_ref._render()
        await interaction.response.edit_message(view=self.layout_ref)


class PermissionListLayout(discord.ui.LayoutView):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.nodes = _all_permission_nodes()
        self.page = 0
        self.max_page = max(0, (len(self.nodes) - 1) // PERM_PAGE_SIZE)

        e = emoji_manager.get
        self.container = discord.ui.Container(accent_color=SUCCESS)
        self.header = discord.ui.TextDisplay(f"## {e('fakeperm')} Available Permission Nodes")
        self.container.add_item(self.header)
        self.container.add_item(discord.ui.Separator())
        self.body = discord.ui.TextDisplay("")
        self.container.add_item(self.body)
        self.container.add_item(discord.ui.Separator())
        self.container.add_item(PermissionListPageRow(self))
        self.container.add_item(discord.ui.Separator())
        for item in footer_block():
            self.container.add_item(item)
        self.add_item(self.container)
        self._render()

    def _render(self):
        start = self.page * PERM_PAGE_SIZE
        page_nodes = self.nodes[start:start + PERM_PAGE_SIZE]
        lines = [f"`{n}` — {_humanize_perm(n)}" for n in page_nodes]
        lines.append("")
        lines.append(f"-# Page {self.page + 1}/{self.max_page + 1} · {len(self.nodes)} total nodes")
        lines.append("-# Use `fakeperm grant @target <node>` or run `fakeperm setup` for a guided flow.")
        self.body.content = "\n".join(lines)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True


class FakePermTargetTypeRow(discord.ui.ActionRow):
    def __init__(self, wizard: "FakePermSetupLayout"):
        super().__init__(
            discord.ui.Button(label="Member", style=discord.ButtonStyle.primary, custom_id="fakeperm:setup:member"),
            discord.ui.Button(label="Role", style=discord.ButtonStyle.primary, custom_id="fakeperm:setup:role"),
        )
        self.wizard = wizard
        self.children[0].callback = self._pick_member
        self.children[1].callback = self._pick_role

    async def _pick_member(self, interaction: discord.Interaction):
        self.wizard.target_type = "user"
        await self.wizard._show_target_select(interaction)

    async def _pick_role(self, interaction: discord.Interaction):
        self.wizard.target_type = "role"
        await self.wizard._show_target_select(interaction)


class FakePermMemberSelectRow(discord.ui.ActionRow):
    def __init__(self, wizard: "FakePermSetupLayout"):
        super().__init__(discord.ui.UserSelect(placeholder="Choose a member..."))
        self.wizard = wizard
        self.children[0].callback = self._on_select

    async def _on_select(self, interaction: discord.Interaction):
        self.wizard.target_id = self.children[0].values[0].id
        self.wizard.target_display = self.children[0].values[0].mention
        await self.wizard._show_permission_select(interaction)


class FakePermRoleSelectRow(discord.ui.ActionRow):
    def __init__(self, wizard: "FakePermSetupLayout"):
        super().__init__(discord.ui.RoleSelect(placeholder="Choose a role..."))
        self.wizard = wizard
        self.children[0].callback = self._on_select

    async def _on_select(self, interaction: discord.Interaction):
        self.wizard.target_id = self.children[0].values[0].id
        self.wizard.target_display = self.children[0].values[0].mention
        await self.wizard._show_permission_select(interaction)


class FakePermPermissionSelectRow(discord.ui.ActionRow):
    def __init__(self, wizard: "FakePermSetupLayout", page: int = 0):
        nodes = _all_permission_nodes()
        page_size = 24
        start = page * page_size
        page_nodes = nodes[start:start + page_size]
        options = [discord.SelectOption(label=n, description=_humanize_perm(n)[:100], value=n) for n in page_nodes]
        options.append(discord.SelectOption(label="administrator (bypass all)", value="administrator", emoji="⭐"))
        super().__init__(discord.ui.Select(placeholder="Choose a permission node...", options=options[:25]))
        self.wizard = wizard
        self.children[0].callback = self._on_select

    async def _on_select(self, interaction: discord.Interaction):
        self.wizard.node = self.children[0].values[0]
        await self.wizard._show_action_confirm(interaction)


class FakePermActionRow(discord.ui.ActionRow):
    def __init__(self, wizard: "FakePermSetupLayout"):
        super().__init__(
            discord.ui.Button(label="Grant", style=discord.ButtonStyle.success, custom_id="fakeperm:setup:grant"),
            discord.ui.Button(label="Revoke", style=discord.ButtonStyle.danger, custom_id="fakeperm:setup:revoke"),
        )
        self.wizard = wizard
        self.children[0].callback = self._grant
        self.children[1].callback = self._revoke

    async def _grant(self, interaction: discord.Interaction):
        await self.wizard._finish(interaction, "grant")

    async def _revoke(self, interaction: discord.Interaction):
        await self.wizard._finish(interaction, "revoke")


class FakePermSetupLayout(discord.ui.LayoutView):
    def __init__(self, author_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.guild_id = guild_id
        self.target_type: Optional[str] = None
        self.target_id: Optional[int] = None
        self.target_display: Optional[str] = None
        self.node: Optional[str] = None
        self._build_step1()

    def _new_container(self, title: str) -> discord.ui.Container:
        e = emoji_manager.get
        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(f"## {e('fakeperm')} Fake Permission Setup\n{title}"))
        container.add_item(discord.ui.Separator())
        return container

    def _finish_container(self, container: discord.ui.Container):
        container.add_item(discord.ui.Separator())
        for item in footer_block():
            container.add_item(item)
        self.clear_items()
        self.add_item(container)

    def _build_step1(self):
        container = self._new_container("**Step 1 of 4** — Is this for a member or a role?")
        container.add_item(FakePermTargetTypeRow(self))
        self._finish_container(container)

    async def _show_target_select(self, interaction: discord.Interaction):
        label = "member" if self.target_type == "user" else "role"
        container = self._new_container(f"**Step 2 of 4** — Choose the {label} to grant or revoke a permission for.")
        if self.target_type == "user":
            container.add_item(FakePermMemberSelectRow(self))
        else:
            container.add_item(FakePermRoleSelectRow(self))
        self._finish_container(container)
        await interaction.response.edit_message(view=self)

    async def _show_permission_select(self, interaction: discord.Interaction):
        container = self._new_container(
            f"**Step 3 of 4** — Target: {self.target_display}\nNow choose the permission node."
        )
        container.add_item(FakePermPermissionSelectRow(self))
        container.add_item(discord.ui.TextDisplay("-# Run `fakeperm plist` first if you need the full list with descriptions."))
        self._finish_container(container)
        await interaction.response.edit_message(view=self)

    async def _show_action_confirm(self, interaction: discord.Interaction):
        container = self._new_container(
            f"**Step 4 of 4** — Target: {self.target_display}\nPermission: `{self.node}`\n\nGrant or revoke this permission?"
        )
        container.add_item(FakePermActionRow(self))
        self._finish_container(container)
        await interaction.response.edit_message(view=self)

    async def _finish(self, interaction: discord.Interaction, action: str):
        e = emoji_manager.get
        if action == "grant":
            await db.raw_execute(
                "INSERT OR IGNORE INTO fakeperm_grants (guild_id, target_id, target_type, node, granted_by, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (self.guild_id, self.target_id, self.target_type, self.node, interaction.user.id, time.time()),
            )
            body = f"Granted `{self.node}` to {self.target_display}."
        else:
            await db.raw_execute(
                "DELETE FROM fakeperm_grants WHERE guild_id=? AND target_id=? AND target_type=? AND node=?",
                (self.guild_id, self.target_id, self.target_type, self.node),
            )
            body = f"Revoked `{self.node}` from {self.target_display}."

        container = discord.ui.Container(accent_color=SUCCESS)
        container.add_item(discord.ui.TextDisplay(f"## {e('check')} Done\n{body}"))
        container.add_item(discord.ui.Separator())
        for item in footer_block():
            container.add_item(item)
        self.clear_items()
        self.add_item(container)
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This setup wizard is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True


class Moderation(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tempban_watcher.start()

    def cog_unload(self):
        self.tempban_watcher.cancel()

    async def _log(self, guild: discord.Guild, action: str, **kwargs):
        await bus.publish(LOG_EVENT, guild_id=guild.id, action=action, **kwargs)
        await bus.publish(MOD_ACTION, guild_id=guild.id, action=action, **kwargs)

    def _can_act_on(self, ctx: commands.Context, target: discord.Member) -> bool:
        if ctx.author.id in config.ALL_PRIVILEGED_IDS:
            return True
        return target.top_role < ctx.author.top_role

    @tasks.loop(minutes=1)
    async def tempban_watcher(self):
        now = time.time()
        rows = await db.raw_fetch("SELECT * FROM temp_bans WHERE unban_at <= ?", (now,))
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                continue
            try:
                user = await self.bot.fetch_user(row["user_id"])
                await guild.unban(user, reason="Temp-ban duration expired")
                case_id = await cases.create_mod_case(guild.id, "unban", row["user_id"], self.bot.user.id, "Temp-ban expired")
                await self._log(guild, "unban", user_id=row["user_id"], moderator_id=self.bot.user.id, reason="Temp-ban expired", case_id=case_id)
            except discord.HTTPException:
                pass
            await db.raw_execute("DELETE FROM temp_bans WHERE guild_id=? AND user_id=?", (row["guild_id"], row["user_id"]))

    @tempban_watcher.before_loop
    async def _before_tempban_watcher(self):
        await self.bot.wait_until_ready()

    @commands.command(name="ban", help="Ban a member from the server.")
    @has_guild_permission("ban_members")
    @commands.guild_only()
    async def ban(self, ctx: commands.Context, target: MemberOrIdConverter, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        if isinstance(target, discord.Member):
            if not self._can_act_on(ctx, target):
                return await ctx.send(view=error_layout("Permission Denied", "You cannot ban someone with a higher or equal role."))
            await target.ban(reason=f"{ctx.author} | {reason}")
            user_id = target.id
            display = str(target)
        else:
            await ctx.guild.ban(discord.Object(id=target), reason=f"{ctx.author} | {reason}")
            user_id = target
            display = str(target)

        case_id = await cases.create_mod_case(ctx.guild.id, "ban", user_id, ctx.author.id, reason)
        await ctx.send(view=_mod_layout(f"{e('ban')} Member Banned", {
            "User": display, "Moderator": ctx.author.mention, "Reason": reason, "Case": f"`{case_id}`",
        }))
        await self._log(ctx.guild, "ban", user_id=user_id, moderator_id=ctx.author.id, reason=reason, case_id=case_id)

    @commands.command(name="tempban", help="Ban a member for a set duration, auto-unbanning when it expires.")
    @has_guild_permission("ban_members")
    @commands.guild_only()
    async def tempban(self, ctx: commands.Context, target: MemberOrIdConverter, duration: DurationConverter, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        if isinstance(target, discord.Member):
            if not self._can_act_on(ctx, target):
                return await ctx.send(view=error_layout("Permission Denied", "You cannot ban someone with a higher or equal role."))
            await target.ban(reason=f"{ctx.author} | {reason}")
            user_id = target.id
            display = str(target)
        else:
            await ctx.guild.ban(discord.Object(id=target), reason=f"{ctx.author} | {reason}")
            user_id = target
            display = str(target)

        unban_at = time.time() + duration
        await db.raw_execute(
            "INSERT INTO temp_bans (guild_id, user_id, unban_at, reason, moderator_id) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET unban_at=excluded.unban_at, reason=excluded.reason, moderator_id=excluded.moderator_id",
            (ctx.guild.id, user_id, unban_at, reason, ctx.author.id),
        )
        case_id = await cases.create_mod_case(ctx.guild.id, "tempban", user_id, ctx.author.id, reason, duration)
        await ctx.send(view=_mod_layout(f"{e('ban')} Member Temp-Banned", {
            "User": display, "Moderator": ctx.author.mention, "Duration": format_duration(duration),
            "Unbans": f"<t:{int(unban_at)}:R>", "Reason": reason, "Case": f"`{case_id}`",
        }))
        await self._log(ctx.guild, "ban", user_id=user_id, moderator_id=ctx.author.id, reason=f"{reason} (temp — {format_duration(duration)})", case_id=case_id)

    @commands.command(name="softban", help="Ban then immediately unban a member, deleting their recent messages.")
    @has_guild_permission("ban_members")
    @commands.guild_only()
    async def softban(self, ctx: commands.Context, member: discord.Member, delete_days: int = 1, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        if not self._can_act_on(ctx, member):
            return await ctx.send(view=error_layout("Permission Denied", "You cannot softban someone with a higher or equal role."))
        delete_days = max(0, min(7, delete_days))
        await member.ban(reason=f"Softban: {ctx.author} | {reason}", delete_message_days=delete_days)
        await ctx.guild.unban(member, reason="Softban auto-unban")
        case_id = await cases.create_mod_case(ctx.guild.id, "softban", member.id, ctx.author.id, reason)
        await ctx.send(view=_mod_layout(f"{e('ban')} Member Softbanned", {
            "User": str(member), "Moderator": ctx.author.mention, "Messages deleted": f"{delete_days} day(s)",
            "Reason": reason, "Case": f"`{case_id}`",
        }))
        await self._log(ctx.guild, "softban", user_id=member.id, moderator_id=ctx.author.id, reason=reason, case_id=case_id)

    @commands.command(name="unban", help="Unban a user by their ID.")
    @has_guild_permission("ban_members")
    @commands.guild_only()
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=f"{ctx.author} | {reason}")
        except discord.NotFound:
            return await ctx.send(view=error_layout("Not Found", "That user is not banned."))

        await db.raw_execute("DELETE FROM temp_bans WHERE guild_id=? AND user_id=?", (ctx.guild.id, user_id))
        case_id = await cases.create_mod_case(ctx.guild.id, "unban", user_id, ctx.author.id, reason)
        await ctx.send(view=_mod_layout(f"{e('unban')} Member Unbanned", {
            "User": str(user), "Moderator": ctx.author.mention, "Reason": reason, "Case": f"`{case_id}`",
        }))
        await self._log(ctx.guild, "unban", user_id=user_id, moderator_id=ctx.author.id, reason=reason, case_id=case_id)

    @commands.command(name="kick", help="Kick a member from the server.")
    @has_guild_permission("kick_members")
    @commands.guild_only()
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        if not self._can_act_on(ctx, member):
            return await ctx.send(view=error_layout("Permission Denied", "You cannot kick someone with a higher or equal role."))

        await member.kick(reason=f"{ctx.author} | {reason}")
        case_id = await cases.create_mod_case(ctx.guild.id, "kick", member.id, ctx.author.id, reason)
        await ctx.send(view=_mod_layout(f"{e('kick')} Member Kicked", {
            "User": str(member), "Moderator": ctx.author.mention, "Reason": reason, "Case": f"`{case_id}`",
        }))
        await self._log(ctx.guild, "kick", user_id=member.id, moderator_id=ctx.author.id, reason=reason, case_id=case_id)

    @commands.command(name="masskick", help="Kick multiple members at once by mentioning or listing their IDs.")
    @has_guild_permission("kick_members")
    @commands.guild_only()
    async def masskick(self, ctx: commands.Context, members: commands.Greedy[discord.Member], *, reason: str = "No reason provided"):
        e = emoji_manager.get
        if not members:
            return await ctx.send(view=error_layout("No Targets", "Mention at least one member to kick."))

        confirm = ConfirmLayout(
            f"{e('kick')} Confirm mass kick",
            f"You are about to kick **{len(members)}** member(s).\n**Reason:** {reason}",
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "Mass kick cancelled."))

        kicked, failed = [], []
        for member in members:
            if not self._can_act_on(ctx, member):
                failed.append(member)
                continue
            try:
                await member.kick(reason=f"{ctx.author} | Mass kick: {reason}")
                case_id = await cases.create_mod_case(ctx.guild.id, "kick", member.id, ctx.author.id, reason)
                await self._log(ctx.guild, "kick", user_id=member.id, moderator_id=ctx.author.id, reason=reason, case_id=case_id)
                kicked.append(member)
            except discord.HTTPException:
                failed.append(member)

        await msg.edit(view=_mod_layout(f"{e('kick')} Mass Kick Complete", {
            "Kicked": f"{len(kicked)} member(s)",
            "Failed": f"{len(failed)} member(s)" if failed else None,
            "Reason": reason,
        }))

    @commands.command(name="mute", aliases=["timeout"], help="Timeout a member for a given duration.")
    @has_guild_permission("moderate_members")
    @commands.guild_only()
    async def mute(self, ctx: commands.Context, member: discord.Member, duration: DurationConverter, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        if not self._can_act_on(ctx, member):
            return await ctx.send(view=error_layout("Permission Denied", "You cannot mute someone with a higher or equal role."))
        until = discord.utils.utcnow() + datetime.timedelta(seconds=duration)
        await member.timeout(until, reason=f"{ctx.author} | {reason}")
        case_id = await cases.create_mod_case(ctx.guild.id, "mute", member.id, ctx.author.id, reason, duration)
        await ctx.send(view=_mod_layout(f"{e('mute')} Member Muted", {
            "User": str(member), "Moderator": ctx.author.mention, "Duration": format_duration(duration),
            "Reason": reason, "Case": f"`{case_id}`",
        }))
        await self._log(ctx.guild, "mute", user_id=member.id, moderator_id=ctx.author.id, reason=reason, duration=duration, case_id=case_id)

    @commands.command(name="unmute", help="Remove a member's timeout.")
    @has_guild_permission("moderate_members")
    @commands.guild_only()
    async def unmute(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        await member.timeout(None, reason=f"{ctx.author} | {reason}")
        case_id = await cases.create_mod_case(ctx.guild.id, "unmute", member.id, ctx.author.id, reason)
        await ctx.send(view=_mod_layout(f"{e('unmute')} Member Unmuted", {
            "User": str(member), "Moderator": ctx.author.mention, "Reason": reason, "Case": f"`{case_id}`",
        }))
        await self._log(ctx.guild, "unmute", user_id=member.id, moderator_id=ctx.author.id, reason=reason, case_id=case_id)

    @commands.command(name="warn", help="Issue a warning to a member.")
    @has_guild_permission("manage_messages", "warn")
    @commands.guild_only()
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        case_id = await cases.create_warn(ctx.guild.id, member.id, ctx.author.id, reason)
        await ctx.send(view=_mod_layout(f"{e('warn')} Warning Issued", {
            "User": str(member), "Moderator": ctx.author.mention, "Reason": reason, "Case": f"`{case_id}`",
        }))
        try:
            await member.send(view=info_layout(
                f"{e('warn')} You were warned in {ctx.guild.name}",
                f"**Reason:** {reason}\n**Case:** `{case_id}`",
            ))
        except discord.HTTPException:
            pass
        await self._log(ctx.guild, "warn", user_id=member.id, moderator_id=ctx.author.id, reason=reason, case_id=case_id)

    @commands.command(name="warnings", aliases=["warns"], help="View the warning history for a member.")
    @has_guild_permission("manage_messages")
    @commands.guild_only()
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        e = emoji_manager.get
        warns = await cases.get_warns(ctx.guild.id, member.id)
        if not warns:
            return await ctx.send(view=info_layout(f"{e('history')} No Warnings", f"{member.mention} has no warnings."))

        lines = [
            f"`{w['case_id']}` — <t:{int(w['created_at'])}:R>\n{e('warn')} **Reason:** {w['reason'] or 'None'}"
            for w in warns[:15]
        ]
        if len(warns) > 15:
            lines.append(f"...and {len(warns) - 15} more")
        await ctx.send(view=info_layout(f"{e('history')} Warnings for {member}", "\n\n".join(lines)))

    @commands.command(name="delwarn", help="Delete a warning by its case ID.")
    @has_guild_permission("manage_messages")
    @commands.guild_only()
    async def delwarn(self, ctx: commands.Context, case_id: str):
        e = emoji_manager.get
        deleted = await cases.delete_warn(case_id.upper(), ctx.guild.id)
        if deleted:
            await ctx.send(view=success_layout(f"{e('check')} Warning Removed", f"Case `{case_id.upper()}` has been deleted."))
        else:
            await ctx.send(view=error_layout(f"{e('cross')} Not Found", f"No warning with case ID `{case_id.upper()}` found."))

    @commands.command(name="warnclear", help="Clear all warnings for a member.")
    @has_guild_permission("manage_messages")
    @commands.guild_only()
    async def warnclear(self, ctx: commands.Context, member: discord.Member):
        e = emoji_manager.get
        warns = await cases.get_warns(ctx.guild.id, member.id)
        if not warns:
            return await ctx.send(view=info_layout(f"{e('history')} No Warnings", f"{member.mention} has no warnings to clear."))

        confirm = ConfirmLayout(
            f"{e('warn')} Confirm clear warnings",
            f"Clear all **{len(warns)}** warning(s) for {member.mention}? This cannot be undone.",
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "Warnings were not cleared."))

        for w in warns:
            await cases.delete_warn(w["case_id"], ctx.guild.id)
        await msg.edit(view=success_layout(f"{e('check')} Warnings Cleared", f"Removed **{len(warns)}** warning(s) for {member.mention}."))

    @commands.command(name="note", help="Add a private moderator note to a member's profile.")
    @has_guild_permission("manage_messages")
    @commands.guild_only()
    async def note(self, ctx: commands.Context, member: discord.Member, *, text: str):
        e = emoji_manager.get
        note_id = str(uuid.uuid4())[:8].upper()
        await db.raw_execute(
            "INSERT INTO mod_notes (note_id, guild_id, user_id, moderator_id, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (note_id, ctx.guild.id, member.id, ctx.author.id, text, time.time()),
        )
        await ctx.send(view=success_layout(f"{e('check')} Note Added", f"Note `{note_id}` added for {member.mention}."))

    @commands.command(name="notes", help="View private moderator notes for a member.")
    @has_guild_permission("manage_messages")
    @commands.guild_only()
    async def notes(self, ctx: commands.Context, member: discord.Member):
        e = emoji_manager.get
        rows = await db.raw_fetch(
            "SELECT * FROM mod_notes WHERE guild_id=? AND user_id=? ORDER BY created_at DESC",
            (ctx.guild.id, member.id),
        )
        if not rows:
            return await ctx.send(view=info_layout(f"{e('history')} No Notes", f"No notes exist for {member.mention}."))
        lines = [
            f"`{r['note_id']}` — <@{r['moderator_id']}> · <t:{int(r['created_at'])}:R>\n{r['note']}"
            for r in rows[:10]
        ]
        await ctx.send(view=info_layout(f"{e('history')} Notes for {member}", "\n\n".join(lines)))

    @commands.command(name="purge", aliases=["clear"], help="Bulk delete messages from the current channel.")
    @has_guild_permission("manage_messages")
    @commands.guild_only()
    async def purge(self, ctx: commands.Context, amount: int, member: Optional[discord.Member] = None):
        e = emoji_manager.get
        if amount < 1 or amount > 1000:
            return await ctx.send(view=error_layout("Invalid Amount", "Amount must be between 1 and 1000."))

        await ctx.message.delete()
        check = (lambda m: m.author == member) if member else (lambda m: True)
        deleted = await ctx.channel.purge(limit=amount, check=check)
        msg = await ctx.send(view=success_layout(f"{e('purge')} Messages Purged", f"Deleted **{len(deleted)}** messages."))
        await asyncio.sleep(4)
        try:
            await msg.delete()
        except discord.HTTPException:
            pass
        await self._log(ctx.guild, "purge", user_id=ctx.author.id, moderator_id=ctx.author.id,
                        reason=f"Purged {len(deleted)} messages" + (f" from {member}" if member else ""), case_id="N/A")

    @commands.command(name="purgebots", help="Bulk delete recent messages sent by bots.")
    @has_guild_permission("manage_messages")
    @commands.guild_only()
    async def purgebots(self, ctx: commands.Context, amount: int = 50):
        e = emoji_manager.get
        amount = max(1, min(1000, amount))
        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author.bot)
        msg = await ctx.send(view=success_layout(f"{e('purge')} Bot Messages Purged", f"Deleted **{len(deleted)}** bot messages."))
        await asyncio.sleep(4)
        try:
            await msg.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="lockdown", aliases=["lock"], help="Prevent members from sending messages in a channel.")
    @has_guild_permission("manage_channels")
    @commands.guild_only()
    async def lockdown(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author} | {reason}")
        await ctx.send(view=_mod_layout(f"{e('lock')} Channel Locked", {
            "Channel": channel.mention, "Moderator": ctx.author.mention, "Reason": reason,
        }))
        await self._log(ctx.guild, "lockdown", user_id=ctx.author.id, moderator_id=ctx.author.id, reason=f"{reason} ({channel.name})", case_id="N/A")

    @commands.command(name="lockdownall", help="Lock every text channel in the server.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def lockdownall(self, ctx: commands.Context, *, reason: str = "Server lockdown"):
        e = emoji_manager.get
        confirm = ConfirmLayout(
            f"{e('lock')} Confirm server-wide lockdown",
            f"This will lock **every text channel** in the server.\n**Reason:** {reason}",
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "Server-wide lockdown cancelled."))

        locked = 0
        for channel in ctx.guild.text_channels:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            if overwrite.send_messages is False:
                continue
            overwrite.send_messages = False
            try:
                await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author} | {reason}")
                locked += 1
            except discord.HTTPException:
                pass

        await msg.edit(view=success_layout(f"{e('lock')} Server Locked", f"Locked **{locked}** channel(s).\n**Reason:** {reason}"))
        await self._log(ctx.guild, "lockdown", user_id=ctx.author.id, moderator_id=ctx.author.id, reason=f"Server-wide: {reason}", case_id="N/A")

    @commands.command(name="unlock", help="Restore send permissions to a channel.")
    @has_guild_permission("manage_channels")
    @commands.guild_only()
    async def unlock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None, *, reason: str = "No reason provided"):
        e = emoji_manager.get
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author} | {reason}")
        await ctx.send(view=_mod_layout(f"{e('unlock')} Channel Unlocked", {
            "Channel": channel.mention, "Moderator": ctx.author.mention, "Reason": reason,
        }))
        await self._log(ctx.guild, "unlock", user_id=ctx.author.id, moderator_id=ctx.author.id, reason=f"{reason} ({channel.name})", case_id="N/A")

    @commands.command(name="unlockall", help="Unlock every text channel in the server.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def unlockall(self, ctx: commands.Context, *, reason: str = "Server lockdown lifted"):
        e = emoji_manager.get
        unlocked = 0
        for channel in ctx.guild.text_channels:
            overwrite = channel.overwrites_for(ctx.guild.default_role)
            if overwrite.send_messages is not False:
                continue
            overwrite.send_messages = None
            try:
                await channel.set_permissions(ctx.guild.default_role, overwrite=overwrite, reason=f"{ctx.author} | {reason}")
                unlocked += 1
            except discord.HTTPException:
                pass

        await ctx.send(view=success_layout(f"{e('unlock')} Server Unlocked", f"Unlocked **{unlocked}** channel(s).\n**Reason:** {reason}"))
        await self._log(ctx.guild, "unlock", user_id=ctx.author.id, moderator_id=ctx.author.id, reason=f"Server-wide: {reason}", case_id="N/A")

    @commands.command(name="slowmode", help="Set the slowmode delay for a channel.")
    @has_guild_permission("manage_channels")
    @commands.guild_only()
    async def slowmode(self, ctx: commands.Context, seconds: int, channel: Optional[discord.TextChannel] = None):
        e = emoji_manager.get
        channel = channel or ctx.channel
        if seconds < 0 or seconds > 21600:
            return await ctx.send(view=error_layout("Invalid", "Slowmode must be between 0 and 21600 seconds."))
        await channel.edit(slowmode_delay=seconds)
        label = f"{seconds}s" if seconds > 0 else "disabled"
        await ctx.send(view=success_layout(f"{e('slowmode')} Slowmode Set", f"Slowmode in {channel.mention} set to **{label}**."))
        await self._log(ctx.guild, "slowmode", user_id=ctx.author.id, moderator_id=ctx.author.id, reason=f"{channel.name} → {label}", case_id="N/A")

    @commands.command(name="nickname", aliases=["nick"], help="Change or reset a member's nickname.")
    @has_guild_permission("manage_nicknames")
    @commands.guild_only()
    async def nickname(self, ctx: commands.Context, member: discord.Member, *, new_nick: Optional[str] = None):
        e = emoji_manager.get
        old_nick = member.display_name
        await member.edit(nick=new_nick, reason=f"Changed by {ctx.author}")
        await ctx.send(view=_mod_layout(f"{e('check')} Nickname Updated", {
            "User": member.mention, "Before": old_nick, "After": new_nick or member.name, "Moderator": ctx.author.mention,
        }))

    @commands.group(name="role", invoke_without_command=True, help="Add or remove a role from a member.")
    @has_guild_permission("manage_roles")
    @commands.guild_only()
    async def role_group(self, ctx: commands.Context):
        e = emoji_manager.get
        await ctx.send(view=info_layout(f"{e('info')} Role Management", "Use `role add @member @role` or `role remove @member @role`."))

    @role_group.command(name="add", help="Add a role to a member.")
    @has_guild_permission("manage_roles")
    async def role_add(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        e = emoji_manager.get
        if role >= ctx.guild.me.top_role:
            return await ctx.send(view=error_layout("Cannot Assign", "That role is higher than or equal to my top role."))
        if role in member.roles:
            return await ctx.send(view=error_layout("Already Has Role", f"{member.mention} already has {role.mention}."))
        await member.add_roles(role, reason=f"Added by {ctx.author}")
        await ctx.send(view=success_layout(f"{e('check')} Role Added", f"Gave {role.mention} to {member.mention}."))

    @role_group.command(name="remove", help="Remove a role from a member.")
    @has_guild_permission("manage_roles")
    async def role_remove(self, ctx: commands.Context, member: discord.Member, role: discord.Role):
        e = emoji_manager.get
        if role not in member.roles:
            return await ctx.send(view=error_layout("Doesn't Have Role", f"{member.mention} doesn't have {role.mention}."))
        await member.remove_roles(role, reason=f"Removed by {ctx.author}")
        await ctx.send(view=success_layout(f"{e('check')} Role Removed", f"Removed {role.mention} from {member.mention}."))

    @commands.command(name="cases", help="View moderation case history.")
    @has_guild_permission("manage_messages")
    @commands.guild_only()
    async def mod_cases_cmd(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        e = emoji_manager.get
        all_cases = await cases.get_mod_cases(ctx.guild.id, member.id if member else None)
        if not all_cases:
            target = member.mention if member else "this server"
            return await ctx.send(view=info_layout(f"{e('case')} No Cases", f"No mod cases found for {target}."))

        lines = [
            f"`{c['case_id']}` **{c['action'].upper()}** — <t:{int(c['created_at'])}:R>\n"
            f"**User:** <@{c['user_id']}> | **Mod:** <@{c['moderator_id']}>\n"
            f"**Reason:** {c['reason'] or 'None'}"
            for c in all_cases[:10]
        ]
        if len(all_cases) > 10:
            lines.append(f"...and {len(all_cases) - 10} more")
        title = f"{e('history')} Cases" + (f" for {member}" if member else "")
        await ctx.send(view=info_layout(title, "\n\n".join(lines)))

    @commands.command(name="modstats", help="View moderation activity stats for a staff member.")
    @has_guild_permission("manage_messages")
    @commands.guild_only()
    async def modstats(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        e = emoji_manager.get
        member = member or ctx.author
        rows = await db.raw_fetch(
            "SELECT action, COUNT(*) as cnt FROM mod_cases WHERE guild_id=? AND moderator_id=? GROUP BY action",
            (ctx.guild.id, member.id),
        )
        if not rows:
            return await ctx.send(view=info_layout(f"{e('history')} No Activity", f"{member.mention} has no moderation actions logged."))
        lines = [f"**{r['action'].title()}:** {r['cnt']}" for r in rows]
        total = sum(r["cnt"] for r in rows)
        await ctx.send(view=info_layout(f"{e('history')} Mod Stats — {member}", "\n".join(lines) + f"\n\n**Total actions:** {total}"))

    @commands.command(name="fakeperm", help="Grant or revoke a bot-specific permission node.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def fakeperm(self, ctx: commands.Context, action: str, target: Union[discord.Member, discord.Role], node: str):
        e = emoji_manager.get
        action = action.lower()
        target_type = "user" if isinstance(target, discord.Member) else "role"
        target_id = target.id

        if action == "grant":
            await db.raw_execute(
                "INSERT OR IGNORE INTO fakeperm_grants (guild_id, target_id, target_type, node, granted_by, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (ctx.guild.id, target_id, target_type, node, ctx.author.id, time.time()),
            )
            await ctx.send(view=success_layout(f"{e('fakeperm')} Fake Permission Granted", f"Granted `{node}` to {target.mention}."))
        elif action == "revoke":
            await db.raw_execute(
                "DELETE FROM fakeperm_grants WHERE guild_id=? AND target_id=? AND target_type=? AND node=?",
                (ctx.guild.id, target_id, target_type, node),
            )
            await ctx.send(view=success_layout(f"{e('fakeperm')} Fake Permission Revoked", f"Revoked `{node}` from {target.mention}."))
        elif action == "list":
            rows = await db.raw_fetch(
                "SELECT node FROM fakeperm_grants WHERE guild_id=? AND target_id=? AND target_type=?",
                (ctx.guild.id, target_id, target_type),
            )
            if not rows:
                return await ctx.send(view=info_layout(f"{e('fakeperm')} No Permissions", f"{target.mention} has no fake permissions."))
            nodes = "\n".join(f"`{r['node']}`" for r in rows)
            await ctx.send(view=info_layout(f"{e('fakeperm')} Fake Permissions for {target}", nodes))
        else:
            await ctx.send(view=error_layout("Invalid Action", "Use `grant`, `revoke`, `list`, `plist`, or `setup`."))

    @commands.command(name="fakeperms", hidden=True)
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def fakeperm_alias(self, ctx: commands.Context, *args):
        await ctx.send(view=error_layout(
            "Command Renamed", f"Use `fakeperm` (singular) instead of `fakeperms`.\nExample: `fakeperm grant @user ban_members`"
        ))

    @commands.command(name="fakepermplist", aliases=["plist"], help="View every valid permission node that can be used with fakeperm.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def fakeperm_plist(self, ctx: commands.Context):
        await ctx.send(view=PermissionListLayout(ctx.author.id))

    @commands.command(name="fakepermsetup", aliases=["fpsetup"], help="Interactive guided setup for granting or revoking a fake permission.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def fakeperm_setup(self, ctx: commands.Context):
        await ctx.send(view=FakePermSetupLayout(ctx.author.id, ctx.guild.id))


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))