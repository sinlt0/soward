from __future__ import annotations

import asyncio
import io
import json
import logging
import time
import uuid
from typing import Optional

import aiohttp
import discord
import wavelink
from discord.ext import commands, tasks
from PIL import Image, ImageDraw

from utils import db, emoji_manager, guild_settings
from utils.checks import has_guild_permission
from utils.colors import ERROR, NEUTRAL, SUCCESS
import config

log = logging.getLogger("soward.music")


FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

RADIO_STATIONS: dict[str, dict] = {
    "groove_salad": {"name": "Groove Salad",        "url": "https://ice.somafm.com/groovesalad-128-mp3",   "emoji": "🥗"},
    "drone_zone":   {"name": "Drone Zone",           "url": "https://ice.somafm.com/dronezone-128-mp3",     "emoji": "🌌"},
    "lush":         {"name": "Lush",                 "url": "https://ice.somafm.com/lush-128-mp3",          "emoji": "🌸"},
    "digitalis":    {"name": "Digitalis",            "url": "https://ice.somafm.com/digitalis-128-mp3",     "emoji": "💊"},
    "fluid":        {"name": "Fluid",                "url": "https://ice.somafm.com/fluid-128-mp3",         "emoji": "💧"},
    "gsclassic":    {"name": "Groove Salad Classic", "url": "https://ice.somafm.com/gsclassic-128-mp3",     "emoji": "📻"},
    "deepspace":    {"name": "Deep Space One",       "url": "https://ice.somafm.com/deepspaceone-128-mp3",  "emoji": "🚀"},
    "defcon":       {"name": "DEF CON Radio",        "url": "https://ice.somafm.com/defcon-128-mp3",        "emoji": "💻"},
}

FILTER_DESCS = {
    "bassboost": "Heavy low-end boost",
    "nightcore": "Sped up + higher pitch",
    "slowed":    "Slowed + reverb feel",
    "vaporwave": "Slowed + nostalgic",
    "8d":        "Rotating stereo panning",
    "karaoke":   "Removes vocals",
    "clear":     "Remove all filters",
}

SEARCH_SOURCES: dict[str, str] = {
    "youtube": "ytmsearch:",
    "soundcloud": "scsearch:",
    "spotify": "spsearch:",
}
SOURCE_LABELS: dict[str, str] = {
    "youtube": "YouTube",
    "soundcloud": "SoundCloud",
    "spotify": "Spotify",
}
_KNOWN_SEARCH_PREFIXES = ("ytsearch:", "ytmsearch:", "scsearch:", "spsearch:")


def _is_spotify_query(resolved_query: str) -> bool:
    return resolved_query.startswith("spsearch:") or "open.spotify.com" in resolved_query


async def _get_default_source(guild_id: int) -> str:
    source = await guild_settings.get(guild_id, "music_source", "youtube")
    return source if source in SEARCH_SOURCES else "youtube"


def _build_search_query(query: str, source: str) -> str:
    if query.startswith(("http://", "https://")) or query.startswith(_KNOWN_SEARCH_PREFIXES):
        return query
    return f"{SEARCH_SOURCES.get(source, 'ytmsearch:')}{query}"


def _fmt(ms: int) -> str:
    s = int(ms / 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _bar(pos: int, dur: int, w: int = 20) -> str:
    if dur <= 0:
        return "─" * w
    filled = int(min(pos / dur, 1.0) * w)
    return "─" * filled + "⬤" + "─" * (w - filled)


def _simple(title: str, body: str, *, color: int = NEUTRAL) -> discord.ui.LayoutView:
    layout = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(f"-# {config.BOT_NAME} · Made by Soward Team"))
    layout.add_item(container)
    return layout


class RateLimitManager:
    def __init__(self):
        self.limited = False
        self.retry_after = 0.0
        self.failures = 0

    def is_limited(self) -> bool:
        now = time.time() * 1000
        if self.limited and now < self.retry_after:
            return True
        if self.limited and now >= self.retry_after:
            self.limited = False
            self.failures = 0
        return False

    def on_rate_limit(self, retry_after_ms: float = 30000):
        self.limited = True
        self.failures += 1
        backoff = min(retry_after_ms * (2 ** (self.failures - 1)), 120000)
        self.retry_after = (time.time() * 1000) + backoff

    def on_success(self):
        self.failures = 0


class MusicPlayer(wavelink.Player):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.controller_msg: Optional[discord.Message] = None
        self.text_channel_id: Optional[int] = None
        self.is_247: bool = False
        self._last_update: float = 0
        self.update_task: Optional[asyncio.Task] = None
        self.rl_manager: RateLimitManager = RateLimitManager()


async def _resolve_stream_url(url: str) -> Optional[str]:
    if "youtube.com" not in url and "youtu.be" not in url:
        return url
    try:
        import yt_dlp
    except ImportError:
        return None

    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "no_warnings": True,
        "source_address": "0.0.0.0",
        "noplaylist": True,
        "extract_flat": False,
        "playlist_items": "1",
        "skip_download": True,
    }
    loop = asyncio.get_event_loop()
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(url, download=False))
    except Exception:
        return None

    if not info:
        return None

    if info.get("_type") == "playlist":
        entries = info.get("entries") or []
        if not entries:
            return None
        info = entries[0]
        if not info:
            return None

    if info.get("is_live") or info.get("was_live"):
        formats = [
            f for f in info.get("formats", [])
            if f.get("acodec") != "none" and f.get("vcodec") == "none"
            and f.get("protocol") in ("https", "http", "m3u8_native", "m3u8")
        ]
        if not formats:
            formats = [f for f in info.get("formats", []) if f.get("acodec") != "none"]
        if not formats:
            return None
        formats.sort(key=lambda f: f.get("abr") or 0, reverse=True)
        return formats[0]["url"]

    stream_url = info.get("url")
    if stream_url:
        return stream_url
    formats = [f for f in info.get("formats", []) if f.get("acodec") != "none"]
    if not formats:
        return None
    return formats[0]["url"]


class LofiPlayer:
    def __init__(self, voice_client: discord.VoiceClient, station_name: str, url: str, volume: float = 0.5):
        self.voice_client = voice_client
        self.station_name = station_name
        self.url = url
        self.volume = volume

    def is_playing(self) -> bool:
        return self.voice_client.is_playing() or self.voice_client.is_paused()

    async def start(self) -> bool:
        stream_url = await _resolve_stream_url(self.url)
        if not stream_url:
            return False
        try:
            source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(source, volume=self.volume)
            self.voice_client.play(source)
            return True
        except Exception:
            return False

    async def stop(self):
        if self.voice_client.is_playing() or self.voice_client.is_paused():
            self.voice_client.stop()
        if self.voice_client.is_connected():
            await self.voice_client.disconnect()


class NPControlRow(discord.ui.ActionRow):
    def __init__(self):
        super().__init__(
            discord.ui.Button(label="⏸ Pause", style=discord.ButtonStyle.secondary, custom_id="music:np:pause"),
            discord.ui.Button(label="⏭ Skip",  style=discord.ButtonStyle.primary,   custom_id="music:np:skip"),
            discord.ui.Button(label="🔀 Shuffle", style=discord.ButtonStyle.secondary, custom_id="music:np:shuffle"),
            discord.ui.Button(label="⏹ Stop",  style=discord.ButtonStyle.danger,    custom_id="music:np:stop"),
        )
        self.children[0].callback = self._pause
        self.children[1].callback = self._skip
        self.children[2].callback = self._shuffle
        self.children[3].callback = self._stop

    async def _pause(self, interaction: discord.Interaction):
        player: MusicPlayer = interaction.guild.voice_client
        if not player:
            return await interaction.response.defer()
        await player.pause(not player.paused)
        self.children[0].label = "▶ Resume" if player.paused else "⏸ Pause"
        await interaction.response.edit_message(view=self.view)

    async def _skip(self, interaction: discord.Interaction):
        player: MusicPlayer = interaction.guild.voice_client
        if player:
            await player.skip(force=True)
        await interaction.response.defer()

    async def _shuffle(self, interaction: discord.Interaction):
        player: MusicPlayer = interaction.guild.voice_client
        if player:
            player.queue.shuffle()
        await interaction.response.defer()

    async def _stop(self, interaction: discord.Interaction):
        player: MusicPlayer = interaction.guild.voice_client
        if player:
            player.queue.clear()
            await player.disconnect()
        await interaction.response.defer()


