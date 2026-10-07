import asyncio
import io
import json
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import cc_engine, db, emoji_manager
from utils.cc_engine import ALL_TRIGGER_TYPES, CCGroup, CustomCommand, TRIGGER_INTERVAL, TRIGGER_REACTION, TRIGGER_MSG_EDIT
from utils.checks import has_guild_permission
from utils.colors import NEUTRAL
from utils.components import ConfirmLayout, error_layout, footer_block, info_layout, success_layout
from utils.prefix import get_guild_prefix
import config


MAX_COMMANDS_PER_GUILD = 100
MAX_GROUPS_PER_GUILD = 20
MAX_RESPONSES_PER_COMMAND = 10


def _cc_body(fields: dict) -> str:
    return "\n".join(f"**{k}:** {v}" for k, v in fields.items() if v is not None)


def _cc_layout(title: str, fields: dict, *, color: int = NEUTRAL) -> discord.ui.LayoutView:
    from utils.components import footer_block
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"## {title}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(_cc_body(fields)))
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


def _build_embed_from_data(cmd: CustomCommand, clean_response: str, embed_data: dict) -> discord.Embed:
    color = embed_data.get("color") or (int(cmd.embed_color.lstrip("#"), 16) if cmd.embed_color else NEUTRAL)
    embed = discord.Embed(
        title=embed_data.get("title") or cmd.embed_title,
        description=clean_response or None,
        color=color,
    )
    if "footer" in embed_data:
        embed.set_footer(text=embed_data["footer"])
    if "thumbnail" in embed_data:
        embed.set_thumbnail(url=embed_data["thumbnail"])
    if "image" in embed_data:
        embed.set_image(url=embed_data["image"])
    for field in embed_data.get("fields", []):
        embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", False))
    return embed


ACTION_PAGES: list[tuple[str, str]] = [
    ("Roles", (
        "`{addrole:Role}` — add role to author\n"
        "`{removerole:Role}` — remove role from author\n"
        "`{togglerole:Role}` — toggle role on/off\n"
        "`{addroleto:@Member|Role}` — add role to specific member\n"
        "`{removerolefrom:@Member|Role}` — remove role from specific member\n"
        "`{createrole:Name|#hex}` — create a new role\n"
        "`{deleterole:Role}` — delete a role\n"
        "`{editrole:Role|name=New Name}` — edit role (name/color/hoist/mentionable)"
    )),
    ("Moderation", (
        "`{kick:@Member|reason}` — kick a member\n"
        "`{ban:@Member|reason}` — ban a member\n"
        "`{softban:@Member|reason}` — ban+unban to clear messages\n"
        "`{unban:user_id}` — unban a user\n"
        "`{timeout:@Member|10m}` / `{mute:@Member|1h}` — timeout\n"
        "`{untimeout:@Member}` / `{unmute:@Member}` — remove timeout\n"
        "`{warn:@Member|reason}` — add a mod warning\n"
        "`{setnick:@Member|Nick}` — set nickname\n"
        "`{resetnick:@Member}` — reset nickname"
    )),
    ("Messages", (
        "`{dm:message}` — DM the author\n"
        "`{dmmember:@Member|message}` — DM specific member\n"
        "`{sendreply:message}` — reply to trigger message\n"
        "`{sendchannel:#channel|message}` — send to a channel\n"
        "`{react:emoji1,emoji2}` — react to trigger\n"
        "`{reactremove:emoji}` — remove a reaction\n"
        "`{silentdelete}` / `{deletetrigger}` — delete trigger\n"
        "`{deleteafter:seconds}` — auto-delete response\n"
        "`{noresponse}` — send no response text"
    )),
    ("Channels", (
        "`{createchannel:name|Category}` — create text channel\n"
        "`{deletechannel:#channel}` — delete a channel\n"
        "`{lockchannel:#channel}` — lock channel (deny send)\n"
        "`{unlockchannel:#channel}` — unlock channel\n"
        "`{hidechannel:#channel}` — hide channel\n"
        "`{showchannel:#channel}` — show channel"
    )),
    ("Embed Builder", (
        "`{settitle:My Title}` — set embed title\n"
        "`{setcolor:#FF5733}` — set embed color\n"
        "`{setfooter:Footer text}` — set embed footer\n"
        "`{setthumbnail:url}` — set embed thumbnail\n"
        "`{setimage:url}` — set embed image\n"
        "`{addfield:Name|Value}` — add embed field\n\n"
        "-# Combine with `cc embed` to force embed mode."
    )),
    ("Utility & Examples", (
        "`{log:#channel|message}` — log to a channel\n"
        "`{sleep:seconds}` — pause execution (max 60s)\n\n"
        "**Example — Self-role toggle:**\n"
        "```\n{togglerole:Member}\n{if hasrole Member}\nRole added!\n{else}\nRole removed.\n{end}\n```\n"
        "**Example — Silent log:**\n"
        "```\n{log:#audit-log|{username} ran the command}\n{noresponse}\n```"
    )),
]


class ActionsPageRow(discord.ui.ActionRow):
    def __init__(self):
        super().__init__(
            discord.ui.Button(label="◀ Prev", style=discord.ButtonStyle.secondary, custom_id="cc:actions:prev"),
            discord.ui.Button(label="Next ▶", style=discord.ButtonStyle.secondary, custom_id="cc:actions:next"),
        )
        self.children[0].callback = self._prev
        self.children[1].callback = self._next

    async def _prev(self, interaction: discord.Interaction):
        view: ActionsLayout = self.view
        view.page = (view.page - 1) % len(ACTION_PAGES)
        view._render()
        await interaction.response.edit_message(view=view)

    async def _next(self, interaction: discord.Interaction):
        view: ActionsLayout = self.view
        view.page = (view.page + 1) % len(ACTION_PAGES)
        view._render()
        await interaction.response.edit_message(view=view)


