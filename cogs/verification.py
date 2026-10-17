import datetime
import io
import secrets
import string
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import db, embed_templates, emoji_manager, guild_settings, incident, message_vars, security
from utils import security_cmds, threat
from utils import security_settings as settings
from utils.checks import has_guild_permission
from utils.security_access import security_owner, security_staff
from utils.events_bus import (
    ANTINUKE_INCIDENT,
    INCIDENT_STATE_CHANGED,
    MEMBER_JOINED_UNVERIFIED,
    MEMBER_VERIFIED,
    VERIFICATION_FAILED,
    VERIFICATION_SUCCESS,
    LOG_EVENT,
    bus,
)
import config

_attempts: dict[tuple[int, int], dict] = {}
_clicks: dict[tuple[int, int], float] = {}

def _lock_remaining(guild_id: int, user_id: int) -> int:
    data = _attempts.get((guild_id, user_id))
    if not data:
        return 0
    return max(0, int(data["locked_until"] - time.time()))


async def _apply_fail_action(guild: discord.Guild, member: discord.abc.User):
    target = guild.get_member(member.id)
    if target is None:
        return
    action = await settings.get(guild.id, "verification", "fail_action")
    reason = "Verification: repeated failed attempts"
    try:
        if action == "ban":
            await guild.ban(target, reason=reason, delete_message_days=0)
        elif action == "kick":
            await target.kick(reason=reason)
        elif action == "timeout":
            until = discord.utils.utcnow() + datetime.timedelta(seconds=config.QUARANTINE_TIMEOUT_SECONDS)
            await target.timeout(until, reason=reason)
        elif action == "quarantine":
            await security.quarantine_member(guild, target, reason, track_escalation=False)
    except discord.HTTPException:
        pass


async def _register_failure(guild: discord.Guild, member: discord.abc.User) -> tuple[int, int]:
    limit = int(await settings.get(guild.id, "verification", "max_attempts"))
    key = (guild.id, member.id)
    data = _attempts.setdefault(key, {"count": 0, "locked_until": 0.0, "lockouts": 0})
    data["count"] += 1
    locked = False
    if data["count"] >= limit:
        data["count"] = 0
        data["lockouts"] += 1
        data["locked_until"] = time.time() + int(await settings.get(guild.id, "verification", "lockout_seconds"))
        locked = True
        await threat.add(guild.id, "verify_lockout", str(member.id))
    await bus.publish(VERIFICATION_FAILED, guild_id=guild.id, user_id=member.id)
    if await settings.get(guild.id, "verification", "log_attempts"):
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="verification_action", user_id=member.id, detail="wrong captcha code")
    fail_after = int(await settings.get(guild.id, "verification", "fail_lockouts"))
    if locked and fail_after and data["lockouts"] >= fail_after:
        _attempts.pop(key, None)
        await _apply_fail_action(guild, member)
    return data["count"], limit


def _notice(title: str, body: str, color: int) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
    view.add_item(container)
    return view

def _make_captcha_image(code: str) -> Optional[discord.File]:
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        import random as rng

        W, H = 280, 90
        img = Image.new("RGB", (W, H), color=(30, 30, 35))
        draw = ImageDraw.Draw(img)

        for _ in range(8):
            x1, y1 = rng.randint(0, W), rng.randint(0, H)
            x2, y2 = rng.randint(0, W), rng.randint(0, H)
            draw.line([(x1, y1), (x2, y2)], fill=(rng.randint(60, 120), rng.randint(60, 120), rng.randint(80, 140)), width=1)

        for _ in range(200):
            x, y = rng.randint(0, W), rng.randint(0, H)
            draw.point((x, y), fill=(rng.randint(60, 100), rng.randint(60, 100), rng.randint(80, 120)))

        char_colors = [
            (255, 255, 255), (200, 220, 255), (180, 255, 200),
            (255, 220, 180), (220, 180, 255), (255, 180, 180),
        ]

        font = None
        font_candidates = [
            "/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/data/data/com.termux/files/usr/share/fonts/truetype/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/system/fonts/DroidSans-Bold.ttf",
            "/system/fonts/DroidSans.ttf",
            "/Library/Fonts/Arial Bold.ttf",
            "/Library/Fonts/Arial.ttf",
        ]
        for path in font_candidates:
            try:
                font = ImageFont.truetype(path, 42)
                break
            except (IOError, OSError):
                continue
        if font is None:
            font = ImageFont.load_default()

        x = 18
        for i, ch in enumerate(code):
            color = char_colors[i % len(char_colors)]
            y_offset = rng.randint(-6, 6)
            draw.text((x, 18 + y_offset), ch, fill=color, font=font)
            x += 40

        img = img.filter(ImageFilter.SMOOTH)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return discord.File(buf, filename="captcha.png")

    except Exception:
        return None