class NPLoopRow(discord.ui.ActionRow):
    def __init__(self):
        super().__init__(
            discord.ui.Button(label="🔁 Loop: Off", style=discord.ButtonStyle.secondary, custom_id="music:np:loop"),
            discord.ui.Button(label="✨ Autoplay: Off", style=discord.ButtonStyle.secondary, custom_id="music:np:autoplay"),
        )
        self.children[0].callback = self._loop
        self.children[1].callback = self._autoplay

    async def _loop(self, interaction: discord.Interaction):
        player: MusicPlayer = interaction.guild.voice_client
        if not player:
            return await interaction.response.defer()
        modes = [wavelink.QueueMode.normal, wavelink.QueueMode.loop, wavelink.QueueMode.loop_all]
        labels = {wavelink.QueueMode.normal: "🔁 Loop: Off", wavelink.QueueMode.loop: "🔂 Loop: Track", wavelink.QueueMode.loop_all: "🔁 Loop: Queue"}
        styles = {wavelink.QueueMode.normal: discord.ButtonStyle.secondary, wavelink.QueueMode.loop: discord.ButtonStyle.success, wavelink.QueueMode.loop_all: discord.ButtonStyle.primary}
        idx = (modes.index(player.queue.mode) + 1) % len(modes)
        player.queue.mode = modes[idx]
        self.children[0].label = labels[modes[idx]]
        self.children[0].style = styles[modes[idx]]
        await interaction.response.edit_message(view=self.view)

    async def _autoplay(self, interaction: discord.Interaction):
        player: MusicPlayer = interaction.guild.voice_client
        if not player:
            return await interaction.response.defer()
        if player.autoplay == wavelink.AutoPlayMode.disabled:
            player.autoplay = wavelink.AutoPlayMode.enabled
            self.children[1].label = "✨ Autoplay: On"
            self.children[1].style = discord.ButtonStyle.success
        else:
            player.autoplay = wavelink.AutoPlayMode.disabled
            self.children[1].label = "✨ Autoplay: Off"
            self.children[1].style = discord.ButtonStyle.secondary
        await interaction.response.edit_message(view=self.view)


class NPLayout(discord.ui.LayoutView):
    def __init__(self, player: MusicPlayer, card: Optional[discord.File] = None):
        super().__init__(timeout=None)
        e = emoji_manager.get
        track = player.current
        pos = player.position
        dur = track.length or 1
        loop_labels = {wavelink.QueueMode.normal: "Off", wavelink.QueueMode.loop: "🔂 Track", wavelink.QueueMode.loop_all: "🔁 Queue"}
        ap_label = "On" if player.autoplay != wavelink.AutoPlayMode.disabled else "Off"
        queue_len = len(player.queue)

        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(
            f"## {e('nowplaying')} Now Playing{'  🔴 LIVE' if track.is_stream else ''}"
        ))
        container.add_item(discord.ui.Separator())

        if track.artwork:
            section = discord.ui.Section(accessory=discord.ui.Thumbnail(media=track.artwork))
            section.add_item(discord.ui.TextDisplay(f"### {track.title}\n-# by **{track.author}**"))
            container.add_item(section)
        else:
            container.add_item(discord.ui.TextDisplay(f"### {track.title}\n-# by **{track.author}**"))

        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f"`{_fmt(pos)}` `{_bar(pos, dur)}` `{_fmt(dur)}`"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(
            f"-# 🔊 Vol {player.volume}%  ·  Loop: {loop_labels[player.queue.mode]}  ·  Autoplay: {ap_label}  ·  Queue: {queue_len} track(s)"
        ))
        container.add_item(discord.ui.Separator())

        ctrl = NPControlRow()
        container.add_item(ctrl)
        container.add_item(discord.ui.Separator())

        loop_row = NPLoopRow()
        container.add_item(loop_row)
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {config.BOT_NAME} · Made by Soward Team"))
        self.add_item(container)


class FilterRow(discord.ui.ActionRow):
    def __init__(self):
        super().__init__(
            discord.ui.Select(
                placeholder="Apply a filter...",
                options=[
                    discord.SelectOption(label=n.title(), value=n, description=FILTER_DESCS.get(n, ""))
                    for n in FILTER_DESCS
                ],
                custom_id="music:filter:select",
            )
        )
        self.children[0].callback = self._on_select

    async def _on_select(self, interaction: discord.Interaction):
        await interaction.response.defer()
        name = interaction.data["values"][0]
        player: MusicPlayer = interaction.guild.voice_client
        if player:
            filters = wavelink.Filters()
            if name == "bassboost":
                filters.equalizer.set(bands=[{"band": 0, "gain": 0.6}, {"band": 1, "gain": 0.67}, {"band": 2, "gain": 0.67}])
            elif name == "nightcore":
                filters.timescale.set(speed=1.2, pitch=1.2, rate=1.0)
            elif name == "slowed":
                filters.timescale.set(speed=0.8, pitch=0.9, rate=1.0)
            elif name == "vaporwave":
                filters.timescale.set(speed=0.85, pitch=0.85, rate=1.0)
            elif name == "8d":
                filters.rotation.set(rotation_hz=0.2)
            elif name == "karaoke":
                filters.karaoke.set(level=1.0, mono_level=1.0, filter_band=220.0, filter_width=100.0)
            await player.set_filters(filters)

        display = self.view.find_item(99)
        if display:
            display.content = self._build_body(name)
        await interaction.edit_original_response(view=self.view)

    def _build_body(self, active: str = "clear") -> str:
        lines = []
        for n in FILTER_DESCS:
            dot = "●" if n == active else "○"
            lines.append(f"`{dot}` **{n.title()}**  -# {FILTER_DESCS[n]}")
        lines.append(f"\n-# Active: **{active.title()}**")
        return "\n".join(lines)


class FilterLayout(discord.ui.LayoutView):
    def __init__(self, author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        e = emoji_manager.get

        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(f"## {e('music_note')} Audio Filters"))
        container.add_item(discord.ui.Separator())
        body_lines = [f"`○` **{n.title()}**  -# {FILTER_DESCS[n]}" for n in FILTER_DESCS]
        body_lines.append("\n-# Active: **Clear**")
        container.add_item(discord.ui.TextDisplay("\n".join(body_lines), id=99))
        container.add_item(discord.ui.Separator())
        container.add_item(FilterRow())
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {config.BOT_NAME} · Made by Soward Team"))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id


