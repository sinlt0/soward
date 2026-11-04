import re
from typing import Optional

import aiohttp

import config
from utils import lookups

DEEPL_TARGETS = {
    "bg": "BG", "cs": "CS", "da": "DA", "de": "DE", "el": "EL", "en": "EN-US", "es": "ES", "fi": "FI", "fr": "FR", "hu": "HU", "id": "ID",
    "it": "IT", "ja": "JA", "ko": "KO", "nl": "NL", "no": "NB", "pl": "PL", "pt": "PT-BR", "ro": "RO", "ru": "RU", "sv": "SV", "tr": "TR",
    "uk": "UK", "zh-cn": "ZH-HANS",
}
CHUNK = 450
MAX_CHUNKS = 40
LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
LINK = re.compile(r"https?://(?:www\.|ptb\.|canary\.)?discord(?:app)?\.com/channels/(\d+|@me)/(\d+)/(\d+)")


def find_link(text: str) -> Optional[tuple[str, int, int]]:
    match = LINK.search(text or "")
    if not match:
        return None
    return match.group(1), int(match.group(2)), int(match.group(3))


def strip_link(text: str) -> str:
    return LINK.sub("", text or "").strip()


def split_pieces(text: str, size: int = CHUNK) -> list[str]:
    pieces = []
    for sentence in re.split(r"(?<=[.!?。！？])\s+", text):
        sentence = sentence.strip()
        while len(sentence) > size:
            cut = sentence.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            pieces.append(sentence)
    return pieces


def plan(text: str) -> list[tuple[str, list[str]]]:
    out = []
    for part in re.split(r"(\n+)", text):
        if not part:
            continue
        if part.startswith("\n") or not LETTER.search(part):
            out.append((part, []))
        else:
            out.append(("", split_pieces(part)))
    return out


async def deepl(text: str, code: str) -> Optional[tuple[str, str]]:
    key = config.TRANSLATE_DEEPL_KEY
    target = DEEPL_TARGETS.get(code.lower())
    if not key or target is None:
        return None
    host = "api-free.deepl.com" if key.endswith(":fx") else "api.deepl.com"
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as session:
            async with session.post(f"https://{host}/v2/translate", json={"text": [text], "target_lang": target}, headers={"Authorization": f"DeepL-Auth-Key {key}"}) as response:
                if response.status != 200:
                    return None
                data = await response.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return None
    items = data.get("translations") or []
    if not items:
        return None
    return items[0]["text"], str(items[0].get("detected_source_language", "")).lower()


async def mymemory(text: str, code: str) -> Optional[tuple[str, str]]:
    steps = plan(text)
    if sum(len(pieces) for _, pieces in steps) > MAX_CHUNKS:
        return None
    detected = ""
    output = []
    for literal, pieces in steps:
        if not pieces:
            output.append(literal)
            continue
        done = []
        for piece in pieces:
            params = {"q": piece, "langpair": f"autodetect|{code}"}
            if config.TRANSLATE_EMAIL:
                params["de"] = config.TRANSLATE_EMAIL
            status, data = await lookups.fetch_json("https://api.mymemory.translated.net/get", params, ttl=3600)
            if status is None or not isinstance(data, dict) or str(data.get("responseStatus")) != "200":
                return None
            info = data.get("responseData") or {}
            result = info.get("translatedText")
            if not result:
                return None
            detected = detected or str(info.get("detectedLanguage") or "")
            done.append(result)
        output.append(" ".join(done))
    return "".join(output), detected


async def translate(text: str, code: str) -> Optional[tuple[str, str, str]]:
    result = await deepl(text, code)
    if result:
        return result[0], result[1], "DeepL"
    result = await mymemory(text, code)
    if result:
        return result[0], result[1], "MyMemory"
    return None


def pages(text: str, limit: int = 3200) -> list[str]:
    out = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = text.rfind(" ", 0, limit)
        if cut < limit // 2:
            cut = limit
        out.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        out.append(text)
    return out