async def _complete_verification(guild: discord.Guild, member: discord.Member) -> bool:
    if await security.is_quarantined(guild.id, member.id):
        return False

    _attempts.pop((guild.id, member.id), None)
    await bus.publish(MEMBER_VERIFIED, guild_id=guild.id, user_id=member.id)
    await bus.publish(VERIFICATION_SUCCESS, guild_id=guild.id, user_id=member.id)
    await bus.publish(
        LOG_EVENT,
        guild_id=guild.id,
        action="verification_action",
        user_id=member.id,
        detail="verified",
    )

    verified_role_id = await guild_settings.get(guild.id, "verification_role_id")
    if verified_role_id:
        role = guild.get_role(int(verified_role_id))
        if role and not role.managed and role < guild.me.top_role:
            try:
                await member.add_roles(role, reason="Soward: verification passed")
            except discord.HTTPException:
                pass

    gate_role_id = await guild_settings.get(guild.id, "verification_gate_role_id")
    if gate_role_id:
        role = guild.get_role(int(gate_role_id))
        if role and role in member.roles:
            try:
                await member.remove_roles(role, reason="Soward: verification passed")
            except discord.HTTPException:
                pass
    return True


class CaptchaCodeModal(discord.ui.Modal, title="Enter captcha code"):
    code_input = discord.ui.TextInput(
        label="Code",
        placeholder="Type the code exactly as shown",
        min_length=4,
        max_length=8,
    )

    def __init__(self, correct: str, issued_at: float, lifetime: int):
        super().__init__()
        self.correct = correct.upper()
        self.issued_at = issued_at
        self.lifetime = lifetime
        self.code_input.min_length = len(correct)
        self.code_input.max_length = len(correct)

    async def on_submit(self, interaction: discord.Interaction):
        e = emoji_manager.get
        guild = interaction.guild
        if guild is None or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("This only works inside a server.", ephemeral=True)

        wait = _lock_remaining(guild.id, interaction.user.id)
        if wait:
            return await interaction.response.send_message(
                view=_notice(f"{e('cross')} Too many attempts", f"Try again in **{wait}s**.", 0xED4245), ephemeral=True,
            )

        if time.time() - self.issued_at > self.lifetime:
            return await interaction.response.send_message(
                view=_notice(f"{e('cross')} Code expired", "Click **Verify** on the panel again for a new code.", 0xED4245), ephemeral=True,
            )

        if not secrets.compare_digest(self.code_input.value.strip().upper(), self.correct):
            used, limit = await _register_failure(guild, interaction.user)
            wait = _lock_remaining(guild.id, interaction.user.id)
            body = (
                f"Too many wrong codes. Try again in **{wait}s**." if wait
                else f"That code is incorrect ({used}/{limit} attempts). Click **Verify** on the panel again for a new code."
            )
            return await interaction.response.send_message(view=_notice(f"{e('cross')} Wrong code", body, 0xED4245), ephemeral=True)

        if not await _complete_verification(guild, interaction.user):
            return await interaction.response.send_message(
                view=_notice(f"{e('cross')} Not available", "You cannot verify right now. Contact a staff member.", 0xED4245), ephemeral=True,
            )
        await interaction.response.send_message(
            view=_notice(f"{e('check')} Verified!", f"You now have access to **{guild.name}**. Welcome!", 0x57F287), ephemeral=True,
        )

