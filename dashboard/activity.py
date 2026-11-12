import base64
import collections
import concurrent.futures
import hashlib
import hmac
import json
import logging
import os
import re
import shutil
import threading
import time
from urllib.parse import urljoin
from collections import defaultdict, deque
from pathlib import Path
from typing import Optional

import requests
from flask import Blueprint, Response, abort, jsonify, render_template, request, send_from_directory
from werkzeug.exceptions import HTTPException

import config
from dashboard import doom, games
from dashboard.ipc import BotClient, BotError, BotUnavailable

log = logging.getLogger("zyro.activity")
DISCORD_API = "https://discord.com/api/v10"
TRACK_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
STATIC = Path(__file__).resolve().parent / "static" / "activity"
MAX_TRACK_SECONDS = 1800
SC_ID = re.compile(r"^s\d{10}$")
TITLE_NOISE = re.compile(r"\([^)]*\)|\[[^\]]*\]|official|video|audio|lyrics?|visualizer|hd|4k", re.I)
CHUNK = 64 * 1024

LIMITS = {"search": (30, 60), "play": (60, 60), "home": (20, 60), "write": (120, 60), "game": (300, 60), "doom": (900, 60), "doominput": (900, 60), "doomwad": (240, 60)}

_users: dict[str, tuple[float, dict]] = {}
_buckets: dict[tuple, deque] = defaultdict(deque)
_resolved: dict[str, tuple[float, str, dict]] = {}
_search_cache: dict[str, tuple[float, list]] = {}
_thumbs: dict[str, tuple[float, bytes, str]] = {}
_lock = threading.Lock()
_resolve_gate = threading.BoundedSemaphore(3)
_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="activity")
_inflight: dict[str, concurrent.futures.Future] = {}
PLAY_WAIT = 22
_failed: dict[str, tuple[float, str, str]] = {}
_hints: dict[str, dict] = {}
_alt: dict[str, str] = {}
_sc_thumbs: dict[str, str] = {}
_yt_blocked_until = 0.0
_lavalink_pause = [0.0]
_blobs: "collections.OrderedDict[str, tuple[bytes, str]]" = collections.OrderedDict()
BLOB_LIMIT = 120 * 1024 * 1024
BLOB_MAX_TRACK = 40 * 1024 * 1024


def _json_error(message: str, status: int):
    response = jsonify(error=message)
    response.status_code = status
    return response


def _hit(uid: str, bucket: str) -> bool:
    limit, window = LIMITS[bucket]
    now = time.time()
    with _lock:
        queue = _buckets[(uid, bucket)]
        while queue and queue[0] < now - window:
            queue.popleft()
        if len(queue) >= limit:
            return False
        queue.append(now)
        return True


def _extractor():
    import yt_dlp
    return yt_dlp


def _cookie_file() -> str:
    encoded = os.getenv("ZYRO_YTDLP_COOKIES_B64", "").strip()
    if encoded:
        target = Path(config.DATA_DIR) / "yt_cookies.txt"
        try:
            data = base64.b64decode(encoded)
            if not target.exists() or target.read_bytes() != data:
                target.write_bytes(data)
            return str(target)
        except Exception as exc:
            log.warning("Could not use ZYRO_YTDLP_COOKIES_B64: %s", exc)
    path = os.getenv("ZYRO_YTDLP_COOKIES", "")
    if path and os.path.isfile(path):
        copy = Path(config.DATA_DIR) / "yt_cookies_copy.txt"
        try:
            copy.write_bytes(Path(path).read_bytes())
            return str(copy)
        except OSError:
            return path
    return ""


def _cookie_names() -> set:
    path = _cookie_file()
    names = set()
    if path:
        try:
            for line in Path(path).read_text().splitlines():
                parts = line.split("\t")
                if len(parts) >= 7 and not line.startswith("#"):
                    names.add(parts[5])
        except OSError:
            pass
    return names


CLIENT_CHAINS = [None, ["tv"], ["web_safari"], ["mweb"], ["android_vr"]]


def _is_bot_block(exc: Exception) -> bool:
    text = str(exc).lower()
    return "sign in to confirm" in text or "not a bot" in text


def _ytdlp_opts(client=None, **extra) -> dict:
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True, "socket_timeout": 10, "retries": 1, "extractor_retries": 1}
    cookies = _cookie_file()
    if cookies:
        opts["cookiefile"] = cookies
    if client:
        opts["extractor_args"] = {"youtube": {"player_client": client}}
    runtime = os.getenv("ZYRO_YTDLP_JS_RUNTIME", "").strip()
    if runtime:
        opts["js_runtimes"] = {runtime: {}}
    opts.update(extra)
    return opts


