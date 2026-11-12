import asyncio
import io
import random
import time
from typing import Optional

import discord
from discord.ext import commands

from cogs.economy import duration
from rpg import transcend as heaven, stones, pouch, arts, bestiary, combat, engine as cult, gear, npcs as people, races, sect, settings, story, titles, ways
from utils import clans, coins, emoji_manager
from utils.colors import NEUTRAL, SUCCESS
from utils import anim_lib, tribulation_card, tribulation_ui
from utils.components import error_layout, footer_block, info_layout, success_layout

NO_PINGS = discord.AllowedMentions.none()


def bar(value: int, total: int, size: int = 12) -> str:
    filled = 0 if total <= 0 else min(size, int(size * value / total))
    return "▰" * filled + "▱" * (size - filled)


def find_item(text: str) -> Optional[str]:
    text = text.strip().lower().replace(" ", "_")
    for key, item in settings.ITEMS.items():
        if text in (key, item["name"].lower().replace(" ", "_")):
            return key
    matches = [key for key, item in settings.ITEMS.items() if text in key or text in item["name"].lower().replace(" ", "_")]
    return matches[0] if len(matches) == 1 else None


def race_line(character: dict) -> str:
    race = cult.race_info(character)
    return f"**{race['name']} ({race['zh']})**"


def root_text(character: dict) -> str:
    return f"{race_line(character)} · **{character['root']} root** · {character['rarity'].title()} · {character['quality']} quality · qi speed x{cult.multiplier(character):.2f}"


def bloodline_text(character: dict) -> str:
    tags = [tag for tag in (character.get("bloodline") or "").split("+") if tag]
    if not tags:
        return "none"
    names = {"root": "spiritual root", "race": "race"}
    return "inherited " + " and ".join(names[tag] for tag in tags) + " from a parent"


def way_status(character: dict) -> str:
    way = cult.way_info(character)
    if not way:
        return "not chosen yet, use `cultivate way`"
    return f"{way['name']} ({way['zh']})\n-# {way['perk']} {way['flaw']}"


def hp_bar(hp: int, total: int, size: int = 12) -> str:
    return bar(max(0, hp), total, size)


def fight_layout(state: dict, owner: int, left: int, active: set) -> discord.ui.LayoutView:
    e = emoji_manager.get
    view = FightView(owner, state, left, active)
    p, m = state["p"], state["m"]
    lines = [
        f"## {e('esword')} {m['name']}" + (f" ({m['zh']})" if m["zh"] else ""),
        f"{e('eheart')} **{m['name']}** {max(0, m['hp'])}/{m['max']}\n{hp_bar(m['hp'], m['max'])}",
        f"{e('eheart')} **You** {max(0, p['hp'])}/{p['max']}\n{hp_bar(p['hp'], p['max'])}",
    ]
    status = []
    if p["guard"] > 0:
        status.append(f"{e('eshield')} guarding")
    if p["evade"] > 0:
        status.append("array ready")
    if m["poison"] > 0:
        status.append("enemy burning")
    if m["stun"] > 0:
        status.append("enemy bound")
    if p.get("buff", 0) > 0:
        status.append(f"empowered ({p['buff']})")
    if m.get("weak", 0) > 0:
        status.append("enemy weakened")
    if status:
        lines.append("-# " + " · ".join(status))
    waiting = [f"{tech['name']} ({p['cd'][key]})" for key, tech in state["techs"].items() if p["cd"].get(key, 0) > 0]
    if waiting:
        lines.append("-# Recharging: " + ", ".join(waiting))
    if state.get("remnant") and state["turn"] == 1:
        lines.append(f"-# Born from {state['remnant']}.")
    if state["log"]:
        lines.append("\n" + "\n".join(state["log"]))
    tail = state.get("tag") or (f"party of {len(state['party'])}" if state.get("party") else "clan boss raid" if state.get("clan_boss") else f"{left} fights left today")
    lines.append(f"-# Turn {state['turn']} of {combat.MAX_TURNS} · {tail}")
    container = discord.ui.Container(accent_color=NEUTRAL)
    if state.get("show_anim"):
        container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://" + state.get("media", "attack.gif"))))
    container.add_item(discord.ui.TextDisplay("\n".join(lines)))
    container.add_item(discord.ui.Separator())
    container.add_item(view.actions)
    if view.techs is not None:
        container.add_item(view.techs)
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


def weapon_note(parts: dict) -> str:
    note = parts.get("weapon")
    if not note:
        return ""
    if note["broke"]:
        return f"\n**Your {note['label']} shattered!** Craft or buy another with `cultivate gear craft weapon`."
    return f"\nYour weapon is wearing out: **{note['durability']}/{note['max']}** durability. Mend it with `cultivate gear repair`."


def herb_lines(parts: dict) -> list[str]:
    lines = []
    if parts.get("herb"):
        key, count = parts["herb"]
        lines.append(f"+{count} **{gear.MATERIALS[key]['name']}** ({gear.MATERIALS[key]['zh']})")
    if parts.get("overflow"):
        lines.append(f"-# Your pouches were full, so {parts.get('overflow_items', 0)} extra items sold for {stones.fmt(parts['overflow'])}. Upgrade with `pouch`.")
    return lines


def pvp_result_layout(state: dict, outcome: dict):
    e = emoji_manager.get
    m = state["m"]
    parts = outcome["parts"]
    if outcome["result"] == "win":
        lines = [f"You defeated **{m['name']}**."]
        if parts.get("stolen"):
            lines.append(f"You took **{stones.fmt(parts['stolen'])}** from their pouch.")
        elif parts.get("capped"):
            lines.append("They have already been looted enough today, so you take no spirit stones.")
        if parts.get("target_qi"):
            lines.append(f"They lose {coins.fmt(parts['target_qi'])} qi.")
        if parts.get("item"):
            lines.append(f"You seize a **{item_name(parts['item'])}** from their bag.")
        return success_layout(f"{e('esword')} Raid won", "\n".join(lines) + weapon_note(parts))
    if outcome["result"] == "lose":
        lines = [f"**{m['name']}** beats you back."]
        if parts.get("coins_lost"):
            lines.append(f"You lose **{stones.fmt(parts['coins_lost'])}** from your pouch.")
        if parts.get("qi_lost"):
            lines.append(f"You lose {coins.fmt(parts['qi_lost'])} qi.")
        if parts.get("item_lost"):
            lines.append(f"You also drop a **{item_name(parts['item_lost'])}** while fleeing.")
        return error_layout("Raid failed", "\n".join(lines) + weapon_note(parts))
    return info_layout(f"{e('esword')} Raid over", f"You back away from **{m['name']}** with nothing gained or lost.")


def item_name(key: str) -> str:
    if key in settings.ITEMS:
        return settings.ITEMS[key]["name"]
    if key in settings.BREWS:
        return settings.BREWS[key]["name"]
    if key in gear.MATERIALS:
        return gear.MATERIALS[key]["name"]
    return gear.name(key)


def party_result_layout(state: dict, outcome: dict):
    e = emoji_manager.get
    m = state["m"]
    if outcome["result"] == "win":
        lines = [f"Your family defeated **{m['name']}**!"]
        for uid, parts in outcome["members"].items():
            bits = [f"+{stones.fmt(parts.get('coins', 0))}", f"+{coins.fmt(parts.get('qi', 0))} qi"]
            if parts.get("material"):
                key, count = parts["material"]
                bits.append(f"{count} {gear.MATERIALS[key]['name']}")
            if parts.get("overflow"):
                bits.append(f"{stones.fmt(parts['overflow'])} from overflow")
            if parts.get("gear"):
                bits.append(f"a **{gear.name(parts['gear'])}**")
            lines.append(f"<@{uid}> " + " · ".join(bits) + weapon_note(parts).replace("\n", " "))
        return success_layout(f"{e('esword')} Dungeon cleared", "\n".join(lines))
    if outcome["result"] == "lose":
        return error_layout("Dungeon failed", f"**{m['name']}** drives your family out. Everyone loses a little qi.")
    return info_layout(f"{e('esword')} Dungeon over", f"Your family retreats from **{m['name']}**.")


