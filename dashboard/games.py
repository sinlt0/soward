import re
import secrets
import threading
import time
from typing import Optional

from flask import jsonify, request

from dashboard import chess_engine as engine

INSTANCE = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
ROOM_ID = re.compile(r"^[0-9a-f]{8}$")
ROOMS_PER_INSTANCE = 20
HOSTED_PER_USER = 2
WAITING_TTL = 1800
IDLE_TTL = 7200
FINISHED_TTL = 1800

_lock = threading.RLock()
_rooms: dict = {}


class GameError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class Room:
    def __init__(self, room_id: str, instance: str, host: dict):
        self.id = room_id
        self.instance = instance
        self.game = "chess"
        self.host = host["id"]
        self.players = {"w": None, "b": None}
        self.status = "waiting"
        self.position = engine.start_position()
        self.moves: list = []
        self.counts: dict = {}
        self.result: Optional[dict] = None
        self.draw_offer: Optional[str] = None
        self.rematch: Optional[str] = None
        self.version = 1
        self.created = time.time()
        self.touched = time.time()
        self.games_played = 0

    def seat_of(self, uid: str) -> str:
        for side in ("w", "b"):
            if self.players[side] and self.players[side]["id"] == uid:
                return side
        return ""

    def bump(self) -> None:
        self.version += 1
        self.touched = time.time()


def _player(user: dict) -> dict:
    return {"id": user["id"], "name": (user.get("name") or "Player")[:40], "avatar": user.get("avatar", "")}


def _sweep() -> None:
    now = time.time()
    for room_id in list(_rooms):
        room = _rooms[room_id]
        age = now - room.touched
        if (room.status == "waiting" and age > WAITING_TTL) or (room.status == "playing" and age > IDLE_TTL) or (room.status == "finished" and age > FINISHED_TTL):
            del _rooms[room_id]


def _get(room_id: str, instance: str) -> Room:
    room = _rooms.get(room_id)
    if room is None or room.instance != instance:
        raise GameError("That room no longer exists.", 404)
    return room


def _start(room: Room) -> None:
    room.position = engine.start_position()
    room.moves = []
    room.counts = {engine.repetition_key(room.position): 1}
    room.result = None
    room.draw_offer = None
    room.rematch = None
    room.status = "playing"
    room.games_played += 1


def _finish(room: Room, winner: Optional[str], reason: str) -> None:
    room.status = "finished"
    room.result = {"winner": winner, "reason": reason}
    room.draw_offer = None
    room.rematch = None


def view(room: Room, uid: str) -> dict:
    you = room.seat_of(uid) or "s"
    pos = room.position
    legal: list = []
    check_square = -1
    if room.status == "playing":
        if you == pos.turn:
            legal = [engine.move_text(m) for m in engine.legal_moves(pos)]
        if engine.in_check(pos):
            check_square = engine.king_square(pos.board, pos.turn == "w")
    return {
        "id": room.id,
        "game": room.game,
        "status": room.status,
        "players": room.players,
        "host": room.host,
        "you": you,
        "turn": pos.turn,
        "board": "".join(pos.board),
        "legal": legal,
        "check": check_square,
        "moves": [{"m": item["m"], "san": item["san"]} for item in room.moves],
        "result": room.result,
        "drawOffer": room.draw_offer,
        "rematch": room.rematch,
        "version": room.version,
        "round": room.games_played,
    }


def summary(room: Room, uid: str = "") -> dict:
    return {
        "you": room.seat_of(uid) if uid else "",
        "id": room.id,
        "game": room.game,
        "status": room.status,
        "players": {side: (room.players[side]["name"] if room.players[side] else None) for side in ("w", "b")},
        "moves": len(room.moves),
    }


def create(user: dict, instance: str, color: str) -> Room:
    with _lock:
        _sweep()
        mine = [r for r in _rooms.values() if r.host == user["id"] and r.status != "finished"]
        if len(mine) >= HOSTED_PER_USER:
            raise GameError("You already have open rooms. Close one first.", 429)
        if sum(1 for r in _rooms.values() if r.instance == instance) >= ROOMS_PER_INSTANCE:
            raise GameError("This session has too many rooms. Try again later.", 429)
        side = color if color in ("w", "b") else secrets.choice(("w", "b"))
        room = Room(secrets.token_hex(4), instance, user)
        room.players[side] = _player(user)
        _rooms[room.id] = room
        return room


def join(room: Room, user: dict) -> None:
    with _lock:
        if room.seat_of(user["id"]):
            return
        side = next((s for s in ("w", "b") if room.players[s] is None), "")
        if not side or room.status == "finished":
            return
        room.players[side] = _player(user)
        if room.players["w"] and room.players["b"] and room.status == "waiting":
            _start(room)
        room.bump()


def close(room: Room, user: dict) -> None:
    with _lock:
        seat = room.seat_of(user["id"])
        if room.status == "playing" or not (seat or room.host == user["id"]):
            raise GameError("You cannot close this room right now.", 403)
        _rooms.pop(room.id, None)


