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


ROLE_TITLES = {"owner": "Young Master", "officer": "Elder", "member": "Member"}


def title(role: str, name: str, branch: str = "") -> str:
    label = ROLE_TITLES.get(role, "Member")
    base = name.strip()
    if base.lower().endswith(" clan"):
        base = base[:-5]
    if branch:
        return f"{label} of the {branch} Branch of the fallen {base} Clan"
    return f"{label} of the fallen {base} Clan"


async def standing(user_id: int) -> Optional[str]:
    mine = await membership(user_id)
    if mine is None:
        return None
    clan = await get(mine["clan_id"])
    return title(mine["role"], clan["name"], await branch_name(mine["clan_id"], mine.get("branch") or "")) if clan else None


def tier(level: int) -> dict:
    index = max(1, min(int(level), len(config.CLAN_TIERS))) - 1
    return config.CLAN_TIERS[index]


def next_tier(level: int) -> Optional[dict]:
    return config.CLAN_TIERS[level] if level < len(config.CLAN_TIERS) else None


def top_level() -> int:
    return len(config.CLAN_TIERS)


def capacity(level: int) -> int:
    return tier(level)["members"]


def family_limit(level: int) -> int:
    return tier(level)["families"]


def upgrade_cost(level: int) -> int:
    nxt = next_tier(level)
    return nxt["cost"] if nxt else 0


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
    rows = await db.raw_fetch("SELECT user_id, role, joined_at, branch FROM clan_members WHERE clan_id=? ORDER BY joined_at", (clan_id,))
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


async def branches(clan_id: str) -> list[dict]:
    rows = await db.raw_fetch(
        "SELECT b.branch_key, b.name, b.founder_id, (SELECT COUNT(*) FROM clan_members m WHERE m.clan_id=b.clan_id AND m.branch=b.branch_key) AS members"
        " FROM clan_branches b WHERE b.clan_id=? ORDER BY b.created_at", (clan_id,))
    return [dict(row) for row in rows]


def branch_limit(level: int) -> int:
    return max(1, int(level))


async def create_branch(clan_id: str, founder_id: int, name: str) -> str:
    name = clean_name(name)
    if not NAME_RULE.match(name):
        return "name"
    existing = await branches(clan_id)
    if any(item["branch_key"] == key_of(name) for item in existing):
        return "taken"
    clan = await get(clan_id)
    if clan is None or len(existing) >= branch_limit(clan["level"]):
        return "limit"
    await db.raw_execute("INSERT INTO clan_branches (clan_id, branch_key, name, founder_id, created_at) VALUES (?, ?, ?, ?, ?)", (clan_id, key_of(name), name, founder_id, time.time()))
    await db.raw_execute("UPDATE clan_members SET branch=? WHERE user_id=?", (key_of(name), founder_id))
    return "ok"


async def find_branch(clan_id: str, name: str) -> Optional[dict]:
    key = key_of(clean_name(name))
    return next((item for item in await branches(clan_id) if item["branch_key"] == key), None)


async def set_branch(user_id: int, branch_key: str) -> None:
    await db.raw_execute("UPDATE clan_members SET branch=? WHERE user_id=?", (branch_key, user_id))


async def remove_branch(clan_id: str, branch_key: str) -> None:
    await db.raw_execute("UPDATE clan_members SET branch='' WHERE clan_id=? AND branch=?", (clan_id, branch_key))
    await db.raw_execute("DELETE FROM clan_branches WHERE clan_id=? AND branch_key=?", (clan_id, branch_key))


async def branch_name(clan_id: str, branch_key: str) -> str:
    if not branch_key:
        return ""
    found = next((item for item in await branches(clan_id) if item["branch_key"] == branch_key), None)
    return found["name"] if found else ""


