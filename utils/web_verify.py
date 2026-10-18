import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

import aiohttp

import config
from utils import db
from utils import security_settings as settings

_intel_cache: dict[str, tuple[float, dict]] = {}
INTEL_TTL = 3600


def _key() -> bytes:
    return (config.WEB_VERIFY_SALT or os.environ.get("SOWARD_IPC_SECRET", "") or "soward").encode()


def hash_value(guild_id: int, value: str) -> str:
    return hmac.new(_key(), f"{guild_id}|{value}".encode(), hashlib.sha256).hexdigest()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def create_token(guild_id: int, user_id: int) -> str:
    token = secrets.token_urlsafe(24)
    now = time.time()
    await db.raw_execute("DELETE FROM web_verify_tokens WHERE guild_id=? AND user_id=?", (guild_id, user_id))
    await db.raw_execute(
        "INSERT INTO web_verify_tokens (token_hash, guild_id, user_id, created_at, expires_at, used) VALUES (?, ?, ?, ?, ?, 0)",
        (token_digest(token), guild_id, user_id, now, now + config.WEB_VERIFY_TOKEN_TTL_SECONDS),
    )
    return token


async def lookup_token(token: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM web_verify_tokens WHERE token_hash=?", (token_digest(token),))
    if row is None or row["used"] or row["expires_at"] < time.time():
        return None
    return dict(row)


async def burn_token(token: str) -> bool:
    cur = await db.raw_execute("UPDATE web_verify_tokens SET used=1 WHERE token_hash=? AND used=0", (token_digest(token),))
    return cur.rowcount == 1


def provider_ready() -> bool:
    return config.WEB_VERIFY_PROVIDER in ("proxycheck", "ipqs") and bool(config.WEB_VERIFY_PROVIDER_KEY or config.WEB_VERIFY_PROVIDER == "proxycheck")


async def _lookup_ip(ip: str) -> Optional[dict]:
    hit = _intel_cache.get(ip)
    if hit and hit[0] > time.time():
        return hit[1]
    timeout = aiohttp.ClientTimeout(total=6)
    result: Optional[dict] = None
    try:
        async with aiohttp.ClientSession(timeout=timeout) as http:
            if config.WEB_VERIFY_PROVIDER == "proxycheck":
                params = {"vpn": "1", "risk": "1", "asn": "1"}
                if config.WEB_VERIFY_PROVIDER_KEY:
                    params["key"] = config.WEB_VERIFY_PROVIDER_KEY
                async with http.get(f"https://proxycheck.io/v2/{ip}", params=params) as resp:
                    data = await resp.json(content_type=None)
                info = data.get(ip) or {}
                if data.get("status") not in ("ok", "warning") or not info:
                    return None
                kind = str(info.get("type", "")).lower()
                result = {
                    "vpn": info.get("proxy") == "yes",
                    "tor": kind == "tor",
                    "hosting": kind in ("hosting", "business"),
                    "risk": int(info.get("risk", 0) or 0),
                    "country": info.get("isocode") or "",
                }
            elif config.WEB_VERIFY_PROVIDER == "ipqs":
                url = f"https://ipqualityscore.com/api/json/ip/{config.WEB_VERIFY_PROVIDER_KEY}/{ip}"
                async with http.get(url, params={"strictness": "1", "allow_public_access_points": "true"}) as resp:
                    data = await resp.json(content_type=None)
                if not data.get("success"):
                    return None
                result = {
                    "vpn": bool(data.get("vpn") or data.get("proxy")),
                    "tor": bool(data.get("tor")),
                    "hosting": bool(data.get("is_crawler")),
                    "risk": int(data.get("fraud_score", 0) or 0),
                    "country": data.get("country_code") or "",
                }
    except (aiohttp.ClientError, ValueError, TimeoutError):
        return None
    if result is not None:
        _intel_cache[ip] = (time.time() + INTEL_TTL, result)
        if len(_intel_cache) > 2000:
            for stale in [k for k, v in _intel_cache.items() if v[0] < time.time()]:
                _intel_cache.pop(stale, None)
    return result


async def find_alts(guild_id: int, user_id: int, ip_hash: str, fingerprint_hash: Optional[str], match: str) -> list[int]:
    found: set[int] = set()
    if match in ("ip", "ip_and_fingerprint"):
        rows = await db.raw_fetch(
            "SELECT user_id, fingerprint_hash FROM web_verifications WHERE guild_id=? AND ip_hash=? AND user_id!=?",
            (guild_id, ip_hash, user_id),
        )
        for row in rows:
            if match == "ip" or (fingerprint_hash and row["fingerprint_hash"] == fingerprint_hash):
                found.add(row["user_id"])
    if match == "fingerprint" and fingerprint_hash:
        rows = await db.raw_fetch(
            "SELECT user_id FROM web_verifications WHERE guild_id=? AND fingerprint_hash=? AND user_id!=?",
            (guild_id, fingerprint_hash, user_id),
        )
        found.update(row["user_id"] for row in rows)
    return sorted(found)


async def analyse(guild_id: int, user_id: int, ip: str, fingerprint: str) -> dict:
    ip_hash = hash_value(guild_id, ip)
    fingerprint_hash = hash_value(guild_id, fingerprint) if fingerprint else None
    block_vpn = bool(await settings.get(guild_id, "verification", "web_block_vpn"))
    intel = None
    if provider_ready():
        intel = await _lookup_ip(ip)
    vpn = bool(intel and (intel["vpn"] or intel["tor"]))
    hosting = bool(intel and intel["hosting"] and await settings.get(guild_id, "verification", "web_block_hosting"))
    reasons = []
    if block_vpn and (vpn or hosting):
        reasons.append("tor exit node" if intel and intel["tor"] else "vpn or proxy" if vpn else "hosting network")
    unknown = intel is None and block_vpn
    match = await settings.get(guild_id, "verification", "web_alt_match")
    alts = await find_alts(guild_id, user_id, ip_hash, fingerprint_hash, match) if await settings.get(guild_id, "verification", "web_alt_check") else []
    return {
        "ip_hash": ip_hash, "fingerprint_hash": fingerprint_hash,
        "vpn": vpn or hosting, "vpn_reasons": reasons, "unknown": unknown,
        "country": (intel or {}).get("country", ""), "risk": int((intel or {}).get("risk", 0)),
        "alts": alts,
    }


async def record(guild_id: int, user_id: int, result: dict, outcome: str) -> None:
    await db.raw_execute(
        "INSERT INTO web_verifications (guild_id, user_id, ip_hash, fingerprint_hash, vpn, country, risk, outcome, alt_of, verified_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(guild_id, user_id) DO UPDATE SET ip_hash=excluded.ip_hash, fingerprint_hash=excluded.fingerprint_hash,"
        " vpn=excluded.vpn, country=excluded.country, risk=excluded.risk, outcome=excluded.outcome, alt_of=excluded.alt_of, verified_at=excluded.verified_at",
        (guild_id, user_id, result["ip_hash"], result["fingerprint_hash"], int(result["vpn"]), result["country"], result["risk"],
         outcome, json.dumps(result["alts"]), time.time()),
    )


async def purge_old() -> None:
    now = time.time()
    await db.raw_execute("DELETE FROM web_verify_tokens WHERE expires_at < ?", (now - 3600,))
    rows = await db.raw_fetch("SELECT DISTINCT guild_id FROM web_verifications")
    for row in rows:
        days = int(await settings.get(row["guild_id"], "verification", "web_retention_days"))
        await db.raw_execute("DELETE FROM web_verifications WHERE guild_id=? AND verified_at < ?", (row["guild_id"], now - days * 86400))
