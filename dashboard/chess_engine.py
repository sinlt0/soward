from typing import Optional

FILES = "abcdefgh"
START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
KNIGHT = ((1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2))
KING = ((1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1))
BISHOP = ((1, 1), (-1, 1), (-1, -1), (1, -1))
ROOK = ((1, 0), (0, 1), (-1, 0), (0, -1))
PROMOTIONS = "qrbn"


class Position:
    __slots__ = ("board", "turn", "castling", "ep", "half", "full")

    def __init__(self, board, turn, castling, ep, half, full):
        self.board = board
        self.turn = turn
        self.castling = castling
        self.ep = ep
        self.half = half
        self.full = full

    def copy(self) -> "Position":
        return Position(self.board[:], self.turn, self.castling, self.ep, self.half, self.full)


def square_name(index: int) -> str:
    return f"{FILES[index % 8]}{index // 8 + 1}"


def square_index(name: str) -> int:
    if len(name) != 2 or name[0] not in FILES or name[1] not in "12345678":
        raise ValueError("bad square")
    return (int(name[1]) - 1) * 8 + FILES.index(name[0])


def is_white(piece: str) -> bool:
    return piece.isupper()


def from_fen(fen: str) -> Position:
    parts = fen.split()
    rows = parts[0].split("/")
    if len(rows) != 8:
        raise ValueError("bad fen")
    board = ["."] * 64
    for row_index, row in enumerate(rows):
        rank = 7 - row_index
        file = 0
        for char in row:
            if char.isdigit():
                file += int(char)
            else:
                board[rank * 8 + file] = char
                file += 1
    turn = parts[1] if len(parts) > 1 else "w"
    castling = parts[2] if len(parts) > 2 and parts[2] != "-" else ""
    ep = square_index(parts[3]) if len(parts) > 3 and parts[3] != "-" else -1
    half = int(parts[4]) if len(parts) > 4 else 0
    full = int(parts[5]) if len(parts) > 5 else 1
    return Position(board, turn, castling, ep, half, full)


def to_fen(pos: Position) -> str:
    rows = []
    for rank in range(7, -1, -1):
        row, empty = "", 0
        for file in range(8):
            piece = pos.board[rank * 8 + file]
            if piece == ".":
                empty += 1
            else:
                if empty:
                    row += str(empty)
                    empty = 0
                row += piece
        if empty:
            row += str(empty)
        rows.append(row)
    ep = square_name(pos.ep) if pos.ep >= 0 else "-"
    return f"{'/'.join(rows)} {pos.turn} {pos.castling or '-'} {ep} {pos.half} {pos.full}"


def start_position() -> Position:
    return from_fen(START_FEN)


def attacked(board: list, square: int, by_white: bool) -> bool:
    file, rank = square % 8, square // 8
    pawn = "P" if by_white else "p"
    pawn_rank = rank - 1 if by_white else rank + 1
    if 0 <= pawn_rank < 8:
        for df in (-1, 1):
            f = file + df
            if 0 <= f < 8 and board[pawn_rank * 8 + f] == pawn:
                return True
    knight = "N" if by_white else "n"
    for df, dr in KNIGHT:
        f, r = file + df, rank + dr
        if 0 <= f < 8 and 0 <= r < 8 and board[r * 8 + f] == knight:
            return True
    king = "K" if by_white else "k"
    for df, dr in KING:
        f, r = file + df, rank + dr
        if 0 <= f < 8 and 0 <= r < 8 and board[r * 8 + f] == king:
            return True
    straight = ("R", "Q") if by_white else ("r", "q")
    diagonal = ("B", "Q") if by_white else ("b", "q")
    for directions, pieces in ((ROOK, straight), (BISHOP, diagonal)):
        for df, dr in directions:
            f, r = file + df, rank + dr
            while 0 <= f < 8 and 0 <= r < 8:
                piece = board[r * 8 + f]
                if piece != ".":
                    if piece in pieces:
                        return True
                    break
                f += df
                r += dr
    return False


def king_square(board: list, white: bool) -> int:
    target = "K" if white else "k"
    return board.index(target)