def _track(entry: dict) -> Optional[dict]:
    track_id = str(entry.get("id") or "")
    if not TRACK_ID.match(track_id) or entry.get("live_status") in ("is_live", "is_upcoming"):
        return None
    duration = int(entry.get("duration") or 0)
    if duration <= 0 or duration > MAX_TRACK_SECONDS:
        return None
    title = str(entry.get("title") or "").strip()
    if not title:
        return None
    artist = str(entry.get("artist") or entry.get("uploader") or entry.get("channel") or "").replace(" - Topic", "").strip()
    return {"id": track_id, "title": title[:150], "artist": artist[:100], "duration": duration, "thumb": f"https://i.ytimg.com/vi/{track_id}/hqdefault.jpg"}


def _sc_track(entry: dict) -> Optional[dict]:
    raw = str(entry.get("id") or "")
    if not raw.isdigit() or len(raw) > 10:
        return None
    duration = int(entry.get("duration") or 0)
    if duration < 45 or duration > MAX_TRACK_SECONDS:
        return None
    title = str(entry.get("title") or "").strip()
    if not title:
        return None
    thumb = str(entry.get("thumbnail") or "").replace("-original", "-t300x300")
    if thumb and not thumb.startswith("https://") :
        thumb = ""
    track_id = f"s{int(raw):010d}"
    if thumb:
        with _lock:
            if len(_sc_thumbs) > 800:
                _sc_thumbs.clear()
            _sc_thumbs[track_id] = thumb
    return {"id": track_id, "title": title[:150], "artist": str(entry.get("uploader") or "").strip()[:100], "duration": duration, "thumb": thumb}


def search_soundcloud(query: str, count: int) -> list[dict]:
    key = f"sc:{count}:{query.lower()}"
    hit = _search_cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    yt_dlp = _extractor()
    opts = _ytdlp_opts(ignoreerrors=True, playlistend=count + 4)
    with _resolve_gate:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"scsearch{count + 4}:{query}", download=False)
    tracks, seen = [], set()
    for entry in (info or {}).get("entries") or []:
        track = _sc_track(entry or {})
        if track and track["id"] not in seen:
            seen.add(track["id"])
            tracks.append(track)
        if len(tracks) >= count:
            break
    with _lock:
        if len(_search_cache) > 300:
            _search_cache.clear()
        _search_cache[key] = (time.time() + 1800, tracks)
    return tracks


def _store_blob(key: str, data: bytes, content_type: str) -> None:
    with _lock:
        _blobs.pop(key, None)
        _blobs[key] = (data, content_type)
        total = sum(len(item[0]) for item in _blobs.values())
        while total > BLOB_LIMIT and len(_blobs) > 1:
            _, dropped = _blobs.popitem(last=False)
            total -= len(dropped[0])


def _download_playlist(playlist_url: str, headers: dict) -> tuple[bytes, str]:
    reply = requests.get(playlist_url, headers=headers, timeout=(8, 15))
    if reply.status_code != 200:
        raise LookupError("unavailable")
    lines = reply.text.splitlines()
    if any(line.startswith("#EXT-X-KEY") and "METHOD=NONE" not in line for line in lines):
        raise LookupError("unavailable")
    parts, init, content_type = [], None, "audio/mpeg"
    for line in lines:
        if line.startswith("#EXT-X-MAP"):
            match = re.search(r'URI="([^"]+)"', line)
            if match:
                init = urljoin(playlist_url, match.group(1))
                content_type = "audio/mp4"
        elif line and not line.startswith("#"):
            parts.append(urljoin(playlist_url, line.strip()))
    if not parts or len(parts) > 600:
        raise LookupError("unavailable")
    data = bytearray()
    for target in ([init] if init else []) + parts:
        piece = requests.get(target, headers=headers, timeout=(8, 20))
        if piece.status_code != 200:
            raise LookupError("unavailable")
        data.extend(piece.content)
        if len(data) > BLOB_MAX_TRACK:
            raise LookupError("unavailable")
    return bytes(data), content_type


