import logging
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from cogs.cultivation import NO_PINGS
from rpg import stones, settings, trade
from utils import coins, emoji_manager
from utils.components import error_layout, info_layout, success_layout

log = logging.getLogger("zyro.marketplace")

ERRORS = {
    "item": ("Unknown item", "Use an item name such as `demon core` or `qi pill`, or a crafted weapon as `#12`. Check your bag with `cultivate bag`."),
    "bound": ("Soul-bound", "Soul-bound weapons and relics cannot be sold, traded or stolen."),
    "qty": ("Bad amount", "Use a whole amount from 1 to {max}. Crafted weapons are sold one at a time."),
    "price": ("Bad price", "Prices run from 1 low-grade spirit stone to {price}. You can write `1.5k`, `2m`, `3mid` or `2high`. A buyout must be higher than the starting price."),
    "hours": ("Bad duration", "Auctions last from {min} to {maxh} hours."),
    "missing": ("You do not have that", "You need to own it, and a weapon must not be equipped or already for sale."),
    "limit": ("Too many listings", "You can have **{limit}** open at once."),
    "gone": ("Not available", "That listing or auction is gone, sold or ended."),
    "own": ("Your own listing", "You cannot trade with yourself."),
    "coins": ("Not enough spirit stones", "You need **{need}**."),
    "low": ("Bid too low", "The next bid must be at least **{min}**."),
    "race": ("Someone was faster", "Another bid landed first. Your spirit stones were returned. Try again."),
    "nobuyout": ("No buyout", "This auction has no buyout price."),
    "bids": ("Already has bids", "An auction with bids cannot be cancelled."),
}


def stamp(when: float) -> str:
    return f"<t:{int(when)}:R>"


def split_page(text: str) -> tuple:
    words = text.split()
    if words and words[-1].isdigit():
        return " ".join(words[:-1]), int(words[-1])
    return text.strip(), 1


