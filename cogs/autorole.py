import asyncio
from typing import Optional

import discord
from discord.ext import commands

from utils import db, emoji_manager, greeting_config, guild_settings
from utils.colors import ERROR, NEUTRAL, SUCCESS
from utils.components import ConfirmLayout, error_layout, footer_block, info_layout, success_layout
from utils.events_bus import MEMBER_VERIFIED, AUTOROLE_ASSIGN, AUTOROLE_STRIP, LOG_EVENT, bus
from utils.checks import has_guild_permission


def _layout(title: str, body: str, *, color: int = NEUTRAL) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


class AutoRoleSettingsRow(discord.ui.ActionRow):
    def __init__(self, layout: "AutoRoleOverviewLayout"):
        super().__init__(
            discord.ui.Select(
                placeholder="View a category...",
                options=[
                    discord.SelectOption(label="Human Join Roles", value="human"),
                    discord.SelectOption(label="Bot Join Roles", value="bot"),
                    discord.SelectOption(label="Verify Roles", value="verify"),
                ],
                custom_id="autorole:overview:select",
            ),
        )
        self.layout_ref = layout
        self.children[0].callback = self._on_select

    async def _on_select(self, interaction: discord.Interaction):
        view = self.layout_ref
        view.page = interaction.data["values"][0]
        await view._load()
        view._render()
        await interaction.response.edit_message(view=view)


