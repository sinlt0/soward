import asyncio
import difflib
import hashlib
import io
import re
import secrets
import shutil
import time
from typing import Optional

import config
from utils import db

CONFIG_FIELDS = ("enabled", "ad", "partner_channel_id", "category_id", "staff_role_id", "ping_role_id", "log_channel_id", "min_members")
TICKET_FIELDS = ("ad", "invite_code", "invite_guild", "attempts", "status")
INVITE_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:discord\.gg|discord(?:app)?\.com/invite)/([A-Za-z0-9-]{2,32})", re.I)
URL_RE = re.compile(r"https?://\S+|discord\.gg/\S+", re.I)


def extract_invite(text: str) -> Optional[str]:
    match = INVITE_RE.search(text or "")
    return match.group(1) if match else None


PING_RE = re.compile(r"\[\s*(?:your\s+)?(?:partner(?:ship)?\s+)?ping\s*\]", re.I)
MASKED_RE = re.compile(r"\[([^\]\n]{1,80})\]\((?:https?://)?[^)\s]+\)")
SPOILER_RE = re.compile(r"\|\|.*?\|\|", re.S)
SPECIAL_RE = re.compile(r"<a?:\w+:\d+>|<[@#][!&]?\d+>|<t:\d+(?::\w)?>|\|\||^-#\s*|^#{1,3}\s*|[*_~`>]", re.M)


def clean_ad(text: str) -> str:
    text = (text or "").strip().replace("```", "'''")
    return text[:config.AUTOPARTNER_AD_MAX_CHARS]


def render_ad(ad: str, ping: str = "") -> str:
    if PING_RE.search(ad):
        text = PING_RE.sub(lambda _: ping, ad)
    elif ping and len(ad) + len(ping) + 1 <= config.AUTOPARTNER_AD_MAX_CHARS:
        text = f"{ad}\n{ping}"
    else:
        text = ad
    return text[:config.AUTOPARTNER_AD_MAX_CHARS]


def link_texts(ad: str) -> list[str]:
    return [m.group(1).strip() for m in MASKED_RE.finditer(ad or "") if INVITE_RE.search(m.group(0))]


def plain_text(ad: str) -> str:
    text = SPOILER_RE.sub(" ", ad or "")
    text = PING_RE.sub(" ", text)
    text = MASKED_RE.sub(lambda m: m.group(1), text)
    text = URL_RE.sub(" ", text)
    return SPECIAL_RE.sub(" ", text)


def normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def words_of(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]{4,}", (text or "").lower())


def ocr_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract
    except ImportError:
        return False
    return True


def run_ocr(data: bytes) -> str:
    import pytesseract
    from PIL import Image, ImageOps, ImageStat

    Image.MAX_IMAGE_PIXELS = 60_000_000
    image = Image.open(io.BytesIO(data))
    image.load()
    image = ImageOps.exif_transpose(image).convert("L")
    width, height = image.size
    if width > 3000:
        image = image.resize((3000, max(1, int(height * 3000 / width))))
    elif width < 1600:
        image = image.resize((width * 2, height * 2))
    if ImageStat.Stat(image).mean[0] < 128:
        image = ImageOps.invert(image)
    return pytesseract.image_to_string(image, config="--psm 6", timeout=config.AUTOPARTNER_OCR_TIMEOUT)


async def read_image(data: bytes) -> str:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, run_ocr, data)


def code_found(ocr_flat: str, code: str) -> bool:
    code = normalise(code)
    if not code:
        return False
    if code in ocr_flat:
        return True
    size = len(code)
    if size < 4 or len(ocr_flat) < size:
        return False
    for start in range(0, len(ocr_flat) - size + 1):
        window = ocr_flat[start:start + size]
        if window[0] != code[0] and window[1] != code[1]:
            continue
        if difflib.SequenceMatcher(None, window, code).ratio() >= config.AUTOPARTNER_CODE_MATCH:
            return True
    return False


def coverage(ocr_text: str, ad: str) -> float:
    wanted = sorted(set(words_of(plain_text(ad))))
    if not wanted:
        return 1.0
    pool = sorted(set(words_of(ocr_text)))[:800]
    pool_set = set(pool)
    hits = 0
    for word in wanted:
        if word in pool_set or difflib.get_close_matches(word, pool, n=1, cutoff=0.8):
            hits += 1
    return hits / len(wanted)