class CaptchaChallengeRow(discord.ui.ActionRow):
    def __init__(self, code: str, layout: "CaptchaChallengeLayout"):
        super().__init__()
        self.code = code
        self.issued_at = time.time()
        self.layout_ref = layout

    @discord.ui.button(label="Enter code", style=discord.ButtonStyle.primary, custom_id="verification:enter_code")
    async def enter_code_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        lifetime = int(await settings.get(interaction.guild.id, "verification", "captcha_lifetime")) if interaction.guild else 180
        await interaction.response.send_modal(CaptchaCodeModal(self.code, self.issued_at, lifetime))

class CaptchaChallengeLayout(discord.ui.LayoutView):

    def __init__(self, code: str):
        super().__init__(timeout=120)
        self.code = code
        e = emoji_manager.get

        self.container = discord.ui.Container(accent_color=0x2B2D31)
        self.container.add_item(discord.ui.TextDisplay(
            f"## {e('verification_cat')} Captcha verification\n"
            "Type the code shown in the image below, then click **Enter code**.\n"
            "The code is case-insensitive."
        ))
        self.container.add_item(discord.ui.Separator())

        self.container.add_item(discord.ui.MediaGallery(
            discord.MediaGalleryItem("attachment://captcha.png")
        ))
        self.container.add_item(discord.ui.Separator())
        self.btn_row = CaptchaChallengeRow(code, self)
        self.container.add_item(self.btn_row)
        self.add_item(self.container)

async def _handle_verify_click(interaction: discord.Interaction):
    e = emoji_manager.get
    guild = interaction.guild
    member = interaction.user
    if guild is None or not isinstance(member, discord.Member):
        return await interaction.response.send_message("This only works inside a server.", ephemeral=True)

    async def reply(title: str, body: str, color: int):
        await interaction.response.send_message(view=_notice(title, body, color), ephemeral=True)

    now = time.time()
    if now - _clicks.get((guild.id, member.id), 0) < int(await settings.get(guild.id, "verification", "click_cooldown")):
        return await reply(f"{e('cross')} Slow down", "Wait a few seconds before trying again.", 0xED4245)
    _clicks[(guild.id, member.id)] = now
    if len(_clicks) > 5000:
        for key in [k for k, v in _clicks.items() if now - v > 300]:
            del _clicks[key]

    if await security.is_quarantined(guild.id, member.id):
        return await reply(f"{e('quarantine')} Not available", "Your account is under review. Contact a staff member.", 0xED4245)

    wait = _lock_remaining(guild.id, member.id)
    if wait:
        return await reply(f"{e('cross')} Too many attempts", f"Try again in **{wait}s**.", 0xED4245)

    current_state = await incident.get_state(guild.id)
    if current_state >= config.INCIDENT_STATES["lockdown"]:
        return await reply(
            f"{e('lockdown')} Server locked",
            "This server is in lockdown. Please wait for a staff member to manually approve your access.",
            0xED4245,
        )

    verified_role_id = await guild_settings.get(guild.id, "verification_role_id")
    if verified_role_id:
        role = guild.get_role(int(verified_role_id))
        if role and role in member.roles:
            return await reply(f"{e('check')} Already verified", f"You already have access to **{guild.name}**.", 0x57F287)

    min_age_hours = await guild_settings.get(guild.id, "verification_min_account_age_hours", 0)
    if min_age_hours:
        age_seconds = now - member.created_at.timestamp()
        if age_seconds < min_age_hours * 3600:
            remaining = int((min_age_hours * 3600 - age_seconds) // 3600) + 1
            return await reply(
                f"{e('cross')} Account too new",
                f"Accounts must be at least **{min_age_hours}h** old to verify here. Try again in about **{remaining}h**.",
                0xED4245,
            )

    level = await guild_settings.get(guild.id, "verification_level", config.VERIFICATION_LEVELS["none"])

    if level == config.VERIFICATION_LEVELS["captcha"]:
        length = int(await settings.get(guild.id, "verification", "captcha_length"))
        code = "".join(secrets.choice(string.ascii_uppercase.replace("O", "").replace("I", "") + string.digits.replace("0", "").replace("1", "")) for _ in range(length))
        captcha_file = _make_captcha_image(code)
        if captcha_file is None:
            return await reply(f"{e('cross')} Captcha unavailable", "The captcha could not be generated. Ask a staff member to approve you.", 0xED4245)
        challenge = CaptchaChallengeLayout(code)
        return await interaction.response.send_message(view=challenge, files=[captcha_file], ephemeral=True)

    if level == config.VERIFICATION_LEVELS["manual"]:
        await reply(f"{e('info')} Manual review", "Your verification request has been noted. A staff member will review and grant you access shortly.", 0x2B2D31)
        await bus.publish(
            LOG_EVENT,
            guild_id=guild.id,
            action="verification_action",
            user_id=member.id,
            detail="manual verification requested",
        )
        return

    if not await _complete_verification(guild, member):
        return await reply(f"{e('cross')} Not available", "You cannot verify right now. Contact a staff member.", 0xED4245)
    await reply(f"{e('check')} Verified!", f"You now have access to **{guild.name}**. Welcome!", 0x57F287)

class VerifyPanelRow(discord.ui.ActionRow):

    def __init__(self):
        super().__init__()

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        custom_id="verification:panel_verify",
        emoji="✅",
    )
    async def verify_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_verify_click(interaction)

