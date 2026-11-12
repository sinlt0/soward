import inspect
import logging
import re
import types
import typing
from typing import Literal, Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.ext.commands.view import StringView

import config
from utils import blacklist, db, slash_sync

log = logging.getLogger("zyro.slash")

NAME_BAD = re.compile(r"[^a-z0-9_-]")
CHANNEL_TYPES = (discord.TextChannel, discord.VoiceChannel, discord.CategoryChannel, discord.StageChannel, discord.ForumChannel, discord.Thread)
DESCRIPTIONS = {
    "user": "Member to use this on",
    "int": "A number",
    "float": "A number",
    "bool": "Yes or no",
    "channel": "A channel",
    "role": "A role",
    "choice": "Pick one",
}


def is_sub(annotation, *types_) -> bool:
    for kind in types_:
        if annotation is kind:
            return True
        try:
            if issubclass(annotation, kind):
                return True
        except TypeError:
            continue
    return False


def slash_name(text: str) -> str:
    return NAME_BAD.sub("-", text.lower())[:32] or "x"


def clip(text: str, limit: int = 100) -> str:
    text = (text or "").strip().split("\n")[0].split(" Usage:")[0].strip()
    return (text or "Run this command.")[:limit]


class Option:
    def __init__(self, param: inspect.Parameter):
        self.name = param.name
        self.slash = slash_name(param.name)
        self.kind = "str"
        self.annotation = str
        self.default = None if param.default is inspect.Parameter.empty else param.default
        self.rest = param.kind in (inspect.Parameter.KEYWORD_ONLY, inspect.Parameter.VAR_POSITIONAL)
        self.required = param.default is inspect.Parameter.empty and param.kind != inspect.Parameter.VAR_POSITIONAL
        self.description = ""
        self.resolve(param.annotation)
        if not self.description:
            self.description = DESCRIPTIONS.get(self.kind) or param.name.replace("_", " ").capitalize()

    def resolve(self, annotation):
        if isinstance(annotation, commands.Greedy):
            self.rest = True
            self.description = "One or more values separated by spaces"
            return
        origin = typing.get_origin(annotation)
        if origin is typing.Union or origin is getattr(types, "UnionType", None):
            args = [a for a in typing.get_args(annotation) if a is not type(None)]
            if len(args) != len(typing.get_args(annotation)):
                self.required = False
            if args:
                return self.resolve(args[0])
            return
        if origin is Literal:
            self.kind = "choice"
            self.annotation = annotation
            return
        if not inspect.isclass(annotation):
            return
        if is_sub(annotation, discord.Member):
            self.kind, self.annotation = "user", discord.Member
        elif is_sub(annotation, discord.User, discord.abc.User):
            self.kind, self.annotation = "user", discord.User
        elif annotation is bool:
            self.kind, self.annotation = "bool", bool
        elif annotation is int:
            self.kind, self.annotation = "int", int
        elif annotation is float:
            self.kind, self.annotation = "float", float
        elif is_sub(annotation, discord.Role):
            self.kind, self.annotation = "role", discord.Role
        elif is_sub(annotation, discord.abc.GuildChannel, discord.Thread):
            self.kind = "channel"
            self.annotation = annotation if annotation in CHANNEL_TYPES else discord.abc.GuildChannel

    def render(self, value) -> str:
        if self.kind == "user":
            return f"<@{value.id}>"
        if self.kind == "role":
            return f"<@&{value.id}>"
        if self.kind == "channel":
            return f"<#{value.id}>"
        if self.kind == "bool":
            return "yes" if value else "no"
        text = str(value)
        if self.rest or self.kind != "str":
            return text
        if not text or any(ch.isspace() for ch in text) or text[0] in "\"'":
            return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'
        return text


def options_for(command: commands.Command) -> list[Option]:
    options = [Option(p) for p in command.clean_params.values()]
    for option in options:
        note = config.SLASH_OPTION_DESCRIPTIONS.get(f"{command.name}.{option.name}")
        if note:
            option.description = note
    users = [o for o in options if o.kind == "user"]
    taken = {o.slash for o in options if o.kind != "user"}
    for index, option in enumerate(users, 1):
        name = "target" if len(users) == 1 else f"target{index}"
        if name not in taken:
            option.slash = name
        taken.add(option.slash)
        if len(users) > 1 and f"{command.name}.{option.name}" not in config.SLASH_OPTION_DESCRIPTIONS:
            option.description = "First member" if index == 1 else "Second member" if index == 2 else f"Member {index}"
    seen = set()
    for option in options:
        while option.slash in seen:
            option.slash += "x"
        seen.add(option.slash)
    return options


