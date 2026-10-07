import time
from typing import Optional

import discord
from discord.ext import commands

from utils import db, embed_templates, emoji_manager, message_vars
from utils.checks import has_guild_permission
from utils.colors import ERROR, NEUTRAL, SUCCESS
from utils.components import ConfirmLayout, error_layout, footer_block, info_layout, success_layout


PROPERTY_LABELS = {
    "title": "Title", "description": "Description", "color": "Color",
    "author": "Author", "footer": "Footer", "image": "Image",
    "thumbnail": "Thumbnail", "timestamp": "Timestamp",
}


def _save_columns(template: dict) -> tuple:
    return (
        template.get("title"), template.get("title_url"), template.get("description"), template.get("color"),
        template.get("author_text"), template.get("author_icon"), template.get("author_url"),
        template.get("footer_text"), template.get("footer_icon"),
        template.get("image_url"), template.get("thumbnail_url"),
        int(template.get("use_timestamp") or 0),
    )


async def _persist_template(guild_id: int, author_id: int, template: dict):
    now = time.time()
    await db.raw_execute(
        "INSERT INTO embed_templates (guild_id, name, title, title_url, description, color, author_text,"
        " author_icon, author_url, footer_text, footer_icon, image_url, thumbnail_url, use_timestamp,"
        " created_by, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(guild_id, name) DO UPDATE SET"
        " title=excluded.title, title_url=excluded.title_url, description=excluded.description, color=excluded.color,"
        " author_text=excluded.author_text, author_icon=excluded.author_icon, author_url=excluded.author_url,"
        " footer_text=excluded.footer_text, footer_icon=excluded.footer_icon,"
        " image_url=excluded.image_url, thumbnail_url=excluded.thumbnail_url,"
        " use_timestamp=excluded.use_timestamp, updated_at=excluded.updated_at",
        (guild_id, template["name"], *_save_columns(template), author_id, now, now),
    )


class PropertyModal(discord.ui.Modal):
    def __init__(self, prop: str, template: dict, on_saved):
        super().__init__(title=f"Edit {PROPERTY_LABELS[prop]}")
        self.prop = prop
        self.on_saved = on_saved
        self.inputs: dict[str, discord.ui.TextInput] = {}

        if prop == "title":
            self.inputs["title"] = discord.ui.TextInput(
                label="Title", default=template.get("title") or "", max_length=256, required=False
            )
            self.inputs["title_url"] = discord.ui.TextInput(
                label="Title URL (makes title clickable)", default=template.get("title_url") or "",
                max_length=500, required=False,
            )
        elif prop == "description":
            self.inputs["description"] = discord.ui.TextInput(
                label="Description", style=discord.TextStyle.paragraph,
                default=template.get("description") or "", max_length=4000, required=False,
            )
        elif prop == "color":
            self.inputs["color"] = discord.ui.TextInput(
                label="Hex color (e.g. #7C6BF6)", default=template.get("color") or "", max_length=7, required=False
            )
        elif prop == "author":
            self.inputs["author_text"] = discord.ui.TextInput(
                label="Author text", default=template.get("author_text") or "", max_length=256, required=False
            )
            self.inputs["author_icon"] = discord.ui.TextInput(
                label="Author icon URL", default=template.get("author_icon") or "", max_length=500, required=False
            )
            self.inputs["author_url"] = discord.ui.TextInput(
                label="Author URL (makes author clickable)", default=template.get("author_url") or "",
                max_length=500, required=False,
            )
        elif prop == "footer":
            self.inputs["footer_text"] = discord.ui.TextInput(
                label="Footer text", default=template.get("footer_text") or "", max_length=2048, required=False
            )
            self.inputs["footer_icon"] = discord.ui.TextInput(
                label="Footer icon URL", default=template.get("footer_icon") or "", max_length=500, required=False
            )
        elif prop == "image":
            self.inputs["image_url"] = discord.ui.TextInput(
                label="Image URL", default=template.get("image_url") or "", max_length=500, required=False
            )
        elif prop == "thumbnail":
            self.inputs["thumbnail_url"] = discord.ui.TextInput(
                label="Thumbnail URL", default=template.get("thumbnail_url") or "", max_length=500, required=False
            )

        for item in self.inputs.values():
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        values = {key: field.value for key, field in self.inputs.items()}
        await self.on_saved(interaction, values)


