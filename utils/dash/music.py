from __future__ import annotations

import re

import discord

from utils import db
from utils.dash.base import (
    ActionContext, action, button, fld, need_choice, need_text, opt_channel, row, section, table,
)

VOICE = (discord.VoiceChannel, discord.StageChannel)
KEY_PATTERN = re.compile(r"[a-z0-9_]{1,20}")
MAX_CUSTOM_STATIONS = 20


def _cog(ctx: ActionContext):
    cog = ctx.bot.get_cog("Music")
    if cog is None:
        raise ValueError("Music is not loaded right now.")
    return cog


def _voice(ctx: ActionContext, values: dict, key: str = "voice") -> discord.VoiceChannel:
    channel = opt_channel(ctx.guild, values, key, "Voice channel", VOICE)
    if channel is None:
        raise ValueError("Pick a voice channel.")
    perms = channel.permissions_for(ctx.guild.me)
    if not (perms.connect and perms.speak):
        raise ValueError(f"I need Connect and Speak in {channel.name}.")
    return channel


async def _stations(ctx_or_guild) -> dict:
    guild = getattr(ctx_or_guild, "guild", ctx_or_guild)
    from cogs.music import RADIO_STATIONS
    stations = dict(RADIO_STATIONS)
    for r in await db.raw_fetch("SELECT key, name, url FROM custom_lofi_stations WHERE guild_id=?", (guild.id,)):
        stations[r["key"]] = {"name": r["name"], "url": r["url"], "emoji": "", "custom": True}
    return stations


def _channel_name(guild: discord.Guild, channel_id) -> str:
    channel = guild.get_channel(int(channel_id)) if channel_id else None
    return channel.name if channel else "Not set"


@section("music")
async def lofi_section(guild: discord.Guild) -> dict:
    state = await db.raw_fetchone("SELECT * FROM lofi_state WHERE guild_id=?", (guild.id,))
    stations = await _stations(guild)
    options = [(k, s["name"]) for k, s in stations.items()]
    on = bool(state and state["enabled"])
    key = (state["radio_key"] if state else None) or "groove_salad"
    station = stations.get(key) or stations["groove_salad"]
    start_fields = [
        fld("voice", "Voice channel", "voice"),
        fld("station", "Station", "select", value=key, options=options),
        fld("text_channel", "Text channel", "channel", help="Optional. Where the bot posts lofi messages."),
    ]
    acts = []
    if on:
        acts = [
            button("lofi_station", "Change station", [fld("station", "Station", "select", value=key, options=options)], prefill=True, title="Change station", submit="Switch"),
            button("lofi_start", "Move", [fld("voice", "Voice channel", "voice"), fld("station", "Station", "select", value=key, options=options)], title="Move lofi", submit="Move"),
            button("lofi_stop", "Stop", style="danger", confirm="Stop the 24/7 lofi stream and leave the voice channel?"),
        ]
    return table(
        "lofi", "Lofi radio", ["Status", "Voice channel", "Station"],
        [row("main", ["Live" if on else "Stopped", _channel_name(guild, state["channel_id"]) if state else "Not set", station["name"]], acts, {"station": key})],
        "",
        description="Streams a radio station around the clock and rejoins after a restart.",
        buttons=[button("lofi_start", "Start lofi" if not on else "Restart lofi", start_fields, style="primary", title="Start 24/7 lofi", submit="Start")],
    )


