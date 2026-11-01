import time
from collections import defaultdict, deque

import discord
from discord.ext import commands, tasks

from utils import emoji_manager, guild_settings, size_gate
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import LOG_EVENT, bus

WINDOW = 10.0
STEPS = (3, 5, 10, 20, 30)
CALM_SECONDS = 180
COOLDOWN = 30.0
KEYS = {
    "enabled": ("smartslow_enabled", False),
    "threshold": ("smartslow_threshold", 20),
    "max": ("smartslow_max", 20),
}


async def get_config(guild_id: int) -> dict:
    out = {}
    for name, (key, default) in KEYS.items():
        out[name] = await guild_settings.get(guild_id, key, default)
    out["threshold"] = max(8, min(200, int(out["threshold"] or 20)))
    out["max"] = max(3, min(120, int(out["max"] or 20)))
    return out


class SmartSlowmode(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hits: dict[int, deque] = defaultdict(lambda: deque(maxlen=400))
        self.cache: dict[int, tuple[float, dict]] = {}
        self.last_change: dict[int, float] = {}
        self.restore_loop.start()

    def cog_unload(self):
        self.restore_loop.cancel()

    async def config(self, guild: discord.Guild) -> dict:
        cached = self.cache.get(guild.id)
        if cached and time.monotonic() - cached[0] < 30:
            return cached[1]
        cfg = await get_config(guild.id)
        cfg["allowed"] = cfg["enabled"] and await size_gate.allowed(guild)
        self.cache[guild.id] = (time.monotonic(), cfg)
        return cfg

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot or not isinstance(message.channel, discord.TextChannel):
            return
        cfg = await self.config(message.guild)
        if not cfg["allowed"]:
            return
        channel = message.channel
        now = time.monotonic()
        pool = self.hits[channel.id]
        pool.append((now, message.author.id))
        while pool and now - pool[0][0] > WINDOW:
            pool.popleft()
        if len(pool) < cfg["threshold"] or len({u for _, u in pool}) < 4:
            return
        if now - self.last_change.get(channel.id, -COOLDOWN) < COOLDOWN:
            return
        me = message.guild.me
        if not channel.permissions_for(me).manage_channels:
            return
        active = await guild_settings.get(message.guild.id, "smartslow_active", {}) or {}
        entry = active.get(str(channel.id))
        current = channel.slowmode_delay
        target = next((s for s in STEPS if s > current and s <= cfg["max"]), None)
        if target is None:
            return
        try:
            await channel.edit(slowmode_delay=target, reason="Smart slowmode: chat is moving very fast")
        except discord.HTTPException:
            return
        self.last_change[channel.id] = now
        active[str(channel.id)] = {"orig": entry["orig"] if entry else current, "calm_since": None, "level": target}
        await guild_settings.set(message.guild.id, "smartslow_active", active)
        await bus.publish(LOG_EVENT, guild_id=message.guild.id, action="slowmode", actor_id=None, detail=f"{channel.mention} slowmode raised to {target}s because of a message burst")

    @tasks.loop(seconds=30)
    async def restore_loop(self):
        for guild in self.bot.guilds:
            active = await guild_settings.get(guild.id, "smartslow_active", {}) or {}
            if not active:
                continue
            cfg = await self.config(guild)
            changed = False
            for channel_id, entry in list(active.items()):
                channel = guild.get_channel(int(channel_id))
                if channel is None:
                    active.pop(channel_id)
                    changed = True
                    continue
                recent = [t for t, _ in self.hits.get(channel.id, ()) if time.monotonic() - t <= WINDOW]
                busy = len(recent) >= max(4, cfg["threshold"] // 2) and cfg["allowed"]
                if busy:
                    if entry.get("calm_since") is not None:
                        entry["calm_since"] = None
                        changed = True
                    continue
                if entry.get("calm_since") is None:
                    entry["calm_since"] = time.time()
                    changed = True
                    continue
                if time.time() - entry["calm_since"] < CALM_SECONDS:
                    continue
                try:
                    if channel.slowmode_delay == entry["level"]:
                        await channel.edit(slowmode_delay=entry["orig"], reason="Smart slowmode: chat calmed down")
                except discord.HTTPException:
                    continue
                active.pop(channel_id)
                changed = True
            if changed:
                if active:
                    await guild_settings.set(guild.id, "smartslow_active", active)
                else:
                    await guild_settings.delete(guild.id, "smartslow_active")

    @restore_loop.before_loop
    async def before_restore(self):
        await self.bot.wait_until_ready()

    @commands.group(name="smartslow", aliases=["autoslow"], invoke_without_command=True, help="Slowmode that rises on its own when chat floods. Servers with 500+ members.")
    @commands.guild_only()
    @has_guild_permission("manage_channels")
    async def smartslow(self, ctx: commands.Context):
        cfg = await get_config(ctx.guild.id)
        allowed = await size_gate.allowed(ctx.guild)
        note = "" if allowed else "\n\n" + size_gate.blocked_text(ctx.guild, "Smart slowmode")
        await ctx.send(view=info_layout("Smart slowmode", (
            f"**Status:** {'on' if cfg['enabled'] else 'off'} · **Trigger:** {cfg['threshold']} messages in 10 seconds from 4+ people · **Highest slowmode:** {cfg['max']}s\n"
            "When a channel floods, slowmode steps up. After 3 calm minutes it goes back to what it was.\n"
            "`smartslow on|off` · `smartslow trigger <8-200>` · `smartslow max <3-120>`" + note)))

    async def _set(self, ctx: commands.Context, name: str, value, text: str):
        key, _ = KEYS[name]
        await guild_settings.set(ctx.guild.id, key, value)
        self.cache.pop(ctx.guild.id, None)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Smart slowmode", text))

    @smartslow.command(name="on", help="Turn it on.")
    @has_guild_permission("manage_channels")
    async def smartslow_on(self, ctx: commands.Context):
        if not await size_gate.allowed(ctx.guild):
            return await ctx.send(view=info_layout("Smart slowmode", size_gate.blocked_text(ctx.guild, "Smart slowmode")))
        await self._set(ctx, "enabled", True, "Smart slowmode is **on**. I need Manage Channels in the channels it should protect.")

    @smartslow.command(name="off", help="Turn it off.")
    @has_guild_permission("manage_channels")
    async def smartslow_off(self, ctx: commands.Context):
        await self._set(ctx, "enabled", False, "Smart slowmode is **off**.")

    @smartslow.command(name="trigger", help="Messages in 10 seconds that count as a flood.")
    @has_guild_permission("manage_channels")
    async def smartslow_trigger(self, ctx: commands.Context, amount: int):
        if not 8 <= amount <= 200:
            return await ctx.send(view=error_layout("Invalid number", "Use 8 to 200."))
        await self._set(ctx, "threshold", amount, f"A flood is **{amount}** messages in 10 seconds from at least 4 people.")

    @smartslow.command(name="max", help="Highest slowmode in seconds it may set.")
    @has_guild_permission("manage_channels")
    async def smartslow_max(self, ctx: commands.Context, seconds: int):
        if not 3 <= seconds <= 120:
            return await ctx.send(view=error_layout("Invalid number", "Use 3 to 120."))
        await self._set(ctx, "max", seconds, f"Slowmode will not go above **{seconds}s**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(SmartSlowmode(bot))