def boss_result_layout(state: dict, outcome: dict):
    e = emoji_manager.get
    m = state["m"]
    parts = outcome["parts"]
    lines = [f"You wound **{m['name']}** for **{coins.fmt(parts.get('damage', 0))}** damage."]
    if outcome.get("late"):
        lines = [f"**{m['name']}** has already fallen. Your strike came too late."]
    if parts.get("qi_lost"):
        lines.append(f"You lose {coins.fmt(parts['qi_lost'])} qi.")
    if outcome.get("killed"):
        lines.append(f"\n**{m['name']} is slain!**")
        for uid, entry in outcome["payouts"].items():
            bits = [f"+{stones.fmt(entry['coins'])}"]
            if entry.get("material"):
                key, count = entry["material"]
                bits.append(f"{count} {gear.MATERIALS[key]['name']}")
            if entry.get("gear"):
                bits.append(f"a **{gear.name(entry['gear'])}**")
            lines.append(f"<@{uid}> " + " · ".join(bits))
        return success_layout(f"{e('esword')} Sect boss slain", "\n".join(lines))
    return info_layout(f"{e('esword')} Boss raid", "\n".join(lines))


def result_layout(state: dict, outcome: dict):
    if state.get("clan_boss"):
        return boss_result_layout(state, outcome)
    if state.get("party"):
        return party_result_layout(state, outcome)
    if state.get("pvp"):
        return pvp_result_layout(state, outcome)
    e = emoji_manager.get
    m = state["m"]
    parts = outcome["parts"]
    if outcome["result"] == "win":
        lines = [f"You defeated **{m['name']}** in {state['turn']} turns."]
        if parts.get("coins"):
            lines.append(f"+**{stones.fmt(parts['coins'])}**")
        if parts.get("qi"):
            lines.append(f"+**{coins.fmt(parts['qi'])}** qi")
        if parts.get("material"):
            key, count = parts["material"]
            lines.append(f"+{count} **{gear.MATERIALS[key]['name']}** ({gear.MATERIALS[key]['zh']})")
        lines.extend(herb_lines(parts))
        if parts.get("gear"):
            lines.append(f"{e('esword')} It dropped a **{gear.name(parts['gear'])}**!")
        return success_layout(f"{e('esword')} Victory", "\n".join(lines) + weapon_note(parts))
    if outcome["result"] == "lose":
        lost = f"\nYou lose **{coins.fmt(parts.get('qi_lost', 0))}** qi while recovering." if parts.get("qi_lost") else ""
        return error_layout("Defeated", f"**{m['name']}** beats you down. You limp away.{lost}{weapon_note(parts)}")
    return info_layout(f"{e('esword')} Fight over", f"You leave **{m['name']}** behind.")


class FightActions(discord.ui.ActionRow):
    def __init__(self, owner: "FightView"):
        super().__init__(
            discord.ui.Button(label="Attack", style=discord.ButtonStyle.primary),
            discord.ui.Button(label="Defend", style=discord.ButtonStyle.secondary),
            discord.ui.Button(label="Flee", style=discord.ButtonStyle.danger),
        )
        self.owner = owner
        for button, action in zip(self.children, ("attack", "defend", "flee")):
            button.callback = self.make(action)

    def make(self, action: str):
        async def callback(interaction: discord.Interaction):
            await self.owner.take(interaction, action)
        return callback


class TechRow(discord.ui.ActionRow):
    def __init__(self, owner: "FightView", options: dict):
        super().__init__(discord.ui.Select(
            placeholder="Use a technique",
            options=[discord.SelectOption(label=f"{tech['name']} ({tech['zh']})", value=key, description=tech["info"][:100]) for key, tech in options.items()]))
        self.owner = owner
        self.children[0].callback = self.chosen

    async def chosen(self, interaction: discord.Interaction):
        await self.owner.take(interaction, self.children[0].values[0])


class FightView(discord.ui.LayoutView):
    def __init__(self, owner: int, state: dict, left: int, active: set):
        super().__init__(timeout=180)
        self.owner = owner
        self.state = state
        self.left = left
        self.active = active
        self.actions = FightActions(self)
        options = combat.ready(state)
        self.techs = TechRow(self, options) if options else None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await interaction.response.send_message("This is not your fight.", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        self.active.discard(self.owner)

    async def take(self, interaction: discord.Interaction, action: str):
        combat.act(self.state, action, random)
        self.stop()
        if self.state["done"]:
            self.active.discard(self.owner)
            if self.state.get("on_done"):
                return await self.state["on_done"](interaction, self.state)
            if self.state.get("clan_boss"):
                outcome = await sect.boss_finish(self.owner, self.state)
            elif self.state.get("party"):
                outcome = await cult.dungeon_finish(self.state)
            else:
                outcome = await (cult.pvp_finish if self.state.get("pvp") else cult.fight_finish)(self.owner, self.state)
            self.state["show_anim"] = False
            return await interaction.response.edit_message(view=result_layout(self.state, outcome), attachments=[])
        keys = tuple(key for key in (self.state.get("anim"), self.state.get("foe")) if key)
        data = await asyncio.to_thread(anim_lib.compose, keys) if keys else b""
        self.state["show_anim"] = bool(data)
        self.state["media"] = "attack.gif"
        attachments = [discord.File(io.BytesIO(data), "attack.gif")] if data else []
        await interaction.response.edit_message(view=fight_layout(self.state, self.owner, self.left, self.active), attachments=attachments)


def awaken_layout(character: dict, rerolls_left: int, owner: int) -> discord.ui.LayoutView:
    e = emoji_manager.get
    view = AwakenView(owner, rerolls_left, character)
    container = discord.ui.Container(accent_color=NEUTRAL)
    race = cult.race_info(character)
    allowed = cult.allowed_paths(character)
    path_lines = [
        f"**{info['name']}** ({info['origin']}): {info['perk']}" if key in allowed else f"~~{info['name']}~~ (closed to your race)"
        for key, info in settings.PATHS.items()
    ]
    way = cult.way_info(character)
    if way:
        way_text = f"**Way:** {way['name']} ({way['zh']})\n{way['perk']}\n-# {way['flaw']}\n\nNow choose the **path** you will walk. You cannot change it later.\n" + "\n".join(path_lines)
    else:
        way_text = "First choose your **way**, the kind of cultivator you will be. You cannot change it later.\n" + "\n".join(f"**{info['name']}** ({info['zh']}): {info['perk']}" for info in ways.WAYS.values())
    body = (
        f"## {e('eroot')} Your spiritual root\n{root_text(character)}\n"
        f"{race['perk']}\n-# {race['flaw']}\n"
        + (f"-# Bloodline: {bloodline_text(character)}\n" if character.get("bloodline") else "")
        + "\n"
        + way_text
    )
    container.add_item(discord.ui.TextDisplay(body))
    container.add_item(discord.ui.Separator())
    if not way:
        container.add_item(view.ways)
    else:
        container.add_item(view.paths)
    if rerolls_left > 0:
        container.add_item(view.reroll_row)
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


class WayRow(discord.ui.ActionRow):
    def __init__(self, owner: "AwakenView"):
        super().__init__(discord.ui.Select(placeholder="Choose your way", options=[discord.SelectOption(label=info["name"], value=key, description=info["perk"][:100]) for key, info in ways.WAYS.items()]))
        self.owner = owner
        self.children[0].callback = self.chosen

    async def chosen(self, interaction: discord.Interaction):
        await self.owner.pick_way(interaction, self.children[0].values[0])


class PathRow(discord.ui.ActionRow):
    def __init__(self, owner: "AwakenView", allowed: tuple):
        super().__init__(*[discord.ui.Button(label=info["name"], style=discord.ButtonStyle.primary, disabled=key not in allowed) for key, info in settings.PATHS.items()])
        self.owner = owner
        for button, key in zip(self.children, settings.PATHS):
            button.callback = self.make(key)

    def make(self, key: str):
        async def callback(interaction: discord.Interaction):
            await self.owner.pick(interaction, key)
        return callback


class RerollRow(discord.ui.ActionRow):
    def __init__(self, owner: "AwakenView", left: int):
        super().__init__(discord.ui.Button(label=f"Reroll root ({left} left)", style=discord.ButtonStyle.secondary))
        self.owner = owner
        self.children[0].callback = self.again

    async def again(self, interaction: discord.Interaction):
        await self.owner.again(interaction)


class AwakenView(discord.ui.LayoutView):
    def __init__(self, owner: int, left: int, character: dict):
        super().__init__(timeout=300)
        self.owner = owner
        self.left = left
        self.ways = WayRow(self)
        self.paths = PathRow(self, cult.allowed_paths(character))
        self.reroll_row = RerollRow(self, left)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await interaction.response.send_message("This is not your awakening.", ephemeral=True)
            return False
        return True

    async def pick_way(self, interaction: discord.Interaction, key: str):
        character = await cult.choose_way(self.owner, key)
        if character is None:
            return await interaction.response.edit_message(view=error_layout("Cannot choose that way", "Your way is already chosen."))
        self.stop()
        left = max(0, settings.REROLLS - character["rerolls"])
        await interaction.response.edit_message(view=awaken_layout(character, left, self.owner))

    async def pick(self, interaction: discord.Interaction, key: str):
        character = await cult.choose_path(self.owner, key)
        if character is None:
            return await interaction.response.edit_message(view=error_layout("Cannot choose that path", "Your path is already chosen, you have not chosen a way yet, or your race cannot walk it."))
        e = emoji_manager.get
        info = settings.PATHS[key]
        self.stop()
        await interaction.response.edit_message(view=success_layout(
            f"{e('ecult')} Awakened",
            f"{root_text(character)}\nWay: **{cult.way_info(character)['name']}** · Path: **{info['name']}** ({info['perk']})\n\nYou begin as a **{cult.stage_name(character)}** cultivator. Qi gathers while you are away. Use `world guide` for your personal guide, `cultivate` to check your progress, `cultivate meditate` to focus, and `cultivate breakthrough` when your qi is full."))

    async def again(self, interaction: discord.Interaction):
        character = await cult.reroll(self.owner)
        if character is None:
            return await interaction.response.send_message("You cannot reroll any more.", ephemeral=True)
        self.stop()
        left = settings.REROLLS - character["rerolls"]
        view = awaken_layout(character, left, self.owner)
        await interaction.response.edit_message(view=view)


def parts_text(parts: dict, e) -> str:
    lines = []
    if parts.get("paid"):
        lines.append(f"{e('ecoin')} Paid **{stones.fmt(parts['paid'])}**")
    if parts.get("coins"):
        lines.append(f"{e('ecoin')} **+{stones.fmt(parts['coins'])}**")
    if parts.get("lost"):
        lines.append(f"{e('ecoin')} Lost **{stones.fmt(parts['lost'])}**")
    if "qi" in parts:
        lines.append(f"{e('eqi')} **+{coins.fmt(parts['qi'])}** qi" if parts["qi"] else f"{e('eqi')} Your qi is already full, so the qi was wasted")
    if parts.get("item"):
        lines.append(f"{e('epill')} Got a **{settings.ITEMS[parts['item']]['name']}**")
    if parts.get("bonus"):
        lines.append(f"{e('etribulation')} Tribulation chance **+{parts['bonus']}%**")
    return "\n".join(lines)


class EventButton(discord.ui.Button):
    def __init__(self, owner_view: "EventView", index: int, label: str):
        super().__init__(label=label, style=discord.ButtonStyle.primary)
        self.owner_view = owner_view
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        await self.owner_view.choose(interaction, self.index)


class EventView(discord.ui.LayoutView):
    def __init__(self, owner: int, event: dict, left: int):
        super().__init__(timeout=180)
        self.owner = owner
        self.event = event
        e = emoji_manager.get
        npc = people.NPCS[event["npc"]]
        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(f"## {e('ecult')} {event['title']}\n**{npc['name']}** · {npc['place']}\n\n{event['text']}\n-# {left} more today after this"))
        container.add_item(discord.ui.Separator())
        row = discord.ui.ActionRow()
        for index, choice in enumerate(event["choices"]):
            row.add_item(EventButton(self, index, choice["label"]))
        container.add_item(row)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner:
            await interaction.response.send_message("This is not your path.", ephemeral=True)
            return False
        return True

    async def choose(self, interaction: discord.Interaction, index: int):
        self.stop()
        result = await cult.resolve_event(self.owner, self.event, index)
        e = emoji_manager.get
        if not result["ok"]:
            return await interaction.response.edit_message(view=error_layout("Cannot afford it", f"That needs **{stones.fmt(result.get('cost', 0))}**."))
        extra = parts_text(result["parts"], e)
        await interaction.response.edit_message(view=info_layout(f"{e('ecult')} {self.event['title']}", f"{result['text']}" + (f"\n\n{extra}" if extra else "")))


