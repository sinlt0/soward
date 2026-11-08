import hashlib
import re
import secrets
import struct
import threading
import time

from flask import Response, jsonify, request

INSTANCE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
ROOM_ID = re.compile(r"^[0-9a-f]{8}$")
TICRATE = 35
ROOMS_PER_INSTANCE = 10
HOSTED_PER_USER = 1
MAX_PLAYERS = 24
ACTIVE_WINDOW = 6.0
VOTER_WINDOW = 20.0
IDLE_TTL = 1800
LOADING_TTL = 600
MAX_EVENTS = 150000
MIN_HOLD_TICS = 2
WAD_MAX_FILES = 4
WAD_MAX_FILE = 16 * 1024 * 1024
WAD_MAX_TOTAL = 24 * 1024 * 1024
WAD_MEMORY_BUDGET = 128 * 1024 * 1024
WAD_CHUNK = 192 * 1024
TURN_CHOICES = (30, 60, 120, 300)
CONTROLS = ("turns", "vote")
SKILLS = (1, 2, 3, 4, 5)
STARTS = ("map", "title")

ALLOWED_KEYS = frozenset(
    [9, 13, 27, 32, 39, 42, 44, 45, 46, 47, 59, 61, 91, 93, 127, 157, 172, 173, 174, 175, 182, 184]
    + list(range(48, 58))
    + list(range(97, 123))
)

_lock = threading.RLock()
_rooms: dict = {}


class DoomError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class Room:
    def __init__(self, room_id: str, instance: str, host: dict, control: str, skill: int, start: str, turn_seconds: int, wads: list):
        now = time.monotonic()
        self.id = room_id
        self.instance = instance
        self.host = host
        self.control = control
        self.skill = skill
        self.start = start
        self.turn_seconds = turn_seconds
        self.wads = wads
        self.status = "loading" if wads else "running"
        self.created = now
        self.touched = now
        self.epoch = 1
        self.version = 1
        self.players: dict = {}
        self.order: list = []
        self.controller = ""
        self.turn_started = now
        self.reset_game(now)

    def reset_game(self, now: float) -> None:
        self.log: list = []
        self.base_tic = 0
        self.running_since = None
        self.effective: set = set()
        self.last_stamp: dict = {}
        self.last_down: dict = {}
        for player in self.players.values():
            player["held"] = set()
        self.turn_started = now


def _player(user: dict) -> dict:
    return {"id": user["id"], "name": (user.get("name") or "Player")[:40], "avatar": user.get("avatar", "")}


def _wad_bytes() -> int:
    return sum(len(w["data"]) for room in _rooms.values() for w in room.wads)


def _sweep() -> None:
    now = time.monotonic()
    for room_id in list(_rooms):
        room = _rooms[room_id]
        if (room.status == "loading" and now - room.created > LOADING_TTL) or now - room.touched > IDLE_TTL:
            del _rooms[room_id]


def _get(room_id: str, instance: str) -> Room:
    room = _rooms.get(room_id)
    if room is None or room.instance != instance:
        raise DoomError("That room no longer exists.", 404)
    return room


def _present(room: Room, now: float) -> list:
    return [uid for uid in room.order if uid in room.players and now - room.players[uid]["seen"] <= ACTIVE_WINDOW]


def _tic(room: Room, now: float) -> int:
    if room.running_since is None:
        return room.base_tic
    return room.base_tic + int((now - room.running_since) * TICRATE)


def _clock(room: Room, now: float) -> None:
    present = _present(room, now)
    if present and room.running_since is None:
        room.running_since = now
    elif not present and room.running_since is not None:
        newest = max((p["seen"] for p in room.players.values()), default=now)
        room.base_tic = _tic(room, min(now, newest + ACTIVE_WINDOW))
        room.running_since = None


def _emit(room: Room, key: int, down: bool, now: float) -> None:
    if len(room.log) >= MAX_EVENTS:
        return
    stamp = _tic(room, now) + 1
    last = room.last_stamp.get(key, 0)
    if down:
        stamp = max(stamp, last + 1)
        room.last_down[key] = stamp
    else:
        stamp = max(stamp, room.last_down.get(key, 0) + MIN_HOLD_TICS, last + 1)
    room.last_stamp[key] = stamp
    room.log.append([stamp, key, 1 if down else 0])
    room.version += 1