def in_check(pos: Position, white: Optional[bool] = None) -> bool:
    side = pos.turn == "w" if white is None else white
    try:
        square = king_square(pos.board, side)
    except ValueError:
        return False
    return attacked(pos.board, square, not side)


def pseudo_moves(pos: Position) -> list:
    board = pos.board
    white = pos.turn == "w"
    moves = []
    for square in range(64):
        piece = board[square]
        if piece == "." or is_white(piece) != white:
            continue
        kind = piece.lower()
        file, rank = square % 8, square // 8
        if kind == "p":
            step = 1 if white else -1
            start_rank = 1 if white else 6
            last_rank = 7 if white else 0
            r = rank + step
            if 0 <= r < 8:
                target = r * 8 + file
                if board[target] == ".":
                    if r == last_rank:
                        for promo in PROMOTIONS:
                            moves.append((square, target, promo))
                    else:
                        moves.append((square, target, ""))
                        if rank == start_rank and board[(rank + 2 * step) * 8 + file] == ".":
                            moves.append((square, (rank + 2 * step) * 8 + file, ""))
                for df in (-1, 1):
                    f = file + df
                    if not 0 <= f < 8:
                        continue
                    target = r * 8 + f
                    other = board[target]
                    if other != "." and is_white(other) != white:
                        if r == last_rank:
                            for promo in PROMOTIONS:
                                moves.append((square, target, promo))
                        else:
                            moves.append((square, target, ""))
                    elif target == pos.ep and other == ".":
                        moves.append((square, target, ""))
        elif kind == "n":
            for df, dr in KNIGHT:
                f, r = file + df, rank + dr
                if 0 <= f < 8 and 0 <= r < 8:
                    other = board[r * 8 + f]
                    if other == "." or is_white(other) != white:
                        moves.append((square, r * 8 + f, ""))
        elif kind == "k":
            for df, dr in KING:
                f, r = file + df, rank + dr
                if 0 <= f < 8 and 0 <= r < 8:
                    other = board[r * 8 + f]
                    if other == "." or is_white(other) != white:
                        moves.append((square, r * 8 + f, ""))
            home = 4 if white else 60
            if square == home and not attacked(board, home, not white):
                king_right, queen_right = ("K", "Q") if white else ("k", "q")
                rook = "R" if white else "r"
                if king_right in pos.castling and board[home + 3] == rook and board[home + 1] == "." and board[home + 2] == "." \
                        and not attacked(board, home + 1, not white) and not attacked(board, home + 2, not white):
                    moves.append((square, home + 2, ""))
                if queen_right in pos.castling and board[home - 4] == rook and board[home - 1] == "." and board[home - 2] == "." and board[home - 3] == "." \
                        and not attacked(board, home - 1, not white) and not attacked(board, home - 2, not white):
                    moves.append((square, home - 2, ""))
        else:
            directions = BISHOP if kind == "b" else ROOK if kind == "r" else BISHOP + ROOK
            for df, dr in directions:
                f, r = file + df, rank + dr
                while 0 <= f < 8 and 0 <= r < 8:
                    other = board[r * 8 + f]
                    if other == ".":
                        moves.append((square, r * 8 + f, ""))
                    else:
                        if is_white(other) != white:
                            moves.append((square, r * 8 + f, ""))
                        break
                    f += df
                    r += dr
    return moves