class FieldModal(discord.ui.Modal, title="Add Embed Field"):
    def __init__(self, on_saved):
        super().__init__()
        self.on_saved = on_saved
        self.name_input = discord.ui.TextInput(label="Field name", max_length=256, required=True)
        self.value_input = discord.ui.TextInput(
            label="Field value", style=discord.TextStyle.paragraph, max_length=1024, required=True
        )
        self.inline_input = discord.ui.TextInput(
            label="Inline? (yes/no)", default="no", max_length=3, required=False
        )
        self.add_item(self.name_input)
        self.add_item(self.value_input)
        self.add_item(self.inline_input)

    async def on_submit(self, interaction: discord.Interaction):
        inline = self.inline_input.value.strip().lower() in ("yes", "y", "true", "1")
        await self.on_saved(interaction, self.name_input.value, self.value_input.value, inline)


class BuilderPropertyRow(discord.ui.ActionRow):
    def __init__(self, builder: "EmbedBuilderView"):
        super().__init__(
            discord.ui.Button(label="Title", style=discord.ButtonStyle.secondary, custom_id="embed:prop:title"),
            discord.ui.Button(label="Description", style=discord.ButtonStyle.secondary, custom_id="embed:prop:description"),
            discord.ui.Button(label="Color", style=discord.ButtonStyle.secondary, custom_id="embed:prop:color"),
            discord.ui.Button(label="Author", style=discord.ButtonStyle.secondary, custom_id="embed:prop:author"),
            discord.ui.Button(label="Footer", style=discord.ButtonStyle.secondary, custom_id="embed:prop:footer"),
        )
        self.builder = builder
        for i, prop in enumerate(("title", "description", "color", "author", "footer")):
            self.children[i].callback = self._make_callback(prop)

    def _make_callback(self, prop: str):
        async def callback(interaction: discord.Interaction):
            async def on_saved(modal_interaction: discord.Interaction, values: dict):
                await self.builder.apply_and_save(values)
                await modal_interaction.response.edit_message(view=self.builder)

            modal = PropertyModal(prop, self.builder.template, on_saved)
            await interaction.response.send_modal(modal)
        return callback


class BuilderMediaRow(discord.ui.ActionRow):
    def __init__(self, builder: "EmbedBuilderView"):
        super().__init__(
            discord.ui.Button(label="Image", style=discord.ButtonStyle.secondary, custom_id="embed:prop:image"),
            discord.ui.Button(label="Thumbnail", style=discord.ButtonStyle.secondary, custom_id="embed:prop:thumbnail"),
            discord.ui.Button(label="Toggle Timestamp", style=discord.ButtonStyle.secondary, custom_id="embed:prop:timestamp"),
            discord.ui.Button(label="Preview", style=discord.ButtonStyle.primary, custom_id="embed:prop:preview"),
        )
        self.builder = builder
        self.children[0].callback = self._make_modal_callback("image")
        self.children[1].callback = self._make_modal_callback("thumbnail")
        self.children[2].callback = self._toggle_timestamp
        self.children[3].callback = self._preview

    def _make_modal_callback(self, prop: str):
        async def callback(interaction: discord.Interaction):
            async def on_saved(modal_interaction: discord.Interaction, values: dict):
                await self.builder.apply_and_save(values)
                await modal_interaction.response.edit_message(view=self.builder)

            modal = PropertyModal(prop, self.builder.template, on_saved)
            await interaction.response.send_modal(modal)
        return callback

    async def _toggle_timestamp(self, interaction: discord.Interaction):
        new_value = 0 if self.builder.template.get("use_timestamp") else 1
        await self.builder.apply_and_save({"use_timestamp": new_value})
        await interaction.response.edit_message(view=self.builder)

    async def _preview(self, interaction: discord.Interaction):
        var_map = message_vars.build_base_variables(interaction.user, interaction.guild, interaction.channel)
        rendered = embed_templates.build_discord_embed(self.builder.template, var_map, self.builder.fields)
        await interaction.response.send_message(embed=rendered, ephemeral=True)


