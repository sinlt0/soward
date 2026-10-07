import io
import random
import string
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import db, embed_templates, emoji_manager, guild_settings, incident, message_vars
from utils.checks import has_guild_permission
from utils.events_bus import (
    ANTINUKE_INCIDENT,
    INCIDENT_STATE_CHANGED,
    MEMBER_JOINED_UNVERIFIED,
    MEMBER_VERIFIED,
    LOG_EVENT,
    bus,
)
import config

def _make_captcha_image(code: str) -> discord.File:
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

        try:
            from PIL import Image, ImageDraw, ImageFont
            img = Image.new("RGB", (280, 90), color=(30, 30, 35))
            draw = ImageDraw.Draw(img)
            font = ImageFont.load_default()
            draw.text((20, 30), code, fill=(255, 255, 255), font=font)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            return discord.File(buf, filename="captcha.png")
        except Exception:
            buf = io.BytesIO(code.encode())
            return discord.File(buf, filename="captcha.txt")

async def _complete_verification(guild: discord.Guild, member: discord.Member):
    await bus.publish(MEMBER_VERIFIED, guild_id=guild.id, user_id=member.id)
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
        if role:
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

class CaptchaCodeModal(discord.ui.Modal, title="Enter captcha code"):
    code_input = discord.ui.TextInput(
        label="Code",
        placeholder="Type the code exactly as shown",
        min_length=6,
        max_length=6,
    )

    def __init__(self, correct: str):
        super().__init__()
        self.correct = correct.upper()

    async def on_submit(self, interaction: discord.Interaction):
        e = emoji_manager.get
        if self.code_input.value.strip().upper() != self.correct:
            err = discord.ui.LayoutView(timeout=None)
            c = discord.ui.Container(accent_color=0xED4245)
            c.add_item(discord.ui.TextDisplay(
                f"## {e('cross')} Wrong code\nThat code is incorrect. Click **Verify** on the panel again for a new code."
            ))
            err.add_item(c)
            await interaction.response.send_message(view=err, ephemeral=True)
            return

        await _complete_verification(interaction.guild, interaction.user)
        ok = discord.ui.LayoutView(timeout=None)
        c = discord.ui.Container(accent_color=0x57F287)
        c.add_item(discord.ui.TextDisplay(
            f"## {e('check')} Verified!\nYou now have access to **{interaction.guild.name}**. Welcome!"
        ))
        ok.add_item(c)
        await interaction.response.send_message(view=ok, ephemeral=True)

