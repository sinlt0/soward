import asyncio
import json
import math
import secrets
import time
import uuid
from dataclasses import dataclass
from typing import Optional

import aiohttp

import config
from utils import coins as coin_store, db, hdwallet, prefix as prefix_utils, supporters

UNITS = 100_000_000
OPEN_STATES = ("pending", "seen")
LIVE_STATES = ("pending", "seen", "expired", "review")
TIMEOUT = aiohttp.ClientTimeout(total=15)
RATE_TTL = 60
COOLDOWN = 120

_lock = asyncio.Lock()
_rates: dict[str, tuple[float, float]] = {}
_cooldowns: dict[str, float] = {}


class PayError(Exception):
    pass


@dataclass
class Tx:
    txid: str
    units: int
    confirmations: int


def fmt_amount(units: int) -> str:
    return f"{units / UNITS:.8f}".rstrip("0").rstrip(".") if units else "0"


def plan_for(key: str) -> Optional[dict]:
    if key.startswith("tip:"):
        try:
            amount = round(float(key[4:]), 2)
        except ValueError:
            return None
        if not config.SUPPORT_MIN_USD <= amount <= config.SUPPORT_MAX_USD:
            return None
        return {"label": f"${amount:g} tip", "days": None, "usd": amount, "key": key}
    if key.startswith("coins:"):
        try:
            amount = round(float(key[6:]), 2)
        except ValueError:
            return None
        if not config.COIN_TOPUP_MIN_USD <= amount <= config.COIN_TOPUP_MAX_USD:
            return None
        return {"label": f"{coin_store.fmt(coin_store.usd_to_diamonds(amount))} diamonds", "days": None, "usd": amount, "key": key}
    plan = config.CRYPTO_PLANS.get(key) or config.CRYPTO_LEGACY_PLANS.get(key)
    return dict(plan, key=key) if plan else None


async def get_xpub(coin: str) -> Optional[str]:
    return await db.get("crypto_pay", f"xpub_{coin}")


async def set_xpub(coin: str, xpub: Optional[str]) -> None:
    if xpub is None:
        await db.set("crypto_pay", f"xpub_{coin}", "")
    else:
        await db.set("crypto_pay", f"xpub_{coin}", xpub)


async def enabled_coins() -> list[str]:
    return [coin for coin in config.CRYPTO_COINS if await get_xpub(coin)]


async def log_channel() -> Optional[int]:
    value = await db.get("crypto_pay", "log_channel")
    return int(value) if value else None


async def set_log_channel(channel_id: Optional[int]) -> None:
    await db.set("crypto_pay", "log_channel", channel_id or 0)


async def _fetch_json(session: aiohttp.ClientSession, url: str, host: str):
    if _cooldowns.get(host, 0) > time.time():
        return None
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            if resp.status in (402, 429, 430):
                _cooldowns[host] = time.time() + COOLDOWN
                return None
            if resp.status != 200:
                return None
            return await resp.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
        return None


async def _fetch_text(session: aiohttp.ClientSession, url: str, host: str) -> Optional[str]:
    if _cooldowns.get(host, 0) > time.time():
        return None
    try:
        async with session.get(url, timeout=TIMEOUT) as resp:
            if resp.status in (402, 429, 430):
                _cooldowns[host] = time.time() + COOLDOWN
                return None
            if resp.status != 200:
                return None
            return (await resp.text()).strip()
    except (aiohttp.ClientError, asyncio.TimeoutError):
        return None


async def _esplora(session: aiohttp.ClientSession, base: str, address: str) -> Optional[list[Tx]]:
    host = base.split("/")[2]
    tip_text = await _fetch_text(session, f"{base}/blocks/tip/height", host)
    data = await _fetch_json(session, f"{base}/address/{address}/txs", host)
    if data is None or not isinstance(data, list) or not tip_text or not tip_text.isdigit():
        return None
    tip = int(tip_text)
    out = []
    for tx in data:
        units = sum(int(o.get("value", 0)) for o in tx.get("vout", []) if o.get("scriptpubkey_address") == address)
        if units <= 0:
            continue
        status = tx.get("status") or {}
        conf = tip - int(status["block_height"]) + 1 if status.get("confirmed") and status.get("block_height") else 0
        out.append(Tx(str(tx["txid"]), units, max(0, conf)))
    return out


