import asyncio
import io
import time
from typing import Optional

import discord
from discord.ext import commands

from cogs.cultivation import NO_PINGS, fight_layout, item_name, weapon_note
from cogs.economy import duration
from rpg import calamity, elements, engine as cult, stones
from utils import boss_card, emoji_manager
from utils.colors import NEUTRAL
from utils.components import error_layout, footer_block, success_layout


def picture_layout(title: str, body: str, filename: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=NEUTRAL)
    container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(f"attachment://{filename}")))
    container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


def reward_lines(parts: dict) -> list:
    lines = [f"+**{stones.fmt(parts.get('coins', 0))}**", f"+{parts.get('qi', 0)} qi"]
    for key, count in parts.get("loot", []):
        lines.append(f"+{count} **{item_name(key)}**")
    if parts.get("gear"):
        lines.append(f"It dropped a **{item_name(parts['gear'])}**!")
    if parts.get("overflow"):
        lines.append(f"-# A pouch was full, so extras sold for {stones.fmt(parts['overflow'])}.")
    return lines


class Board(commands.Cog):
    category = "Cultivation"
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def active(self) -> set:
        cog = self.bot.get_cog("Cultivation")
        return cog.active if cog else set()

    async def need_character(self, ctx: commands.Context) -> Optional[dict]:
        character = await cult.get(ctx.author.id)
        if character is None or not character["path"]:
            await ctx.send(view=error_layout("Not awakened", "You have not awakened yet. Use `cultivate awaken` to begin."))
            return None
        return character

    @commands.group(name="board", aliases=["calamity", "calamities"], invoke_without_command=True, help="Today's calamity bosses. They are generated fresh every day and one fight each.")
    async def board(self, ctx: commands.Context):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        bosses = calamity.board()
        done = await calamity.attempts(ctx.author.id)
        data = await asyncio.to_thread(boss_card.render_board, bosses, done)
        lines = []
        for boss in bosses:
            state = "defeated" if done.get(boss["slot"]) else "spent" if boss["slot"] in done else "open"
            weak = elements.ELEMENTS[calamity.weakness(boss)]["name"]
            lines.append(f"**{boss['slot'] + 1}.** {boss['name']} ({boss['zh']}) · {boss['rank'].title()} · weak to **{weak}** · {calamity.affix_text(boss)} · *{state}*")
        lines.append(f"\n-# Each boss can be fought once a day and the board changes at midnight UTC. Use `{ctx.clean_prefix}board hunt <1-4>`. Exploit the weakness with matching techniques for extra damage. Bounties and weekly contracts: `{ctx.clean_prefix}world bounty`. Lords and Calamities drop Realm Keys for `{ctx.clean_prefix}realm`.")
        await ctx.send(view=picture_layout(f"{e('esword')} Calamity board", "\n".join(lines), "board.png"), files=[discord.File(io.BytesIO(data), "board.png")])

    @board.command(name="hunt", aliases=["fight", "challenge"], help="Challenge a calamity boss. Usage: board hunt <1-4>")
    async def hunt(self, ctx: commands.Context, slot: int = 0):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        if slot < 1 or slot > len(calamity.SLOTS):
            return await ctx.send(view=error_layout("Which boss?", f"Pick a number from 1 to {len(calamity.SLOTS)}. See `{ctx.clean_prefix}board`."))
        if ctx.author.id in self.active():
            return await ctx.send(view=error_layout("Already fighting", "Finish your current fight first."))
        result = await calamity.begin(ctx.author.id, slot - 1)
        if not result["ok"]:
            reasons = {
                "hurt": ("You are injured", f"You recover in **{duration(result.get('wait', 0))}**. A Healing Pill cures it."),
                "done": ("Already faced", "You already took on that boss today. A new board arrives at midnight UTC."),
            }
            title, body = reasons.get(result["reason"], ("Cannot hunt", "That did not work."))
            return await ctx.send(view=error_layout(title, body))
        state = result["state"]
        boss = result["boss"]
        state["log"] = [f"**{boss['name']}** rises. Weak to **{elements.ELEMENTS[calamity.weakness(boss)]['name']}**. {calamity.affix_text(boss)}."]
        state["on_done"] = self.finished(ctx.author.id)
        state["show_anim"] = True
        state["media"] = "boss.png"
        data = await asyncio.to_thread(boss_card.render_portrait, boss)
        self.active().add(ctx.author.id)
        await ctx.send(view=fight_layout(state, ctx.author.id, 0, self.active()), files=[discord.File(io.BytesIO(data), "boss.png")], allowed_mentions=NO_PINGS)

    def finished(self, user_id: int):
        async def callback(interaction: discord.Interaction, state: dict):
            e = emoji_manager.get
            outcome = await calamity.finish(user_id, state)
            parts = outcome["parts"]
            if outcome["result"] == "win":
                body = f"**{state['m']['name']}** collapses.\n" + "\n".join(reward_lines(parts)) + weapon_note(parts)
                return await interaction.response.edit_message(view=success_layout(f"{e('esword')} Calamity slain", body), attachments=[])
            lost = f" You lose **{parts['qi_lost']:,}** qi." if parts.get("qi_lost") else ""
            await interaction.response.edit_message(view=error_layout("Driven back", f"**{state['m']['name']}** was too much this time.{lost} That boss will not return today.{weapon_note(parts)}"), attachments=[])
        return callback


async def setup(bot: commands.Bot):
    await bot.add_cog(Board(bot))