class ActionsLayout(discord.ui.LayoutView):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.page = 0

        e = emoji_manager.get
        self.container = discord.ui.Container(accent_color=NEUTRAL)
        self.header = discord.ui.TextDisplay(f"## {e('info')} Action Tags")
        self.container.add_item(self.header)
        self.container.add_item(discord.ui.Separator())
        self.body = discord.ui.TextDisplay("")
        self.container.add_item(self.body)
        self.container.add_item(discord.ui.Separator())
        self.container.add_item(ActionsPageRow())
        self.container.add_item(discord.ui.Separator())
        for item in footer_block():
            self.container.add_item(item)
        self.add_item(self.container)
        self._render()

    def _render(self):
        title, body = ACTION_PAGES[self.page]
        self.header.content = f"## {emoji_manager.get('info')} Action Tags — {title}"
        self.body.content = f"{body}\n\n-# Page {self.page + 1}/{len(ACTION_PAGES)}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True


class CustomCommands(commands.Cog):
    category = "Config"
    submodule = True

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._cache: dict[int, dict[str, CustomCommand]] = {}
        self._groups: dict[int, dict[str, CCGroup]] = {}
        self._next_id = 1
        self._loaded_guilds: set[int] = set()

    async def cog_load(self):
        self.interval_loop.start()

    def cog_unload(self):
        self.interval_loop.cancel()

    async def _ensure_loaded(self, guild_id: int):
        if guild_id in self._loaded_guilds:
            return
        rows = await db.raw_fetch("SELECT trigger, data FROM custom_commands WHERE guild_id=?", (guild_id,))
        commands_map = {}
        for row in rows:
            data = json.loads(row["data"])
            commands_map[row["trigger"]] = CustomCommand(row["trigger"], data)
            self._next_id = max(self._next_id, data.get("numeric_id", 0) + 1)
        self._cache[guild_id] = commands_map

        group_rows = await db.raw_fetch("SELECT name, data FROM custom_command_groups WHERE guild_id=?", (guild_id,))
        groups_map = {r["name"]: CCGroup(json.loads(r["data"])) for r in group_rows}
        self._groups[guild_id] = groups_map

        self._loaded_guilds.add(guild_id)

    def _alloc_id(self) -> int:
        nid = self._next_id
        self._next_id += 1
        return nid

    def _get_commands(self, guild_id: int) -> dict[str, CustomCommand]:
        return self._cache.get(guild_id, {})

    def _get_groups(self, guild_id: int) -> dict[str, CCGroup]:
        return self._groups.get(guild_id, {})

    async def _save_command(self, guild_id: int, cmd: CustomCommand, created_by: Optional[int] = None):
        existing = await db.raw_fetchone(
            "SELECT created_by FROM custom_commands WHERE guild_id=? AND trigger=?", (guild_id, cmd.trigger)
        )
        creator = created_by if created_by is not None else (existing["created_by"] if existing else 0)
        await db.raw_execute(
            "INSERT INTO custom_commands (guild_id, trigger, numeric_id, data, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id, trigger) DO UPDATE SET data=excluded.data, numeric_id=excluded.numeric_id",
            (guild_id, cmd.trigger, cmd.numeric_id, json.dumps(cmd.to_dict()), creator, time.time()),
        )

    async def _delete_command(self, guild_id: int, trigger: str):
        await db.raw_execute("DELETE FROM custom_commands WHERE guild_id=? AND trigger=?", (guild_id, trigger))

    async def _save_group(self, guild_id: int, group: CCGroup):
        await db.raw_execute(
            "INSERT INTO custom_command_groups (guild_id, name, data) VALUES (?, ?, ?)"
            " ON CONFLICT(guild_id, name) DO UPDATE SET data=excluded.data",
            (guild_id, group.name, json.dumps(group.to_dict())),
        )

    async def _delete_group(self, guild_id: int, name: str):
        await db.raw_execute("DELETE FROM custom_command_groups WHERE guild_id=? AND name=?", (guild_id, name))

    @tasks.loop(minutes=1)
    async def interval_loop(self):
        now = time.time()
        for guild_id, cmds in list(self._cache.items()):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            for trigger, cmd in cmds.items():
                if cmd.trigger_type != TRIGGER_INTERVAL or not cmd.enabled:
                    continue
                if not cmd.interval_minutes or not cmd.interval_channel:
                    continue
                if now < cmd.interval_next_run:
                    continue
                channel = guild.get_channel(cmd.interval_channel)
                if not channel:
                    continue
                var_map = {
                    "server": guild.name, "serverid": str(guild.id),
                    "membercount": str(guild.member_count),
                    "channel": channel.mention, "channelname": channel.name,
                    "channelid": str(channel.id),
                }
                raw = cc_engine.substitute_variables(cmd.get_response(), var_map)
                clean, _, channel_sends, embed_data = await cc_engine.process_actions(raw, None, self.bot)
                if clean or embed_data:
                    try:
                        if cmd.embed or embed_data:
                            await channel.send(embed=_build_embed_from_data(cmd, clean, embed_data))
                        else:
                            await channel.send(clean)
                    except discord.HTTPException:
                        pass
                cmd.interval_next_run = now + (cmd.interval_minutes * 60)
                cmd.uses += 1
                await self._save_command(guild_id, cmd)

    @interval_loop.before_loop
    async def _before_interval(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id or (payload.member and payload.member.bot):
            return
        await self._ensure_loaded(payload.guild_id)
        cmds = self._get_commands(payload.guild_id)

        for trigger, cmd in cmds.items():
            if cmd.trigger_type != TRIGGER_REACTION or not cmd.enabled:
                continue
            if cmd.reaction_emoji and str(payload.emoji) != cmd.reaction_emoji:
                continue
            if cmd.reaction_message_id and payload.message_id != cmd.reaction_message_id:
                continue

            guild = self.bot.get_guild(payload.guild_id)
            if not guild:
                continue
            member = payload.member or guild.get_member(payload.user_id)
            channel = guild.get_channel(payload.channel_id)
            if not member or not channel:
                continue

            group = self._get_groups(guild.id).get(cmd.group) if cmd.group else None
            ok, _ = cmd.check_restrictions(member, channel, group)
            if not ok or cmd.check_cooldown(member.id) > 0:
                continue

            cmd.apply_cooldown(member.id)
            cmd.uses += 1
            var_map = {
                "user": member.mention, "username": member.display_name, "userid": str(member.id),
                "server": guild.name, "serverid": str(guild.id), "membercount": str(guild.member_count),
                "channel": channel.mention, "channelname": channel.name, "channelid": str(channel.id),
                "emoji": str(payload.emoji), "msgid": str(payload.message_id),
            }
            raw = cc_engine.substitute_variables(cmd.get_response(), var_map)
            clean, delete_after, channel_sends, embed_data = await cc_engine.process_actions(raw, None, self.bot)

            if clean or embed_data:
                da = delete_after or cmd.delete_response_after or None
                try:
                    if cmd.embed or embed_data:
                        await channel.send(embed=_build_embed_from_data(cmd, clean, embed_data), delete_after=da)
                    else:
                        await channel.send(clean, delete_after=da)
                except discord.HTTPException:
                    pass
            for ch, msg in channel_sends:
                try:
                    await ch.send(msg)
                except discord.HTTPException:
                    pass

            await self._save_command(guild.id, cmd)
            break

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.author.bot or not after.guild:
            return
        await self._ensure_loaded(after.guild.id)
        cmds = self._get_commands(after.guild.id)

        for trigger, cmd in cmds.items():
            if cmd.trigger_type != TRIGGER_MSG_EDIT or not cmd.enabled:
                continue
            if not cmd.matches(after.content, after.content):
                continue

            group = self._get_groups(after.guild.id).get(cmd.group) if cmd.group else None
            ok, _ = cmd.check_restrictions(after.author, after.channel, group)
            if not ok or cmd.check_cooldown(after.author.id) > 0:
                continue

            cmd.apply_cooldown(after.author.id)
            cmd.uses += 1
            args = after.content.split()[1:]
            var_map = cc_engine.build_variables(after, args)
            var_map["before"] = before.content
            raw = cc_engine.substitute_variables(cmd.get_response(), var_map)
            clean, delete_after, channel_sends, embed_data = await cc_engine.process_actions(raw, after, self.bot)

            if clean or embed_data:
                da = delete_after or cmd.delete_response_after or None
                try:
                    if cmd.embed or embed_data:
                        await after.channel.send(embed=_build_embed_from_data(cmd, clean, embed_data), delete_after=da)
                    else:
                        await after.channel.send(clean, delete_after=da)
                except discord.HTTPException:
                    pass

            await self._save_command(after.guild.id, cmd)
            break

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        await self._ensure_loaded(message.guild.id)
        cmds = self._get_commands(message.guild.id)
        if not cmds:
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        prefix = await get_guild_prefix(message.guild.id)
        prefix_stripped = message.content[len(prefix):].strip() if message.content.startswith(prefix) else message.content
        args = prefix_stripped.split()[1:] if prefix_stripped else []

        for trigger, cmd in cmds.items():
            if not cmd.enabled or cmd.trigger_type in (TRIGGER_REACTION, TRIGGER_INTERVAL, TRIGGER_MSG_EDIT):
                continue
            if not cmd.matches(message.content, prefix_stripped):
                continue

            group = self._get_groups(message.guild.id).get(cmd.group) if cmd.group else None
            ok, reason = cmd.check_restrictions(message.author, message.channel, group)
            if not ok:
                try:
                    await message.channel.send(view=error_layout("Restricted", reason), delete_after=5)
                except discord.HTTPException:
                    pass
                return

            remaining = cmd.check_cooldown(message.author.id)
            if remaining > 0:
                try:
                    await message.channel.send(
                        view=error_layout("On Cooldown", f"Try again in `{remaining:.1f}s`."), delete_after=5
                    )
                except discord.HTTPException:
                    pass
                return

            cmd.apply_cooldown(message.author.id)
            cmd.uses += 1

            var_map = cc_engine.build_variables(message, args)
            if cmd.trigger_type == cc_engine.TRIGGER_REGEX:
                import re
                try:
                    flags = 0 if cmd.case_sensitive else re.IGNORECASE
                    m = re.search(cmd.trigger, message.content, flags)
                    if m:
                        for i, grp in enumerate(m.groups(), 1):
                            var_map[f"match{i}"] = grp or ""
                        var_map["match0"] = m.group(0)
                except re.error:
                    pass

            raw_response = cc_engine.substitute_variables(cmd.get_response(), var_map)
            clean_response, delete_after_secs, channel_sends, embed_data = await cc_engine.process_actions(raw_response, message, self.bot)

            da = delete_after_secs or cmd.delete_response_after or None
            if clean_response or embed_data:
                try:
                    if cmd.embed or embed_data:
                        await message.channel.send(embed=_build_embed_from_data(cmd, clean_response, embed_data), delete_after=da)
                    else:
                        await message.channel.send(clean_response, delete_after=da)
                except discord.HTTPException:
                    pass

            for ch, msg in channel_sends:
                try:
                    await ch.send(msg)
                except discord.HTTPException:
                    pass

            if cmd.delete_trigger:
                if cmd.delete_trigger_after:
                    await asyncio.sleep(cmd.delete_trigger_after)
                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

            await self._save_command(message.guild.id, cmd)
            break

    @commands.group(name="cc", aliases=["customcommand", "customcmd"], invoke_without_command=True, help="Manage custom text commands for this server.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def cc_group(self, ctx: commands.Context):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        if not cmds:
            return await ctx.send(view=info_layout(f"{e('settings')} Custom Commands", "No custom commands configured.\nUse `cc add <trigger> <response>` to create one."))
        await ctx.send(view=info_layout(f"{e('settings')} Custom Commands", f"**{len(cmds)}** command(s) configured.\nUse `cc list` to view them all."))

    @cc_group.command(name="add", help="Add a custom command. Usage: cc add <trigger> <response>")
    @has_guild_permission("manage_guild")
    async def cc_add(self, ctx: commands.Context, trigger: str, *, response: str):
        e = emoji_manager.get
        trigger_key = trigger.lower()
        if len(trigger_key) > 50:
            return await ctx.send(view=error_layout("Too Long", "Trigger must be under 50 characters."))
        if len(response) > 4000:
            return await ctx.send(view=error_layout("Too Long", "Response must be under 4000 characters."))
        if self.bot.get_command(trigger_key):
            return await ctx.send(view=error_layout("Reserved Name", f"`{trigger_key}` conflicts with an existing bot command."))

        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        if len(cmds) >= MAX_COMMANDS_PER_GUILD:
            return await ctx.send(view=error_layout("Limit Reached", f"Maximum {MAX_COMMANDS_PER_GUILD} custom commands per server."))

        nid = self._alloc_id()
        cmd = CustomCommand(trigger_key, {"responses": [response], "numeric_id": nid})
        self._cache.setdefault(ctx.guild.id, {})[trigger_key] = cmd
        await self._save_command(ctx.guild.id, cmd, created_by=ctx.author.id)
        await ctx.send(view=success_layout(f"{e('check')} Command Created", f"`{trigger_key}` created.\n**Type:** `command` · **Responses:** `1`"))

    @cc_group.command(name="remove", aliases=["delete"], help="Remove a custom command.")
    @has_guild_permission("manage_guild")
    async def cc_remove(self, ctx: commands.Context, trigger: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        if trigger not in self._get_commands(ctx.guild.id):
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        del self._cache[ctx.guild.id][trigger]
        await self._delete_command(ctx.guild.id, trigger)
        await ctx.send(view=success_layout(f"{e('check')} Removed", f"Command `{trigger}` removed."))

    @cc_group.command(name="edit", help="Edit the primary response of a command.")
    @has_guild_permission("manage_guild")
    async def cc_edit(self, ctx: commands.Context, trigger: str, *, response: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        cmd.responses[0] = response
        await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=success_layout(f"{e('check')} Updated", f"Response for `{trigger}` updated."))

    @cc_group.command(name="addresponse", aliases=["ar"], help="Add an extra random response to a command.")
    @has_guild_permission("manage_guild")
    async def cc_addresponse(self, ctx: commands.Context, trigger: str, *, response: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        if len(cmd.responses) >= MAX_RESPONSES_PER_COMMAND:
            return await ctx.send(view=error_layout("Limit Reached", f"Maximum {MAX_RESPONSES_PER_COMMAND} responses per command."))
        cmd.responses.append(response)
        await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=success_layout(f"{e('check')} Response Added", f"`{trigger}` now has **{len(cmd.responses)}** responses (picked randomly)."))

    @cc_group.command(name="removeresponse", aliases=["rr"], help="Remove a response by index (1-based).")
    @has_guild_permission("manage_guild")
    async def cc_removeresponse(self, ctx: commands.Context, trigger: str, index: int):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        if len(cmd.responses) <= 1:
            return await ctx.send(view=error_layout("Cannot Remove", "Cannot remove the only response. Use `cc edit` instead."))
        if not 1 <= index <= len(cmd.responses):
            return await ctx.send(view=error_layout("Invalid Index", f"Index must be 1–{len(cmd.responses)}."))
        cmd.responses.pop(index - 1)
        await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=success_layout(f"{e('check')} Response Removed", f"Response `{index}` removed from `{trigger}`."))

    @cc_group.command(name="triggertype", aliases=["tt"], help="Set trigger type: command, starts_with, contains, regex, exact_match, reaction, interval, message_edit.")
    @has_guild_permission("manage_guild")
    async def cc_triggertype(self, ctx: commands.Context, trigger: str, trigger_type: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        trigger_type = trigger_type.lower()
        if trigger_type not in ALL_TRIGGER_TYPES:
            return await ctx.send(view=error_layout("Invalid Type", f"Choose: {', '.join(f'`{t}`' for t in ALL_TRIGGER_TYPES)}"))
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        if trigger_type == cc_engine.TRIGGER_REGEX:
            import re
            try:
                re.compile(cmd.trigger)
            except re.error as ex:
                return await ctx.send(view=error_layout("Invalid Regex", f"Current trigger is not a valid regex: `{ex}`"))
        cmd.trigger_type = trigger_type
        await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=success_layout(f"{e('check')} Trigger Type Set", f"`{trigger}` now uses `{trigger_type}`."))

    @cc_group.command(name="casesensitive", aliases=["cs"], help="Toggle case sensitivity for a command.")
    @has_guild_permission("manage_guild")
    async def cc_casesensitive(self, ctx: commands.Context, trigger: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        cmd.case_sensitive = not cmd.case_sensitive
        await self._save_command(ctx.guild.id, cmd)
        state = "enabled" if cmd.case_sensitive else "disabled"
        await ctx.send(view=success_layout(f"{e('check')} Case Sensitivity {state.title()}", f"Case sensitivity {state} for `{trigger}`."))

    @cc_group.command(name="cooldown", aliases=["cd"], help="Set a cooldown. Usage: cc cooldown <trigger> <seconds> [user|global]")
    @has_guild_permission("manage_guild")
    async def cc_cooldown(self, ctx: commands.Context, trigger: str, seconds: int, cooldown_type: str = "user"):
        e = emoji_manager.get
        trigger = trigger.lower()
        if cooldown_type not in ("user", "global"):
            return await ctx.send(view=error_layout("Invalid Type", "Cooldown type must be `user` or `global`."))
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        cmd.cooldown = max(0, seconds)
        cmd.cooldown_type = cooldown_type
        await self._save_command(ctx.guild.id, cmd)
        if seconds == 0:
            await ctx.send(view=success_layout(f"{e('check')} Cooldown Removed", f"Cooldown removed from `{trigger}`."))
        else:
            await ctx.send(view=success_layout(f"{e('check')} Cooldown Set", f"`{trigger}` now has a `{seconds}s` cooldown ({cooldown_type})."))

    @cc_group.command(name="deleteafter", aliases=["da"], help="Auto-delete trigger/response. Usage: cc deleteafter <trigger> <trigger_secs> <response_secs>")
    @has_guild_permission("manage_guild")
    async def cc_deleteafter(self, ctx: commands.Context, trigger: str, trigger_secs: int = 0, response_secs: int = 0):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        cmd.delete_trigger = trigger_secs > 0
        cmd.delete_trigger_after = max(0, trigger_secs)
        cmd.delete_response_after = max(0, response_secs)
        await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=_cc_layout(f"{e('check')} Auto-Delete Set", {
            "Trigger": "disabled" if not trigger_secs else f"{trigger_secs}s",
            "Response": "disabled" if not response_secs else f"{response_secs}s",
        }))

    @cc_group.command(name="restrict", help="Restrict a command to specific roles/channels. Usage: cc restrict <trigger> <allow|deny|clear> <role|channel> <targets...>")
    @has_guild_permission("manage_guild")
    async def cc_restrict(self, ctx: commands.Context, trigger: str, mode: str, target_type: str, *, targets: str = ""):
        e = emoji_manager.get
        trigger = trigger.lower()
        mode, target_type = mode.lower(), target_type.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        if mode not in ("allow", "deny", "clear"):
            return await ctx.send(view=error_layout("Invalid Mode", "Mode must be `allow`, `deny`, or `clear`."))
        if target_type not in ("role", "channel"):
            return await ctx.send(view=error_layout("Invalid Type", "Target type must be `role` or `channel`."))

        if mode == "clear":
            if target_type == "role":
                cmd.allowed_roles.clear()
                cmd.denied_roles.clear()
            else:
                cmd.allowed_channels.clear()
                cmd.denied_channels.clear()
            await self._save_command(ctx.guild.id, cmd)
            return await ctx.send(view=success_layout(f"{e('check')} Cleared", f"Cleared {target_type} restrictions for `{trigger}`."))

        ids = [int(m.strip("<#@&>")) for m in targets.split() if m.strip("<#@&>").isdigit()]
        if not ids:
            return await ctx.send(view=error_layout("No Targets", "No valid role/channel IDs or mentions found."))

        if target_type == "role":
            if mode == "allow":
                cmd.allowed_roles = list(set(cmd.allowed_roles + ids))
            else:
                cmd.denied_roles = list(set(cmd.denied_roles + ids))
        else:
            if mode == "allow":
                cmd.allowed_channels = list(set(cmd.allowed_channels + ids))
            else:
                cmd.denied_channels = list(set(cmd.denied_channels + ids))

        await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=success_layout(f"{e('check')} Restriction Applied", f"{mode.title()}ed {len(ids)} {target_type}(s) for `{trigger}`."))

    @cc_group.command(name="toggle", help="Enable or disable a custom command.")
    @has_guild_permission("manage_guild")
    async def cc_toggle(self, ctx: commands.Context, trigger: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        cmd.enabled = not cmd.enabled
        await self._save_command(ctx.guild.id, cmd)
        state = "enabled" if cmd.enabled else "disabled"
        await ctx.send(view=success_layout(f"{e('check')} Command {state.title()}", f"`{trigger}` is now {state}."))

    @cc_group.command(name="embed", help="Toggle embed mode and optionally set title/color.")
    @has_guild_permission("manage_guild")
    async def cc_embed(self, ctx: commands.Context, trigger: str, title: Optional[str] = None, color: Optional[str] = None):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        cmd.embed = not cmd.embed
        if title:
            cmd.embed_title = title
        if color:
            try:
                int(color.lstrip("#"), 16)
                cmd.embed_color = color.lstrip("#")
            except ValueError:
                return await ctx.send(view=error_layout("Invalid Color", "Provide a valid hex color."))
        await self._save_command(ctx.guild.id, cmd)
        state = "enabled" if cmd.embed else "disabled"
        await ctx.send(view=success_layout(f"{e('check')} Embed Mode {state.title()}", f"Embed mode {state} for `{trigger}`."))

    @cc_group.command(name="setgroup", help="Assign a command to a group.")
    @has_guild_permission("manage_guild")
    async def cc_setgroup(self, ctx: commands.Context, trigger: str, *, group_name: Optional[str] = None):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        if group_name and group_name not in self._get_groups(ctx.guild.id):
            return await ctx.send(view=error_layout("Group Not Found", f"Group `{group_name}` not found. Create it with `cc group create`."))
        cmd.group = group_name
        await self._save_command(ctx.guild.id, cmd)
        msg = f"`{trigger}` assigned to group **{group_name}**." if group_name else f"`{trigger}` removed from its group."
        await ctx.send(view=success_layout(f"{e('check')} Group Updated", msg))

    @cc_group.command(name="describe", help="Set a description for a custom command.")
    @has_guild_permission("manage_guild")
    async def cc_describe(self, ctx: commands.Context, trigger: str, *, description: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        cmd.description = description[:200]
        await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=success_layout(f"{e('check')} Description Updated", f"Description updated for `{trigger}`."))

    @cc_group.command(name="info", help="View full details about a custom command.")
    async def cc_info(self, ctx: commands.Context, trigger: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))

        fields = {
            "Type": f"`{cmd.trigger_type}`",
            "Enabled": f"`{cmd.enabled}`",
            "Case Sensitive": f"`{cmd.case_sensitive}`",
            "Uses": f"`{cmd.uses}`",
            "Responses": f"`{len(cmd.responses)}`",
            "Embed": f"`{cmd.embed}`",
            "Cooldown": f"`{cmd.cooldown}s` ({cmd.cooldown_type})",
            "Delete Trigger After": f"`{cmd.delete_trigger_after or 'off'}s`",
            "Delete Response After": f"`{cmd.delete_response_after or 'off'}s`",
            "Group": f"`{cmd.group or 'None'}`",
            "Allowed Roles": ", ".join(f"<@&{r}>" for r in cmd.allowed_roles) or "None",
            "Denied Roles": ", ".join(f"<@&{r}>" for r in cmd.denied_roles) or "None",
            "Allowed Channels": ", ".join(f"<#{c}>" for c in cmd.allowed_channels) or "None",
            "Denied Channels": ", ".join(f"<#{c}>" for c in cmd.denied_channels) or "None",
        }
        if cmd.description:
            fields["Description"] = cmd.description
        fields["Primary Response"] = f"```\n{cmd.responses[0][:300]}\n```"
        await ctx.send(view=_cc_layout(f"{e('history')} Command: {trigger}", fields))

    @cc_group.command(name="list", help="List all custom commands, optionally filtered by group.")
    async def cc_list(self, ctx: commands.Context, group: Optional[str] = None):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        if not cmds:
            return await ctx.send(view=info_layout(f"{e('history')} Custom Commands", "No custom commands configured."))
        filtered = {t: c for t, c in cmds.items() if group is None or c.group == group}
        if not filtered:
            return await ctx.send(view=info_layout(f"{e('history')} Custom Commands", f"No commands in group `{group}`."))

        lines = []
        for trigger, cmd in sorted(filtered.items()):
            status = "🟢" if cmd.enabled else "🔴"
            cd = f" ⏱`{cmd.cooldown}s`" if cmd.cooldown else ""
            grp = f" [{cmd.group}]" if cmd.group else ""
            lines.append(f"{status} `{trigger}` — `{cmd.trigger_type}`{cd}{grp}")
        await ctx.send(view=info_layout(f"{e('history')} Custom Commands ({len(filtered)}/{MAX_COMMANDS_PER_GUILD})", "\n".join(lines)))

    @cc_group.command(name="variables", aliases=["vars"], help="Show all available template variables.")
    async def cc_variables(self, ctx: commands.Context):
        e = emoji_manager.get
        body = (
            "**User:** `{user}` `{username}` `{userid}` `{usertag}` `{useravatar}`\n\n"
            "**Server:** `{server}` `{serverid}` `{membercount}` `{servericon}`\n\n"
            "**Channel:** `{channel}` `{channelname}` `{channelid}`\n\n"
            "**Arguments:** `{args}` `{arg1}` `{arg2}`... `{argscount}`\n\n"
            "**Regex Captures:** `{match0}` `{match1}`...\n\n"
            "**Message:** `{msgid}` `{msglink}` `{timestamp}`\n\n"
            "**Blocks:** `{if arg1 == yes}...{else}...{end}` · `{random}a{|}b{endrandom}`"
        )
        await ctx.send(view=info_layout(f"{e('info')} Template Variables", body))

    @cc_group.command(name="actions", aliases=["acts"], help="Show all available action tags for custom command responses.")
    async def cc_actions(self, ctx: commands.Context):
        await ctx.send(view=ActionsLayout(ctx.author.id))

    @cc_group.command(name="interval", help="Set a command to run on an interval. Usage: cc interval <trigger> <minutes> [#channel]")
    @has_guild_permission("manage_guild")
    async def cc_interval(self, ctx: commands.Context, trigger: str, minutes: int, channel: Optional[discord.TextChannel] = None):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        if not 1 <= minutes <= 10080:
            return await ctx.send(view=error_layout("Invalid Duration", "Interval must be between 1 minute and 7 days (10080 minutes)."))
        channel = channel or ctx.channel
        cmd.trigger_type = TRIGGER_INTERVAL
        cmd.interval_minutes = minutes
        cmd.interval_channel = channel.id
        cmd.interval_next_run = time.time() + (minutes * 60)
        await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=success_layout(
            f"{e('check')} Interval Set",
            f"`{trigger}` runs every **{minutes}** minute(s) in {channel.mention}.\nFirst run: <t:{int(cmd.interval_next_run)}:R>",
        ))

    @cc_group.command(name="reaction", help="Set a command to fire on a reaction. Usage: cc reaction <trigger> <emoji> [message_id]")
    @has_guild_permission("manage_guild")
    async def cc_reaction(self, ctx: commands.Context, trigger: str, emoji: str, message_id: Optional[int] = None):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        cmd.trigger_type = TRIGGER_REACTION
        cmd.reaction_emoji = emoji
        cmd.reaction_message_id = message_id
        await self._save_command(ctx.guild.id, cmd)
        scope = f"on message `{message_id}`" if message_id else "on any message"
        await ctx.send(view=success_layout(f"{e('check')} Reaction Trigger Set", f"`{trigger}` fires on {emoji} {scope}."))

    @cc_group.command(name="exec", aliases=["run"], help="Execute a custom command by name or numeric ID.")
    @has_guild_permission("manage_guild")
    async def cc_exec(self, ctx: commands.Context, trigger_or_id: str, *, args: str = ""):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        cmd = cmds.get(trigger_or_id.lower())
        if not cmd and trigger_or_id.isdigit():
            cmd = next((c for c in cmds.values() if c.numeric_id == int(trigger_or_id)), None)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger_or_id}` not found."))
        if not cmd.enabled:
            return await ctx.send(view=error_layout("Disabled", f"Command `{cmd.trigger}` is disabled."))

        arg_list = args.split() if args else []
        var_map = cc_engine.build_variables(ctx.message, arg_list)
        raw = cc_engine.substitute_variables(cmd.get_response(), var_map)
        clean, delete_after, channel_sends, embed_data = await cc_engine.process_actions(raw, ctx.message, self.bot)
        da = delete_after or cmd.delete_response_after or None

        if clean or embed_data:
            if cmd.embed or embed_data:
                await ctx.send(embed=_build_embed_from_data(cmd, clean, embed_data), delete_after=da)
            else:
                await ctx.send(clean, delete_after=da)
        for ch, msg in channel_sends:
            try:
                await ch.send(msg)
            except discord.HTTPException:
                pass

        cmd.uses += 1
        await self._save_command(ctx.guild.id, cmd)

    @cc_group.command(name="id", help="Show the numeric ID of a custom command (for use with exec).")
    async def cc_id(self, ctx: commands.Context, trigger: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        await ctx.send(view=success_layout(f"{e('info')} Numeric ID", f"`{trigger}` has numeric ID: `{cmd.numeric_id}`."))

    @cc_group.command(name="export", help="Export all custom commands as a JSON file.")
    @has_guild_permission("manage_guild")
    async def cc_export(self, ctx: commands.Context):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        if not cmds:
            return await ctx.send(view=error_layout("Nothing to Export", "No custom commands to export."))
        data = {trigger: cmd.to_dict() for trigger, cmd in cmds.items()}
        buf = io.BytesIO(json.dumps(data, indent=2).encode())
        buf.seek(0)
        await ctx.send(
            view=success_layout(f"{e('check')} Exported", f"Exported **{len(data)}** custom command(s)."),
            file=discord.File(buf, filename=f"cc_export_{ctx.guild.id}.json"),
        )

    @cc_group.command(name="import", help="Import custom commands from a JSON file (attach the file).")
    @has_guild_permission("manage_guild")
    async def cc_import(self, ctx: commands.Context):
        e = emoji_manager.get
        if not ctx.message.attachments:
            return await ctx.send(view=error_layout("No Attachment", "Attach a JSON file exported with `cc export`."))
        attachment = ctx.message.attachments[0]
        if not attachment.filename.endswith(".json"):
            return await ctx.send(view=error_layout("Invalid File", "File must be a `.json` file."))

        raw_bytes = await attachment.read()
        try:
            data = json.loads(raw_bytes.decode())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return await ctx.send(view=error_layout("Invalid JSON", "Could not parse the attached file."))

        await self._ensure_loaded(ctx.guild.id)
        existing = self._get_commands(ctx.guild.id)
        imported, skipped = 0, 0

        for trigger, cmd_data in data.items():
            trigger = trigger.lower()
            if len(existing) + imported >= MAX_COMMANDS_PER_GUILD or trigger in existing:
                skipped += 1
                continue
            cmd_data["numeric_id"] = self._alloc_id()
            new_cmd = CustomCommand(trigger, cmd_data)
            self._cache.setdefault(ctx.guild.id, {})[trigger] = new_cmd
            await self._save_command(ctx.guild.id, new_cmd, created_by=ctx.author.id)
            imported += 1

        msg = f"Imported **{imported}** command(s)."
        if skipped:
            msg += f" Skipped **{skipped}** (duplicates or limit reached)."
        await ctx.send(view=success_layout(f"{e('check')} Import Complete", msg))

    @cc_group.command(name="search", help="Search custom commands by trigger name or response content.")
    async def cc_search(self, ctx: commands.Context, *, query: str):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        query_lower = query.lower()
        matches = {
            t: c for t, c in cmds.items()
            if query_lower in t or any(query_lower in r.lower() for r in c.responses) or query_lower in (c.description or "").lower()
        }
        if not matches:
            return await ctx.send(view=info_layout(f"{e('info')} Search", f"No commands matching `{query}`."))
        lines = [f"`{t}` — `{c.trigger_type}`" for t, c in list(matches.items())[:15]]
        await ctx.send(view=info_layout(f"{e('info')} Search: \"{query}\" ({len(matches)} results)", "\n".join(lines)))

    @cc_group.command(name="resetcd", help="Reset the cooldown of a command for a specific user or globally.")
    @has_guild_permission("manage_guild")
    async def cc_resetcd(self, ctx: commands.Context, trigger: str, member: Optional[discord.Member] = None):
        e = emoji_manager.get
        trigger = trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmd = self._get_commands(ctx.guild.id).get(trigger)
        if not cmd:
            return await ctx.send(view=error_layout("Not Found", f"Command `{trigger}` not found."))
        if member:
            cmd._cooldown_cache.pop(member.id, None)
            await ctx.send(view=success_layout(f"{e('check')} Cooldown Reset", f"Cooldown reset for {member.mention} on `{trigger}`."))
        else:
            cmd._cooldown_cache.clear()
            await ctx.send(view=success_layout(f"{e('check')} Cooldowns Reset", f"All cooldowns reset for `{trigger}`."))

    @cc_group.command(name="rename", help="Rename a custom command trigger.")
    @has_guild_permission("manage_guild")
    async def cc_rename(self, ctx: commands.Context, old_trigger: str, new_trigger: str):
        e = emoji_manager.get
        old_trigger, new_trigger = old_trigger.lower(), new_trigger.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        if old_trigger not in cmds:
            return await ctx.send(view=error_layout("Not Found", f"Command `{old_trigger}` not found."))
        if new_trigger in cmds:
            return await ctx.send(view=error_layout("Already Exists", f"Command `{new_trigger}` already exists."))
        if self.bot.get_command(new_trigger):
            return await ctx.send(view=error_layout("Reserved Name", f"`{new_trigger}` conflicts with an existing bot command."))

        cmd = cmds.pop(old_trigger)
        cmd.trigger = new_trigger
        cmds[new_trigger] = cmd
        await self._delete_command(ctx.guild.id, old_trigger)
        await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=success_layout(f"{e('check')} Renamed", f"`{old_trigger}` → `{new_trigger}`."))

    @cc_group.command(name="copy", help="Copy a custom command to a new trigger name.")
    @has_guild_permission("manage_guild")
    async def cc_copy(self, ctx: commands.Context, source: str, *, destination: str):
        e = emoji_manager.get
        source, destination = source.lower(), destination.lower()
        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        if source not in cmds:
            return await ctx.send(view=error_layout("Not Found", f"Command `{source}` not found."))
        if destination in cmds:
            return await ctx.send(view=error_layout("Already Exists", f"Command `{destination}` already exists."))
        if len(cmds) >= MAX_COMMANDS_PER_GUILD:
            return await ctx.send(view=error_layout("Limit Reached", f"Maximum {MAX_COMMANDS_PER_GUILD} custom commands per server."))

        data = cmds[source].to_dict()
        data["numeric_id"] = self._alloc_id()
        data["uses"] = 0
        new_cmd = CustomCommand(destination, data)
        self._cache[ctx.guild.id][destination] = new_cmd
        await self._save_command(ctx.guild.id, new_cmd, created_by=ctx.author.id)
        await ctx.send(view=success_layout(f"{e('check')} Copied", f"`{source}` → `{destination}`."))

    @cc_group.command(name="stats", help="Show usage statistics for custom commands in this server.")
    async def cc_stats(self, ctx: commands.Context):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        if not cmds:
            return await ctx.send(view=info_layout(f"{e('history')} Stats", "No custom commands configured."))
        sorted_cmds = sorted(cmds.items(), key=lambda x: x[1].uses, reverse=True)[:10]
        lines = [f"`{i+1}.` `{t}` — **{c.uses}** uses" for i, (t, c) in enumerate(sorted_cmds)]
        total = sum(c.uses for c in cmds.values())
        await ctx.send(view=info_layout(f"{e('history')} Custom Command Stats", f"**Total uses:** `{total}`\n\n" + "\n".join(lines)))

    @cc_group.command(name="enableall", help="Enable all custom commands at once.")
    @has_guild_permission("manage_guild")
    async def cc_enableall(self, ctx: commands.Context):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        for cmd in cmds.values():
            cmd.enabled = True
            await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=success_layout(f"{e('check')} All Enabled", f"All **{len(cmds)}** command(s) enabled."))

    @cc_group.command(name="disableall", help="Disable all custom commands at once.")
    @has_guild_permission("manage_guild")
    async def cc_disableall(self, ctx: commands.Context):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        for cmd in cmds.values():
            cmd.enabled = False
            await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=success_layout(f"{e('check')} All Disabled", f"All **{len(cmds)}** command(s) disabled."))

    @cc_group.command(name="purge", help="Delete all custom commands for this server. Requires confirmation.")
    @has_guild_permission("manage_guild")
    async def cc_purge(self, ctx: commands.Context):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        cmds = self._get_commands(ctx.guild.id)
        if not cmds:
            return await ctx.send(view=error_layout("Nothing to Delete", "No custom commands to delete."))

        confirm = ConfirmLayout(
            f"{e('cross')} Confirm Purge",
            f"This will permanently delete all **{len(cmds)}** custom command(s). This cannot be undone.",
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "Purge cancelled."))

        count = len(cmds)
        for trigger in list(cmds.keys()):
            await self._delete_command(ctx.guild.id, trigger)
        self._cache[ctx.guild.id] = {}
        await msg.edit(view=success_layout(f"{e('check')} Purged", f"Deleted all **{count}** custom command(s)."))

    @cc_group.group(name="group", invoke_without_command=True, help="Custom command group management.")
    @has_guild_permission("manage_guild")
    async def cc_groupcmd(self, ctx: commands.Context):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        groups = self._get_groups(ctx.guild.id)
        if not groups:
            return await ctx.send(view=info_layout(f"{e('settings')} Command Groups", "No groups configured.\nUse `cc group create <name>` to create one."))
        await ctx.send(view=info_layout(f"{e('settings')} Command Groups", f"**{len(groups)}** group(s) configured.\nUse `cc group list` to view them."))

    @cc_groupcmd.command(name="create", help="Create a command group.")
    @has_guild_permission("manage_guild")
    async def ccg_create(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        if len(name) > 50:
            return await ctx.send(view=error_layout("Too Long", "Group name must be under 50 characters."))
        await self._ensure_loaded(ctx.guild.id)
        groups = self._get_groups(ctx.guild.id)
        if len(groups) >= MAX_GROUPS_PER_GUILD:
            return await ctx.send(view=error_layout("Limit Reached", f"Maximum {MAX_GROUPS_PER_GUILD} groups per server."))
        if name in groups:
            return await ctx.send(view=error_layout("Already Exists", f"Group `{name}` already exists."))
        group = CCGroup({"name": name})
        self._groups.setdefault(ctx.guild.id, {})[name] = group
        await self._save_group(ctx.guild.id, group)
        await ctx.send(view=success_layout(f"{e('check')} Group Created", f"Group **{name}** created."))

    @cc_groupcmd.command(name="delete", help="Delete a command group.")
    @has_guild_permission("manage_guild")
    async def ccg_delete(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        groups = self._get_groups(ctx.guild.id)
        if name not in groups:
            return await ctx.send(view=error_layout("Not Found", f"Group `{name}` not found."))
        del groups[name]
        await self._delete_group(ctx.guild.id, name)
        for cmd in self._get_commands(ctx.guild.id).values():
            if cmd.group == name:
                cmd.group = None
                await self._save_command(ctx.guild.id, cmd)
        await ctx.send(view=success_layout(f"{e('check')} Group Deleted", f"Group **{name}** deleted."))

    @cc_groupcmd.command(name="list", help="List all command groups.")
    async def ccg_list(self, ctx: commands.Context):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        groups = self._get_groups(ctx.guild.id)
        if not groups:
            return await ctx.send(view=info_layout(f"{e('settings')} Command Groups", "No groups configured."))
        cmds = self._get_commands(ctx.guild.id)
        lines = []
        for name in groups:
            count = sum(1 for c in cmds.values() if c.group == name)
            lines.append(f"**{name}** — `{count}` command(s)")
        await ctx.send(view=info_layout(f"{e('settings')} Command Groups ({len(groups)}/{MAX_GROUPS_PER_GUILD})", "\n".join(lines)))

    @cc_groupcmd.command(name="restrict", help="Apply role/channel restrictions to a group.")
    @has_guild_permission("manage_guild")
    async def ccg_restrict(self, ctx: commands.Context, group_name: str, mode: str, target_type: str, *, targets: str = ""):
        e = emoji_manager.get
        await self._ensure_loaded(ctx.guild.id)
        groups = self._get_groups(ctx.guild.id)
        if group_name not in groups:
            return await ctx.send(view=error_layout("Not Found", f"Group `{group_name}` not found."))
        group = groups[group_name]
        mode, target_type = mode.lower(), target_type.lower()
        if mode not in ("allow", "deny", "clear"):
            return await ctx.send(view=error_layout("Invalid Mode", "Mode must be `allow`, `deny`, or `clear`."))
        if target_type not in ("role", "channel"):
            return await ctx.send(view=error_layout("Invalid Type", "Target type must be `role` or `channel`."))

        if mode == "clear":
            if target_type == "role":
                group.allowed_roles.clear()
                group.denied_roles.clear()
            else:
                group.allowed_channels.clear()
                group.denied_channels.clear()
            await self._save_group(ctx.guild.id, group)
            return await ctx.send(view=success_layout(f"{e('check')} Cleared", "Cleared group restrictions."))

        ids = [int(m.strip("<#@&>")) for m in targets.split() if m.strip("<#@&>").isdigit()]
        if not ids:
            return await ctx.send(view=error_layout("No Targets", "No valid IDs found."))

        if target_type == "role":
            if mode == "allow":
                group.allowed_roles = list(set(group.allowed_roles + ids))
            else:
                group.denied_roles = list(set(group.denied_roles + ids))
        else:
            if mode == "allow":
                group.allowed_channels = list(set(group.allowed_channels + ids))
            else:
                group.denied_channels = list(set(group.denied_channels + ids))

        await self._save_group(ctx.guild.id, group)
        await ctx.send(view=success_layout(f"{e('check')} Restriction Applied", f"Group **{group_name}** {mode}ed {len(ids)} {target_type}(s)."))


async def setup(bot: commands.Bot):
    await bot.add_cog(CustomCommands(bot))