class Marketplace(commands.Cog):
    category = "Cultivation"
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.settle_loop.start()

    def cog_unload(self):
        self.settle_loop.cancel()

    @tasks.loop(minutes=1)
    async def settle_loop(self):
        now = time.time()
        try:
            notes = await trade.expire_market(now) + await trade.settle_due(now)
        except Exception:
            log.warning("Market settlement failed", exc_info=True)
            return
        for note in notes:
            await self.notify(note)

    @settle_loop.before_loop
    async def before_settle(self):
        await self.bot.wait_until_ready()

    async def dm(self, user_id: int, text: str) -> None:
        if not user_id:
            return
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            await user.send(text)
        except (discord.HTTPException, discord.Forbidden):
            pass

    async def notify(self, note: dict) -> None:
        label = f"{note['qty']}x {await trade.describe(note['item'])}" if not note["item"].startswith("w:") else await trade.describe(note["item"])
        if note["kind"] == "market":
            await self.dm(note["seller_id"], f"Your marketplace listing #{note['id']} expired. **{label}** is back in your bag.")
        elif note.get("sold"):
            await self.dm(note["seller_id"], f"Your auction #{note['id']} sold: **{label}** for **{stones.fmt(note['price'])}**. After the {settings.AUCTION_FEE_PCT}% fee you received **{stones.fmt(note['net'])}**.")
            await self.dm(note["winner_id"], f"You won auction #{note['id']}: **{label}** for **{stones.fmt(note['price'])}**. It is in your bag.")
        else:
            await self.dm(note["seller_id"], f"Your auction #{note['id']} ended with no bids. **{label}** is back in your bag.")

    def failure(self, reason: str, **extra):
        title, body = ERRORS.get(reason, ("Cannot do that", "That did not work."))
        values = {"max": settings.MARKET_MAX_QTY, "price": stones.fmt(settings.MARKET_MAX_PRICE), "min": settings.AUCTION_MIN_HOURS, "maxh": settings.AUCTION_MAX_HOURS, "limit": extra.get("limit", ""), "need": stones.fmt(extra.get('total') or extra.get('amount') or extra.get('need') or 0)}
        if "min" in extra:
            values["min"] = stones.fmt(extra["min"])
        return error_layout(title, body.format(**values))

    async def listing_line(self, row: dict, auction: bool = False) -> str:
        label = await trade.describe(row["item"])
        if not row["item"].startswith("w:"):
            label = f"**{label}** x{row['qty']}"
        if auction:
            current = f"**{stones.fmt(row['bid'])}** ({row['bids']} bids)" if row["bids"] else f"starts at **{stones.fmt(row['start_price'])}**"
            extra = f" · buyout **{stones.fmt(row['buyout'])}**" if row["buyout"] else ""
            return f"`#{row['auction_id']}` {label} · {current}{extra} · ends {stamp(row['ends_at'])}"
        each = f" ({stones.fmt(row['price'])} each)" if row["qty"] > 1 else ""
        return f"`#{row['listing_id']}` {label} · **{stones.fmt(row['price'] * row['qty'])}**{each} · <@{row['seller_id']}> · expires {stamp(row['expires_at'])}"

    @commands.group(name="market", aliases=["mp", "marketplace"], invoke_without_command=True, help="Buy and sell items with other players. Usage: market [search] [page]")
    async def market(self, ctx: commands.Context, *, search: str = ""):
        await self.show_market(ctx, search)

    async def show_market(self, ctx: commands.Context, search: str):
        e = emoji_manager.get
        query, page = split_page(search)
        data = await trade.browse_market(query, page, time.time())
        if not data["rows"]:
            text = "Nothing is for sale" + (f" matching **{query}**" if query else "") + f". List something with `{ctx.clean_prefix}market sell`."
            return await ctx.send(view=info_layout(f"{e('ecoin')} Marketplace", text))
        lines = [await self.listing_line(row) for row in data["rows"]]
        lines.append(f"\n-# Page {data['page']}/{data['pages']} · {data['total']} listings · Buy with `{ctx.clean_prefix}market buy <id> [amount]` · {settings.MARKET_FEE_PCT}% fee is taken from the seller")
        await ctx.send(view=info_layout(f"{e('ecoin')} Marketplace", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @market.command(name="browse", aliases=["list", "search", "find"], help="Browse listings. Usage: market browse [search] [page]")
    async def market_browse(self, ctx: commands.Context, *, search: str = ""):
        await self.show_market(ctx, search)

    @market.command(name="sell", aliases=["add", "post"], help="List an item. Usage: market sell <item> <amount> <price each>  or  market sell #<weapon id> <price>")
    async def market_sell(self, ctx: commands.Context, item: str, first: str = "", second: str = ""):
        e = emoji_manager.get
        key = trade.resolve(item)
        if key is not None and key.startswith("w:"):
            qty, price = 1, trade.parse_amount(first)
        else:
            qty, price = trade.parse_amount(first), trade.parse_amount(second)
        if price is None or qty is None:
            return await ctx.send(view=error_layout("Usage", f"`{ctx.clean_prefix}market sell <item> <amount> <price each>`, for example `market sell \"demon core\" 10 150`.\nFor a crafted weapon: `market sell #12 5000`."))
        result = await trade.list_item(ctx.author.id, key, qty, price, time.time())
        if not result["ok"]:
            return await ctx.send(view=self.failure(result["reason"], **{k: v for k, v in result.items() if k == "limit"}))
        label = await trade.describe(key)
        what = label if key.startswith("w:") else f"**{label}** x{qty}"
        await ctx.send(view=success_layout(f"{e('ecoin')} Listed", f"Listing `#{result['id']}`: {what} for **{stones.fmt(price * qty)}**.\nWhen it sells you receive **{stones.fmt(result['net'])}** after the {settings.MARKET_FEE_PCT}% marketplace fee ({stones.fmt(result['fee'])}). It expires {stamp(result['expires_at'])}."))

    @market.command(name="buy", aliases=["purchase"], help="Buy a listing. Usage: market buy <id> [amount]")
    async def market_buy(self, ctx: commands.Context, listing_id: int, amount: int = 1):
        e = emoji_manager.get
        result = await trade.buy(ctx.author.id, listing_id, amount, time.time())
        if not result["ok"]:
            return await ctx.send(view=self.failure(result["reason"], **{k: v for k, v in result.items() if k in ("total",)}))
        label = await trade.describe(result["item"])
        what = label if result["item"].startswith("w:") else f"**{label}** x{result['qty']}"
        await ctx.send(view=success_layout(f"{e('ecoin')} Bought", f"You bought {what} for **{stones.fmt(result['total'])}**. It is in your bag."))
        await self.dm(result["seller_id"], f"{ctx.author.display_name} bought {what} from your listing #{listing_id}. After the {settings.MARKET_FEE_PCT}% fee you received **{stones.fmt(result['net'])}**.")

    @market.command(name="mine", aliases=["my", "listings"], help="See your own listings.")
    async def market_mine(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await trade.my_market(ctx.author.id)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('ecoin')} Your listings", "You have nothing listed."))
        lines = [await self.listing_line(row) for row in rows]
        lines.append(f"\n-# Cancel with `{ctx.clean_prefix}market cancel <id>`")
        await ctx.send(view=info_layout(f"{e('ecoin')} Your listings", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @market.command(name="cancel", aliases=["remove", "delist"], help="Cancel a listing and take the items back. Usage: market cancel <id>")
    async def market_cancel(self, ctx: commands.Context, listing_id: int):
        result = await trade.cancel_market(ctx.author.id, listing_id)
        if not result["ok"]:
            return await ctx.send(view=self.failure(result["reason"]))
        await ctx.send(view=success_layout("Listing cancelled", "Your items are back in your bag. Cancelling is free."))

    @market.command(name="fees", aliases=["fee", "info"], help="See how the marketplace and auctions work.")
    async def market_fees(self, ctx: commands.Context):
        e = emoji_manager.get
        text = (
            f"**Marketplace:** fixed prices. List up to {settings.MARKET_MAX_LISTINGS} items for {settings.MARKET_DAYS} days. A **{settings.MARKET_FEE_PCT}%** fee is taken from the seller when something sells.\n"
            f"**Auction house:** `{ctx.clean_prefix}auction`. Up to {settings.AUCTION_MAX} at once, lasting {settings.AUCTION_MIN_HOURS} to {settings.AUCTION_MAX_HOURS} hours. A **{settings.AUCTION_FEE_PCT}%** fee is taken from the final price. Bids in the last {settings.AUCTION_SNIPE_SECONDS // 60} minutes extend the auction, and each bid must beat the last by {settings.AUCTION_RAISE_PCT}%.\n"
            "Buying costs no fee, listing is free, and cancelling or an unsold item costs nothing.\n"
            "You can sell pills, materials, armor, charms and crafted weapons (which keep their quality and durability). Soul-bound weapons and story relics can never be traded."
        )
        await ctx.send(view=info_layout(f"{e('ecoin')} Trading", text))

    @commands.group(name="auction", aliases=["ah", "auctions"], invoke_without_command=True, help="Bid on player auctions. Usage: auction [search] [page]")
    async def auction(self, ctx: commands.Context, *, search: str = ""):
        await self.show_auctions(ctx, search)

    async def show_auctions(self, ctx: commands.Context, search: str):
        e = emoji_manager.get
        query, page = split_page(search)
        data = await trade.browse_auctions(query, page, time.time())
        if not data["rows"]:
            return await ctx.send(view=info_layout(f"{e('ecoin')} Auction house", "No auctions are running" + (f" for **{query}**" if query else "") + f". Start one with `{ctx.clean_prefix}auction create`."))
        lines = [await self.listing_line(row, True) for row in data["rows"]]
        lines.append(f"\n-# Page {data['page']}/{data['pages']} · Bid with `{ctx.clean_prefix}auction bid <id> <amount>` · {settings.AUCTION_FEE_PCT}% fee is taken from the seller")
        await ctx.send(view=info_layout(f"{e('ecoin')} Auction house", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @auction.command(name="list", aliases=["browse", "search"], help="Browse auctions. Usage: auction list [search] [page]")
    async def auction_list(self, ctx: commands.Context, *, search: str = ""):
        await self.show_auctions(ctx, search)

    @auction.command(name="view", aliases=["show", "details"], help="See one auction. Usage: auction view <id>")
    async def auction_view(self, ctx: commands.Context, auction_id: int):
        e = emoji_manager.get
        row = await trade.get_auction(auction_id)
        if row is None:
            return await ctx.send(view=self.failure("gone"))
        label = await trade.describe(row["item"])
        what = label if row["item"].startswith("w:") else f"**{label}** x{row['qty']}"
        lines = [what, f"Seller: <@{row['seller_id']}>"]
        if row["bids"]:
            lines.append(f"Current bid: **{stones.fmt(row['bid'])}** by <@{row['bidder_id']}> ({row['bids']} bids)")
        else:
            lines.append(f"Starting price: **{stones.fmt(row['start_price'])}** · no bids yet")
        if row["status"] == "open":
            lines.append(f"Next bid: at least **{stones.fmt(trade.min_bid(row))}**")
        if row["buyout"]:
            lines.append(f"Buyout: **{stones.fmt(row['buyout'])}**")
        lines.append(("Ends " if row["status"] == "open" else "Ended ") + stamp(row["ends_at"]))
        await ctx.send(view=info_layout(f"{e('ecoin')} Auction #{auction_id}", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @auction.command(name="create", aliases=["start", "sell", "new"], help="Start an auction. Usage: auction create <item> <amount> <start price> [hours] [buyout]  or  auction create #<weapon id> <start price> [hours] [buyout]")
    async def auction_create(self, ctx: commands.Context, item: str, a: str = "", b: str = "", c: str = "", d: str = ""):
        e = emoji_manager.get
        key = trade.resolve(item)
        if key is not None and key.startswith("w:"):
            qty, rest = 1, [a, b, c]
        else:
            qty, rest = trade.parse_amount(a), [b, c, d]
        start = trade.parse_amount(rest[0])
        hours = int(rest[1]) if rest[1].isdigit() else (settings.AUCTION_DEFAULT_HOURS if not rest[1] else -1)
        buyout = trade.parse_amount(rest[2]) if rest[2] else 0
        if qty is None or start is None or buyout is None:
            return await ctx.send(view=error_layout("Usage", f"`{ctx.clean_prefix}auction create <item> <amount> <start price> [hours] [buyout]`, for example `auction create \"demon core\" 10 1000 24 5000`.\nFor a crafted weapon: `auction create #12 2000 24 10k`."))
        result = await trade.create_auction(ctx.author.id, key, qty, start, hours, buyout, time.time())
        if not result["ok"]:
            return await ctx.send(view=self.failure(result["reason"], **{k: v for k, v in result.items() if k == "limit"}))
        label = await trade.describe(key)
        what = label if key.startswith("w:") else f"**{label}** x{qty}"
        extra = f" Buyout **{stones.fmt(buyout)}**." if buyout else ""
        await ctx.send(view=success_layout(f"{e('ecoin')} Auction started", f"Auction `#{result['id']}`: {what}, starting at **{stones.fmt(start)}**.{extra}\nIt ends {stamp(result['ends_at'])}. A {settings.AUCTION_FEE_PCT}% fee is taken from the final price."))

    @auction.command(name="bid", aliases=["offer"], help="Bid on an auction. Usage: auction bid <id> <amount>")
    async def auction_bid(self, ctx: commands.Context, auction_id: int, amount: str):
        e = emoji_manager.get
        value = trade.parse_amount(amount)
        if value is None:
            return await ctx.send(view=error_layout("Bad amount", "Write a whole number of spirit stones, such as `1500`, `2k` or `3mid`."))
        result = await trade.bid(ctx.author.id, auction_id, value, time.time())
        if not result["ok"]:
            return await ctx.send(view=self.failure(result["reason"], **{k: v for k, v in result.items() if k in ("min", "amount")}))
        label = await trade.describe(result["item"])
        what = label if result["item"].startswith("w:") else f"**{label}** x{result['qty']}"
        if result.get("bought"):
            await ctx.send(view=success_layout(f"{e('ecoin')} Bought out", f"You bought out auction `#{auction_id}`: {what} for **{stones.fmt(result['price'])}**. It is in your bag."))
            await self.dm(result["seller_id"], f"Your auction #{auction_id} was bought out: {what} for **{stones.fmt(result['price'])}**. After the {settings.AUCTION_FEE_PCT}% fee you received **{stones.fmt(result['net'])}**.")
        else:
            extended = " The auction was extended by the last-minute bid." if result["extended"] else ""
            await ctx.send(view=success_layout(f"{e('ecoin')} Bid placed", f"You lead auction `#{auction_id}` with **{stones.fmt(result['amount'])}**. It ends {stamp(result['ends_at'])}.{extended}\nIf someone outbids you, your spirit stones are returned at once."))
        if result.get("outbid"):
            await self.dm(result["outbid"], f"You were outbid on auction #{auction_id} ({what}). Your spirit stones were returned.")

    @auction.command(name="buyout", aliases=["buynow"], help="Pay the buyout price. Usage: auction buyout <id>")
    async def auction_buyout(self, ctx: commands.Context, auction_id: int):
        e = emoji_manager.get
        result = await trade.buyout(ctx.author.id, auction_id, time.time())
        if not result["ok"]:
            return await ctx.send(view=self.failure(result["reason"], **{k: v for k, v in result.items() if k == "amount"}))
        label = await trade.describe(result["item"])
        what = label if result["item"].startswith("w:") else f"**{label}** x{result['qty']}"
        await ctx.send(view=success_layout(f"{e('ecoin')} Bought out", f"You bought out auction `#{auction_id}`: {what} for **{stones.fmt(result['price'])}**. It is in your bag."))
        await self.dm(result["seller_id"], f"Your auction #{auction_id} was bought out: {what} for **{stones.fmt(result['price'])}**. After the {settings.AUCTION_FEE_PCT}% fee you received **{stones.fmt(result['net'])}**.")
        if result.get("outbid"):
            await self.dm(result["outbid"], f"You were outbid on auction #{auction_id} ({what}) by a buyout. Your spirit stones were returned.")

    @auction.command(name="mine", aliases=["my", "active"], help="See auctions you started or are bidding on.")
    async def auction_mine(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await trade.my_auctions(ctx.author.id)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('ecoin')} Your auctions", "You are not selling or bidding on anything."))
        lines = []
        for row in rows:
            role = "selling" if row["seller_id"] == ctx.author.id else ("winning" if row["bidder_id"] == ctx.author.id else "bidding")
            lines.append(f"{await self.listing_line(row, True)} · *{role}*")
        await ctx.send(view=info_layout(f"{e('ecoin')} Your auctions", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @auction.command(name="cancel", aliases=["remove"], help="Cancel your auction if it has no bids. Usage: auction cancel <id>")
    async def auction_cancel(self, ctx: commands.Context, auction_id: int):
        result = await trade.cancel_auction(ctx.author.id, auction_id)
        if not result["ok"]:
            return await ctx.send(view=self.failure(result["reason"]))
        await ctx.send(view=success_layout("Auction cancelled", "Your items are back in your bag."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Marketplace(bot))