class BuilderFieldRow(discord.ui.ActionRow):
    def __init__(self, builder: "EmbedBuilderView"):
        super().__init__(
            discord.ui.Button(label="Add Field", style=discord.ButtonStyle.secondary, custom_id="embed:field:add"),
            discord.ui.Button(label="Remove Last Field", style=discord.ButtonStyle.danger, custom_id="embed:field:remove"),
            discord.ui.Button(label="Done", style=discord.ButtonStyle.success, custom_id="embed:field:done"),
        )
        self.builder = builder
        self.children[0].callback = self._add_field
        self.children[1].callback = self._remove_field
        self.children[2].callback = self._done

    async def _add_field(self, interaction: discord.Interaction):
        e = emoji_manager.get
        if len(self.builder.fields) >= 25:
            return await interaction.response.send_message(
                view=error_layout("Limit Reached", "An embed can have at most 25 fields."), ephemeral=True
            )

        async def on_saved(modal_interaction: discord.Interaction, name: str, value: str, inline: bool):
            ok = await embed_templates.add_field(self.builder.guild_id, self.builder.template["name"], name, value, inline)
            if ok:
                self.builder.fields = await embed_templates.get_fields(self.builder.guild_id, self.builder.template["name"])
                self.builder._build()
                await modal_interaction.response.edit_message(view=self.builder)
            else:
                await modal_interaction.response.send_message(
                    view=error_layout("Limit Reached", "An embed can have at most 25 fields."), ephemeral=True
                )

        modal = FieldModal(on_saved)
        await interaction.response.send_modal(modal)

    async def _remove_field(self, interaction: discord.Interaction):
        e = emoji_manager.get
        if not self.builder.fields:
            return await interaction.response.send_message(
                view=error_layout("No Fields", "This embed has no fields to remove."), ephemeral=True
            )
        last_position = self.builder.fields[-1]["position"]
        await embed_templates.remove_field(self.builder.guild_id, self.builder.template["name"], last_position)
        self.builder.fields = await embed_templates.get_fields(self.builder.guild_id, self.builder.template["name"])
        self.builder._build()
        await interaction.response.edit_message(view=self.builder)

    async def _done(self, interaction: discord.Interaction):
        e = emoji_manager.get
        await interaction.response.edit_message(
            view=success_layout(f"{e('check')} Embed Saved", f"Template `{self.builder.template['name']}` is ready to use.\nReference it anywhere with `{{embed:{self.builder.template['name']}}}`.")
        )


class EmbedBuilderView(discord.ui.LayoutView):
    def __init__(self, guild_id: int, author_id: int, template: dict, fields: list[dict]):
        super().__init__(timeout=600)
        self.guild_id = guild_id
        self.author_id = author_id
        self.template = template
        self.fields = fields
        self._build()

    def _build(self):
        self.clear_items()
        e = emoji_manager.get

        container = discord.ui.Container(accent_color=embed_templates.parse_color(self.template.get("color")))
        container.add_item(discord.ui.TextDisplay(f"## {e('settings')} Embed Builder — `{self.template['name']}`"))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(self._preview_body()))
        container.add_item(discord.ui.Separator())
        container.add_item(BuilderPropertyRow(self))
        container.add_item(BuilderMediaRow(self))
        container.add_item(BuilderFieldRow(self))
        container.add_item(discord.ui.Separator())
        for item in footer_block():
            container.add_item(item)
        self.add_item(container)

    async def apply_and_save(self, values: dict):
        for key, value in values.items():
            self.template[key] = value
        await _persist_template(self.guild_id, self.author_id, self.template)
        self._build()

    def _preview_body(self) -> str:
        lines = [
            f"**Title:** {self.template.get('title') or '*(none)*'}"
            + (f" → {self.template['title_url']}" if self.template.get("title_url") else ""),
            f"**Description:** {self.template.get('description') or '*(none)*'}",
            f"**Color:** `{self.template.get('color') or 'default'}`",
            f"**Author:** {self.template.get('author_text') or '*(none)*'}",
            f"**Footer:** {self.template.get('footer_text') or '*(none)*'}",
            f"**Image:** {'Set' if self.template.get('image_url') else '*(none)*'}",
            f"**Thumbnail:** {'Set' if self.template.get('thumbnail_url') else '*(none)*'}",
            f"**Timestamp:** {'On' if self.template.get('use_timestamp') else 'Off'}",
            f"**Fields:** {len(self.fields)}/25",
            "",
            f"-# Use this embed anywhere with `{{embed:{self.template['name']}}}`",
        ]
        return "\n".join(lines)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This builder is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True