class QueuePageRow(discord.ui.ActionRow):
    def __init__(self):
        super().__init__(
            discord.ui.Button(label="◀ Prev",     style=discord.ButtonStyle.secondary, custom_id="music:q:prev"),
            discord.ui.Button(label="Next ▶",     style=discord.ButtonStyle.secondary, custom_id="music:q:next"),
            discord.ui.Button(label="🔀 Shuffle", style=discord.ButtonStyle.primary,   custom_id="music:q:shuffle"),
            discord.ui.Button(label="🗑 Clear",    style=discord.ButtonStyle.danger,    custom_id="music:q:clear"),
        )
        self.children[0].callback = self._prev
        self.children[1].callback = self._next
        self.children[2].callback = self._shuffle
        self.children[3].callback = self._clear

    async def _prev(self, interaction: discord.Interaction):
        layout: QueueLayout = self.view
        layout.page = max(0, layout.page - 1)
        layout._render()
        await interaction.response.edit_message(view=layout)

    async def _next(self, interaction: discord.Interaction):
        layout: QueueLayout = self.view
        player: MusicPlayer = interaction.guild.voice_client
        if player:
            max_page = max(0, (len(player.queue) - 1) // QueueLayout.PAGE)
            layout.page = min(max_page, layout.page + 1)
        layout._render()
        await interaction.response.edit_message(view=layout)

    async def _shuffle(self, interaction: discord.Interaction):
        player: MusicPlayer = interaction.guild.voice_client
        if player:
            player.queue.shuffle()
        layout: QueueLayout = self.view
        layout._render()
        await interaction.response.edit_message(view=layout)

    async def _clear(self, interaction: discord.Interaction):
        player: MusicPlayer = interaction.guild.voice_client
        if player:
            player.queue.clear()
        layout: QueueLayout = self.view
        layout.page = 0
        layout._render()
        await interaction.response.edit_message(view=layout)


class QueueLayout(discord.ui.LayoutView):
    PAGE = 10

    def __init__(self, player: Optional[MusicPlayer], author_id: int):
        super().__init__(timeout=120)
        self.author_id = author_id
        self.player = player
        self.page = 0
        e = emoji_manager.get

        self.container = discord.ui.Container(accent_color=NEUTRAL)
        self.container.add_item(discord.ui.TextDisplay(f"## {e('queue')} Queue", id=100))
        self.container.add_item(discord.ui.Separator())
        self.container.add_item(discord.ui.TextDisplay("Loading...", id=101))
        self.container.add_item(discord.ui.Separator())
        self.container.add_item(QueuePageRow())
        self.container.add_item(discord.ui.Separator())
        self.container.add_item(discord.ui.TextDisplay(f"-# {config.BOT_NAME} · Made by Soward Team"))
        self.add_item(self.container)
        self._render()

    def _render(self):
        body = self.find_item(101)
        if not body:
            return
        player = self.player
        if not player:
            body.content = "Not connected to voice."
            return

        lines = []
        if player.current:
            lines += [f"**▶ {player.current.title}**", f"-# {player.current.author}  ·  {_fmt(player.current.length)}", ""]

        queue_list = list(player.queue)
        start = self.page * self.PAGE
        for i, t in enumerate(queue_list[start:start + self.PAGE], start + 1):
            lines += [f"`{i:02}.` **{t.title}**", f"-# {t.author}  ·  {_fmt(t.length)}"]

        if not queue_list and not player.current:
            lines = ["Queue is empty.", "-# Use `play <song>` to add tracks."]

        total = sum(t.length for t in queue_list if not t.is_stream)
        max_page = max(0, (len(queue_list) - 1) // self.PAGE)
        lines.append(f"\n-# Page {self.page+1}/{max_page+1}  ·  {len(queue_list)} track(s)  ·  {_fmt(total)} total")
        body.content = "\n".join(lines)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id


class RadioSelectRow(discord.ui.ActionRow):
    def __init__(self, current_key: str, stations: dict):
        opts = [
            discord.SelectOption(
                label=f"{s['emoji']} {s['name']}"[:100], value=k,
                default=(k == current_key),
            )
            for k, s in list(stations.items())[:25]
        ]
        super().__init__(discord.ui.Select(
            placeholder="Choose a station...",
            options=opts,
            custom_id="music:radio:select",
        ))
        self.stations = stations
        self.children[0].callback = self._on_select

    async def _on_select(self, interaction: discord.Interaction):
        await interaction.response.defer()
        radio_key = interaction.data["values"][0]
        cog: Music = interaction.client.get_cog("Music")

        await db.raw_execute(
            "INSERT INTO lofi_state (guild_id, radio_key) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET radio_key=excluded.radio_key",
            (interaction.guild.id, radio_key),
        )

        row = await db.raw_fetchone("SELECT * FROM lofi_state WHERE guild_id=?", (interaction.guild.id,))
        if row and row["enabled"] and row["channel_id"]:
            vc = interaction.guild.get_channel(int(row["channel_id"]))
            if vc and cog:
                await cog._start_lofi(interaction.guild, vc, radio_key, text_ch_id=row["text_channel_id"])

        body = self.view.find_item(200)
        if body:
            body.content = "\n".join(
                f"`{'▶' if k == radio_key else '○'}` {s['emoji']} **{s['name']}**"
                for k, s in self.stations.items()
            )
        await interaction.edit_original_response(view=self.view)


class RadioLayout(discord.ui.LayoutView):
    def __init__(self, current_key: str, author_id: int, stations: Optional[dict] = None):
        super().__init__(timeout=120)
        self.author_id = author_id
        all_stations = stations or RADIO_STATIONS
        e = emoji_manager.get

        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(f"## {e('music_note')} Radio Station"))
        container.add_item(discord.ui.Separator())
        body = "\n".join(
            f"`{'▶' if k == current_key else '○'}` {s['emoji']} **{s['name']}**"
            for k, s in all_stations.items()
        )
        container.add_item(discord.ui.TextDisplay(body, id=200))
        container.add_item(discord.ui.Separator())
        container.add_item(RadioSelectRow(current_key, all_stations))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {config.BOT_NAME} · Made by Soward Team"))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True


class LofiSetupSelectRow(discord.ui.ActionRow):
    def __init__(self, vc: discord.VoiceChannel, text_ch_id: int, author_id: int):
        super().__init__(
            discord.ui.Select(
                placeholder="Select a radio station...",
                options=[
                    discord.SelectOption(label=f"{s['emoji']} {s['name']}", value=k)
                    for k, s in RADIO_STATIONS.items()
                ],
                custom_id="music:setup:select",
            )
        )
        self.vc = vc
        self.text_ch_id = text_ch_id
        self.author_id = author_id
        self.children[0].callback = self._on_select

    async def _on_select(self, interaction: discord.Interaction):
        await interaction.response.defer()
        radio_key = interaction.data["values"][0]
        station = RADIO_STATIONS[radio_key]
        cog: Music = interaction.client.get_cog("Music")
        e = emoji_manager.get

        if cog:
            await cog._start_lofi(interaction.guild, self.vc, radio_key, text_ch_id=self.text_ch_id)

        layout = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=SUCCESS)
        container.add_item(discord.ui.TextDisplay(
            f"## ✅ Lofi is live!\n"
            f"**Station:** {station['emoji']} {station['name']}\n"
            f"**Voice channel:** {self.vc.mention}\n\n"
            "-# Use `lofi radio` to change · `lofi disable` to stop"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {config.BOT_NAME} · Made by Soward Team"))
        layout.add_item(container)
        await interaction.edit_original_response(view=layout)


class LofiSetupLayout(discord.ui.LayoutView):
    def __init__(self, vc: discord.VoiceChannel, text_ch_id: int, author_id: int):
        super().__init__(timeout=120)
        e = emoji_manager.get

        lines = [f"## {e('music_note')} Lofi setup — Step 2 of 2",
                 f"Voice channel: **{vc.name}**", "", "Pick a station:"]
        for k, s in RADIO_STATIONS.items():
            lines.append(f"{s['emoji']} **{s['name']}**")

        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay("\n".join(lines)))
        container.add_item(discord.ui.Separator())
        container.add_item(LofiSetupSelectRow(vc, text_ch_id, author_id))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {config.BOT_NAME} · Made by Soward Team"))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This setup is not for you.", ephemeral=True)
            return False
        return True


