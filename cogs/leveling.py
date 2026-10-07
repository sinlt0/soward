import io
import time
import uuid
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks
from PIL import Image, ImageDraw, ImageFont, ImageOps

import config
from utils import db, emoji_manager, message_vars, xp_engine
from utils.checks import has_guild_permission
from utils.colors import ERROR, NEUTRAL, SUCCESS
from utils.components import ConfirmLayout, error_layout, footer_block, info_layout, success_layout


LEVELING_VARIABLE_DOCS = {
    "level": "The member's new level",
    "oldlevel": "The member's previous level",
    "xp": "The member's total XP",
    "rank": "The member's current leaderboard position",
}

PERIOD_LABELS = {"alltime": "All-Time", "weekly": "Weekly", "monthly": "Monthly"}


def _layout(title: str, body: str, *, color: int = NEUTRAL) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


def _circle_mask(size: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse((0, 0, size, size), fill=255)
    return mask


def _load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


class Leveling(commands.Cog):
    category = "Engagement"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: Optional[aiohttp.ClientSession] = None
        self._voice_sessions: dict[tuple[int, int], float] = {}

    async def cog_load(self):
        self._session = aiohttp.ClientSession()
        self.voice_xp_loop.start()
        self.period_reset_loop.start()

    def cog_unload(self):
        self.voice_xp_loop.cancel()
        self.period_reset_loop.cancel()
        if self._session:
            self.bot.loop.create_task(self._session.close())

    async def _generate_rank_card(self, member: discord.Member, xp_row: dict, rank_position: int) -> discord.File:
        W, H = 900, 260
        canvas = Image.new("RGB", (W, H), (24, 24, 28))
        draw = ImageDraw.Draw(canvas)

        accent = member.top_role.color
        accent_rgb = accent.to_rgb() if accent.value != 0 else (138, 99, 255)

        draw.rectangle([0, 0, 10, H], fill=accent_rgb)

        avatar_size = 150
        try:
            async with self._session.get(member.display_avatar.replace(size=256).url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                avatar_bytes = await r.read()
            avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((avatar_size, avatar_size))
            mask = _circle_mask(avatar_size)
            avatar_circle = ImageOps.fit(avatar_img, (avatar_size, avatar_size))
            canvas.paste(avatar_circle, (50, 55), mask)
        except Exception:
            pass

        draw.ellipse([48, 53, 48 + avatar_size + 4, 53 + avatar_size + 4], outline=accent_rgb, width=4)

        name_font = _load_font(32, bold=True)
        sub_font = _load_font(18)
        stat_font = _load_font(22, bold=True)
        stat_label_font = _load_font(14)

        text_x = 230
        draw.text((text_x, 60), member.display_name[:22], font=name_font, fill=(240, 240, 245))
        draw.text((text_x, 100), f"Rank #{rank_position}", font=sub_font, fill=(160, 160, 168))

        level = xp_row["level"]
        total_xp = xp_row["xp"]
        into_level, needed_for_level = xp_engine.xp_progress(total_xp, level)

        bar_x, bar_y, bar_w, bar_h = text_x, 160, 560, 22
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_w, bar_y + bar_h], bar_h // 2, fill=(45, 45, 52))
        pct = min(into_level / needed_for_level, 1.0) if needed_for_level else 0
        if pct > 0:
            draw.rounded_rectangle([bar_x, bar_y, bar_x + int(bar_w * pct), bar_y + bar_h], bar_h // 2, fill=accent_rgb)

        draw.text((bar_x, bar_y - 28), f"{into_level:,} / {needed_for_level:,} XP", font=stat_label_font, fill=(180, 180, 188))

        level_x = 720
        draw.text((level_x, 60), "LEVEL", font=stat_label_font, fill=(140, 140, 148))
        draw.text((level_x, 78), str(level), font=stat_font, fill=(240, 240, 245))
        if xp_row.get("prestige", 0) > 0:
            draw.text((level_x, 110), f"Prestige {xp_row['prestige']}", font=stat_label_font, fill=accent_rgb)

        buf = io.BytesIO()
        canvas.save(buf, format="PNG")
        buf.seek(0)
        return discord.File(buf, "rank-card.png")

    async def _announce_level_up(self, guild: discord.Guild, member: discord.Member, result: dict, guild_config: dict):
        mode = guild_config["announce_mode"]
        if mode == "off":
            return

        template = guild_config["announce_message"] or (
            "{user} just reached **level {level}**!"
        )

        rank_row = await db.raw_fetchone(
            "SELECT COUNT(*) + 1 as rank FROM member_xp WHERE guild_id=? AND xp > ?",
            (guild.id, result["total_xp"]),
        )
        var_map = message_vars.build_base_variables(member, guild)
        var_map.update({
            "level": str(result["new_level"]),
            "oldlevel": str(result["old_level"]),
            "xp": str(result["total_xp"]),
            "rank": str(rank_row["rank"] if rank_row else "?"),
        })
        text = message_vars.substitute(template, var_map)

        if mode == "dm":
            try:
                await member.send(text)
            except discord.HTTPException:
                pass
            return

        channel = guild.get_channel(guild_config["announce_channel_id"]) if guild_config["announce_channel_id"] else None
        if channel:
            try:
                await channel.send(text)
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_config = await xp_engine.get_guild_config(message.guild.id)
        if not guild_config["enabled"]:
            return

        if await xp_engine.is_no_xp_channel(message.guild.id, message.channel.id):
            return
        if await xp_engine.has_no_xp_role(message.guild.id, message.author):
            return

        row = await db.raw_fetchone(
            "SELECT last_text_xp_at FROM member_xp WHERE guild_id=? AND user_id=?", (message.guild.id, message.author.id)
        )
        last_xp_at = row["last_text_xp_at"] if row else 0
        if time.time() - last_xp_at < guild_config["text_cooldown_seconds"]:
            return

        base_xp = xp_engine.roll_text_xp(guild_config)
        result = await xp_engine.add_xp(message.guild.id, message.author.id, base_xp, message.author, message.channel.id)

        if result["leveled_up"]:
            new_roles = await xp_engine.apply_role_rewards(
                message.guild, message.author, result["new_level"], guild_config["role_stack_mode"]
            )
            await self._announce_level_up(message.guild, message.author, result, guild_config)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot:
            return

        key = (member.guild.id, member.id)

        if after.channel and not before.channel:
            self._voice_sessions[key] = time.time()
        elif before.channel and not after.channel:
            self._voice_sessions.pop(key, None)

    @tasks.loop(minutes=1)
    async def voice_xp_loop(self):
        for (guild_id, user_id), joined_at in list(self._voice_sessions.items()):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            member = guild.get_member(user_id)
            if not member or not member.voice or not member.voice.channel:
                self._voice_sessions.pop((guild_id, user_id), None)
                continue

            guild_config = await xp_engine.get_guild_config(guild_id)
            if not guild_config["enabled"] or not guild_config["voice_enabled"]:
                continue

            voice_state = member.voice
            if guild_config["voice_require_unmuted"] and (voice_state.mute or voice_state.deaf or voice_state.self_mute or voice_state.self_deaf):
                continue
            if guild_config["voice_require_others"]:
                other_humans = [m for m in voice_state.channel.members if not m.bot and m.id != member.id]
                if not other_humans:
                    continue

            if await xp_engine.is_no_xp_channel(guild_id, voice_state.channel.id):
                continue
            if await xp_engine.has_no_xp_role(guild_id, member):
                continue

            result = await xp_engine.add_xp(guild_id, user_id, guild_config["voice_xp_per_minute"], member, voice_state.channel.id)
            await db.raw_execute(
                "UPDATE member_xp SET total_voice_minutes = total_voice_minutes + 1 WHERE guild_id=? AND user_id=?",
                (guild_id, user_id),
            )

            if result["leveled_up"]:
                await xp_engine.apply_role_rewards(guild, member, result["new_level"], guild_config["role_stack_mode"])
                await self._announce_level_up(guild, member, result, guild_config)

    @voice_xp_loop.before_loop
    async def _before_voice_xp_loop(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=1)
    async def period_reset_loop(self):
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)

        configs = await db.raw_fetch("SELECT guild_id, weekly_reset_enabled, monthly_reset_enabled FROM guild_leveling_config")
        for cfg in configs:
            if cfg["weekly_reset_enabled"] and now.weekday() == 0 and now.hour == 0:
                state = await db.raw_fetchone(
                    "SELECT period_start FROM leveling_period_state WHERE guild_id=? AND period='weekly'", (cfg["guild_id"],)
                )
                if not state or time.time() - state["period_start"] > 86400 * 6:
                    await xp_engine.reset_period(cfg["guild_id"], "weekly")

            if cfg["monthly_reset_enabled"] and now.day == 1 and now.hour == 0:
                state = await db.raw_fetchone(
                    "SELECT period_start FROM leveling_period_state WHERE guild_id=? AND period='monthly'", (cfg["guild_id"],)
                )
                if not state or time.time() - state["period_start"] > 86400 * 27:
                    await xp_engine.reset_period(cfg["guild_id"], "monthly")

    @period_reset_loop.before_loop
    async def _before_period_reset_loop(self):
        await self.bot.wait_until_ready()

    @commands.command(name="rank", aliases=["level", "lvl"], help="View a member's XP rank and level.")
    @commands.guild_only()
    async def rank(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        e = emoji_manager.get
        member = member or ctx.author
        guild_config = await xp_engine.get_guild_config(ctx.guild.id)
        if not guild_config["enabled"]:
            return await ctx.send(view=error_layout("Leveling Disabled", "Leveling is not enabled in this server."))

        row = await db.raw_fetchone("SELECT * FROM member_xp WHERE guild_id=? AND user_id=?", (ctx.guild.id, member.id))
        if not row:
            return await ctx.send(view=info_layout(f"{e('xp')} No Data", f"{member.mention} hasn't earned any XP yet."))

        rank_row = await db.raw_fetchone(
            "SELECT COUNT(*) + 1 as rank FROM member_xp WHERE guild_id=? AND xp > ?", (ctx.guild.id, row["xp"])
        )
        rank_position = rank_row["rank"] if rank_row else 1

        card = await self._generate_rank_card(member, dict(row), rank_position)
        await ctx.send(file=card)

    @commands.command(name="leaderboard", aliases=["lb", "top"], help="View the XP leaderboard for this server.")
    @commands.guild_only()
    async def leaderboard(self, ctx: commands.Context, period: str = "alltime"):
        e = emoji_manager.get
        period = period.lower()
        if period not in ("alltime", "weekly", "monthly"):
            return await ctx.send(view=error_layout("Invalid Period", "Use `alltime`, `weekly`, or `monthly`."))

        guild_config = await xp_engine.get_guild_config(ctx.guild.id)
        if not guild_config["enabled"]:
            return await ctx.send(view=error_layout("Leveling Disabled", "Leveling is not enabled in this server."))

        entries = await xp_engine.get_leaderboard(ctx.guild.id, period, limit=10)
        if not entries:
            return await ctx.send(view=info_layout(f"{e('leaderboard')} Leaderboard", "No XP data yet for this period."))

        lines = []
        for i, entry in enumerate(entries, 1):
            member = ctx.guild.get_member(entry["user_id"])
            name = member.mention if member else f"<@{entry['user_id']}>"
            level_text = f" (Level {entry['level']})" if "level" in entry else ""
            lines.append(f"`{i}.` {name} — **{entry['xp']:,} XP**{level_text}")

        await ctx.send(view=info_layout(f"{e('leaderboard')} {PERIOD_LABELS[period]} Leaderboard", "\n".join(lines)))

    @commands.group(name="leveling", aliases=["lvlconfig"], invoke_without_command=True, help="View or configure the XP leveling system.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def leveling_group(self, ctx: commands.Context):
        e = emoji_manager.get
        cfg = await xp_engine.get_guild_config(ctx.guild.id)
        body = (
            f"**Status:** {'🟢 Enabled' if cfg['enabled'] else '🔴 Disabled'}\n"
            f"**Text XP:** {cfg['xp_min']}–{cfg['xp_max']} per message · `{cfg['text_cooldown_seconds']}s` cooldown\n"
            f"**Voice XP:** {'Enabled' if cfg['voice_enabled'] else 'Disabled'} · `{cfg['voice_xp_per_minute']}`/min\n"
            f"**Role reward mode:** `{cfg['role_stack_mode']}`\n"
            f"**Announce mode:** `{cfg['announce_mode']}`\n"
            f"**Weekly reset:** {'On' if cfg['weekly_reset_enabled'] else 'Off'} · **Monthly reset:** {'On' if cfg['monthly_reset_enabled'] else 'Off'}\n\n"
            "-# Subcommands: `enable` `disable` `channel` `setxp` `resetxp` `levelrole` `multiplier` `noxp` `announce`"
        )
        await ctx.send(view=info_layout(f"{e('settings')} Leveling Configuration", body))

    @leveling_group.command(name="enable", help="Enable the XP leveling system.")
    @has_guild_permission("manage_guild")
    async def lvl_enable(self, ctx: commands.Context):
        e = emoji_manager.get
        await db.raw_execute(
            "INSERT INTO guild_leveling_config (guild_id, enabled) VALUES (?, 1)"
            " ON CONFLICT(guild_id) DO UPDATE SET enabled=1",
            (ctx.guild.id,),
        )
        await ctx.send(view=success_layout(f"{e('check')} Leveling Enabled", "Members will now earn XP from messages and voice activity."))

    @leveling_group.command(name="disable", help="Disable the XP leveling system.")
    @has_guild_permission("manage_guild")
    async def lvl_disable(self, ctx: commands.Context):
        e = emoji_manager.get
        await db.raw_execute(
            "INSERT INTO guild_leveling_config (guild_id, enabled) VALUES (?, 0)"
            " ON CONFLICT(guild_id) DO UPDATE SET enabled=0",
            (ctx.guild.id,),
        )
        await ctx.send(view=success_layout(f"{e('check')} Leveling Disabled", "XP tracking has been paused."))

    @leveling_group.command(name="channel", help="Set the channel for level-up announcements.")
    @has_guild_permission("manage_guild")
    async def lvl_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        e = emoji_manager.get
        await db.raw_execute(
            "INSERT INTO guild_leveling_config (guild_id, announce_mode, announce_channel_id) VALUES (?, 'channel', ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET announce_mode='channel', announce_channel_id=excluded.announce_channel_id",
            (ctx.guild.id, channel.id),
        )
        await ctx.send(view=success_layout(f"{e('check')} Announce Channel Set", f"Level-ups will be announced in {channel.mention}."))

    @leveling_group.command(name="announce", help="Set announcement mode: channel, dm, or off.")
    @has_guild_permission("manage_guild")
    async def lvl_announce(self, ctx: commands.Context, mode: str):
        e = emoji_manager.get
        mode = mode.lower()
        if mode not in ("channel", "dm", "off"):
            return await ctx.send(view=error_layout("Invalid Mode", "Use `channel`, `dm`, or `off`."))
        await db.raw_execute(
            "INSERT INTO guild_leveling_config (guild_id, announce_mode) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET announce_mode=excluded.announce_mode",
            (ctx.guild.id, mode),
        )
        await ctx.send(view=success_layout(f"{e('check')} Announce Mode Set", f"Level-up announcements set to `{mode}`."))

    @leveling_group.command(name="message", help="Set a custom level-up message using template variables.")
    @has_guild_permission("manage_guild")
    async def lvl_message(self, ctx: commands.Context, *, message: str):
        e = emoji_manager.get
        await db.raw_execute(
            "INSERT INTO guild_leveling_config (guild_id, announce_message) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET announce_message=excluded.announce_message",
            (ctx.guild.id, message),
        )
        preview_vars = {k: f"[{k}]" for k in LEVELING_VARIABLE_DOCS}
        preview_vars.update({k: f"[{k}]" for k in message_vars.DEFAULT_VARIABLE_DOCS})
        preview = message_vars.substitute(message, preview_vars)
        await ctx.send(view=success_layout(f"{e('check')} Message Updated", f"**Preview:**\n{preview}"))

    @leveling_group.command(name="variables", aliases=["vars"], help="Show all available level-up message variables.")
    async def lvl_variables(self, ctx: commands.Context):
        e = emoji_manager.get
        body = message_vars.variables_doc_block(LEVELING_VARIABLE_DOCS)
        await ctx.send(view=info_layout(f"{e('info')} Level-Up Variables", body))

    @leveling_group.command(name="setxp", help="Set a member's XP amount directly.")
    @has_guild_permission("manage_guild")
    async def lvl_setxp(self, ctx: commands.Context, member: discord.Member, amount: int):
        e = emoji_manager.get
        amount = max(0, amount)
        level = xp_engine.level_from_xp(amount)
        await db.raw_execute(
            "INSERT INTO member_xp (guild_id, user_id, xp, level) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=excluded.xp, level=excluded.level",
            (ctx.guild.id, member.id, amount, level),
        )
        await ctx.send(view=success_layout(f"{e('check')} XP Set", f"{member.mention} is now at **{amount:,} XP** (Level {level})."))

    @leveling_group.command(name="resetxp", help="Reset a member's XP to zero.")
    @has_guild_permission("manage_guild")
    async def lvl_resetxp(self, ctx: commands.Context, member: discord.Member):
        e = emoji_manager.get
        await db.raw_execute(
            "INSERT INTO member_xp (guild_id, user_id, xp, level) VALUES (?, ?, 0, 0)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET xp=0, level=0",
            (ctx.guild.id, member.id),
        )
        await ctx.send(view=success_layout(f"{e('check')} XP Reset", f"{member.mention}'s XP has been reset to 0."))

    @leveling_group.command(name="levelrole", help="Award a role when a member reaches a specific level.")
    @has_guild_permission("manage_guild")
    async def lvl_levelrole(self, ctx: commands.Context, level: int, role: discord.Role):
        e = emoji_manager.get
        await db.raw_execute(
            "INSERT OR IGNORE INTO level_role_rewards (guild_id, level, role_id) VALUES (?, ?, ?)",
            (ctx.guild.id, level, role.id),
        )
        await ctx.send(view=success_layout(f"{e('check')} Role Reward Set", f"{role.mention} will be awarded at **level {level}**."))

    @leveling_group.command(name="removelevelrole", help="Remove a role reward for a level.")
    @has_guild_permission("manage_guild")
    async def lvl_removelevelrole(self, ctx: commands.Context, level: int, role: discord.Role):
        e = emoji_manager.get
        cur = await db.raw_execute(
            "DELETE FROM level_role_rewards WHERE guild_id=? AND level=? AND role_id=?", (ctx.guild.id, level, role.id)
        )
        if cur.rowcount:
            await ctx.send(view=success_layout(f"{e('check')} Removed", f"Removed {role.mention} from level {level} rewards."))
        else:
            await ctx.send(view=error_layout("Not Found", "No matching role reward found."))

    @leveling_group.command(name="rolestack", help="Set role reward mode: stack or nonstack.")
    @has_guild_permission("manage_guild")
    async def lvl_rolestack(self, ctx: commands.Context, mode: str):
        e = emoji_manager.get
        mode = mode.lower()
        if mode not in ("stack", "nonstack"):
            return await ctx.send(view=error_layout("Invalid Mode", "Use `stack` or `nonstack`."))
        await db.raw_execute(
            "INSERT INTO guild_leveling_config (guild_id, role_stack_mode) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET role_stack_mode=excluded.role_stack_mode",
            (ctx.guild.id, mode),
        )
        await ctx.send(view=success_layout(f"{e('check')} Role Stack Mode Set", f"Role rewards will now use `{mode}` mode."))

    @leveling_group.command(name="levelroles", help="List all configured level role rewards.")
    async def lvl_levelroles(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await db.raw_fetch("SELECT level, role_id FROM level_role_rewards WHERE guild_id=? ORDER BY level ASC", (ctx.guild.id,))
        if not rows:
            return await ctx.send(view=info_layout(f"{e('trophy')} Role Rewards", "No role rewards configured."))
        lines = [f"**Level {r['level']}** → <@&{r['role_id']}>" for r in rows]
        await ctx.send(view=info_layout(f"{e('trophy')} Role Rewards", "\n".join(lines)))

    @leveling_group.group(name="multiplier", aliases=["mult"], invoke_without_command=True, help="Manage XP multipliers.")
    @has_guild_permission("manage_guild")
    async def lvl_multiplier(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await db.raw_fetch("SELECT * FROM xp_multipliers WHERE guild_id=?", (ctx.guild.id,))
        if not rows:
            return await ctx.send(view=info_layout(
                f"{e('xp')} XP Multipliers",
                "No multipliers configured.\nUse `leveling multiplier add <global|channel|role> <target> <value>`.",
            ))
        lines = []
        for r in rows:
            target = "Server-wide" if r["scope_type"] == "global" else (
                f"<#{r['scope_id']}>" if r["scope_type"] == "channel" else f"<@&{r['scope_id']}>"
            )
            lines.append(f"`{r['multiplier_id']}` **{r['scope_type'].title()}** — {target} → `{r['multiplier']}x`")
        await ctx.send(view=info_layout(f"{e('xp')} XP Multipliers", "\n".join(lines)))

    @lvl_multiplier.command(name="add", help="Add an XP multiplier. Usage: leveling multiplier add <global|channel|role> <target> <value>")
    @has_guild_permission("manage_guild")
    async def lvl_multiplier_add(self, ctx: commands.Context, scope: str, target: Optional[str], value: float):
        e = emoji_manager.get
        scope = scope.lower()
        if scope not in (xp_engine.SCOPE_GLOBAL, xp_engine.SCOPE_CHANNEL, xp_engine.SCOPE_ROLE):
            return await ctx.send(view=error_layout("Invalid Scope", "Use `global`, `channel`, or `role`."))
        if value <= 0:
            return await ctx.send(view=error_layout("Invalid Value", "Multiplier must be greater than 0."))

        scope_id = None
        if scope == xp_engine.SCOPE_CHANNEL:
            channel = await commands.TextChannelConverter().convert(ctx, target) if target else None
            if not channel:
                return await ctx.send(view=error_layout("Missing Target", "Provide a channel for the `channel` scope."))
            scope_id = channel.id
        elif scope == xp_engine.SCOPE_ROLE:
            role = await commands.RoleConverter().convert(ctx, target) if target else None
            if not role:
                return await ctx.send(view=error_layout("Missing Target", "Provide a role for the `role` scope."))
            scope_id = role.id

        multiplier_id = xp_engine.new_multiplier_id()
        await db.raw_execute(
            "INSERT INTO xp_multipliers (multiplier_id, guild_id, scope_type, scope_id, multiplier) VALUES (?, ?, ?, ?, ?)",
            (multiplier_id, ctx.guild.id, scope, scope_id, value),
        )
        await ctx.send(view=success_layout(f"{e('check')} Multiplier Added", f"`{multiplier_id}` — **{scope}** scope at `{value}x`."))

    @lvl_multiplier.command(name="remove", help="Remove an XP multiplier by ID.")
    @has_guild_permission("manage_guild")
    async def lvl_multiplier_remove(self, ctx: commands.Context, multiplier_id: str):
        e = emoji_manager.get
        cur = await db.raw_execute(
            "DELETE FROM xp_multipliers WHERE multiplier_id=? AND guild_id=?", (multiplier_id.upper(), ctx.guild.id)
        )
        if cur.rowcount:
            await ctx.send(view=success_layout(f"{e('check')} Removed", f"Multiplier `{multiplier_id.upper()}` removed."))
        else:
            await ctx.send(view=error_layout("Not Found", f"No multiplier with ID `{multiplier_id.upper()}`."))

    @leveling_group.group(name="noxp", invoke_without_command=True, help="Manage no-XP channels and roles.")
    @has_guild_permission("manage_guild")
    async def lvl_noxp(self, ctx: commands.Context):
        e = emoji_manager.get
        channels = await db.raw_fetch("SELECT channel_id FROM xp_no_xp_channels WHERE guild_id=?", (ctx.guild.id,))
        roles = await db.raw_fetch("SELECT role_id FROM xp_no_xp_roles WHERE guild_id=?", (ctx.guild.id,))
        channel_mentions = ", ".join(f"<#{c['channel_id']}>" for c in channels) or "None"
        role_mentions = ", ".join(f"<@&{r['role_id']}>" for r in roles) or "None"
        body = f"**No-XP channels:** {channel_mentions}\n**No-XP roles:** {role_mentions}"
        await ctx.send(view=info_layout(f"{e('info')} No-XP Settings", body))

    @lvl_noxp.command(name="channel", help="Toggle a channel as no-XP.")
    @has_guild_permission("manage_guild")
    async def lvl_noxp_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        e = emoji_manager.get
        existing = await db.raw_fetchone(
            "SELECT 1 FROM xp_no_xp_channels WHERE guild_id=? AND channel_id=?", (ctx.guild.id, channel.id)
        )
        if existing:
            await db.raw_execute("DELETE FROM xp_no_xp_channels WHERE guild_id=? AND channel_id=?", (ctx.guild.id, channel.id))
            await ctx.send(view=success_layout(f"{e('check')} Removed", f"{channel.mention} now earns XP again."))
        else:
            await db.raw_execute("INSERT INTO xp_no_xp_channels (guild_id, channel_id) VALUES (?, ?)", (ctx.guild.id, channel.id))
            await ctx.send(view=success_layout(f"{e('check')} Added", f"{channel.mention} no longer earns XP."))

    @lvl_noxp.command(name="role", help="Toggle a role as no-XP.")
    @has_guild_permission("manage_guild")
    async def lvl_noxp_role(self, ctx: commands.Context, role: discord.Role):
        e = emoji_manager.get
        existing = await db.raw_fetchone(
            "SELECT 1 FROM xp_no_xp_roles WHERE guild_id=? AND role_id=?", (ctx.guild.id, role.id)
        )
        if existing:
            await db.raw_execute("DELETE FROM xp_no_xp_roles WHERE guild_id=? AND role_id=?", (ctx.guild.id, role.id))
            await ctx.send(view=success_layout(f"{e('check')} Removed", f"Members with {role.mention} now earn XP again."))
        else:
            await db.raw_execute("INSERT INTO xp_no_xp_roles (guild_id, role_id) VALUES (?, ?)", (ctx.guild.id, role.id))
            await ctx.send(view=success_layout(f"{e('check')} Added", f"Members with {role.mention} no longer earn XP."))

    @leveling_group.command(name="weeklyreset", help="Toggle automatic weekly leaderboard resets.")
    @has_guild_permission("manage_guild")
    async def lvl_weeklyreset(self, ctx: commands.Context):
        e = emoji_manager.get
        cfg = await xp_engine.get_guild_config(ctx.guild.id)
        new_value = 0 if cfg["weekly_reset_enabled"] else 1
        await db.raw_execute(
            "INSERT INTO guild_leveling_config (guild_id, weekly_reset_enabled) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET weekly_reset_enabled=excluded.weekly_reset_enabled",
            (ctx.guild.id, new_value),
        )
        state = "enabled" if new_value else "disabled"
        await ctx.send(view=success_layout(f"{e('check')} Weekly Reset {state.title()}", f"Automatic weekly leaderboard resets are now {state}."))

    @leveling_group.command(name="monthlyreset", help="Toggle automatic monthly leaderboard resets.")
    @has_guild_permission("manage_guild")
    async def lvl_monthlyreset(self, ctx: commands.Context):
        e = emoji_manager.get
        cfg = await xp_engine.get_guild_config(ctx.guild.id)
        new_value = 0 if cfg["monthly_reset_enabled"] else 1
        await db.raw_execute(
            "INSERT INTO guild_leveling_config (guild_id, monthly_reset_enabled) VALUES (?, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET monthly_reset_enabled=excluded.monthly_reset_enabled",
            (ctx.guild.id, new_value),
        )
        state = "enabled" if new_value else "disabled"
        await ctx.send(view=success_layout(f"{e('check')} Monthly Reset {state.title()}", f"Automatic monthly leaderboard resets are now {state}."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Leveling(bot))