class AutoRoleOverviewLayout(discord.ui.LayoutView):
    def __init__(self, author_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.guild_id = guild_id
        self.page = "human"
        self.body_text = ""

        e = emoji_manager.get
        self.container = discord.ui.Container(accent_color=NEUTRAL)
        self.header = discord.ui.TextDisplay(f"## {e('autorole_cat')} AutoRole")
        self.container.add_item(self.header)
        self.container.add_item(discord.ui.Separator())
        self.body = discord.ui.TextDisplay("Loading...")
        self.container.add_item(self.body)
        self.container.add_item(discord.ui.Separator())
        self.container.add_item(AutoRoleSettingsRow(self))
        self.container.add_item(discord.ui.Separator())
        for item in footer_block():
            self.container.add_item(item)
        self.add_item(self.container)

    @classmethod
    async def create(cls, author_id: int, guild_id: int) -> "AutoRoleOverviewLayout":
        view = cls(author_id, guild_id)
        await view._load()
        view._render()
        return view

    async def _load(self):
        if self.page == "human":
            roles = await guild_settings.get(self.guild_id, "autorole_human_join", [])
            self.body_text = "\n".join(f"<@&{r}>" for r in roles) or "No human join roles set.\nUse `autorole add human @role`."
        elif self.page == "bot":
            roles = await guild_settings.get(self.guild_id, "autorole_bot_join", [])
            self.body_text = "\n".join(f"<@&{r}>" for r in roles) or "No bot join roles set.\nUse `autorole add bot @role`."
        elif self.page == "verify":
            roles = await guild_settings.get(self.guild_id, "autorole_on_verify", [])
            self.body_text = "\n".join(f"<@&{r}>" for r in roles) or "No verify roles set.\nUse `autorole verifyrole @role`."

    def _render(self):
        labels = {"human": "Human Join Roles", "bot": "Bot Join Roles", "verify": "Verify Roles"}
        e = emoji_manager.get
        self.header.content = f"## {e('autorole_cat')} AutoRole — {labels[self.page]}"
        self.body.content = self.body_text

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True


class AutoRole(commands.Cog):
    category = "Config"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bus.subscribe(MEMBER_VERIFIED, self._on_member_verified)
        bus.subscribe(AUTOROLE_ASSIGN, self._on_autorole_assign)
        bus.subscribe(AUTOROLE_STRIP, self._on_autorole_strip)

    async def _on_member_verified(self, *, guild_id: int, user_id: int, **_):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        member = guild.get_member(user_id)
        if not member:
            return

        verified_roles: list = await guild_settings.get(guild_id, "autorole_on_verify", [])
        for role_id in verified_roles:
            role = guild.get_role(int(role_id))
            if role:
                try:
                    await member.add_roles(role, reason="AutoRole: verification passed")
                except discord.HTTPException:
                    pass

        await self._apply_join_roles(guild, member, "AutoRole: applied after verification")

    async def _on_autorole_assign(self, *, guild_id: int, user_id: int, reason: str = "AutoRole", **_):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        member = guild.get_member(user_id)
        if not member:
            return
        await self._apply_join_roles(guild, member, reason)

    async def _apply_join_roles(self, guild: discord.Guild, member: discord.Member, reason: str):
        key = "autorole_bot_join" if member.bot else "autorole_human_join"
        role_ids: list = await guild_settings.get(guild.id, key, [])
        applied = []
        for role_id in role_ids:
            role = guild.get_role(int(role_id))
            if role and role not in member.roles:
                try:
                    await member.add_roles(role, reason=reason)
                    applied.append(role.id)
                except discord.HTTPException:
                    pass
        if applied:
            await bus.publish(
                LOG_EVENT, guild_id=guild.id, action="autorole_action",
                user_id=member.id, detail=f"Applied {len(applied)} {'bot' if member.bot else 'human'} join role(s)",
            )
        return applied

    async def _on_autorole_strip(self, *, guild_id: int, user_id: int, reason: str = "AutoRole strip", **_):
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return
        member = guild.get_member(user_id)
        if not member:
            return
        try:
            removable = [r for r in member.roles if not r.is_default() and r < guild.me.top_role]
            if removable:
                await member.remove_roles(*removable, reason=reason)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild_id = member.guild.id

        if not member.bot:
            verification_level = await guild_settings.get(guild_id, "verification_level", 0)
            if verification_level > 0:
                return

        delay_seconds = (await greeting_config.get_config(guild_id, "join"))["join_role_delay_seconds"]

        if delay_seconds and delay_seconds > 0:
            self.bot.loop.create_task(self._delayed_assign(guild_id, member.id, delay_seconds))
        else:
            await bus.publish(AUTOROLE_ASSIGN, guild_id=guild_id, user_id=member.id, reason="AutoRole: member joined")

    async def _delayed_assign(self, guild_id: int, user_id: int, delay_seconds: int) -> None:
        await asyncio.sleep(delay_seconds)
        guild = self.bot.get_guild(guild_id)
        if not guild or not guild.get_member(user_id):
            return
        await bus.publish(AUTOROLE_ASSIGN, guild_id=guild_id, user_id=user_id, reason=f"AutoRole: member joined (delayed {delay_seconds}s)")

    @commands.group(name="autorole", aliases=["arole"], invoke_without_command=True, help="View or configure automatic role assignment.")
    @has_guild_permission("manage_roles")
    @commands.guild_only()
    async def autorole_group(self, ctx: commands.Context):
        view = await AutoRoleOverviewLayout.create(ctx.author.id, ctx.guild.id)
        await ctx.send(view=view)

    @autorole_group.command(name="add", help="Add a join role. Usage: autorole add <human|bot> <role>")
    @has_guild_permission("manage_roles")
    async def ar_add(self, ctx: commands.Context, target: str, role: discord.Role):
        e = emoji_manager.get
        target = target.lower()
        if target not in ("human", "bot"):
            return await ctx.send(view=error_layout("Invalid Target", "Use `human` or `bot` as the target."))

        key = f"autorole_{target}_join"
        current: list = await guild_settings.get(ctx.guild.id, key, [])
        if role.id in current:
            return await ctx.send(view=error_layout("Already Added", f"{role.mention} is already a {target} join role."))

        current.append(role.id)
        await guild_settings.set(ctx.guild.id, key, current)
        await ctx.send(view=success_layout(
            f"{e('check')} {target.title()} Join Role Added",
            f"{role.mention} will be given to all new {target}s that join.\n-# Run `autorole sync {target}` to apply this to existing members.",
        ))

    @autorole_group.command(name="remove", help="Remove a join role. Usage: autorole remove <human|bot> <role>")
    @has_guild_permission("manage_roles")
    async def ar_remove(self, ctx: commands.Context, target: str, role: discord.Role):
        e = emoji_manager.get
        target = target.lower()
        if target not in ("human", "bot"):
            return await ctx.send(view=error_layout("Invalid Target", "Use `human` or `bot` as the target."))

        key = f"autorole_{target}_join"
        current: list = await guild_settings.get(ctx.guild.id, key, [])
        if role.id not in current:
            return await ctx.send(view=error_layout("Not Found", f"{role.mention} is not a {target} join role."))

        current.remove(role.id)
        await guild_settings.set(ctx.guild.id, key, current)
        await ctx.send(view=success_layout(f"{e('check')} {target.title()} Join Role Removed", f"{role.mention} removed from {target} join roles."))

    @autorole_group.command(name="clear", help="Clear all join roles for humans or bots. Usage: autorole clear <human|bot>")
    @has_guild_permission("manage_roles")
    async def ar_clear(self, ctx: commands.Context, target: str):
        e = emoji_manager.get
        target = target.lower()
        if target not in ("human", "bot"):
            return await ctx.send(view=error_layout("Invalid Target", "Use `human` or `bot` as the target."))

        key = f"autorole_{target}_join"
        await guild_settings.set(ctx.guild.id, key, [])
        await ctx.send(view=success_layout(f"{e('check')} Cleared", f"All {target} join roles cleared."))

    @autorole_group.command(name="sync", help="Retroactively apply join roles to existing members. Usage: autorole sync <human|bot|all>")
    @has_guild_permission("manage_roles")
    @commands.bot_has_permissions(manage_roles=True)
    async def ar_sync(self, ctx: commands.Context, target: str = "all"):
        e = emoji_manager.get
        target = target.lower()
        if target not in ("human", "bot", "all"):
            return await ctx.send(view=error_layout("Invalid Target", "Use `human`, `bot`, or `all`."))

        human_roles: list = await guild_settings.get(ctx.guild.id, "autorole_human_join", [])
        bot_roles: list = await guild_settings.get(ctx.guild.id, "autorole_bot_join", [])

        if not human_roles and not bot_roles:
            return await ctx.send(view=error_layout("Nothing To Sync", "No human or bot join roles are configured."))

        do_humans = target in ("human", "all") and human_roles
        do_bots = target in ("bot", "all") and bot_roles

        if not do_humans and not do_bots:
            return await ctx.send(view=error_layout("Nothing To Sync", f"No join roles configured for `{target}`."))

        scope_desc = {"human": "all human members", "bot": "all bot members", "all": "all members"}[target]
        confirm = ConfirmLayout(
            f"{e('autorole_cat')} Confirm Sync",
            f"This will apply the configured join role(s) to **{scope_desc}** in this server who don't already have them.\nThis may take a while in large servers.",
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "Sync cancelled."))

        await msg.edit(view=info_layout(f"{e('autorole_cat')} Syncing...", "Applying roles to members. This may take a moment."))

        synced = 0
        failed = 0
        for member in ctx.guild.members:
            if member.bot and not do_bots:
                continue
            if not member.bot and not do_humans:
                continue

            role_ids = bot_roles if member.bot else human_roles
            to_add = [ctx.guild.get_role(rid) for rid in role_ids]
            to_add = [r for r in to_add if r and r not in member.roles]
            if not to_add:
                continue
            try:
                await member.add_roles(*to_add, reason=f"AutoRole sync by {ctx.author}")
                synced += 1
            except discord.HTTPException:
                failed += 1

        result_body = f"**Members updated:** `{synced}`"
        if failed:
            result_body += f"\n**Failed:** `{failed}` (permission or hierarchy issues)"
        await msg.edit(view=success_layout(f"{e('check')} Sync Complete", result_body))

    @autorole_group.command(name="verifyrole", help="Add a role to assign after verification.")
    @has_guild_permission("manage_roles")
    async def ar_verifyrole(self, ctx: commands.Context, role: discord.Role):
        e = emoji_manager.get
        current: list = await guild_settings.get(ctx.guild.id, "autorole_on_verify", [])
        if role.id in current:
            return await ctx.send(view=error_layout("Already Added", f"{role.mention} is already a verify role."))
        current.append(role.id)
        await guild_settings.set(ctx.guild.id, "autorole_on_verify", current)
        await ctx.send(view=success_layout(f"{e('check')} Verify Role Added", f"{role.mention} will be given after verification."))

    @autorole_group.command(name="removeverifyrole", help="Remove a verify role.")
    @has_guild_permission("manage_roles")
    async def ar_removeverifyrole(self, ctx: commands.Context, role: discord.Role):
        e = emoji_manager.get
        current: list = await guild_settings.get(ctx.guild.id, "autorole_on_verify", [])
        if role.id not in current:
            return await ctx.send(view=error_layout("Not Found", f"{role.mention} is not a verify role."))
        current.remove(role.id)
        await guild_settings.set(ctx.guild.id, "autorole_on_verify", current)
        await ctx.send(view=success_layout(f"{e('check')} Verify Role Removed", f"{role.mention} removed from verify roles."))


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoRole(bot))
