import asyncio
import random
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import coins, emoji_manager, rewards
from utils.checks import is_owner
from utils.components import ConfirmLayout, error_layout, info_layout, success_layout

NO_PINGS = discord.AllowedMentions.none()


def duration(seconds: float) -> str:
    seconds = max(1, int(seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def parse_bet(text: str, wallet: int) -> Optional[int]:
    text = text.strip().lower().replace(",", "")
    if text in ("all", "max"):
        return min(wallet, config.GAMBLE_MAX_BET)
    if text == "half":
        return min(wallet // 2, config.GAMBLE_MAX_BET)
    if text.endswith("k") and text[:-1].isdigit():
        return int(text[:-1]) * 1000
    return int(text) if text.isdigit() else None


class Economy(commands.Cog):
    category = "Engagement"
    submodule = "Economy"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.locks: dict[int, asyncio.Lock] = {}

    def lock_for(self, user_id: int) -> asyncio.Lock:
        return self.locks.setdefault(user_id, asyncio.Lock())

    @commands.group(name="coins", aliases=["balance", "bal", "wallet", "diamonds", "gems"], invoke_without_command=True, help="See your coins and diamonds. Usage: coins [user]")
    async def coins_group(self, ctx: commands.Context, user: Optional[discord.User] = None):
        e = emoji_manager.get
        target = user or ctx.author
        wallet = await coins.balances(target.id)
        who = "Your" if target.id == ctx.author.id else f"{target.display_name}'s"
        lines = [
            f"{e('ecoin')} **{coins.fmt(wallet['coins'])}** coins",
            f"{e('ediamond')} **{coins.fmt(wallet['diamonds'])}** diamonds",
            "",
            f"-# Coins come from sect duties: `reward`, `work`, `gather`, `hunt`, `mine`, `ruins` and `vote`. Diamonds are rare heaven crystals: buy them with `coins topup`, refine them into coins with `coins convert` (1 diamond = {config.DIAMOND_TO_COINS} coins) and pass coins or diamonds to fellow cultivators with `coins give`.",
        ]
        await ctx.send(view=info_layout(f"{e('ewallet')} {who} storage ring", "\n".join(lines)))

    @coins_group.command(name="topup", aliases=["buy", "add"], help="Buy diamonds with Bitcoin or Litecoin. Usage: coins topup [amount in USD]")
    async def coins_topup(self, ctx: commands.Context, amount: Optional[float] = None):
        cog = self.bot.get_cog("CryptoPay")
        if cog is None:
            return await ctx.send(view=error_layout("Unavailable", "Crypto payments are not available right now."))
        await cog.start_coins(ctx, amount)

    @coins_group.command(name="give", aliases=["pay", "send"], help="Give coins or diamonds to someone. Usage: coins give <user> <amount> [coins|diamonds]")
    async def coins_give(self, ctx: commands.Context, user: discord.User, amount: int, kind: str = "coins"):
        e = emoji_manager.get
        if user.bot or user.id == ctx.author.id:
            return await ctx.send(view=error_layout("Cannot do that", "Pick another cultivator."))
        diamonds = kind.lower() in ("diamond", "diamonds", "gems", "d")
        if kind.lower() not in ("coin", "coins", "c") and not diamonds:
            return await ctx.send(view=error_layout("Pick a currency", "Use `coins` or `diamonds`."))
        unit, icon, minimum = ("diamonds", e("ediamond"), config.COIN_TRANSFER_MIN) if diamonds else ("coins", e("ecoin"), config.COIN_GIVE_MIN)
        if amount < minimum:
            return await ctx.send(view=error_layout("Too small", f"The smallest gift is **{minimum}** {unit}."))
        async with self.lock_for(ctx.author.id):
            sent = await coins.transfer(ctx.author.id, user.id, amount, "diamonds" if diamonds else "coins")
        if not sent:
            have = await coins.diamonds(ctx.author.id) if diamonds else await coins.balance(ctx.author.id)
            return await ctx.send(view=error_layout(f"Not enough {unit}", f"You have **{coins.fmt(have)}** {unit}."))
        await ctx.send(view=success_layout(f"{e('check')} Sent", f"You passed {icon} **{coins.fmt(amount)}** {unit} to {user.mention}."), allowed_mentions=NO_PINGS)

    @coins_group.command(name="convert", aliases=["exchange", "swap"], help="Turn diamonds into coins. Usage: coins convert <diamonds|all>")
    async def coins_convert(self, ctx: commands.Context, amount: str):
        e = emoji_manager.get
        async with self.lock_for(ctx.author.id):
            have = await coins.diamonds(ctx.author.id)
            value = have if amount.lower() == "all" else int(amount) if amount.isdigit() else 0
            if value <= 0:
                return await ctx.send(view=error_layout("Invalid amount", "Use a number of diamonds, or `all`."))
            if value > have:
                return await ctx.send(view=error_layout("Not enough diamonds", f"You have **{coins.fmt(have)}** diamonds."))
            gained = value * config.DIAMOND_TO_COINS
            view = ConfirmLayout("Heavenly exchange", f"Refine {e('ediamond')} **{coins.fmt(value)}** diamonds into {e('ecoin')} **{coins.fmt(gained)}** coins?\nThis cannot be undone: coins cannot be turned back into diamonds.", author_id=ctx.author.id, timeout=30.0)
            message = await ctx.send(view=view)
            await view.wait()
            if view.value is not True:
                return
            result = await coins.convert(ctx.author.id, value)
            if not result:
                return await message.edit(view=error_layout("Not enough diamonds", "Your balance changed. Try again."))
            await message.edit(view=success_layout(f"{e('check')} Refined", f"The crystals dissolved into {e('ecoin')} **{coins.fmt(result)}** coins."))

    @coins_group.command(name="grant", help="Give coins or diamonds out of thin air (bot owner only). Usage: coins grant <user> <amount> [coins|diamonds]")
    @is_owner()
    async def coins_grant(self, ctx: commands.Context, user: discord.User, amount: int, kind: str = "coins"):
        e = emoji_manager.get
        if user.bot:
            return await ctx.send(view=error_layout("Cannot do that", "Bots do not have wallets."))
        if amount <= 0:
            return await ctx.send(view=error_layout("Invalid amount", "The amount must be above zero."))
        if kind.lower() in ("diamond", "diamonds", "gems", "bought"):
            total = await coins.add_diamonds(user.id, amount)
            name = "diamonds"
        else:
            total = await coins.add(user.id, amount)
            name = "coins"
        await ctx.send(view=success_layout(f"{e('check')} Granted", f"Gave **{coins.fmt(amount)}** {name} to {user.mention}. They now have **{coins.fmt(total)}**."), allowed_mentions=NO_PINGS)

    @coins_group.command(name="top", aliases=["leaderboard", "lb", "richest"], help="Show the wealthiest cultivators.")
    async def coins_top(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await coins.richest(10)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('leaderboard')} Wealthiest cultivators", "No cultivator has any coins yet."))
        lines = [f"**{i}.** <@{row['user_id']}> · {coins.fmt(row['coins'])}" for i, row in enumerate(rows, 1)]
        await ctx.send(view=info_layout(f"{e('leaderboard')} Wealthiest cultivators", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @coins_group.command(name="earn", aliases=["info", "howto"], help="See how to get coins and diamonds.")
    async def coins_earn(self, ctx: commands.Context):
        e = emoji_manager.get
        vote = max(config.VOTE_COINS.values(), default=0)
        top_bonus = config.REWARD_BASE + config.REWARD_STREAK_MAX_BONUS
        lines = [
            "**Coins: sect duties**",
            f"{e('edaily')} `reward` collects your sect stipend every day: **{config.REWARD_BASE}** coins, growing with your cultivation streak up to **{top_bonus}**.",
            f"{e('ework')} `work` an hour-long shift every hour, up to {config.WORK_DAILY_LIMIT} times a day. Pay depends on your sect `job`, and every shift brings you closer to a better one.",
            f"{e('egather')} `gather`, `hunt`, `mine` and `ruins` are small daily trips with cooldowns. `hunt` and `ruins` can come back empty. Every one of these, and `reward` and `work`, has a small chance to drop diamonds too.",
            f"{e('star')} `vote` for the bot: **{coins.fmt(vote)}** coins per vote, plus **{config.VOTE_DIAMONDS_MIN}-{config.VOTE_DIAMONDS_MAX}** diamonds once a day per bot list.",
            f"{e('gift')} `support`: **{coins.fmt(config.SUPPORT_COINS)}** coins for any tip.",
            f"{e('egamble')} `coinflip` (yin or yang) and `gamble` (fate draw) can win more, but the heavens favour the house.",
            "",
            "**Diamonds: heaven crystals**",
            f"{e('ediamond')} Buy them with Bitcoin or Litecoin using `coins topup`: {config.DIAMOND_PER_USD:,} diamonds for $1.",
            f"Refine them with `coins convert`: 1 diamond = {config.DIAMOND_TO_COINS} coins. Coins cannot become diamonds.",
            "",
            "**Spend them on**",
            "`premium` (coins or diamonds), `family upgrade`, `clan create`, `clan upgrade`, `profile theme buy` and `pet shop`.",
        ]
        await ctx.send(view=info_layout(f"{e('ewallet')} Ways to grow your wealth", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
