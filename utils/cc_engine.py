import random
import re
import time
from typing import Optional

import discord

TRIGGER_COMMAND = "command"
TRIGGER_STARTS = "starts_with"
TRIGGER_CONTAINS = "contains"
TRIGGER_REGEX = "regex"
TRIGGER_EXACT = "exact_match"
TRIGGER_REACTION = "reaction"
TRIGGER_INTERVAL = "interval"
TRIGGER_MSG_EDIT = "message_edit"

ALL_TRIGGER_TYPES = [
    TRIGGER_COMMAND, TRIGGER_STARTS, TRIGGER_CONTAINS,
    TRIGGER_REGEX, TRIGGER_EXACT, TRIGGER_REACTION,
    TRIGGER_INTERVAL, TRIGGER_MSG_EDIT,
]

ACTION_PATTERN = re.compile(
    r"\{("
    r"addrole|removerole|addroleto|removerolefrom"
    r"|togglerole"
    r"|dm|dmmember"
    r"|deleteafter|silentdelete|deletetrigger"
    r"|react|reactremove"
    r"|sendchannel|sendreply"
    r"|kick|ban|softban|unban|timeout|untimeout"
    r"|mute|unmute"
    r"|setnick|resetnick"
    r"|createchannel|deletechannel|lockchannel|unlockchannel|hidechannel|showchannel"
    r"|createrole|deleterole|editrole"
    r"|log|warn"
    r"|sleep|noresponse"
    r"|settitle|setcolor|setfooter|setthumbnail|setimage|addfield"
    r"):([^}]*)\}",
    re.IGNORECASE,
)

VAR_PATTERN = re.compile(r"\{(\w+(?:\d+)?)\}")


class CCGroup:
    def __init__(self, data: dict):
        self.name = data.get("name", "Unnamed")
        self.allowed_channels = data.get("allowed_channels", [])
        self.denied_channels = data.get("denied_channels", [])
        self.allowed_roles = data.get("allowed_roles", [])
        self.denied_roles = data.get("denied_roles", [])

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "allowed_channels": self.allowed_channels,
            "denied_channels": self.denied_channels,
            "allowed_roles": self.allowed_roles,
            "denied_roles": self.denied_roles,
        }


