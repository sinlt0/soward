import json
import re
import time
import uuid
from typing import Any, Optional

import config
from utils import db

TRACK_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def clean_track(raw: Any) -> Optional[dict]:
    if not isinstance(raw, dict):
        return None
    track_id = str(raw.get("id", ""))
    if not TRACK_ID.match(track_id):
        return None
    title = str(raw.get("title", "")).strip()[:150]
    if not title:
        return None
    try:
        duration = max(0, min(int(raw.get("duration") or 0), 86400))
    except (TypeError, ValueError):
        duration = 0
    return {"id": track_id, "title": title, "artist": str(raw.get("artist", "")).strip()[:100], "duration": duration, "thumb": str(raw.get("thumb", ""))[:300]}


def _out(row) -> dict:
    return {"id": row["track_id"], "title": row["title"], "artist": row["artist"], "duration": row["duration"], "thumb": row["thumb"]}


async def likes(user_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM activity_likes WHERE user_id=? ORDER BY liked_at DESC", (user_id,))
    return [_out(r) for r in rows]


async def like_ids(user_id: int) -> list[str]:
    rows = await db.raw_fetch("SELECT track_id FROM activity_likes WHERE user_id=?", (user_id,))
    return [r["track_id"] for r in rows]


async def set_like(user_id: int, track: dict, liked: bool) -> bool:
    if not liked:
        await db.raw_execute("DELETE FROM activity_likes WHERE user_id=? AND track_id=?", (user_id, track["id"]))
        return True
    count = await db.raw_fetchone("SELECT COUNT(*) AS n FROM activity_likes WHERE user_id=?", (user_id,))
    exists = await db.raw_fetchone("SELECT 1 FROM activity_likes WHERE user_id=? AND track_id=?", (user_id, track["id"]))
    if not exists and count["n"] >= config.ACTIVITY_MAX_LIKES:
        return False
    await db.raw_execute(
        "INSERT INTO activity_likes (user_id, track_id, title, artist, duration, thumb, liked_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id, track_id) DO UPDATE SET title=excluded.title, artist=excluded.artist, duration=excluded.duration, thumb=excluded.thumb",
        (user_id, track["id"], track["title"], track["artist"], track["duration"], track["thumb"], time.time()),
    )
    return True


async def history(user_id: int, limit: int = 100) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM activity_history WHERE user_id=? ORDER BY played_at DESC, entry_id DESC LIMIT ?", (user_id, limit))
    return [_out(r) for r in rows]


async def add_history(user_id: int, track: dict) -> None:
    last = await db.raw_fetchone("SELECT track_id FROM activity_history WHERE user_id=? ORDER BY played_at DESC, entry_id DESC LIMIT 1", (user_id,))
    if last and last["track_id"] == track["id"]:
        return
    await db.raw_execute(
        "INSERT INTO activity_history (user_id, track_id, title, artist, duration, thumb, played_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, track["id"], track["title"], track["artist"], track["duration"], track["thumb"], time.time()),
    )
    stale = await db.raw_fetch(
        "SELECT entry_id FROM activity_history WHERE user_id=? ORDER BY played_at DESC, entry_id DESC LIMIT -1 OFFSET ?",
        (user_id, config.ACTIVITY_HISTORY_KEEP),
    )
    for row in stale:
        await db.raw_execute("DELETE FROM activity_history WHERE entry_id=?", (row["entry_id"],))


async def clear_history(user_id: int) -> None:
    await db.raw_execute("DELETE FROM activity_history WHERE user_id=?", (user_id,))


async def playlists(user_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM activity_playlists WHERE user_id=? ORDER BY updated_at DESC", (user_id,))
    return [{"id": r["playlist_id"], "name": r["name"], "tracks": json.loads(r["tracks"]), "updated_at": r["updated_at"]} for r in rows]


async def get_playlist(user_id: int, playlist_id: str) -> Optional[dict]:
    row = await db.raw_fetchone("SELECT * FROM activity_playlists WHERE user_id=? AND playlist_id=?", (user_id, playlist_id))
    if row is None:
        return None
    return {"id": row["playlist_id"], "name": row["name"], "tracks": json.loads(row["tracks"]), "updated_at": row["updated_at"]}


async def create_playlist(user_id: int, name: str) -> Optional[dict]:
    name = name.strip()[:60]
    if not name:
        raise ValueError("Give the playlist a name.")
    count = await db.raw_fetchone("SELECT COUNT(*) AS n FROM activity_playlists WHERE user_id=?", (user_id,))
    if count["n"] >= config.ACTIVITY_MAX_PLAYLISTS:
        raise ValueError(f"You can keep {config.ACTIVITY_MAX_PLAYLISTS} playlists.")
    playlist_id = uuid.uuid4().hex[:10]
    now = time.time()
    await db.raw_execute("INSERT INTO activity_playlists (playlist_id, user_id, name, tracks, created_at, updated_at) VALUES (?, ?, ?, '[]', ?, ?)", (playlist_id, user_id, name, now, now))
    return {"id": playlist_id, "name": name, "tracks": [], "updated_at": now}


async def save_tracks(user_id: int, playlist_id: str, tracks: list[dict]) -> None:
    await db.raw_execute("UPDATE activity_playlists SET tracks=?, updated_at=? WHERE user_id=? AND playlist_id=?", (json.dumps(tracks), time.time(), user_id, playlist_id))


async def add_to_playlist(user_id: int, playlist_id: str, track: dict) -> dict:
    playlist = await get_playlist(user_id, playlist_id)
    if playlist is None:
        raise ValueError("Playlist not found.")
    if any(t["id"] == track["id"] for t in playlist["tracks"]):
        raise ValueError("That song is already in the playlist.")
    if len(playlist["tracks"]) >= config.ACTIVITY_MAX_PLAYLIST_TRACKS:
        raise ValueError(f"A playlist holds {config.ACTIVITY_MAX_PLAYLIST_TRACKS} songs.")
    playlist["tracks"].append(track)
    await save_tracks(user_id, playlist_id, playlist["tracks"])
    return playlist


async def remove_from_playlist(user_id: int, playlist_id: str, track_id: str) -> dict:
    playlist = await get_playlist(user_id, playlist_id)
    if playlist is None:
        raise ValueError("Playlist not found.")
    playlist["tracks"] = [t for t in playlist["tracks"] if t["id"] != track_id]
    await save_tracks(user_id, playlist_id, playlist["tracks"])
    return playlist


async def rename_playlist(user_id: int, playlist_id: str, name: str) -> None:
    name = name.strip()[:60]
    if not name:
        raise ValueError("Give the playlist a name.")
    await db.raw_execute("UPDATE activity_playlists SET name=?, updated_at=? WHERE user_id=? AND playlist_id=?", (name, time.time(), user_id, playlist_id))


async def delete_playlist(user_id: int, playlist_id: str) -> None:
    await db.raw_execute("DELETE FROM activity_playlists WHERE user_id=? AND playlist_id=?", (user_id, playlist_id))


async def library(user_id: int) -> dict:
    return {"likes": await likes(user_id), "playlists": await playlists(user_id), "history": await history(user_id)}
