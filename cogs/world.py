import asyncio
import random
import time
from typing import Awaitable, Callable, Optional

import discord
from discord.ext import commands

from cogs.cultivation import NO_PINGS, bar, fight_layout, item_name
from cogs.economy import duration
from rpg import bestiary, chapters, engine as cult, gear, quest, rifts, settings, titles, wanderers, wild
from utils import coins, db, emoji_manager
from utils.colors import NEUTRAL
from utils.components import error_layout, footer_block, info_layout, success_layout

Choice = tuple[str, discord.ButtonStyle, Callable[[discord.Interaction], Awaitable[None]]]


class ChoiceRow(discord.ui.ActionRow):
    def __init__(self, view: "ChoiceView", choices: list):
        super().__init__(*[discord.ui.Button(label=label, style=style) for label, style, _ in choices])
        self.owner = view
        for button, (_, _, callback) in zip(self.children, choices):
            button.callback = self.make(callback)

    def make(self, callback):
        async def run(interaction: discord.Interaction):
            if self.owner.owner and interaction.user.id != self.owner.owner:
                return await interaction.response.send_message("This is not your journey.", ephemeral=True)
            if self.owner.stop_on_click:
                self.owner.stop()
            await callback(interaction)
        return run


class ChoiceView(discord.ui.LayoutView):
    def __init__(self, owner: Optional[int], title: str, body: str, choices: list, color: int = NEUTRAL, timeout: float = 240, on_timeout=None, stop_on_click: bool = True):
        super().__init__(timeout=timeout)
        self.owner = owner
        self.stop_on_click = stop_on_click
        self.timeout_callback = on_timeout
        container = discord.ui.Container(accent_color=color)
        container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
        if choices:
            container.add_item(discord.ui.Separator())
            container.add_item(ChoiceRow(self, choices))
        for item in footer_block():
            container.add_item(item)
        self.add_item(container)

    async def on_timeout(self) -> None:
        if self.timeout_callback:
            await self.timeout_callback()


def loot_text(parts: dict) -> list[str]:
    e = emoji_manager.get
    lines = []
    if parts.get("coins"):
        lines.append(f"+**{coins.fmt(parts['coins'])}** coins")
    if parts.get("qi"):
        lines.append(f"+**{coins.fmt(parts['qi'])}** qi")
    if parts.get("material"):
        key, count = parts["material"]
        lines.append(f"+{count} **{gear.MATERIALS[key]['name']}** ({gear.MATERIALS[key]['zh']})")
    if parts.get("gear"):
        lines.append(f"{e('esword')} It dropped a **{gear.name(parts['gear'])}**!")
    if parts.get("shard"):
        lines.append("+1 **Rift Shard** (裂隙碎片)")
    return lines


def wild_result(state: dict, outcome: dict):
    e = emoji_manager.get
    m = state["m"]
    parts = outcome["parts"]
    if outcome["result"] == "win":
        return success_layout(f"{e('esword')} {m['name']} falls", "\n".join([f"The resentment fades from **{m['name']}** and it crumbles to dust."] + loot_text(parts)))
    if outcome["result"] == "lose":
        lost = f"\nYou lose **{coins.fmt(parts.get('qi_lost', 0))}** qi." if parts.get("qi_lost") else ""
        return error_layout("You are driven off", f"**{m['name']}** is too strong this time.{lost}")
    return info_layout(f"{e('esword')} You slip away", f"You escape from **{m['name']}**.")


def standing(affinity: int) -> str:
    return f"{wild.friendship(affinity)} · {bar(affinity, 100, 8)} {affinity}/100"


def npc_card(npc: dict) -> str:
    kind = wanderers.KINDS[npc["kind"]]
    return f"**{npc['name']}** ({npc['zh']}) · {kind['title']} ({kind['zh']})\n-# {npc['tale']}"


def reward_text(rewards: dict) -> list[str]:
    lines = []
    if "friend" in rewards:
        lines.append(f"They now call you a friend and press **{coins.fmt(rewards['friend']['coins'])}** coins and a Qi Pill into your hands.")
    if "confidant" in rewards:
        lines.append(f"They trust you enough to share a secret: *{rewards['confidant']['secret']}*\n+{coins.fmt(rewards['confidant']['qi'])} qi")
    if "companion" in rewards:
        if rewards["companion"].get("bond"):
            lines.append("They become your **Dao companion**. Your qi grows 1% faster from now on.")
        else:
            lines.append(f"They become your Dao companion and gift you **{coins.fmt(rewards['companion']['coins'])}** coins.")
    return lines


