import re
from typing import Optional

from rpg import engine, gear, schema, settings, stones
from utils import coins, db

WEAPON_REF = re.compile(r"^(?:#|w:?)(\d+)$", re.IGNORECASE)


def fee_for(total: int, pct: int) -> int:
    return max(1, total * pct // 100) if total > 0 else 0


def parse_amount(text: str) -> Optional[int]:
    text = (text or "").strip().lower().replace(",", "").replace("_", "")
    stones_value = stones.parse(text)
    if stones_value is not None:
        return stones_value if stones_value >= 1 else None
    match = re.fullmatch(r"(\d+(?:\.\d+)?)([kmb]?)", text)
    if not match:
        return None
    value = float(match.group(1)) * {"": 1, "k": 1_000, "m": 1_000_000, "b": 1_000_000_000}[match.group(2)]
    return int(value) if value >= 1 else None


def tradable_key(key: str) -> bool:
    if key in settings.ITEMS or key in settings.BREWS or key in gear.MATERIALS:
        return True
    parsed = gear.parse(key)
    return bool(parsed) and not gear.soulbound(key) and not engine.LEGACY_WEAPON.match(key)


def find_key(text: str) -> Optional[str]:
    text = text.strip().lower().replace("-", " ")
    flat = text.replace(" ", "_")
    tables = (settings.ITEMS, settings.BREWS, gear.MATERIALS)
    for table in tables:
        for key, info in table.items():
            if flat in (key, info["name"].lower().replace(" ", "_")):
                return key
    matches = [key for table in tables for key, info in table.items() if flat in key or flat in info["name"].lower().replace(" ", "_")]
    if len(set(matches)) == 1:
        return matches[0]
    return gear.find(text)


def resolve(text: str) -> Optional[str]:
    match = WEAPON_REF.match(text.strip())
    if match:
        return f"w:{int(match.group(1))}"
    return find_key(text)


async def describe(item: str) -> str:
    if item.startswith("w:"):
        row = await engine.weapon_row(int(item[2:]))
        return f"{gear.weapon_line(row)} (weapon #{item[2:]})" if row else f"Weapon #{item[2:]} (gone)"
    if item in settings.ITEMS:
        return settings.ITEMS[item]["name"]
    if item in settings.BREWS:
        return settings.BREWS[item]["name"]
    if item in gear.MATERIALS:
        return gear.MATERIALS[item]["name"]
    return gear.name(item)


async def escrow(user_id: int, item: str, qty: int) -> bool:
    if item.startswith("w:"):
        cursor = await db.raw_execute("UPDATE cult_weapons SET listed=1 WHERE weapon_id=? AND owner_id=? AND equipped=0 AND listed=0", (int(item[2:]), user_id))
        return getattr(cursor, "rowcount", 0) > 0
    cursor = await db.raw_execute("UPDATE cult_items SET qty=qty-? WHERE user_id=? AND item=? AND qty>=?", (qty, user_id, item, qty))
    return getattr(cursor, "rowcount", 0) > 0


async def give_back(user_id: int, item: str, qty: int) -> None:
    if item.startswith("w:"):
        await db.raw_execute("UPDATE cult_weapons SET listed=0 WHERE weapon_id=? AND owner_id=?", (int(item[2:]), user_id))
    elif qty > 0:
        await engine.add_item(user_id, item, qty)


async def deliver(user_id: int, item: str, qty: int) -> None:
    if item.startswith("w:"):
        await db.raw_execute("UPDATE cult_weapons SET owner_id=?, listed=0, equipped=0 WHERE weapon_id=?", (user_id, int(item[2:])))
    else:
        await engine.add_item(user_id, item, qty)


def check_item(item: Optional[str], qty: int) -> Optional[str]:
    if item is None:
        return "item"
    if not item.startswith("w:") and gear.soulbound(item):
        return "bound"
    if not item.startswith("w:") and not tradable_key(item):
        return "item"
    if item.startswith("w:") and qty != 1:
        return "qty"
    if not 1 <= qty <= settings.MARKET_MAX_QTY:
        return "qty"
    return None


async def list_item(seller_id: int, item: Optional[str], qty: int, price: int, now: float) -> dict:
    await schema.ensure()
    bad = check_item(item, qty)
    if bad:
        return {"ok": False, "reason": bad}
    if not 1 <= price <= settings.MARKET_MAX_PRICE:
        return {"ok": False, "reason": "price"}
    row = await db.raw_fetchone("SELECT COUNT(*) AS n FROM market_listings WHERE seller_id=? AND status='open'", (seller_id,))
    if row["n"] >= settings.MARKET_MAX_LISTINGS:
        return {"ok": False, "reason": "limit", "limit": settings.MARKET_MAX_LISTINGS}
    if not await escrow(seller_id, item, qty):
        return {"ok": False, "reason": "missing"}
    cursor = await db.raw_execute(
        "INSERT INTO market_listings (seller_id, item, qty, price, created_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, 'open')",
        (seller_id, item, qty, price, now, now + settings.MARKET_DAYS * 86400))
    total = price * qty
    fee = fee_for(total, settings.MARKET_FEE_PCT)
    return {"ok": True, "id": cursor.lastrowid, "item": item, "qty": qty, "price": price, "fee": fee, "net": total - fee, "expires_at": now + settings.MARKET_DAYS * 86400}


async def expire_market(now: float) -> list:
    await schema.ensure()
    rows = await db.raw_fetch("SELECT * FROM market_listings WHERE status='open' AND expires_at<=?", (now,))
    out = []
    for row in rows:
        cursor = await db.raw_execute("UPDATE market_listings SET status='expired' WHERE listing_id=? AND status='open'", (row["listing_id"],))
        if getattr(cursor, "rowcount", 0) <= 0:
            continue
        current = await db.raw_fetchone("SELECT qty FROM market_listings WHERE listing_id=?", (row["listing_id"],))
        await give_back(row["seller_id"], row["item"], int(current["qty"]))
        out.append({"seller_id": row["seller_id"], "item": row["item"], "qty": int(current["qty"]), "id": row["listing_id"], "kind": "market"})
    return out


async def browse_market(query: str, page: int, now: float) -> dict:
    await expire_market(now)
    rows = [dict(r) for r in await db.raw_fetch("SELECT * FROM market_listings WHERE status='open' AND expires_at>? ORDER BY price ASC, listing_id ASC", (now,))]
    needle = query.strip().lower()
    if needle:
        wanted = resolve(needle)
        rows = [r for r in rows if (wanted and r["item"] == wanted) or needle in (await describe(r["item"])).lower()]
    pages = max(1, -(-len(rows) // settings.TRADE_PAGE))
    page = min(max(1, page), pages)
    return {"rows": rows[(page - 1) * settings.TRADE_PAGE: page * settings.TRADE_PAGE], "page": page, "pages": pages, "total": len(rows)}


async def my_market(user_id: int) -> list:
    return [dict(r) for r in await db.raw_fetch("SELECT * FROM market_listings WHERE seller_id=? AND status='open' ORDER BY listing_id", (user_id,))]


async def buy(buyer_id: int, listing_id: int, qty: int, now: float) -> dict:
    await schema.ensure()
    row = await db.raw_fetchone("SELECT * FROM market_listings WHERE listing_id=?", (listing_id,))
    if row is None or row["status"] != "open" or row["expires_at"] <= now:
        return {"ok": False, "reason": "gone"}
    if row["seller_id"] == buyer_id:
        return {"ok": False, "reason": "own"}
    if qty < 1 or qty > row["qty"]:
        return {"ok": False, "reason": "qty", "have": row["qty"]}
    cursor = await db.raw_execute("UPDATE market_listings SET qty=qty-? WHERE listing_id=? AND status='open' AND qty>=? AND expires_at>?", (qty, listing_id, qty, now))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "gone"}
    await db.raw_execute("UPDATE market_listings SET status='sold' WHERE listing_id=? AND qty=0", (listing_id,))
    total = row["price"] * qty
    if not await coins.spend(buyer_id, total):
        await db.raw_execute("UPDATE market_listings SET qty=qty+?, status='open' WHERE listing_id=?", (qty, listing_id))
        return {"ok": False, "reason": "coins", "total": total}
    fee = fee_for(total, settings.MARKET_FEE_PCT)
    await coins.add(row["seller_id"], total - fee)
    await deliver(buyer_id, row["item"], qty)
    return {"ok": True, "item": row["item"], "qty": qty, "total": total, "fee": fee, "seller_id": row["seller_id"], "net": total - fee, "left": row["qty"] - qty}


async def cancel_market(user_id: int, listing_id: int) -> dict:
    cursor = await db.raw_execute("UPDATE market_listings SET status='cancelled' WHERE listing_id=? AND seller_id=? AND status='open'", (listing_id, user_id))
    if getattr(cursor, "rowcount", 0) <= 0:
        return {"ok": False, "reason": "gone"}
    row = await db.raw_fetchone("SELECT * FROM market_listings WHERE listing_id=?", (listing_id,))
    await give_back(user_id, row["item"], int(row["qty"]))
    return {"ok": True, "item": row["item"], "qty": int(row["qty"])}


def min_bid(row: dict) -> int:
    if row["bids"] <= 0:
        return row["start_price"]
    return row["bid"] + max(1, row["bid"] * settings.AUCTION_RAISE_PCT // 100)


async def create_auction(seller_id: int, item: Optional[str], qty: int, start: int, hours: int, buyout: int, now: float) -> dict:
    await schema.ensure()
    bad = check_item(item, qty)
    if bad:
        return {"ok": False, "reason": bad}
    if not 1 <= start <= settings.MARKET_MAX_PRICE or buyout < 0 or buyout > settings.MARKET_MAX_PRICE or (buyout and buyout <= start):
        return {"ok": False, "reason": "price"}
    if not settings.AUCTION_MIN_HOURS <= hours <= settings.AUCTION_MAX_HOURS:
        return {"ok": False, "reason": "hours"}
    row = await db.raw_fetchone("SELECT COUNT(*) AS n FROM auctions WHERE seller_id=? AND status='open'", (seller_id,))
    if row["n"] >= settings.AUCTION_MAX:
        return {"ok": False, "reason": "limit", "limit": settings.AUCTION_MAX}
    if not await escrow(seller_id, item, qty):
        return {"ok": False, "reason": "missing"}
    ends = now + hours * 3600
    cursor = await db.raw_execute(
        "INSERT INTO auctions (seller_id, item, qty, start_price, buyout, bid, bidder_id, bids, created_at, ends_at, status) VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, ?, 'open')",
        (seller_id, item, qty, start, buyout, now, ends))
    return {"ok": True, "id": cursor.lastrowid, "item": item, "qty": qty, "start": start, "buyout": buyout, "ends_at": ends}


async def get_auction(auction_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM auctions WHERE auction_id=?", (auction_id,))
    return dict(row) if row else None


async def browse_auctions(query: str, page: int, now: float) -> dict:
    await settle_due(now)
    rows = [dict(r) for r in await db.raw_fetch("SELECT * FROM auctions WHERE status='open' AND ends_at>? ORDER BY ends_at ASC", (now,))]
    needle = query.strip().lower()
    if needle:
        wanted = resolve(needle)
        rows = [r for r in rows if (wanted and r["item"] == wanted) or needle in (await describe(r["item"])).lower()]
    pages = max(1, -(-len(rows) // settings.TRADE_PAGE))
    page = min(max(1, page), pages)
    return {"rows": rows[(page - 1) * settings.TRADE_PAGE: page * settings.TRADE_PAGE], "page": page, "pages": pages, "total": len(rows)}


async def my_auctions(user_id: int) -> list:
    return [dict(r) for r in await db.raw_fetch("SELECT * FROM auctions WHERE (seller_id=? OR bidder_id=?) AND status='open' ORDER BY ends_at", (user_id, user_id))]


async def pay_out(row: dict) -> dict:
    fee = fee_for(row["bid"], settings.AUCTION_FEE_PCT)
    await coins.add(row["seller_id"], row["bid"] - fee)
    await deliver(row["bidder_id"], row["item"], row["qty"])
    return {"kind": "auction", "sold": True, "id": row["auction_id"], "item": row["item"], "qty": row["qty"], "seller_id": row["seller_id"], "winner_id": row["bidder_id"], "price": row["bid"], "fee": fee, "net": row["bid"] - fee}


async def settle_one(auction_id: int) -> Optional[dict]:
    cursor = await db.raw_execute("UPDATE auctions SET status='done' WHERE auction_id=? AND status='open'", (auction_id,))
    if getattr(cursor, "rowcount", 0) <= 0:
        return None
    row = dict(await db.raw_fetchone("SELECT * FROM auctions WHERE auction_id=?", (auction_id,)))
    if row["bids"] > 0 and row["bidder_id"]:
        return await pay_out(row)
    await give_back(row["seller_id"], row["item"], row["qty"])
    return {"kind": "auction", "sold": False, "id": row["auction_id"], "item": row["item"], "qty": row["qty"], "seller_id": row["seller_id"]}


async def settle_due(now: float) -> list:
    await schema.ensure()
    rows = await db.raw_fetch("SELECT auction_id FROM auctions WHERE status='open' AND ends_at<=?", (now,))
    out = []
    for row in rows:
        result = await settle_one(row["auction_id"])
        if result:
            out.append(result)
    return out


async def bid(bidder_id: int, auction_id: int, amount: int, now: float) -> dict:
    await schema.ensure()
    row = await get_auction(auction_id)
    if row is None or row["status"] != "open" or row["ends_at"] <= now:
        return {"ok": False, "reason": "gone"}
    if row["seller_id"] == bidder_id:
        return {"ok": False, "reason": "own"}
    if row["buyout"] and amount >= row["buyout"]:
        return await buyout(bidder_id, auction_id, now)
    needed = min_bid(row)
    if amount < needed:
        return {"ok": False, "reason": "low", "min": needed}
    if amount > settings.MARKET_MAX_PRICE:
        return {"ok": False, "reason": "price"}
    if not await coins.spend(bidder_id, amount):
        return {"ok": False, "reason": "coins", "amount": amount}
    ends = now + settings.AUCTION_SNIPE_SECONDS if row["ends_at"] - now < settings.AUCTION_SNIPE_SECONDS else row["ends_at"]
    cursor = await db.raw_execute(
        "UPDATE auctions SET bid=?, bidder_id=?, bids=bids+1, ends_at=? WHERE auction_id=? AND status='open' AND bid=? AND bidder_id=? AND ends_at>?",
        (amount, bidder_id, ends, auction_id, row["bid"], row["bidder_id"], now))
    if getattr(cursor, "rowcount", 0) <= 0:
        await coins.add(bidder_id, amount)
        return {"ok": False, "reason": "race"}
    if row["bidder_id"] and row["bid"] > 0:
        await coins.add(row["bidder_id"], row["bid"])
    return {"ok": True, "amount": amount, "ends_at": ends, "extended": ends != row["ends_at"], "outbid": row["bidder_id"] if row["bidder_id"] != bidder_id else 0, "item": row["item"], "qty": row["qty"]}


async def buyout(bidder_id: int, auction_id: int, now: float) -> dict:
    await schema.ensure()
    row = await get_auction(auction_id)
    if row is None or row["status"] != "open" or row["ends_at"] <= now:
        return {"ok": False, "reason": "gone"}
    if row["seller_id"] == bidder_id:
        return {"ok": False, "reason": "own"}
    if not row["buyout"]:
        return {"ok": False, "reason": "nobuyout"}
    if not await coins.spend(bidder_id, row["buyout"]):
        return {"ok": False, "reason": "coins", "amount": row["buyout"]}
    cursor = await db.raw_execute(
        "UPDATE auctions SET bid=?, bidder_id=?, bids=bids+1, status='done' WHERE auction_id=? AND status='open' AND bid=? AND bidder_id=? AND ends_at>?",
        (row["buyout"], bidder_id, auction_id, row["bid"], row["bidder_id"], now))
    if getattr(cursor, "rowcount", 0) <= 0:
        await coins.add(bidder_id, row["buyout"])
        return {"ok": False, "reason": "race"}
    previous = row["bidder_id"]
    if previous and row["bid"] > 0:
        await coins.add(previous, row["bid"])
    row.update({"bid": row["buyout"], "bidder_id": bidder_id})
    result = await pay_out(row)
    return {"ok": True, "bought": True, **result, "outbid": previous if previous != bidder_id else 0}


async def cancel_auction(user_id: int, auction_id: int) -> dict:
    cursor = await db.raw_execute("UPDATE auctions SET status='cancelled' WHERE auction_id=? AND seller_id=? AND status='open' AND bids=0", (auction_id, user_id))
    if getattr(cursor, "rowcount", 0) <= 0:
        row = await get_auction(auction_id)
        return {"ok": False, "reason": "bids" if row and row["seller_id"] == user_id and row["status"] == "open" else "gone"}
    row = await get_auction(auction_id)
    await give_back(user_id, row["item"], row["qty"])
    return {"ok": True, "item": row["item"], "qty": row["qty"]}