async def _blockcypher(session: aiohttp.ClientSession, base: str, address: str) -> Optional[list[Tx]]:
    host = base.split("/")[2]
    token = f"&token={config.BLOCKCYPHER_TOKEN}" if config.BLOCKCYPHER_TOKEN else ""
    data = await _fetch_json(session, f"{base}/addrs/{address}/full?limit=50{token}", host)
    if not isinstance(data, dict):
        return None
    out = []
    for tx in data.get("txs", []):
        units = sum(int(o.get("value", 0)) for o in tx.get("outputs", []) if address in (o.get("addresses") or []))
        if units > 0:
            out.append(Tx(str(tx["hash"]), units, int(tx.get("confirmations", 0))))
    return out


async def _blockchair(session: aiohttp.ClientSession, base: str, address: str) -> Optional[list[Tx]]:
    host = base.split("/")[2]
    data = await _fetch_json(session, f"{base}/dashboards/address/{address}?transaction_details=true&limit=50", host)
    if not isinstance(data, dict) or not isinstance(data.get("data"), dict):
        return None
    entry = data["data"].get(address)
    if not isinstance(entry, dict):
        return None
    try:
        tip = int((data.get("context") or {}).get("state"))
    except (TypeError, ValueError):
        return None
    out = []
    for tx in entry.get("transactions") or []:
        if not isinstance(tx, dict) or not tx.get("hash"):
            continue
        units = int(tx.get("balance_change") or 0)
        if units <= 0:
            continue
        block = int(tx.get("block_id") or -1)
        out.append(Tx(str(tx["hash"]), units, tip - block + 1 if block > 0 else 0))
    return out


DRIVERS = {"esplora": _esplora, "blockcypher": _blockcypher, "blockchair": _blockchair}


async def health(session: aiohttp.ClientSession, kind: str, base: str, address: str) -> Optional[int]:
    started = time.time()
    result = await DRIVERS[kind](session, base, address)
    return int((time.time() - started) * 1000) if result is not None else None


async def observe(session: aiohttp.ClientSession, coin: str, address: str) -> list[Optional[list[Tx]]]:
    providers = config.CRYPTO_PROVIDERS.get(coin, [])
    results = await asyncio.gather(*[DRIVERS[kind](session, base, address) for kind, base in providers], return_exceptions=True)
    return [r if isinstance(r, list) else None for r in results]


def consensus(observations: list[Optional[list[Tx]]]) -> tuple[list[Tx], int]:
    responders = [obs for obs in observations if obs is not None]
    need = config.CRYPTO_MIN_AGREE
    if len(responders) < need:
        return [], len(responders)
    reported: dict[str, list[Tx]] = {}
    for obs in responders:
        for tx in obs:
            reported.setdefault(tx.txid, []).append(tx)
    out = []
    for txid, items in reported.items():
        if len(items) < need:
            continue
        out.append(Tx(txid, min(t.units for t in items), min(t.confirmations for t in items)))
    return out, len(responders)


def unconfirmed_hint(observations: list[Optional[list[Tx]]]) -> int:
    best = 0
    for obs in observations:
        if obs:
            best = max(best, sum(t.units for t in obs))
    return best


def evaluate(invoice: dict, txs: list[Tx]) -> dict:
    required = config.CRYPTO_CONFIRMATIONS.get(invoice["coin"], 1)
    received = sum(t.units for t in txs)
    confirmed = sum(t.units for t in txs if t.confirmations >= required)
    need = invoice["amount_units"] * (1 - config.CRYPTO_UNDERPAY_TOLERANCE)
    if confirmed >= need:
        state = "paid"
    elif received > 0:
        state = "seen"
    elif invoice["status"] == "seen":
        state = "pending"
    else:
        state = invoice["status"]
    return {"state": state, "received": received, "confirmed": confirmed, "required": required}


async def fetch_rate(session: aiohttp.ClientSession, coin: str) -> float:
    cached = _rates.get(coin)
    if cached and time.time() - cached[0] < RATE_TTL:
        return cached[1]
    names = {"btc": ("bitcoin", "XBTUSD", "XXBTZUSD"), "ltc": ("litecoin", "LTCUSD", "XLTCZUSD")}[coin]
    values = []
    data = await _fetch_json(session, f"https://api.coingecko.com/api/v3/simple/price?ids={names[0]}&vs_currencies=usd", "coingecko")
    try:
        values.append(float(data[names[0]]["usd"]))
    except (TypeError, KeyError, ValueError):
        pass
    data = await _fetch_json(session, f"https://api.kraken.com/0/public/Ticker?pair={names[1]}", "kraken")
    try:
        result = data["result"]
        values.append(float(next(iter(result.values()))["c"][0]))
    except (TypeError, KeyError, ValueError, StopIteration):
        pass
    values = [v for v in values if v > 0]
    if not values:
        if cached and time.time() - cached[0] < 900:
            return cached[1]
        raise PayError("I could not get a price for that coin right now. Try again in a minute.")
    if len(values) == 2 and abs(values[0] - values[1]) / max(values) > 0.05:
        raise PayError("Price sources disagree right now, so invoices are paused for a few minutes.")
    rate = max(values) if len(values) == 2 else values[0]
    _rates[coin] = (time.time(), rate)
    return rate


