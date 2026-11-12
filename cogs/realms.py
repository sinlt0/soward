import asyncio
import io
import random
import time
from typing import Optional

import discord
from discord.ext import commands

from cogs.cultivation import NO_PINGS, fight_layout, item_name, weapon_note
from cogs.economy import duration
from cogs.world import ChoiceView
from rpg import calamity, elements, engine as cult, gear, realms, stones
from utils import boss_card, coins, emoji_manager
from utils.components import error_layout, info_layout, success_layout

FLOOR_TEXT = {
    "monster": "Something that belongs to this realm turns toward you.",
    "elite": "A stronger guardian blocks the passage, humming with the realm's power.",
    "treasure": "A sealed cache rests against the wall, wrapped in the realm's own ward.",
    "spring": "A pool of condensed spirit qi sits in an alcove, untouched for ages.",
    "shrine": "An old shrine stands here. Its stone eyes follow you and wait for an offering.",
    "guardian": "The heart of the realm. Its master has been waiting since the doors first opened.",
}


def element_name(key: str) -> str:
    return elements.ELEMENTS[key]["name"]


def loot_line(run: dict) -> str:
    loot = run["loot"]
    return f"-# Loot so far: {stones.fmt(loot['coins'])}, {loot['essence']} {element_name(run['realm']['element'])} essence, {sum(loot['materials'].values()) + sum(loot['herbs'].values())} materials and herbs. Health {int(run['hp'] * 100)}%"