def _desired(room: Room, now: float) -> set:
    if room.control == "turns":
        player = room.players.get(room.controller)
        return set(player["held"]) if player else set()
    voters = [p for p in room.players.values() if now - p["seen"] <= ACTIVE_WINDOW and now - p["input"] <= VOTER_WINDOW]
    if not voters:
        return set()
    counts: dict = {}
    for p in voters:
        for key in p["held"]:
            counts[key] = counts.get(key, 0) + 1
    return {key for key, count in counts.items() if count * 2 > len(voters)}


def _recompute(room: Room, now: float) -> None:
    wanted = _desired(room, now)
    for key in sorted(room.effective - wanted):
        _emit(room, key, False, now)
    for key in sorted(wanted - room.effective):
        _emit(room, key, True, now)
    room.effective = wanted


def _rotate(room: Room, now: float) -> None:
    present = _present(room, now)
    if not present:
        room.controller = ""
        return
    if room.controller in present:
        index = (present.index(room.controller) + 1) % len(present)
    else:
        index = 0
    room.controller = present[index]
    room.turn_started = now
    room.version += 1


def _tick_state(room: Room, now: float) -> None:
    _clock(room, now)
    if room.control == "turns":
        present = _present(room, now)
        if room.controller not in present:
            _rotate(room, now)
        elif len(present) > 1 and now - room.turn_started >= room.turn_seconds:
            _rotate(room, now)
    _recompute(room, now)


def _join(room: Room, user: dict, now: float) -> dict:
    info = _player(user)
    entry = room.players.get(user["id"])
    if entry is None:
        if len(room.players) >= MAX_PLAYERS:
            raise DoomError("This room is full.", 400)
        entry = {**info, "held": set(), "seen": now, "input": 0.0}
        room.players[user["id"]] = entry
        room.order.append(user["id"])
        room.version += 1
    else:
        if now - entry["seen"] > ACTIVE_WINDOW:
            entry["held"] = set()
        entry.update(info)
    return entry


def _leave(room: Room, uid: str, now: float) -> None:
    if uid in room.players:
        room.players[uid]["held"] = set()
        del room.players[uid]
    if uid in room.order:
        room.order.remove(uid)
    room.version += 1
    _tick_state(room, now)


def _config(room: Room) -> dict:
    return {
        "id": room.id,
        "control": room.control,
        "skill": room.skill,
        "start": room.start,
        "turn_seconds": room.turn_seconds,
        "status": room.status,
        "epoch": room.epoch,
        "host": room.host["name"],
        "host_id": room.host["id"],
        "wads": [{"name": w["name"], "size": w["size"], "have": len(w["data"]), "sha1": w.get("sha1", "")} for w in room.wads],
    }


def _summary(room: Room, uid: str) -> dict:
    now = time.monotonic()
    return {
        "id": room.id,
        "game": "doom",
        "host": room.host["name"],
        "control": room.control,
        "skill": room.skill,
        "status": room.status,
        "players": len(_present(room, now)),
        "custom": bool(room.wads),
        "you": uid in room.players,
        "mine": room.host["id"] == uid,
    }


def _poll_view(room: Room, uid: str, since: int, epoch: int, now: float) -> dict:
    reset = epoch != room.epoch
    start = 0 if reset else max(0, min(since, len(room.log)))
    present = set(_present(room, now))
    players = []
    for pid in room.order:
        entry = room.players.get(pid)
        if entry is None:
            continue
        players.append({"id": pid, "name": entry["name"], "avatar": entry["avatar"], "online": pid in present, "held": len(entry["held"])})
    left = 0
    if room.control == "turns" and room.controller and len(present) > 1:
        left = max(0, int(room.turn_seconds - (now - room.turn_started)))
    return {
        "epoch": room.epoch,
        "reset": reset,
        "horizon": _tic(room, now),
        "events": room.log[start:],
        "next": len(room.log),
        "players": players,
        "controller": room.controller,
        "turn_left": left,
        "effective": sorted(room.effective),
        "status": room.status,
        "full": len(room.log) >= MAX_EVENTS,
    }


def _valid_wad(data: bytes) -> bool:
    if len(data) < 12 or data[:4] not in (b"IWAD", b"PWAD"):
        return False
    count, offset = struct.unpack("<ii", data[4:12])
    return 0 <= count <= 200000 and 12 <= offset <= len(data) and offset + count * 16 <= len(data)


def _clean_name(raw: str, taken: set) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]", "_", str(raw or "custom"))[:36].strip("._") or "custom"
    if not base.lower().endswith(".wad"):
        base += ".wad"
    name, n = base, 2
    while name.lower() in taken:
        name = base[:-4] + "-" + str(n) + ".wad"
        n += 1
    taken.add(name.lower())
    return name


