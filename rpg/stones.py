import re
from typing import Optional

from rpg import settings

LOW = max(1, settings.STONE_COINS_PER_LOW)
MID = LOW * max(2, settings.STONE_MID)
HIGH = MID * max(2, settings.STONE_HIGH)
GRADES = {"low": LOW, "mid": MID, "high": HIGH}
WORDS = {"low": "low", "lg": "low", "mid": "mid", "mg": "mid", "high": "high", "hg": "high"}
PATTERN = re.compile(r"^\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*(low|mid|high|lg|mg|hg)(?:[- ]?grade)?\s*$", re.I)


def to_coins(low: int = 0, mid: int = 0, high: int = 0) -> int:
    return low * LOW + mid * MID + high * HIGH


def to_stones(coins: int) -> int:
    return int(coins) // LOW


def split(coins: int) -> tuple[int, int, int]:
    stones = max(0, to_stones(coins))
    high, rest = divmod(stones * LOW, HIGH)
    mid, rest = divmod(rest, MID)
    return high, mid, rest // LOW


def fmt(coins: int) -> str:
    amount = int(coins)
    sign = "-" if amount < 0 else ""
    high, mid, low = split(abs(amount))
    parts = []
    if high:
        parts.append(f"{high:,} high-grade")
    if mid:
        parts.append(f"{mid:,} mid-grade")
    if low or not parts:
        parts.append(f"{low:,} low-grade")
    if len(parts) > 1:
        text = ", ".join(parts[:-1]) + " and " + parts[-1]
    else:
        text = parts[0]
    noun = "spirit stone" if len(parts) == 1 and text.startswith("1 ") else "spirit stones"
    return f"{sign}{text} {noun}"


def short(coins: int) -> str:
    amount = int(coins)
    high, mid, low = split(abs(amount))
    bits = [f"{high:,}H" if high else "", f"{mid}M" if mid else "", f"{low}L" if low or not (high or mid) else ""]
    return ("-" if amount < 0 else "") + " ".join(bit for bit in bits if bit)


def parse(text: str) -> Optional[int]:
    match = PATTERN.match(text or "")
    if match is None:
        return None
    try:
        number = float(match.group(1).replace(",", ""))
    except ValueError:
        return None
    unit = GRADES[WORDS[match.group(2).lower()]]
    return int(number * unit)
