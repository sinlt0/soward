import re
import secrets
import time
from typing import Optional

import config
from utils import coins, db

NAME_RULE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _-]{1,18}[A-Za-z0-9]$")
ROLE_ORDER = {"owner": 3, "officer": 2, "member": 1}


def key_of(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip()).lower()


def clean_name(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip())


def capacity(level: int) -> int:
    return config.CLAN_BASE_MEMBERS + (level - 1) * config.CLAN_LEVEL_MEMBERS


def upgrade_cost(level: int) -> int:
    return config.CLAN_UPGRADE_COST * level


async def membership(user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM clan_members WHERE user_id=?", (user_id,))
    return dict(row) if row else None


async def get(clan_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM clans WHERE clan_id=?", (clan_id,))
    return dict(row) if row else None


async def find(name: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM clans WHERE name_key=?", (key_of(name),))
    return dict(row) if row else None


async def members(clan_id: str) -> list[dict]:
    rows = await db.raw_fetch("SELECT user_id, role, joined_at FROM clan_members WHERE clan_id=? ORDER BY joined_at", (clan_id,))
    result = [dict(r) for r in rows]
    result.sort(key=lambda m: (-ROLE_ORDER.get(m["role"], 0), m["joined_at"]))
    return result


async def member_count(clan_id: str) -> int:
    row = await db.raw_fetchone("SELECT COUNT(*) AS n FROM clan_members WHERE clan_id=?", (clan_id,))
    return int(row["n"])


async def top(limit: int = 10) -> list[dict]:
    rows = await db.raw_fetch(
        "SELECT c.clan_id, c.name, c.level, c.bank, (SELECT COUNT(*) FROM clan_members m WHERE m.clan_id=c.clan_id) AS size"
        " FROM clans c ORDER BY c.level DESC, size DESC, c.bank DESC LIMIT ?", (limit,))
    return [dict(r) for r in rows]


async def create(owner_id: int, name: str) -> Optional[dict]:
    name = clean_name(name)
    if await find(name):
        return None
    clan_id = secrets.token_hex(4)
    now = time.time()
    await db.raw_execute(
        "INSERT INTO clans (clan_id, name, name_key, description, owner_id, bank, level, created_at) VALUES (?, ?, ?, '', ?, 0, 1, ?)",
        (clan_id, name, key_of(name), owner_id, now))
    await db.raw_execute("INSERT INTO clan_members (user_id, clan_id, role, joined_at) VALUES (?, ?, 'owner', ?)", (owner_id, clan_id, now))
    return await get(clan_id)


async def add_member(clan_id: str, user_id: int) -> None:
    await db.raw_execute("INSERT OR REPLACE INTO clan_members (user_id, clan_id, role, joined_at) VALUES (?, ?, 'member', ?)", (user_id, clan_id, time.time()))
    await db.raw_execute("DELETE FROM clan_invites WHERE user_id=?", (user_id,))


async def remove_member(user_id: int) -> None:
    await db.raw_execute("DELETE FROM clan_members WHERE user_id=?", (user_id,))


async def set_role(user_id: int, role: str) -> None:
    await db.raw_execute("UPDATE clan_members SET role=? WHERE user_id=?", (role, user_id))


async def transfer(clan_id: str, old_owner: int, new_owner: int) -> None:
    await db.raw_execute("UPDATE clans SET owner_id=? WHERE clan_id=?", (new_owner, clan_id))
    await set_role(new_owner, "owner")
    await set_role(old_owner, "officer")


async def set_description(clan_id: str, text: str) -> None:
    await db.raw_execute("UPDATE clans SET description=? WHERE clan_id=?", (text[:200], clan_id))


async def disband(clan_id: str) -> None:
    await db.raw_execute("DELETE FROM clan_members WHERE clan_id=?", (clan_id,))
    await db.raw_execute("DELETE FROM clan_invites WHERE clan_id=?", (clan_id,))
    await db.raw_execute("DELETE FROM clans WHERE clan_id=?", (clan_id,))


async def invite(clan_id: str, user_id: int, invited_by: int) -> None:
    await db.raw_execute(
        "INSERT INTO clan_invites (clan_id, user_id, invited_by, created_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(clan_id, user_id) DO UPDATE SET invited_by=excluded.invited_by, created_at=excluded.created_at",
        (clan_id, user_id, invited_by, time.time()))


async def has_invite(clan_id: str, user_id: int) -> bool:
    row = await db.raw_fetchone("SELECT created_at FROM clan_invites WHERE clan_id=? AND user_id=?", (clan_id, user_id))
    return bool(row) and time.time() - row["created_at"] <= config.CLAN_INVITE_HOURS * 3600


async def deposit(clan_id: str, user_id: int, amount: int) -> bool:
    if not await coins.spend(user_id, amount):
        return False
    await db.raw_execute("UPDATE clans SET bank=bank+? WHERE clan_id=?", (int(amount), clan_id))
    return True


async def upgrade(clan_id: str) -> tuple[bool, str]:
    clan = await get(clan_id)
    if clan["level"] >= config.CLAN_MAX_LEVEL:
        return False, "maxed"
    cost = upgrade_cost(clan["level"])
    cursor = await db.raw_execute("UPDATE clans SET bank=bank-?, level=level+1 WHERE clan_id=? AND bank>=? AND level=?", (cost, clan_id, cost, clan["level"]))
    if getattr(cursor, "rowcount", 0) == 0:
        return False, "bank"
    return True, str(clan["level"] + 1)


async def families(clan: dict, limit: int) -> dict:
    from utils import family
    rows = await members(clan["clan_id"])
    ordered = [r["user_id"] for r in rows]
    covered: set[int] = set()
    groups: list[dict] = []
    single: list[int] = []
    budget = limit
    truncated = False
    for user_id in ordered:
        if user_id in covered:
            continue
        if budget < 2:
            truncated = True
            single.append(user_id)
            continue
        comp = await family.component(user_id, min(config.FAMILY_TREE_LIMIT, budget))
        covered.add(user_id)
        if len(comp["nodes"]) < 2:
            single.append(user_id)
            continue
        covered |= comp["nodes"]
        budget -= len(comp["nodes"])
        truncated = truncated or comp["truncated"]
        groups.append({"head": user_id, "comp": comp, "members": [m for m in ordered if m in comp["nodes"]]})
    main = next((i for i, g in enumerate(groups) if clan["owner_id"] in g["comp"]["nodes"]), None)
    if main is None and groups:
        main = max(range(len(groups)), key=lambda i: len(groups[i]["members"]))
    result = []
    if main is not None:
        groups[main]["main"] = True
        result.append(groups[main])
    rest = [g for i, g in enumerate(groups) if i != main]
    rest.sort(key=lambda g: -len(g["members"]))
    for g in rest:
        g["main"] = False
        result.append(g)
    return {"families": result, "unattached": single, "truncated": truncated}


def merged(found: dict) -> dict:
    nodes: set[int] = set()
    couples: dict = {}
    parents: dict = {}
    for group in found["families"]:
        comp = group["comp"]
        nodes |= comp["nodes"]
        couples.update(comp["couples"])
        parents.update(comp["parents"])
    return {"nodes": nodes, "couples": couples, "parents": parents, "truncated": found["truncated"]}