def register(bp, need_user, json_error, hit, enabled_games) -> None:
    def instance_arg(source) -> str:
        value = str(source or "")
        if not INSTANCE.match(value):
            raise DoomError("This game must be opened inside Discord.", 400)
        return value

    def guarded(bucket):
        def decorate(handler):
            def wrapper(*args, **kwargs):
                user, error = need_user()
                if error:
                    return error
                if not enabled_games().get("doom"):
                    return json_error("Doom is turned off on this bot.", 404)
                if not hit(user["id"], bucket):
                    return json_error("Slow down a little.", 429)
                try:
                    return handler(user, *args, **kwargs)
                except DoomError as exc:
                    return json_error(exc.message, exc.status)
            wrapper.__name__ = handler.__name__
            return wrapper
        return decorate

    def room_arg(room_id: str, instance: str) -> Room:
        if not ROOM_ID.match(room_id):
            raise DoomError("That room no longer exists.", 404)
        return _get(room_id, instance)

    @bp.route("/activity/api/games/doom/rooms", methods=["GET"])
    @guarded("game")
    def doom_rooms(user):
        instance = instance_arg(request.args.get("instance"))
        with _lock:
            _sweep()
            items = [_summary(r, user["id"]) for r in _rooms.values() if r.instance == instance]
        items.sort(key=lambda item: (item["status"] != "running", item["id"]))
        return jsonify(rooms=items)

    @bp.route("/activity/api/games/doom/rooms", methods=["POST"])
    @guarded("game")
    def doom_create(user):
        body = request.get_json(silent=True) or {}
        instance = instance_arg(body.get("instance"))
        control = str(body.get("control", "turns"))
        if control not in CONTROLS:
            raise DoomError("Pick turns or vote.", 400)
        try:
            skill = int(body.get("skill", 3))
            turn_seconds = int(body.get("turn_seconds", 60))
        except (TypeError, ValueError):
            raise DoomError("Those settings are not valid.", 400)
        start = str(body.get("start", "map"))
        if skill not in SKILLS or start not in STARTS or turn_seconds not in TURN_CHOICES:
            raise DoomError("Those settings are not valid.", 400)
        declared = body.get("wads") or []
        if not isinstance(declared, list) or len(declared) > WAD_MAX_FILES:
            raise DoomError("Use at most %d WAD files." % WAD_MAX_FILES, 400)
        wads = []
        taken: set = set()
        total = 0
        for item in declared:
            try:
                size = int((item or {}).get("size", 0))
            except (TypeError, ValueError):
                size = 0
            if size < 12 or size > WAD_MAX_FILE:
                raise DoomError("Each WAD must be under %d MB." % (WAD_MAX_FILE // 1048576), 400)
            total += size
            wads.append({"name": _clean_name((item or {}).get("name"), taken), "size": size, "data": bytearray()})
        if total > WAD_MAX_TOTAL:
            raise DoomError("The WAD files are too large together (limit %d MB)." % (WAD_MAX_TOTAL // 1048576), 400)
        with _lock:
            _sweep()
            if sum(1 for r in _rooms.values() if r.instance == instance) >= ROOMS_PER_INSTANCE:
                raise DoomError("This session already has too many Doom rooms.", 400)
            if sum(1 for r in _rooms.values() if r.instance == instance and r.host["id"] == user["id"]) >= HOSTED_PER_USER:
                raise DoomError("Close your other Doom room first.", 400)
            if _wad_bytes() + total > WAD_MEMORY_BUDGET:
                raise DoomError("The server cannot take more WAD files right now.", 503)
            room = Room(secrets.token_hex(4), instance, _player(user), control, skill, start, turn_seconds, wads)
            _rooms[room.id] = room
            _join(room, user, time.monotonic())
            return jsonify(room=_config(room))

    @bp.route("/activity/api/games/doom/room/<room_id>", methods=["GET"])
    @guarded("game")
    def doom_room(user, room_id):
        instance = instance_arg(request.args.get("instance"))
        with _lock:
            room = room_arg(room_id, instance)
            return jsonify(room=_config(room))

    @bp.route("/activity/api/games/doom/room/<room_id>/wad/<int:index>", methods=["POST"])
    @guarded("doomwad")
    def doom_upload(user, room_id, index):
        instance = instance_arg(request.args.get("instance"))
        chunk = request.get_data(cache=False)
        if len(chunk) > WAD_CHUNK + 1024:
            raise DoomError("That chunk is too large.", 413)
        try:
            offset = int(request.args.get("offset", "-1"))
        except ValueError:
            offset = -1
        with _lock:
            room = room_arg(room_id, instance)
            if room.host["id"] != user["id"]:
                raise DoomError("Only the host can upload WAD files.", 403)
            if room.status != "loading" or index < 0 or index >= len(room.wads):
                raise DoomError("This room is not waiting for that file.", 400)
            wad = room.wads[index]
            if offset != len(wad["data"]) or len(wad["data"]) + len(chunk) > wad["size"]:
                raise DoomError("The upload is out of order. Try again.", 409)
            wad["data"].extend(chunk)
            room.touched = time.monotonic()
            if all(len(w["data"]) == w["size"] for w in room.wads):
                for w in room.wads:
                    w["data"] = bytes(w["data"])
                    if not _valid_wad(w["data"]):
                        del _rooms[room.id]
                        raise DoomError("%s is not a valid WAD file." % w["name"], 400)
                    w["sha1"] = hashlib.sha1(w["data"]).hexdigest()
                room.status = "running"
                room.version += 1
            return jsonify(room=_config(room))

    @bp.route("/activity/api/games/doom/room/<room_id>/wad/<int:index>", methods=["GET"])
    @guarded("doomwad")
    def doom_download(user, room_id, index):
        instance = instance_arg(request.args.get("instance"))
        with _lock:
            room = room_arg(room_id, instance)
            if room.status != "running" or index < 0 or index >= len(room.wads):
                raise DoomError("That file is not ready.", 404)
            data = room.wads[index]["data"]
        response = Response(data, mimetype="application/octet-stream")
        response.headers["Cache-Control"] = "no-store"
        return response

    @bp.route("/activity/api/games/doom/room/<room_id>/poll", methods=["GET"])
    @guarded("doom")
    def doom_poll(user, room_id):
        instance = instance_arg(request.args.get("instance"))
        try:
            since = int(request.args.get("since", "0"))
            epoch = int(request.args.get("epoch", "0"))
        except ValueError:
            since, epoch = 0, 0
        now = time.monotonic()
        with _lock:
            room = room_arg(room_id, instance)
            if room.status != "running":
                raise DoomError("This room is still loading.", 409)
            entry = _join(room, user, now)
            entry["seen"] = now
            room.touched = now
            _tick_state(room, now)
            return jsonify(_poll_view(room, user["id"], since, epoch, now))

    @bp.route("/activity/api/games/doom/room/<room_id>/input", methods=["POST"])
    @guarded("doominput")
    def doom_input(user, room_id):
        body = request.get_json(silent=True) or {}
        instance = instance_arg(body.get("instance"))
        items = body.get("keys")
        if not isinstance(items, list) or len(items) > 16:
            raise DoomError("Bad input.", 400)
        now = time.monotonic()
        with _lock:
            room = room_arg(room_id, instance)
            if room.status != "running":
                raise DoomError("This room is still loading.", 409)
            entry = _join(room, user, now)
            entry["seen"] = now
            room.touched = now
            _tick_state(room, now)
            for item in items:
                try:
                    key, down = int(item[0]), bool(item[1])
                except (TypeError, ValueError, IndexError):
                    continue
                if key not in ALLOWED_KEYS:
                    continue
                if down:
                    entry["held"].add(key)
                else:
                    entry["held"].discard(key)
                entry["input"] = now
                _recompute(room, now)
            return jsonify(ok=True, horizon=_tic(room, now))

    @bp.route("/activity/api/games/doom/room/<room_id>/<action>", methods=["POST"])
    @guarded("doom")
    def doom_action(user, room_id, action):
        body = request.get_json(silent=True) or {}
        instance = instance_arg(body.get("instance"))
        now = time.monotonic()
        with _lock:
            room = room_arg(room_id, instance)
            if action == "leave":
                _leave(room, user["id"], now)
                if not room.players and room.status == "running":
                    room.touched = now
                return jsonify(ok=True)
            if action == "pass":
                if room.control == "turns" and room.controller == user["id"]:
                    _rotate(room, now)
                    _recompute(room, now)
                return jsonify(ok=True)
            if action == "restart":
                if room.host["id"] != user["id"]:
                    raise DoomError("Only the host can restart.", 403)
                room.epoch += 1
                room.reset_game(now)
                room.version += 1
                return jsonify(ok=True)
            if action == "close":
                if room.host["id"] != user["id"]:
                    raise DoomError("Only the host can close the room.", 403)
                del _rooms[room.id]
                return jsonify(ok=True)
        raise DoomError("Unknown action.", 404)
