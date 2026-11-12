import asyncio
import io
import random
from typing import Optional

import discord
from PIL import Image

from rpg import engine as cult, settings, stones as stones_text, titles, transcend
from utils import emoji_manager, tribulation_card
from utils.colors import NEUTRAL
from utils.components import error_layout, footer_block

GOLD = 0xF2C14E
STORM = 0x5B6BC0
ACTIVE: set = set()
REASONS = {
    "none": ("Not awakened", "You have not awakened yet. Use `cultivate awaken` to begin."),
    "max": ("Nothing above you", "You have transcended as far as the heavens allow."),
    "open": ("The realm beyond is open", "A new realm has opened above you. Break through to it with `cultivate breakthrough` instead of defying the heavens."),
    "stage": ("Not at the peak", "You can only defy the heavens at the Peak of the highest open realm."),
    "hurt": ("You are injured", "Heal first. A Healing Pill cures it."),
    "qi": ("Your qi is not full", "The tribulation will not come until your qi is full."),
}


async def load_avatar(user: discord.abc.User) -> Optional[Image.Image]:
    try:
        return Image.open(io.BytesIO(await user.display_avatar.replace(size=128, format="png").read()))
    except (discord.HTTPException, OSError):
        return None


def png_file(buffer: io.BytesIO, name: str = "tribulation.gif") -> discord.File:
    return discord.File(buffer, name)


def hp_line(state: dict) -> str:
    e = emoji_manager.get
    filled = max(0, min(10, round(10 * state["hp"] / max(1, state["max"]))))
    return f"{e('eheart')} **{max(0, state['hp']):,}/{state['max']:,}** [{'#' * filled}{'-' * (10 - filled)}]"


def omen_text(state: dict) -> str:
    kind = transcend.KINDS[state["omen"]]
    return f"*{kind['omen']}*\nThe heavens seem to gather a **{kind['name']}**, but omens can lie."


def preview_layout(character: dict, owner: int, on_start, error: Optional[str] = None) -> discord.ui.LayoutView:
    e = emoji_manager.get
    tier = transcend.tier_for(character)
    next_bonus = titles.bonus_text("transcendent", tier)
    lines = [
        f"## {e('etribulation')} Transcend",
        f"You stand at **{cult.stage_name(character)}**. No realm lies above you, so the only way forward is to defy the heavens.",
        f"**Transcendence {titles.ROMAN[tier]}** · {transcend.waves_for(tier)} waves of lightning · fee **{stones_text.fmt(transcend.fee_for(tier))}**",
        f"Each wave shows an omen of the bolt that is coming, but the omen is only true about **{transcend.omen_chance(tier)}%** of the time. Dodge the splitting bolt, endure the crushing bolt and strike back at the piercing bolt. Guess right and it barely hurts. You can circulate qi **{settings.TRANSCEND_HEALS}** times to heal.",
        f"**If you win:** a permanent +{round(settings.TRANSCEND_POWER * 100)}% health, attack and defense, +{round(settings.TRANSCEND_QI * 100)}% qi gain, and the **Transcendent {titles.ROMAN[tier]}** title ({next_bonus}). When a new realm opens you move into it automatically.",
        f"**If you lose:** half your qi, a long injury, and the fee is gone. Healing Pills and the Heaven-Defying Pill ease the lightning.",
    ]
    if character["chance_bonus"]:
        lines.append(f"-# Your pills ease the bolts by {min(20, character['chance_bonus'])}%.")
    view = discord.ui.LayoutView(timeout=180)
    container = discord.ui.Container(accent_color=STORM)
    container.add_item(discord.ui.TextDisplay("\n\n".join(lines)))
    container.add_item(discord.ui.Separator())
    button = discord.ui.Button(label="Defy the heavens", style=discord.ButtonStyle.danger)

    async def pressed(interaction: discord.Interaction):
        if interaction.user.id != owner:
            return await interaction.response.send_message("This is not your tribulation.", ephemeral=True)
        view.stop()
        await on_start(interaction)

    button.callback = pressed
    container.add_item(discord.ui.ActionRow(button))
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


def scene_layout(state: dict, owner: int, name: str, avatar, on_done) -> "TribulationView":
    return TribulationView(state, owner, name, avatar, on_done)