class CaptchaChallengeRow(discord.ui.ActionRow):
    def __init__(self, code: str, layout: "CaptchaChallengeLayout"):
        super().__init__()
        self.code = code
        self.layout_ref = layout

    @discord.ui.button(label="Enter code", style=discord.ButtonStyle.primary, custom_id="verification:enter_code")
    async def enter_code_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(CaptchaCodeModal(self.code))

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

    current_state = await incident.get_state(guild.id)
    if current_state >= config.INCIDENT_STATES["lockdown"]:
        lock = discord.ui.LayoutView(timeout=None)
        c = discord.ui.Container(accent_color=0xED4245)
        c.add_item(discord.ui.TextDisplay(
            f"## {e('lockdown')} Server locked\n"
            "This server is in lockdown. Please wait for a staff member to manually approve your access."
        ))
        lock.add_item(c)
        await interaction.response.send_message(view=lock, ephemeral=True)
        return

    verified_role_id = await guild_settings.get(guild.id, "verification_role_id")
    if verified_role_id:
        role = guild.get_role(int(verified_role_id))
        if role and role in member.roles:
            already = discord.ui.LayoutView(timeout=None)
            c = discord.ui.Container(accent_color=0x57F287)
            c.add_item(discord.ui.TextDisplay(
                f"## {e('check')} Already verified\nYou already have access to **{guild.name}**."
            ))
            already.add_item(c)
            await interaction.response.send_message(view=already, ephemeral=True)
            return

    level = await guild_settings.get(guild.id, "verification_level", config.VERIFICATION_LEVELS["none"])

    if level == config.VERIFICATION_LEVELS["none"] or level == config.VERIFICATION_LEVELS["button"]:

        await _complete_verification(guild, member)
        ok = discord.ui.LayoutView(timeout=None)
        c = discord.ui.Container(accent_color=0x57F287)
        c.add_item(discord.ui.TextDisplay(
            f"## {e('check')} Verified!\nYou now have access to **{guild.name}**. Welcome!"
        ))
        ok.add_item(c)
        await interaction.response.send_message(view=ok, ephemeral=True)

    elif level == config.VERIFICATION_LEVELS["captcha"]:
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        captcha_file = _make_captcha_image(code)
        challenge = CaptchaChallengeLayout(code)
        await interaction.response.send_message(
            view=challenge,
            files=[captcha_file],
            ephemeral=True,
        )

    elif level == config.VERIFICATION_LEVELS["manual"]:
        pending = discord.ui.LayoutView(timeout=None)
        c = discord.ui.Container(accent_color=0x2B2D31)
        c.add_item(discord.ui.TextDisplay(
            f"## {e('info')} Manual review\n"
            "Your verification request has been noted. A staff member will review and grant you access shortly."
        ))
        pending.add_item(c)
        await interaction.response.send_message(view=pending, ephemeral=True)
        await bus.publish(
            LOG_EVENT,
            guild_id=guild.id,
            action="verification_action",
            user_id=member.id,
            detail="manual verification requested",
        )

    else:
        await _complete_verification(guild, member)
        ok = discord.ui.LayoutView(timeout=None)
        c = discord.ui.Container(accent_color=0x57F287)
        c.add_item(discord.ui.TextDisplay(
            f"## {e('check')} Verified!\nYou now have access to **{guild.name}**. Welcome!"
        ))
        ok.add_item(c)
        await interaction.response.send_message(view=ok, ephemeral=True)

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
        if current >= config.INCIDENT_STATES["lockdown"]:
            await guild_settings.set(guild_id, "verification_level", config.VERIFICATION_LEVELS["manual"])

    async def _on_incident_state_changed(self, *, guild_id: int, new_state: int, **kwargs):
        if new_state == config.INCIDENT_STATES["normal"]:
            base = await guild_settings.get(
                guild_id, "verification_level_base", config.VERIFICATION_LEVELS["button"]
            )
            await guild_settings.set(guild_id, "verification_level", base)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        guild_id = member.guild.id
        level = await guild_settings.get(guild_id, "verification_level", config.VERIFICATION_LEVELS["none"])
        if level == config.VERIFICATION_LEVELS["none"]:
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

    @verification_group.command(name="setup", help="Post the one-time verification panel in a channel.")
    @has_guild_permission("administrator")
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
    @has_guild_permission("administrator")
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
    @has_guild_permission("administrator")
    async def verification_role(self, ctx: commands.Context, role: discord.Role):
        from utils.components import success_layout
        e = emoji_manager.get
        await guild_settings.set(ctx.guild.id, "verification_role_id", role.id)
        await ctx.send(view=success_layout(
            f"{e('check')} Verified role set",
            f"Members receive {role.mention} after passing verification.",
        ))

    @verification_group.command(name="message", help="Set a custom verification panel message, or `none`/`reset`/`default` to revert to the default look. Supports {embed:name} to render a saved embed template as a real embed (footer/image included), plus {server}/{membercount}/{servericon} and other variables.")
    @has_guild_permission("administrator")
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
    @has_guild_permission("administrator")
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
    @has_guild_permission("administrator")
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

    @commands.command(name="approve", help='Manually approve a member awaiting verification.')
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def approve(self, ctx: commands.Context, member: discord.Member):
        from utils.components import success_layout
        e = emoji_manager.get
        await _complete_verification(ctx.guild, member)
        await ctx.send(view=success_layout(
            f"{e('check')} Approved",
            f"{member.mention} has been manually approved and granted access.",
        ))

async def setup(bot: commands.Bot):
    await bot.add_cog(Verification(bot))