class Realms(commands.Cog):
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

    @commands.group(name="realm", aliases=["realms", "secret", "secretrealm"], invoke_without_command=True, help="Secret realms. Spend a Realm Key to delve floor by floor for essences and treasure.")
    async def realm(self, ctx: commands.Context):
        e = emoji_manager.get
        character = await self.need_character(ctx)
        if character is None:
            return
        held = await cult.inventory(ctx.author.id)
        lines = []
        for item in realms.open_realms():
            tag = " **(hidden)**" if item["hidden"] else ""
            lines.append(f"**{item['slot'] + 1}.** {item['name']} ({item['zh']}){tag} · {element_name(item['element'])} · {item['floors']} floors + guardian · {item['keys']} key(s)\n-# {item['about']} Use {realms.counter(item)} techniques.")
        lines.append(f"\nYou carry **{held.get('realm_key', 0)}** Realm Key(s).")
        essences = ", ".join(f"{held.get(elements.essence(key), 0)} {value['name']}" for key, value in elements.ELEMENTS.items())
        lines.append(f"-# Essences: {essences}")
        current = realms.attunement(character)
        if current:
            lines.append(f"**Attuned to {element_name(current[0])}** for {duration(current[1])}: its techniques deal 25% more damage.")
        lines.append(f"\n-# Enter with `{ctx.clean_prefix}realm enter <number>`. Realm Keys drop from calamity bosses (`{ctx.clean_prefix}board`) and bounty chests. Essences from a realm let you attune with `{ctx.clean_prefix}realm attune <element>` ({realms.ATTUNE_COST} essences, {realms.ATTUNE_HOURS} hours) for stronger boss hunts.")
        await ctx.send(view=info_layout(f"{e('ecult')} Secret realms", "\n".join(lines)))

    @realm.command(name="attune", aliases=["imbue"], help="Spend essences to empower one element for 12 hours. Usage: realm attune <element>")
    async def attune_command(self, ctx: commands.Context, element: str = ""):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        key = element.lower().strip()
        key = next((k for k, v in elements.ELEMENTS.items() if key in (k, v["name"].lower())), key)
        result = await realms.attune(ctx.author.id, key)
        if not result["ok"]:
            names = ", ".join(v["name"].lower() for v in elements.ELEMENTS.values())
            reasons = {"unknown": f"Pick an element: {names}.", "essence": f"You need **{realms.ATTUNE_COST} {item_name(elements.essence(key))}**. Secret realms and calamity bosses drop them.", "none": "You have not awakened."}
            return await ctx.send(view=error_layout("Cannot attune", reasons.get(result["reason"], "That did not work.")))
        await ctx.send(view=success_layout(f"{e('ecult')} Attuned", f"Your **{element_name(key)}** techniques deal **25% more damage** for {realms.ATTUNE_HOURS} hours, on top of weaknesses."))

    @realm.command(name="enter", aliases=["delve", "start"], help="Enter a secret realm. Usage: realm enter <1-3>")
    async def enter(self, ctx: commands.Context, slot: int = 0):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        if ctx.author.id in self.active():
            return await ctx.send(view=error_layout("Already fighting", "Finish your current fight first."))
        result = await realms.begin(ctx.author.id, slot - 1)
        if not result["ok"]:
            reasons = {
                "hurt": f"You are injured for another **{duration(result.get('wait', 0))}**.",
                "slot": f"Pick one of today's realms. See `{ctx.clean_prefix}realm`.",
                "limit": f"You can enter {realms.DAILY} realms a day.",
                "key": f"You need **{result.get('need', 1)} Realm Key(s)**. Calamity bosses and bounty chests drop them.",
            }
            return await ctx.send(view=error_layout("Cannot enter", reasons.get(result["reason"], "That did not work.")))
        run = result["run"]
        await ctx.send(view=self.floor_view(run, f"The doors of the **{run['realm']['name']}** ({run['realm']['zh']}) close behind you.\n*{run['realm']['about']}*"), allowed_mentions=NO_PINGS)

    def floor_view(self, run: dict, note: str):
        e = emoji_manager.get
        user_id = run["user_id"]
        kind = realms.kind_at(run)
        index = run["index"]
        total = len(run["floors"])
        label = "Guardian" if kind == "guardian" else f"Floor {index + 1}/{total - 1}"
        body = FLOOR_TEXT[kind]
        retreat = ("Retreat with loot", discord.ButtonStyle.secondary, self.end(run, "retreat"))
        if kind in ("monster", "elite", "guardian"):
            choices = [("Fight", discord.ButtonStyle.danger, self.fight(run))]
        elif kind == "treasure":
            choices = [("Break the ward", discord.ButtonStyle.danger, self.step(run, "bold")), ("Unseal carefully", discord.ButtonStyle.success, self.step(run, "careful"))]
        elif kind == "spring":
            choices = [("Rest", discord.ButtonStyle.success, self.step(run, "rest"))]
        else:
            choices = [("Pray for might", discord.ButtonStyle.primary, self.step(run, "might")), ("Pray for vigor", discord.ButtonStyle.success, self.step(run, "vigor"))]
        if index > 0:
            choices.append(retreat)
        return ChoiceView(user_id, f"{e('ecult')} {run['realm']['name']} · {label}", f"{note}\n\n{body}\n\n{loot_line(run)}", choices, timeout=300, on_timeout=self.timeout(run))

    def timeout(self, run: dict):
        async def callback():
            if not run.get("closed"):
                run["closed"] = True
                await realms.finish(run["user_id"], run, "retreat")
        return callback

    def end(self, run: dict, outcome: str):
        async def callback(interaction: discord.Interaction):
            await self.close(interaction, run, outcome)
        return callback

    async def close(self, interaction: discord.Interaction, run: dict, outcome: str, note: str = ""):
        e = emoji_manager.get
        run["closed"] = True
        parts = await realms.finish(run["user_id"], run, outcome)
        name = run["realm"]["name"]
        lines = [note] if note else []
        lines.append({"clear": f"The guardian falls and the **{name}** opens its vault to you.", "retreat": f"You leave the **{name}** while you still can.", "fail": f"The **{name}** throws you out. You keep only half of what you gathered."}[outcome])
        lines.append(f"+**{stones.fmt(parts['coins'])}**")
        if parts.get("qi"):
            lines.append(f"+{coins.fmt(parts['qi'])} qi")
        for key, count in parts["items"].items():
            lines.append(f"+{count} **{item_name(key)}**")
        for dropped in parts["gear"]:
            lines.append(f"{e('esword')} **{item_name(dropped)}**")
        if parts.get("overflow"):
            lines.append(f"-# A pouch was full, so extras sold for {stones.fmt(parts['overflow'])}.")
        if parts.get("qi_lost"):
            lines.append(f"You lose {coins.fmt(parts['qi_lost'])} qi.")
        layout = (success_layout if outcome == "clear" else error_layout if outcome == "fail" else info_layout)(f"{e('ecult')} {name}", "\n".join(lines) + weapon_note(parts))
        await interaction.response.edit_message(view=layout, attachments=[])

    def step(self, run: dict, action: str):
        async def callback(interaction: discord.Interaction):
            character = await cult.get(run["user_id"])
            if action in ("bold", "careful"):
                got = realms.treasure(run, character, action == "careful", random)
                note = f"A ward flares and burns you. Health {int(got['hp'] * 100)}%." if got.get("trap") else f"You open the cache: +{stones.fmt(got['coins'])}" + (f", +{got['essence']} essence" if got.get("essence") else "") + "."
            elif action == "rest":
                note = f"You drink the spirit qi and recover **{int(realms.rest(run, realms.SPRING_HEAL) * 100)}%** health."
            else:
                got = realms.pray(run, action)
                note = f"The shrine hums. Your strikes grow sharper (+15% damage), at the cost of some health." if action == "might" else f"The shrine mends you for **{int(got['healed'] * 100)}%** health."
            realms.advance(run)
            await interaction.response.edit_message(view=self.floor_view(run, note), allowed_mentions=NO_PINGS)
        return callback

    def fight(self, run: dict):
        async def callback(interaction: discord.Interaction):
            user_id = run["user_id"]
            character = await cult.get(user_id)
            state = realms.fight_state(character, run)
            boss = realms.boss_for(run)
            state["log"] = [f"**{boss['name']}** blocks the way. Weak to **{element_name(elements.ELEMENTS[boss['element']]['weak'])}**."]
            state["on_done"] = self.fight_done(run)
            state["show_anim"] = True
            state["media"] = "boss.png"
            data = await asyncio.to_thread(boss_card.render_portrait, boss)
            self.active().add(user_id)
            await interaction.response.edit_message(view=fight_layout(state, user_id, 0, self.active()), attachments=[discord.File(io.BytesIO(data), "boss.png")], allowed_mentions=NO_PINGS)
        return callback

    def fight_done(self, run: dict):
        async def callback(interaction: discord.Interaction, state: dict):
            character = await cult.get(run["user_id"])
            result = state["done"]
            kind = realms.kind_at(run)
            if result == "lose":
                return await self.close(interaction, run, "fail", f"**{state['m']['name']}** overpowers you.")
            if result == "flee":
                return await self.close(interaction, run, "retreat", "You break away from the fight.")
            realms.add_loot(run, character, kind, random)
            run["hp"] = max(0.05, state["p"]["hp"] / state["p"]["max"])
            if realms.advance(run):
                return await self.close(interaction, run, "clear", f"**{state['m']['name']}** falls.")
            await interaction.response.edit_message(view=self.floor_view(run, f"**{state['m']['name']}** falls."), attachments=[], allowed_mentions=NO_PINGS)
        return callback


async def setup(bot: commands.Bot):
    await bot.add_cog(Realms(bot))