def move(room: Room, user: dict, text: str) -> None:
    with _lock:
        seat = room.seat_of(user["id"])
        if not seat:
            raise GameError("You are not playing in this room.", 403)
        if room.status != "playing":
            raise GameError("This game is not running.", 409)
        pos = room.position
        if pos.turn != seat:
            raise GameError("It is not your turn.", 409)
        try:
            parsed = engine.parse_move(text)
        except ValueError:
            raise GameError("That move is not valid.", 400)
        legal = engine.legal_moves(pos)
        if parsed not in legal:
            raise GameError("That move is not legal.", 400)
        label = engine.san(pos, parsed, legal)
        room.position = engine.apply(pos, parsed)
        room.moves.append({"m": engine.move_text(parsed), "san": label})
        key = engine.repetition_key(room.position)
        room.counts[key] = room.counts.get(key, 0) + 1
        room.draw_offer = None
        outcome = engine.game_state(room.position, room.counts)
        if outcome:
            _finish(room, outcome["winner"], outcome["reason"])
        room.bump()


def resign(room: Room, user: dict) -> None:
    with _lock:
        seat = room.seat_of(user["id"])
        if not seat or room.status != "playing":
            raise GameError("You cannot resign right now.", 409)
        _finish(room, "b" if seat == "w" else "w", "resignation")
        room.bump()


def draw(room: Room, user: dict, action: str) -> None:
    with _lock:
        seat = room.seat_of(user["id"])
        if not seat or room.status != "playing":
            raise GameError("You cannot do that right now.", 409)
        if action == "offer":
            if room.draw_offer is None:
                room.draw_offer = seat
        elif action == "accept":
            if room.draw_offer and room.draw_offer != seat:
                _finish(room, None, "agreement")
        elif action == "decline":
            if room.draw_offer and room.draw_offer != seat:
                room.draw_offer = None
        else:
            raise GameError("Unknown action.", 400)
        room.bump()


def rematch(room: Room, user: dict) -> None:
    with _lock:
        seat = room.seat_of(user["id"])
        if not seat or room.status != "finished" or not (room.players["w"] and room.players["b"]):
            raise GameError("A rematch is not possible right now.", 409)
        if room.rematch and room.rematch != seat:
            room.players["w"], room.players["b"] = room.players["b"], room.players["w"]
            _start(room)
        else:
            room.rematch = seat
        room.bump()


def register(bp, need_user, json_error, hit, enabled_games) -> None:
    def instance_arg(source) -> str:
        value = str(source or "")
        if not INSTANCE.match(value):
            raise GameError("This game must be opened inside Discord.", 400)
        return value

    def guarded(handler):
        def wrapper(*args, **kwargs):
            user, error = need_user()
            if error:
                return error
            if not hit(user["id"], "game"):
                return json_error("Slow down a little.", 429)
            try:
                return handler(user, *args, **kwargs)
            except GameError as exc:
                return json_error(exc.message, exc.status)
        wrapper.__name__ = handler.__name__
        return wrapper

    @bp.route("/activity/api/games/rooms", methods=["GET"])
    @guarded
    def rooms_list(user):
        instance = instance_arg(request.args.get("instance"))
        with _lock:
            _sweep()
            items = [summary(r, user["id"]) for r in _rooms.values() if r.instance == instance]
        items.sort(key=lambda item: (item["status"] != "waiting", item["id"]))
        return jsonify(rooms=items)

    @bp.route("/activity/api/games/rooms", methods=["POST"])
    @guarded
    def rooms_create(user):
        body = request.get_json(silent=True) or {}
        instance = instance_arg(body.get("instance"))
        if not enabled_games().get(str(body.get("game", "chess"))):
            raise GameError("That game is not available.", 400)
        room = create(user, instance, str(body.get("color", "random")))
        return jsonify(room=view(room, user["id"]))

    @bp.route("/activity/api/games/room/<room_id>", methods=["GET"])
    @guarded
    def room_get(user, room_id):
        if not ROOM_ID.match(room_id):
            raise GameError("That room no longer exists.", 404)
        instance = instance_arg(request.args.get("instance"))
        with _lock:
            room = _get(room_id, instance)
            try:
                known = int(request.args.get("v", "0"))
            except ValueError:
                known = 0
            if known == room.version:
                return jsonify(changed=False)
            return jsonify(changed=True, room=view(room, user["id"]))

    def room_action(name, runner):
        def handler(user, room_id):
            if not ROOM_ID.match(room_id):
                raise GameError("That room no longer exists.", 404)
            body = request.get_json(silent=True) or {}
            instance = instance_arg(body.get("instance"))
            with _lock:
                room = _get(room_id, instance)
                runner(room, user, body)
                alive = _rooms.get(room.id) is room
                return jsonify(room=view(room, user["id"]) if alive else None)
        handler.__name__ = f"room_{name}"
        bp.add_url_rule(f"/activity/api/games/room/<room_id>/{name}", endpoint=f"games_{name}", view_func=guarded(handler), methods=["POST"])

    room_action("join", lambda room, user, body: join(room, user))
    room_action("move", lambda room, user, body: move(room, user, str(body.get("move", ""))))
    room_action("resign", lambda room, user, body: resign(room, user))
    room_action("draw", lambda room, user, body: draw(room, user, str(body.get("action", ""))))
    room_action("rematch", lambda room, user, body: rematch(room, user))
    room_action("close", lambda room, user, body: close(room, user))
