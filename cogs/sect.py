import asyncio
import time
from typing import Optional

import discord
from discord.ext import commands

from cogs.cultivation import NO_PINGS, bar, fight_layout
from cogs.economy import duration
from rpg import arts, engine as cult, sect, settings
from utils import clans, coins, emoji_manager
from utils.components import error_layout, info_layout, success_layout


class Sect(commands.Cog):
    category = "Cultivation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = asyncio.Lock()

    def cultivation_active(self) -> set:
        cog = self.bot.get_cog("Cultivation")
        return cog.active if cog else set()

    async def own(self, ctx: commands.Context) -> Optional[tuple[dict, dict]]:
        mine = await clans.membership(ctx.author.id)
        if mine is None:
            await ctx.send(view=error_layout("No clan", "Your clan is your great family. Use `clan create <name>` or ask for an invite."))
            return None
        return mine, await clans.get(mine["clan_id"])

    def find_building(self, text: str) -> Optional[str]:
        text = text.lower().strip()
        for key, info in settings.BUILDINGS.items():
            if text in (key, info["name"].lower(), info["zh"]) or text in info["name"].lower().split():
                return key
        return None

    @commands.group(name="sect", aliases=["sects", "hall"], invoke_without_command=True, help="Your clan hall: buildings, boss raids and wars.")
    async def sect_group(self, ctx: commands.Context):
        await self.status(ctx)

    @sect_group.command(name="status", aliases=["info", "buildings"], help="Show your clan's buildings, boss and war.")
    async def status(self, ctx: commands.Context):
        e = emoji_manager.get
        owned = await self.own(ctx)
        if owned is None:
            return
        _, clan = owned
        levels = await cult.building_levels(clan["clan_id"])
        cap = sect.level_cap(clan)
        lines = [f"**Bank:** {coins.fmt(clan['bank'])} coins · buildings can reach level **{cap}** at this tier\n"]
        for key, info in settings.BUILDINGS.items():
            level = levels.get(key, 0)
            nxt = f"next: {coins.fmt(sect.cost_of(level))}" if level < min(cap, settings.BUILDING_MAX) else "at tier limit" if level < settings.BUILDING_MAX else "max"
            lines.append(f"**{info['name']}** ({info['zh']}) level {level}/{settings.BUILDING_MAX} · {nxt}\n-# {info['info']}")
        war = await sect.war_of(clan["clan_id"])
        if war:
            lines.append(f"\n{e('esword')} A war with **{await self.other_name(war, clan['clan_id'])}** is **{war['status']}**. See `sect war`.")
        lines.append("\n-# `sect build <building>`, `sect boss`, `sect attack`, `sect war`, `sect techniques`")
        await ctx.send(view=info_layout(f"{e('ecult')} {clan['name']} Clan hall", "\n".join(lines)))

    async def other_name(self, war: dict, clan_id: str) -> str:
        other = war["clan_b"] if war["clan_a"] == clan_id else war["clan_a"]
        clan = await clans.get(other)
        return clan["name"] if clan else "a fallen clan"

    @sect_group.command(name="build", aliases=["upgrade", "construct"], help="Spend clan bank coins on a building. Usage: sect build <building>")
    async def build(self, ctx: commands.Context, *, name: Optional[str] = None):
        e = emoji_manager.get
        owned = await self.own(ctx)
        if owned is None:
            return
        mine, clan = owned
        if clans.ROLE_ORDER[mine["role"]] < clans.ROLE_ORDER["officer"]:
            return await ctx.send(view=error_layout("Not allowed", "Only the Young Master and Elders can build."))
        key = self.find_building(name or "")
        if key is None:
            names = ", ".join(f"`{k}`" for k in settings.BUILDINGS)
            return await ctx.send(view=error_layout("Pick a building", f"Use `sect build <building>`: {names}."))
        async with self.lock:
            result = await sect.build(clan["clan_id"], key)
        if not result["ok"]:
            reasons = {
                "max": ("Fully built", "That building is already at its highest level."),
                "tier": ("Clan tier too low", f"At this tier buildings can reach level {result.get('cap', 1)}. Upgrade the clan with `clan upgrade`."),
                "bank": ("Not enough in the bank", f"The next level costs **{coins.fmt(result.get('cost', 0))}** coins. Members can add coins with `clan deposit`."),
                "race": ("Try again", "Someone else built at the same moment."),
            }
            title, body = reasons.get(result["reason"], ("Cannot build", "That did not work."))
            return await ctx.send(view=error_layout(title, body))
        info = settings.BUILDINGS[key]
        await ctx.send(view=success_layout(f"{e('ecult')} {info['name']} level {result['level']}", f"The clan spends **{coins.fmt(result['cost'])}** coins.\n{info['info']}"))

    @sect_group.command(name="techniques", aliases=["arts", "scripture"], help="Show the clan techniques the Scripture Pavilion unlocks.")
    async def techniques(self, ctx: commands.Context):
        e = emoji_manager.get
        owned = await self.own(ctx)
        if owned is None:
            return
        _, clan = owned
        level = (await cult.building_levels(clan["clan_id"])).get("scripture", 0)
        lines = []
        for tech in arts.SECT_TECHNIQUES.values():
            if tech["sect"] <= level:
                lines.append(f"**{tech['name']}** ({tech['zh']}) · recharge {tech['cd']} turns\n{tech['info']}")
            else:
                lines.append(f"~~{tech['name']}~~ · needs Scripture Pavilion level {tech['sect']}")
        lines.append("\n-# Every member can use unlocked clan techniques in any fight, whatever their path.")
        await ctx.send(view=info_layout(f"{e('esword')} Clan techniques", "\n\n".join(lines)))

    @sect_group.command(name="boss", aliases=["beast"], help="Show your clan's boss and who hurt it most.")
    async def boss(self, ctx: commands.Context):
        e = emoji_manager.get
        owned = await self.own(ctx)
        if owned is None:
            return
        _, clan = owned
        row = await sect.boss_current(clan["clan_id"])
        info = sect.boss_info(row["boss"])
        if row["killed"]:
            wait = row["killed_at"] + settings.BOSS_RESPAWN_HOURS * 3600 - time.time()
            return await ctx.send(view=info_layout(f"{e('esword')} {info['name']} (slain)", f"Your clan killed it. A new boss appears in **{duration(max(0, wait))}**."))
        hits = await sect.boss_hits(clan["clan_id"], 5)
        board = "\n".join(f"{index}. <@{hit['user_id']}> {coins.fmt(hit['damage'])}" for index, hit in enumerate(hits, 1)) or "Nobody has struck it yet."
        left = row["spawned_at"] + settings.BOSS_DAYS * 86400 - time.time()
        await ctx.send(view=info_layout(f"{e('esword')} {info['name']} ({info['zh']})", (
            f"{e('eheart')} {coins.fmt(row['hp'])}/{coins.fmt(row['max_hp'])}\n{bar(row['hp'], row['max_hp'], 14)}\n\n"
            f"**Top strikers**\n{board}\n\n"
            f"-# Use `sect attack`, {settings.BOSS_DAILY} times a day. It flees in {duration(max(0, left))}. Everyone who struck it shares the loot when it falls.")), allowed_mentions=NO_PINGS)

    @sect_group.command(name="attack", aliases=["strike", "hit"], help="Strike your clan's boss in a turn-based fight.")
    async def attack(self, ctx: commands.Context):
        if await cult.get(ctx.author.id) is None:
            return await ctx.send(view=error_layout("Not awakened", "Use `cultivate awaken` to begin."))
        active = self.cultivation_active()
        if ctx.author.id in active:
            return await ctx.send(view=error_layout("Already fighting", "Finish your current fight first."))
        result = await sect.boss_start(ctx.author.id)
        if not result["ok"]:
            reasons = {
                "no_clan": ("No clan", "Your clan is your great family. Use `clan create <name>` or ask for an invite."),
                "none": ("Not awakened", "Choose a path with `cultivate awaken` first."),
                "hurt": ("You are injured", f"You recover in **{duration(result.get('wait', 0))}**."),
                "dead": ("The boss is slain", "Wait for the next one with `sect boss`."),
                "limit": ("No strikes left", f"You can strike the boss **{settings.BOSS_DAILY}** times a day."),
            }
            title, body = reasons.get(result["reason"], ("Cannot attack", "That did not work."))
            return await ctx.send(view=error_layout(title, body))
        active.add(ctx.author.id)
        await ctx.send(view=fight_layout(result["state"], ctx.author.id, result["left"], active), allowed_mentions=NO_PINGS)

    @sect_group.command(name="war", aliases=["wars"], help="Clan wars. Usage: sect war [declare <clan>|accept|decline]")
    async def war(self, ctx: commands.Context, action: Optional[str] = None, *, clan_name: Optional[str] = None):
        e = emoji_manager.get
        owned = await self.own(ctx)
        if owned is None:
            return
        _, clan = owned
        if action == "declare":
            if not clan_name:
                return await ctx.send(view=error_layout("Pick a clan", "Use `sect war declare <clan name>`."))
            result = await sect.declare(ctx.author.id, clan_name)
            if not result["ok"]:
                reasons = {
                    "rank": ("Not allowed", "Only the Young Master and Elders can declare war."),
                    "unknown": ("Unknown clan", "No clan has that name."),
                    "self": ("Not your own clan", "Pick another clan."),
                    "tier": ("Tier too low", f"Both clans must be at least tier {settings.WAR_MIN_TIER}."),
                    "busy": ("Already at war", "One of the clans already has a war pending or running."),
                    "cooldown": ("Too soon", f"**{result.get('clan', {}).get('name', 'A clan')}** fought recently. Try again in **{duration(result.get('wait', 0))}**."),
                }
                title, body = reasons.get(result["reason"], ("Cannot declare", "That did not work."))
                return await ctx.send(view=error_layout(title, body))
            return await ctx.send(view=success_layout(f"{e('esword')} War declared", f"**{result['clan']['name']}** challenges **{result['target']['name']}**.\nTheir Young Master or an Elder must use `sect war accept` within {settings.WAR_PENDING_HOURS} hours."))
        if action in ("accept", "decline"):
            result = await sect.respond(ctx.author.id, action == "accept")
            if not result["ok"]:
                reasons = {
                    "rank": ("Not allowed", "Only the Young Master and Elders can answer a war."),
                    "none": ("No challenge", "Nobody has challenged your clan."),
                }
                title, body = reasons.get(result["reason"], ("Cannot answer", "That did not work."))
                return await ctx.send(view=error_layout(title, body))
            if action == "decline":
                return await ctx.send(view=info_layout("War declined", "The challenge is withdrawn."))
            return await ctx.send(view=success_layout(f"{e('esword')} War begins", f"For **{settings.WAR_HOURS} hours**, every raid that beats a member of the other clan scores points. See `sect war`."))
        war = await sect.war_of(clan["clan_id"])
        if war is None:
            last = await sect.last_war(clan["clan_id"])
            text = "Your clan is at peace. Use `sect war declare <clan>`."
            if last:
                rival = await self.other_name(last, clan["clan_id"])
                ours = last["score_a"] if last["clan_a"] == clan["clan_id"] else last["score_b"]
                theirs = last["score_b"] if last["clan_a"] == clan["clan_id"] else last["score_a"]
                outcome = "A draw." if last["result"] == "draw" else (f"{'Your clan won' if last['result'].split(':')[1] == clan['clan_id'] else 'Your clan lost'}, {coins.fmt(int(last['result'].split(':')[2]))} coins changed hands.")
                text += f"\n\n**Last war** against {rival}: {ours} to {theirs}. {outcome}"
            return await ctx.send(view=info_layout(f"{e('esword')} Clan war", text + f"\n\n-# Rules: both clans tier {settings.WAR_MIN_TIER}+, {settings.WAR_HOURS} hours, one point per raid win (up to 3 against higher realms). The winner needs {settings.WAR_MIN_SCORE}+ points and takes {int(settings.WAR_STAKE_PCT * 100)}% of the loser's bank, up to {coins.fmt(settings.WAR_STAKE_MAX)}."))
        rival = await self.other_name(war, clan["clan_id"])
        ours = war["score_a"] if war["clan_a"] == clan["clan_id"] else war["score_b"]
        theirs = war["score_b"] if war["clan_a"] == clan["clan_id"] else war["score_a"]
        if war["status"] == "pending":
            who = "waiting for them to accept" if war["clan_a"] == clan["clan_id"] else "waiting for your Young Master or an Elder to `sect war accept`"
            return await ctx.send(view=info_layout(f"{e('esword')} War pending", f"Against **{rival}**, {who}."))
        await ctx.send(view=info_layout(f"{e('esword')} War against {rival}", f"**{ours}** to **{theirs}**\nEnds in **{duration(max(0, war['ends_at'] - time.time()))}**.\n\n-# Win raids against members of {rival} with `cultivate raid`."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Sect(bot))