@section("music")
async def always_on_section(guild: discord.Guild) -> dict:
    state = await db.raw_fetchone("SELECT * FROM vc247_state WHERE guild_id=?", (guild.id,))
    on = bool(state and state["enabled"])
    acts = [button("vc247_disable", "Disable", style="danger", confirm="Let the bot leave the voice channel when the queue ends?")] if on else []
    return table(
        "always_on", "24/7 mode", ["Status", "Voice channel", "Text channel"],
        [row("main", ["On" if on else "Off", _channel_name(guild, state["voice_channel_id"]) if state else "Not set",
                      _channel_name(guild, state["text_channel_id"]) if state else "Not set"], acts)],
        "",
        description="Keeps the bot in a voice channel even when the music queue is empty.",
        buttons=[button("vc247_enable", "Enable 24/7" if not on else "Change channel", [
            fld("voice", "Voice channel", "voice"),
            fld("text_channel", "Text channel", "channel", help="Optional. Where music messages are posted."),
        ], style="primary", title="Enable 24/7 mode", submit="Enable")],
    )


@section("music")
async def stations_section(guild: discord.Guild) -> dict:
    stations = await _stations(guild)
    rows = []
    for key, s in stations.items():
        custom = bool(s.get("custom"))
        rows.append(row(
            key, [s["name"], key, "Custom" if custom else "Built in", s["url"][:60]],
            [button("station_remove", "Remove", style="danger", confirm=f"Remove the station {s['name']}?")] if custom else [],
        ))
    custom_count = sum(1 for s in stations.values() if s.get("custom"))
    return table(
        "stations", f"Stations ({custom_count}/{MAX_CUSTOM_STATIONS} custom)", ["Name", "Key", "Type", "Stream"], rows, "No stations.",
        description="Built in stations are available everywhere. Add your own stream URLs.",
        buttons=[button("station_add", "Add station", [
            fld("key", "Key", "text", maxlen=20, help="Short id with letters, numbers and underscores."),
            fld("name", "Name", "text", maxlen=50),
            fld("url", "Stream URL", "text", maxlen=500, placeholder="https://"),
        ], style="primary", title="Add station", submit="Add")],
    )


@action("music", "lofi_start")
async def lofi_start(ctx: ActionContext, payload: dict) -> list:
    values = payload.get("values") or {}
    cog = _cog(ctx)
    stations = await _stations(ctx)
    key = need_choice(values, "station", "Station", list(stations))
    voice = _voice(ctx, values)
    text = opt_channel(ctx.guild, values, "text_channel", "Text channel")
    if text is None:
        state = await db.raw_fetchone("SELECT text_channel_id FROM lofi_state WHERE guild_id=?", (ctx.guild.id,))
        text_id = state["text_channel_id"] if state else None
    else:
        text_id = text.id
    if not await cog._start_lofi(ctx.guild, voice, key, text_ch_id=text_id):
        raise ValueError("Could not connect or stream that station. Check the bot's voice permissions and that ffmpeg is installed.")
    return [f"Lofi started: {stations[key]['name']} in {voice.name}"]


@action("music", "lofi_station")
async def lofi_station(ctx: ActionContext, payload: dict) -> list:
    values = payload.get("values") or {}
    cog = _cog(ctx)
    stations = await _stations(ctx)
    key = need_choice(values, "station", "Station", list(stations))
    state = await db.raw_fetchone("SELECT * FROM lofi_state WHERE guild_id=?", (ctx.guild.id,))
    if not state or not state["enabled"]:
        raise ValueError("Lofi is not running. Start it first.")
    voice = ctx.guild.get_channel(int(state["channel_id"])) if state["channel_id"] else None
    if not isinstance(voice, VOICE):
        raise ValueError("The lofi voice channel no longer exists. Start lofi again.")
    if not await cog._start_lofi(ctx.guild, voice, key, text_ch_id=state["text_channel_id"]):
        raise ValueError("Could not stream that station.")
    return [f"Lofi station: {stations[key]['name']}"]


@action("music", "lofi_stop")
async def lofi_stop(ctx: ActionContext, payload: dict) -> list:
    cog = _cog(ctx)
    state = await db.raw_fetchone("SELECT enabled FROM lofi_state WHERE guild_id=?", (ctx.guild.id,))
    if not state or not state["enabled"]:
        raise ValueError("Lofi is not running.")
    await cog._stop_lofi(ctx.guild.id)
    return ["Lofi stopped"]


