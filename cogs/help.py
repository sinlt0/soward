import discord
from discord.ext import commands

from utils.colors import NEUTRAL, ERROR
import config

COMMANDS_PER_PAGE = 8

CATEGORY_DESCRIPTIONS = {
    "Moderation": "Ban, kick, mute, warn, purge, and case logging.",
    "Config": "Server setup and protection systems.",
    "Engagement": "Giveaways, alerts, and other ways to engage your members.",
    "Tickets": "Support ticket panels, claiming, transcripts, and staff tools.",
    "Music": "Voice channel music playback and queueing.",
    "Utility": "Server and user information commands.",
    "Premium": "Premium activation and no-prefix settings.",
}

COG_DESCRIPTIONS = {
    "AntiNuke": "Protection against malicious admin actions.",
    "AntiRaid": "Join-based raid protection and panic mode.",
    "AutoMod": "Automated filters for spam, mentions, links, and banned words.",
    "Verification": "Member verification gates and approval flows.",
    "AutoRole": "Join roles, reaction roles, and verification roles.",
    "Logging": "Configurable audit and moderation logging.",
    "CustomCommands": "Per-server custom text commands.",
    "Alerts": "YouTube and Twitch upload/live notifications.",
}

def _humanize(name):
    out = []
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not name[i - 1].isupper():
            out.append(" ")
        out.append(ch)
    return "".join(out)

def _category_description(category, cog_count):
    fallback = f"{cog_count} module{'s' if cog_count != 1 else ''}."
    return CATEGORY_DESCRIPTIONS.get(category, fallback)

def _cog_description(cog_name):
    return COG_DESCRIPTIONS.get(cog_name, f"{_humanize(cog_name)} commands.")

def _submodule_name(cog, cog_name):
    value = getattr(cog, "submodule", False)
    if value is True:
        return _humanize(cog_name)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None

async def _is_privileged(bot, user):
    if user.id in config.ALL_PRIVILEGED_IDS:
        return True
    for guild in bot.guilds:
        member = guild.get_member(user.id)
        if member:
            role_ids = {r.id for r in member.roles}
            if role_ids & set(config.DEV_ROLE_IDS):
                return True
    return False

def _category_map(bot):
    mapping = {}
    for cog_name, cog in bot.cogs.items():
        if cog_name == "Help":
            continue
        category = getattr(cog, "category", None) or cog_name
        mapping.setdefault(category, []).append(cog_name)
    return mapping

def _visible_category_map(bot, privileged):
    result = {}
    for category, cog_names in _category_map(bot).items():
        if category in config.HELP_HIDDEN_CATEGORIES and not privileged:
            continue
        visible_cogs = [n for n in cog_names if any(not c.hidden for c in bot.cogs[n].get_commands())]
        if visible_cogs:
            result[category] = visible_cogs
    return result

def _split_cogs(bot, cog_names):
    flat, submodule_groups = [], {}
    for cog_name in cog_names:
        cog = bot.cogs[cog_name]
        group_name = _submodule_name(cog, cog_name)
        if group_name:
            submodule_groups.setdefault(group_name, []).append(cog_name)
        else:
            flat.append(cog_name)
    return flat, submodule_groups

def _submodule_description(group_name, member_cogs):
    if len(member_cogs) == 1 and _humanize(member_cogs[0]) == group_name:
        return _cog_description(member_cogs[0])
    return f"{len(member_cogs)} module{'s' if len(member_cogs) != 1 else ''}: {', '.join(_humanize(c) for c in member_cogs)}"

def _command_lines_for_cogs(bot, cog_names):
    lines = []
    for cog_name in cog_names:
        cog = bot.cogs[cog_name]
        for cmd in cog.get_commands():
            if cmd.hidden:
                continue
            if isinstance(cmd, commands.Group):
                sub_names = ", ".join(s.name for s in cmd.commands)
                lines.append(f"**{cmd.name}** — {cmd.help or 'No description'}\n*Subcommands: {sub_names}*")
            else:
                lines.append(f"**{cmd.name}** — {cmd.help or 'No description'}")
    return lines

def _paginate(lines):
    pages = [lines[i:i + COMMANDS_PER_PAGE] for i in range(0, len(lines), COMMANDS_PER_PAGE)]
    return pages or [["No commands in this category."]]

