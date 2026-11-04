import random
import time
from datetime import datetime, timezone
from typing import Optional

import config
from utils import coins, db, rewards


def all_jobs() -> tuple:
    return config.CULTIVATION_JOBS


def find_job(text: str) -> Optional[dict]:
    text = text.strip().lower()
    if not text:
        return None
    for job in all_jobs():
        if text in (job["key"], job["name"].lower()):
            return job
    matches = [job for job in all_jobs() if text in job["key"] or text in job["name"].lower()]
    return matches[0] if len(matches) == 1 else None


def unlocked(shifts: int) -> list[dict]:
    return [job for job in all_jobs() if shifts >= job["shifts"]]


def next_job(shifts: int) -> Optional[dict]:
    for job in all_jobs():
        if shifts < job["shifts"]:
            return job
    return None


async def profile(user_id: int) -> dict:
    row = await db.raw_fetchone("SELECT job, shifts FROM user_jobs WHERE user_id=?", (user_id,))
    job = (row["job"] if row else "") or config.CULTIVATION_DEFAULT_JOB
    shifts = int(row["shifts"]) if row else 0
    current = find_job(job) or find_job(config.CULTIVATION_DEFAULT_JOB)
    if shifts < current["shifts"]:
        current = unlocked(shifts)[-1]
    return {"job": current, "shifts": shifts}


async def choose(user_id: int, job: dict) -> bool:
    current = await profile(user_id)
    if current["shifts"] < job["shifts"]:
        return False
    await db.raw_execute(
        "INSERT INTO user_jobs (user_id, job, shifts) VALUES (?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET job=excluded.job",
        (user_id, job["key"], current["shifts"]))
    return True


async def do_work(user_id: int, now: Optional[float] = None, rng: Optional[random.Random] = None) -> dict:
    now = now or time.time()
    rng = rng or random
    data = await rewards.state(user_id)
    day = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
    if data["work_day"] != day:
        data["work_day"], data["work_count"] = day, 0
    if data["work_count"] >= config.WORK_DAILY_LIMIT:
        return {"ok": False, "reason": "limit"}
    wait = data["work_at"] + config.WORK_COOLDOWN_SECONDS - now
    if wait > 0:
        return {"ok": False, "reason": "cooldown", "wait": wait}
    current = await profile(user_id)
    job = current["job"]
    amount = rng.randint(job["min"], job["max"])
    shifts = current["shifts"] + 1
    data.update(work_at=now, work_count=data["work_count"] + 1)
    await rewards.save(data)
    await db.raw_execute(
        "INSERT INTO user_jobs (user_id, job, shifts) VALUES (?, ?, ?)"
        " ON CONFLICT(user_id) DO UPDATE SET job=excluded.job, shifts=excluded.shifts",
        (user_id, job["key"], shifts))
    await coins.add(user_id, amount)
    diamonds = await rewards.drop_diamonds(user_id, "work", rng)
    promoted = [item for item in all_jobs() if current["shifts"] < item["shifts"] <= shifts]
    return {"ok": True, "amount": amount, "diamonds": diamonds, "job": job, "task": rng.choice(job["tasks"]), "left": config.WORK_DAILY_LIMIT - data["work_count"],
            "shifts": shifts, "promoted": promoted[-1] if promoted else None}


async def do_activity(user_id: int, key: str, now: Optional[float] = None, rng: Optional[random.Random] = None) -> dict:
    now = now or time.time()
    rng = rng or random
    spec = config.CULTIVATION_ACTIVITIES[key]
    row = await db.raw_fetchone("SELECT used_at, day, count FROM activity_state WHERE user_id=? AND activity=?", (user_id, key))
    used_at, day, count = (float(row["used_at"]), row["day"], int(row["count"])) if row else (0.0, "", 0)
    today = datetime.fromtimestamp(now, timezone.utc).strftime("%Y-%m-%d")
    if day != today:
        day, count = today, 0
    if count >= spec["daily"]:
        return {"ok": False, "reason": "limit"}
    wait = used_at + spec["cooldown"] - now
    if wait > 0:
        return {"ok": False, "reason": "cooldown", "wait": wait}
    await db.raw_execute(
        "INSERT INTO activity_state (user_id, activity, used_at, day, count) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(user_id, activity) DO UPDATE SET used_at=excluded.used_at, day=excluded.day, count=excluded.count",
        (user_id, key, now, day, count + 1))
    left = spec["daily"] - count - 1
    if rng.random() < spec["fail"]:
        return {"ok": True, "amount": 0, "diamonds": 0, "text": rng.choice(spec["fails"]), "left": left}
    amount = rng.randint(spec["min"], spec["max"])
    await coins.add(user_id, amount)
    diamonds = await rewards.drop_diamonds(user_id, key, rng)
    return {"ok": True, "amount": amount, "diamonds": diamonds, "text": rng.choice(spec["wins"]), "left": left}