class Music(commands.Cog):
    category = "Music"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None
        self._lofi_players: dict[int, LofiPlayer] = {}
        bot.loop.create_task(self._start_nodes())
        bot.loop.create_task(self._restore_sessions())

    async def cog_load(self):
        self._session = aiohttp.ClientSession()
        self.lofi_watchdog.start()

    def cog_unload(self):
        self.lofi_watchdog.cancel()
        if self._session:
            self.bot.loop.create_task(self._session.close())

    async def _start_nodes(self):
        await self.bot.wait_until_ready()
        nodes = []
        for n in config.LAVALINK_NODES:
            host = n.get("host", "127.0.0.1")
            port = n.get("port", 2333)
            password = n.get("password", "youshallnotpass")
            secure = n.get("secure", False)
            identifier = n.get("identifier", f"SOWARD-{host}:{port}")
            scheme = "https" if secure else "http"
            nodes.append(wavelink.Node(
                uri=f"{scheme}://{host}:{port}",
                password=password,
                identifier=identifier,
                retries=999999,
            ))
            log.info("Configured Lavalink node %s at %s://%s:%s", identifier, scheme, host, port)

        try:
            connected = await wavelink.Pool.connect(nodes=nodes, client=self.bot, cache_capacity=100)
            log.info("wavelink.Pool.connect returned %d node(s): %s", len(connected), list(connected.keys()))
        except wavelink.AuthorizationFailedException:
            log.error("Lavalink authorization failed — check SOWARD_LAVALINK_PASSWORD matches your Lavalink application.yml password.")
        except wavelink.InvalidClientException:
            log.error("Lavalink connection failed — invalid discord.Client passed to Pool.connect.")
        except wavelink.NodeException as ex:
            log.error("Lavalink node failed to connect: %s — confirm Lavalink is running and is version 4+.", ex)
        except Exception:
            log.exception("Unexpected error while connecting to Lavalink nodes.")

    async def _restore_sessions(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(5)

        lofi_rows = await db.raw_fetch("SELECT * FROM lofi_state WHERE enabled=1")
        for row in lofi_rows:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                continue
            vc_channel = guild.get_channel(int(row["channel_id"])) if row["channel_id"] else None
            if not vc_channel or not isinstance(vc_channel, discord.VoiceChannel):
                continue
            try:
                vc = await vc_channel.connect(self_deaf=True)
                stations = await self._get_stations(guild.id)
                radio_key = row["radio_key"] or "groove_salad"
                station = stations.get(radio_key, RADIO_STATIONS["groove_salad"])
                lofi_player = LofiPlayer(vc, station["name"], station["url"])
                if await lofi_player.start():
                    self._lofi_players[guild.id] = lofi_player
            except Exception:
                pass

        vc247_rows = await db.raw_fetch("SELECT * FROM vc247_state WHERE enabled=1")
        for row in vc247_rows:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild or guild.voice_client:
                continue
            vc = guild.get_channel(int(row["voice_channel_id"])) if row["voice_channel_id"] else None
            if not vc or not isinstance(vc, discord.VoiceChannel):
                continue
            try:
                player: MusicPlayer = await vc.connect(cls=MusicPlayer, self_deaf=True)
                player.is_247 = True
                if row["text_channel_id"]:
                    player.text_channel_id = int(row["text_channel_id"])
            except Exception:
                pass

    async def _get_stations(self, guild_id: int) -> dict[str, dict]:
        stations = dict(RADIO_STATIONS)
        rows = await db.raw_fetch("SELECT key, name, url FROM custom_lofi_stations WHERE guild_id=?", (guild_id,))
        for row in rows:
            stations[row["key"]] = {"name": row["name"], "url": row["url"], "emoji": "📡"}
        return stations

    async def _start_lofi(self, guild: discord.Guild, vc: discord.VoiceChannel, radio_key: str, *, text_ch_id: Optional[int] = None) -> bool:
        stations = await self._get_stations(guild.id)
        station = stations.get(radio_key, RADIO_STATIONS["groove_salad"])

        existing = self._lofi_players.get(guild.id)
        if existing:
            await existing.stop()
            self._lofi_players.pop(guild.id, None)

        try:
            voice_client = guild.voice_client
            if voice_client and not isinstance(voice_client, wavelink.Player):
                if voice_client.channel != vc:
                    await voice_client.move_to(vc)
            else:
                if voice_client:
                    await voice_client.disconnect(force=True)
                voice_client = await vc.connect(self_deaf=True)
        except Exception:
            return False

        lofi_player = LofiPlayer(voice_client, station["name"], station["url"])
        if not await lofi_player.start():
            return False

        self._lofi_players[guild.id] = lofi_player
        await db.raw_execute(
            "INSERT INTO lofi_state (guild_id, channel_id, text_channel_id, enabled, radio_key) VALUES (?, ?, ?, 1, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id,"
            " text_channel_id=excluded.text_channel_id, enabled=1, radio_key=excluded.radio_key",
            (guild.id, vc.id, text_ch_id, radio_key),
        )
        return True

    async def _stop_lofi(self, guild_id: int):
        lofi = self._lofi_players.pop(guild_id, None)
        if lofi:
            await lofi.stop()
        await db.raw_execute("UPDATE lofi_state SET enabled=0 WHERE guild_id=?", (guild_id,))

    @tasks.loop(seconds=30)
    async def lofi_watchdog(self):
        rows = await db.raw_fetch("SELECT * FROM lofi_state WHERE enabled=1")
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                continue
            lofi = self._lofi_players.get(guild.id)
            if lofi and lofi.is_playing() and lofi.voice_client.is_connected():
                continue
            vc = guild.get_channel(int(row["channel_id"])) if row["channel_id"] else None
            if not vc or not isinstance(vc, discord.VoiceChannel):
                continue
            radio_key = row["radio_key"] or "groove_salad"
            try:
                await self._start_lofi(guild, vc, radio_key, text_ch_id=row["text_channel_id"])
            except Exception:
                pass

    @lofi_watchdog.before_loop
    async def _before_watchdog(self):
        await self.bot.wait_until_ready()

    async def _generate_card(self, player: MusicPlayer) -> discord.File:
        track = player.current
        W, H = 800, 280
        canvas = Image.new("RGB", (W, H), (20, 20, 20))
        draw = ImageDraw.Draw(canvas)

        if track.artwork and self._session:
            try:
                async with self._session.get(track.artwork, timeout=aiohttp.ClientTimeout(total=5)) as r:
                    if r.status == 200:
                        art = Image.open(io.BytesIO(await r.read())).resize((200, 200))
                        canvas.paste(art, (40, 40))
            except Exception:
                pass

        draw.text((280, 40), (track.title or "Unknown")[:42], fill=(255, 255, 255))
        draw.text((280, 80), track.author or "Unknown", fill=(180, 180, 180))

        pos = player.position
        dur = track.length or 1
        pct = min(pos / dur, 1.0)
        bx, by, bw, bh = 280, 160, 460, 8
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], 4, fill=(60, 60, 60))
        if pct > 0:
            draw.rounded_rectangle([bx, by, bx + int(bw * pct), by + bh], 4, fill=(138, 99, 255))

        draw.text((280, 180), _fmt(pos), fill=(200, 200, 200))
        draw.text((680, 180), _fmt(dur), fill=(200, 200, 200))

        mode_label = {wavelink.QueueMode.normal: "Off", wavelink.QueueMode.loop: "Track", wavelink.QueueMode.loop_all: "Queue"}
        draw.text((280, 220), f"Loop: {mode_label.get(player.queue.mode, 'Off')}  |  Queue: {len(player.queue)}", fill=(140, 140, 140))

        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        buf.seek(0)
        return discord.File(buf, "music-card.png")

    def _build_controller_view(self, player: MusicPlayer) -> discord.ui.LayoutView:
        e = emoji_manager.get
        track = player.current

        layout = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(
            f"## {e('nowplaying')} Now Playing{'  🔴 LIVE' if track.is_stream else ''}"
        ))
        container.add_item(discord.ui.Separator())

        if track.artwork:
            section = discord.ui.Section(accessory=discord.ui.Thumbnail(media=track.artwork))
            section.add_item(discord.ui.TextDisplay(f"### {track.title}\n-# by **{track.author}**"))
            container.add_item(section)
        else:
            container.add_item(discord.ui.TextDisplay(f"### {track.title}\n-# by **{track.author}**"))

        container.add_item(discord.ui.Separator())
        gallery = discord.ui.MediaGallery()
        gallery.add_item(media="attachment://music-card.png")
        container.add_item(gallery)
        container.add_item(discord.ui.Separator())

        queue_len = len(player.queue)
        mode_label = {wavelink.QueueMode.normal: "Off", wavelink.QueueMode.loop: "🔂 Track", wavelink.QueueMode.loop_all: "🔁 Queue"}
        ap_label = "On" if player.autoplay != wavelink.AutoPlayMode.disabled else "Off"
        container.add_item(discord.ui.TextDisplay(
            f"-# 🔊 Vol {player.volume}%  ·  Loop: {mode_label[player.queue.mode]}  ·  Autoplay: {ap_label}  ·  Queue: {queue_len}"
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(NPControlRow())
        container.add_item(discord.ui.Separator())
        container.add_item(NPLoopRow())
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {config.BOT_NAME} · Made by Soward Team"))
        layout.add_item(container)
        return layout

    async def _send_controller(self, player: MusicPlayer):
        if not player.current or not player.text_channel_id:
            return
        guild = player.guild
        channel = guild.get_channel(player.text_channel_id)
        if not channel:
            return

        if player.controller_msg:
            try:
                await player.controller_msg.delete()
            except Exception:
                pass
            player.controller_msg = None

        try:
            card = await self._generate_card(player)
            layout = self._build_controller_view(player)
            player.controller_msg = await channel.send(view=layout, file=card)
            player._last_update = time.time()
            player.rl_manager.on_success()
        except Exception:
            pass

    async def _update_controller(self, player: MusicPlayer):
        if not player.current or not player.controller_msg:
            return
        try:
            card = await self._generate_card(player)
            layout = self._build_controller_view(player)
            await player.controller_msg.edit(view=layout, attachments=[card])
            player.rl_manager.on_success()
            player._last_update = time.time()
        except discord.HTTPException as ex:
            if ex.status == 429:
                player.rl_manager.on_rate_limit(getattr(ex, "retry_after", 30) * 1000)
            else:
                player.controller_msg = None
        except Exception:
            pass

    async def _controller_loop(self, player: MusicPlayer):
        while player.playing:
            if player.paused:
                await asyncio.sleep(5)
                continue
            if player.rl_manager.is_limited():
                await asyncio.sleep(10)
                continue
            if time.time() - player._last_update < 20:
                await asyncio.sleep(5)
                continue
            await self._update_controller(player)
            await asyncio.sleep(20)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        log.info("Lavalink node %s is ready (resumed=%s, session_id=%s)", payload.node.identifier, payload.resumed, payload.session_id)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player: MusicPlayer = payload.player
        if not player:
            return
        if player.update_task:
            player.update_task.cancel()
        await self._send_controller(player)
        player.update_task = self.bot.loop.create_task(self._controller_loop(player))

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player: MusicPlayer = payload.player
        if not player:
            return

        reason = str(payload.reason).upper()
        if reason not in ("FINISHED", "LOAD_FAILED"):
            return

        try:
            next_track = player.queue.get()
        except wavelink.QueueEmpty:
            if player.update_task:
                player.update_task.cancel()
                player.update_task = None
            return

        try:
            await player.play(next_track)
        except Exception:
            log.error("Failed to auto-advance to next queued track.", exc_info=True)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: MusicPlayer):
        if not player.is_247:
            await player.disconnect()

    async def _ensure_player(self, ctx: commands.Context) -> Optional[MusicPlayer]:
        e = emoji_manager.get
        if not ctx.author.voice:
            await ctx.send(view=_simple(f"{e('cross')} Not in voice", "Join a voice channel first.", color=ERROR))
            return None

        existing = ctx.voice_client
        if existing and not isinstance(existing, wavelink.Player):
            await self._stop_lofi(ctx.guild.id)
            try:
                await existing.disconnect(force=True)
            except Exception:
                pass
            existing = None

        player: MusicPlayer = existing
        if not player:
            try:
                player = await ctx.author.voice.channel.connect(cls=MusicPlayer, self_deaf=True)
                player.text_channel_id = ctx.channel.id
            except Exception as ex:
                await ctx.send(view=_simple(f"{e('cross')} Connection failed", f"Could not connect: {ex}", color=ERROR))
                return None
        elif player.channel != ctx.author.voice.channel:
            await ctx.send(view=_simple(f"{e('cross')} Wrong channel", "Join my voice channel.", color=ERROR))
            return None
        if not player.text_channel_id:
            player.text_channel_id = ctx.channel.id
        return player

    async def _do_play(self, ctx: commands.Context, query: str, forced_source: Optional[str] = None):
        e = emoji_manager.get
        player = await self._ensure_player(ctx)
        if not player:
            return

        source = forced_source or await _get_default_source(ctx.guild.id)
        resolved_query = _build_search_query(query, source)

        tracks = await wavelink.Playable.search(resolved_query)
        if not tracks:
            body = f"Nothing found for `{query}`."
            if _is_spotify_query(resolved_query):
                body += (
                    "\n-# Spotify requires the Lavalink node to have the **LavaSrc** plugin installed"
                    " with valid Spotify API credentials. Ask the bot owner to confirm that's configured,"
                    " or try `soundcloud`/`play` with a YouTube search instead."
                )
            return await ctx.send(view=_simple(f"{e('cross')} No results", body, color=ERROR))

        if isinstance(tracks, wavelink.Playlist):
            for t in tracks.tracks:
                t.extras = {"requester_id": ctx.author.id}
                player.queue.put(t)
            if not player.playing:
                await player.play(player.queue.get())
            await ctx.send(view=_simple(f"{e('queue')} Playlist queued",
                f"**{tracks.name}** — {len(tracks.tracks)} tracks added.", color=SUCCESS))
        else:
            track = tracks[0]
            track.extras = {"requester_id": ctx.author.id}
            if not player.playing:
                await player.play(track)
            else:
                player.queue.put(track)
                await ctx.send(view=_simple(f"{e('queue')} Added to queue",
                    f"**{track.title}**\nby {track.author} · `{_fmt(track.length)}`\nPosition: **#{len(player.queue)}**",
                    color=SUCCESS))

    @commands.command(name="play", aliases=["p"], help="Play a song or add it to the queue. Uses this server's default source (see `musicsource`).")
    @commands.guild_only()
    async def play(self, ctx: commands.Context, *, query: str):
        await self._do_play(ctx, query)

    @commands.command(name="soundcloud", aliases=["sc", "playsc"], help="Play a track/playlist from SoundCloud (or add it to the queue).")
    @commands.guild_only()
    async def soundcloud_play(self, ctx: commands.Context, *, query: str):
        await self._do_play(ctx, query, forced_source="soundcloud")

    @commands.command(name="spotify", aliases=["sp", "playsp"], help="Play a track/playlist from Spotify (or add it to the queue). Requires the Lavalink node to have Spotify support configured.")
    @commands.guild_only()
    async def spotify_play(self, ctx: commands.Context, *, query: str):
        await self._do_play(ctx, query, forced_source="spotify")

    @commands.command(name="playnext", aliases=["pn"], help="Insert a track to play immediately after the current one.")
    @commands.guild_only()
    async def playnext(self, ctx: commands.Context, *, query: str):
        e = emoji_manager.get
        player = await self._ensure_player(ctx)
        if not player:
            return
        source = await _get_default_source(ctx.guild.id)
        resolved_query = _build_search_query(query, source)
        tracks = await wavelink.Playable.search(resolved_query)
        if not tracks:
            body = f"Nothing found for `{query}`."
            if _is_spotify_query(resolved_query):
                body += "\n-# Spotify requires the Lavalink node to have the **LavaSrc** plugin configured."
            return await ctx.send(view=_simple(f"{e('cross')} No results", body, color=ERROR))
        track = tracks[0] if isinstance(tracks, list) else tracks.tracks[0]
        track.extras = {"requester_id": ctx.author.id}
        if not player.playing:
            await player.play(track)
        else:
            player.queue.put_at(0, track)
            await ctx.send(view=_simple(f"{e('queue')} Playing next", f"**{track.title}** will play next.", color=SUCCESS))

    @commands.command(name="skip", aliases=["s"], help="Skip the current track. Pass a number to skip multiple.")
    @commands.guild_only()
    async def skip(self, ctx: commands.Context, amount: int = 1):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player or not player.playing:
            return await ctx.send(view=_simple(f"{e('cross')} Not playing", "Nothing to skip.", color=ERROR))
        skipped = player.current.title
        for _ in range(max(0, amount - 1)):
            try:
                player.queue.get()
            except wavelink.QueueEmpty:
                break
        await player.skip(force=True)
        await ctx.send(view=_simple(f"{e('skip')} Skipped",
            f"Skipped **{skipped}**" + (f" (+{amount-1} more)" if amount > 1 else "")))

    @commands.command(name="pause", help="Pause or resume playback.")
    @commands.guild_only()
    async def pause(self, ctx: commands.Context):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player:
            return await ctx.send(view=_simple(f"{e('cross')} Not playing", "Nothing playing.", color=ERROR))
        await player.pause(not player.paused)
        state = "Paused" if player.paused else "Resumed"
        icon = e("pause") if player.paused else e("play")
        await ctx.send(view=_simple(f"{icon} {state}", f"Playback {state.lower()}."))

    @commands.command(name="resume", help="Resume paused playback.")
    @commands.guild_only()
    async def resume(self, ctx: commands.Context):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player:
            return await ctx.send(view=_simple(f"{e('cross')} Not connected", "Not in voice.", color=ERROR))
        await player.pause(False)
        await ctx.send(view=_simple(f"{e('play')} Resumed", "Playback resumed."))

    @commands.command(name="stop", help="Stop playback, clear the queue, and disconnect.")
    @commands.guild_only()
    async def stop(self, ctx: commands.Context):
        e = emoji_manager.get
        player = ctx.voice_client
        if not player:
            return await ctx.send(view=_simple(f"{e('cross')} Not connected", "Not in voice.", color=ERROR))

        await self._stop_lofi(ctx.guild.id)
        await db.raw_execute("UPDATE vc247_state SET enabled=0 WHERE guild_id=?", (ctx.guild.id,))

        if isinstance(player, wavelink.Player):
            player.queue.clear()
            player.is_247 = False
            await player.disconnect()
        elif player.is_connected():
            await player.disconnect()

        await ctx.send(view=_simple(f"{e('stop')} Stopped", "Stopped playback and cleared the queue."))

    @commands.command(name="volume", aliases=["vol"], help="Set the playback volume (0–1000).")
    @commands.guild_only()
    async def volume_cmd(self, ctx: commands.Context, level: int):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player:
            return await ctx.send(view=_simple(f"{e('cross')} Not connected", "Not in voice.", color=ERROR))
        level = max(0, min(1000, level))
        await player.set_volume(level)
        await ctx.send(view=_simple(f"{e('volume')} Volume", f"Volume set to **{level}%**."))

    @commands.command(name="seek", help="Seek to a timestamp in the current track (e.g. 1:30 or 90).")
    @commands.guild_only()
    async def seek(self, ctx: commands.Context, position: str):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player or not player.current:
            return await ctx.send(view=_simple(f"{e('cross')} Not playing", "Nothing playing.", color=ERROR))
        parts = position.split(":")
        secs = sum(int(p) * (60 ** i) for i, p in enumerate(reversed(parts)))
        await player.seek(secs * 1000)
        await ctx.send(view=_simple(f"{e('play')} Seeked", f"Jumped to `{position}`."))

    @commands.command(name="nowplaying", aliases=["np"], help="Show the now-playing card with controls.")
    @commands.guild_only()
    async def nowplaying(self, ctx: commands.Context):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player or not player.current:
            return await ctx.send(view=_simple(f"{e('nowplaying')} Not playing", "Nothing is currently playing."))
        await ctx.send(view=NPLayout(player))

    @commands.command(name="queue", aliases=["q"], help="Show the current queue with pagination.")
    @commands.guild_only()
    async def queue_cmd(self, ctx: commands.Context):
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        await ctx.send(view=QueueLayout(player, ctx.author.id))

    @commands.command(name="remove", aliases=["rm"], help="Remove a track from the queue by its position number.")
    @commands.guild_only()
    async def remove(self, ctx: commands.Context, index: int):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player or player.queue.is_empty:
            return await ctx.send(view=_simple(f"{e('cross')} Queue empty", "Nothing in the queue.", color=ERROR))
        if index < 1 or index > len(player.queue):
            return await ctx.send(view=_simple(f"{e('cross')} Invalid", f"Index must be 1–{len(player.queue)}.", color=ERROR))
        removed = player.queue[index - 1]
        del player.queue[index - 1]
        await ctx.send(view=_simple(f"{e('check')} Removed", f"Removed **{removed.title}** from the queue."))

    @commands.command(name="move", aliases=["mv"], help="Move a track from one queue position to another.")
    @commands.guild_only()
    async def move(self, ctx: commands.Context, from_pos: int, to_pos: int):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player:
            return await ctx.send(view=_simple(f"{e('cross')} Not connected", "Not in voice.", color=ERROR))
        q = list(player.queue)
        if not (1 <= from_pos <= len(q) and 1 <= to_pos <= len(q)):
            return await ctx.send(view=_simple(f"{e('cross')} Invalid", "Invalid position(s).", color=ERROR))
        track = q.pop(from_pos - 1)
        q.insert(to_pos - 1, track)
        player.queue.clear()
        for t in q:
            player.queue.put(t)
        await ctx.send(view=_simple(f"{e('check')} Moved", f"Moved track #{from_pos} to position #{to_pos}."))

    @commands.command(name="shuffle", help="Shuffle the current queue.")
    @commands.guild_only()
    async def shuffle_cmd(self, ctx: commands.Context):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player or player.queue.is_empty:
            return await ctx.send(view=_simple(f"{e('cross')} Queue empty", "Nothing to shuffle.", color=ERROR))
        player.queue.shuffle()
        await ctx.send(view=_simple(f"{e('shuffle')} Shuffled", f"Shuffled **{len(player.queue)}** tracks."))

    @commands.command(name="loop", help="Set loop mode: off, track, or queue.")
    @commands.guild_only()
    async def loop_cmd(self, ctx: commands.Context, mode: str = "track"):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player:
            return await ctx.send(view=_simple(f"{e('cross')} Not connected", "Not in voice.", color=ERROR))
        mode_map = {"off": wavelink.QueueMode.normal, "track": wavelink.QueueMode.loop, "queue": wavelink.QueueMode.loop_all}
        if mode.lower() not in mode_map:
            return await ctx.send(view=_simple(f"{e('cross')} Invalid mode", "Use `off`, `track`, or `queue`.", color=ERROR))
        player.queue.mode = mode_map[mode.lower()]
        await ctx.send(view=_simple(f"{e('loop')} Loop", f"Loop mode set to `{mode}`."))

    @commands.command(name="autoplay", aliases=["ap"], help="Toggle automatic queuing of related tracks when queue ends.")
    @commands.guild_only()
    async def autoplay_cmd(self, ctx: commands.Context):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player:
            return await ctx.send(view=_simple(f"{e('cross')} Not connected", "Not in voice.", color=ERROR))
        if player.autoplay == wavelink.AutoPlayMode.disabled:
            player.autoplay = wavelink.AutoPlayMode.enabled
            await ctx.send(view=_simple(f"{e('play')} Autoplay enabled", "Will auto-queue related tracks when the queue ends.", color=SUCCESS))
        else:
            player.autoplay = wavelink.AutoPlayMode.disabled
            await ctx.send(view=_simple(f"{e('play')} Autoplay disabled", "Autoplay turned off."))

    @commands.command(name="filter", aliases=["fx"], help="Open the audio filter panel or apply a named filter.")
    @commands.guild_only()
    async def filter_cmd(self, ctx: commands.Context, preset: str = None):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player or not player.playing:
            return await ctx.send(view=_simple(f"{e('cross')} Not playing", "Play something first.", color=ERROR))
        if preset is None:
            return await ctx.send(view=FilterLayout(ctx.author.id))
        preset = preset.lower()
        if preset not in FILTER_DESCS:
            return await ctx.send(view=_simple(f"{e('cross')} Unknown filter", f"Options: {', '.join(FILTER_DESCS)}", color=ERROR))
        filters = wavelink.Filters()
        if preset == "bassboost":
            filters.equalizer.set(bands=[{"band": 0, "gain": 0.6}, {"band": 1, "gain": 0.67}])
        elif preset == "nightcore":
            filters.timescale.set(speed=1.2, pitch=1.2, rate=1.0)
        elif preset == "slowed":
            filters.timescale.set(speed=0.8, pitch=0.9, rate=1.0)
        elif preset == "vaporwave":
            filters.timescale.set(speed=0.85, pitch=0.85, rate=1.0)
        elif preset == "8d":
            filters.rotation.set(rotation_hz=0.2)
        elif preset == "karaoke":
            filters.karaoke.set(level=1.0, mono_level=1.0, filter_band=220.0, filter_width=100.0)
        await player.set_filters(filters)
        await ctx.send(view=_simple(f"{e('music_note')} Filter applied", f"Filter `{preset}` is now active.", color=SUCCESS))

    @commands.command(name="clearfilter", aliases=["nofx"], help="Remove all active audio filters.")
    @commands.guild_only()
    async def clearfilter(self, ctx: commands.Context):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player:
            return await ctx.send(view=_simple(f"{e('cross')} Not connected", "Not in voice.", color=ERROR))
        await player.set_filters(wavelink.Filters())
        await ctx.send(view=_simple(f"{e('check')} Filters cleared", "All audio filters removed."))

    @commands.command(name="disconnect", aliases=["dc", "vcleave"], help="Disconnect the bot from the voice channel.")
    @commands.guild_only()
    async def disconnect(self, ctx: commands.Context):
        e = emoji_manager.get
        player = ctx.voice_client
        if not player:
            return await ctx.send(view=_simple(f"{e('cross')} Not connected", "Not in voice.", color=ERROR))

        await self._stop_lofi(ctx.guild.id)
        await db.raw_execute("UPDATE vc247_state SET enabled=0 WHERE guild_id=?", (ctx.guild.id,))

        if isinstance(player, wavelink.Player):
            player.is_247 = False
            await player.disconnect()
        elif player.is_connected():
            await player.disconnect()

        await ctx.send(view=_simple(f"{e('check')} Disconnected", "Left the voice channel."))

    @commands.command(name="search", help="Search this server's default source (YouTube/SoundCloud/Spotify) and choose a track from results.")
    @commands.guild_only()
    async def search_cmd(self, ctx: commands.Context, *, query: str):
        e = emoji_manager.get
        player = await self._ensure_player(ctx)
        if not player:
            return
        source = await _get_default_source(ctx.guild.id)
        resolved_query = _build_search_query(query, source)
        tracks = await wavelink.Playable.search(resolved_query)
        if not tracks:
            body = f"Nothing found for `{query}`."
            if _is_spotify_query(resolved_query):
                body += "\n-# Spotify requires the Lavalink node to have the **LavaSrc** plugin configured."
            return await ctx.send(view=_simple(f"{e('cross')} No results", body, color=ERROR))
        results = tracks[:5] if isinstance(tracks, list) else tracks.tracks[:5]
        options = [
            discord.SelectOption(label=f"{i+1}. {t.title[:80]}", value=str(i), description=f"{t.author} · {_fmt(t.length)}")
            for i, t in enumerate(results)
        ]

        class SearchSelectRow(discord.ui.ActionRow):
            def __init__(self_row):
                super().__init__(
                    discord.ui.Select(placeholder="Select a track...", options=options, custom_id="music:search:select")
                )
                self_row.children[0].callback = self_row._on_select

            async def _on_select(self_row, interaction: discord.Interaction):
                await interaction.response.defer()
                track = results[int(interaction.data["values"][0])]
                track.extras = {"requester_id": interaction.user.id}
                if not player.playing:
                    await player.play(track)
                    msg = f"Now playing **{track.title}**."
                else:
                    player.queue.put(track)
                    msg = f"Added **{track.title}** to queue."
                layout = _simple(f"{e('music_note')} Track selected", msg, color=SUCCESS)
                await interaction.edit_original_response(view=layout)

        lines = [f"`{i+1}.` **{t.title}** — {t.author} `{_fmt(t.length)}`" for i, t in enumerate(results)]
        layout = discord.ui.LayoutView(timeout=60)
        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(f"## {e('music_note')} Search: `{query}`\n" + "\n".join(lines)))
        container.add_item(discord.ui.Separator())
        container.add_item(SearchSelectRow())
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {config.BOT_NAME} · Made by Soward Team"))
        layout.add_item(container)
        await ctx.send(view=layout)

    @commands.group(name="musicsource", aliases=["musrc", "defaultsource"], invoke_without_command=True,
                     help="View or set the default search provider for `play`/`playnext`/`search` (youtube, soundcloud, or spotify).")
    @commands.guild_only()
    async def music_source_group(self, ctx: commands.Context):
        e = emoji_manager.get
        current = await _get_default_source(ctx.guild.id)
        body = (
            f"**Current default:** `{SOURCE_LABELS[current]}`\n\n"
            "Use `musicsource set <youtube|soundcloud|spotify>` to change it.\n"
            "-# You can always override per-request: paste a link directly, use `soundcloud <query>` / `spotify <query>`,"
            " or prefix a search with `ytsearch:` / `scsearch:` / `spsearch:`."
        )
        await ctx.send(view=_simple(f"{e('music_note')} Default Search Source", body))

    @music_source_group.command(name="set", help="Set the default search provider: youtube, soundcloud, or spotify.")
    @has_guild_permission("manage_guild")
    async def music_source_set(self, ctx: commands.Context, source: str):
        e = emoji_manager.get
        source = source.lower()
        if source not in SEARCH_SOURCES:
            return await ctx.send(view=_simple(
                f"{e('cross')} Invalid source", "Choose from `youtube`, `soundcloud`, or `spotify`.", color=ERROR,
            ))
        await guild_settings.set(ctx.guild.id, "music_source", source)
        body = f"`play`, `playnext`, and `search` will now default to **{SOURCE_LABELS[source]}**."
        if source == "spotify" and not config.SPOTIFY_SEARCH_CONFIGURED:
            body += (
                "\n-# ⚠ The bot owner hasn't set Spotify credentials for this bot. Spotify search also requires the "
                "**LavaSrc** plugin (with Spotify API credentials) installed on the Lavalink node — searches will "
                "return no results until that's set up there."
            )
        await ctx.send(view=_simple(f"{e('check')} Default Source Set", body, color=SUCCESS))

    @commands.command(name="247", help="Toggle 24/7 mode — keeps the bot in voice even when the queue ends.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def mode_247(self, ctx: commands.Context):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        if not player:
            return await ctx.send(view=_simple(f"{e('cross')} Not connected", "Not in voice.", color=ERROR))
        player.is_247 = not player.is_247
        state = "enabled" if player.is_247 else "disabled"

        if player.is_247:
            await db.raw_execute(
                "INSERT INTO vc247_state (guild_id, enabled, voice_channel_id, text_channel_id) VALUES (?, 1, ?, ?)"
                " ON CONFLICT(guild_id) DO UPDATE SET enabled=1, voice_channel_id=excluded.voice_channel_id,"
                " text_channel_id=excluded.text_channel_id",
                (ctx.guild.id, player.channel.id if player.channel else None, ctx.channel.id),
            )
        else:
            await db.raw_execute("UPDATE vc247_state SET enabled=0 WHERE guild_id=?", (ctx.guild.id,))

        await ctx.send(view=_simple(f"{e('music_note')} 24/7 mode {state}",
            f"The bot will {'stay in voice when the queue ends' if player.is_247 else 'disconnect when idle'}."))

    @commands.group(name="lofi", invoke_without_command=True, help="View or manage the 24/7 lofi radio session.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def lofi_group(self, ctx: commands.Context):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT * FROM lofi_state WHERE guild_id=?", (ctx.guild.id,))
        enabled = bool(row["enabled"]) if row else False
        ch_id = row["channel_id"] if row else None
        radio_key = (row["radio_key"] or "groove_salad") if row else "groove_salad"
        stations = await self._get_stations(ctx.guild.id)
        station = stations.get(radio_key, RADIO_STATIONS["groove_salad"])
        body = (
            f"**Status:** {'🟢 Active' if enabled else '🔴 Inactive'}\n"
            f"**Channel:** {f'<#{ch_id}>' if ch_id else 'Not set'}\n"
            f"**Station:** {station['emoji']} {station['name']}\n\n"
            "-# Subcommands: `lofi 247 #vc` · `lofi channel #vc` · `lofi disable` · `lofi radio` · `lofi setup`"
        )
        await ctx.send(view=_simple(f"{e('music_note')} Lofi 24/7", body))

    @lofi_group.command(name="247", help="Start 24/7 lofi in a voice channel.")
    @has_guild_permission("manage_guild")
    async def lofi_247(self, ctx: commands.Context, channel: discord.VoiceChannel):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT radio_key FROM lofi_state WHERE guild_id=?", (ctx.guild.id,))
        radio_key = (row["radio_key"] or "groove_salad") if row else "groove_salad"
        ok = await self._start_lofi(ctx.guild, channel, radio_key, text_ch_id=ctx.channel.id)
        if not ok:
            return await ctx.send(view=_simple(f"{e('cross')} Failed to start", "Could not connect or stream that station.", color=ERROR))
        stations = await self._get_stations(ctx.guild.id)
        station = stations.get(radio_key, RADIO_STATIONS["groove_salad"])
        await ctx.send(view=_simple(f"{e('music_note')} 24/7 Lofi started",
            f"Streaming **{station['name']}** in {channel.mention}.\n-# `lofi disable` to stop · `lofi radio` to change station",
            color=SUCCESS))

    @lofi_group.command(name="channel", help="Move the lofi stream to a different voice channel.")
    @has_guild_permission("manage_guild")
    async def lofi_channel(self, ctx: commands.Context, channel: discord.VoiceChannel):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT * FROM lofi_state WHERE guild_id=?", (ctx.guild.id,))
        if not row or not row["enabled"]:
            return await ctx.send(view=_simple(f"{e('cross')} Not active", "Start lofi first with `lofi 247 #vc`.", color=ERROR))
        radio_key = row["radio_key"] or "groove_salad"
        text_ch_id = row["text_channel_id"] or ctx.channel.id
        ok = await self._start_lofi(ctx.guild, channel, radio_key, text_ch_id=text_ch_id)
        if not ok:
            return await ctx.send(view=_simple(f"{e('cross')} Failed", "Could not move to that channel.", color=ERROR))
        await ctx.send(view=_simple(f"{e('check')} Channel changed", f"Lofi moved to {channel.mention}.", color=SUCCESS))

    @lofi_group.command(name="disable", help="Stop the 24/7 lofi session.")
    @has_guild_permission("manage_guild")
    async def lofi_disable(self, ctx: commands.Context):
        e = emoji_manager.get
        await self._stop_lofi(ctx.guild.id)
        await ctx.send(view=_simple(f"{e('check')} Lofi disabled", "24/7 lofi session ended."))

    @lofi_group.command(name="radio", help="Change the lofi radio station via dropdown — includes custom stations.")
    @has_guild_permission("manage_guild")
    async def lofi_radio(self, ctx: commands.Context):
        row = await db.raw_fetchone("SELECT radio_key FROM lofi_state WHERE guild_id=?", (ctx.guild.id,))
        current_key = (row["radio_key"] or "groove_salad") if row else "groove_salad"
        stations = await self._get_stations(ctx.guild.id)
        await ctx.send(view=RadioLayout(current_key, ctx.author.id, stations))

    @lofi_group.command(name="setup", help="Interactive lofi setup — prompts for channel then shows station picker.")
    @has_guild_permission("manage_guild")
    async def lofi_setup(self, ctx: commands.Context):
        e = emoji_manager.get
        layout = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=NEUTRAL)
        container.add_item(discord.ui.TextDisplay(
            f"## {e('music_note')} Lofi setup — Step 1 of 2\n"
            "Which voice channel should lofi play in?\n\n"
            "**Mention or type the channel name.**\n-# You have 60 seconds to respond."
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(discord.ui.TextDisplay(f"-# {config.BOT_NAME} · Made by Soward Team"))
        layout.add_item(container)
        prompt = await ctx.send(view=layout)

        def check(m):
            return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

        try:
            reply = await self.bot.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            await prompt.edit(view=_simple(f"{e('cross')} Timed out", "Run `lofi setup` again.", color=ERROR))
            return

        vc = None
        if reply.channel_mentions:
            vc = reply.channel_mentions[0]
        else:
            name = reply.content.strip().lstrip("#").lower()
            vc = discord.utils.find(lambda ch: ch.name.lower() == name and isinstance(ch, discord.VoiceChannel), ctx.guild.channels)

        try:
            await reply.delete()
        except Exception:
            pass

        if not vc or not isinstance(vc, discord.VoiceChannel):
            await prompt.edit(view=_simple(f"{e('cross')} Not found", "Run `lofi setup` again.", color=ERROR))
            return

        await prompt.edit(view=LofiSetupLayout(vc, ctx.channel.id, ctx.author.id))

    @lofi_group.command(name="volume", help="Set the lofi stream volume (0–100).")
    @has_guild_permission("manage_guild")
    async def lofi_volume(self, ctx: commands.Context, level: int):
        e = emoji_manager.get
        lofi = self._lofi_players.get(ctx.guild.id)
        if not lofi or not isinstance(lofi.voice_client.source, discord.PCMVolumeTransformer):
            return await ctx.send(view=_simple(f"{e('cross')} Not playing", "Lofi is not currently playing.", color=ERROR))
        level = max(0, min(100, level))
        lofi.voice_client.source.volume = level / 100
        lofi.volume = level / 100
        await ctx.send(view=_simple(f"{e('volume')} Lofi volume", f"Volume set to **{level}%**."))

    @lofi_group.command(name="nowplaying", help="Show the currently playing lofi station.")
    @commands.guild_only()
    async def lofi_nowplaying(self, ctx: commands.Context):
        e = emoji_manager.get
        lofi = self._lofi_players.get(ctx.guild.id)
        if not lofi or not lofi.is_playing():
            return await ctx.send(view=_simple(f"{e('music_note')} Not playing", "No lofi station is currently playing."))
        await ctx.send(view=_simple(f"{e('music_note')} Lofi now playing",
            f"**Station:** {lofi.station_name}\n**Stream:** `{lofi.url[:80]}`"))

    @lofi_group.group(name="station", invoke_without_command=True, help="Manage custom lofi stations for this server.")
    @has_guild_permission("manage_guild")
    async def lofi_station(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await db.raw_fetch("SELECT key, name, url FROM custom_lofi_stations WHERE guild_id=?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(view=_simple(f"{e('music_note')} Custom stations",
                "No custom stations added yet.\nUse `lofi station add <key> <name> | <url>` to add one."))
        lines = [f"`{r['key']}` **{r['name']}** — `{r['url'][:60]}...`" for r in rows]
        await ctx.send(view=_simple(f"{e('music_note')} Custom stations ({len(rows)})", "\n".join(lines)))

    @lofi_station.command(name="add", help="Add a custom lofi stream. Format: lofi station add <key> <name> | <stream url>")
    @has_guild_permission("manage_guild")
    async def lofi_station_add(self, ctx: commands.Context, key: str, *, rest: str):
        e = emoji_manager.get
        if "|" not in rest:
            return await ctx.send(view=_simple(f"{e('cross')} Invalid format",
                "Use: `lofi station add <key> <name> | <stream url>`\nExample: `lofi station add chill Chill Vibes | https://stream.example.com/chill`",
                color=ERROR))
        name_part, url_part = rest.split("|", 1)
        name = name_part.strip()
        url = url_part.strip()
        if not name or not url:
            return await ctx.send(view=_simple(f"{e('cross')} Missing fields", "Both a name and URL are required.", color=ERROR))
        key = key.lower().replace(" ", "_")[:20]
        existing = await db.raw_fetchone("SELECT 1 FROM custom_lofi_stations WHERE guild_id=? AND key=?", (ctx.guild.id, key))
        if existing:
            return await ctx.send(view=_simple(f"{e('cross')} Key taken", f"A station with key `{key}` already exists. Use `lofi station remove {key}` first.", color=ERROR))
        count = await db.raw_fetchone("SELECT COUNT(*) as c FROM custom_lofi_stations WHERE guild_id=?", (ctx.guild.id,))
        if count and count["c"] >= 20:
            return await ctx.send(view=_simple(f"{e('cross')} Limit reached", "Max 20 custom stations per server.", color=ERROR))
        await db.raw_execute(
            "INSERT INTO custom_lofi_stations (guild_id, key, name, url, added_by) VALUES (?, ?, ?, ?, ?)",
            (ctx.guild.id, key, name[:50], url, ctx.author.id),
        )
        await ctx.send(view=_simple(f"{e('check')} Station added",
            f"**{name}** added as `{key}`.\nUse `lofi radio` to switch to it.", color=SUCCESS))

    @lofi_station.command(name="remove", aliases=["del"], help="Remove a custom lofi station by its key.")
    @has_guild_permission("manage_guild")
    async def lofi_station_remove(self, ctx: commands.Context, key: str):
        e = emoji_manager.get
        cur = await db.raw_execute("DELETE FROM custom_lofi_stations WHERE guild_id=? AND key=?", (ctx.guild.id, key.lower()))
        if cur.rowcount:
            await ctx.send(view=_simple(f"{e('check')} Station removed", f"Station `{key}` has been removed."))
        else:
            await ctx.send(view=_simple(f"{e('cross')} Not found", f"No custom station with key `{key}`.", color=ERROR))

    @lofi_station.command(name="test", help="Test a custom station by playing it briefly in your current voice channel.")
    @has_guild_permission("manage_guild")
    async def lofi_station_test(self, ctx: commands.Context, key: str):
        e = emoji_manager.get
        if not ctx.author.voice:
            return await ctx.send(view=_simple(f"{e('cross')} Not in voice", "Join a voice channel to test a station.", color=ERROR))
        row = await db.raw_fetchone("SELECT * FROM custom_lofi_stations WHERE guild_id=? AND key=?", (ctx.guild.id, key.lower()))
        if not row:
            return await ctx.send(view=_simple(f"{e('cross')} Not found", f"No custom station with key `{key}`.", color=ERROR))

        existing = self._lofi_players.get(ctx.guild.id)
        if existing:
            await existing.stop()
            self._lofi_players.pop(ctx.guild.id, None)

        try:
            voice_client = ctx.voice_client
            if voice_client and not isinstance(voice_client, wavelink.Player):
                if voice_client.channel != ctx.author.voice.channel:
                    await voice_client.move_to(ctx.author.voice.channel)
            else:
                if voice_client:
                    await voice_client.disconnect(force=True)
                voice_client = await ctx.author.voice.channel.connect(self_deaf=True)
        except Exception as ex:
            return await ctx.send(view=_simple(f"{e('cross')} Connection failed", str(ex), color=ERROR))

        lofi_player = LofiPlayer(voice_client, row["name"], row["url"])
        if not await lofi_player.start():
            return await ctx.send(view=_simple(f"{e('cross')} Unplayable", f"Could not load stream from `{row['url']}`.", color=ERROR))

        self._lofi_players[ctx.guild.id] = lofi_player
        await ctx.send(view=_simple(f"{e('music_note')} Testing station",
            f"Playing **{row['name']}** — use `lofi disable` or `stop` to stop.", color=SUCCESS))

    @commands.group(name="playlist", aliases=["pl"], invoke_without_command=True, help="Manage your personal saved playlists.")
    @commands.guild_only()
    async def playlist_group(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await db.raw_fetch("SELECT playlist_id, name, tracks FROM user_playlists WHERE user_id=?", (ctx.author.id,))
        if not rows:
            return await ctx.send(view=_simple(f"{e('disc')} Your playlists",
                "No saved playlists.\nUse `playlist save <name>` while tracks are queued."))
        lines = [f"`{r['playlist_id'][:6]}` **{r['name']}** — {len(json.loads(r['tracks']))} tracks" for r in rows]
        await ctx.send(view=_simple(f"{e('disc')} Your playlists", "\n".join(lines)))

    @playlist_group.command(name="save", help="Save the current queue as a named playlist.")
    async def playlist_save(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        player: MusicPlayer = ctx.voice_client
        if player is not None and not isinstance(player, wavelink.Player):
            player = None
        all_tracks = []
        if player and player.current:
            all_tracks.append(player.current)
        if player and not player.queue.is_empty:
            all_tracks.extend(list(player.queue))
        if not all_tracks:
            return await ctx.send(view=_simple(f"{e('cross')} Empty queue", "Nothing in the queue to save.", color=ERROR))
        count = await db.raw_fetchone("SELECT COUNT(*) as c FROM user_playlists WHERE user_id=?", (ctx.author.id,))
        if count and count["c"] >= 25:
            return await ctx.send(view=_simple(f"{e('cross')} Limit reached", "Max 25 playlists per user.", color=ERROR))
        track_data = [{"title": t.title, "author": t.author, "uri": t.uri, "length": t.length} for t in all_tracks]
        pid = str(uuid.uuid4())
        await db.raw_execute(
            "INSERT INTO user_playlists (playlist_id, user_id, name, tracks, created_at) VALUES (?, ?, ?, ?, ?)",
            (pid, ctx.author.id, name[:50], json.dumps(track_data), time.time()),
        )
        await ctx.send(view=_simple(f"{e('disc')} Saved", f"**{name}** saved with **{len(track_data)}** tracks.", color=SUCCESS))

    @playlist_group.command(name="load", help="Load a saved playlist into the queue.")
    @commands.guild_only()
    async def playlist_load(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT * FROM user_playlists WHERE user_id=? AND LOWER(name)=LOWER(?)", (ctx.author.id, name))
        if not row:
            return await ctx.send(view=_simple(f"{e('cross')} Not found", f"No playlist named `{name}`.", color=ERROR))
        player = await self._ensure_player(ctx)
        if not player:
            return
        tracks_data = json.loads(row["tracks"])
        loaded = 0
        first = not player.playing
        for td in tracks_data[:config.MUSIC_MAX_PLAYLIST_TRACKS]:
            try:
                results = await wavelink.Playable.search(td.get("uri") or f"ytmsearch:{td['title']}")
                if not results:
                    continue
                track = results[0] if isinstance(results, list) else results.tracks[0]
                track.extras = {"requester_id": ctx.author.id}
                if first and not player.playing:
                    await player.play(track)
                    first = False
                else:
                    player.queue.put(track)
                loaded += 1
            except Exception:
                continue
        await ctx.send(view=_simple(f"{e('disc')} Loaded",
            f"Loaded **{loaded}** tracks from **{row['name']}**.", color=SUCCESS))

    @playlist_group.command(name="delete", aliases=["del"], help="Delete a saved playlist.")
    async def playlist_delete(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        cur = await db.raw_execute("DELETE FROM user_playlists WHERE user_id=? AND LOWER(name)=LOWER(?)", (ctx.author.id, name))
        if cur.rowcount:
            await ctx.send(view=_simple(f"{e('check')} Deleted", f"Playlist **{name}** deleted."))
        else:
            await ctx.send(view=_simple(f"{e('cross')} Not found", f"No playlist named `{name}`.", color=ERROR))

    @playlist_group.command(name="view", help="View the tracks in a saved playlist.")
    async def playlist_view(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT * FROM user_playlists WHERE user_id=? AND LOWER(name)=LOWER(?)", (ctx.author.id, name))
        if not row:
            return await ctx.send(view=_simple(f"{e('cross')} Not found", f"No playlist named `{name}`.", color=ERROR))
        tracks = json.loads(row["tracks"])
        lines = [f"`{i+1}.` **{t['title']}** — {t['author']} `{_fmt(t.get('length', 0))}`" for i, t in enumerate(tracks[:20])]
        if len(tracks) > 20:
            lines.append(f"...and {len(tracks)-20} more")
        await ctx.send(view=_simple(f"{e('disc')} {row['name']}", "\n".join(lines)))

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        from utils import guild_settings
        from utils.prefix import get_guild_prefix
        ch_id = await guild_settings.get(message.guild.id, "music_247_channel_id")
        if not ch_id or message.channel.id != int(ch_id):
            return
        content = message.content.strip()
        if not content:
            return
        prefix = await get_guild_prefix(message.guild.id)
        if content.startswith(prefix) or content.startswith(f"<@{self.bot.user.id}>"):
            return
        vc_id = await guild_settings.get(message.guild.id, "music_247_vc_id")
        if not vc_id:
            return
        vc = message.guild.get_channel(int(vc_id))
        if not vc or not isinstance(vc, discord.VoiceChannel):
            return
        player: MusicPlayer = message.guild.voice_client
        if player is None:
            try:
                player = await vc.connect(cls=MusicPlayer, self_deaf=True)
                player.text_channel_id = message.channel.id
            except Exception:
                return
        source = await _get_default_source(message.guild.id)
        content = _build_search_query(content, source)
        try:
            tracks = await wavelink.Playable.search(content)
        except Exception:
            return
        if not tracks:
            return
        track = tracks[0] if isinstance(tracks, list) else tracks.tracks[0]
        track.extras = {"requester_id": message.author.id}
        if not player.playing:
            await player.play(track)
        else:
            player.queue.put(track)
            try:
                await message.add_reaction("✅")
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
