import discord

from utils.colors import ERROR, NEUTRAL, SUCCESS
import config

_FOOTER_TEXT = f"-# {config.BOT_NAME} · Made by Soward Team"

def footer_block() -> list:
    return [
        discord.ui.Separator(),
        discord.ui.TextDisplay(_FOOTER_TEXT),
    ]

def _add_footer(container: discord.ui.Container) -> None:
    for item in footer_block():
        container.add_item(item)

def info_layout(title: str, body: str, *, color: int = NEUTRAL, timeout: float | None = None) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=timeout)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
    _add_footer(container)
    view.add_item(container)
    return view

def success_layout(title: str, body: str, *, timeout: float | None = None) -> discord.ui.LayoutView:
    return info_layout(title, body, color=SUCCESS, timeout=timeout)

def error_layout(title: str, body: str, *, timeout: float | None = None) -> discord.ui.LayoutView:
    return info_layout(title, body, color=ERROR, timeout=timeout)

class ConfirmRow(discord.ui.ActionRow):
    def __init__(self, layout: "ConfirmLayout" = None):
        super().__init__()
        self.layout_ref = layout

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, custom_id="confirm:yes")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.layout_ref
        view.value = True
        view.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger, custom_id="confirm:no")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.layout_ref
        view.value = False
        view.stop()
        for item in view.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        await interaction.response.edit_message(view=view)

class ConfirmLayout(discord.ui.LayoutView):
    def __init__(self, title: str, body: str, *, author_id: int, color: int = NEUTRAL, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: bool | None = None

        self.container = discord.ui.Container(accent_color=color)
        self.container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
        self.container.add_item(discord.ui.Separator())
        self.button_row = ConfirmRow(layout=self)
        self.container.add_item(self.button_row)
        _add_footer(self.container)
        self.add_item(self.container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This confirmation is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