def amount_for(usd: float, rate: float) -> int:
    return max(1000, math.ceil(usd / rate * UNITS))


def uri_for(invoice: dict) -> str:
    scheme = "bitcoin" if invoice["coin"] == "btc" else "litecoin"
    return f"{scheme}:{invoice['address']}?amount={fmt_amount(invoice['amount_units'])}"


async def open_count(user_id: int) -> int:
    row = await db.raw_fetchone("SELECT COUNT(*) AS c FROM crypto_invoices WHERE user_id=? AND status IN ('pending','seen') AND expires_at>?", (user_id, time.time()))
    return int(row["c"]) if row else 0


async def create_invoice(session: aiohttp.ClientSession, guild_id: int, user_id: int, plan_key: str, coin: str, kind: str) -> dict:
    plan = plan_for(plan_key)
    xpub = await get_xpub(coin)
    if plan is None or coin not in config.CRYPTO_COINS or not xpub:
        raise PayError("That plan or coin is not available.")
    if await open_count(user_id) >= config.CRYPTO_MAX_OPEN_PER_USER:
        raise PayError(f"You already have {config.CRYPTO_MAX_OPEN_PER_USER} open invoices. Pay or cancel one first.")
    rate = await fetch_rate(session, coin)
    units = amount_for(plan["usd"], rate)
    async with _lock:
        row = await db.raw_fetchone("SELECT COALESCE(MAX(derivation_index), -1) + 1 AS n FROM crypto_invoices WHERE coin=?", (coin,))
        index = int(row["n"])
        try:
            address = hdwallet.derive_address(xpub, coin, index)
        except hdwallet.WalletError as exc:
            raise PayError(str(exc))
        invoice_id = uuid.uuid4().hex[:8].upper()
        now = time.time()
        await db.raw_execute(
            "INSERT INTO crypto_invoices (invoice_id, guild_id, user_id, kind, plan, coin, usd, rate, amount_units, address, derivation_index, status, created_at, expires_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)",
            (invoice_id, guild_id, user_id, kind, plan_key, coin, plan["usd"], rate, units, address, index, now, now + config.CRYPTO_INVOICE_MINUTES * 60))
    return await get_invoice(invoice_id)


async def get_invoice(invoice_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM crypto_invoices WHERE invoice_id=?", (invoice_id.upper(),))
    return dict(row) if row else None


async def watchable() -> list[dict]:
    cutoff = time.time() - config.CRYPTO_GRACE_HOURS * 3600
    rows = await db.raw_fetch("SELECT * FROM crypto_invoices WHERE status IN ('pending','seen','expired') AND expires_at>?", (cutoff,))
    return [dict(r) for r in rows]


async def recent(status: Optional[str] = None, user_id: Optional[int] = None, limit: int = 15) -> list[dict]:
    sql, params = "SELECT * FROM crypto_invoices", []
    clauses = []
    if status:
        clauses.append("status=?")
        params.append(status)
    if user_id:
        clauses.append("user_id=?")
        params.append(user_id)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in await db.raw_fetch(sql, tuple(params))]


async def update(invoice_id: str, **fields) -> None:
    keys = ", ".join(f"{k}=?" for k in fields)
    await db.raw_execute(f"UPDATE crypto_invoices SET {keys} WHERE invoice_id=?", (*fields.values(), invoice_id))


async def remember_message(invoice_id: str, channel_id: int, message_id: int) -> None:
    await update(invoice_id, channel_id=channel_id, message_id=message_id)


async def record_txs(invoice: dict, txs: list[Tx]) -> None:
    for tx in txs:
        await db.raw_execute(
            "INSERT INTO crypto_payments (txid, address, invoice_id, units, confirmations, first_seen) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(txid, address) DO UPDATE SET units=excluded.units, confirmations=excluded.confirmations",
            (tx.txid, invoice["address"], invoice["invoice_id"], tx.units, tx.confirmations, time.time()))