def _resolve_query(bot, text, privileged):
    key = text.lower().replace(" ", "")
    category_map = _visible_category_map(bot, privileged)
    for category in category_map:
        if category.lower().replace(" ", "") == key:
            return ("category", category)
    for category, cog_names in category_map.items():
        _, submodule_groups = _split_cogs(bot, cog_names)
        for group_name in submodule_groups:
            if group_name.lower().replace(" ", "") == key:
                return ("submodule", category, group_name)
        for cog_name in cog_names:
            if cog_name.lower() == key:
                group_name = _submodule_name(bot.cogs[cog_name], cog_name)
                if group_name:
                    return ("submodule", category, group_name)
                return ("cog", category, cog_name)
    return None

class HelpLayout(discord.ui.LayoutView):
    def __init__(self, bot, author_id, prefix, privileged, preview_notice=False):
        super().__init__(timeout=120)
        self.bot = bot
        self.author_id = author_id
        self.prefix = prefix
        self.privileged = privileged
        self.preview_notice = preview_notice
        self.category_map = _visible_category_map(bot, privileged)
        self.stage = "home"
        self.current_category = None
        self.current_submodule = None
        self.pages = []
        self.page_index = 0
        self.render()

    def open_category(self, category):
        cog_names = self.category_map.get(category, [])
        flat_cogs, submodule_groups = _split_cogs(self.bot, cog_names)
        self.current_category = category
        self.current_submodule = None

        if not flat_cogs and len(submodule_groups) == 1:
            only_group_name = next(iter(submodule_groups))
            self.open_submodule(category, only_group_name)
            return

        self.stage = "category"
        self.pages = _paginate(_command_lines_for_cogs(self.bot, flat_cogs))
        self.page_index = 0
        self.render()

    def open_submodule(self, category, group_name):
        cog_names = self.category_map.get(category, [])
        _, submodule_groups = _split_cogs(self.bot, cog_names)
        member_cogs = submodule_groups.get(group_name, [])

        self.current_category = category
        self.current_submodule = group_name
        self.pages = _paginate(_command_lines_for_cogs(self.bot, member_cogs))
        self.page_index = 0
        self.stage = "submodule"
        self.render()

    def go_home(self):
        self.stage = "home"
        self.current_category = None
        self.current_submodule = None
        self.pages = []
        self.page_index = 0
        self.render()

    def go_back(self):
        if self.stage == "submodule":
            self.open_category(self.current_category)
        else:
            self.go_home()

    def _home_text(self):
        notice = "*Previewing help as a regular user would see it.*\n\n" if self.preview_notice else ""
        total = len(set(self.bot.walk_commands()))
        return (
            f"## {config.BOT_NAME} help\n"
            f"{notice}"
            f"Select a category below to view its commands.\n\n"
            f"**Prefix:** `{self.prefix}` • **Total commands:** {total}"
        )

    def _category_text(self):
        page = self.pages[self.page_index] if self.pages else []
        body = "\n\n".join(page)
        footer = f"\n\n*Page {self.page_index + 1}/{len(self.pages)}*" if len(self.pages) > 1 else ""
        return f"## {self.current_category}\n{body}{footer}"

    def _submodule_text(self):
        page = self.pages[self.page_index] if self.pages else []
        body = "\n\n".join(page)
        footer = f"\n\n*Page {self.page_index + 1}/{len(self.pages)}*" if len(self.pages) > 1 else ""
        return f"## {self.current_category} → {self.current_submodule}\n{body}{footer}"

    def _header_text(self):
        if self.stage == "home":
            return self._home_text()
        if self.stage == "submodule":
            return self._submodule_text()
        return self._category_text()

    def _category_select(self):
        options = [
            discord.SelectOption(
                label=cat,
                value=cat,
                description=_category_description(cat, len(cogs))[:100],
                default=(cat == self.current_category),
            )
            for cat, cogs in self.category_map.items()
        ] or [discord.SelectOption(label="No categories available", value="__none__")]
        select = discord.ui.Select(placeholder="Switch category...", options=options, custom_id="help:category")
        select.callback = self._on_category_select
        return select

    def _submodule_select(self):
        cog_names = self.category_map.get(self.current_category, [])
        _, submodule_groups = _split_cogs(self.bot, cog_names)
        options = [
            discord.SelectOption(
                label=group_name,
                value=group_name,
                description=_submodule_description(group_name, member_cogs)[:100],
                default=(group_name == self.current_submodule),
            )
            for group_name, member_cogs in submodule_groups.items()
        ]
        select = discord.ui.Select(placeholder="View a module...", options=options, custom_id="help:submodule")
        select.callback = self._on_submodule_select
        return select

    async def _on_category_select(self, interaction):
        value = interaction.data["values"][0]
        if value == "__none__":
            return await interaction.response.defer()
        self.open_category(value)
        await interaction.response.edit_message(view=self)

    async def _on_submodule_select(self, interaction):
        value = interaction.data["values"][0]
        self.open_submodule(self.current_category, value)
        await interaction.response.edit_message(view=self)

    async def _on_back(self, interaction):
        self.go_back()
        await interaction.response.edit_message(view=self)

    async def _on_prev(self, interaction):
        self.page_index -= 1
        self.render()
        await interaction.response.edit_message(view=self)

    async def _on_next(self, interaction):
        self.page_index += 1
        self.render()
        await interaction.response.edit_message(view=self)

    def render(self):
        self.clear_items()
        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(self._header_text()))
        container.add_item(discord.ui.Separator())

        if self.stage != "home":
            cog_names = self.category_map.get(self.current_category, [])
            _, submodule_groups = _split_cogs(self.bot, cog_names)
            if submodule_groups:
                submodule_row = discord.ui.ActionRow()
                submodule_row.add_item(self._submodule_select())
                container.add_item(submodule_row)

        category_row = discord.ui.ActionRow()
        category_row.add_item(self._category_select())
        container.add_item(category_row)

        if self.stage != "home":
            nav_row = discord.ui.ActionRow()
            back_btn = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="help:back")
            back_btn.callback = self._on_back
            nav_row.add_item(back_btn)
            if len(self.pages) > 1:
                prev_btn = discord.ui.Button(
                    label="◀", style=discord.ButtonStyle.secondary, custom_id="help:prev",
                    disabled=self.page_index <= 0,
                )
                next_btn = discord.ui.Button(
                    label="▶", style=discord.ButtonStyle.secondary, custom_id="help:next",
                    disabled=self.page_index >= len(self.pages) - 1,
                )
                prev_btn.callback = self._on_prev
                next_btn.callback = self._on_next
                nav_row.add_item(prev_btn)
                nav_row.add_item(next_btn)
            container.add_item(nav_row)

        self.add_item(container)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This help menu is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