class CustomCommand:
    def __init__(self, trigger: str, data: dict):
        self.trigger = trigger
        self.trigger_type = data.get("trigger_type", TRIGGER_COMMAND)
        self.responses = data.get("responses", [data.get("response", "")])
        self.case_sensitive = data.get("case_sensitive", False)
        self.embed = data.get("embed", False)
        self.embed_color = data.get("embed_color")
        self.embed_title = data.get("embed_title")
        self.delete_trigger = data.get("delete_trigger", False)
        self.delete_trigger_after = data.get("delete_trigger_after", 0)
        self.delete_response_after = data.get("delete_response_after", 0)
        self.cooldown = data.get("cooldown", 0)
        self.cooldown_type = data.get("cooldown_type", "user")
        self.allowed_channels = data.get("allowed_channels", [])
        self.denied_channels = data.get("denied_channels", [])
        self.allowed_roles = data.get("allowed_roles", [])
        self.denied_roles = data.get("denied_roles", [])
        self.group = data.get("group")
        self.enabled = data.get("enabled", True)
        self.uses = data.get("uses", 0)
        self.description = data.get("description", "")
        self.numeric_id = data.get("numeric_id", 0)
        self.reaction_emoji = data.get("reaction_emoji", "")
        self.reaction_message_id = data.get("reaction_message_id")
        self.interval_minutes = data.get("interval_minutes", 0)
        self.interval_channel = data.get("interval_channel")
        self.interval_next_run = data.get("interval_next_run", 0)
        self._cooldown_cache: dict = {}

    def to_dict(self) -> dict:
        return {
            "trigger_type": self.trigger_type,
            "responses": self.responses,
            "case_sensitive": self.case_sensitive,
            "embed": self.embed,
            "embed_color": self.embed_color,
            "embed_title": self.embed_title,
            "delete_trigger": self.delete_trigger,
            "delete_trigger_after": self.delete_trigger_after,
            "delete_response_after": self.delete_response_after,
            "cooldown": self.cooldown,
            "cooldown_type": self.cooldown_type,
            "allowed_channels": self.allowed_channels,
            "denied_channels": self.denied_channels,
            "allowed_roles": self.allowed_roles,
            "denied_roles": self.denied_roles,
            "group": self.group,
            "enabled": self.enabled,
            "uses": self.uses,
            "description": self.description,
            "numeric_id": self.numeric_id,
            "reaction_emoji": self.reaction_emoji,
            "reaction_message_id": self.reaction_message_id,
            "interval_minutes": self.interval_minutes,
            "interval_channel": self.interval_channel,
            "interval_next_run": self.interval_next_run,
        }

    def matches(self, content: str, prefix_stripped: str) -> bool:
        t = self.trigger if self.case_sensitive else self.trigger.lower()
        c = content if self.case_sensitive else content.lower()
        p = prefix_stripped if self.case_sensitive else prefix_stripped.lower()

        if self.trigger_type == TRIGGER_COMMAND:
            parts = p.split()
            return bool(parts) and parts[0] == t
        if self.trigger_type == TRIGGER_STARTS:
            return c.startswith(t)
        if self.trigger_type == TRIGGER_CONTAINS:
            return t in c
        if self.trigger_type == TRIGGER_EXACT:
            return c == t
        if self.trigger_type == TRIGGER_REGEX:
            try:
                flags = 0 if self.case_sensitive else re.IGNORECASE
                return bool(re.search(self.trigger, content, flags))
            except re.error:
                return False
        return False

    def check_cooldown(self, user_id: int) -> float:
        now = time.time()
        key = user_id if self.cooldown_type == "user" else "global"
        last = self._cooldown_cache.get(key, 0)
        remaining = self.cooldown - (now - last)
        return max(0.0, remaining)

    def apply_cooldown(self, user_id: int) -> None:
        key = user_id if self.cooldown_type == "user" else "global"
        self._cooldown_cache[key] = time.time()

    def check_restrictions(self, member: discord.Member, channel, group: Optional[CCGroup] = None) -> tuple[bool, Optional[str]]:
        member_role_ids = [r.id for r in member.roles]

        denied_roles = list(self.denied_roles)
        allowed_roles = list(self.allowed_roles)
        denied_channels = list(self.denied_channels)
        allowed_channels = list(self.allowed_channels)

        if group:
            denied_roles += group.denied_roles
            allowed_roles += group.allowed_roles
            denied_channels += group.denied_channels
            allowed_channels += group.allowed_channels

        if any(r in member_role_ids for r in denied_roles):
            return False, "You have a denied role for this command."
        if denied_channels and channel.id in denied_channels:
            return False, "This command is disabled in this channel."
        if allowed_roles and not any(r in member_role_ids for r in allowed_roles):
            return False, "You need a required role to use this command."
        if allowed_channels and channel.id not in allowed_channels:
            return False, "This command is not allowed in this channel."

        return True, None

    def get_response(self) -> str:
        responses = [r for r in self.responses if r.strip()]
        return random.choice(responses) if responses else ""


def build_variables(message: discord.Message, args: list[str]) -> dict:
    member = message.author
    guild = message.guild
    all_args = " ".join(args)
    var_map = {
        "user": member.mention,
        "username": member.display_name,
        "userid": str(member.id),
        "usertag": str(member),
        "useravatar": member.display_avatar.url,
        "server": guild.name,
        "serverid": str(guild.id),
        "servericon": guild.icon.url if guild.icon else "",
        "membercount": str(guild.member_count),
        "channel": message.channel.mention,
        "channelname": message.channel.name,
        "channelid": str(message.channel.id),
        "args": all_args,
        "argscount": str(len(args)),
        "msgid": str(message.id),
        "msglink": message.jump_url,
        "timestamp": f"<t:{int(message.created_at.timestamp())}:f>",
    }
    for i, arg in enumerate(args, 1):
        var_map[f"arg{i}"] = arg
    return var_map