def _resolve_soundcloud(track_id: str) -> tuple[str, dict]:
    yt_dlp = _extractor()
    opts = _ytdlp_opts(format="bestaudio[protocol=https]/bestaudio[protocol=http]/bestaudio[format_id^=hls_mp3]/bestaudio[format_id^=hls_aac]/bestaudio")
    with _resolve_gate:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"https://api.soundcloud.com/tracks/{int(track_id[1:])}", download=False)
    url = (info or {}).get("url")
    if not url:
        raise LookupError("unavailable")
    headers = dict(info.get("http_headers") or {})
    if "m3u8" in str(info.get("protocol", "")) or ".m3u8" in url:
        data, content_type = _download_playlist(url, headers)
        _store_blob(track_id, data, content_type)
        return f"blob:{track_id}", {}
    return url, headers


def _words(text: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1}


def _alternative_query(hint: dict) -> str:
    title = TITLE_NOISE.sub(" ", str(hint.get("title", "")))
    artist = TITLE_NOISE.sub(" ", str(hint.get("artist", "")))
    return " ".join(f"{artist} {title}".split())[:100]


def _find_alternative(hint: dict, notes: Optional[dict] = None) -> Optional[str]:
    query = _alternative_query(hint)
    if notes is not None:
        notes["query"] = query
    if len(query) < 3:
        return None
    wanted = int(hint.get("duration") or 0)
    wanted_words = _words(query)
    candidates = search_soundcloud(query, 10)
    if notes is not None:
        notes["candidates"] = [{"id": t["id"], "title": t["title"][:60], "artist": t["artist"][:30], "duration": t["duration"]} for t in candidates]
    best, best_score = None, 0.0
    for position, candidate in enumerate(candidates):
        overlap = len(wanted_words & _words(f"{candidate['title']} {candidate['artist']}")) / max(1, len(wanted_words))
        if wanted and abs(candidate["duration"] - wanted) > 45:
            continue
        score = overlap - position * 0.01
        if score > best_score:
            best, best_score = candidate, score
    if best is None or best_score < 0.5:
        return None
    return best["id"]


def search_tracks(query: str, count: int) -> list[dict]:
    key = f"{count}:{query.lower()}"
    hit = _search_cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    yt_dlp = _extractor()
    opts = _ytdlp_opts(extract_flat=True)
    with _resolve_gate:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{count + 8}:{query}", download=False)
    tracks, seen = [], set()
    for entry in (info or {}).get("entries") or []:
        track = _track(entry or {})
        if track and track["id"] not in seen:
            seen.add(track["id"])
            tracks.append(track)
        if len(tracks) >= count:
            break
    with _lock:
        if len(_search_cache) > 300:
            _search_cache.clear()
        _search_cache[key] = (time.time() + 1800, tracks)
    return tracks


def resolve(track_id: str, fresh: bool = False, trail: Optional[list] = None) -> tuple[str, dict]:
    hit = _resolved.get(track_id)
    if hit and hit[0] > time.time() and not fresh:
        return hit[1], hit[2]
    if SC_ID.match(track_id):
        url, headers = _resolve_soundcloud(track_id)
        with _lock:
            if len(_resolved) > 500:
                _resolved.clear()
            _resolved[track_id] = (time.time() + config.ACTIVITY_RESOLVE_TTL, url, headers)
        return url, headers
    hint = _hints.get(track_id)
    if hint and trail is None and _yt_blocked_until > time.time():
        return _resolve_alternative(track_id, hint, LookupError("YouTube is blocking this server."))
    yt_dlp = _extractor()
    info, failure = None, None
    for client in CLIENT_CHAINS:
        opts = _ytdlp_opts(client=client, format="bestaudio[ext=m4a]/bestaudio[acodec^=mp4a]/bestaudio/best", source_address="0.0.0.0")
        try:
            with _resolve_gate:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(f"https://www.youtube.com/watch?v={track_id}", download=False)
            failure = None
            break
        except Exception as exc:
            failure = failure or exc
            if trail is not None:
                trail.append({"client": ",".join(client) if client else "default", "error": str(exc)[:160]})
            if not _is_bot_block(exc):
                raise
    if failure is not None:
        if _is_bot_block(failure):
            globals()["_yt_blocked_until"] = time.time() + 600
            if hint and trail is None:
                return _resolve_alternative(track_id, hint, failure)
        raise failure
    if not info or info.get("is_live"):
        raise LookupError("unavailable")
    url = info.get("url")
    headers = dict(info.get("http_headers") or {})
    if not url:
        formats = [f for f in info.get("formats", []) if f.get("acodec") not in (None, "none") and f.get("url") and f.get("protocol") in ("https", "http")]
        if not formats:
            raise LookupError("unavailable")
        formats.sort(key=lambda f: (f.get("vcodec") == "none", f.get("abr") or 0), reverse=True)
        url, headers = formats[0]["url"], dict(formats[0].get("http_headers") or headers)
    with _lock:
        if len(_resolved) > 500:
            _resolved.clear()
        _resolved[track_id] = (time.time() + config.ACTIVITY_RESOLVE_TTL, url, headers)
    return url, headers