@action("music", "vc247_enable")
async def vc247_enable(ctx: ActionContext, payload: dict) -> list:
    from cogs.music import MusicPlayer
    values = payload.get("values") or {}
    voice = _voice(ctx, values)
    text = opt_channel(ctx.guild, values, "text_channel", "Text channel")
    client = ctx.guild.voice_client
    if client is not None and not isinstance(client, MusicPlayer):
        raise ValueError("Lofi is using the voice connection. Stop lofi first.")
    try:
        if client is None:
            client = await voice.connect(cls=MusicPlayer, self_deaf=True)
        elif client.channel != voice:
            await client.move_to(voice)
    except (discord.ClientException, discord.HTTPException, TimeoutError):
        raise ValueError("Could not join that voice channel.")
    client.is_247 = True
    if text is not None:
        client.text_channel_id = text.id
    await db.raw_execute(
        "INSERT INTO vc247_state (guild_id, enabled, voice_channel_id, text_channel_id) VALUES (?, 1, ?, ?)"
        " ON CONFLICT(guild_id) DO UPDATE SET enabled=1, voice_channel_id=excluded.voice_channel_id,"
        " text_channel_id=excluded.text_channel_id",
        (ctx.guild.id, voice.id, text.id if text else None),
    )
    return [f"24/7 mode on in {voice.name}"]


@action("music", "vc247_disable")
async def vc247_disable(ctx: ActionContext, payload: dict) -> list:
    from cogs.music import MusicPlayer
    state = await db.raw_fetchone("SELECT enabled FROM vc247_state WHERE guild_id=?", (ctx.guild.id,))
    if not state or not state["enabled"]:
        raise ValueError("24/7 mode is not on.")
    await db.raw_execute("UPDATE vc247_state SET enabled=0 WHERE guild_id=?", (ctx.guild.id,))
    client = ctx.guild.voice_client
    if isinstance(client, MusicPlayer):
        client.is_247 = False
    return ["24/7 mode off"]


@action("music", "station_add")
async def station_add(ctx: ActionContext, payload: dict) -> list:
    from cogs.music import RADIO_STATIONS
    values = payload.get("values") or {}
    key = need_text(values, "key", "Key", maxlen=20).lower().replace(" ", "_")
    if not KEY_PATTERN.fullmatch(key):
        raise ValueError("Key can only contain letters, numbers and underscores.")
    if key in RADIO_STATIONS:
        raise ValueError("That key belongs to a built in station.")
    name = need_text(values, "name", "Name", maxlen=50)
    url = need_text(values, "url", "Stream URL", maxlen=500)
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValueError("Stream URL must start with http:// or https://.")
    if await db.raw_fetchone("SELECT 1 FROM custom_lofi_stations WHERE guild_id=? AND key=?", (ctx.guild.id, key)):
        raise ValueError("A station with that key already exists.")
    count = await db.raw_fetchone("SELECT COUNT(*) AS c FROM custom_lofi_stations WHERE guild_id=?", (ctx.guild.id,))
    if count and count["c"] >= MAX_CUSTOM_STATIONS:
        raise ValueError(f"Servers can have up to {MAX_CUSTOM_STATIONS} custom stations.")
    await db.raw_execute(
        "INSERT INTO custom_lofi_stations (guild_id, key, name, url, added_by) VALUES (?, ?, ?, ?, ?)",
        (ctx.guild.id, key, name, url, ctx.user_id),
    )
    return [f"Added station {name}"]


@action("music", "station_remove")
async def station_remove(ctx: ActionContext, payload: dict) -> list:
    key = str(payload.get("id") or "").lower()
    cur = await db.raw_execute("DELETE FROM custom_lofi_stations WHERE guild_id=? AND key=?", (ctx.guild.id, key))
    if not cur.rowcount:
        raise ValueError("That station no longer exists.")
    return [f"Removed station {key}"]
