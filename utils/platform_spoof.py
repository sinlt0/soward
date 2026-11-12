import logging

from discord import gateway

log = logging.getLogger("zyro.platform")

PLATFORMS = {
    "desktop": None,
    "mobile": {"os": "android", "browser": "Discord Android", "device": "Discord Android"},
    "vr": {"os": "android", "browser": "Discord VR", "device": "Discord VR"},
    "console": {"os": "linux", "browser": "Discord Embedded", "device": "Discord Embedded"},
}
LABELS = {
    "desktop": "Desktop (default)",
    "mobile": "Mobile (phone icon)",
    "vr": "VR headset",
    "console": "Console (PlayStation / Xbox, experimental)",
}

current = "desktop"
active = "desktop"
_installed = False
_original = None


def normalize(value) -> str:
    return value if value in PLATFORMS else "desktop"


def select(value) -> None:
    global current
    current = normalize(value)


async def _send_as_json(self, data):
    global active
    if isinstance(data, dict) and data.get("op") == 2 and isinstance(data.get("d"), dict):
        props = PLATFORMS.get(current)
        if props:
            data["d"]["properties"] = {**data["d"].get("properties", {}), **props}
        active = current
        log.info("Identifying as platform: %s", current)
    return await _original(self, data)


def install() -> None:
    global _installed, _original
    if _installed:
        return
    _original = gateway.DiscordWebSocket.send_as_json
    gateway.DiscordWebSocket.send_as_json = _send_as_json
    _installed = True