class VerificationPanelClassicView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Verify",
        style=discord.ButtonStyle.success,
        custom_id="verification:panel_verify_embed",
        emoji="✅",
    )
    async def verify_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_verify_click(interaction)

class VerificationPanelLayout(discord.ui.LayoutView):

    def __init__(self, guild_name: str = "", custom_text: str = None):
        super().__init__(timeout=None)
        e = emoji_manager.get
        container = discord.ui.Container(accent_color=0x2B2D31)
        if custom_text:
            container.add_item(discord.ui.TextDisplay(custom_text))
            container.add_item(discord.ui.Separator())
        elif guild_name:
            container.add_item(discord.ui.TextDisplay(
                f"## {e('verification_cat')} Verification — {guild_name}\n"
                "Click **Verify** below to gain access to this server.\n\n"
                "By verifying you agree to follow the server rules."
            ))
            container.add_item(discord.ui.Separator())
        container.add_item(VerifyPanelRow())
        self.add_item(container)


class Verification(commands.Cog):
    category = "Config"
    submodule = "Security"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bus.subscribe(ANTINUKE_INCIDENT, self._on_antinuke_incident)
        bus.subscribe(INCIDENT_STATE_CHANGED, self._on_incident_state_changed)
        bus.subscribe(MEMBER_VERIFIED, self._on_member_verified_cleanup)

        bot.add_view(VerificationPanelLayout())
        bot.add_view(VerificationPanelClassicView())
        self.pending_timeout_checker.start()

    def cog_unload(self):
        self.pending_timeout_checker.cancel()

    async def _on_member_verified_cleanup(self, *, guild_id: int, user_id: int, **_):
        await db.raw_execute(
            "DELETE FROM pending_verification WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )

    @tasks.loop(minutes=2)
    async def pending_timeout_checker(self):
        rows = await db.raw_fetch("SELECT DISTINCT guild_id FROM pending_verification")
        for row in rows:
            guild_id = row["guild_id"]
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            enabled = await guild_settings.get(guild_id, "verification_pending_timeout_enabled", config.VERIFICATION_PENDING_TIMEOUT_ENABLED_DEFAULT)
            if not enabled:
                continue

            timeout_minutes = await guild_settings.get(guild_id, "verification_pending_timeout_minutes", config.VERIFICATION_PENDING_TIMEOUT_MINUTES_DEFAULT)
            action = await guild_settings.get(guild_id, "verification_pending_timeout_action", config.VERIFICATION_PENDING_TIMEOUT_ACTION_DEFAULT)
            cutoff = time.time() - (timeout_minutes * 60)

            overdue = await db.raw_fetch(
                "SELECT user_id FROM pending_verification WHERE guild_id=? AND joined_at<=?", (guild_id, cutoff)
            )
            for overdue_row in overdue:
                member = guild.get_member(overdue_row["user_id"])
                await db.raw_execute(
                    "DELETE FROM pending_verification WHERE guild_id=? AND user_id=?",
                    (guild_id, overdue_row["user_id"]),
                )
                if not member:
                    continue
                try:
                    if action == "kick":
                        await member.kick(reason=f"Verification: pending timeout exceeded ({timeout_minutes}m)")
                    elif action == "ban":
                        await guild.ban(member, reason=f"Verification: pending timeout exceeded ({timeout_minutes}m)")
                except discord.HTTPException:
                    pass
                await bus.publish(
                    LOG_EVENT, guild_id=guild_id, action="verification_action",
                    user_id=overdue_row["user_id"], detail=f"pending timeout exceeded, action={action}",
                )

    @pending_timeout_checker.before_loop
    async def _before_pending_timeout_checker(self):
        await self.bot.wait_until_ready()

    async def _on_antinuke_incident(self, *, guild_id: int, **kwargs):
        current = await incident.get_state(guild_id)
        if current < config.INCIDENT_STATES["lockdown"]:
            return
        level = await guild_settings.get(guild_id, "verification_level", config.VERIFICATION_LEVELS["none"])
        manual = config.VERIFICATION_LEVELS["manual"]
        if level != manual:
            await guild_settings.set(guild_id, "verification_level_base", level)
            await guild_settings.set(guild_id, "verification_level", manual)

    async def _on_incident_state_changed(self, *, guild_id: int, new_state: int, **kwargs):
        if new_state != config.INCIDENT_STATES["normal"]:
            return
        base = await guild_settings.get(guild_id, "verification_level_base")
        if base is not None:
            await guild_settings.set(guild_id, "verification_level", base)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        guild_id = member.guild.id
        level = await guild_settings.get(guild_id, "verification_level", config.VERIFICATION_LEVELS["none"])
        if level == config.VERIFICATION_LEVELS["none"]:
            return

        if await settings.get(guild_id, "verification", "target") == "suspicious":
            antiraid = self.bot.get_cog("AntiRaid")
            if antiraid is not None:
                needed = await settings.get(guild_id, "antiraid", "gate_suspicious_score")
                if antiraid._suspicion_points(member) < needed:
                    return

        await bus.publish(MEMBER_JOINED_UNVERIFIED, guild_id=guild_id, user_id=member.id)

        await db.raw_execute(
            "INSERT INTO pending_verification (guild_id, user_id, joined_at) VALUES (?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET joined_at=excluded.joined_at",
            (guild_id, member.id, time.time()),
        )

        gate_role_id = await guild_settings.get(guild_id, "verification_gate_role_id")
        if gate_role_id:
            role = member.guild.get_role(int(gate_role_id))
            if role:
                try:
                    await member.add_roles(role, reason="Soward: pending verification")
                except discord.HTTPException:
                    pass

    @commands.group(name="verification", aliases=["verify"], invoke_without_command=True, help='View or configure the member verification system.')
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def verification_group(self, ctx: commands.Context):
        from utils.security_panels import VerificationOverviewLayout
        view = await VerificationOverviewLayout.create(ctx.author.id, ctx.guild.id)
        await ctx.send(view=view)

    @verification_group.command(name="settings", aliases=["config", "options"], help="List every verification setting and its current value. Usage: settings [group|all]")
    @has_guild_permission("administrator")
    async def verification_cfg_settings(self, ctx: commands.Context, group: Optional[str] = None):
        await security_cmds.show_settings(ctx, "verification", group)

    @verification_group.command(name="get", help="Show one verification setting with its default. Usage: get <key>")
    @has_guild_permission("administrator")
    async def verification_cfg_get(self, ctx: commands.Context, key: str):
        await security_cmds.get_setting(ctx, "verification", key)

    @verification_group.command(name="set", help="Change a verification setting. Usage: set <key> <value>")
    @security_staff()
    async def verification_cfg_set(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.set_setting(ctx, "verification", key, value)

    @verification_group.command(name="reset", help="Reset one verification setting, or `all`, to its default. Usage: reset <key|all>")
    @security_owner()
    async def verification_cfg_reset(self, ctx: commands.Context, key: str):
        await security_cmds.reset_setting(ctx, "verification", key)

    @verification_group.command(name="add", help="Add an entry to a verification list setting. Usage: add <key> <value>")
    @security_staff()
    async def verification_cfg_add(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.list_edit(ctx, "verification", key, value, True)

    @verification_group.command(name="remove", help="Remove an entry from a verification list setting. Usage: remove <key> <value>")
    @security_staff()
    async def verification_cfg_remove(self, ctx: commands.Context, key: str, *, value: str):
        await security_cmds.list_edit(ctx, "verification", key, value, False)

    @verification_group.command(name="list", help="Show the entries of a verification list setting. Usage: list <key>")
    @has_guild_permission("administrator")
    async def verification_cfg_list(self, ctx: commands.Context, key: str):
        await security_cmds.show_list(ctx, "verification", key)

    @verification_group.command(name="setup", help="Post the one-time verification panel in a channel.")
    @security_staff()
    async def verification_setup(self, ctx: commands.Context, channel: discord.TextChannel):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get

        level = await guild_settings.get(ctx.guild.id, "verification_level", config.VERIFICATION_LEVELS["none"])
        if level == config.VERIFICATION_LEVELS["none"]:
            return await ctx.send(view=error_layout(
                f"{e('cross')} No verification type set",
                "Set a verification type first: `verification type <button|captcha|manual>`",
            ))

        embeds, text = await self._resolve_panel_content(ctx.guild, ctx.author)
        if embeds:
            msg = await channel.send(content=text, embeds=embeds, view=VerificationPanelClassicView())
        else:
            panel = VerificationPanelLayout(ctx.guild.name, custom_text=text)
            msg = await channel.send(view=panel)

        await guild_settings.set(ctx.guild.id, "verification_channel_id", channel.id)
        await guild_settings.set(ctx.guild.id, "verification_panel_message_id", msg.id)

        await ctx.send(view=success_layout(
            f"{e('check')} Verification panel posted",
            f"Panel sent to {channel.mention}. Members click Verify there to gain access.\n\n"
            f"Make sure **{channel.mention} is not visible** to your verified role — "
            "only unverified members should see it.",
        ))

    async def _resolve_panel_content(self, guild: discord.Guild, var_source: discord.abc.User) -> tuple[list, Optional[str]]:
        template_str = await guild_settings.get(guild.id, "verification_panel_message")
        if not template_str:
            return [], None

        var_map = message_vars.build_base_variables(var_source, guild)

        if embed_templates.has_embed_ref(template_str):
            remaining, embeds = await embed_templates.resolve_embed_refs(guild.id, template_str, var_map)
            return embeds, remaining

        return [], message_vars.substitute(template_str, var_map)

    @verification_group.command(name="type", help='Set the verification type: button, captcha, or manual.')
    @security_staff()
    async def verification_type(self, ctx: commands.Context, level: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        level = level.lower()
        if level not in config.VERIFICATION_LEVELS:
            return await ctx.send(view=error_layout(
                "Invalid type",
                f"Choose from: {', '.join(f'`{l}`' for l in config.VERIFICATION_LEVELS if l != 'none')}",
            ))
        lvl_int = config.VERIFICATION_LEVELS[level]
        await guild_settings.set(ctx.guild.id, "verification_level", lvl_int)
        await guild_settings.set(ctx.guild.id, "verification_level_base", lvl_int)

        descriptions = {
            "button": "One click — members click Verify and are immediately granted the role.",
            "captcha": "Members click Verify, receive an ephemeral captcha image, and must type the code to pass.",
            "manual": "Members click Verify to signal intent; staff must run `approve @member` to grant access.",
        }
        await ctx.send(view=success_layout(
            f"{e('check')} Verification type set to `{level}`",
            descriptions.get(level, ""),
        ))

    @verification_group.command(name="role", help='Set the role granted after passing verification.')
    @security_staff()
    async def verification_role(self, ctx: commands.Context, role: discord.Role):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "verification_role_id", role.id)
        await ctx.send(view=success_layout(
            f"{e('check')} Verified role set",
            f"Members receive {role.mention} after passing verification.",
        ))

    @verification_group.command(name="message", help="Set a custom verification panel message, or `none`/`reset`/`default` to revert to the default look. Supports {embed:name} to render a saved embed template as a real embed (footer/image included), plus {server}/{membercount}/{servericon} and other variables.")
    @security_staff()
    async def verification_message(self, ctx: commands.Context, *, message: str):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get

        if message.strip().lower() in ("none", "reset", "default", "clear", "off"):
            await guild_settings.set(ctx.guild.id, "verification_panel_message", None)
            return await ctx.send(view=success_layout(
                f"{e('check')} Reverted to default",
                "The verification panel will use the default look. Re-run `verification setup #channel` to repost it.",
            ))

        if embed_templates.has_embed_ref(message):
            for embed_name in embed_templates.EMBED_REF_PATTERN.findall(message):
                template = await embed_templates.get_template(ctx.guild.id, embed_name)
                if not template:
                    return await ctx.send(view=error_layout(
                        f"{e('cross')} Embed not found",
                        f"No embed template named `{embed_name}` exists. Create one first with `embed create {embed_name}`.",
                    ))

        await guild_settings.set(ctx.guild.id, "verification_panel_message", message)

        embeds, text = await self._resolve_panel_content(ctx.guild, ctx.author)
        if embeds:
            await ctx.send(content=text, embeds=embeds)
            await ctx.send(view=success_layout(
                f"{e('check')} Panel message updated",
                "Preview above — the panel will render as a real embed (footer/image included), not the usual layout.\n\n"
                "-# Re-run `verification setup #channel` to repost the panel with this message. "
                "Use `verification message none` any time to go back to the default look.",
            ))
        else:
            await ctx.send(view=success_layout(
                f"{e('check')} Panel message updated",
                f"Preview:\n\n{text}\n\n"
                "-# Re-run `verification setup #channel` to repost the panel with this message. "
                "Use `verification message none` any time to go back to the default look.",
            ))

    @verification_group.command(name="gaterole", help='Set the role held until a member is verified.')
    @security_staff()
    async def verification_gaterole(self, ctx: commands.Context, role: discord.Role):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "verification_gate_role_id", role.id)
        await ctx.send(view=success_layout(
            f"{e('check')} Gate role set",
            f"{role.mention} will be given on join and removed after verification. "
            "Use this to restrict channel access until verified.",
        ))

    @verification_group.command(name="pendingtimeout", help="Configure auto-action for members who never complete verification. Usage: verification pendingtimeout <on|off> [minutes] [kick|ban]")
    @security_staff()
    async def verification_pendingtimeout(self, ctx: commands.Context, toggle: str, minutes: Optional[int] = None, action: Optional[str] = None):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        toggle = toggle.lower()

        if toggle not in ("on", "off"):
            return await ctx.send(view=error_layout("Invalid", "Use `on` or `off`."))

        if toggle == "off":
            await guild_settings.set(ctx.guild.id, "verification_pending_timeout_enabled", False)
            return await ctx.send(view=success_layout(f"{e('check')} Pending timeout disabled", "Members can now stay unverified indefinitely."))

        if minutes is not None and minutes < 5:
            return await ctx.send(view=error_layout("Too Short", "Minimum timeout is 5 minutes, to avoid accidentally kicking slow-but-genuine members."))
        if action and action.lower() not in ("kick", "ban"):
            return await ctx.send(view=error_layout("Invalid Action", "Use `kick` or `ban`."))

        await guild_settings.set(ctx.guild.id, "verification_pending_timeout_enabled", True)
        if minutes is not None:
            await guild_settings.set(ctx.guild.id, "verification_pending_timeout_minutes", minutes)
        if action:
            await guild_settings.set(ctx.guild.id, "verification_pending_timeout_action", action.lower())

        final_minutes = minutes or await guild_settings.get(ctx.guild.id, "verification_pending_timeout_minutes", config.VERIFICATION_PENDING_TIMEOUT_MINUTES_DEFAULT)
        final_action = (action or await guild_settings.get(ctx.guild.id, "verification_pending_timeout_action", config.VERIFICATION_PENDING_TIMEOUT_ACTION_DEFAULT)).lower()

        await ctx.send(view=success_layout(
            f"{e('check')} Pending timeout enabled",
            f"Members who don't complete verification within **{final_minutes} minutes** will be **{final_action}ed** automatically.",
        ))

    @verification_group.command(name="attempts", help="Set how many wrong captcha codes are allowed before a temporary lockout (1-10).")
    @security_staff()
    async def verification_attempts(self, ctx: commands.Context, attempts: int):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if not 1 <= attempts <= 10:
            return await ctx.send(view=error_layout("Invalid value", "Choose a number between 1 and 10."))
        await guild_settings.set(ctx.guild.id, "verification_max_attempts", attempts)
        await ctx.send(view=success_layout(f"{e('check')} Attempts set", f"Members are locked out for {int(await settings.get(ctx.guild.id, 'verification', 'lockout_seconds')) // 60} minutes after **{attempts}** wrong codes."))

    @verification_group.command(name="minage", help="Require accounts to be at least this many hours old before they can verify (0 turns it off).")
    @security_staff()
    async def verification_minage(self, ctx: commands.Context, hours: int):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if not 0 <= hours <= 720:
            return await ctx.send(view=error_layout("Invalid value", "Choose between 0 and 720 hours."))
        await guild_settings.set(ctx.guild.id, "verification_min_account_age_hours", hours)
        text = f"Accounts younger than **{hours}h** cannot verify yet." if hours else "Account age is no longer checked."
        await ctx.send(view=success_layout(f"{e('check')} Minimum account age set", text))

    @verification_group.command(name="deny", help="Reject a member awaiting manual verification by kicking them.")
    @security_staff()
    @commands.guild_only()
    async def verification_deny(self, ctx: commands.Context, member: discord.Member, *, reason: str = "Verification denied"):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if member.id == ctx.guild.owner_id or member.top_role >= ctx.guild.me.top_role or (member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id):
            return await ctx.send(view=error_layout(f"{e('cross')} Cannot deny", "That member's role is too high for me or for you to act on."))
        try:
            await member.kick(reason=f"Verification denied by {ctx.author}: {reason}")
        except discord.HTTPException:
            return await ctx.send(view=error_layout(f"{e('cross')} Failed", "I could not kick that member."))
        await db.raw_execute("DELETE FROM pending_verification WHERE guild_id=? AND user_id=?", (ctx.guild.id, member.id))
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="verification_action", user_id=member.id, detail=f"denied by {ctx.author.id}")
        await ctx.send(view=success_layout(f"{e('check')} Denied", f"{member.mention} was removed."))

    @commands.command(name="approve", help='Manually approve a member awaiting verification.')
    @security_staff()
    @commands.guild_only()
    async def approve(self, ctx: commands.Context, member: discord.Member):
        from utils.components import error_layout, success_layout
        e = emoji_manager.get
        if not await _complete_verification(ctx.guild, member):
            return await ctx.send(view=error_layout(f"{e('cross')} Quarantined", f"{member.mention} is quarantined. Only the server owner or an Extra Owner can release them with `release`."))
        await ctx.send(view=success_layout(
            f"{e('check')} Approved",
            f"{member.mention} has been manually approved and granted access.",
        ))

async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