def apply(pos: Position, move: tuple) -> Position:
    source, target, promo = move
    new = pos.copy()
    board = new.board
    piece = board[source]
    white = piece.isupper()
    captured = board[target]
    board[source] = "."
    if piece.lower() == "p" and target == pos.ep and captured == ".":
        board[target + (-8 if white else 8)] = "."
        captured = "p" if white else "P"
    board[target] = (promo.upper() if white else promo.lower()) if promo else piece
    if piece.lower() == "k" and abs(target - source) == 2:
        if target > source:
            board[source + 1] = board[source + 3]
            board[source + 3] = "."
        else:
            board[source - 1] = board[source - 4]
            board[source - 4] = "."
    castling = new.castling
    if piece == "K":
        castling = castling.replace("K", "").replace("Q", "")
    elif piece == "k":
        castling = castling.replace("k", "").replace("q", "")
    for corner, right in ((0, "Q"), (7, "K"), (56, "q"), (63, "k")):
        if source == corner or target == corner:
            castling = castling.replace(right, "")
    new.castling = castling
    new.ep = -1
    if piece.lower() == "p" and abs(target - source) == 16:
        middle = (source + target) // 2
        enemy = "p" if white else "P"
        file = target % 8
        for df in (-1, 1):
            f = file + df
            if 0 <= f < 8 and board[(target // 8) * 8 + f] == enemy:
                new.ep = middle
                break
    new.half = 0 if piece.lower() == "p" or captured != "." else pos.half + 1
    if pos.turn == "b":
        new.full += 1
    new.turn = "b" if pos.turn == "w" else "w"
    return new


def legal_moves(pos: Position) -> list:
    white = pos.turn == "w"
    result = []
    for move in pseudo_moves(pos):
        after = apply(pos, move)
        if not attacked(after.board, king_square(after.board, white), not white):
            result.append(move)
    return result


def move_text(move: tuple) -> str:
    return square_name(move[0]) + square_name(move[1]) + move[2]


def parse_move(text: str) -> tuple:
    if len(text) not in (4, 5):
        raise ValueError("bad move")
    promo = text[4].lower() if len(text) == 5 else ""
    if promo and promo not in PROMOTIONS:
        raise ValueError("bad promotion")
    return (square_index(text[0:2]), square_index(text[2:4]), promo)


def insufficient_material(board: list) -> bool:
    pieces = [(i, p) for i, p in enumerate(board) if p not in (".", "K", "k")]
    if not pieces:
        return True
    if any(p.lower() in "pqr" for _, p in pieces):
        return False
    if len(pieces) == 1:
        return True
    if all(p.lower() == "b" for _, p in pieces):
        colors = {((i % 8) + (i // 8)) % 2 for i, _ in pieces}
        return len(colors) == 1
    return False


def repetition_key(pos: Position) -> str:
    return " ".join(to_fen(pos).split()[:4])


def san(pos: Position, move: tuple, legal: Optional[list] = None) -> str:
    legal = legal if legal is not None else legal_moves(pos)
    source, target, promo = move
    piece = pos.board[source]
    kind = piece.upper()
    if kind == "K" and abs(target - source) == 2:
        text = "O-O" if target > source else "O-O-O"
    else:
        capture = pos.board[target] != "." or (kind == "P" and target == pos.ep)
        if kind == "P":
            text = (FILES[source % 8] + "x" if capture else "") + square_name(target)
            if promo:
                text += "=" + promo.upper()
        else:
            rivals = [m for m in legal if m[1] == target and m[0] != source and pos.board[m[0]] == piece]
            disambiguation = ""
            if rivals:
                if all(m[0] % 8 != source % 8 for m in rivals):
                    disambiguation = FILES[source % 8]
                elif all(m[0] // 8 != source // 8 for m in rivals):
                    disambiguation = str(source // 8 + 1)
                else:
                    disambiguation = square_name(source)
            text = kind + disambiguation + ("x" if capture else "") + square_name(target)
    after = apply(pos, move)
    if in_check(after):
        text += "#" if not legal_moves(after) else "+"
    return text


def game_state(pos: Position, history: dict) -> Optional[dict]:
    if not legal_moves(pos):
        if in_check(pos):
            return {"winner": "b" if pos.turn == "w" else "w", "reason": "checkmate"}
        return {"winner": None, "reason": "stalemate"}
    if insufficient_material(pos.board):
        return {"winner": None, "reason": "insufficient material"}
    if history.get(repetition_key(pos), 0) >= 3:
        return {"winner": None, "reason": "threefold repetition"}
    if pos.half >= 100:
        return {"winner": None, "reason": "fifty-move rule"}
    return None


def perft(pos: Position, depth: int) -> int:
    if depth == 0:
        return 1
    moves = legal_moves(pos)
    if depth == 1:
        return len(moves)
    return sum(perft(apply(pos, move), depth - 1) for move in moves)
