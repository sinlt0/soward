import discord

from utils.colors import ERROR, NEUTRAL, SUCCESS
import config

def _base_embed(color: int, title: str = None, description: str = None) -> discord.Embed:
    embed = discord.Embed(color=color)
    if title:
        embed.title = title
    if description:
        embed.description = description
    embed.set_footer(text=config.BOT_NAME)
    return embed

def neutral(title: str = None, description: str = None) -> discord.Embed:
    return _base_embed(NEUTRAL, title, description)

def success(title: str = None, description: str = None) -> discord.Embed:
    return _base_embed(SUCCESS, title, description)

def error(title: str = None, description: str = None) -> discord.Embed:
    return _base_embed(ERROR, title, description)

def build_container(*rows: list[discord.Component], accent_color: int = NEUTRAL) -> list[discord.Component]:
    return list(rows)

class PaginatorView(discord.ui.View):
    def __init__(self, pages: list[discord.Embed], *, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current = 0
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.current == 0
        self.next_btn.disabled = self.current >= len(self.pages) - 1

    def _page_embed(self) -> discord.Embed:
        embed = self.pages[self.current]
        embed.set_footer(text=f"{config.BOT_NAME} • Page {self.current + 1}/{len(self.pages)}")
        return embed

    @discord.ui.button(label="◀", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._page_embed(), view=self)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self._page_embed(), view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True

class ConfirmView(discord.ui.View):
    def __init__(self, *, author_id: int, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "This confirmation is not for you.", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()
        await interaction.response.defer()