def _lavalink_nodes() -> list[tuple[str, str, str]]:
    nodes = []
    for node in config.LAVALINK_NODES:
        scheme = "https" if node.get("secure") else "http"
        base = f"{scheme}://{node['host']}:{node['port']}"
        nodes.append((str(node.get("identifier") or node["host"]), base, str(node.get("password", ""))))
    return nodes


def _resolve_lavalink(track_id: str) -> tuple[str, dict]:
    if _lavalink_pause[0] > time.time():
        raise LookupError("paused after the node refused requests")
    last: Optional[Exception] = None
    client = os.getenv("ZYRO_LAVALINK_CLIENT", "").strip()
    for _, base, password in _lavalink_nodes():
        url = f"{base}/youtube/stream/{track_id}" + (f"?withClient={client}" if client else "")
        headers = {"Authorization": password}
        try:
            probe = requests.get(url, headers={**headers, "Range": "bytes=0-1"}, stream=True, timeout=(6, 20))
        except requests.RequestException as exc:
            last = exc
            continue
        status, kind = probe.status_code, probe.headers.get("Content-Type", "")
        probe.close()
        if status == 429:
            _lavalink_pause[0] = time.time() + 180
        if status in (200, 206) and (kind.startswith("audio/") or kind.startswith("video/") or kind == "application/octet-stream"):
            return url, headers
        last = LookupError(f"Lavalink answered {status}")
    raise last or LookupError("No Lavalink node is configured.")


def _resolve_alternative(track_id: str, hint: dict, original: Exception) -> tuple[str, dict]:
    notes: list[str] = []
    try:
        url, headers = _resolve_lavalink(track_id)
        with _lock:
            _alt.pop(track_id, None)
            _resolved[track_id] = (time.time() + config.ACTIVITY_RESOLVE_TTL, url, headers)
        return url, headers
    except Exception as exc:
        notes.append(f"lavalink: {str(exc)[:80]}")
    alt = _alt.get(track_id)
    try:
        if not alt:
            details: dict = {}
            alt = _find_alternative(hint, details)
            if not alt:
                notes.append(f"soundcloud: no close match for '{details.get('query', '')}' among {len(details.get('candidates', []))} results")
        if alt:
            url, headers = _resolve_soundcloud(alt)
            with _lock:
                if len(_alt) > 500:
                    _alt.clear()
                _alt[track_id] = alt
                if len(_resolved) > 500:
                    _resolved.clear()
                _resolved[track_id] = (time.time() + config.ACTIVITY_RESOLVE_TTL, url, headers)
            return url, headers
    except Exception as exc:
        notes.append(f"soundcloud: {str(exc)[:80]}")
    raise LookupError(f"{original} | {'; '.join(notes)}")


def friendly(exc: Exception) -> str:
    text = str(exc).lower()
    if "sign in to confirm" in text or "not a bot" in text or "cookies" in text:
        return "YouTube is blocking this server. The bot owner needs to add cookies."
    if "429" in text or "too many requests" in text:
        return "YouTube is rate limiting this server. Try again in a minute."
    if "requested format is not available" in text or "no video formats" in text:
        return "No playable audio was found for this song."
    if "private" in text or "unavailable" in text or "removed" in text or "age" in text:
        return "This song is unavailable."
    return "Could not prepare this song."


def start_prepare(track_id: str) -> None:
    hit = _resolved.get(track_id)
    if hit and hit[0] > time.time():
        return
    with _lock:
        if track_id in _inflight:
            return
        _failed.pop(track_id, None)
        future = _pool.submit(resolve, track_id)
        _inflight[track_id] = future

    def done(finished, key=track_id):
        _inflight.pop(key, None)
        error = finished.exception()
        if error is not None:
            log.warning("Could not prepare %s: %s", key, str(error)[:400])
            with _lock:
                if len(_failed) > 300:
                    _failed.clear()
                _failed[key] = (time.time() + 120, friendly(error), str(error)[:400])

    future.add_done_callback(done)