def build_container(state: dict, note: str, actions: Optional[discord.ui.ActionRow], accent: int = STORM, title: str = "") -> discord.ui.Container:
    e = emoji_manager.get
    container = discord.ui.Container(accent_color=accent)
    container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://tribulation.gif")))
    body = [f"## {e('etribulation')} {title or 'Heavenly Tribulation'}", note]
    container.add_item(discord.ui.TextDisplay("\n".join(part for part in body if part)))
    if actions is not None:
        container.add_item(discord.ui.Separator())
        container.add_item(actions)
    for item in footer_block():
        container.add_item(item)
    return container


class TribulationView(discord.ui.LayoutView):
    def __init__(self, state: dict, owner: int, name: str, avatar, on_done):
        super().__init__(timeout=settings.TRANSCEND_TIMEOUT)
        self.state = state
        self.owner = owner
        self.name = name
        self.avatar = avatar
        self.on_done = on_done
        self.message: Optional[discord.Message] = None
        self.row = discord.ui.ActionRow()
        for key in ("dodge", "endure", "strike"):
            button = discord.ui.Button(label=transcend.ACTION_NAMES[key], style=discord.ButtonStyle.danger if key == "strike" else discord.ButtonStyle.secondary)
            button.callback = self.make(key)
            self.row.add_item(button)
        heal = discord.ui.Button(label=f"Circulate qi ({state['heals']})", style=discord.ButtonStyle.success, disabled=state["heals"] <= 0)
        heal.callback = self.make("circulate")
        self.row.add_item(heal)
        self.add_item(build_container(state, self.note(), self.row))

    def note(self) -> str:
        lines = [hp_line(self.state)]
        if self.state["log"]:
            lines.append("\n".join(self.state["log"]))
        if not self.state["done"]:
            lines.append("\n" + omen_text(self.state))
        return "\n".join(lines)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await interaction.response.send_message("This is not your tribulation.", ephemeral=True)
            return False
        return True

    def make(self, action: str):
        async def callback(interaction: discord.Interaction):
            await self.choose(interaction, action)
        return callback

    async def choose(self, interaction: discord.Interaction, action: str):
        await interaction.response.defer()
        transcend.act(self.state, action, random)
        self.stop()
        result = self.state.get("last")
        done = self.state["done"]
        if done:
            ACTIVE.discard(self.owner)
            await self.on_done(interaction, self.state, self.name, self.avatar, result)
            return
        buffer = await asyncio.to_thread(tribulation_card.render_round, self.state, self.name, self.avatar, result)
        view = TribulationView(self.state, self.owner, self.name, self.avatar, self.on_done)
        view.message = self.message
        await interaction.edit_original_response(view=view, attachments=[png_file(buffer)])
        view.message = await interaction.original_response()

    async def on_timeout(self) -> None:
        if self.state["done"]:
            return
        ACTIVE.discard(self.owner)
        self.state["done"] = "lose"
        self.state["log"] = ["You hesitated, and the heavens do not wait."]
        outcome = await transcend.finish(self.owner, self.state)
        if self.message is not None:
            try:
                view = discord.ui.LayoutView(timeout=None)
                view.add_item(build_container(self.state, f"{self.state['log'][0]}\nYou lost half your qi and were badly injured.", None, 0xB04A4A, "The heavens hold"))
                buffer = await asyncio.to_thread(tribulation_card.render_result, False, self.state["tier"], self.name, self.avatar)
                await self.message.edit(view=view, attachments=[png_file(buffer)])
            except discord.HTTPException:
                pass
        return None


def result_layout(outcome: dict, state: dict) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    if outcome["won"]:
        character = outcome["character"]
        tier = outcome["tier"]
        note = "\n".join(state["log"]) + (
            f"\n\n**{outcome['title']}** is yours. {titles.bonus_text('transcendent', tier)} while you wear it.\n"
            f"You now stand at **{outcome['after']}**.\n"
            f"-# Permanent: +{round(settings.TRANSCEND_POWER * 100 * tier)}% health, attack and defense and +{round(settings.TRANSCEND_QI * 100 * tier)}% qi gain. Wear the title with `world titles set transcendent`."
        )
        view.add_item(build_container(state, note, None, GOLD, f"{outcome['title']}"))
    else:
        note = "\n".join(state["log"]) + f"\n\nYou lost half your qi and were badly injured. A Healing Pill cures it. The **{stones_text.fmt(state.get('fee', 0))}** fee is gone."
        view.add_item(build_container(state, note, None, 0xB04A4A, "The heavens hold"))
    return view