async def payments(invoice_id: str) -> list[dict]:
    return [dict(r) for r in await db.raw_fetch("SELECT * FROM crypto_payments WHERE invoice_id=? ORDER BY first_seen", (invoice_id,))]


def days_for(invoice: dict, received_units: int) -> Optional[int]:
    plan = plan_for(invoice["plan"])
    if plan is None or plan["days"] is None:
        return None
    ratio = min(received_units / invoice["amount_units"], 12.0)
    return max(1, int(plan["days"] * ratio))


async def grant_server(guild_id: int, days: Optional[int]) -> Optional[float]:
    row = await db.raw_fetchone("SELECT premium, premium_expires_at FROM guilds WHERE guild_id=?", (guild_id,))
    now = time.time()
    if row and row["premium"] and row["premium_expires_at"] is None:
        return None
    if days is None:
        expires = None
    else:
        base = now
        if row and row["premium"] and row["premium_expires_at"] and row["premium_expires_at"] > now:
            base = row["premium_expires_at"]
        expires = base + days * 86400
    await db.raw_execute(
        "INSERT INTO guilds (guild_id, premium, premium_expires_at) VALUES (?, 1, ?)"
        " ON CONFLICT(guild_id) DO UPDATE SET premium=1, premium_expires_at=excluded.premium_expires_at",
        (guild_id, expires))
    prefix_utils.invalidate_premium_cache(guild_id)
    return expires


async def create_key(days: Optional[int], label: str, user_id: int) -> str:
    part = lambda: secrets.token_hex(4).upper()
    key = f"ZYRO-{part()}-{part()}-{part()}"
    await db.raw_execute(
        "INSERT INTO premium_keys (key_id, duration_days, duration_label, used, created_by, created_at) VALUES (?, ?, ?, 0, ?, ?)",
        (key, days if days is not None else 36500, label, user_id, time.time()))
    return key


async def settle(invoice_id: str, received_units: int, confirmed_units: int, approved_by: Optional[int] = None) -> Optional[dict]:
    async with _lock:
        invoice = await get_invoice(invoice_id)
        if invoice is None or invoice["status"] not in LIVE_STATES:
            return None
        cursor = await db.raw_execute(
            "UPDATE crypto_invoices SET status='paid', received_units=?, confirmed_units=?, paid_at=? WHERE invoice_id=? AND status IN ('pending','seen','expired','review')",
            (received_units, confirmed_units, time.time(), invoice["invoice_id"]))
        if getattr(cursor, "rowcount", 1) == 0:
            return None
        plan = plan_for(invoice["plan"])
        days = days_for(invoice, max(confirmed_units, received_units) if approved_by else confirmed_units)
        if invoice["kind"] == "key":
            key = await create_key(days, plan["label"] if plan else invoice["plan"], invoice["user_id"])
            result = {"type": "key", "key": key, "days": days}
        elif invoice["kind"] == "tip":
            ratio = min(max(confirmed_units, received_units) / invoice["amount_units"], 12.0) if approved_by else min(confirmed_units / invoice["amount_units"], 12.0)
            value = round(invoice["usd"] * ratio, 2)
            await supporters.record(invoice["user_id"], value)
            await coin_store.add(invoice["user_id"], config.SUPPORT_COINS)
            result = {"type": "tip", "usd": value, "coins": config.SUPPORT_COINS}
        elif invoice["kind"] == "coins":
            ratio = min(max(confirmed_units, received_units) / invoice["amount_units"], 12.0) if approved_by else min(confirmed_units / invoice["amount_units"], 12.0)
            value = round(invoice["usd"] * ratio, 2)
            granted = coin_store.usd_to_diamonds(value)
            await coin_store.add_diamonds(invoice["user_id"], granted)
            result = {"type": "coins", "usd": value, "diamonds": granted}
        else:
            expires = await grant_server(invoice["guild_id"], days)
            result = {"type": "server", "expires": expires, "days": days}
        await update(invoice["invoice_id"], result=json.dumps(result))
        invoice = await get_invoice(invoice["invoice_id"])
        invoice["result_data"] = result
        return invoice


def result_of(invoice: dict) -> dict:
    try:
        return json.loads(invoice.get("result") or "{}")
    except ValueError:
        return {}