class Embeds(commands.Cog):
    category = "Config"
    submodule = True

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="embed", invoke_without_command=True, help="View, create, edit, or delete reusable embed templates.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def embed_group(self, ctx: commands.Context):
        e = emoji_manager.get
        templates = await embed_templates.list_templates(ctx.guild.id)
        cap = await embed_templates.get_template_cap(ctx.guild.id)
        body = (
            f"**Templates:** `{len(templates)}/{cap}`\n\n"
            "Use `embed create <name>` to make a new one, `embed list` to view them all,\n"
            "or reference any embed elsewhere with `{embed:name}`."
        )
        await ctx.send(view=info_layout(f"{e('settings')} Embed Templates", body))

    @embed_group.command(name="create", help="Create a new reusable embed template. Usage: embed create <name>")
    @has_guild_permission("manage_guild")
    async def embed_create(self, ctx: commands.Context, name: str):
        e = emoji_manager.get
        name = name.lower().strip()
        if not name.replace("_", "").replace("-", "").isalnum():
            return await ctx.send(view=error_layout("Invalid Name", "Names can only contain letters, numbers, underscores, and hyphens."))
        if len(name) > 50:
            return await ctx.send(view=error_layout("Too Long", "Name must be 50 characters or fewer."))

        existing = await embed_templates.get_template(ctx.guild.id, name)
        if existing:
            return await ctx.send(view=error_layout("Already Exists", f"An embed named `{name}` already exists. Use `embed edit {name}` instead."))

        count = await embed_templates.count_templates(ctx.guild.id)
        cap = await embed_templates.get_template_cap(ctx.guild.id)
        if count >= cap:
            return await ctx.send(view=error_layout(
                "Limit Reached", f"This server has reached its embed template limit (`{cap}`). Upgrade to premium for more."
            ))

        now = time.time()
        await db.raw_execute(
            "INSERT INTO embed_templates (guild_id, name, created_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (ctx.guild.id, name, ctx.author.id, now, now),
        )
        template = await embed_templates.get_template(ctx.guild.id, name)
        await ctx.send(view=EmbedBuilderView(ctx.guild.id, ctx.author.id, template, []))

    @embed_group.command(name="edit", help="Open the interactive builder for an existing embed. Usage: embed edit <name>")
    @has_guild_permission("manage_guild")
    async def embed_edit(self, ctx: commands.Context, name: str):
        e = emoji_manager.get
        template = await embed_templates.get_template(ctx.guild.id, name)
        if not template:
            return await ctx.send(view=error_layout("Not Found", f"No embed template named `{name}`."))
        fields = await embed_templates.get_fields(ctx.guild.id, name)
        await ctx.send(view=EmbedBuilderView(ctx.guild.id, ctx.author.id, template, fields))

    @embed_group.command(name="delete", help="Delete an embed template. Usage: embed delete <name>")
    @has_guild_permission("manage_guild")
    async def embed_delete(self, ctx: commands.Context, name: str):
        e = emoji_manager.get
        name = name.lower().strip()
        template = await embed_templates.get_template(ctx.guild.id, name)
        if not template:
            return await ctx.send(view=error_layout("Not Found", f"No embed template named `{name}`."))

        confirm = ConfirmLayout(
            "Confirm Delete",
            f"Delete embed template `{name}`? Any message using `{{embed:{name}}}` will stop showing it.",
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "Embed template was not deleted."))

        await embed_templates.clear_fields(ctx.guild.id, name)
        await db.raw_execute("DELETE FROM embed_templates WHERE guild_id=? AND name=?", (ctx.guild.id, name))
        await msg.edit(view=success_layout(f"{e('check')} Deleted", f"Embed template `{name}` has been deleted."))

    @embed_group.command(name="list", help="List all embed templates in this server.")
    async def embed_list(self, ctx: commands.Context):
        e = emoji_manager.get
        templates = await embed_templates.list_templates(ctx.guild.id)
        if not templates:
            return await ctx.send(view=info_layout(f"{e('info')} Embed Templates", "No embed templates configured yet.\nUse `embed create <name>` to make one."))

        cap = await embed_templates.get_template_cap(ctx.guild.id)
        lines = []
        for t in templates:
            title_preview = t.get("title") or t.get("description") or "*(empty embed)*"
            lines.append(f"**{t['name']}** — {title_preview[:60]}\n-# `{{embed:{t['name']}}}`")
        await ctx.send(view=info_layout(f"{e('info')} Embed Templates ({len(templates)}/{cap})", "\n\n".join(lines)))

    @embed_group.command(name="preview", help="Preview how an embed template currently looks. Usage: embed preview <name>")
    async def embed_preview(self, ctx: commands.Context, name: str):
        e = emoji_manager.get
        template = await embed_templates.get_template(ctx.guild.id, name)
        if not template:
            return await ctx.send(view=error_layout("Not Found", f"No embed template named `{name}`."))

        fields = await embed_templates.get_fields(ctx.guild.id, name)
        var_map = message_vars.build_base_variables(ctx.author, ctx.guild, ctx.channel)
        rendered = embed_templates.build_discord_embed(template, var_map, fields)
        await ctx.send(embed=rendered)

    @embed_group.command(name="rename", help="Rename an embed template. Usage: embed rename <old_name> <new_name>")
    @has_guild_permission("manage_guild")
    async def embed_rename(self, ctx: commands.Context, old_name: str, new_name: str):
        e = emoji_manager.get
        old_name, new_name = old_name.lower().strip(), new_name.lower().strip()
        template = await embed_templates.get_template(ctx.guild.id, old_name)
        if not template:
            return await ctx.send(view=error_layout("Not Found", f"No embed template named `{old_name}`."))
        if await embed_templates.get_template(ctx.guild.id, new_name):
            return await ctx.send(view=error_layout("Already Exists", f"An embed named `{new_name}` already exists."))

        await db.raw_execute("UPDATE embed_templates SET name=? WHERE guild_id=? AND name=?", (new_name, ctx.guild.id, old_name))
        await db.raw_execute("UPDATE embed_template_fields SET embed_name=? WHERE guild_id=? AND embed_name=?", (new_name, ctx.guild.id, old_name))
        await ctx.send(view=success_layout(f"{e('check')} Renamed", f"`{old_name}` → `{new_name}`.\nUpdate any `{{embed:{old_name}}}` references to `{{embed:{new_name}}}`."))

    @embed_group.command(name="duplicate", aliases=["copy"], help="Duplicate an embed template under a new name. Usage: embed duplicate <name> <new_name>")
    @has_guild_permission("manage_guild")
    async def embed_duplicate(self, ctx: commands.Context, name: str, new_name: str):
        e = emoji_manager.get
        name, new_name = name.lower().strip(), new_name.lower().strip()
        template = await embed_templates.get_template(ctx.guild.id, name)
        if not template:
            return await ctx.send(view=error_layout("Not Found", f"No embed template named `{name}`."))
        if await embed_templates.get_template(ctx.guild.id, new_name):
            return await ctx.send(view=error_layout("Already Exists", f"An embed named `{new_name}` already exists."))

        count = await embed_templates.count_templates(ctx.guild.id)
        cap = await embed_templates.get_template_cap(ctx.guild.id)
        if count >= cap:
            return await ctx.send(view=error_layout("Limit Reached", f"This server has reached its embed template limit (`{cap}`)."))

        new_template = dict(template)
        new_template["name"] = new_name
        await _persist_template(ctx.guild.id, ctx.author.id, new_template)

        for field in await embed_templates.get_fields(ctx.guild.id, name):
            await embed_templates.add_field(ctx.guild.id, new_name, field["field_name"], field["field_value"], bool(field["inline"]))

        await ctx.send(view=success_layout(f"{e('check')} Duplicated", f"`{name}` copied to `{new_name}`."))

    @embed_group.command(name="variables", aliases=["vars"], help="Show all available template variables for embeds.")
    async def embed_variables(self, ctx: commands.Context):
        e = emoji_manager.get
        body = message_vars.variables_doc_block()
        await ctx.send(view=info_layout(f"{e('info')} Embed Variables", body))


async def setup(bot: commands.Bot):
    await bot.add_cog(Embeds(bot))