class CommandDetailLayout(discord.ui.LayoutView):
    def __init__(self, cmd, prefix):
        super().__init__(timeout=60)

        lines = [
            f"## {cmd.name}",
            cmd.help or "No description available.",
            f"**Usage:** `{prefix}{cmd.name} {cmd.signature}`",
        ]
        if cmd.aliases:
            lines.append(f"**Aliases:** {', '.join(cmd.aliases)}")
        if isinstance(cmd, commands.Group) and cmd.commands:
            sub_text = "\n".join(f"`{s.name}` — {s.help or 'No description'}" for s in cmd.commands)
            lines.append(f"**Subcommands**\n{sub_text}")

        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay("\n\n".join(lines)))
        self.add_item(container)

class NotFoundLayout(discord.ui.LayoutView):
    def __init__(self, query):
        super().__init__(timeout=None)
        container = discord.ui.Container(accent_color=ERROR)
        container.add_item(discord.ui.TextDisplay(
            f"## Not found\nNo command or category named `{query}` found."
        ))
        self.add_item(container)

class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.help_command = None

    @commands.command(name="help", aliases=["commands", "h"], help="Browse all commands by category.")
    async def help_cmd(self, ctx, *, query: str = None):
        privileged = await _is_privileged(self.bot, ctx.author)

        if query and query.lower() == "asuser" and privileged:
            view = HelpLayout(self.bot, ctx.author.id, ctx.prefix, privileged=False, preview_notice=True)
            return await ctx.send(view=view)

        if query:
            cmd = self.bot.get_command(query.lower())
            if cmd:
                cog = cmd.cog
                category = getattr(cog, "category", None) or (cog.qualified_name if cog else None)
                if category in config.HELP_HIDDEN_CATEGORIES and not privileged:
                    return await ctx.send(view=NotFoundLayout(query))
                return await ctx.send(view=CommandDetailLayout(cmd, ctx.prefix))

            resolved = _resolve_query(self.bot, query, privileged)
            if not resolved:
                return await ctx.send(view=NotFoundLayout(query))

            view = HelpLayout(self.bot, ctx.author.id, ctx.prefix, privileged=privileged)
            if resolved[0] == "category":
                view.open_category(resolved[1])
            elif resolved[0] == "submodule":
                view.open_submodule(resolved[1], resolved[2])
            else:
                view.open_category(resolved[1])
            return await ctx.send(view=view)

        view = HelpLayout(self.bot, ctx.author.id, ctx.prefix, privileged=privileged)
        await ctx.send(view=view)

async def setup(bot):
    await bot.add_cog(Help(bot))