def apply_conditionals(response: str, var_map: dict) -> str:
    def eval_condition(cond: str) -> bool:
        cond = cond.strip()
        parts = cond.split()
        if len(parts) == 3:
            left = var_map.get(parts[0].strip("{}"), parts[0])
            op = parts[1]
            right = parts[2]
            if op == "==":
                return left == right
            if op == "!=":
                return left != right
            if op in (">", ">=", "<", "<="):
                try:
                    l, r = float(left), float(right)
                    if op == ">":
                        return l > r
                    if op == ">=":
                        return l >= r
                    if op == "<":
                        return l < r
                    if op == "<=":
                        return l <= r
                except ValueError:
                    pass
        if cond.startswith("hasarg "):
            idx = cond[7:].strip()
            return f"arg{idx}" in var_map and bool(var_map[f"arg{idx}"])
        return bool(cond)

    pattern = re.compile(r"\{if ([^}]+)\}(.*?)(?:\{else\}(.*?))?\{end\}", re.DOTALL)

    def replacer(m: re.Match) -> str:
        cond_str, if_body, else_body = m.group(1), m.group(2), m.group(3) or ""
        return if_body.strip() if eval_condition(cond_str) else else_body.strip()

    for _ in range(5):
        new = pattern.sub(replacer, response)
        if new == response:
            break
        response = new
    return response


def apply_random_blocks(response: str) -> str:
    pattern = re.compile(r"\{random\}(.*?)\{endrandom\}", re.DOTALL)

    def replacer(m: re.Match) -> str:
        options = [o.strip() for o in m.group(1).split("{|}") if o.strip()]
        return random.choice(options) if options else ""

    return pattern.sub(replacer, response)


def resolve_role(guild: discord.Guild, ref: str):
    ref = ref.strip().strip("<@&>").strip()
    if ref.isdigit():
        return guild.get_role(int(ref))
    return discord.utils.get(guild.roles, name=ref)


def resolve_channel(guild: discord.Guild, ref: str):
    ref = ref.strip().strip("<#>").strip()
    if ref.isdigit():
        return guild.get_channel(int(ref))
    return discord.utils.get(guild.text_channels, name=ref)


def resolve_member(guild: discord.Guild, ref: str):
    ref = ref.strip().strip("<@!>").strip()
    if ref.isdigit():
        return guild.get_member(int(ref))
    return discord.utils.find(
        lambda m: m.display_name.lower() == ref.lower() or str(m).lower() == ref.lower(),
        guild.members,
    )


class ActionContext:
    def __init__(self, message: Optional[discord.Message]):
        self.message = message
        self.guild = message.guild if message else None
        self.author = message.author if message else None
        self.channel = message.channel if message else None
        self.delete_after: Optional[int] = None
        self.no_response = False
        self.channel_sends: list[tuple] = []
        self.embed_data: dict = {}