def prepare(track_id: str):
    hit = _resolved.get(track_id)
    if hit and hit[0] > time.time():
        return hit[1], hit[2]
    with _lock:
        future = _inflight.get(track_id)
        if future is None:
            future = _pool.submit(resolve, track_id)
            _inflight[track_id] = future
            future.add_done_callback(lambda _f, key=track_id: _inflight.pop(key, None))
    return future.result(timeout=PLAY_WAIT)


def register(app, ipc: BotClient, session_secret: str) -> None:
    bp = Blueprint("activity", __name__)
    client_id = os.getenv("ZYRO_CLIENT_ID", "")
    client_secret = os.getenv("ZYRO_CLIENT_SECRET", "")

    def sign(uid: str, track_id: str, exp: int) -> str:
        return hmac.new(session_secret.encode(), f"{uid}:{track_id}:{exp}".encode(), hashlib.sha256).hexdigest()[:40]

    def current_user() -> Optional[dict]:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer ") or len(header) > 200:
            return None
        token = header[7:].strip()
        digest = hashlib.sha256(token.encode()).hexdigest()
        hit = _users.get(digest)
        if hit and hit[0] > time.time():
            return hit[1]
        try:
            reply = requests.get(f"{DISCORD_API}/users/@me", headers={"Authorization": f"Bearer {token}"}, timeout=8)
        except requests.RequestException:
            return None
        if reply.status_code != 200:
            return None
        data = reply.json()
        user = {"id": str(data["id"]), "name": data.get("global_name") or data.get("username") or "", "avatar": data.get("avatar") or ""}
        with _lock:
            if len(_users) > 2000:
                _users.clear()
            _users[digest] = (time.time() + 300, user)
        return user

    @bp.before_request
    def feature_gate():
        path = request.path
        if not path.startswith("/activity/api/"):
            return None
        tail = path[len("/activity/api/"):]
        if tail.startswith("games/"):
            if not config.ACTIVITY_GAMES:
                return _json_error("The games app is turned off on this bot.", 404)
        elif tail.split("/")[0] not in ("token", "me"):
            if not config.ACTIVITY_MUSIC:
                return _json_error("The music app is turned off on this bot.", 404)
        return None

    def need_user():
        if not config.ACTIVITY_ENABLED or not client_id or not client_secret:
            return None, _json_error("The music activity is not set up on this bot.", 503)
        user = current_user()
        if user is None:
            return None, _json_error("Sign in again.", 401)
        return user, None

    def bot_call(user: dict, method: str, path: str, body=None):
        try:
            return jsonify(ipc.request(method, path, user["id"], body))
        except BotUnavailable:
            return _json_error("The bot is restarting. Try again in a moment.", 503)
        except BotError as exc:
            return _json_error(exc.message, exc.status)

    @bp.errorhandler(Exception)
    def api_errors(error):
        if not request.path.startswith("/activity/api/"):
            if isinstance(error, HTTPException):
                return error
            raise error
        if isinstance(error, HTTPException):
            return _json_error(error.description or error.name, error.code or 500)
        log.error("Activity request failed: %s %s", request.method, request.path, exc_info=True)
        return _json_error("The music server hit an error.", 500)

    @bp.route("/activity")
    def activity_redirect():
        return Response(status=302, headers={"Location": "/activity/"})

    def build_id() -> str:
        digest = hashlib.sha1()
        for name in ("app.js", "app.css", "discord.js", "games.js", "doom.js"):
            try:
                digest.update(str(os.stat(os.path.join(STATIC, name)).st_mtime_ns).encode())
            except OSError:
                pass
        return digest.hexdigest()[:8]

    @bp.route("/activity/")
    def activity_page():
        response = Response(render_template("activity.html", build=build_id(), client_id=client_id, enabled=bool(config.ACTIVITY_ENABLED and client_id and client_secret), music=config.ACTIVITY_MUSIC, games=",".join(name for name, on in config.ACTIVITY_GAME_LIST.items() if on)))
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.route("/activity/<path:name>")
    def activity_static(name: str):
        if name.startswith("api/") or "/" in name:
            abort(404)
        response = send_from_directory(STATIC, name, max_age=0)
        response.headers["Cache-Control"] = "no-cache"
        return response

    @bp.route("/activity/api/token", methods=["POST"])
    def token():
        if not config.ACTIVITY_ENABLED or not client_id or not client_secret:
            return _json_error("The music activity is not set up on this bot.", 503)
        code = str((request.get_json(silent=True) or {}).get("code", ""))
        if not code or len(code) > 200:
            return _json_error("Missing code.", 400)
        try:
            reply = requests.post(
                f"{DISCORD_API}/oauth2/token",
                data={"client_id": client_id, "client_secret": client_secret, "grant_type": "authorization_code", "code": code},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10,
            )
        except requests.RequestException:
            return _json_error("Discord did not answer. Try again.", 502)
        if reply.status_code != 200:
            return _json_error("Discord refused the sign in.", 401)
        return jsonify(access_token=reply.json().get("access_token", ""))

    @bp.route("/activity/api/me")
    def me():
        user, error = need_user()
        if error:
            return error
        return jsonify({**user, "admin": int(user["id"]) in config.ALL_PRIVILEGED_IDS})

    @bp.route("/activity/api/diag")
    def diag():
        user, error = need_user()
        if error:
            return error
        privileged = int(user["id"]) in config.ALL_PRIVILEGED_IDS
        report = {"you": user["id"], "owner": privileged}
        if not privileged:
            report["note"] = "Your account id is not in devs.json for the dashboard process, so only basic checks run."
        report.update({"python_threads": threading.active_count(), "node": shutil.which("node"), "deno": shutil.which("deno"), "cookies": bool(_cookie_file()), "js_runtime_setting": os.getenv("ZYRO_YTDLP_JS_RUNTIME", "")} if privileged else {})
        try:
            yt_dlp = _extractor()
            report["yt_dlp"] = getattr(getattr(yt_dlp, "version", None), "__version__", "unknown")
        except Exception as exc:
            report["yt_dlp"] = f"missing: {exc}"
            return jsonify(report)
        started = time.time()
        try:
            found = search_tracks("test song official audio", 3)
            report["search_ok"] = bool(found)
        except Exception as exc:
            report["search_ok"] = False
            report["search_error"] = str(exc)[:400]
        report["search_seconds"] = round(time.time() - started, 1)
        started = time.time()
        try:
            wanted = request.args.get("id", "")
            test_id = wanted if TRACK_ID.match(wanted) else "dQw4w9WgXcQ"
            trail: list = []
            report["test_video"] = test_id
            try:
                url, headers = resolve(test_id, fresh=True, trail=trail)
            finally:
                if trail:
                    report["attempts"] = trail
            report["resolve_ok"] = True
            try:
                probe = requests.get(url, headers={**headers, "Range": "bytes=0-1023"}, stream=True, timeout=(8, 15))
                report["stream_status"] = probe.status_code
                report["stream_type"] = probe.headers.get("Content-Type", "")
                probe.close()
            except requests.RequestException as exc:
                report["stream_status"] = "failed"
                report["stream_error"] = str(exc)[:300]
        except Exception as exc:
            report["resolve_ok"] = False
            report["resolve_error"] = str(exc)[:600] if privileged else friendly(exc)
            report["cookie_names"] = sorted(_cookie_names()) if privileged else []
        report["resolve_seconds"] = round(time.time() - started, 1)
        if privileged and request.args.get("title"):
            hint = {"title": request.args.get("title", "")[:150], "artist": request.args.get("artist", "")[:100], "duration": int(request.args.get("duration", "0") or 0) if request.args.get("duration", "0").isdigit() else 0}
            details = {}
            try:
                chosen = _find_alternative(hint, details)
                details["chosen"] = chosen
                if chosen:
                    try:
                        _resolve_soundcloud(chosen)
                        details["resolve"] = "ok"
                    except Exception as exc:
                        details["resolve"] = str(exc)[:200]
            except Exception as exc:
                details["error"] = str(exc)[:200]
            report["soundcloud_fallback"] = details
        if privileged:
            nodes = []
            for name, base, password in _lavalink_nodes():
                entry = {"node": name}
                try:
                    info = requests.get(f"{base}/v4/info", headers={"Authorization": password}, timeout=8)
                    entry["info_status"] = info.status_code
                    if info.status_code == 200:
                        data = info.json()
                        entry["plugins"] = [f"{p.get('name')} {p.get('version')}" for p in ((data.get("plugins") if isinstance(data, dict) else None) or [])]
                    stream = requests.get(f"{base}/youtube/stream/dQw4w9WgXcQ", headers={"Authorization": password, "Range": "bytes=0-1"}, stream=True, timeout=(6, 20))
                    entry["stream_status"] = stream.status_code
                    entry["stream_type"] = stream.headers.get("Content-Type", "")
                    stream.close()
                except requests.RequestException as exc:
                    entry["error"] = str(exc)[:200]
                except Exception as exc:
                    entry["error"] = str(exc)[:200]
                nodes.append(entry)
            report["lavalink"] = nodes
        if privileged and _cookie_file():
            report["cookies_missing_psidts"] = not ({"__Secure-1PSIDTS", "__Secure-3PSIDTS"} & _cookie_names())
        return jsonify(report)

    @bp.route("/activity/api/search")
    def search():
        user, error = need_user()
        if error:
            return error
        query = request.args.get("q", "").strip()[:100]
        if len(query) < 2:
            return jsonify(tracks=[])
        if not _hit(user["id"], "search"):
            return _json_error("Slow down a little.", 429)
        try:
            if request.args.get("source") == "soundcloud":
                return jsonify(tracks=search_soundcloud(query, config.ACTIVITY_SEARCH_RESULTS))
            return jsonify(tracks=search_tracks(query, config.ACTIVITY_SEARCH_RESULTS))
        except Exception:
            return _json_error("Search is unavailable right now.", 502)

    @bp.route("/activity/api/home")
    def home():
        user, error = need_user()
        if error:
            return error
        if not _hit(user["id"], "home"):
            return _json_error("Slow down a little.", 429)
        seeds: list[str] = []
        try:
            library = ipc.request("GET", "/activity/library", user["id"])
            for item in (library.get("likes") or [])[:20] + (library.get("history") or [])[:20]:
                artist = (item.get("artist") or "").strip()
                if artist and artist not in seeds:
                    seeds.append(artist)
        except (BotUnavailable, BotError):
            pass
        queries = [f"{artist} songs" for artist in seeds[:2]]
        day = int(time.time() // 86400)
        generic = list(config.ACTIVITY_HOME_QUERIES)
        queries += [generic[(day + i) % len(generic)] for i in range(2 if queries else 3)]
        tracks, seen = [], set()
        for query in queries:
            try:
                for track in search_tracks(query, 8):
                    if track["id"] not in seen:
                        seen.add(track["id"])
                        tracks.append(track)
            except Exception:
                continue
        return jsonify(tracks=tracks[:24], personal=bool(seeds))

    def source_for(user_id: str, track_id: str) -> str:
        exp = int(time.time()) + config.ACTIVITY_STREAM_TTL
        return f"api/stream/{track_id}?u={user_id}&e={exp}&s={sign(user_id, track_id, exp)}"

    def readiness(user: dict, track_id: str):
        hit = _resolved.get(track_id)
        if hit and hit[0] > time.time():
            return jsonify(state="ready", src=source_for(user["id"], track_id), via="soundcloud" if track_id in _alt else "")
        failure = _failed.get(track_id)
        if failure and failure[0] > time.time():
            body = {"state": "error", "error": failure[1]}
            if int(user["id"]) in config.ALL_PRIVILEGED_IDS:
                body["detail"] = failure[2]
            return jsonify(body)
        if track_id not in _inflight:
            start_prepare(track_id)
        return jsonify(state="pending")

    @bp.route("/activity/api/play", methods=["POST"])
    def play():
        user, error = need_user()
        if error:
            return error
        body = request.get_json(silent=True) or {}
        track_id = str(body.get("id", ""))
        if not TRACK_ID.match(track_id):
            return _json_error("Invalid song.", 400)
        if not _hit(user["id"], "play"):
            return _json_error("Slow down a little.", 429)
        try:
            duration = int(body.get("duration") or 0)
        except (TypeError, ValueError):
            duration = 0
        if not SC_ID.match(track_id):
            with _lock:
                if len(_hints) > 500:
                    _hints.clear()
                _hints[track_id] = {"title": str(body.get("title", ""))[:150], "artist": str(body.get("artist", ""))[:100], "duration": duration}
        start_prepare(track_id)
        return readiness(user, track_id)

    @bp.route("/activity/api/ready/<track_id>")
    def ready(track_id: str):
        user, error = need_user()
        if error:
            return error
        if not TRACK_ID.match(track_id):
            return _json_error("Invalid song.", 400)
        return readiness(user, track_id)

    def blob_response(data: bytes, content_type: str):
        size = len(data)
        start, end, status = 0, size - 1, 200
        match = re.match(r"^bytes=(\d*)-(\d*)$", request.headers.get("Range", ""))
        if match and (match.group(1) or match.group(2)):
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else size - 1
            else:
                start = max(0, size - int(match.group(2)))
            end = min(end, size - 1)
            if start > end:
                response = Response(status=416)
                response.headers["Content-Range"] = f"bytes */{size}"
                return response
            status = 206
        response = Response(data[start:end + 1], status=status, mimetype=content_type)
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Content-Length"] = str(end - start + 1)
        if status == 206:
            response.headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        response.headers["Cache-Control"] = "private, max-age=3600"
        return response

    @bp.route("/activity/api/stream/<track_id>")
    def stream(track_id: str):
        uid, sig = request.args.get("u", ""), request.args.get("s", "")
        try:
            exp = int(request.args.get("e", "0"))
        except ValueError:
            abort(403)
        if not TRACK_ID.match(track_id) or not uid.isdigit() or exp < time.time() or not hmac.compare_digest(sign(uid, track_id, exp), sig):
            abort(403)
        upstream = None
        for attempt in (False, True):
            try:
                url, headers = resolve(track_id, fresh=attempt) if attempt else prepare(track_id)
            except Exception as exc:
                log.warning("Stream resolve failed for %s: %s", track_id, str(exc)[:300])
                abort(502)
            if url.startswith("blob:"):
                blob = _blobs.get(url[5:])
                if blob is None:
                    continue
                return blob_response(blob[0], blob[1])
            send = dict(headers)
            if request.headers.get("Range"):
                send["Range"] = request.headers["Range"]
            try:
                upstream = requests.get(url, headers=send, stream=True, timeout=(8, 30))
            except requests.RequestException:
                upstream = None
                continue
            if upstream.status_code in (200, 206):
                break
            upstream.close()
            upstream = None
        if upstream is None:
            abort(502)

        def body():
            try:
                for chunk in upstream.iter_content(CHUNK):
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        response = Response(body(), status=upstream.status_code)
        for name in ("Content-Type", "Content-Length", "Content-Range"):
            if upstream.headers.get(name):
                response.headers[name] = upstream.headers[name]
        response.headers["Accept-Ranges"] = "bytes"
        response.headers["Cache-Control"] = "private, max-age=3600"
        return response

    @bp.route("/activity/api/thumb/<track_id>")
    def thumb(track_id: str):
        if not TRACK_ID.match(track_id):
            abort(404)
        hit = _thumbs.get(track_id)
        if not hit or hit[0] < time.time():
            if SC_ID.match(track_id):
                source = _sc_thumbs.get(track_id) or request.args.get("src", "")
                if not re.match(r"^https://[a-z0-9.-]+\.sndcdn\.com/[\w./?=&%-]+$", source):
                    abort(404)
            else:
                source = f"https://i.ytimg.com/vi/{track_id}/mqdefault.jpg"
            try:
                reply = requests.get(source, timeout=8)
            except requests.RequestException:
                abort(502)
            if reply.status_code != 200 or len(reply.content) > 400000:
                abort(404)
            hit = (time.time() + 86400, reply.content, reply.headers.get("Content-Type", "image/jpeg"))
            with _lock:
                if len(_thumbs) > 400:
                    _thumbs.clear()
                _thumbs[track_id] = hit
        response = Response(hit[1], mimetype=hit[2])
        response.headers["Cache-Control"] = "public, max-age=86400"
        return response

    @bp.route("/activity/api/library")
    def library():
        user, error = need_user()
        return error or bot_call(user, "GET", "/activity/library")

    def write(path: str):
        user, error = need_user()
        if error:
            return error
        if not _hit(user["id"], "write"):
            return _json_error("Slow down a little.", 429)
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or len(json.dumps(body)) > 4000:
            return _json_error("Invalid request.", 400)
        return bot_call(user, "POST", path, body)

    @bp.route("/activity/api/like", methods=["POST"])
    def like():
        return write("/activity/like")

    @bp.route("/activity/api/history", methods=["POST"])
    def history_add():
        return write("/activity/history")

    @bp.route("/activity/api/history/clear", methods=["POST"])
    def history_clear():
        return write("/activity/history/clear")

    @bp.route("/activity/api/playlists", methods=["POST"])
    def playlist_create():
        return write("/activity/playlists")

    @bp.route("/activity/api/playlists/<pid>", methods=["POST"])
    def playlist_action(pid: str):
        if not re.fullmatch(r"[a-f0-9]{10}", pid):
            abort(404)
        return write(f"/activity/playlists/{pid}")

    games.register(bp, need_user, _json_error, _hit, lambda: config.ACTIVITY_GAME_LIST)
    doom.register(bp, need_user, _json_error, _hit, lambda: config.ACTIVITY_GAME_LIST)
    app.register_blueprint(bp)
