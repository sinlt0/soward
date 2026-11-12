from rpg import schema
from utils import db


async def add(user_id: int, feat: str, amount: int = 1) -> None:
    await schema.ensure()
    await db.raw_execute(
        "INSERT INTO cult_feats (user_id, feat, count) VALUES (?, ?, ?) ON CONFLICT(user_id, feat) DO UPDATE SET count=count+excluded.count",
        (user_id, feat, amount))


async def get(user_id: int, feat: str) -> int:
    await schema.ensure()
    row = await db.raw_fetchone("SELECT count FROM cult_feats WHERE user_id=? AND feat=?", (user_id, feat))
    return int(row["count"]) if row else 0


async def prefixed(user_id: int, prefix: str) -> dict:
    await schema.ensure()
    rows = await db.raw_fetch("SELECT feat, count FROM cult_feats WHERE user_id=? AND feat LIKE ?", (user_id, prefix + "%"))
    return {row["feat"][len(prefix):]: int(row["count"]) for row in rows}