class Leaf:
    def __init__(self, name: str, command: commands.Command, fallback: bool = False):
        self.name = slash_name(config.SLASH_RENAMES.get(name, name))
        self.command = command
        self.fallback = fallback
        self.options = [] if fallback else options_for(command)
        if fallback:
            fake = inspect.Parameter("input", inspect.Parameter.KEYWORD_ONLY, default="", annotation=str)
            option = Option(fake)
            option.description = "Subcommand and options, the same as after the prefix command"
            self.options = [option]
        self.descriptions = clip(command.help or command.brief or "")


class Node:
    def __init__(self, name: str, description: str):
        self.name = slash_name(name)
        self.description = clip(description)
        self.children: dict[str, "Leaf | Node"] = {}

    def add(self, child):
        if isinstance(child, Leaf) and child.name == self.name:
            child.name = "view"
        base = child.name
        n = 2
        while child.name in self.children:
            child.name = f"{base[:29]}-{n}"
            n += 1
        self.children[child.name] = child


def usable(command: commands.Command, picked: bool = False) -> bool:
    if command.hidden or not command.enabled:
        return False
    if not picked and command.qualified_name in config.SLASH_CLAIMED:
        return False
    if command.name in config.SLASH_EXCLUDE or command.qualified_name in config.HELP_HIDDEN_COMMANDS:
        return False
    return True


def bare_name(command: commands.Command) -> str:
    return config.SLASH_BARE_NAMES.get(command.name, "view")


def group_node(command: commands.Group, level: int, name: Optional[str] = None) -> Node:
    node = Node(name or config.SLASH_RENAMES.get(command.name, command.name), clip(command.help or command.brief or f"{command.name} commands"))
    node.add(Leaf(bare_name(command), command))
    for sub in command.commands:
        if usable(sub):
            node.add(child_for(sub, level))
    return node


def child_for(command: commands.Command, container_level: int):
    if isinstance(command, commands.Group):
        if container_level == 1:
            return group_node(command, 2)
        return Leaf(command.name, command, fallback=True)
    return Leaf(command.name, command)


def fill_from_cog(node: Node, cog: commands.Cog, container_level: int, inline: Optional[str] = None):
    for command in cog.get_commands():
        if not usable(command):
            continue
        if inline and isinstance(command, commands.Group) and command.name == inline:
            node.add(Leaf(bare_name(command), command))
            for sub in command.commands:
                if usable(sub):
                    node.add(child_for(sub, container_level))
            continue
        node.add(child_for(command, container_level))


def overflow(node: Node):
    limit = config.SLASH_GROUP_LIMIT
    if len(node.children) <= limit:
        return
    more = Node("more", f"More {node.name} commands")
    for name in list(node.children)[limit - 1:]:
        child = node.children.pop(name)
        if isinstance(child, Node):
            log.warning("Slash group '%s' is too large; dropped nested group '%s'", node.name, child.name)
            continue
        more.add(child)
    node.add(more)


def split_overflow(node: Node, extra_name: str) -> Optional[Node]:
    limit = config.SLASH_GROUP_LIMIT
    if len(node.children) <= limit:
        return None
    extra = Node(extra_name, f"More {node.name} commands")
    for name in list(node.children)[limit:]:
        extra.add(node.children.pop(name))
    return extra


def build_layout(bot: commands.Bot) -> dict[str, Node]:
    roots: dict[str, Node] = {}
    for group_name, spec in config.SLASH_LAYOUT.items():
        description = spec["description"]
        if "commands" in spec:
            node = Node(group_name, description)
            for qualified in spec["commands"]:
                command = bot.get_command(qualified)
                if command is not None and usable(command, True):
                    node.add(Leaf(command.name, command))
            if node.children:
                roots[group_name] = node
            continue
        if "flatten" in spec:
            command = bot.get_command(spec["flatten"])
            if not isinstance(command, commands.Group) or not usable(command):
                continue
            node = group_node(command, 1, group_name)
            node.description = clip(description)
            overflow(node)
            roots[group_name] = node
            continue
        node = Node(group_name, description)
        for entry in spec["entries"]:
            if isinstance(entry, list):
                sub_name, cog_name = entry
                cog = bot.get_cog(cog_name)
                if cog is None:
                    continue
                sub = Node(sub_name, f"{sub_name} commands")
                fill_from_cog(sub, cog, 2, inline=sub_name)
                if sub.children:
                    overflow(sub)
                    node.add(sub)
            else:
                cog = bot.get_cog(entry)
                if cog is not None:
                    fill_from_cog(node, cog, 1, inline=group_name)
        if node.children:
            extra_name = config.SLASH_OVERFLOW_GROUPS.get(group_name)
            extra = split_overflow(node, extra_name) if extra_name else None
            if extra is not None:
                overflow(extra)
                roots[extra.name] = extra
            overflow(node)
            roots[group_name] = node
    return roots


