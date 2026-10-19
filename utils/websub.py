import hashlib
import hmac
import re
import time
import xml.etree.ElementTree as ET
from typing import Optional

import aiohttp

import config
from utils import db

TOPIC_BASE = "https://www.youtube.com/xml/feeds/videos.xml?channel_id="
CHANNEL_RE = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
NS_ATOM = "{http://www.w3.org/2005/Atom}"
NS_YT = "{http://www.youtube.com/xml/schemas/2015}"


def enabled() -> bool:
    return bool(config.WEBSUB_ENABLED_FLAG and config.WEBSUB_CALLBACK_URL and config.WEBSUB_SECRET)


def topic_for(channel_id: str) -> str:
    return TOPIC_BASE + channel_id


def channel_from_topic(topic: str) -> Optional[str]:
    if not topic.startswith(TOPIC_BASE):
        return None
    value = topic[len(TOPIC_BASE):]
    return value if CHANNEL_RE.match(value) else None


def _secret() -> str:
    return hmac.new(config.WEBSUB_SECRET.encode(), b"websub-youtube", hashlib.sha256).hexdigest()


def signature_valid(body: bytes, header: str) -> bool:
    if not header or "=" not in header:
        return False
    algo, _, given = header.partition("=")
    algo = algo.strip().lower()
    if algo not in ("sha1", "sha256", "sha384", "sha512"):
        return False
    expected = hmac.new(_secret().encode(), body, getattr(hashlib, algo)).hexdigest()
    return hmac.compare_digest(expected, given.strip().lower())


def parse_feed(body: bytes) -> list[dict]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    entries = []
    for entry in root.findall(f"{NS_ATOM}entry"):
        video_id = entry.findtext(f"{NS_YT}videoId")
        channel_id = entry.findtext(f"{NS_YT}channelId")
        if not video_id or not channel_id:
            continue
        entries.append({
            "video_id": video_id.strip(),
            "channel_id": channel_id.strip(),
            "title": (entry.findtext(f"{NS_ATOM}title") or "").strip(),
            "published": (entry.findtext(f"{NS_ATOM}published") or "").strip(),
        })
    return entries


async def get_row(channel_id: str) -> Optional[dict]:
    return await db.raw_fetchone("SELECT * FROM websub_subscriptions WHERE channel_id=?", (channel_id,))


async def all_rows() -> dict[str, dict]:
    rows = await db.raw_fetch("SELECT * FROM websub_subscriptions")
    return {r["channel_id"]: dict(r) for r in rows}


async def _save(channel_id: str, status: str, requested_at: float, lease_expires: float, error: Optional[str]):
    await db.raw_execute(
        "INSERT INTO websub_subscriptions (channel_id, status, requested_at, lease_expires, last_error) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(channel_id) DO UPDATE SET status=excluded.status, requested_at=excluded.requested_at,"
        " lease_expires=excluded.lease_expires, last_error=excluded.last_error",
        (channel_id, status, requested_at, lease_expires, error),
    )


async def mark_active(channel_id: str, lease_seconds: int):
    now = time.time()
    row = await get_row(channel_id)
    await _save(channel_id, "active", row["requested_at"] if row else now, now + lease_seconds, None)


async def mark_push(channel_id: str):
    await db.raw_execute(
        "UPDATE websub_subscriptions SET last_push_at=? WHERE channel_id=?", (time.time(), channel_id)
    )


async def forget(channel_id: str):
    await db.raw_execute("DELETE FROM websub_subscriptions WHERE channel_id=?", (channel_id,))


async def _post(session: aiohttp.ClientSession, mode: str, channel_id: str) -> Optional[str]:
    data = {
        "hub.callback": config.WEBSUB_CALLBACK_URL,
        "hub.topic": topic_for(channel_id),
        "hub.verify": "async",
        "hub.mode": mode,
    }
    if mode == "subscribe":
        data["hub.lease_seconds"] = str(config.WEBSUB_LEASE_SECONDS)
        data["hub.secret"] = _secret()
    try:
        async with session.post(config.WEBSUB_HUB_URL, data=data, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status in (200, 202, 204):
                return None
            text = (await resp.text())[:150]
            return f"hub returned {resp.status}: {text}"
    except (aiohttp.ClientError, TimeoutError) as exc:
        return f"{type(exc).__name__}: {exc}"[:150]


async def subscribe(session: aiohttp.ClientSession, channel_id: str) -> bool:
    row = await get_row(channel_id)
    keep_lease = row["lease_expires"] if row and row["status"] == "active" else 0
    if row is None:
        await _save(channel_id, "pending", time.time(), 0, None)
    error = await _post(session, "subscribe", channel_id)
    now = time.time()
    if error:
        await _save(channel_id, "failed" if not keep_lease else "active", now, keep_lease, error)
        return False
    await _save(channel_id, "active" if keep_lease else "pending", now, keep_lease, None)
    return True


async def unsubscribe(session: aiohttp.ClientSession, channel_id: str):
    await _post(session, "unsubscribe", channel_id)
    await forget(channel_id)


def needs_subscribe(row: Optional[dict], now: float) -> bool:
    if row is None:
        return True
    if row["status"] == "active":
        return row["lease_expires"] - now < config.WEBSUB_RENEW_BEFORE_SECONDS
    return now - row["requested_at"] >= config.WEBSUB_PENDING_RETRY_SECONDS


def push_live(row: Optional[dict], now: float) -> bool:
    return bool(row and row["status"] == "active" and row["lease_expires"] > now)
