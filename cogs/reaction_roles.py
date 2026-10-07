import time
import uuid
from typing import Optional

import discord
from discord.ext import commands

from utils import db, embed_templates, emoji_manager, message_vars
from utils.checks import has_guild_permission
from utils.components import ConfirmLayout, error_layout, info_layout, success_layout
from utils.events_bus import LOG_EVENT, bus

BINDING_MODES = ("normal", "unique", "verify", "reversed", "binding", "add_only", "remove_only")
PANEL_TYPES = ("reaction", "select")

BINDING_MODE_DESCRIPTIONS = {
    "normal": "React to add the role, unreact to remove it.",
    "unique": "Picking this role removes any other role from the same panel.",
    "verify": "Reacting grants the role once, then the bot removes the reaction. Unreacting does nothing.",
    "reversed": "Reacting removes the role, unreacting adds it back — for opt-out patterns.",
    "binding": "Reacting removes a set role and adds this one, in a single swap.",
    "add_only": "Reacting grants the role. Unreacting never removes it.",
    "remove_only": "Reacting removes the role. Unreacting never grants it.",
}


def new_panel_id() -> str:
    return str(uuid.uuid4())[:8].upper()


async def get_panel(panel_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM reaction_role_panels WHERE panel_id=?", (panel_id,))
    return dict(row) if row else None


async def get_panel_by_message(message_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM reaction_role_panels WHERE message_id=?", (message_id,))
    return dict(row) if row else None


async def list_panels(guild_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM reaction_role_panels WHERE guild_id=? ORDER BY created_at ASC", (guild_id,))
    return [dict(r) for r in rows]


async def get_bindings(panel_id: str) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM reaction_role_bindings WHERE panel_id=?", (panel_id,))
    return [dict(r) for r in rows]


async def get_binding(panel_id: str, emoji: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM reaction_role_bindings WHERE panel_id=? AND emoji=?", (panel_id, emoji))
    return dict(row) if row else None


async def build_panel_embed(guild: discord.Guild, panel: dict) -> discord.Embed:
    var_map = message_vars.build_base_variables(guild.me, guild)

    if panel["embed_name"]:
        template = await embed_templates.get_template(guild.id, panel["embed_name"])
        if template:
            fields = await embed_templates.get_fields(guild.id, panel["embed_name"])
            return embed_templates.build_discord_embed(template, var_map, fields)

    embed = discord.Embed(
        title=message_vars.substitute(panel["fallback_title"] or "Reaction Roles", var_map),
        description=message_vars.substitute(panel["fallback_description"] or "React below to receive a role.", var_map),
        color=0x2B2D31,
    )
    return embed


async def append_role_list(embed: discord.Embed, panel_id: str) -> None:
    bindings = await get_bindings(panel_id)
    if not bindings:
        return
    lines = []
    for b in bindings:
        line = f"{b['emoji']} — <@&{b['role_id']}>"
        if b["label"]:
            line += f" ({b['label']})"
        if b["binding_mode"] != "normal":
            line += f" · *{b['binding_mode']}*"
        lines.append(line)
    embed.add_field(name="Roles", value="\n".join(lines), inline=False)


class RoleSelectMenu(discord.ui.Select):
    def __init__(self, guild: discord.Guild, panel: dict, bindings: list[dict]):
        options = []
        for b in bindings[:25]:
            role = guild.get_role(b["role_id"])
            label = role.name if role else f"Unknown role ({b['role_id']})"
            options.append(discord.SelectOption(label=label[:100], value=b["emoji"], description=(b["label"] or "")[:100]))

        max_values = panel["max_roles"] or len(options)
        super().__init__(
            placeholder="Select your role(s)...",
            options=options,
            min_values=0,
            max_values=min(max_values, len(options)),
            custom_id=f"rr:select:{panel['panel_id']}",
        )

    async def callback(self, interaction: discord.Interaction):
        cog: "ReactionRoles" = interaction.client.get_cog("ReactionRoles")
        await cog.handle_select_submission(interaction, self.values)


class RoleSelectView(discord.ui.View):
    def __init__(self, guild: discord.Guild, panel: dict, bindings: list[dict]):
        super().__init__(timeout=None)
        self.add_item(RoleSelectMenu(guild, panel, bindings))


class ReactionRoles(commands.Cog):
    category = "Config"
    submodule = True

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        panels = await db.raw_fetch("SELECT * FROM reaction_role_panels WHERE panel_type='select' AND message_id IS NOT NULL")
        for panel in panels:
            panel = dict(panel)
            guild = self.bot.get_guild(panel["guild_id"])
            if not guild:
                continue
            bindings = await get_bindings(panel["panel_id"])
            if bindings:
                self.bot.add_view(RoleSelectView(guild, panel, bindings))

    @commands.group(name="reactionrole", aliases=["rr"], invoke_without_command=True, help="Manage advanced reaction role panels.")
    @has_guild_permission("manage_roles")
    @commands.guild_only()
    async def rr_group(self, ctx: commands.Context):
        e = emoji_manager.get
        panels = await list_panels(ctx.guild.id)
        if not panels:
            return await ctx.send(view=info_layout(
                f"{e('role')} Reaction Roles",
                "No panels yet. Use `rr create <name>` to make one.\n\n"
                "Panels can use any saved `embed` template for full visual customization — "
                "see `embed create` to build one first, or leave it unset for a simple default look.",
            ))

        lines = []
        for p in panels:
            binding_count = len(await get_bindings(p["panel_id"]))
            status_bits = []
            status_bits.append("Posted" if p["message_id"] else "Not posted yet")
            if p["locked"]:
                status_bits.append("🔒 Locked")
            lines.append(f"`{p['panel_id']}` — {binding_count} role(s) · `{p['panel_type']}` · mode `{p['mode']}` · {' · '.join(status_bits)}")
        await ctx.send(view=info_layout(f"{e('role')} Reaction Role Panels", "\n".join(lines)))

    @rr_group.command(name="create", help="Create a new reaction role panel. Usage: rr create [embed_template_name] [reaction|select]")
    @has_guild_permission("manage_roles")
    async def rr_create(self, ctx: commands.Context, embed_name: Optional[str] = None, panel_type: str = "reaction"):
        e = emoji_manager.get

        panel_type = panel_type.lower()
        if panel_type not in PANEL_TYPES:
            return await ctx.send(view=error_layout("Invalid Type", f"Panel type must be one of: {', '.join(f'`{t}`' for t in PANEL_TYPES)}"))

        if embed_name:
            template = await embed_templates.get_template(ctx.guild.id, embed_name)
            if not template:
                return await ctx.send(view=error_layout(
                    "Embed Not Found", f"No embed template named `{embed_name}`. Create one with `embed create {embed_name}` first."
                ))

        panel_id = new_panel_id()
        await db.raw_execute(
            "INSERT INTO reaction_role_panels (panel_id, guild_id, embed_name, fallback_title, fallback_description, panel_type, created_by, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (panel_id, ctx.guild.id, embed_name, "Reaction Roles", "React below to receive a role.", panel_type, ctx.author.id, time.time()),
        )

        emoji_note = "" if panel_type == "reaction" else " (emoji is just an internal label for select panels, not shown to users)"
        body = (
            f"Panel `{panel_id}` created as a **{panel_type}** panel" + (f" using embed template `{embed_name}`." if embed_name else " with a default look.") +
            f"\n\nNext: `rr addrole {panel_id} <emoji> <role>`{emoji_note}, then `rr post {panel_id} #channel` when ready.\n"
            f"You can also `rr attach {panel_id} <message_id>` to use an existing message instead of posting a new one."
        )
        await ctx.send(view=success_layout(f"{e('check')} Panel Created", body))

    @rr_group.command(name="addrole", help="Bind an emoji to a role on a panel. Usage: rr addrole <panel_id> <emoji> <role> [label]")
    @has_guild_permission("manage_roles")
    async def rr_addrole(self, ctx: commands.Context, panel_id: str, emoji: str, role: discord.Role, *, label: Optional[str] = None):
        e = emoji_manager.get
        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        if role >= ctx.guild.me.top_role:
            return await ctx.send(view=error_layout("Role Too High", f"{role.mention} is at or above my top role, so I can't assign it."))
        if role.managed:
            return await ctx.send(view=error_layout("Managed Role", f"{role.mention} is managed by an integration and can't be assigned manually."))

        existing_count = len(await get_bindings(panel["panel_id"]))
        if existing_count >= 20:
            return await ctx.send(view=error_layout("Limit Reached", "A panel can have at most 20 role bindings."))

        await db.raw_execute(
            "INSERT INTO reaction_role_bindings (panel_id, emoji, role_id, label) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(panel_id, emoji) DO UPDATE SET role_id=excluded.role_id, label=excluded.label",
            (panel["panel_id"], emoji, role.id, label),
        )

        if panel["message_id"]:
            await self._sync_panel_message(ctx.guild, panel)

        await ctx.send(view=success_layout(f"{e('check')} Role Bound", f"{emoji} now grants {role.mention} on panel `{panel['panel_id']}`."))

    @rr_group.command(name="removerole", help="Unbind an emoji from a panel. Usage: rr removerole <panel_id> <emoji>")
    @has_guild_permission("manage_roles")
    async def rr_removerole(self, ctx: commands.Context, panel_id: str, emoji: str):
        e = emoji_manager.get
        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        cur = await db.raw_execute("DELETE FROM reaction_role_bindings WHERE panel_id=? AND emoji=?", (panel["panel_id"], emoji))
        if not cur.rowcount:
            return await ctx.send(view=error_layout("Not Found", f"No binding for {emoji} on that panel."))

        if panel["message_id"]:
            await self._sync_panel_message(ctx.guild, panel)
            if panel["panel_type"] == "reaction":
                try:
                    channel = ctx.guild.get_channel(panel["channel_id"])
                    message = await channel.fetch_message(panel["message_id"])
                    await message.clear_reaction(emoji)
                except discord.HTTPException:
                    pass

        await ctx.send(view=success_layout(f"{e('check')} Role Unbound", f"{emoji} no longer grants a role on that panel."))

    @rr_group.command(name="bindingmode", aliases=["rolemode"], help="Set a specific binding's behavior mode. Usage: rr bindingmode <panel_id> <emoji> <mode>")
    @has_guild_permission("manage_roles")
    async def rr_bindingmode(self, ctx: commands.Context, panel_id: str, emoji: str, mode: str):
        e = emoji_manager.get
        mode = mode.lower()
        if mode not in BINDING_MODES:
            return await ctx.send(view=error_layout("Invalid Mode", f"Choose from: {', '.join(f'`{m}`' for m in BINDING_MODES)}"))

        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        binding = await get_binding(panel["panel_id"], emoji)
        if not binding:
            return await ctx.send(view=error_layout("Not Found", f"No binding for {emoji} on that panel."))

        if mode == "binding":
            return await ctx.send(view=error_layout(
                "Use rr bind Instead", "Binding mode needs a swap role — set it with `rr bind <panel_id> <emoji> <swap_role>` instead."
            ))

        await db.raw_execute("UPDATE reaction_role_bindings SET binding_mode=? WHERE panel_id=? AND emoji=?", (mode, panel["panel_id"], emoji))
        await ctx.send(view=success_layout(f"{e('check')} Mode Set", f"{emoji} on `{panel['panel_id']}` is now **{mode}** — {BINDING_MODE_DESCRIPTIONS[mode]}"))

    @rr_group.command(name="bind", help="Set up Binding mode: reacting removes one role and grants another. Usage: rr bind <panel_id> <emoji> <swap_role>")
    @has_guild_permission("manage_roles")
    async def rr_bind(self, ctx: commands.Context, panel_id: str, emoji: str, swap_role: discord.Role):
        e = emoji_manager.get
        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        binding = await get_binding(panel["panel_id"], emoji)
        if not binding:
            return await ctx.send(view=error_layout("Not Found", f"No binding for {emoji} on that panel. Add it first with `rr addrole`."))

        if swap_role.id == binding["role_id"]:
            return await ctx.send(view=error_layout("Same Role", "The swap role must be different from the role this emoji grants."))

        await db.raw_execute(
            "UPDATE reaction_role_bindings SET binding_mode='binding', swap_role_id=? WHERE panel_id=? AND emoji=?",
            (swap_role.id, panel["panel_id"], emoji),
        )
        await ctx.send(view=success_layout(
            f"{e('check')} Binding Set", f"Reacting {emoji} now removes {swap_role.mention} and grants <@&{binding['role_id']}>."
        ))

    @rr_group.command(name="group", help="Assign a binding to a role group, so only one role per group can be held. Usage: rr group <panel_id> <emoji> <group_name|off>")
    @has_guild_permission("manage_roles")
    async def rr_group_cmd(self, ctx: commands.Context, panel_id: str, emoji: str, group_name: str):
        e = emoji_manager.get
        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        binding = await get_binding(panel["panel_id"], emoji)
        if not binding:
            return await ctx.send(view=error_layout("Not Found", f"No binding for {emoji} on that panel."))

        value = None if group_name.lower() == "off" else group_name.lower()
        await db.raw_execute("UPDATE reaction_role_bindings SET group_id=? WHERE panel_id=? AND emoji=?", (value, panel["panel_id"], emoji))

        if value:
            await ctx.send(view=success_layout(f"{e('check')} Group Set", f"{emoji} is now part of group `{value}` — only one role from this group can be held at a time."))
        else:
            await ctx.send(view=success_layout(f"{e('check')} Group Cleared", f"{emoji} is no longer part of a role group."))

    @rr_group.command(name="mode", help="Set a panel's default role mode: toggle, add_only, or unique. Usage: rr mode <panel_id> <mode>")
    @has_guild_permission("manage_roles")
    async def rr_mode(self, ctx: commands.Context, panel_id: str, mode: str):
        e = emoji_manager.get
        mode = mode.lower()
        legacy_modes = ("toggle", "add_only", "unique")
        if mode not in legacy_modes:
            return await ctx.send(view=error_layout("Invalid Mode", f"Choose from: {', '.join(f'`{m}`' for m in legacy_modes)}"))

        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        await db.raw_execute("UPDATE reaction_role_panels SET mode=? WHERE panel_id=?", (mode, panel["panel_id"]))
        await ctx.send(view=success_layout(
            f"{e('check')} Mode Set",
            f"Panel `{panel['panel_id']}` default mode set to `{mode}`. Individual bindings can still override this with `rr bindingmode`.",
        ))

    @rr_group.command(name="lock", help="Lock a panel so reactions stop granting or removing roles until unlocked.")
    @has_guild_permission("manage_roles")
    async def rr_lock(self, ctx: commands.Context, panel_id: str):
        e = emoji_manager.get
        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        await db.raw_execute("UPDATE reaction_role_panels SET locked=1 WHERE panel_id=?", (panel["panel_id"],))
        await ctx.send(view=success_layout(f"{e('check')} Panel Locked", f"Panel `{panel['panel_id']}` is locked — no roles will be granted or removed until unlocked."))

    @rr_group.command(name="unlock", help="Unlock a previously locked panel.")
    @has_guild_permission("manage_roles")
    async def rr_unlock(self, ctx: commands.Context, panel_id: str):
        e = emoji_manager.get
        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        await db.raw_execute("UPDATE reaction_role_panels SET locked=0 WHERE panel_id=?", (panel["panel_id"],))
        await ctx.send(view=success_layout(f"{e('check')} Panel Unlocked", f"Panel `{panel['panel_id']}` is active again."))

    @rr_group.command(name="maxroles", help="Limit how many roles a member can hold from one panel. Usage: rr maxroles <panel_id> <count|off>")
    @has_guild_permission("manage_roles")
    async def rr_maxroles(self, ctx: commands.Context, panel_id: str, count: str):
        e = emoji_manager.get
        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        if count.lower() == "off":
            await db.raw_execute("UPDATE reaction_role_panels SET max_roles=NULL WHERE panel_id=?", (panel["panel_id"],))
            return await ctx.send(view=success_layout(f"{e('check')} Limit Removed", "No role limit on this panel."))

        if not count.isdigit() or int(count) <= 0:
            return await ctx.send(view=error_layout("Invalid Count", "Provide a positive number, or `off` to remove the limit."))

        await db.raw_execute("UPDATE reaction_role_panels SET max_roles=? WHERE panel_id=?", (int(count), panel["panel_id"]))
        await ctx.send(view=success_layout(f"{e('check')} Limit Set", f"Members can hold at most **{count}** role(s) from this panel."))

    @rr_group.command(name="gate", help="Require or block a role, panel-wide or for one binding. Usage: rr gate <panel_id> <required|blacklist> <role|off> [emoji]")
    @has_guild_permission("manage_roles")
    async def rr_gate(self, ctx: commands.Context, panel_id: str, gate_type: str, role: Optional[discord.Role] = None, emoji: Optional[str] = None):
        e = emoji_manager.get
        gate_type = gate_type.lower()
        if gate_type not in ("required", "blacklist"):
            return await ctx.send(view=error_layout("Invalid Gate Type", "Use `required` or `blacklist`."))

        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        column = "required_role_id" if gate_type == "required" else "blacklist_role_id"
        role_id = role.id if role else None

        if emoji:
            binding = await get_binding(panel["panel_id"], emoji)
            if not binding:
                return await ctx.send(view=error_layout("Not Found", f"No binding for {emoji} on that panel."))
            await db.raw_execute(f"UPDATE reaction_role_bindings SET {column}=? WHERE panel_id=? AND emoji=?", (role_id, panel["panel_id"], emoji))
            scope_text = f"binding {emoji}"
        else:
            await db.raw_execute(f"UPDATE reaction_role_panels SET {column}=? WHERE panel_id=?", (role_id, panel["panel_id"]))
            scope_text = "the whole panel"

        if role:
            await ctx.send(view=success_layout(f"{e('check')} Gate Set", f"{gate_type.title()} role for {scope_text}: {role.mention}."))
        else:
            await ctx.send(view=success_layout(f"{e('check')} Gate Cleared", f"{gate_type.title()} role requirement removed from {scope_text}."))

    @rr_group.command(name="post", help="Post a panel as a brand-new message. Usage: rr post <panel_id> [#channel]")
    @has_guild_permission("manage_roles")
    async def rr_post(self, ctx: commands.Context, panel_id: str, channel: Optional[discord.TextChannel] = None):
        e = emoji_manager.get
        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        bindings = await get_bindings(panel["panel_id"])
        if not bindings:
            return await ctx.send(view=error_layout("No Roles", "Add at least one role with `rr addrole` before posting."))

        target_channel = channel or ctx.channel
        embed = await build_panel_embed(ctx.guild, panel)
        await append_role_list(embed, panel["panel_id"])

        try:
            if panel["panel_type"] == "select":
                message = await target_channel.send(embed=embed, view=RoleSelectView(ctx.guild, panel, bindings))
            else:
                message = await target_channel.send(embed=embed)
                for binding in bindings:
                    await message.add_reaction(binding["emoji"])
        except discord.HTTPException as ex:
            return await ctx.send(view=error_layout("Failed", f"Couldn't post the panel: {ex}"))

        await db.raw_execute(
            "UPDATE reaction_role_panels SET channel_id=?, message_id=? WHERE panel_id=?",
            (target_channel.id, message.id, panel["panel_id"]),
        )
        await ctx.send(view=success_layout(f"{e('check')} Panel Posted", f"Posted in {target_channel.mention}."))

    @rr_group.command(name="attach", help="Attach a panel to an already-existing message instead of posting a new one. Usage: rr attach <panel_id> <message_id> [#channel]")
    @has_guild_permission("manage_roles")
    async def rr_attach(self, ctx: commands.Context, panel_id: str, message_id: int, channel: Optional[discord.TextChannel] = None):
        e = emoji_manager.get
        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        bindings = await get_bindings(panel["panel_id"])
        if not bindings:
            return await ctx.send(view=error_layout("No Roles", "Add at least one role with `rr addrole` before attaching."))

        target_channel = channel or ctx.channel
        try:
            message = await target_channel.fetch_message(message_id)
        except discord.HTTPException:
            return await ctx.send(view=error_layout("Not Found", f"Couldn't find a message with ID `{message_id}` in {target_channel.mention}."))

        if panel["panel_type"] == "reaction":
            try:
                for binding in bindings:
                    await message.add_reaction(binding["emoji"])
            except discord.HTTPException as ex:
                return await ctx.send(view=error_layout("Failed", f"Couldn't add reactions to that message: {ex}"))

        await db.raw_execute(
            "UPDATE reaction_role_panels SET channel_id=?, message_id=? WHERE panel_id=?",
            (target_channel.id, message.id, panel["panel_id"]),
        )
        await ctx.send(view=success_layout(f"{e('check')} Panel Attached", f"Panel `{panel['panel_id']}` is now live on that message."))

    async def _sync_panel_message(self, guild: discord.Guild, panel: dict) -> None:
        if not panel["channel_id"] or not panel["message_id"]:
            return
        channel = guild.get_channel(panel["channel_id"])
        if not channel:
            return
        try:
            message = await channel.fetch_message(panel["message_id"])
        except discord.HTTPException:
            return

        embed = await build_panel_embed(guild, panel)
        await append_role_list(embed, panel["panel_id"])
        try:
            await message.edit(embed=embed)
        except discord.HTTPException:
            pass

    @rr_group.command(name="delete", help="Delete a panel entirely, including its posted message.")
    @has_guild_permission("manage_roles")
    async def rr_delete(self, ctx: commands.Context, panel_id: str):
        e = emoji_manager.get
        panel = await get_panel(panel_id.upper())
        if not panel or panel["guild_id"] != ctx.guild.id:
            return await ctx.send(view=error_layout("Not Found", f"No panel with ID `{panel_id.upper()}` in this server."))

        confirm = ConfirmLayout(
            "Confirm Delete", f"Delete panel `{panel['panel_id']}` and its posted message? This can't be undone.", author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "Panel was not deleted."))

        if panel["channel_id"] and panel["message_id"]:
            channel = ctx.guild.get_channel(panel["channel_id"])
            if channel:
                try:
                    message = await channel.fetch_message(panel["message_id"])
                    await message.delete()
                except discord.HTTPException:
                    pass

        await db.raw_execute("DELETE FROM reaction_role_bindings WHERE panel_id=?", (panel["panel_id"],))
        await db.raw_execute("DELETE FROM reaction_role_panels WHERE panel_id=?", (panel["panel_id"],))
        await msg.edit(view=success_layout(f"{e('check')} Deleted", f"Panel `{panel['panel_id']}` has been removed."))

    async def _check_gate(self, member: discord.Member, required_role_id: Optional[int], blacklist_role_id: Optional[int]) -> bool:
        if required_role_id and not any(r.id == required_role_id for r in member.roles):
            return False
        if blacklist_role_id and any(r.id == blacklist_role_id for r in member.roles):
            return False
        return True

    async def _enforce_group(self, guild: discord.Guild, member: discord.Member, panel: dict, new_role_id: int, group_id: str) -> None:
        bindings = await get_bindings(panel["panel_id"])
        group_role_ids = {b["role_id"] for b in bindings if b["group_id"] == group_id and b["role_id"] != new_role_id}
        roles_to_remove = [r for r in member.roles if r.id in group_role_ids]
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason=f"Reaction role: group '{group_id}' swap")
            except discord.HTTPException:
                pass

    async def _enforce_max_roles(self, member: discord.Member, panel: dict) -> bool:
        if not panel["max_roles"]:
            return True
        bindings = await get_bindings(panel["panel_id"])
        panel_role_ids = {b["role_id"] for b in bindings}
        currently_held = [r for r in member.roles if r.id in panel_role_ids]
        return len(currently_held) < panel["max_roles"]

    async def handle_select_submission(self, interaction: discord.Interaction, selected_emojis: list[str]) -> None:
        e = emoji_manager.get
        panel = await get_panel_by_message(interaction.message.id)
        if not panel:
            return await interaction.response.send_message("This panel is no longer active.", ephemeral=True)
        if panel["locked"]:
            return await interaction.response.send_message("This panel is currently locked.", ephemeral=True)

        guild = interaction.guild
        member = interaction.user
        bindings = await get_bindings(panel["panel_id"])
        selected_bindings = [b for b in bindings if b["emoji"] in selected_emojis]

        granted, denied = [], []
        for binding in selected_bindings:
            if not await self._check_gate(member, binding["required_role_id"], binding["blacklist_role_id"]):
                denied.append(f"<@&{binding['role_id']}> (missing requirement)")
                continue
            if not await self._check_gate(member, panel["required_role_id"], panel["blacklist_role_id"]):
                denied.append(f"<@&{binding['role_id']}> (panel requirement)")
                continue

            role = guild.get_role(binding["role_id"])
            if not role:
                continue

            if binding["group_id"]:
                await self._enforce_group(guild, member, panel, role.id, binding["group_id"])

            try:
                await member.add_roles(role, reason=f"Reaction role: select panel {panel['panel_id']}")
                granted.append(role.mention)
                await bus.publish(LOG_EVENT, guild_id=guild.id, action="reaction_role_granted", user_id=member.id, role_id=role.id, panel_id=panel["panel_id"])
            except discord.HTTPException:
                denied.append(f"<@&{binding['role_id']}> (couldn't assign)")

        selected_role_ids = {b["role_id"] for b in selected_bindings}
        all_panel_role_ids = {b["role_id"] for b in bindings}
        roles_to_remove = [r for r in member.roles if r.id in all_panel_role_ids and r.id not in selected_role_ids]
        if roles_to_remove:
            try:
                await member.remove_roles(*roles_to_remove, reason=f"Reaction role: select panel {panel['panel_id']} deselect")
            except discord.HTTPException:
                pass

        parts = []
        if granted:
            parts.append(f"**Granted:** {', '.join(granted)}")
        if denied:
            parts.append(f"**Skipped:** {', '.join(denied)}")
        if not parts:
            parts.append("No roles selected.")
        await interaction.response.send_message(f"{e('check')} " + "\n".join(parts), ephemeral=True)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or (payload.member and payload.member.bot):
            return

        panel = await get_panel_by_message(payload.message_id)
        if not panel or panel["panel_type"] != "reaction":
            return
        if panel["locked"]:
            return

        binding = await get_binding(panel["panel_id"], str(payload.emoji))
        if not binding:
            return

        guild = self.bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id) if guild else None
        if not guild or not member:
            return

        async def strip_reaction():
            try:
                channel = guild.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)
                await message.remove_reaction(payload.emoji, member)
            except discord.HTTPException:
                pass

        if not await self._check_gate(member, binding["required_role_id"], binding["blacklist_role_id"]):
            return await strip_reaction()
        if not await self._check_gate(member, panel["required_role_id"], panel["blacklist_role_id"]):
            return await strip_reaction()

        mode = binding["binding_mode"]

        if mode == "remove_only":
            role = guild.get_role(binding["role_id"])
            if role:
                try:
                    await member.remove_roles(role, reason=f"Reaction role: panel {panel['panel_id']} (remove_only)")
                    await bus.publish(LOG_EVENT, guild_id=guild.id, action="reaction_role_removed", user_id=member.id, role_id=role.id, panel_id=panel["panel_id"])
                except discord.HTTPException:
                    pass
            return

        if mode == "reversed":
            role = guild.get_role(binding["role_id"])
            if role:
                try:
                    await member.remove_roles(role, reason=f"Reaction role: panel {panel['panel_id']} (reversed)")
                    await bus.publish(LOG_EVENT, guild_id=guild.id, action="reaction_role_removed", user_id=member.id, role_id=role.id, panel_id=panel["panel_id"])
                except discord.HTTPException:
                    pass
            return

        if mode == "binding" and binding["swap_role_id"]:
            swap_role = guild.get_role(binding["swap_role_id"])
            if swap_role and swap_role in member.roles:
                try:
                    await member.remove_roles(swap_role, reason=f"Reaction role: panel {panel['panel_id']} (binding swap)")
                except discord.HTTPException:
                    pass

        if not await self._enforce_max_roles(member, panel):
            return await strip_reaction()

        if binding["group_id"]:
            await self._enforce_group(guild, member, panel, binding["role_id"], binding["group_id"])
        elif panel["mode"] == "unique":
            bindings = await get_bindings(panel["panel_id"])
            other_role_ids = {b["role_id"] for b in bindings if b["role_id"] != binding["role_id"]}
            roles_to_remove = [r for r in member.roles if r.id in other_role_ids]
            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason="Reaction role: unique mode swap")
                except discord.HTTPException:
                    pass

        role = guild.get_role(binding["role_id"])
        if not role:
            return

        try:
            await member.add_roles(role, reason=f"Reaction role: panel {panel['panel_id']}")
        except discord.HTTPException:
            return

        await bus.publish(LOG_EVENT, guild_id=guild.id, action="reaction_role_granted", user_id=member.id, role_id=role.id, panel_id=panel["panel_id"])

        if mode == "verify":
            await strip_reaction()

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return

        panel = await get_panel_by_message(payload.message_id)
        if not panel or panel["panel_type"] != "reaction" or panel["locked"]:
            return

        binding = await get_binding(panel["panel_id"], str(payload.emoji))
        if not binding:
            return

        mode = binding["binding_mode"]
        if mode in ("add_only", "verify", "remove_only", "binding"):
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return

        role = guild.get_role(binding["role_id"])
        if not role:
            return

        if mode == "reversed":
            try:
                await member.add_roles(role, reason=f"Reaction role: panel {panel['panel_id']} (reversed unreact)")
                await bus.publish(LOG_EVENT, guild_id=guild.id, action="reaction_role_granted", user_id=member.id, role_id=role.id, panel_id=panel["panel_id"])
            except discord.HTTPException:
                pass
            return

        try:
            await member.remove_roles(role, reason=f"Reaction role: panel {panel['panel_id']}")
        except discord.HTTPException:
            return

        await bus.publish(LOG_EVENT, guild_id=guild.id, action="reaction_role_removed", user_id=member.id, role_id=role.id, panel_id=panel["panel_id"])


async def setup(bot: commands.Bot):
    await bot.add_cog(ReactionRoles(bot))
