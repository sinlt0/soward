import random
import re
from typing import Optional

from utils import db

TTT_LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))
C4_ROWS = 6
C4_COLS = 7
RPS_CHOICES = ("rock", "paper", "scissors")
RPS_BEATS = {"rock": "scissors", "paper": "rock", "scissors": "paper"}

WORDS = (
    "anchor balloon bicycle blanket bridge butterfly cactus camera candle canyon castle chimney circus compass cookie crystal dragon "
    "eclipse elephant feather fireplace flamingo forest galaxy garden giraffe glacier guitar hammock harbor horizon iceberg jungle "
    "kangaroo kingdom ladder lantern lighthouse magnet meadow mirror mountain notebook ocean orchard oxygen paintbrush parrot pencil "
    "penguin pirate planet pumpkin puzzle rainbow raccoon rocket sandwich satellite scarecrow shadow signal skyline snowman spaceship "
    "sparrow sunrise sunflower telescope thunder tornado treasure umbrella unicorn valley volcano waterfall whistle windmill winter "
    "wizard zeppelin avocado backpack bonfire cinnamon dolphin engine firefly gravity hurricane island jigsaw keyboard lemonade "
    "marathon mushroom necklace octopus pancake quicksand raincoat sailboat tangerine vanilla walrus xylophone yogurt zucchini"
).split()

SENTENCES = (
    "The quick brown fox jumps over the lazy dog near the quiet river.",
    "A small boat drifted slowly across the glowing lake at midnight.",
    "She packed her bag, locked the door and walked toward the old station.",
    "Fresh bread, warm soup and a good book make a perfect rainy evening.",
    "The robot carefully painted a tiny blue star on every window of the house.",
    "Typing fast is mostly about staying calm and keeping your eyes on the words.",
    "Every great adventure begins with a single step and a very bad map.",
    "The library was silent except for the soft ticking of the ancient clock.",
    "Thunder rolled over the hills as the village lit its lanterns one by one.",
    "He found a mysterious key under the third stone of the garden wall.",
    "Clouds gathered above the mountain while the travelers shared their last apple.",
    "Practice makes progress, and progress makes the next challenge feel smaller.",
    "A curious cat watched the snowflakes dance past the frosted window.",
    "The orchestra tuned their instruments as the audience slowly found their seats.",
    "Please keep your hands inside the ride until it comes to a complete stop.",
    "Moonlight spilled across the desert and turned every dune into silver.",
    "The chef tasted the sauce, smiled, and added one final pinch of salt.",
    "Somewhere beyond the horizon a lighthouse keeps its patient watch over the sea.",
    "Our team shipped the update early, then celebrated with cold lemonade.",
    "Gentle waves washed the footprints from the sand as the sun went down.",
)

HANGMAN_STAGES = (
    "```\n  +---+\n  |   |\n      |\n      |\n      |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n      |\n      |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n  |   |\n      |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n /|   |\n      |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n      |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n /    |\n      |\n=========\n```",
    "```\n  +---+\n  |   |\n  O   |\n /|\\  |\n / \\  |\n      |\n=========\n```",
)


def ttt_winner(board: list[int]) -> int:
    for a, b, c in TTT_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    return 0


def ttt_full(board: list[int]) -> bool:
    return all(board)


def _minimax(board: list[int], turn: int, me: int) -> int:
    won = ttt_winner(board)
    if won:
        return 1 if won == me else -1
    if ttt_full(board):
        return 0
    other = 3 - turn
    scores = []
    for i in range(9):
        if not board[i]:
            board[i] = turn
            scores.append(_minimax(board, other, me))
            board[i] = 0
    return max(scores) if turn == me else min(scores)


def ttt_bot_move(board: list[int], me: int, mistakes: float = 0.25) -> int:
    free = [i for i in range(9) if not board[i]]
    for piece in (me, 3 - me):
        for i in free:
            board[i] = piece
            won = ttt_winner(board) == piece
            board[i] = 0
            if won and (piece == me or random.random() >= mistakes):
                return i
    if random.random() < mistakes:
        return random.choice(free)
    best, best_score = [], -2
    for i in free:
        board[i] = me
        score = _minimax(board, 3 - me, me)
        board[i] = 0
        if score > best_score:
            best, best_score = [i], score
        elif score == best_score:
            best.append(i)
    return random.choice(best)


def c4_new() -> list[list[int]]:
    return [[0] * C4_COLS for _ in range(C4_ROWS)]


def c4_drop(board: list[list[int]], col: int, piece: int) -> Optional[int]:
    for row in range(C4_ROWS - 1, -1, -1):
        if not board[row][col]:
            board[row][col] = piece
            return row
    return None


def c4_open(board: list[list[int]], col: int) -> bool:
    return not board[0][col]


def c4_full(board: list[list[int]]) -> bool:
    return all(board[0])


def c4_winner(board: list[list[int]]) -> int:
    for r in range(C4_ROWS):
        for c in range(C4_COLS):
            piece = board[r][c]
            if not piece:
                continue
            for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
                if all(0 <= r + dr * k < C4_ROWS and 0 <= c + dc * k < C4_COLS and board[r + dr * k][c + dc * k] == piece for k in range(4)):
                    return piece
    return 0


def c4_bot_move(board: list[list[int]], me: int) -> int:
    options = [c for c in range(C4_COLS) if c4_open(board, c)]
    for piece in (me, 3 - me):
        for col in options:
            row = c4_drop(board, col, piece)
            won = c4_winner(board) == piece
            board[row][col] = 0
            if won:
                return col
    safe = []
    for col in options:
        row = c4_drop(board, col, me)
        danger = False
        if row > 0:
            c4_drop(board, col, 3 - me)
            danger = c4_winner(board) == 3 - me
            board[row - 1][col] = 0
        board[row][col] = 0
        if not danger:
            safe.append(col)
    pool = safe or options
    return min(pool, key=lambda c: (abs(c - 3), random.random()))


def rps_result(a: str, b: str) -> int:
    if a == b:
        return 0
    return 1 if RPS_BEATS[a] == b else 2


def mask(word: str, guessed: set[str]) -> str:
    return " ".join(ch.upper() if ch in guessed else "_" for ch in word)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def wpm(text: str, seconds: float) -> float:
    return round((len(text) / 5) / max(seconds, 0.5) * 60, 1)


async def record(user_id: int, game: str, result: str) -> None:
    column = {"win": "wins", "loss": "losses", "draw": "draws"}[result]
    await db.raw_execute(
        f"INSERT INTO game_stats (user_id, game, {column}) VALUES (?, ?, 1)"
        f" ON CONFLICT(user_id, game) DO UPDATE SET {column}={column}+1",
        (user_id, game))


async def stats(user_id: int) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM game_stats WHERE user_id=? ORDER BY wins DESC, game", (user_id,))
    return [dict(r) for r in rows]


async def top(game: str, limit: int = 10) -> list[dict]:
    rows = await db.raw_fetch("SELECT * FROM game_stats WHERE game=? AND wins>0 ORDER BY wins DESC, losses ASC LIMIT ?", (game, limit))
    return [dict(r) for r in rows]