async def disband(clan_id: str) -> None:
    await db.raw_execute("DELETE FROM clan_branches WHERE clan_id=?", (clan_id,))
    await db.raw_execute("DELETE FROM clan_members WHERE clan_id=?", (clan_id,))
    await db.raw_execute("DELETE FROM clan_invites WHERE clan_id=?", (clan_id,))
    await db.raw_execute("DELETE FROM clan_contributions WHERE clan_id=?", (clan_id,))
    await db.raw_execute("DELETE FROM clan_buildings WHERE clan_id=?", (clan_id,))
    await db.raw_execute("DELETE FROM clan_boss WHERE clan_id=?", (clan_id,))
    await db.raw_execute("DELETE FROM clan_boss_hits WHERE clan_id=?", (clan_id,))
    await db.raw_execute("DELETE FROM clan_wars WHERE clan_a=? OR clan_b=?", (clan_id, clan_id))
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
    await db.raw_execute(
        "INSERT INTO clan_contributions (clan_id, user_id, amount) VALUES (?, ?, ?)"
        " ON CONFLICT(clan_id, user_id) DO UPDATE SET amount=amount+excluded.amount",
        (clan_id, user_id, int(amount)))
    return True


async def contributions(clan_id: str, limit: int = 10) -> list[dict]:
    rows = await db.raw_fetch("SELECT user_id, amount FROM clan_contributions WHERE clan_id=? ORDER BY amount DESC LIMIT ?", (clan_id, limit))
    return [dict(r) for r in rows]


async def upgrade(clan_id: str) -> tuple[bool, str]:
    clan = await get(clan_id)
    nxt = next_tier(clan["level"])
    if nxt is None:
        return False, "maxed"
    if await member_count(clan_id) < nxt["need"]:
        return False, "members"
    cursor = await db.raw_execute("UPDATE clans SET bank=bank-?, level=level+1 WHERE clan_id=? AND bank>=? AND level=?", (nxt["cost"], clan_id, nxt["cost"], clan["level"]))
    if getattr(cursor, "rowcount", 0) == 0:
        return False, "bank"
    return True, str(clan["level"] + 1)


async def set_stipend(clan_id: str, enabled: bool) -> None:
    await db.raw_execute("UPDATE clans SET stipend_on=? WHERE clan_id=?", (1 if enabled else 0, clan_id))


async def bonus_percent(user_id: int) -> int:
    mine = await membership(user_id)
    if mine is None:
        return 0
    clan = await get(mine["clan_id"])
    return tier(clan["level"])["bonus"] if clan else 0


async def boost(user_id: int, amount: int) -> tuple[int, int]:
    percent = await bonus_percent(user_id)
    extra = amount * percent // 100
    return amount + extra, extra


async def claim_stipend(user_id: int, now: Optional[float] = None) -> dict:
    now = now or time.time()
    mine = await membership(user_id)
    if mine is None:
        return {"ok": False, "reason": "no_clan"}
    clan = await get(mine["clan_id"])
    amount = tier(clan["level"])["stipend"]
    if amount <= 0:
        return {"ok": False, "reason": "no_tier", "clan": clan}
    if not clan["stipend_on"]:
        return {"ok": False, "reason": "off", "clan": clan}
    row = await db.raw_fetchone("SELECT used_at FROM activity_state WHERE user_id=? AND activity='clan_stipend'", (user_id,))
    wait = (float(row["used_at"]) if row else 0.0) + config.CLAN_STIPEND_COOLDOWN_HOURS * 3600 - now
    if wait > 0:
        return {"ok": False, "reason": "cooldown", "wait": wait, "clan": clan}
    cursor = await db.raw_execute("UPDATE clans SET bank=bank-? WHERE clan_id=? AND bank>=?", (amount, clan["clan_id"], amount))
    if getattr(cursor, "rowcount", 0) == 0:
        return {"ok": False, "reason": "bank", "clan": clan, "amount": amount}
    await db.raw_execute(
        "INSERT INTO activity_state (user_id, activity, used_at, day, count) VALUES (?, 'clan_stipend', ?, '', 0)"
        " ON CONFLICT(user_id, activity) DO UPDATE SET used_at=excluded.used_at",
        (user_id, now))
    await coins.add(user_id, amount)
    return {"ok": True, "amount": amount, "clan": clan}


async def joins_new_family(clan: dict, user_id: int) -> bool:
    from utils import family
    comp = await family.component(user_id, config.FAMILY_TREE_LIMIT)
    if len(comp["nodes"]) < 2:
        return False
    rows = await members(clan["clan_id"])
    return not any(r["user_id"] in comp["nodes"] for r in rows)


async def family_count(clan: dict) -> int:
    found = await families(clan, config.CLAN_TREE_LIMIT)
    return len(found["families"])


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
