from typing import Optional

import discord
from discord.ext import commands

import config
from utils import coins, emoji_manager
from utils.checks import is_owner
from utils.components import error_layout, info_layout, success_layout


class Economy(commands.Cog):
    category = "Economy"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="coins", aliases=["balance", "bal", "wallet"], invoke_without_command=True, help="See your coin balance. Usage: coins [user]")
    async def coins_group(self, ctx: commands.Context, user: Optional[discord.User] = None):
        e = emoji_manager.get
        target = user or ctx.author
        wallet = await coins.balances(target.id)
        who = "Your" if target.id == ctx.author.id else f"{target.display_name}'s"
        lines = [
            f"{e('coin')} **{coins.fmt(wallet['total'])}** coins",
            f"Bought: **{coins.fmt(wallet['bought'])}** · Earned: **{coins.fmt(wallet['earned'])}**",
            "",
            "-# Only bought coins can be given to other people. Earn coins by voting (`vote`) or supporting (`support`), or buy them with `coins topup`.",
        ]
        await ctx.send(view=info_layout(f"{e('wallet')} {who} wallet", "\n".join(lines)))

    @coins_group.command(name="topup", aliases=["buy", "add"], help="Buy coins with Bitcoin or Litecoin. Usage: coins topup [amount in USD]")
    async def coins_topup(self, ctx: commands.Context, amount: Optional[float] = None):
        cog = self.bot.get_cog("CryptoPay")
        if cog is None:
            return await ctx.send(view=error_layout("Unavailable", "Crypto payments are not available right now."))
        await cog.start_coins(ctx, amount)

    @coins_group.command(name="give", aliases=["pay", "send"], help="Give some of your bought coins to someone. Earned coins cannot be given. Usage: coins give <user> <amount>")
    async def coins_give(self, ctx: commands.Context, user: discord.User, amount: int):
        e = emoji_manager.get
        if user.bot or user.id == ctx.author.id:
            return await ctx.send(view=error_layout("Cannot do that", "Pick another person."))
        if amount < config.COIN_TRANSFER_MIN:
            return await ctx.send(view=error_layout("Too small", f"The smallest transfer is **{config.COIN_TRANSFER_MIN}** coins."))
        if not await coins.transfer(ctx.author.id, user.id, amount):
            wallet = await coins.balances(ctx.author.id)
            return await ctx.send(view=error_layout("Not enough bought coins", f"Only bought coins can be given away. You have **{coins.fmt(wallet['bought'])}** bought and **{coins.fmt(wallet['earned'])}** earned coins."))
        await ctx.send(view=success_layout(f"{e('check')} Sent", f"You gave **{coins.fmt(amount)}** coins to {user.mention}."))

    @coins_group.command(name="grant", help="Give coins to a user out of thin air (bot owner only). Usage: coins grant <user> <amount> [bought]")
    @is_owner()
    async def coins_grant(self, ctx: commands.Context, user: discord.User, amount: int, kind: str = "earned"):
        e = emoji_manager.get
        if user.bot:
            return await ctx.send(view=error_layout("Cannot do that", "Bots do not have wallets."))
        if amount <= 0:
            return await ctx.send(view=error_layout("Invalid amount", "The amount must be above zero."))
        bought = kind.lower() == "bought"
        total = await coins.add(user.id, amount, bought=bought)
        await ctx.send(view=success_layout(f"{e('check')} Coins granted", f"Gave **{coins.fmt(amount)}** {'bought' if bought else 'earned'} coins to {user.mention}. They now have **{coins.fmt(total)}**."), allowed_mentions=discord.AllowedMentions.none())

    @coins_group.command(name="top", aliases=["leaderboard", "lb", "richest"], help="Show the richest users.")
    async def coins_top(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await coins.richest(10)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('trophy')} Richest users", "Nobody has coins yet."))
        lines = [f"**{i}.** <@{row['user_id']}> · {coins.fmt(row['coins'])}" for i, row in enumerate(rows, 1)]
        await ctx.send(view=info_layout(f"{e('trophy')} Richest users", "\n".join(lines)))

    @coins_group.command(name="earn", aliases=["info", "howto"], help="See how to get coins.")
    async def coins_earn(self, ctx: commands.Context):
        e = emoji_manager.get
        vote = max(config.VOTE_COINS.values(), default=0)
        lines = [
            f"{e('star')} **Vote** for the bot with `vote`: **{coins.fmt(vote)}** coins per vote on each bot list.",
            f"{e('gift')} **Support** with `support`: **{coins.fmt(config.SUPPORT_COINS)}** coins for any tip, whatever the amount.",
            f"{e('coin')} **Buy** coins with Bitcoin or Litecoin using `coins topup`: {config.COIN_PER_USD:,} coins for $1. Bought coins can also be given to other people with `coins give`.",
            "",
            "**Spend them on**",
            "`premium coins` for server premium, `family upgrade` for more marriages or children, and `clan create` or `clan upgrade` for clans.",
        ]
        await ctx.send(view=info_layout(f"{e('wallet')} Getting coins", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Economy(bot))