class Cultivation(commands.Cog):
    category = "Cultivation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active: set = set()

    async def need_character(self, ctx: commands.Context, user_id: Optional[int] = None) -> Optional[dict]:
        character = await cult.get(user_id or ctx.author.id)
        if character is None or not character["path"]:
            who = "You have not" if not user_id or user_id == ctx.author.id else "They have not"
            await ctx.send(view=error_layout("Not awakened", f"{who} awakened yet. Use `cultivate awaken` to begin."))
            return None
        return character

    @commands.group(name="cultivate", aliases=["cult", "cultivation", "xiu"], invoke_without_command=True, help="Your cultivation. Awaken, gather qi and break through realms.")
    async def cultivate(self, ctx: commands.Context):
        await self.status(ctx)

    @cultivate.command(name="awaken", aliases=["begin", "start"], help="Awaken your spiritual root and choose a path.")
    async def awaken(self, ctx: commands.Context):
        existing = await cult.get(ctx.author.id)
        if existing and existing["path"]:
            return await ctx.send(view=error_layout("Already awakened", "You already walk a path. Use `cultivate` to see your progress."))
        character = existing or await cult.awaken(ctx.author.id)
        left = max(0, settings.REROLLS - character["rerolls"])
        await ctx.send(view=awaken_layout(character, left, ctx.author.id))

    @cultivate.command(name="status", aliases=["stats", "me", "profile", "collect"], help="Show your cultivation. Usage: cultivate status [user]")
    async def status(self, ctx: commands.Context, user: Optional[discord.User] = None):
        e = emoji_manager.get
        target = user or ctx.author
        character = await self.need_character(ctx, target.id)
        if character is None:
            return
        now = time.time()
        gained = cult.settle(character, now)
        await cult.save(character)
        if target.id == ctx.author.id:
            await cult.check_titles(target.id, now)
        cost = cult.need(character)
        major = cult.is_major(character)
        title_line = titles.TITLES.get(character.get("title") or "")
        standing = await clans.standing(target.id) or 'A wanderer with no clan. Join one with `clan` and it becomes your great family.'
        heading = cult.realm_text(character) + (f" · {titles.label(character.get('title') or '', character.get('transcend') or 0)} ({title_line['zh']})" if title_line else "")
        lines = [
            f"**{heading}**\n-# {standing}",
            f"{e('eroot')} {root_text(character)}",
            f"-# {cult.race_info(character)['perk']} {cult.race_info(character)['flaw']}",
            f"**Way:** {way_status(character)}",
            f"**Path:** {cult.path_info(character)['name']} ({cult.path_info(character)['perk']})",
            f"**Safe:** {stones.fmt(character['safe'])}/{stones.fmt(cult.safe_cap(character))}" + (" · protected from raids" if cult.shielded(character, now) else " · open to raids"),
            f"**Bloodline:** {bloodline_text(character)}",
            f"**Gear:** " + ", ".join(gear.name(character[slot]) if character.get(slot) else f"no {slot}" for slot in gear.SLOTS),
            "",
            f"{e('eqi')} **Qi:** {coins.fmt(character['qi'])}/{coins.fmt(cost)}\n{bar(character['qi'], cost)}",
            f"**Idle gain:** {cult.idle_rate(character):.0f} qi an hour, banked for up to {cult.offline_hours(character)} hours",
        ]
        if gained:
            lines.append(f"-# {coins.fmt(gained)} qi was gathered since you were last here.")
        if character["qi"] >= cost:
            if major and not cult.gate_open(character):
                lines.append("\nYour qi is full, but the path beyond this realm is not open yet.")
            else:
                lines.append(f"\n{e('etribulation') if major else e('eqi')} Your qi is full. Use `cultivate breakthrough`.")
        chance = cult.major_chance(character) if major else cult.minor_chance(character)
        if major and cult.gate_open(character):
            lines.append(f"**Tribulation:** {chance}% chance · fee {stones.fmt(cult.realm_of(character)['fee'])}" + (f" · pills +{character['chance_bonus']}%" if character["chance_bonus"] else ""))
        elif major and heaven.check(character) in (None, "qi"):
            lines.append(f"**Transcend:** no higher realm is open. Defy the heavens with `cultivate transcend` ({heaven.waves_for(heaven.tier_for(character))} waves · fee {stones.fmt(heaven.fee_for(heaven.tier_for(character)))})")
        elif not major:
            lines.append(f"**Next breakthrough:** {chance}% chance")
        hurt = cult.hurt(character, now)
        if hurt:
            lines.append(f"\n**Injured:** recovers in {duration(hurt)}. A Healing Pill cures it.")
        ready = character["last_meditate"] + settings.MEDITATE_COOLDOWN - now
        lines.append(f"**Meditation:** {'ready' if ready <= 0 else 'ready in ' + duration(ready)}")
        await ctx.send(view=info_layout(f"{e('ecult')} {target.display_name}", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @cultivate.command(name="meditate", aliases=["focus", "train"], help="Focus your mind for a burst of qi.")
    async def meditate(self, ctx: commands.Context):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        result = await cult.meditate(ctx.author.id)
        if not result["ok"]:
            reason = result["reason"]
            if reason == "hurt":
                return await ctx.send(view=error_layout("You are injured", f"You cannot meditate for **{duration(result['wait'])}**. A Healing Pill cures it."))
            if reason == "cooldown":
                return await ctx.send(view=error_layout("Mind not settled", f"You can meditate again in **{duration(result['wait'])}**."))
            if reason == "full":
                return await ctx.send(view=error_layout("Qi is full", "You cannot hold more qi. Use `cultivate breakthrough`."))
        character = result["character"]
        await ctx.send(view=success_layout(f"{e('eqi')} Meditation", f"You focus and draw in **{coins.fmt(result['gain'])}** qi.\n{coins.fmt(character['qi'])}/{coins.fmt(cult.need(character))} {bar(character['qi'], cult.need(character))}"))

    @cultivate.command(name="transcend", aliases=["defy", "heaven"], help="Defy the heavens when no higher realm is open and endure the tribulation of transcendence.")
    async def transcend(self, ctx: commands.Context):
        character = await self.need_character(ctx)
        if character is None:
            return
        uid = ctx.author.id
        if uid in tribulation_ui.ACTIVE:
            return await ctx.send(view=error_layout("Already in tribulation", "Finish the tribulation you are in first."))
        settled = cult.settle(character, time.time())
        await cult.save(character)
        reason = heaven.check(character)
        if reason:
            title, body = tribulation_ui.REASONS[reason]
            if reason == "qi":
                body = f"The tribulation will not come until your qi is full. You have **{coins.fmt(character['qi'])}/{coins.fmt(cult.need(character))}**."
            if reason == "hurt":
                body = f"You recover in **{duration(cult.hurt(character, time.time()))}**. A Healing Pill cures it."
            return await ctx.send(view=error_layout(title, body))
        author = ctx.author
        avatar = await tribulation_ui.load_avatar(author)

        async def begin(interaction: discord.Interaction):
            await interaction.response.defer()
            started = await heaven.start(uid, rng=random)
            if not started["ok"]:
                reason = started["reason"]
                if reason == "fee":
                    return await interaction.edit_original_response(view=error_layout("Not enough spirit stones", f"The heavens demand **{stones.fmt(started['fee'])}** before they answer."), attachments=[])
                title, body = tribulation_ui.REASONS.get(reason, ("Cannot transcend", "That did not work."))
                return await interaction.edit_original_response(view=error_layout(title, body), attachments=[])
            tribulation_ui.ACTIVE.add(uid)
            state = started["state"]
            buffer = await asyncio.to_thread(tribulation_card.render_wave, state, author.display_name, avatar)
            view = tribulation_ui.TribulationView(state, uid, author.display_name, avatar, finish)
            await interaction.edit_original_response(view=view, attachments=[tribulation_ui.png_file(buffer)])
            view.message = await interaction.original_response()

        async def finish(interaction: discord.Interaction, state: dict, name: str, portrait, result):
            outcome = await heaven.finish(uid, state)
            await cult.check_titles(uid)
            buffer = await asyncio.to_thread(tribulation_card.render_final, state, name, portrait, result, outcome.get("title", ""))
            await interaction.edit_original_response(view=tribulation_ui.result_layout(outcome, state), attachments=[tribulation_ui.png_file(buffer)])

        await ctx.send(view=tribulation_ui.preview_layout(character, uid, begin), allowed_mentions=NO_PINGS)

    @cultivate.command(name="breakthrough", aliases=["advance", "tribulation", "bt"], help="Try to break through to the next stage or realm.")
    async def breakthrough(self, ctx: commands.Context):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        result = await cult.breakthrough(ctx.author.id)
        if not result["ok"]:
            reason = result["reason"]
            character = result["character"]
            if reason == "hurt":
                return await ctx.send(view=error_layout("You are injured", f"You cannot break through for **{duration(result['wait'])}**. A Healing Pill cures it."))
            if reason == "qi":
                return await ctx.send(view=error_layout("Not enough qi", f"You need **{coins.fmt(result['missing'])}** more qi ({coins.fmt(character['qi'])}/{coins.fmt(cult.need(character))})."))
            if reason == "gate":
                return await ctx.send(view=error_layout("The path is closed", f"The realm beyond has not opened yet. Your cultivation is at its current peak. You can defy the heavens instead with `{ctx.clean_prefix}cultivate transcend`."))
            return await ctx.send(view=error_layout("Cannot afford the tribulation", f"The tribulation needs **{stones.fmt(result['fee'])}**."))
        character = result["character"]
        icon = e("etribulation") if result["major"] else e("eqi")
        if result["won"]:
            text = f"**{result['before']}** to **{result['after']}**\n" + ("Lightning tears the sky and you endure it. You step into a new realm!" if result["major"] else "Your qi surges and settles. You advance.")
            return await ctx.send(view=success_layout(f"{icon} Breakthrough", f"{text}\n-# {result['chance']}% chance" + (f" · {stones.fmt(result['fee'])} paid" if result["fee"] else "")))
        hurt = cult.hurt(character, time.time())
        text = ("The tribulation lightning crushes your attempt." if result["major"] else "Your qi runs wild and the attempt fails.") + f"\nYou lost some qi and are injured for **{duration(hurt)}**."
        await ctx.send(view=error_layout(f"{icon} Breakthrough failed", f"{text}\n-# {result['chance']}% chance" + (f" · {stones.fmt(result['fee'])} lost" if result["fee"] else "")))

    @cultivate.command(name="shop", aliases=["store", "market"], help="See the pills you can buy.")
    async def shop(self, ctx: commands.Context):
        e = emoji_manager.get
        character = await cult.get(ctx.author.id)
        character = character if character and character["path"] else None
        lines = []
        for key, item in settings.ITEMS.items():
            lines.append(f"{e('epill')} **{item['name']}** · `{key}` · {stones.fmt(cult.price(key, character))}\n{item['info']}")
        lines.append("\n-# Buy with `cultivate buy <pill> [amount]` and use with `cultivate use <pill>`. Prices rise with your realm.")
        await ctx.send(view=info_layout(f"{e('epill')} Pill shop", "\n".join(lines)))

    @cultivate.command(name="buy", help="Buy a pill. Usage: cultivate buy <pill> [amount]")
    async def buy(self, ctx: commands.Context, item: str, amount: int = 1):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        key = find_item(item)
        if key is None:
            return await ctx.send(view=error_layout("Unknown pill", "Use `cultivate shop` to see the pills."))
        if not 1 <= amount <= 20:
            return await ctx.send(view=error_layout("Invalid amount", "Buy between 1 and 20 at a time."))
        result = await cult.buy(ctx.author.id, key, amount)
        if not result["ok"]:
            return await ctx.send(view=error_layout("Not enough spirit stones", f"That costs **{stones.fmt(result['cost'])}** and you have **{stones.fmt(await coins.balance(ctx.author.id))}**."))
        await ctx.send(view=success_layout(f"{e('epill')} Bought", f"You bought **{amount}x {settings.ITEMS[key]['name']}** for {e('ecoin')} **{stones.fmt(result['cost'])}**."))

    @cultivate.command(name="use", aliases=["eat", "consume"], help="Use a pill. Usage: cultivate use <pill>")
    async def use(self, ctx: commands.Context, *, item: str):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        key = find_item(item)
        if key is None:
            return await ctx.send(view=error_layout("Unknown pill", "Use `cultivate bag` to see what you own."))
        result = await cult.use(ctx.author.id, key)
        if not result["ok"]:
            reasons = {
                "missing": ("You have none", "Buy one with `cultivate buy`."),
                "limit": ("Pill limit reached", f"You can take **{settings.PILL_DAILY_LIMIT}** Qi Gathering Pills a day."),
                "full": ("Qi is full", "You cannot hold more qi. Break through first."),
                "stacked": ("Already at the limit", "Your tribulation bonus is already at +30%."),
                "healthy": ("You are not injured", "You do not need a Healing Pill."),
            }
            title, body = reasons.get(result["reason"], ("Cannot use", "That did not work."))
            return await ctx.send(view=error_layout(title, body))
        character = result["character"]
        name = settings.ITEMS[key]["name"]
        if key == "qi_pill":
            text = f"You take a **{name}** and gain **{coins.fmt(result['gain'])}** qi.\n{coins.fmt(character['qi'])}/{coins.fmt(cult.need(character))} {bar(character['qi'], cult.need(character))}"
        elif key == "tribulation_pill":
            text = f"You take a **{name}**. Your next tribulation has **+{character['chance_bonus']}%** chance."
        else:
            text = f"You take a **{name}** and your injury fades."
        await ctx.send(view=success_layout(f"{e('epill')} Pill taken", text))

    @cultivate.command(name="bag", aliases=["inventory", "inv", "items"], help="See your pills.")
    async def bag(self, ctx: commands.Context):
        e = emoji_manager.get
        await cult.convert_legacy(ctx.author.id)
        items = await cult.inventory(ctx.author.id)
        crafted = await cult.weapons(ctx.author.id)
        if not items and not crafted:
            return await ctx.send(view=info_layout(f"{e('epill')} Your bag", "Empty. Buy pills with `cultivate buy`."))
        lines = []
        for row in crafted[:15]:
            lines.append(f"**#{row['weapon_id']}** {gear.weapon_line(row)}" + (" · listed for sale" if row["listed"] else ""))
        if len(crafted) > 15:
            lines.append(f"-# and {len(crafted) - 15} more weapons")
        for key, qty in items.items():
            if key in settings.ITEMS:
                lines.append(f"**{settings.ITEMS[key]['name']}** x{qty}")
            elif key in settings.BREWS:
                lines.append(f"**{settings.BREWS[key]['name']}** ({settings.BREWS[key]['zh']}) x{qty}")
            elif key in gear.MATERIALS:
                lines.append(f"**{gear.MATERIALS[key]['name']}** ({gear.MATERIALS[key]['zh']}) x{qty}")
            elif gear.parse(key):
                lines.append(f"**{gear.name(key)}** x{qty}" + (" · soul-bound" if gear.soulbound(key) else ""))
        if not lines:
            return await ctx.send(view=info_layout(f"{e('epill')} Your bag", "Empty. Buy pills with `cultivate buy` or win fights with `cultivate fight`."))
        space = await pouch.usage(ctx.author.id)
        lines.append(f"\n-# Herb pouch {space['herb']['used']}/{space['herb']['cap']} · Material pouch {space['material']['used']}/{space['material']['cap']} · `pouch` to upgrade")
        await ctx.send(view=info_layout(f"{e('epill')} Your bag", "\n".join(lines)))

    @cultivate.command(name="fight", aliases=["battle", "monster", "slay"], help="Fight a monster in turn-based combat. Usage: cultivate fight [monster]")
    async def fight(self, ctx: commands.Context, *, monster: Optional[str] = None):
        if await self.need_character(ctx) is None:
            return
        if ctx.author.id in self.active:
            return await ctx.send(view=error_layout("Already fighting", "Finish your current fight first."))
        key = None
        if monster:
            text = monster.lower().strip()
            key = next((k for k, m in bestiary.MONSTERS.items() if text in (k, m["name"].lower(), m["zh"])), None)
        result = await cult.fight_start(ctx.author.id, key)
        if not result["ok"]:
            reasons = {
                "hurt": ("You are injured", f"You recover in **{duration(result.get('wait', 0))}**. A Healing Pill cures it."),
                "limit": ("No fights left", f"You can fight **{settings.FIGHT_DAILY}** times a day."),
            }
            title, body = reasons.get(result["reason"], ("Cannot fight", "That did not work."))
            return await ctx.send(view=error_layout(title, body))
        self.active.add(ctx.author.id)
        await ctx.send(view=fight_layout(result["state"], ctx.author.id, result["left"], self.active), allowed_mentions=NO_PINGS)

    @cultivate.command(name="raid", aliases=["rob", "pvp", "attack"], help="Raid another cultivator for spirit stones. Usage: cultivate raid <user>")
    async def raid(self, ctx: commands.Context, user: Optional[discord.User] = None):
        e = emoji_manager.get
        character = await self.need_character(ctx)
        if character is None:
            return
        now = time.time()
        if user is None:
            guard = "protected" if cult.shielded(character, now) else "open to raids"
            return await ctx.send(view=info_layout(f"{e('esword')} Raids", (
                f"You are **{guard}**.\n\n"
                f"- Cultivators in their first realm or in their first {settings.SHIELD_DAYS} days are protected, and cannot raid.\n"
                f"- You can only raid cultivators within **{settings.PVP_REALM_GAP}** realms of you.\n"
                f"- {settings.PVP_DAILY} raids a day, one per target every {settings.PVP_TARGET_COOLDOWN // 3600} hours. A target can be robbed {settings.PVP_ROBBED_DAILY} times a day.\n"
                f"- A win takes {int(settings.PVP_STEAL_PCT * 100)}% of their pouch, up to {stones.fmt(settings.PVP_STEAL_MAX)}. Spirit stones in the safe, diamonds and the clan bank cannot be taken.\n"
                f"- Loser loses a little qi and a chance to drop one item. Realm and character are never lost.\n"
                f"- Partners, family and clan members cannot raid each other.\n\n"
                "-# Use `cultivate raid <user>`. Keep spirit stones safe with `cultivate safe`.")))
        if user.bot:
            return await ctx.send(view=error_layout("Not a cultivator", "Bots do not cultivate."))
        if ctx.author.id in self.active:
            return await ctx.send(view=error_layout("Already fighting", "Finish your current fight first."))
        result = await cult.pvp_start(ctx.author.id, user.id, user.display_name, now)
        if not result["ok"]:
            reasons = {
                "self": ("Not yourself", "Pick another cultivator."),
                "target_none": ("Not a cultivator", "They have not awakened yet."),
                "hurt": ("You are injured", f"You recover in **{duration(result.get('wait', 0))}**."),
                "shield_self": ("You are protected", "Protected cultivators cannot raid. Reach your second realm and pass your first week."),
                "shield_target": ("They are protected", "New cultivators and those in their first realm cannot be raided."),
                "gap": ("Too far apart", f"You can only raid cultivators within {settings.PVP_REALM_GAP} realms of you."),
                "partner": ("Not your partner", "You cannot raid your partner."),
                "family": ("Not your family", "You cannot raid family."),
                "clan": ("Not your clanmate", "You cannot raid your own clan."),
                "cooldown": ("Too soon", f"You can raid them again in **{duration(result.get('wait', 0))}**."),
                "looted": ("Already looted", "They have been robbed enough today."),
                "poor": ("Not worth it", "They carry too little in their pouch."),
                "limit": ("No raids left", f"You can raid **{settings.PVP_DAILY}** times a day."),
            }
            title, body = reasons.get(result["reason"], ("Cannot raid", "That did not work."))
            return await ctx.send(view=error_layout(title, body))
        self.active.add(ctx.author.id)
        await ctx.send(view=fight_layout(result["state"], ctx.author.id, result["left"], self.active), allowed_mentions=NO_PINGS)

    @cultivate.command(name="safe", aliases=["vault", "stash"], help="Keep spirit stones safe from raids. Usage: cultivate safe [deposit|withdraw] [amount]")
    async def safe(self, ctx: commands.Context, action: Optional[str] = None, amount: Optional[int] = None):
        e = emoji_manager.get
        character = await self.need_character(ctx)
        if character is None:
            return
        if action in ("deposit", "withdraw", "put", "take") and amount:
            result = await cult.safe_move(ctx.author.id, amount, action in ("deposit", "put"))
            if not result["ok"]:
                reasons = {
                    "full": ("Safe is full", f"Your safe holds **{stones.fmt(result.get('safe', 0))}/{stones.fmt(result.get('cap', 0))}**."),
                    "coins": ("Not enough spirit stones", "You do not have that many spirit stones in your pouch."),
                    "safe": ("Not enough in the safe", f"Your safe holds **{stones.fmt(result.get('safe', 0))}**."),
                    "amount": ("Invalid amount", "Use a positive number."),
                }
                title, body = reasons.get(result["reason"], ("Cannot do that", "That did not work."))
                return await ctx.send(view=error_layout(title, body))
            character = result["character"]
            title = "Deposited" if action in ("deposit", "put") else "Withdrawn"
            return await ctx.send(view=success_layout(f"{e('eshield')} {title}", f"Your safe holds **{stones.fmt(character['safe'])}/{stones.fmt(cult.safe_cap(character))}**."))
        pouch = await coins.balance(ctx.author.id)
        await ctx.send(view=info_layout(f"{e('eshield')} Your safe", (
            f"**Safe:** {stones.fmt(character['safe'])}/{stones.fmt(cult.safe_cap(character))} (cannot be raided)\n"
            f"**Pouch:** {stones.fmt(pouch)}\n\n"
            "-# `cultivate safe deposit <amount>` and `cultivate safe withdraw <amount>`. The safe grows with every realm.")))

    @cultivate.command(name="techniques", aliases=["arts", "skills", "tech"], help="Show your combat techniques.")
    async def techniques(self, ctx: commands.Context):
        e = emoji_manager.get
        character = await self.need_character(ctx)
        if character is None:
            return
        mine = arts.known(character, cult.sect_level(character, "scripture"))
        sections = (
            ("Path", {k: v for k, v in arts.TECHNIQUES.items() if v["path"] == character["path"]}),
            ("Way", {k: v for k, v in arts.WAY_TECHNIQUES.items() if v["way"] == character["way"]}),
            ("Race", {k: v for k, v in arts.RACE_TECHNIQUES.items() if v["race"] == character["race"]}),
            ("Sect", arts.SECT_TECHNIQUES),
        )
        lines = []
        for label, table in sections:
            if not table:
                continue
            lines.append(f"### {label}")
            for key, tech in table.items():
                if key in mine:
                    lines.append(f"**{tech['name']}** ({tech['zh']}) · recharge {tech['cd']} turns\n{tech['info']}")
                elif "sect" in tech:
                    lines.append(f"~~{tech['name']}~~ · unlocks at sect scripture level **{tech['sect']}**")
                else:
                    lines.append(f"~~{tech['name']}~~ · unlocks in **{settings.REALMS[tech['realm']]['name']}**")
        lines.append("\n-# Techniques come from your path, your way, your race and your sect. Attack and Defend are always free.")
        await ctx.send(view=info_layout(f"{e('esword')} Techniques", "\n\n".join(lines)))

    @cultivate.command(name="bestiary", aliases=["monsters", "beasts"], help="See the monsters of your realm.")
    async def bestiary_cmd(self, ctx: commands.Context):
        e = emoji_manager.get
        character = await cult.get(ctx.author.id)
        realm = character["realm"] if character and character["path"] else 0
        tier = min(realm, 3)
        lines = [f"**{bestiary.MONSTERS[k]['name']} ({bestiary.MONSTERS[k]['zh']})**\n-# Signature move: {bestiary.MONSTERS[k]['skill']}" for k in bestiary.for_realm(realm)]
        lines.append(f"\n**Loot:** {settings.FIGHT_COINS[tier][0]}-{settings.FIGHT_COINS[tier][1]} spirit stones, some qi, and {gear.MATERIALS[gear.GRADES[tier]['material']]['name']} ({gear.MATERIALS[gear.GRADES[tier]['material']]['zh']}) for crafting.")
        lines.append("-# Use `cultivate fight` to meet one at random, or `cultivate fight <name>`.")
        await ctx.send(view=info_layout(f"{e('esword')} Monsters of the {settings.REALMS[tier]['name']} realm", "\n".join(lines)))

    @cultivate.command(name="gear", aliases=["equipment", "forge"], help="Show, craft, equip, refine or enchant gear. Usage: cultivate gear [craft <slot> [grade]] [equip <name>] [refine <slot>] [enchant <slot> <enchant>]")
    async def gear_cmd(self, ctx: commands.Context, action: Optional[str] = None, *, rest: str = ""):
        e = emoji_manager.get
        character = await self.need_character(ctx)
        if character is None:
            return
        if action == "craft":
            words = rest.lower().split()
            slot = words[0] if words else ""
            grade = min(character["realm"], len(gear.GRADES) - 1)
            if len(words) > 1:
                names = [g["name"].lower() for g in gear.GRADES]
                grade = names.index(words[1]) if words[1] in names else (int(words[1]) - 1 if words[1].isdigit() else -1)
            if slot not in gear.SLOTS:
                return await ctx.send(view=error_layout("Pick a slot", "Use `cultivate gear craft weapon`, `armor` or `charm`, with an optional grade (yellow, mystic, earth, heaven). Soul-bound weapons are made with `cultivate gear forge`."))
            result = await cult.craft(ctx.author.id, slot, grade)
            if not result["ok"]:
                reasons = {
                    "grade": ("Grade not available", "You can only craft grades up to your realm."),
                    "materials": ("Not enough materials", f"You need **{gear.CRAFT_MATERIALS} {gear.MATERIALS[result.get('material', 'beast_core')]['name']}**. Win fights to collect them."),
                    "coins": ("Not enough spirit stones", f"Crafting costs **{stones.fmt(result.get('cost', 0))}**."),
                }
                title, body = reasons.get(result["reason"], ("Cannot craft", "That did not work."))
                return await ctx.send(view=error_layout(title, body))
            return await ctx.send(view=success_layout(f"{e('esword')} Crafted", f"You forged a **{gear.name(result['item'])}** for {stones.fmt(result['cost'])}.\nEquip it with `cultivate gear equip {'#' + result['item'][2:] if result['item'].startswith('w:') else result['item']}`."))
        if action == "forge":
            words = rest.lower().split()
            kind = words[0] if words else ""
            if kind not in gear.WEAPONS:
                lines = [f"**{info['name']}** ({info['zh']}) `{key}`: {info['info']}" for key, info in gear.WEAPONS.items()]
                costs = [f"**{g['name']}:** {gear.FORGE_MATERIALS} {gear.MATERIALS[g['material']]['name']} + {gear.FORGE_SHARDS} Rift Shards + {stones.fmt(gear.forge_cost(i)['coins'])} · {gear.FORGE_CHANCE[i]}% success" for i, g in enumerate(gear.GRADES) if i <= character["realm"]]
                return await ctx.send(view=info_layout(f"{e('esword')} Soul-bound weapons", "Your own weapon. It never breaks and can never be traded or stolen, but forging it is hard and can fail.\n\n" + "\n".join(lines) + "\n\n" + "\n".join(costs) + f"\n\nA failed forge loses the materials and {100 - gear.FORGE_REFUND}% of the spirit stones.\n-# `cultivate gear forge <type> [grade]`"))
            grade = min(character["realm"], len(gear.GRADES) - 1)
            if len(words) > 1:
                names = [g["name"].lower() for g in gear.GRADES]
                grade = names.index(words[1]) if words[1] in names else (int(words[1]) - 1 if words[1].isdigit() else -1)
            result = await cult.forge(ctx.author.id, kind, grade)
            if not result["ok"]:
                reasons = {
                    "grade": ("Grade not available", "You can only forge grades up to your realm."),
                    "materials": ("Not enough materials", f"You need **{gear.FORGE_MATERIALS} {gear.MATERIALS[result.get('material', 'beast_core')]['name']}**."),
                    "shards": ("Not enough Rift Shards", f"You need **{gear.FORGE_SHARDS} Rift Shards** from rifts."),
                    "coins": ("Not enough spirit stones", f"Forging costs **{stones.fmt(result.get('coins', 0))}**."),
                }
                title, body = reasons.get(result["reason"], ("Cannot forge", "That did not work."))
                return await ctx.send(view=error_layout(title, body))
            if result["success"]:
                return await ctx.send(view=success_layout(f"{e('esword')} Forged", f"The metal sings. You forged a soul-bound **{gear.name(result['item'])}**.\nEquip it with `cultivate gear equip {result['item']}`."))
            return await ctx.send(view=error_layout("The forge failed", f"The weapon cracked in the fire. The materials are lost and you got back {stones.fmt(result['refund'])}. Chance was {result['chance']}%."))
        if action == "repair":
            result = await cult.repair(ctx.author.id)
            if not result["ok"]:
                reasons = {
                    "nothing": ("Nothing to repair", "Only a crafted weapon you are holding can wear out. Soul-bound weapons never do."),
                    "full": ("Already sound", "Your weapon is at full durability."),
                    "materials": ("Not enough materials", f"You need **{result.get('materials', 1)} {gear.MATERIALS[result.get('material', 'beast_core')]['name']}**."),
                    "coins": ("Not enough spirit stones", f"Repairs cost **{stones.fmt(result.get('coins', 0))}**."),
                }
                title, body = reasons.get(result["reason"], ("Cannot repair", "That did not work."))
                return await ctx.send(view=error_layout(title, body))
            return await ctx.send(view=success_layout(f"{e('esword')} Repaired", f"Your weapon is restored to **{result['durability']}** durability. Each repair lowers its maximum by {int(gear.REPAIR_LOSS * 100)}%, so it cannot last forever."))
        if action == "refine":
            slot = rest.lower().strip()
            if slot not in gear.SLOTS:
                return await ctx.send(view=error_layout("Pick a slot", "Use `cultivate gear refine weapon`, `armor` or `charm`. Refining upgrades the gear you are wearing, up to +5."))
            result = await cult.refine(ctx.author.id, slot)
            if not result["ok"]:
                reasons = {
                    "empty": ("Nothing equipped", f"Equip a {gear.SLOTS[slot]['name']} first."),
                    "max": ("Fully refined", "That gear is already at +5."),
                    "materials": ("Not enough materials", f"You need **{result.get('materials', 1)} {gear.MATERIALS[result.get('material', 'beast_core')]['name']}**."),
                    "coins": ("Not enough spirit stones", f"Refining costs **{stones.fmt(result.get('coins', 0))}**."),
                }
                title, body = reasons.get(result["reason"], ("Cannot refine", "That did not work."))
                return await ctx.send(view=error_layout(title, body))
            name = gear.name(result["item"])
            if result["success"]:
                return await ctx.send(view=success_layout(f"{e('esword')} Refined", f"Your **{name}** glows and is now **+{result['plus']}**."))
            return await ctx.send(view=error_layout("The refining failed", f"The spirit energy scattered. Your **{name}** stays at **+{result['plus']}** and the materials are gone. Chance was {result['chance']}%."))
        if action == "enchant":
            words = rest.lower().split()
            if len(words) < 2 or words[0] not in gear.SLOTS or gear.find_enchant(" ".join(words[1:])) is None:
                options = ", ".join(f"**{info['name']}** ({'/'.join(info['slots'])}, {info['info']})" for info in gear.ENCHANTS.values())
                return await ctx.send(view=info_layout(f"{e('eshield')} Enchanting", f"Usage: `cultivate gear enchant <slot> <enchant>`.\n\n{options}\n\nEach enchant costs **{gear.ENCHANT_SHARDS} Rift Shards** and spirit stones that grow with your realm. Rift Shards come from rifts. A slot holds one enchant, and a new one replaces the old. Swapping the gear itself removes its enchant."))
            slot = words[0]
            key = gear.find_enchant(" ".join(words[1:]))
            result = await cult.enchant(ctx.author.id, slot, key)
            if not result["ok"]:
                reasons = {
                    "slot": ("Wrong slot", f"{gear.ENCHANTS[key]['name']} fits {'/'.join(gear.ENCHANTS[key]['slots'])}."),
                    "empty": ("Nothing equipped", f"Equip a {gear.SLOTS[slot]['name']} first."),
                    "same": ("Already enchanted", "That enchant is already on this gear."),
                    "materials": ("Not enough Rift Shards", f"You need **{result.get('need', gear.ENCHANT_SHARDS)} Rift Shards**."),
                    "coins": ("Not enough spirit stones", f"Enchanting costs **{stones.fmt(result.get('cost', 0))}**."),
                }
                title, body = reasons.get(result["reason"], ("Cannot enchant", "That did not work."))
                return await ctx.send(view=error_layout(title, body))
            info = gear.ENCHANTS[key]
            return await ctx.send(view=success_layout(f"{e('esword')} Enchanted", f"Your **{gear.SLOTS[slot]['name']}** now carries **{info['name']}** ({info['zh']}): {info['info']}."))
        if action == "equip":
            digits = rest.strip().lstrip("#").lower().removeprefix("w:")
            item = f"w:{digits}" if digits.isdigit() else gear.find(rest)
            if item is None:
                return await ctx.send(view=error_layout("Unknown gear", "Try `cultivate gear equip #12` for a crafted weapon from your bag, or a name such as `yellow armor` or `earth dragon spear`."))
            result = await cult.equip(ctx.author.id, item)
            if not result["ok"]:
                reasons = {
                    "missing": ("You do not own it", "Craft it with `cultivate gear craft`."),
                    "realm": ("Realm too low", "You must reach a higher realm to use that grade."),
                }
                title, body = reasons.get(result["reason"], ("Cannot equip", "That did not work."))
                return await ctx.send(view=error_layout(title, body))
            note = f"\nYour old gear lost its **+{result['lost_plus']}** refinement." if result.get("lost_plus") else ""
            if result.get("lost_enchant"):
                note += f"\nIt also lost its **{gear.ENCHANTS[result['lost_enchant']]['name']}** enchant."
            return await ctx.send(view=success_layout(f"{e('eshield')} Equipped", f"You equip the **{gear.name(result['item'])}**.{note}"))
        mods = cult.fight_mods(character)
        lines = []
        for slot, info in gear.SLOTS.items():
            item = character.get(slot)
            plus = int(character.get(f"{slot}_r") or 0)
            charm = gear.ENCHANTS.get(character.get(f"{slot}_e") or "")
            shown = gear.weapon_line(character["_weapon"]) if slot == "weapon" and character.get("_weapon") else (gear.name(item) if item else "")
            lines.append(f"**{info['name']}:** {shown + (f' +{plus}' if plus else '') if item else 'nothing'}" + (f" · {charm['name']}" if charm and item else "") + f"\n-# boosts {info['info']}")
        lines.append("")
        for grade, info in enumerate(gear.GRADES):
            if grade > character["realm"]:
                break
            lines.append(f"**{info['name']} grade ({info['zh']}):** {gear.CRAFT_MATERIALS} {gear.MATERIALS[info['material']]['name']} + {stones.fmt(info['coins'])}")
        lines.append("\n**Crafted weapons** are common and tradable. They come in five qualities (" + ", ".join(q["name"] for q in gear.WEAPON_QUALITIES) + ") that change attack and durability, and they break at zero durability. `cultivate gear repair` mends one.")
        lines.append("**Soul-bound weapons** (" + ", ".join(info["name"] for info in gear.WEAPONS.values()) + ") never break and cannot be traded, but are hard to forge: `cultivate gear forge`.")
        stats = combat.player_stats(character, mods)
        lines.append(f"\n**Combat stats:** x{mods['hp']:.2f} health · x{mods['atk']:.2f} attack · x{mods['def']:.2f} defense · {stats['dodge']:.0f}% dodge · {stats['crit']:.0f}% critical · x{stats['tech']:.2f} technique power")
        lines.append(f"**Refining:** `cultivate gear refine <slot>` upgrades what you wear up to +{gear.REFINE_MAX}. Each step adds {int(gear.REFINE_STEP * 100)}% to that gear's bonus. It costs materials and spirit stones, can fail, and resets if you swap the gear.")
        lines.append("**Enchanting:** `cultivate gear enchant <slot> <enchant>` adds a rune from Rift Shards. Run it without a slot to see them all.")
        lines.append("-# `cultivate gear craft <slot> [grade]`, `equip <name or #id>`, `repair` and `forge`. Story relics are equipped by their name and are soul-bound.")
        await ctx.send(view=info_layout(f"{e('eshield')} Gear", "\n".join(lines)))

    @cultivate.command(name="realms", aliases=["ladder"], help="Show the realms of cultivation.")
    async def realms(self, ctx: commands.Context):
        e = emoji_manager.get
        mine = await cult.get(ctx.author.id)
        lines = []
        for index, info in enumerate(settings.REALMS):
            here = " **(you)**" if mine and mine["path"] and mine["realm"] == index else ""
            fee = f" · tribulation fee {stones.fmt(info['fee'])}" if info["fee"] else ""
            lines.append(f"**{index + 1}. {info['name']}**{here}\n{len(info['stages'])} stages · {info['gain']} qi an hour{fee}")
        lines.append("\nComing later: " + ", ".join(settings.FUTURE_REALMS) + ".")
        await ctx.send(view=info_layout(f"{e('ecult')} Realms", "\n".join(lines)))

    @cultivate.command(name="roots", help="Explain spiritual roots.")
    async def roots(self, ctx: commands.Context):
        e = emoji_manager.get
        lines = [f"**{rarity.title()}** ({info['weight']}%): {', '.join(info['names'])} · x{info['mult']}" for rarity, info in settings.ROOTS.items()]
        lines.append("\n" + "\n".join(f"**{q['name']}** quality ({q['weight']}%): x{q['mult']}" for q in settings.QUALITIES))
        lines.append("\n-# Your root is rolled once when you awaken. Rarity times quality sets your qi speed.")
        await ctx.send(view=info_layout(f"{e('eroot')} Spiritual roots", "\n".join(lines)))

    @cultivate.command(name="races", aliases=["race", "peoples"], help="Show the races and what each is good at.")
    async def races_cmd(self, ctx: commands.Context):
        e = emoji_manager.get
        lines = []
        for key, race in races.RACES.items():
            lines.append(f"**{race['name']} ({race['zh']})** · {race['weight']}%\n{race['about']}\n{race['perk']}\n-# {race['flaw']}")
        lines.append("\n-# Your race is rolled together with your spiritual root when you awaken, and rerolled with it.")
        await ctx.send(view=info_layout(f"{e('eroot')} Races of Canhuang", "\n\n".join(lines)))

    @cultivate.command(name="ways", aliases=["types", "cultivators"], help="Show the kinds of cultivators you can be.")
    async def ways_cmd(self, ctx: commands.Context):
        e = emoji_manager.get
        lines = [f"**{way['name']} ({way['zh']})**\n{way['about']}\n{way['perk']}\n-# {way['flaw']}" for way in ways.WAYS.values()]
        lines.append("\n-# You choose your way once, with `cultivate way <name>` or when you awaken. It stacks with your race and path.")
        await ctx.send(view=info_layout(f"{e('ecult')} Ways of cultivation", "\n\n".join(lines)))

    @cultivate.command(name="way", help="Choose your way once. Usage: cultivate way [immortal|demonic|ghost|buddhist|gu|rogue]")
    async def way(self, ctx: commands.Context, *, name: Optional[str] = None):
        e = emoji_manager.get
        character = await self.need_character(ctx)
        if character is None:
            return
        if not name:
            return await ctx.send(view=info_layout(f"{e('ecult')} Your way", way_status(character) + "\n\n-# See every way with `cultivate ways`."))
        text = name.lower().strip()
        key = next((k for k, w in ways.WAYS.items() if text in (k, w["name"].lower(), w["zh"], w["name"].lower().replace(" cultivator", ""))), None)
        if key is None:
            return await ctx.send(view=error_layout("Unknown way", "Use `cultivate ways` to see the options."))
        updated = await cult.choose_way(ctx.author.id, key)
        if updated is None:
            return await ctx.send(view=error_layout("Way already chosen", "Your way cannot be changed."))
        await ctx.send(view=success_layout(f"{e('ecult')} {ways.WAYS[key]['name']}", f"{ways.WAYS[key]['perk']}\n-# {ways.WAYS[key]['flaw']}"))

    @cultivate.command(name="paths", help="Explain the cultivation paths.")
    async def paths(self, ctx: commands.Context):
        e = emoji_manager.get
        lines = [f"**{info['name']}** ({info['origin']}): {info['perk']}" for info in settings.PATHS.values()]
        lines.append("\n-# You choose your path when you awaken. More comes with combat.")
        await ctx.send(view=info_layout(f"{e('ecult')} Paths", "\n".join(lines)))

    @cultivate.command(name="lore", aliases=["story", "plot"], help="Read about the world. Usage: cultivate lore [world|abyss|clans|rifts]")
    async def lore_cmd(self, ctx: commands.Context, topic: str = "world"):
        e = emoji_manager.get
        pages = {
            "world": ("The Shattering of Honghuang", story.WORLD),
            "abyss": ("The Abyssal Beasts", story.ABYSS),
            "clans": ("The Great Families", story.CLANS),
            "rifts": ("Rifts and Lower Worlds", story.RIFTS),
        }
        title, text = pages.get(topic.lower(), pages["world"])
        others = ", ".join(f"`{key}`" for key in pages if pages[key][0] != title)
        await ctx.send(view=info_layout(f"{e('ecult')} {title}", text + f"\n\n-# Also: {others}. For a guide to your own journey, use `world guide`."))

    @cultivate.command(name="npcs", aliases=["people", "characters"], help="See the people of the world you can talk to.")
    async def npcs(self, ctx: commands.Context):
        e = emoji_manager.get
        character = await cult.get(ctx.author.id)
        character = character if character and character["path"] else {"realm": 0}
        lines = []
        for key, npc in people.NPCS.items():
            if cult.npc_unlocked(key, character):
                lines.append(f"**{npc['name']}** · {npc['title']} · {npc['place']}\n{npc['about']}")
            else:
                lines.append(f"**???** · appears when you reach {settings.REALMS[npc['realm']]['name']}")
        lines.append("\n-# Talk with `cultivate talk <name>`. These are the people of the Qingxu Refuge. Travelers you meet in the wilds are yours alone: see `world people`.")
        await ctx.send(view=info_layout(f"{e('ecult')} People", "\n".join(lines)))

    @cultivate.command(name="talk", aliases=["speak", "chat"], help="Talk to someone. Usage: cultivate talk <name>")
    async def talk(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        key = cult.find_npc(name)
        if key is None:
            return await ctx.send(view=error_layout("Nobody by that name", "Use `cultivate npcs` to see who is around."))
        result = await cult.talk(ctx.author.id, key)
        if not result["ok"]:
            return await ctx.send(view=error_layout("You have not met them", "They have not appeared to you yet. Keep climbing."))
        npc = result["npc"]
        body = f"*{npc['title']} · {npc['place']}*\n\n\"{result['line']}\""
        favor = result["favor"]
        if favor:
            extra = parts_text({k: v for k, v in favor.items() if k != "text"}, e)
            body += f"\n\n{favor['text']}" + (f"\n{extra}" if extra else "")
        else:
            body += "\n\n-# Their favor for today is already given."
        await ctx.send(view=info_layout(f"{e('ecult')} {npc['name']}", body))

    @cultivate.command(name="event", aliases=["quest", "wander", "adventure"], help="Wander the world and meet a situation to decide on.")
    async def event(self, ctx: commands.Context):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        result = await cult.start_event(ctx.author.id)
        if not result["ok"]:
            return await ctx.send(view=error_layout("You have wandered enough", f"You can face **{settings.EVENT_DAILY}** events a day. Come back tomorrow."))
        await ctx.send(view=EventView(ctx.author.id, result["event"], result["left"]))

    @cultivate.command(name="top", aliases=["leaderboard", "lb"], help="Show the highest cultivators.")
    async def top(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await cult.top(10)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('ecult')} Top cultivators", "Nobody has awakened yet."))
        lines = [f"**{i}.** <@{row['user_id']}> · {cult.stage_name(row)}" for i, row in enumerate(rows, 1)]
        await ctx.send(view=info_layout(f"{e('ecult')} Top cultivators", "\n".join(lines)), allowed_mentions=NO_PINGS)


async def setup(bot: commands.Bot):
    await bot.add_cog(Cultivation(bot))
