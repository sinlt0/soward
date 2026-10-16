import difflib
import re
import unicodedata
from collections import deque
from typing import Iterable, Optional

import config

ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿­᠎"))
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s", "!": "i", "|": "i", "(": "c", "+": "t"})

INVITE_PATTERN = re.compile(
    r"(?:discord(?:app)?\s*\.\s*(?:gg|com\s*/\s*invite)|dsc\.gg|invite\.gg|discord\.me|discord\.link|disboard\.org/server/join)\s*/?\s*[a-z0-9-]{2,}",
    re.IGNORECASE,
)
URL_PATTERN = re.compile(r"(?:https?://|www\.)([^\s/?#<>\"'\]\)]+)", re.IGNORECASE)
BARE_DOMAIN_PATTERN = re.compile(r"(?<![\w@.-])((?:[a-z0-9-]{1,63}\.)+[a-z]{2,24})(?![\w-])", re.IGNORECASE)
EMOJI_PATTERN = re.compile(r"<a?:[a-zA-Z0-9_]+:[0-9]+>|[\U0001F000-\U0001FFFF☀-➿]")

LEGIT_DOMAINS = (
    "discord.com", "discord.gg", "discordapp.com", "discordapp.net", "discord.media", "discord.new",
    "discord.gift", "discordstatus.com", "discord.dev", "discord.design", "discord.store", "discord.tools",
    "discord.co", "steamcommunity.com", "steampowered.com", "roblox.com", "rbxcdn.com",
)
PHISHING_PATTERN = re.compile(
    r"d[i1l!]sc[o0]rd|d[i1l]scrod|dlscord|discorb|dicsord|discor[dt]-?(?:app|gift|nitro|promo)|"
    r"(?:free|gift|claim|get|steam|discord)[-.]?nitro|nitro[-.]?(?:gift|free|drop|promo|claim|giveaway)|"
    r"steamc[o0]mm|steamcomun|steamcommunlty|robl[o0]x(?!\.com)|r[o0]blox",
    re.IGNORECASE,
)
IP_LOGGER_DOMAINS = (
    "grabify.link", "iplogger.org", "iplogger.com", "iplogger.ru", "iplogger.co", "2no.co", "yip.su",
    "leancoding.co", "stopify.co", "freegiftcards.co", "joinmy.site", "curiouscat.club", "catsnthings.fun",
    "gamingfun.me", "headshot.monster", "grabify.org", "ps3cfw.com", "bmwforum.co", "quickmessage.us",
    "spottyfly.com", "shrekis.life", "datauth.com", "lovebird.guru", "linkbucks.com", "blasze.com", "blasze.tk",
)


def normalize(text: str) -> str:
    folded = unicodedata.normalize("NFKD", text).translate(ZERO_WIDTH)
    return "".join(c for c in folded if not unicodedata.combining(c)).lower()


def squash(text: str) -> str:
    return re.sub(r"[\W_]+", "", normalize(text).translate(LEET))


def banned_word_hit(content: str, words: Iterable[str], whole_word: bool = False) -> Optional[str]:
    plain = normalize(content)
    leet = plain.translate(LEET)
    squashed = re.sub(r"[\W_]+", "", leet)
    for word in words:
        needle = normalize(str(word)).strip()
        if not needle:
            continue
        if whole_word:
            pattern = re.compile(r"(?<!\w)" + re.escape(needle) + r"(?!\w)")
            if pattern.search(plain) or pattern.search(leet):
                return str(word)
            continue
        if needle in plain or needle in leet:
            return str(word)
        flat = squash(needle)
        if len(flat) >= 4 and flat in squashed:
            return str(word)
    return None


def has_invite(content: str) -> bool:
    return bool(INVITE_PATTERN.search(normalize(content)))


def clean_domain(raw: str) -> str:
    text = raw.strip().lower()
    text = re.sub(r"^[a-z]+://", "", text)
    text = text.split("/")[0].split("?")[0].split("#")[0].rsplit("@", 1)[-1]
    text = re.sub(r":\d+$", "", text).strip(".")
    return text[4:] if text.startswith("www.") else text


def host_of(raw: str) -> str:
    return clean_domain(raw)


def url_hosts(content: str) -> list[str]:
    hosts = []
    for match in URL_PATTERN.finditer(content):
        host = host_of(match.group(1))
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def all_hosts(content: str) -> list[str]:
    hosts = url_hosts(content)
    for match in BARE_DOMAIN_PATTERN.finditer(content):
        host = host_of(match.group(1))
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def host_matches(host: str, domain: str) -> bool:
    target = clean_domain(domain)
    return bool(target) and (host == target or host.endswith("." + target))


def blocked_host(content: str, blocklist: Iterable[str]) -> Optional[str]:
    entries = [clean_domain(d) for d in blocklist if clean_domain(d)]
    for host in all_hosts(content):
        if any(host_matches(host, d) for d in entries):
            return host
    return None


def disallowed_host(content: str, allowlist: Iterable[str]) -> Optional[str]:
    entries = [clean_domain(d) for d in allowlist if clean_domain(d)]
    if not entries:
        return None
    for host in url_hosts(content):
        if not any(host_matches(host, d) for d in entries):
            return host
    return None


def scam_host(content: str) -> Optional[tuple[str, str]]:
    for host in all_hosts(content):
        if any(host_matches(host, d) for d in IP_LOGGER_DOMAINS):
            return host, "iplogger"
        if PHISHING_PATTERN.search(host) and not any(host_matches(host, d) for d in LEGIT_DOMAINS):
            return host, "phishing"
    return None


def is_caps_spam(content: str, min_length: int = config.AUTOMOD_CAPS_MIN_LENGTH, ratio: float = config.AUTOMOD_CAPS_RATIO) -> bool:
    letters = [c for c in content if c.isalpha()]
    if len(letters) < min_length:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= ratio


def is_zalgo(content: str) -> bool:
    return sum(1 for c in unicodedata.normalize("NFD", content) if unicodedata.combining(c)) >= 12 and \
        sum(1 for c in content if unicodedata.combining(c)) >= 8


def is_text_wall(content: str, length: int = 600) -> bool:
    return len(content) > length and "\n" not in content[:300]


def is_emoji_spam(content: str, limit: int = 10) -> bool:
    return len(EMOJI_PATTERN.findall(content)) > limit


def is_duplicate(history: deque, content: str, now: float, window: int = config.AUTOMOD_DUPLICATE_WINDOW_SECONDS, similarity: float = config.AUTOMOD_DUPLICATE_SIMILARITY) -> bool:
    text = normalize(content)[:300]
    if len(text) < 10:
        return False
    hit = False
    for stamp, old in history:
        if now - stamp > window:
            continue
        if text == old:
            hit = True
            break
        matcher = difflib.SequenceMatcher(None, text, old)
        if matcher.real_quick_ratio() >= similarity and matcher.quick_ratio() >= similarity and matcher.ratio() >= similarity:
            hit = True
            break
    history.append((now, text))
    return hit
