import asyncio
import random
from typing import Optional

import discord
from discord.ext import commands

import config
from cogs.economy import duration, parse_bet
from utils import coins, emoji_manager, jobs, rewards
from utils.components import error_layout, info_layout, success_layout


SIDES = {"yin": "yin", "yang": "yang", "tails": "yin", "t": "yin", "heads": "yang", "h": "yang"}
FATE = {1.5: "A faint omen of luck.", 2.0: "The spirit lanterns glow in your favour.", 3.0: "A heavenly sign blesses your draw!", 6.0: "The Dao itself nods at you!"}


def drop(result: dict, e) -> str:
    text = ""
    if result.get("bonus"):
        text += f"\n{e('shield')} Clan bonus: **+{coins.fmt(result['bonus'])}** coins"
    if result.get("diamonds"):
        text += f"\n{e('ediamond')} A heaven crystal fell out: **+{result['diamonds']}** diamond(s)!"
    return text


class Earn(commands.Cog):
    category = "Engagement"
    submodule = "Economy"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.locks: dict[int, asyncio.Lock] = {}

    def lock_for(self, user_id: int) -> asyncio.Lock:
        return self.locks.setdefault(user_id, asyncio.Lock())

    @commands.command(name="reward", aliases=["claim", "dailyreward"], help="Collect your daily sect stipend. Keep your cultivation streak for more.")
    async def reward(self, ctx: commands.Context):
        e = emoji_manager.get
        async with self.lock_for(ctx.author.id):
            result = await rewards.claim_reward(ctx.author.id)
        if not result["ok"]:
            return await ctx.send(view=error_layout("Stipend already collected", f"The elders have nothing more for you yet. Return in **{duration(result['wait'])}**. Your cultivation streak is **{result['streak']}**."))
        note = "\nYour cultivation was interrupted, so the streak starts over from day 1." if result["reset"] else ""
        await ctx.send(view=success_layout(f"{e('edaily')} Sect stipend", f"The elders hand you your stipend: {e('ecoin')} **+{coins.fmt(result['amount'])}** coins\nCultivation streak: **{result['streak']}** day(s). Collect every day to raise it.{drop(result, e)}{note}"))

    @commands.command(name="work", help="Work a shift at your sect job. Check jobs with `job`.")
    async def work(self, ctx: commands.Context):
        e = emoji_manager.get
        async with self.lock_for(ctx.author.id):
            result = await jobs.do_work(ctx.author.id)
        if not result["ok"]:
            if result["reason"] == "limit":
                return await ctx.send(view=error_layout("Done for today", f"You can work {config.WORK_DAILY_LIMIT} shifts a day. Come back tomorrow (UTC)."))
            return await ctx.send(view=error_layout("Still tired", f"You can work again in **{duration(result['wait'])}**."))
        lines = [f"As a **{result['job']['name']}** you {result['task']} and earned {e('ecoin')} **{coins.fmt(result['amount'])}** coins.{drop(result, e)}", f"-# {result['left']} shift(s) left today · {result['shifts']} shifts in total"]
        if result["promoted"]:
            lines.insert(1, f"\n{e('ejob')} You can now take the **{result['promoted']['name']}** job. Use `job take {result['promoted']['key']}`.")
        await ctx.send(view=success_layout(f"{e('ework')} Work", "\n".join(lines)))

    @commands.group(name="job", aliases=["jobs", "career"], invoke_without_command=True, help="See your sect job and how close you are to the next one.")
    async def job_group(self, ctx: commands.Context):
        e = emoji_manager.get
        current = await jobs.profile(ctx.author.id)
        job = current["job"]
        lines = [f"{e('ejob')} **{job['name']}**", f"Pay per shift: **{job['min']}-{job['max']}** coins · Shifts worked: **{current['shifts']}**"]
        nxt = jobs.next_job(current["shifts"])
        if nxt:
            lines.append(f"Next job: **{nxt['name']}** in **{nxt['shifts'] - current['shifts']}** more shift(s).")
        else:
            lines.append("You hold the highest job in the sect.")
        lines.append("\n-# `job list` shows every job. `job take <name>` switches between jobs you have unlocked. Work a shift with `work`.")
        await ctx.send(view=info_layout(f"{e('ework')} Your job", "\n".join(lines)))

    @job_group.command(name="list", aliases=["all", "ladder"], help="List every sect job and what it takes to get it.")
    async def job_list(self, ctx: commands.Context):
        e = emoji_manager.get
        current = await jobs.profile(ctx.author.id)
        lines = []
        for job in jobs.all_jobs():
            open_ = current["shifts"] >= job["shifts"]
            mark = "**(current)** " if job["key"] == current["job"]["key"] else ""
            need = "unlocked" if open_ else f"needs {job['shifts']} shifts"
            lines.append(f"{'' if open_ else '🔒 '}`{job['key']}` · **{job['name']}** {mark}· {job['min']}-{job['max']} coins · {need}")
        await ctx.send(view=info_layout(f"{e('ejob')} Sect jobs", "\n".join(lines)))

    @job_group.command(name="take", aliases=["set", "switch", "apply"], help="Take a job you have unlocked. Usage: job take <name>")
    async def job_take(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        job = jobs.find_job(name)
        if not job:
            return await ctx.send(view=error_layout("Unknown job", "Use `job list` to see the job names."))
        if not await jobs.choose(ctx.author.id, job):
            current = await jobs.profile(ctx.author.id)
            return await ctx.send(view=error_layout("Not yet", f"**{job['name']}** needs **{job['shifts']}** shifts and you have **{current['shifts']}**."))
        await ctx.send(view=success_layout(f"{e('ejob')} New job", f"You are now a **{job['name']}**. Your shifts pay **{job['min']}-{job['max']}** coins."))

    async def run_activity(self, ctx: commands.Context, key: str):
        e = emoji_manager.get
        spec = config.CULTIVATION_ACTIVITIES[key]
        async with self.lock_for(ctx.author.id):
            result = await jobs.do_activity(ctx.author.id, key)
        title = f"{e(spec['icon'])} {spec['title']}"
        if not result["ok"]:
            if result["reason"] == "limit":
                return await ctx.send(view=error_layout(title, f"You can do this {spec['daily']} time(s) a day. Come back tomorrow (UTC)."))
            return await ctx.send(view=error_layout(title, f"You are still recovering. Try again in **{duration(result['wait'])}**."))
        if result["amount"]:
            return await ctx.send(view=success_layout(title, f"{result['text']} {e('ecoin')} **{coins.fmt(result['amount'])}** coins.{drop(result, e)}\n-# {result['left']} left today"))
        await ctx.send(view=error_layout(title, f"{result['text']}\n-# {result['left']} left today"))

    @commands.command(name="gather", aliases=["herbs", "forage"], help="Gather spirit herbs and sell them for coins.")
    async def gather(self, ctx: commands.Context):
        await self.run_activity(ctx, "gather")

    @commands.command(name="hunt", aliases=["beasthunt"], help="Hunt spirit beasts for their cores. You may come back empty handed.")
    async def hunt(self, ctx: commands.Context):
        await self.run_activity(ctx, "hunt")

    @commands.command(name="mine", aliases=["dig", "spiritmine"], help="Mine spirit stone shards for coins.")
    async def mine(self, ctx: commands.Context):
        await self.run_activity(ctx, "mine")

    @commands.command(name="ruins", aliases=["explore", "delve"], help="Explore ancient ruins for a chance at big treasure.")
    async def ruins(self, ctx: commands.Context):
        await self.run_activity(ctx, "ruins")

    async def take_bet(self, ctx: commands.Context, text: str) -> Optional[int]:
        wallet = await coins.balance(ctx.author.id)
        bet = parse_bet(text, wallet)
        if bet is None or bet < config.GAMBLE_MIN_BET:
            await ctx.send(view=error_layout("Invalid wager", f"Wager between **{config.GAMBLE_MIN_BET}** and **{coins.fmt(config.GAMBLE_MAX_BET)}** coins. You can also use `all` or `half`."))
            return None
        if bet > config.GAMBLE_MAX_BET:
            await ctx.send(view=error_layout("Wager too high", f"The gambling pavilion accepts at most **{coins.fmt(config.GAMBLE_MAX_BET)}** coins."))
            return None
        if bet > wallet:
            await ctx.send(view=error_layout("Not enough coins", f"You have **{coins.fmt(wallet)}** coins."))
            return None
        wait = await rewards.gamble_gate(ctx.author.id)
        if wait > 0:
            await ctx.send(view=error_layout("Slow down", f"The dealer needs **{duration(wait)}** before the next wager."))
            return None
        if not await coins.spend(ctx.author.id, bet):
            await ctx.send(view=error_layout("Not enough coins", "Your balance changed. Try again."))
            return None
        return bet

    @commands.command(name="coinflip", aliases=["cf", "flip"], help="Wager coins on a yin-yang toss. Usage: coinflip <bet|all|half> [yin|yang]")
    async def coinflip(self, ctx: commands.Context, bet: str, side: str = ""):
        e = emoji_manager.get
        side = side.lower()
        if side and side not in SIDES:
            return await ctx.send(view=error_layout("Pick a side", "Use `yin` or `yang`, or leave it out for the heavens to pick."))
        async with self.lock_for(ctx.author.id):
            amount = await self.take_bet(ctx, bet)
            if amount is None:
                return
            pick = SIDES.get(side) or random.choice(("yin", "yang"))
            landed = random.choice(("yin", "yang"))
            if pick == landed:
                payout = int(amount * config.COINFLIP_PAYOUT)
                await coins.add(ctx.author.id, payout)
                body = f"The talisman settled on **{landed}**. You called **{pick}** and won {e('ecoin')} **{coins.fmt(payout - amount)}** coins."
                view = success_layout(f"{e('egamble')} Yin-yang toss", body)
            else:
                view = error_layout(f"{e('egamble')} Yin-yang toss", f"The talisman settled on **{landed}**. You called **{pick}** and lost {e('ecoin')} **{coins.fmt(amount)}** coins.")
        await ctx.send(view=view)

    @commands.command(name="gamble", aliases=["bet"], help="Draw your fate for a multiplier on your wager. Usage: gamble <bet|all|half>")
    async def gamble(self, ctx: commands.Context, bet: str):
        e = emoji_manager.get
        async with self.lock_for(ctx.author.id):
            amount = await self.take_bet(ctx, bet)
            if amount is None:
                return
            multiplier = rewards.roll_gamble()
            if multiplier <= 0:
                view = error_layout(f"{e('egamble')} Fate draw", f"The heavens turned away from you. You lost {e('ecoin')} **{coins.fmt(amount)}** coins.")
            else:
                payout = int(amount * multiplier)
                await coins.add(ctx.author.id, payout)
                view = success_layout(f"{e('egamble')} Fate draw", f"{FATE.get(multiplier, 'Fortune smiles on you.')} **x{multiplier:g}**! You got back {e('ecoin')} **{coins.fmt(payout)}** coins (**{payout - amount:+,}**).")
        await ctx.send(view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Earn(bot))