GUILD_CHECKS = ("guild_only", "has_guild_permission", "has_permissions", "bot_has_permissions", "has_guild_permissions", "bot_has_guild_permissions")


def needs_guild(command: commands.Command) -> bool:
    if command.qualified_name in config.USER_APP_BLOCKED:
        return True
    node = command
    while node is not None:
        for check in node.checks:
            name = getattr(check, "__qualname__", "")
            if any(name.startswith(prefix) for prefix in GUILD_CHECKS):
                return True
        node = node.parent
    return False


def bot_in_guild(bot: commands.Bot, interaction: discord.Interaction) -> bool:
    return interaction.guild_id is not None and bot.get_guild(interaction.guild_id) is not None


def root_of(command: commands.Command) -> commands.Command:
    while command.parent is not None:
        command = command.parent
    return command


def tail_of(command: commands.Command) -> str:
    return " ".join(command.qualified_name.split(" ")[1:])


class Slash(commands.Cog):
    category = "Dev"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.registered: list[str] = []
        self.synced = False

    def make_command(self, leaf: Leaf) -> app_commands.Command:
        options = leaf.options
        command = leaf.command
        cog = self

        async def callback(interaction: discord.Interaction, **values):
            await cog.run(interaction, command, options, values)

        params = [inspect.Parameter("interaction", inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=discord.Interaction)]
        for option in options:
            if option.required:
                params.append(inspect.Parameter(option.slash, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=option.annotation))
            else:
                params.append(inspect.Parameter(option.slash, inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None, annotation=Optional[option.annotation]))
        callback.__signature__ = inspect.Signature(params)
        callback.__annotations__ = {p.name: p.annotation for p in params}
        if options:
            callback = app_commands.describe(**{o.slash: clip(o.description) for o in options})(callback)
        return app_commands.Command(name=leaf.name, description=leaf.descriptions, callback=callback)

    def make_group(self, node: Node, top: bool = False) -> app_commands.Group:
        extra = {}
        if top and node.name in config.USER_APP_GROUPS:
            extra = {
                "allowed_installs": app_commands.AppInstallationType(guild=True, user=True),
                "allowed_contexts": app_commands.AppCommandContext(guild=True, dm_channel=True, private_channel=True),
            }
        group = app_commands.Group(name=node.name, description=node.description, **extra)
        for child in node.children.values():
            group.add_command(self.make_group(child) if isinstance(child, Node) else self.make_command(child))
        return group

    async def cog_load(self):
        for name, node in build_layout(self.bot).items():
            try:
                self.bot.tree.add_command(self.make_group(node, top=True))
                self.registered.append(name)
            except Exception:
                log.error("Could not register slash group '%s'", name, exc_info=True)

    async def cog_unload(self):
        for name in self.registered:
            self.bot.tree.remove_command(name)
        self.registered = []

    @commands.Cog.listener()
    async def on_ready(self):
        if self.synced:
            return
        self.synced = True
        digest = slash_sync.digest(self.bot)
        if await db.get("slash", "version") == digest:
            return
        try:
            await slash_sync.sync(self.bot)
        except discord.HTTPException:
            log.error("Slash sync failed", exc_info=True)
            self.synced = False
            return
        await db.set("slash", "version", digest)

    async def run(self, interaction: discord.Interaction, command: commands.Command, options: list[Option], values: dict):
        if await blacklist.is_user_blacklisted(interaction.user.id) or (interaction.guild and await blacklist.is_guild_blacklisted(interaction.guild.id)):
            return await interaction.response.send_message("You cannot use this bot.", ephemeral=True)
        from utils import dev_state
        if dev_state.blocks(interaction.user):
            return await interaction.response.send_message(dev_state.notice_text(), ephemeral=True)
        if not bot_in_guild(self.bot, interaction) and needs_guild(command):
            return await interaction.response.send_message("That command needs Zyro to be added to this server. Use it in a server where Zyro is added, or ask a server admin to add it.", ephemeral=True)
        await interaction.response.defer()
        tokens = [tail_of(command)]
        given = [o for o in options if values.get(o.slash) not in (None, "")]
        last = max((options.index(o) for o in given), default=-1)
        for index, option in enumerate(options):
            value = values.get(option.slash)
            if value is None or value == "":
                if index < last and not option.rest and isinstance(option.default, (str, int, float)) and not isinstance(option.default, bool) and option.default != "":
                    tokens.append(option.render(option.default))
                continue
            tokens.append(option.render(value))
        root = root_of(command)
        ctx = await commands.Context.from_interaction(interaction)
        ctx.command = root
        ctx.invoked_with = root.name
        ctx.view = StringView(" ".join(t for t in tokens if t).strip())
        await self.bot.invoke(ctx)
        try:
            original = await interaction.original_response()
            if original.flags.loading:
                await interaction.delete_original_response()
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Slash(bot))