def verify(ocr_text: str, our_ad: str, our_code: str, names: tuple = ()) -> dict:
    flat = normalise(ocr_text)
    score = coverage(ocr_text, our_ad)
    found = code_found(flat, our_code) if our_code else True
    if not found:
        found = any(len(normalise(name)) >= 4 and code_found(flat, name) for name in names)
    return {"score": score, "code": found, "ok": score >= config.AUTOPARTNER_OCR_THRESHOLD and found}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def get_config(guild_id: int) -> dict:
    row = await db.raw_fetchone("SELECT * FROM autopartner_config WHERE guild_id=?", (guild_id,))
    if row:
        return dict(row)
    return {"guild_id": guild_id, "enabled": 1, "ad": "", "partner_channel_id": None, "category_id": None, "staff_role_id": None, "ping_role_id": None, "log_channel_id": None, "min_members": 0}


async def update_config(guild_id: int, **fields) -> None:
    await db.raw_execute("INSERT INTO autopartner_config (guild_id) VALUES (?) ON CONFLICT(guild_id) DO NOTHING", (guild_id,))
    for key, value in fields.items():
        if key in CONFIG_FIELDS:
            await db.raw_execute(f"UPDATE autopartner_config SET {key}=? WHERE guild_id=?", (value, guild_id))


async def next_number(guild_id: int) -> int:
    row = await db.raw_fetchone("SELECT COUNT(*) AS n FROM autopartner_tickets WHERE guild_id=?", (guild_id,))
    return int(row["n"]) + 1


async def create_ticket(guild_id: int, channel_id: int, user_id: int, number: int) -> None:
    await db.raw_execute(
        "INSERT INTO autopartner_tickets (channel_id, guild_id, user_id, number, created_at) VALUES (?, ?, ?, ?, ?)",
        (channel_id, guild_id, user_id, number, time.time()))


async def get_ticket(channel_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM autopartner_tickets WHERE channel_id=?", (channel_id,))
    return dict(row) if row else None


async def update_ticket(channel_id: int, **fields) -> None:
    for key, value in fields.items():
        if key in TICKET_FIELDS:
            await db.raw_execute(f"UPDATE autopartner_tickets SET {key}=? WHERE channel_id=?", (value, channel_id))


async def open_ticket_of(guild_id: int, user_id: int) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM autopartner_tickets WHERE guild_id=? AND user_id=? AND status='open'", (guild_id, user_id))
    return dict(row) if row else None


async def stale_tickets(cutoff: float) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM autopartner_tickets WHERE status='open' AND created_at<?", (cutoff,))
    return [dict(row) for row in rows]


async def open_channel_ids() -> set[int]:
    rows = await db.raw_fetch("SELECT channel_id FROM autopartner_tickets WHERE status='open'")
    return {int(row["channel_id"]) for row in rows}


async def add_post(guild_id: int, user_id: int, code: str, invite_guild: str, channel_id: int, message_id: int) -> str:
    post_id = secrets.token_hex(3)
    await db.raw_execute(
        "INSERT INTO autopartner_posts (post_id, guild_id, user_id, invite_code, invite_guild, channel_id, message_id, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (post_id, guild_id, user_id, code, invite_guild, channel_id, message_id, time.time()))
    return post_id


async def recent_posts(guild_id: int, limit: int = 15) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM autopartner_posts WHERE guild_id=? ORDER BY created_at DESC LIMIT ?", (guild_id, limit))
    return [dict(row) for row in rows]


async def get_post(guild_id: int, post_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM autopartner_posts WHERE guild_id=? AND post_id=?", (guild_id, post_id))
    return dict(row) if row else None


async def delete_post(post_id: str) -> None:
    await db.raw_execute("DELETE FROM autopartner_posts WHERE post_id=?", (post_id,))


async def recent_post_for_code(guild_id: int, code: str) -> Optional[dict]:
    cutoff = time.time() - config.AUTOPARTNER_REPEAT_DAYS * 86400
    row = await db.raw_fetchone(
        "SELECT * FROM autopartner_posts WHERE guild_id=? AND LOWER(invite_code)=LOWER(?) AND created_at>? ORDER BY created_at DESC LIMIT 1",
        (guild_id, code, cutoff))
    return dict(row) if row else None


async def hash_used(guild_id: int, value: str) -> bool:
    row = await db.raw_fetchone("SELECT 1 FROM autopartner_hashes WHERE guild_id=? AND digest=?", (guild_id, value))
    return row is not None


async def save_hash(guild_id: int, value: str) -> None:
    await db.raw_execute("INSERT INTO autopartner_hashes (guild_id, digest) VALUES (?, ?) ON CONFLICT DO NOTHING", (guild_id, value))
