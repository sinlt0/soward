import ast
import math
import operator
import re
import time
from typing import Any, Optional

import aiohttp

LANGUAGES = {
    "afrikaans": "af", "arabic": "ar", "bengali": "bn", "bangla": "bn", "bulgarian": "bg", "chinese": "zh-CN", "czech": "cs", "danish": "da",
    "dutch": "nl", "english": "en", "filipino": "tl", "finnish": "fi", "french": "fr", "german": "de", "greek": "el", "gujarati": "gu",
    "hebrew": "he", "hindi": "hi", "hungarian": "hu", "indonesian": "id", "italian": "it", "japanese": "ja", "korean": "ko", "malay": "ms",
    "marathi": "mr", "nepali": "ne", "norwegian": "no", "persian": "fa", "polish": "pl", "portuguese": "pt", "punjabi": "pa", "romanian": "ro",
    "russian": "ru", "spanish": "es", "swahili": "sw", "swedish": "sv", "tamil": "ta", "telugu": "te", "thai": "th", "turkish": "tr",
    "ukrainian": "uk", "urdu": "ur", "vietnamese": "vi",
}
LANGUAGE_CODES = {code.lower(): code for code in LANGUAGES.values()}

COINS = {
    "btc": "bitcoin", "bitcoin": "bitcoin", "eth": "ethereum", "ethereum": "ethereum", "ltc": "litecoin", "litecoin": "litecoin",
    "doge": "dogecoin", "dogecoin": "dogecoin", "sol": "solana", "solana": "solana", "xrp": "ripple", "ada": "cardano", "cardano": "cardano",
    "bnb": "binancecoin", "dot": "polkadot", "polkadot": "polkadot", "trx": "tron", "tron": "tron", "ton": "the-open-network",
    "matic": "matic-network", "avax": "avalanche-2", "link": "chainlink", "xmr": "monero", "monero": "monero", "bch": "bitcoin-cash",
    "usdt": "tether", "tether": "tether", "usdc": "usd-coin", "shib": "shiba-inu",
}

WEATHER_CODES = {
    0: "Clear sky", 1: "Mostly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Freezing fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 56: "Freezing drizzle", 57: "Heavy freezing drizzle",
    61: "Light rain", 63: "Rain", 65: "Heavy rain", 66: "Freezing rain", 67: "Heavy freezing rain",
    71: "Light snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains", 80: "Light showers", 81: "Showers", 82: "Violent showers",
    85: "Snow showers", 86: "Heavy snow showers", 95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Severe thunderstorm with hail",
}

_cache: dict[str, tuple[float, Any]] = {}


async def fetch_json(url: str, params: Optional[dict] = None, ttl: float = 0.0) -> tuple[Optional[int], Any]:
    key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    cached = _cache.get(key)
    if ttl and cached and time.time() - cached[0] < ttl:
        return 200, cached[1]
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10), headers={"User-Agent": "SowardBot/1.0"}) as session:
            async with session.get(url, params=params) as response:
                data = await response.json(content_type=None)
                if ttl and response.status == 200:
                    _cache[key] = (time.time(), data)
                return response.status, data
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return None, None


def language_code(text: str) -> Optional[str]:
    key = text.strip().lower()
    if key in LANGUAGES:
        return LANGUAGES[key]
    if key in LANGUAGE_CODES:
        return LANGUAGE_CODES[key]
    return None


def weather_text(code: Optional[int]) -> str:
    return WEATHER_CODES.get(int(code), "Unknown") if code is not None else "Unknown"


def to_f(celsius: float) -> float:
    return celsius * 9 / 5 + 32


def temp(celsius: Optional[float]) -> str:
    if celsius is None:
        return "n/a"
    return f"{celsius:.0f}°C ({to_f(celsius):.0f}°F)"


def strip_brackets(text: str) -> str:
    return re.sub(r"\[([^\]]*)\]", r"\1", text or "").replace("\r", "")


def clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


BIN_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
}
UNARY_OPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
FUNCTIONS = {
    "sqrt": math.sqrt, "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "log": math.log10, "ln": math.log, "log2": math.log2, "abs": abs, "round": round, "floor": math.floor, "ceil": math.ceil,
    "exp": math.exp, "factorial": math.factorial, "deg": math.degrees, "rad": math.radians,
}
CONSTANTS = {"pi": math.pi, "e": math.e, "tau": math.tau}


class CalcError(Exception):
    pass


def _eval(node):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name) and node.id in CONSTANTS:
        return CONSTANTS[node.id]
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY_OPS:
        return UNARY_OPS[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.BinOp) and type(node.op) in BIN_OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and (abs(right) > 1000 or abs(left) > 1e6 and abs(right) > 50):
            raise CalcError("That power is too large.")
        return BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
        args = [_eval(a) for a in node.args]
        if node.func.id == "factorial" and (len(args) != 1 or args[0] > 500 or args[0] < 0 or int(args[0]) != args[0]):
            raise CalcError("Factorial needs a whole number from 0 to 500.")
        return FUNCTIONS[node.func.id](*(int(a) if node.func.id == "factorial" else a for a in args))
    raise CalcError("I can only do numbers, + - * / // % ^, brackets and functions like sqrt, sin, log and ln.")


def calculate(expression: str):
    text = expression.strip().replace("^", "**").replace("×", "*").replace("÷", "/").replace(",", "")
    text = re.sub(r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\d+(?:\.\d+)?)", r"(\1/100)*\2", text)
    if not text or len(text) > 200:
        raise CalcError("Give me an expression up to 200 characters.")
    try:
        tree = ast.parse(text, mode="eval")
        value = _eval(tree)
    except CalcError:
        raise
    except ZeroDivisionError:
        raise CalcError("You cannot divide by zero.")
    except (SyntaxError, ValueError, TypeError, OverflowError, RecursionError):
        raise CalcError("I could not understand that expression.")
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        raise CalcError("That has no finite answer.")
    return value


def format_number(value) -> str:
    if isinstance(value, int):
        return f"{value:,}" if abs(value) < 10 ** 18 else f"{value:.6e}"
    if value == int(value) and abs(value) < 10 ** 15:
        return f"{int(value):,}"
    return f"{value:,.10g}" if abs(value) >= 1e-4 and abs(value) < 1e15 else f"{value:.8e}"


def money(value: float) -> str:
    if value >= 1:
        return f"{value:,.2f}"
    return f"{value:.6f}".rstrip("0").rstrip(".")