async def process_actions(response: str, message: Optional[discord.Message], bot) -> tuple[str, Optional[int], list, dict]:
    if not message or not message.guild:
        clean = ACTION_PATTERN.sub("", response).strip()
        return clean, None, [], {}

    ctx = ActionContext(message)
    guild = ctx.guild
    author = ctx.author

    for match in ACTION_PATTERN.finditer(response):
        action = match.group(1).lower()
        value = match.group(2).strip()

        try:
            if action == "addrole":
                role = resolve_role(guild, value)
                if role:
                    await author.add_roles(role, reason="Custom Command")

            elif action == "removerole":
                role = resolve_role(guild, value)
                if role:
                    await author.remove_roles(role, reason="Custom Command")

            elif action == "togglerole":
                role = resolve_role(guild, value)
                if role:
                    if role in author.roles:
                        await author.remove_roles(role, reason="Custom Command Toggle")
                    else:
                        await author.add_roles(role, reason="Custom Command Toggle")

            elif action in ("addroleto", "removerolefrom"):
                parts = value.split("|", 1)
                if len(parts) == 2:
                    target = resolve_member(guild, parts[0])
                    role = resolve_role(guild, parts[1])
                    if target and role:
                        if action == "addroleto":
                            await target.add_roles(role, reason="Custom Command")
                        else:
                            await target.remove_roles(role, reason="Custom Command")

            elif action in ("dm", "dmmember"):
                parts = value.split("|", 1)
                if len(parts) == 2:
                    target = resolve_member(guild, parts[0])
                    if target:
                        await target.send(parts[1].strip())
                else:
                    await author.send(value)

            elif action == "sendreply":
                await message.reply(value, mention_author=False)

            elif action == "sendchannel":
                parts = value.split("|", 1)
                if len(parts) == 2:
                    ch = resolve_channel(guild, parts[0])
                    if ch:
                        ctx.channel_sends.append((ch, parts[1].strip()))

            elif action == "deleteafter":
                ctx.delete_after = max(0, int(value))

            elif action in ("silentdelete", "deletetrigger"):
                await message.delete()

            elif action == "react":
                for emoji in [e.strip() for e in value.split(",")][:5]:
                    try:
                        await message.add_reaction(emoji)
                    except discord.HTTPException:
                        pass

            elif action == "reactremove":
                for emoji in [e.strip() for e in value.split(",")][:5]:
                    try:
                        await message.clear_reaction(emoji)
                    except discord.HTTPException:
                        pass

            elif action == "noresponse":
                ctx.no_response = True

            elif action == "sleep":
                import asyncio
                await asyncio.sleep(min(60, max(0, int(value))))

            elif action == "kick":
                parts = value.split("|", 1)
                target = resolve_member(guild, parts[0]) if "|" in value else author
                reason = parts[1].strip() if len(parts) > 1 else "Custom Command"
                if target and guild.me.guild_permissions.kick_members:
                    await target.kick(reason=reason)

            elif action == "ban":
                parts = value.split("|", 1)
                target = resolve_member(guild, parts[0]) if "|" in value else author
                reason = parts[1].strip() if len(parts) > 1 else "Custom Command"
                if target and guild.me.guild_permissions.ban_members:
                    await target.ban(reason=reason, delete_message_seconds=0)

            elif action == "softban":
                parts = value.split("|", 1)
                target = resolve_member(guild, parts[0]) if "|" in value else author
                reason = parts[1].strip() if len(parts) > 1 else "Custom Command"
                if target and guild.me.guild_permissions.ban_members:
                    await target.ban(reason=reason, delete_message_seconds=604800)
                    await guild.unban(target, reason="Softban auto-unban")

            elif action == "unban":
                try:
                    user = await bot.fetch_user(int(value.strip()))
                    if guild.me.guild_permissions.ban_members:
                        await guild.unban(user, reason="Custom Command")
                except (ValueError, discord.NotFound):
                    pass

            elif action in ("timeout", "mute"):
                parts = value.split("|", 1)
                target_ref = parts[0].strip()
                duration_str = parts[1].strip() if len(parts) > 1 else "10m"
                target = resolve_member(guild, target_ref)
                if target and guild.me.guild_permissions.moderate_members:
                    m = re.match(r"(\d+)([smhd])", duration_str.lower())
                    if m:
                        import datetime
                        secs = int(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
                        until = discord.utils.utcnow() + datetime.timedelta(seconds=secs)
                        await target.timeout(until, reason="Custom Command")

            elif action in ("untimeout", "unmute"):
                target = resolve_member(guild, value)
                if target and guild.me.guild_permissions.moderate_members:
                    await target.timeout(None, reason="Custom Command")

            elif action == "setnick":
                parts = value.split("|", 1)
                target = resolve_member(guild, parts[0]) if len(parts) > 1 else author
                nick = parts[1].strip() if len(parts) > 1 else parts[0].strip()
                if target and guild.me.guild_permissions.manage_nicknames:
                    await target.edit(nick=nick[:32] or None)

            elif action == "resetnick":
                target = resolve_member(guild, value) if value else author
                if target and guild.me.guild_permissions.manage_nicknames:
                    await target.edit(nick=None)

            elif action == "createchannel":
                parts = value.split("|")
                name = parts[0].strip()
                cat_ref = parts[1].strip() if len(parts) > 1 else None
                category = None
                if cat_ref:
                    category = discord.utils.get(guild.categories, name=cat_ref)
                    if not category and cat_ref.isdigit():
                        category = guild.get_channel(int(cat_ref))
                if guild.me.guild_permissions.manage_channels:
                    await guild.create_text_channel(name, category=category, reason="Custom Command")

            elif action == "deletechannel":
                ch = resolve_channel(guild, value)
                if ch and guild.me.guild_permissions.manage_channels:
                    await ch.delete(reason="Custom Command")

            elif action == "lockchannel":
                ch = resolve_channel(guild, value) if value else ctx.channel
                if ch and guild.me.guild_permissions.manage_channels:
                    ow = ch.overwrites_for(guild.default_role)
                    ow.send_messages = False
                    await ch.set_permissions(guild.default_role, overwrite=ow)

            elif action == "unlockchannel":
                ch = resolve_channel(guild, value) if value else ctx.channel
                if ch and guild.me.guild_permissions.manage_channels:
                    ow = ch.overwrites_for(guild.default_role)
                    ow.send_messages = None
                    await ch.set_permissions(guild.default_role, overwrite=ow)

            elif action == "hidechannel":
                ch = resolve_channel(guild, value) if value else ctx.channel
                if ch and guild.me.guild_permissions.manage_channels:
                    ow = ch.overwrites_for(guild.default_role)
                    ow.view_channel = False
                    await ch.set_permissions(guild.default_role, overwrite=ow)

            elif action == "showchannel":
                ch = resolve_channel(guild, value) if value else ctx.channel
                if ch and guild.me.guild_permissions.manage_channels:
                    ow = ch.overwrites_for(guild.default_role)
                    ow.view_channel = None
                    await ch.set_permissions(guild.default_role, overwrite=ow)

            elif action == "createrole":
                parts = value.split("|")
                name = parts[0].strip()
                color_str = parts[1].strip() if len(parts) > 1 else None
                color = discord.Color(int(color_str.lstrip("#"), 16)) if color_str else discord.Color.default()
                if guild.me.guild_permissions.manage_roles:
                    await guild.create_role(name=name, color=color, reason="Custom Command")

            elif action == "deleterole":
                role = resolve_role(guild, value)
                if role and guild.me.guild_permissions.manage_roles:
                    await role.delete(reason="Custom Command")

            elif action == "editrole":
                parts = value.split("|")
                if len(parts) >= 2:
                    role = resolve_role(guild, parts[0])
                    prop, _, val = parts[1].strip().partition("=")
                    prop = prop.strip().lower()
                    val = val.strip()
                    if role and guild.me.guild_permissions.manage_roles:
                        if prop == "name":
                            await role.edit(name=val)
                        elif prop == "color":
                            await role.edit(color=discord.Color(int(val.lstrip("#"), 16)))
                        elif prop == "hoist":
                            await role.edit(hoist=val.lower() in ("true", "yes", "1"))
                        elif prop == "mentionable":
                            await role.edit(mentionable=val.lower() in ("true", "yes", "1"))

            elif action == "warn":
                parts = value.split("|", 1)
                target = resolve_member(guild, parts[0])
                reason = parts[1].strip() if len(parts) > 1 else "Custom Command warn"
                if target:
                    from utils import cases
                    await cases.create_warn(guild.id, target.id, author.id, reason)

            elif action == "log":
                parts = value.split("|", 1)
                if len(parts) == 2:
                    ch = resolve_channel(guild, parts[0])
                    if ch:
                        from utils.colors import NEUTRAL
                        log_layout = discord.ui.LayoutView(timeout=None)
                        container = discord.ui.Container(accent_color=NEUTRAL)
                        container.add_item(discord.ui.TextDisplay(f"**{author}**\n{parts[1].strip()}"))
                        log_layout.add_item(container)
                        await ch.send(view=log_layout)

            elif action == "settitle":
                ctx.embed_data["title"] = value
            elif action == "setcolor":
                try:
                    ctx.embed_data["color"] = int(value.lstrip("#"), 16)
                except ValueError:
                    pass
            elif action == "setfooter":
                ctx.embed_data["footer"] = value
            elif action == "setthumbnail":
                ctx.embed_data["thumbnail"] = value
            elif action == "setimage":
                ctx.embed_data["image"] = value
            elif action == "addfield":
                parts = value.split("|", 2)
                if len(parts) >= 2:
                    ctx.embed_data.setdefault("fields", []).append({
                        "name": parts[0].strip(), "value": parts[1].strip(),
                    })

        except discord.Forbidden:
            pass
        except Exception:
            pass

    clean_response = ACTION_PATTERN.sub("", response).strip()
    if ctx.no_response:
        clean_response = ""

    return clean_response, ctx.delete_after, ctx.channel_sends, ctx.embed_data


def substitute_variables(response: str, var_map: dict) -> str:
    response = apply_conditionals(response, var_map)
    response = apply_random_blocks(response)
    for key, val in var_map.items():
        response = response.replace(f"{{{key}}}", str(val))
    return response