class World(commands.Cog):
    category = "Cultivation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.spawn_channels: set[int] = set()
        self.channel_state: dict = {}
        self.runs: dict[int, float] = {}
        self.lock = asyncio.Lock()

    async def cog_load(self) -> None:
        try:
            rows = await db.raw_fetch("SELECT channel_id FROM cult_spawn_channels")
            self.spawn_channels = {int(row["channel_id"]) for row in rows}
        except Exception:
            self.spawn_channels = set()

    def in_run(self, user_id: int) -> bool:
        return self.runs.get(user_id, 0) > time.time()

    def active(self) -> set:
        cog = self.bot.get_cog("Cultivation")
        return cog.active if cog else set()

    async def need_character(self, ctx: commands.Context) -> Optional[dict]:
        character = await cult.get(ctx.author.id)
        if character is None or not character["path"]:
            await ctx.send(view=error_layout("Not awakened", "You have not awakened yet. Use `cultivate awaken` to begin."))
            return None
        return character

    @commands.group(name="world", aliases=["wild", "wander"], invoke_without_command=True, help="Explore the wilds, meet travelers and enter rifts.")
    async def world(self, ctx: commands.Context):
        await self.guide(ctx)

    @world.command(name="guide", aliases=["help", "start"], help="Your personal guide and what to do next.")
    async def guide(self, ctx: commands.Context):
        e = emoji_manager.get
        character = await cult.get(ctx.author.id)
        if character is None or not character["path"]:
            return await ctx.send(view=info_layout(f"{e('ecult')} Your journey", "You have not awakened yet. Use `cultivate awaken` to feel your spiritual root and pick your way and path. Your guide will find you after that."))
        found = await wild.people(ctx.author.id)
        guide = next((npc for npc in found if npc["kind"] == "guide"), None)
        if guide is None:
            guide = await wild.meet(ctx.author.id, kind="guide")
        steps = await wild.guide_steps(ctx.author.id, character)
        done = sum(1 for ok, _, _ in steps if ok)
        lines = [f"{'[x]' if ok else '[ ]'} {label}\n-# {hint}" for ok, label, hint in steps]
        header = f"{npc_card(guide)}\n\n*\"{wanderers.line('guide')}\"*\n\n" if guide else ""
        await ctx.send(view=info_layout(f"{e('ecult')} Your journey ({done}/{len(steps)})", header + "\n".join(lines) + "\n\n-# Talk to your guide with `world talk`. Meet more people with `world explore`.\nFollow the main story with `world chapter`."))

    @world.command(name="bounty", aliases=["bounties", "quests", "daily"], help="Today's bounties. Finish them to claim coins, qi and a bonus chest.")
    async def bounty(self, ctx: commands.Context):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        claimed = await cult.claim_bounties(ctx.author.id)
        board = claimed["board"] if claimed.get("board") else await cult.bounties(ctx.author.id)
        lines = []
        for item in board["items"]:
            mark = "[x]" if item["claimed"] else "[ ]"
            lines.append(f"{mark} {item['text']} ({item['done']}/{item['goal']})")
        rewards = board["rewards"]
        lines.append(f"\n**Each bounty:** {coins.fmt(rewards['coins'])} coins and some qi.")
        lines.append(f"**All three:** a chest with {coins.fmt(rewards['bonus_coins'])} coins and {rewards['material_qty']} {gear.MATERIALS[rewards['material']]['name']}.")
        if claimed["ok"]:
            bits = [f"{coins.fmt(claimed['coins'])} coins", f"{claimed['qi']} qi"]
            if claimed["chest"]:
                bits.append(f"the chest ({coins.fmt(rewards['bonus_coins'])} coins and {rewards['material_qty']} {gear.MATERIALS[rewards['material']]['name']})")
            lines.append(f"\n**Claimed:** " + ", ".join(bits) + ".")
            return await ctx.send(view=success_layout(f"{e('ecult')} Bounties", "\n".join(lines)))
        lines.append("\n-# Bounties reset every day. Finish them, then use `world bounty` again to claim.")
        await ctx.send(view=info_layout(f"{e('ecult')} Bounties", "\n".join(lines)))

    def reward_lines(self, given: dict) -> list:
        lines = []
        if given.get("coins"):
            lines.append(f"+**{coins.fmt(given['coins'])}** coins")
        for key, qty in (given.get("items") or {}).items():
            lines.append(f"+{qty} **{item_name(key)}**")
        return lines

    async def chapter_view(self, user_id: int):
        e = emoji_manager.get
        character = await cult.get(user_id)
        info = await quest.status(user_id, character)
        if info["finished"]:
            ending = info["row"]["flags"].get("ending")
            label = next((option[1] for option in chapters.CHAPTERS[-1]["choice"]["options"] if option[0] == ending), "your own road")
            return ChoiceView(user_id, f"{e('ecult')} The first story is done", f"You have walked every chapter of the Qingxu saga. When the Gate waited for an answer, you chose: **{label}**.\n\nSoul Transformation and the worlds beyond are still ahead.\n\n-# Use `world chapter log` to look back at your choices.", [])
        chapter = info["chapter"]
        act = chapters.ACTS[chapter["act"]]
        lines = [f"-# {act[0]}: {act[1]} ({act[2]}) · Chapter {info['index'] + 1} of {chapters.TOTAL}", f"**{chapter['npc']}**", chapter["scene"]]
        lines += [f"*{text}*" for text in info["echoes"]]
        lines.append("")
        for label, have, need in info["goals"]:
            lines.append(f"{'[x]' if have >= need else '[ ]'} {label}" + (f" ({have}/{need})" if need > 1 else ""))
        if chapter["boss"]:
            lines.append(f"{'[x]' if info['boss_done'] else '[ ]'} Defeat **{bestiary.BOSSES[chapter['boss']]['name']}**")
        stage = info["stage"]
        buttons = []
        if stage == "locked":
            lines.append(f"\n-# Reach **{settings.REALMS[chapter['realm']]['name']}** to continue this chapter.")
        elif stage == "goals":
            lines.append("\n-# Do these anywhere in the game, then come back with `world chapter`.")
        elif stage == "boss":
            lines.append("\nThe way forward is blocked. You can only fight this when you are ready.")
            buttons.append((f"Face {bestiary.BOSSES[chapter['boss']]['name']}", discord.ButtonStyle.danger, self.story_boss(user_id, chapter["boss"])))
        elif stage == "choice":
            lines.append(f"\n**{chapter['choice']['prompt']}**")
            for index, option in enumerate(chapter["choice"]["options"]):
                buttons.append((option[1], discord.ButtonStyle.primary if index == 0 else discord.ButtonStyle.secondary, self.story_choice(user_id, option[0])))
        else:
            if chapter["choice"]:
                picked = next(option[1] for option in chapter["choice"]["options"] if option[0] == info["choice"])
                lines.append(f"\n-# You chose: {picked}")
            lines.append("\nThe chapter is ready to close.")
            buttons.append(("Complete chapter", discord.ButtonStyle.success, self.story_complete(user_id)))
        return ChoiceView(user_id, f"{e('ecult')} {chapter['title']} ({chapter['zh']})", "\n".join(lines), buttons)

    def story_refresh(self, user_id: int):
        async def callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=await self.chapter_view(user_id))
        return callback

    def story_choice(self, user_id: int, option: str):
        async def callback(interaction: discord.Interaction):
            result = await quest.choose(user_id, option)
            if result is None:
                return await interaction.response.edit_message(view=await self.chapter_view(user_id))
            body = result["text"] + "".join("\n" + line for line in self.reward_lines(result["given"]))
            await interaction.response.edit_message(view=ChoiceView(user_id, f"{emoji_manager.get('ecult')} {result['label']}", body, [("Continue", discord.ButtonStyle.primary, self.story_refresh(user_id))]))
        return callback

    def story_boss(self, user_id: int, key: str):
        async def callback(interaction: discord.Interaction):
            character = await cult.get(user_id)
            if user_id in self.active():
                return await interaction.response.edit_message(view=error_layout("Already fighting", "Finish your current fight first, then use `world chapter`."))
            wait = cult.hurt(character, time.time())
            if wait:
                return await interaction.response.edit_message(view=error_layout("You are injured", f"You recover in **{duration(wait)}**. A Healing Pill cures it. Then use `world chapter`."))
            state = quest.boss_state(character, cult.fight_mods(character), key)
            state["log"] = [f"**{state['m']['name']}** bars the way."]
            state["on_done"] = self.story_boss_done(user_id)
            self.active().add(user_id)
            await interaction.response.edit_message(view=fight_layout(state, user_id, 0, self.active()), allowed_mentions=NO_PINGS)
        return callback

    def story_boss_done(self, user_id: int):
        async def callback(interaction: discord.Interaction, state: dict):
            e = emoji_manager.get
            outcome = await quest.boss_finish(user_id, state)
            if outcome["result"] == "win":
                return await interaction.response.edit_message(view=ChoiceView(user_id, f"{e('esword')} Victory", f"**{state['m']['name']}** falls. The way forward is open.", [("Continue the story", discord.ButtonStyle.primary, self.story_refresh(user_id))]))
            await interaction.response.edit_message(view=info_layout(f"{e('esword')} Not yet", "You were beaten back. Heal, level up or change your gear, then try again with `world chapter`."))
        return callback

    def story_complete(self, user_id: int):
        async def callback(interaction: discord.Interaction):
            e = emoji_manager.get
            character = await cult.get(user_id)
            result = await quest.complete(user_id, character)
            if result is None:
                return await interaction.response.edit_message(view=await self.chapter_view(user_id))
            chapter = result["chapter"]
            lines = [chapter["outro"], "", "**Rewards**"] + self.reward_lines(result["given"])
            for key in await cult.check_titles(user_id):
                lines.append(f"{e('ecult')} Title earned: **{titles.TITLES[key]['name']}** ({titles.TITLES[key]['zh']})")
            following = result["next"]
            if following:
                lines.append(f"\n-# Next: **{following['title']}** ({following['zh']})" + (f", needs {settings.REALMS[following['realm']]['name']}" if following["realm"] > character["realm"] else ""))
            buttons = [("Next chapter", discord.ButtonStyle.primary, self.story_refresh(user_id))] if following else []
            await interaction.response.edit_message(view=ChoiceView(user_id, f"{e('ecult')} {chapter['title']} complete", "\n".join(lines), buttons))
        return callback

    @world.command(name="chapter", aliases=["story", "saga", "main", "plot"], help="Follow the main story. Usage: world chapter [log]")
    async def chapter_cmd(self, ctx: commands.Context, action: Optional[str] = None):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        if action and action.lower() in ("log", "journal", "past", "recap"):
            rows = await quest.journal(ctx.author.id)
            if not rows:
                return await ctx.send(view=info_layout(f"{e('ecult')} Story log", "You have not finished a chapter yet. Start with `world chapter`."))
            lines = []
            for number, (chapter, label) in enumerate(rows, 1):
                lines.append(f"**{number}. {chapter['title']}** ({chapter['zh']})" + (f"\n-# You chose: {label}" if label else ""))
            return await ctx.send(view=info_layout(f"{e('ecult')} Story log", "\n".join(lines)))
        await ctx.send(view=await self.chapter_view(ctx.author.id), allowed_mentions=NO_PINGS)

    @world.command(name="brew", aliases=["alchemy", "pills"], help="Brew battle pills, or drink one. Usage: world brew [pill] | world brew drink <pill>")
    async def brew(self, ctx: commands.Context, *, rest: str = ""):
        e = emoji_manager.get
        character = await self.need_character(ctx)
        if character is None:
            return
        words = rest.strip()
        drinking = words.lower().startswith(("drink ", "use ", "eat "))
        if drinking:
            words = words.split(" ", 1)[1]
        if words:
            key = cult.find_brew(words)
            if key is None:
                return await ctx.send(view=error_layout("Unknown pill", "Run `world brew` to see the recipes."))
            if drinking:
                result = await cult.drink(ctx.author.id, key)
                if not result["ok"]:
                    reasons = {"missing": ("You do not have one", "Brew it with `world brew`."), "active": ("Already active", "That pill is still working until midnight UTC.")}
                    title, body = reasons.get(result["reason"], ("Cannot drink", "That did not work."))
                    return await ctx.send(view=error_layout(title, body))
                info = settings.BREWS[key]
                return await ctx.send(view=success_layout(f"{e('epill')} Pill taken", f"You swallow a **{info['name']}** ({info['zh']}). {info['info']}."))
            result = await cult.brew(ctx.author.id, key)
            if not result["ok"]:
                reasons = {
                    "materials": ("Not enough materials", f"You need **{result.get('need', settings.BREW_MATERIALS)} {gear.MATERIALS[result.get('material', 'beast_core')]['name']}**. Win fights to collect them."),
                    "coins": ("Not enough coins", f"Brewing costs **{coins.fmt(result.get('cost', 0))}** coins."),
                }
                title, body = reasons.get(result["reason"], ("Cannot brew", "That did not work."))
                return await ctx.send(view=error_layout(title, body))
            info = settings.BREWS[key]
            return await ctx.send(view=success_layout(f"{e('epill')} Brewed", f"You brewed **{result['qty']} {info['name']}** ({info['zh']}) for {coins.fmt(result['cost'])} coins.\nDrink it with `world brew drink {key.replace('_pill', '')}`."))
        grade = gear.GRADES[min(character["realm"], len(gear.GRADES) - 1)]
        lines = []
        for key, info in settings.BREWS.items():
            lines.append(f"**{info['name']}** ({info['zh']})\n-# {info['info']}")
        active = [settings.BREWS[k]["name"] for k in sorted(character.get("_buffs") or ())]
        cost = int(settings.BREW_COINS * (1 + character["realm"]))
        lines.append(f"\n**Recipe:** {settings.BREW_MATERIALS} {gear.MATERIALS[grade['material']]['name']} + about {coins.fmt(cost)} coins for one pill. Alchemy cultivators brew two at a time and pay less.")
        if active:
            lines.append(f"**Working now:** {', '.join(active)}")
        lines.append("-# `world brew <pill>` to brew, `world brew drink <pill>` to drink. Pills last until midnight UTC.")
        await ctx.send(view=info_layout(f"{e('epill')} Alchemy", "\n".join(lines)))

    @world.command(name="titles", aliases=["title", "achievements"], help="Your titles. Usage: world titles [set <name>|clear]")
    async def titles_cmd(self, ctx: commands.Context, *, rest: str = ""):
        e = emoji_manager.get
        character = await self.need_character(ctx)
        if character is None:
            return
        fresh = await cult.check_titles(ctx.author.id)
        words = rest.strip()
        if words.lower() == "clear":
            await cult.set_title(ctx.author.id, "")
            return await ctx.send(view=success_layout(f"{e('ecult')} Title cleared", "You walk without a title."))
        if words.lower().startswith(("set ", "equip ", "use ")):
            key = titles.find(words.split(" ", 1)[1])
            if key is None:
                return await ctx.send(view=error_layout("Unknown title", "Run `world titles` to see them."))
            result = await cult.set_title(ctx.author.id, key)
            if not result["ok"]:
                return await ctx.send(view=error_layout("Not earned yet", f"{titles.TITLES[key]['about']}"))
            info = titles.TITLES[key]
            return await ctx.send(view=success_layout(f"{e('ecult')} Title set", f"You are now known as **{info['name']}** ({info['zh']})."))
        earned = await cult.title_rows(ctx.author.id)
        lines = []
        for key, info in titles.TITLES.items():
            mark = "[x]" if key in earned else "[ ]"
            tag = " (new)" if key in fresh else ""
            current = " · wearing" if character.get("title") == key else ""
            lines.append(f"{mark} **{info['name']}** ({info['zh']}){tag}{current}\n-# {info['about']}")
        await ctx.send(view=info_layout(f"{e('ecult')} Titles ({len(earned)}/{len(titles.TITLES)})", "\n".join(lines) + "\n\n-# Wear one with `world titles set <name>`. It shows on your `cultivate status`."))

    @world.command(name="raids", aliases=["raidlog", "history"], help="Your recent raids and who raided you.")
    async def raids(self, ctx: commands.Context):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        rows = await cult.raid_log(ctx.author.id, 10)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('esword')} Raid log", "Nothing yet. Raids from the last two weeks show up here."))
        lines = []
        for row in rows:
            mine = row["attacker_id"] == ctx.author.id
            other_id = row["target_id"] if mine else row["attacker_id"]
            user = self.bot.get_user(other_id)
            name = user.display_name if user else f"someone ({other_id})"
            won = row["result"] == "win"
            when = f"<t:{int(row['at'])}:R>"
            money = abs(row["coins"])
            item = gear.name(row["item"]) if gear.parse(row["item"] or "") else (gear.MATERIALS[row["item"]]["name"] if row["item"] in gear.MATERIALS else "")
            if mine:
                text = f"You raided **{name}** and {'won' if won else 'lost'}"
                text += f", taking {coins.fmt(money)} coins" if won and money else (f", losing {coins.fmt(money)} coins" if money else "")
                if item:
                    text += f" ({'got' if won else 'dropped'} {item})"
            else:
                text = f"**{name}** raided you and {'won' if won else 'lost'}"
                text += f", taking {coins.fmt(money)} coins" if won and money else (f", losing {coins.fmt(money)} coins" if money else "")
                if item:
                    text += f" ({'dropped' if not won else 'took'} {item})"
            lines.append(f"{text} {when}")
        await ctx.send(view=info_layout(f"{e('esword')} Raid log", "\n".join(lines) + "\n\n-# Keep coins safe with `cultivate safe`."), allowed_mentions=NO_PINGS)

    @world.command(name="people", aliases=["npcs", "companions", "journey"], help="The travelers and friends you have met.")
    async def people(self, ctx: commands.Context):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        found = await wild.people(ctx.author.id)
        if not found:
            return await ctx.send(view=info_layout(f"{e('ecult')} People you have met", "Nobody yet. Use `world guide`, then `world explore` to find travelers."))
        lines = [f"{npc_card(npc)}\n{standing(npc['affinity'])}" for npc in found]
        lines.append(f"\n-# {len(found)}/{settings.NPC_LIMIT} met. Talk with `world talk <name>`. Dao companions boost your qi.")
        await ctx.send(view=info_layout(f"{e('ecult')} People you have met", "\n\n".join(lines)))

    async def pick_person(self, ctx: commands.Context, name: Optional[str]) -> Optional[dict]:
        found = await wild.people(ctx.author.id)
        if not found:
            await ctx.send(view=error_layout("Nobody yet", "Use `world explore` to meet travelers."))
            return None
        if not name:
            return found[0]
        npc = await wild.find_person(ctx.author.id, name)
        if npc is None:
            await ctx.send(view=error_layout("Nobody by that name", "Use `world people` to see who you have met."))
        return npc

    @world.command(name="talk", aliases=["chat", "speak"], help="Talk to someone you have met. Usage: world talk [name]")
    async def talk(self, ctx: commands.Context, *, name: Optional[str] = None):
        if await self.need_character(ctx) is None:
            return
        npc = await self.pick_person(ctx, name)
        if npc is None:
            return
        await ctx.send(view=await self.talk_view(ctx.author.id, npc["npc_id"]))

    async def talk_view(self, user_id: int, npc_id: str):
        e = emoji_manager.get
        result = await wild.talk_person(user_id, npc_id)
        npc = result.get("npc") or await wild.person(user_id, npc_id)
        kind = wanderers.KINDS[npc["kind"]]
        if not result["ok"]:
            body = f"{npc_card(npc)}\n\n{standing(npc['affinity'])}\nThey have nothing more to say today."
        else:
            body = f"{npc_card(npc)}\n\n*\"{result['line']}\"*\n\n{standing(result['after'])} (+{result['after'] - result['before']})"
            extra = reward_text(result["rewards"])
            if extra:
                body += "\n\n" + "\n".join(extra)
        choices = []
        if kind["action"]:
            choices.append((kind["action"], discord.ButtonStyle.primary, self.make_act(user_id, npc_id)))
        return ChoiceView(user_id, f"{e('ecult')} {npc['name']}", body, choices)

    def make_act(self, user_id: int, npc_id: str):
        async def callback(interaction: discord.Interaction):
            await self.do_act(interaction, user_id, npc_id)
        return callback

    async def do_act(self, interaction: discord.Interaction, user_id: int, npc_id: str):
        e = emoji_manager.get
        npc = await wild.person(user_id, npc_id)
        if npc is None:
            return await interaction.response.edit_message(view=error_layout("They are gone", "They slipped away."))
        if npc["kind"] == "rival":
            result = await wild.spar_start(user_id, npc_id)
            if not result["ok"]:
                reasons = {"hurt": f"You are injured for another **{duration(result.get('wait', 0))}**.", "limit": f"You can spar {settings.SPAR_DAILY} times a day."}
                return await interaction.response.edit_message(view=error_layout("Cannot spar", reasons.get(result["reason"], "That did not work.")))
            state = result["state"]
            state["tag"] = f"spar with {npc['name']}"
            state["on_done"] = self.spar_done(user_id, npc)
            self.active().add(user_id)
            return await interaction.response.edit_message(view=fight_layout(state, user_id, 0, self.active()), allowed_mentions=NO_PINGS)
        result = await wild.act(user_id, npc_id)
        if not result["ok"]:
            reasons = {
                "done": "You already did this today.",
                "coins": f"That costs **{coins.fmt(result.get('cost', 0))}** coins.",
                "nothing": "You have no materials to sell.",
            }
            return await interaction.response.edit_message(view=error_layout("Not now", reasons.get(result["reason"], "That did not work.")))
        kind = result["kind"]
        if kind == "alchemist":
            body = f"You buy a **Qi Pill** for **{coins.fmt(result['cost'])}** coins, 30% below the usual price."
        elif kind == "swordsman":
            body = f"They correct your stance and you gather **{coins.fmt(result['qi'])}** qi."
        elif kind == "survivor":
            body = f"You share a meal for **{coins.fmt(result['cost'])}** coins. They tell you: *{result['secret']}*"
            body += "".join("\n" + line for line in reward_text(result.get("rewards", {})))
        elif kind == "scout":
            if result.get("rift"):
                body = f"They point to a shimmering tear in the air: the **{result['rift']['world']}** ({result['rift']['zh']}). Enter it with `world rift`."
            else:
                body = "You already carry a rift, so they sell you a **Rift Shard** instead."
        else:
            sold = ", ".join(f"{count} {gear.MATERIALS[key]['name']}" for key, count in result["sold"].items())
            body = f"They take your {sold} and pay **{coins.fmt(result['coins'])}** coins."
        await interaction.response.edit_message(view=success_layout(f"{e('ecult')} {npc['name']}", body))

    def spar_done(self, user_id: int, npc: dict):
        async def callback(interaction: discord.Interaction, state: dict):
            e = emoji_manager.get
            outcome = await wild.spar_finish(user_id, state)
            parts = outcome["parts"]
            if outcome["result"] == "win":
                body = f"You win the spar against **{npc['name']}**.\n+{coins.fmt(parts.get('qi', 0))} qi"
            elif outcome["result"] == "lose":
                body = f"**{npc['name']}** wins this time. They are smug about it."
            else:
                body = "You step back from the spar."
            body += "".join("\n" + line for line in reward_text(parts["rewards"]))
            await interaction.response.edit_message(view=info_layout(f"{e('esword')} Spar", body))
        return callback

    @world.command(name="explore", aliases=["wander", "roam", "hunt"], help="Explore the wilds and see what finds you.")
    async def explore(self, ctx: commands.Context):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        if ctx.author.id in self.active() or self.in_run(ctx.author.id):
            return await ctx.send(view=error_layout("Busy", "Finish what you are doing first."))
        result = await wild.explore(ctx.author.id)
        if not result["ok"]:
            reasons = {
                "hurt": ("You are injured", f"You recover in **{duration(result.get('wait', 0))}**."),
                "cooldown": ("Catch your breath", f"You can explore again in **{duration(result.get('wait', 0))}**."),
                "limit": ("Enough for today", f"You can explore {settings.EXPLORE_DAILY} times a day."),
            }
            title, body = reasons.get(result["reason"], ("Cannot explore", "That did not work."))
            return await ctx.send(view=error_layout(title, body))
        await ctx.send(view=await self.encounter(ctx.author.id, result), allowed_mentions=NO_PINGS)

    async def encounter(self, user_id: int, result: dict) -> discord.ui.LayoutView:
        e = emoji_manager.get
        kind = result["kind"]
        left = f"\n\n-# {result['left']} explorations left today"
        if kind == "nothing":
            return info_layout(f"{e('ecult')} The wilds", result["text"] + left)
        if kind == "shard":
            return success_layout(f"{e('ecult')} A fragment of a world", "A rift flickers nearby, but you already carry one. It leaves a **Rift Shard** in your hand." + left)
        if kind == "rift":
            rift = result["rift"]
            return ChoiceView(user_id, f"{e('ecult')} A rift opens", (
                f"The air tears open and shows you the **{rift['world']}** ({rift['zh']}).\n*{rift['about']}*\n\n"
                f"It will close in {rifts.EXPIRY_HOURS} hours. Enter it any time with `world rift`." + left),
                [("Enter now", discord.ButtonStyle.success, self.enter_callback(user_id)), ("Later", discord.ButtonStyle.secondary, self.dismiss("The rift hums quietly. You can return with `world rift`."))])
        if kind == "traveler":
            npc = result["npc"]
            kind_info = wanderers.KINDS[npc["kind"]]
            choices = [("Talk", discord.ButtonStyle.primary, self.talk_callback(user_id, npc["npc_id"])), ("Walk on", discord.ButtonStyle.secondary, self.dismiss("You nod and keep walking. You can find them again with `world people`."))]
            return ChoiceView(user_id, f"{e('ecult')} A traveler", f"{npc_card(npc)}\n\nThey {kind_info['intro']}" + left, choices)
        if kind == "treasure":
            return ChoiceView(user_id, f"{e('ecult')} A forgotten cache", result["text"] + left, [
                ("Open it", discord.ButtonStyle.danger, self.treasure_callback(user_id, False, result["trap"])),
                ("Open carefully", discord.ButtonStyle.success, self.treasure_callback(user_id, True, result["trap"])),
                ("Leave it", discord.ButtonStyle.secondary, self.dismiss("You leave it sealed. Some things are better forgotten."))])
        if kind == "event":
            event = result["event"]
            choices = [(label, discord.ButtonStyle.primary if index == 0 else discord.ButtonStyle.secondary, self.crossroads_callback(user_id, result["index"], index)) for index, (label, _) in enumerate(event["options"])]
            return ChoiceView(user_id, f"{e('ecult')} A crossroads", event["text"] + left, choices)
        state = result["state"]
        boss = kind == "boss"
        m = state["m"]
        state["tag"] = "abyssal lord" if boss else "wild encounter"
        state["on_done"] = self.wild_done(user_id)
        self.active().add(user_id)
        intro = f"A **{m['name']}** steps out of the dark."
        if boss:
            intro = f"The air goes cold. **{m['name']}** rises from the ground, carrying the shape of a cultivator who died long ago."
        state["log"] = [intro]
        return fight_layout(state, user_id, result["left"], self.active())

    def dismiss(self, text: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=info_layout(f"{emoji_manager.get('ecult')} The wilds", text))
        return callback

    def talk_callback(self, user_id: int, npc_id: str):
        async def callback(interaction: discord.Interaction):
            view = await self.talk_view(user_id, npc_id)
            await interaction.response.edit_message(view=view)
        return callback

    def treasure_callback(self, user_id: int, careful: bool, trap: bool):
        async def callback(interaction: discord.Interaction):
            e = emoji_manager.get
            result = await wild.treasure(user_id, careful, trap)
            if result.get("trap"):
                return await interaction.response.edit_message(view=error_layout("A trap!", f"Old wards flare as you tear the lid off. You lose **{coins.fmt(result['loss'])}** qi."))
            lines = [f"+**{coins.fmt(result['coins'])}** coins"]
            if result.get("material"):
                key, count = result["material"]
                lines.append(f"+{count} **{gear.MATERIALS[key]['name']}**")
            await interaction.response.edit_message(view=success_layout(f"{e('ecult')} Treasure", "\n".join(lines)))
        return callback

    def crossroads_callback(self, user_id: int, index: int, option: int):
        async def callback(interaction: discord.Interaction):
            e = emoji_manager.get
            result = await wild.crossroads(user_id, index, option)
            outcome = result["outcome"]
            if outcome == "qi":
                body = f"The place gives you something quiet and warm. +**{coins.fmt(result['qi'])}** qi."
            elif outcome == "coins":
                body = f"You find something worth selling. +**{coins.fmt(result['coins'])}** coins."
            elif outcome == "loss":
                body = f"It was a mistake. The world takes **{coins.fmt(result['loss'])}** qi from you."
                return await interaction.response.edit_message(view=error_layout("A mistake", body))
            else:
                body = "Nothing comes of it. The road is quiet again."
            await interaction.response.edit_message(view=info_layout(f"{e('ecult')} The crossroads", body))
        return callback

    def wild_done(self, user_id: int):
        async def callback(interaction: discord.Interaction, state: dict):
            outcome = await wild.wild_finish(user_id, state)
            await interaction.response.edit_message(view=wild_result(state, outcome))
        return callback

    @world.command(name="rift", aliases=["rifts", "portal"], help="See or enter your rift. Usage: world rift [open]")
    async def rift(self, ctx: commands.Context, action: Optional[str] = None):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        await cult.check_titles(ctx.author.id)
        if action == "open":
            result = await wild.rift_open_with_shards(ctx.author.id)
            if not result["ok"]:
                reasons = {"open": "You already have an open rift.", "shards": f"You need **{rifts.SHARDS_TO_OPEN} Rift Shards**. Collect them from abyssal lords and rift runs."}
                return await ctx.send(view=error_layout("Cannot open a rift", reasons.get(result["reason"], "That did not work.")))
            rift = result["rift"]
            return await ctx.send(view=success_layout(f"{e('ecult')} A rift opens", f"You press the shards together and tear open the **{rift['world']}** ({rift['zh']}). Enter it with `world rift`."))
        rift = await wild.rift_get(ctx.author.id)
        if rift is None:
            shards = (await cult.inventory(ctx.author.id)).get("rift_shard", 0)
            return await ctx.send(view=info_layout(f"{e('ecult')} No open rift", f"Rifts are found while exploring. You carry **{shards}** Rift Shards, and {rifts.SHARDS_TO_OPEN} open one with `world rift open`."))
        if self.in_run(ctx.author.id) or ctx.author.id in self.active():
            return await ctx.send(view=error_layout("Busy", "Finish what you are doing first."))
        left = rift["expires_at"] - time.time()
        await ctx.send(view=ChoiceView(ctx.author.id, f"{e('ecult')} {rift['world']} ({rift['zh']})", (
            f"*{rift['about']}*\n\nThe rift closes in **{duration(max(0, left))}**. Inside are {rifts.ROOM_COUNT} rooms and a guardian, and you can retreat with your loot between rooms. "
            f"You can enter {rifts.DAILY} rifts a day."), [("Enter the rift", discord.ButtonStyle.success, self.enter_callback(ctx.author.id))]))

    def enter_callback(self, user_id: int):
        async def callback(interaction: discord.Interaction):
            result = await wild.rift_enter(user_id)
            if not result["ok"]:
                reasons = {
                    "hurt": f"You are injured for another **{duration(result.get('wait', 0))}**.",
                    "no_rift": "The rift has closed.",
                    "limit": f"You can enter {rifts.DAILY} rifts a day.",
                    "none": "You have not awakened.",
                }
                return await interaction.response.edit_message(view=error_layout("Cannot enter", reasons.get(result["reason"], "That did not work.")))
            run = result["run"]
            self.runs[user_id] = time.time() + 900
            await interaction.response.edit_message(view=self.room_view(run, user_id, f"You step through the tear and arrive in the **{run['world']}** ({run['zh']}).\n*{run['about']}*"), allowed_mentions=NO_PINGS)
        return callback

    def room_view(self, run: dict, user_id: int, note: str):
        e = emoji_manager.get
        self.runs[user_id] = time.time() + 900
        index = run["index"]
        room = run["rooms"][index]
        header = f"Room {index + 1}/{len(run['rooms'])} in the {run['world']}"
        loot = run["loot"]
        status = f"\n\n-# Loot so far: {coins.fmt(loot['coins'])} coins, {sum(loot['materials'].values())} materials"
        retreat = ("Retreat with loot", discord.ButtonStyle.secondary, self.run_end(run, user_id, "retreat"))
        if room == "beast":
            body = "A shape drags itself out of the rubble: an abyssal beast, still wearing scraps of a cultivator's robe."
            choices = [("Fight", discord.ButtonStyle.danger, self.run_fight(run, user_id, False)), ("Sneak past", discord.ButtonStyle.primary, self.run_step(run, user_id, "sneak"))]
        elif room == "treasure":
            run["trap"] = random.random() < 0.3
            body = rifts.TREASURE_TEXT[index % len(rifts.TREASURE_TEXT)]
            choices = [("Open boldly", discord.ButtonStyle.danger, self.run_step(run, user_id, "open")), ("Open carefully", discord.ButtonStyle.success, self.run_step(run, user_id, "careful"))]
        elif room == "trap":
            run["safe"] = random.randint(0, 1)
            body = rifts.TRAP_TEXT[index % len(rifts.TRAP_TEXT)]
            choices = [("Left", discord.ButtonStyle.primary, self.run_step(run, user_id, "left")), ("Right", discord.ButtonStyle.primary, self.run_step(run, user_id, "right"))]
        elif room == "spring":
            body = rifts.SPRING_TEXT[index % len(rifts.SPRING_TEXT)]
            choices = [("Rest here", discord.ButtonStyle.success, self.run_step(run, user_id, "spring"))]
        elif room == "traveler":
            body = "A figure sits among the ruins, not an abyssal beast but a living cultivator who must have fallen through a rift long ago."
            choices = [("Talk", discord.ButtonStyle.primary, self.run_step(run, user_id, "talk")), ("Pass by", discord.ButtonStyle.secondary, self.run_step(run, user_id, "pass"))]
        else:
            body = "The way out is held by a guardian: an **Abyssal Lord** that remembers being someone great."
            choices = [("Challenge it", discord.ButtonStyle.danger, self.run_fight(run, user_id, True))]
        if index > 0:
            choices.append(retreat)
        return ChoiceView(user_id, f"{e('ecult')} {header}", f"{note}\n\n{body}{status}", choices, timeout=300, on_timeout=self.run_timeout(run, user_id))

    def run_timeout(self, run: dict, user_id: int):
        async def callback():
            if self.in_run(user_id):
                self.runs.pop(user_id, None)
                await wild.rift_finish(user_id, run, "retreat")
        return callback

    def run_end(self, run: dict, user_id: int, outcome: str):
        async def callback(interaction: discord.Interaction):
            await self.finish_run(interaction, run, user_id, outcome)
        return callback

    async def finish_run(self, interaction: discord.Interaction, run: dict, user_id: int, outcome: str, note: str = ""):
        e = emoji_manager.get
        self.runs.pop(user_id, None)
        summary = await wild.rift_finish(user_id, run, outcome)
        lines = [note] if note else []
        if summary["outcome"] == "clear":
            lines.append(f"You defeat the guardian and leave the **{run['world']}** with the rift's treasure.")
        elif summary["outcome"] == "retreat":
            lines.append(f"You leave the **{run['world']}** while you still can.")
        else:
            lines.append(f"The **{run['world']}** throws you out. You keep only half your coins.")
        lines.append(f"+**{coins.fmt(summary['coins'])}** coins")
        if summary.get("qi"):
            lines.append(f"+{coins.fmt(summary['qi'])} qi")
        for key, count in (summary.get("materials") or {}).items():
            lines.append(f"+{count} **{gear.MATERIALS[key]['name']}**")
        if summary.get("shards"):
            lines.append(f"+{summary['shards']} **Rift Shard**")
        for drop in summary.get("gear") or []:
            lines.append(f"{e('esword')} **{gear.name(drop)}**")
        if summary.get("qi_lost"):
            lines.append(f"You lose {coins.fmt(summary['qi_lost'])} qi.")
        layout = (success_layout if summary["outcome"] == "clear" else error_layout if summary["outcome"] == "fail" else info_layout)(f"{e('ecult')} {run['world']}", "\n".join(lines))
        await interaction.response.edit_message(view=layout)

    def run_step(self, run: dict, user_id: int, action: str):
        async def callback(interaction: discord.Interaction):
            if action == "pass":
                run["index"] += 1
                return await interaction.response.edit_message(view=self.room_view(run, user_id, "You leave them to their ruins."))
            result = await wild.run_action(user_id, run, action)
            if result.get("caught"):
                return await self.start_fight(interaction, run, user_id, False, "It spots you. There is no sneaking past now.")
            note = self.step_note(result)
            run["index"] += 1
            await interaction.response.edit_message(view=self.room_view(run, user_id, note), allowed_mentions=NO_PINGS)
        return callback

    def step_note(self, result: dict) -> str:
        if result.get("sneaked"):
            return "You slip past without a sound."
        if result.get("trap") is not None and "trap" in result:
            return f"A ward flares and burns **{coins.fmt(result['trap'])}** coins of your loot to ash."
        if result.get("fell") is not None and "fell" in result:
            return f"You choose wrong and a floor gives way. You lose **{coins.fmt(result['fell'])}** coins of loot."
        if result.get("safe"):
            return f"You choose well. +{coins.fmt(result.get('coins', 0))} coins."
        if result.get("npc"):
            return f"You talk with **{result['npc']['name']}** ({result['npc']['zh']}), who will remember you. +{coins.fmt(result.get('coins', 0))} coins."
        if result.get("npc") is None and result.get("action") == "talk":
            return f"They share a little and wander off. +{coins.fmt(result.get('coins', 0))} coins."
        if result.get("qi"):
            return f"You rest and gather +{coins.fmt(result['qi'])} qi (paid when you leave)."
        return f"+{coins.fmt(result.get('coins', 0))} coins."

    def run_fight(self, run: dict, user_id: int, guardian: bool):
        async def callback(interaction: discord.Interaction):
            await self.start_fight(interaction, run, user_id, guardian, "")
        return callback

    async def start_fight(self, interaction: discord.Interaction, run: dict, user_id: int, guardian: bool, note: str):
        character = await cult.get(user_id)
        state = wild.room_fight(character, random, guardian)
        state["tag"] = f"{run['world']}, room {run['index'] + 1}"
        state["on_done"] = self.run_fight_done(run, user_id, guardian)
        self.active().add(user_id)
        await interaction.response.edit_message(view=fight_layout(state, user_id, 0, self.active()), allowed_mentions=NO_PINGS)

    def run_fight_done(self, run: dict, user_id: int, guardian: bool):
        async def callback(interaction: discord.Interaction, state: dict):
            character = await cult.get(user_id)
            result = state["done"]
            if result == "lose":
                return await self.finish_run(interaction, run, user_id, "fail", f"**{state['m']['name']}** beats you down.")
            if result == "flee":
                return await self.finish_run(interaction, run, user_id, "retreat", "You break away from the fight.")
            wild.add_loot(run, character, 3.0 if guardian else 1.0, random, 80 if guardian else 35)
            if guardian:
                return await self.finish_run(interaction, run, user_id, "clear", f"**{state['m']['name']}** falls.")
            run["index"] += 1
            await interaction.response.edit_message(view=self.room_view(run, user_id, f"**{state['m']['name']}** falls and dissolves into ash."), allowed_mentions=NO_PINGS)
        return callback

    @world.command(name="spawn", aliases=["spawns"], help="Turn wild abyssal spawns on or off in this channel. Usage: world spawn [on|off]")
    @commands.has_permissions(manage_guild=True)
    @commands.guild_only()
    async def spawn(self, ctx: commands.Context, action: Optional[str] = None):
        e = emoji_manager.get
        channel_id = ctx.channel.id
        if action == "on":
            await db.raw_execute("INSERT OR REPLACE INTO cult_spawn_channels (channel_id, guild_id) VALUES (?, ?)", (channel_id, ctx.guild.id))
            self.spawn_channels.add(channel_id)
            return await ctx.send(view=success_layout(f"{e('esword')} Spawns on", f"Abyssal beasts and lords will now appear here while people chat. Roughly one every {settings.SPAWN_COOLDOWN // 60}+ minutes of activity."))
        if action == "off":
            await db.raw_execute("DELETE FROM cult_spawn_channels WHERE channel_id=?", (channel_id,))
            self.spawn_channels.discard(channel_id)
            return await ctx.send(view=info_layout(f"{e('esword')} Spawns off", "Nothing will appear in this channel any more."))
        state = "on" if channel_id in self.spawn_channels else "off"
        await ctx.send(view=info_layout(f"{e('esword')} Wild spawns", f"Spawns are **{state}** in this channel. Use `world spawn on` or `world spawn off`."))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or message.channel.id not in self.spawn_channels:
            return
        now = time.time()
        state = self.channel_state.setdefault(message.channel.id, {"count": 0, "last": 0.0})
        state["count"] += 1
        if now - state["last"] < settings.SPAWN_COOLDOWN or state["count"] < settings.SPAWN_MESSAGES:
            return
        if random.randint(1, 100) > settings.SPAWN_CHANCE:
            return
        state["count"] = 0
        state["last"] = now
        try:
            if random.randint(1, 100) <= settings.SPAWN_BOSS_CHANCE:
                await self.spawn_boss(message.channel)
            else:
                await self.spawn_beast(message.channel)
        except discord.HTTPException:
            return

    async def spawn_beast(self, channel):
        e = emoji_manager.get
        key = random.choice(list(bestiary.MONSTERS))
        monster = bestiary.MONSTERS[key]
        remnant = bestiary.remnant(random)
        claimed: dict = {"user": 0}
        holder: dict = {}

        async def fight(interaction: discord.Interaction):
            if claimed["user"]:
                return await interaction.response.send_message("Someone else already took this fight.", ephemeral=True)
            character = await cult.get(interaction.user.id)
            if character is None or not character["path"]:
                return await interaction.response.send_message("You have not awakened yet. Use `cultivate awaken`.", ephemeral=True)
            if cult.hurt(character, time.time()):
                return await interaction.response.send_message("You are injured and cannot fight.", ephemeral=True)
            if interaction.user.id in self.active():
                return await interaction.response.send_message("Finish your current fight first.", ephemeral=True)
            if await cult.claim_daily(interaction.user.id, "cult_wild", settings.WILD_DAILY, time.time()) is None:
                return await interaction.response.send_message(f"You can only take {settings.WILD_DAILY} wild fights a day.", ephemeral=True)
            claimed["user"] = interaction.user.id
            view_state = wild.beast_state(character, random, key=key)
            view_state["tag"] = "wild abyssal beast"
            view_state["remnant"] = remnant
            view_state["on_done"] = done
            self.active().add(interaction.user.id)
            holder["view"].stop()
            await interaction.response.send_message(view=fight_layout(view_state, interaction.user.id, 0, self.active()), ephemeral=True, allowed_mentions=NO_PINGS)
            await message.edit(view=info_layout(f"{e('esword')} {monster['name']} ({monster['zh']})", f"{interaction.user.mention} stands against the beast."), allowed_mentions=NO_PINGS)

        async def done(interaction: discord.Interaction, state: dict):
            outcome = await wild.wild_finish(claimed["user"], state)
            await interaction.response.edit_message(view=wild_result(state, outcome))
            if outcome["result"] == "win":
                await message.edit(view=info_layout(f"{e('esword')} {monster['name']} falls", f"<@{claimed['user']}> slew the beast."), allowed_mentions=NO_PINGS)
            else:
                await message.edit(view=info_layout(f"{e('esword')} {monster['name']} fades", "The beast fades back into the dark."))

        async def expire():
            if not claimed["user"]:
                try:
                    await message.edit(view=info_layout(f"{e('esword')} {monster['name']} fades", "Nobody came. The beast dissolves back into the dark."))
                except discord.HTTPException:
                    pass

        view = ChoiceView(None, f"{e('esword')} An abyssal beast appears!", (
            f"**{monster['name']}** ({monster['zh']}) lurches out of the dark, born from {remnant}.\n\nThe first cultivator to act takes the fight. It lasts {settings.SPAWN_BEAST_SECONDS // 60} minutes."),
            [("Fight it", discord.ButtonStyle.danger, fight)], timeout=settings.SPAWN_BEAST_SECONDS, on_timeout=expire, stop_on_click=False)
        holder["view"] = view
        message = await channel.send(view=view, allowed_mentions=NO_PINGS)


    async def spawn_boss(self, channel):
        e = emoji_manager.get
        boss = random.choice(bestiary.CLAN_BOSSES)
        data = {"hp": settings.SPAWN_BOSS_HP, "max": settings.SPAWN_BOSS_HP, "damage": {}, "strikes": {}, "dead": False}
        lock = asyncio.Lock()

        def board() -> str:
            top = sorted(data["damage"].items(), key=lambda item: item[1], reverse=True)[:5]
            return "\n".join(f"{i}. <@{uid}> {coins.fmt(dmg)}" for i, (uid, dmg) in enumerate(top, 1)) or "Nobody has struck it yet."

        def view_for() -> ChoiceView:
            return ChoiceView(None, f"{e('esword')} Abyssal Lord: {boss['name']} ({boss['zh']})", (
                f"{e('eheart')} {coins.fmt(data['hp'])}/{coins.fmt(data['max'])}\n{bar(data['hp'], data['max'], 14)}\n\n**Top strikers**\n{board()}\n\n"
                f"-# Anyone can strike it twice. It fades in {settings.SPAWN_BOSS_SECONDS // 60} minutes."),
                [("Strike", discord.ButtonStyle.danger, strike)], timeout=settings.SPAWN_BOSS_SECONDS, on_timeout=expire, stop_on_click=False)

        async def strike(interaction: discord.Interaction):
            if data["dead"]:
                return await interaction.response.send_message("It has already fallen.", ephemeral=True)
            user_id = interaction.user.id
            character = await cult.get(user_id)
            if character is None or not character["path"]:
                return await interaction.response.send_message("You have not awakened yet. Use `cultivate awaken`.", ephemeral=True)
            if cult.hurt(character, time.time()):
                return await interaction.response.send_message("You are injured and cannot fight.", ephemeral=True)
            if user_id in self.active():
                return await interaction.response.send_message("Finish your current fight first.", ephemeral=True)
            if data["strikes"].get(user_id, 0) >= 2:
                return await interaction.response.send_message("You have already struck it twice.", ephemeral=True)
            if await cult.claim_daily(user_id, "cult_wildboss", settings.WILD_STRIKE_DAILY, time.time()) is None:
                return await interaction.response.send_message(f"You can strike lords {settings.WILD_STRIKE_DAILY} times a day.", ephemeral=True)
            data["strikes"][user_id] = data["strikes"].get(user_id, 0) + 1
            state = wild.strike_state(character, boss)
            state["tag"] = "abyssal lord"
            state["on_done"] = lambda inter, st, uid=user_id: finish(inter, st, uid)
            self.active().add(user_id)
            await interaction.response.send_message(view=fight_layout(state, user_id, 0, self.active()), ephemeral=True, allowed_mentions=NO_PINGS)

        async def finish(interaction: discord.Interaction, state: dict, user_id: int):
            character = await cult.get(user_id)
            units = wild.strike_units(character, state)
            payouts = {}
            async with lock:
                if data["dead"]:
                    units = 0
                else:
                    applied = min(units, data["hp"])
                    data["hp"] -= applied
                    data["damage"][user_id] = data["damage"].get(user_id, 0) + applied
                    if data["hp"] <= 0:
                        data["dead"] = True
                        payouts = await wild.world_boss_payout(data["damage"])
            await interaction.response.edit_message(view=info_layout(f"{e('esword')} Strike", f"You wound **{boss['name']}** for **{coins.fmt(units)}** damage."))
            try:
                if data["dead"]:
                    lines = [f"<@{uid}> +{coins.fmt(entry['coins'])} coins · {entry['material'][1]} {gear.MATERIALS[entry['material'][0]]['name']}" + (f" · {gear.name(entry['gear'])}" if entry.get("gear") else "") + (" · Rift Shard" if entry.get("shard") else "") for uid, entry in payouts.items()]
                    await message.edit(view=success_layout(f"{e('esword')} {boss['name']} is slain!", "\n".join(lines) or "It falls."), allowed_mentions=NO_PINGS)
                else:
                    await message.edit(view=view_for(), allowed_mentions=NO_PINGS)
            except discord.HTTPException:
                pass

        async def expire():
            if not data["dead"]:
                data["dead"] = True
                try:
                    await message.edit(view=info_layout(f"{e('esword')} {boss['name']} retreats", "The lord returns to the abyss, still wounded."))
                except discord.HTTPException:
                    pass

        message = await channel.send(view=view_for(), allowed_mentions=NO_PINGS)


async def setup(bot: commands.Bot):
    await bot.add_cog(World(bot))
