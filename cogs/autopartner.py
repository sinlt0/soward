import asyncio
import logging
import time
from typing import Optional

import discord
from discord.ext import commands, tasks

import config
from utils import autopartner as store, emoji_manager
from utils.checks import has_guild_permission
from utils.colors import ERROR, NEUTRAL, SUCCESS
from utils.components import error_layout, footer_block, info_layout, success_layout

log = logging.getLogger("zyro.autopartner")

NO_PINGS = discord.AllowedMentions.none()
IMAGE_TYPES = ("image/png", "image/jpeg", "image/jpg", "image/webp")


def layout(title: str, body: str, *, color: int = NEUTRAL, row: Optional[discord.ui.ActionRow] = None) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
    if row is not None:
        container.add_item(discord.ui.Separator())
        container.add_item(row)
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


def panel_view(guild_name: str) -> discord.ui.LayoutView:
    e = emoji_manager.get
    body = (
        f"Want to partner with **{guild_name}**? Open a partner ticket and follow the steps:\n"
        "1. Post our ad in your server.\n"
        "2. Send your own ad in the ticket.\n"
        "3. Send a screenshot of our ad in your server.\n\n"
        "When the screenshot checks out, your ad is posted here automatically."
    )
    return layout(f"{e('epartner')} Partner with us", body, color=SUCCESS, row=OpenRow())


class OpenRow(discord.ui.ActionRow):
    def __init__(self):
        super().__init__(discord.ui.Button(label="Open partner ticket", style=discord.ButtonStyle.success, custom_id="autopartner:open", emoji=emoji_manager.get("epartner") or None))
        self.children[0].callback = self.open

    async def open(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("AutoPartner")
        if cog is None:
            return await interaction.response.send_message(view=error_layout("Unavailable", "Auto partner is not available right now."), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await cog.open_ticket(interaction)


class ControlRow(discord.ui.ActionRow):
    def __init__(self):
        super().__init__(
            discord.ui.Button(label="Approve", style=discord.ButtonStyle.success, custom_id="autopartner:approve"),
            discord.ui.Button(label="Close", style=discord.ButtonStyle.danger, custom_id="autopartner:close"),
        )
        self.children[0].callback = self.approve
        self.children[1].callback = self.close

    async def approve(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("AutoPartner")
        if cog is not None:
            await cog.button_approve(interaction)

    async def close(self, interaction: discord.Interaction):
        cog = interaction.client.get_cog("AutoPartner")
        if cog is not None:
            await cog.button_close(interaction)


def control_view() -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=SUCCESS)
    container.add_item(ControlRow())
    view.add_item(container)
    return view


class AutoPartner(commands.Cog):
    category = "Partners"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.open_channels: set[int] = set()
        self.locks: dict[int, asyncio.Lock] = {}

    async def cog_load(self):
        self.open_channels = await store.open_channel_ids()
        self.bot.add_view(control_view())
        self.bot.add_view(panel_view("this server"))
        self.sweep.start()

    async def cog_unload(self):
        self.sweep.cancel()

    @tasks.loop(minutes=30)
    async def sweep(self):
        for ticket in await store.stale_tickets(time.time() - config.AUTOPARTNER_IDLE_HOURS * 3600):
            await store.update_ticket(ticket["channel_id"], status="closed")
            self.open_channels.discard(ticket["channel_id"])
            channel = self.bot.get_channel(ticket["channel_id"])
            if channel is not None:
                try:
                    await channel.delete(reason="[Zyro Auto Partner] Ticket expired")
                except discord.HTTPException:
                    pass

    @sweep.before_loop
    async def before_sweep(self):
        await self.bot.wait_until_ready()

    def is_staff(self, member: discord.Member, cfg: dict) -> bool:
        if member.guild_permissions.manage_guild:
            return True
        role_id = cfg.get("staff_role_id")
        return bool(role_id and any(role.id == role_id for role in member.roles))

    async def log_to(self, guild: discord.Guild, cfg: dict, title: str, body: str, color: int = NEUTRAL) -> None:
        channel = guild.get_channel(cfg["log_channel_id"]) if cfg.get("log_channel_id") else None
        if channel is None:
            return
        try:
            await channel.send(view=layout(title, body, color=color), allowed_mentions=NO_PINGS)
        except discord.HTTPException:
            pass

    def overwrites(self, guild: discord.Guild, member: discord.Member, cfg: dict) -> dict:
        visible = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True)
        result = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: visible,
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, embed_links=True, attach_files=True),
        }
        role = guild.get_role(cfg["staff_role_id"]) if cfg.get("staff_role_id") else None
        if role is not None:
            result[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        return result

    async def open_ticket(self, interaction: discord.Interaction) -> None:
        e = emoji_manager.get
        guild, member = interaction.guild, interaction.user
        cfg = await store.get_config(guild.id)
        problem = None
        if not cfg["enabled"]:
            problem = "Partnerships are closed right now."
        elif not cfg["ad"] or not store.extract_invite(cfg["ad"]):
            problem = "Partnerships are not set up yet. Please tell an admin."
        elif guild.get_channel(cfg["partner_channel_id"] or 0) is None:
            problem = "Partnerships are not set up yet. Please tell an admin."
        if problem:
            return await interaction.followup.send(view=error_layout("Not available", problem), ephemeral=True)
        async with self.locks.setdefault(guild.id, asyncio.Lock()):
            existing = await store.open_ticket_of(guild.id, member.id)
            if existing:
                channel = guild.get_channel(existing["channel_id"])
                if channel is not None:
                    return await interaction.followup.send(view=error_layout("Already open", f"You already have a partner ticket: {channel.mention}"), ephemeral=True)
                await store.update_ticket(existing["channel_id"], status="closed")
                self.open_channels.discard(existing["channel_id"])
            category = guild.get_channel(cfg["category_id"]) if cfg.get("category_id") else None
            number = await store.next_number(guild.id)
            try:
                channel = await guild.create_text_channel(
                    name=f"partner-{number:04d}",
                    category=category if isinstance(category, discord.CategoryChannel) else None,
                    overwrites=self.overwrites(guild, member, cfg),
                    topic=f"Partner ticket #{number:04d} - {member} ({member.id})",
                    reason=f"[Zyro Auto Partner] Ticket opened by {member} ({member.id})",
                )
            except discord.HTTPException as exc:
                hint = "I need **Manage Channels** and **Manage Roles**." if isinstance(exc, discord.Forbidden) else "The category may be full."
                return await interaction.followup.send(view=error_layout("Could not create ticket", hint), ephemeral=True)
            await store.create_ticket(guild.id, channel.id, member.id, number)
            self.open_channels.add(channel.id)
        steps = (
            f"{member.mention}, here is how to partner with **{guild.name}**:\n\n"
            "**1.** Post this ad in your server:\n"
            f"```\n{cfg['ad']}\n```\n"
            "**2.** Send **your own ad** here in this channel exactly as you want it posted. It must contain your server invite. Image and gif links, masked links, `[Your Partnership ping]` and spoilers all work.\n"
            "**3.** Send a **screenshot** here that shows our ad posted in your server.\n\n"
            "I read the screenshot and check that our ad and invite are in it. When it passes, your ad is posted automatically.\n"
            f"-# You have {config.AUTOPARTNER_MAX_ATTEMPTS} tries. Staff can step in if the screenshot cannot be read."
        )
        await channel.send(view=layout(f"{e('epartner')} Partner ticket #{number:04d}", steps, row=ControlRow()), allowed_mentions=discord.AllowedMentions(users=[member]))
        await interaction.followup.send(view=success_layout(f"{e('check')} Ticket opened", f"Your ticket is ready: {channel.mention}"), ephemeral=True)
        await self.log_to(guild, cfg, f"{e('epartner')} Partner ticket opened", f"{channel.mention} by {member.mention}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or message.channel.id not in self.open_channels:
            return
        ticket = await store.get_ticket(message.channel.id)
        if ticket is None or ticket["status"] != "open" or message.author.id != ticket["user_id"]:
            return
        async with self.locks.setdefault(message.channel.id, asyncio.Lock()):
            ticket = await store.get_ticket(message.channel.id)
            if ticket is None or ticket["status"] != "open":
                return
            cfg = await store.get_config(message.guild.id)
            if message.content and store.extract_invite(message.content):
                await self.save_ad(message, ticket, cfg)
                return
            images = [a for a in message.attachments if (a.content_type or "").split(";")[0] in IMAGE_TYPES]
            if images:
                await self.check_screenshot(message, ticket, cfg, images[0])
            elif message.content and not ticket["ad"]:
                await message.reply(view=error_layout("I need your ad", "Send your ad with your server invite in it, for example `discord.gg/yourcode`."), mention_author=False)

    async def save_ad(self, message: discord.Message, ticket: dict, cfg: dict) -> bool:
        code = store.extract_invite(message.content)
        try:
            invite = await self.bot.fetch_invite(code)
        except discord.NotFound:
            await message.reply(view=error_layout("Invite not found", "That invite is invalid or expired. Send an invite that never expires."), mention_author=False)
            return False
        except discord.HTTPException:
            await message.reply(view=error_layout("Could not check the invite", "Try again in a moment."), mention_author=False)
            return False
        if invite.guild is not None and invite.guild.id == message.guild.id:
            await message.reply(view=error_layout("That is our server", "Send the invite of **your** server."), mention_author=False)
            return False
        if getattr(invite, "expires_at", None) is not None:
            await message.reply(view=error_layout("Invite expires", "Send an invite that never expires so the partnership keeps working."), mention_author=False)
            return False
        members = getattr(invite, "approximate_member_count", None) or 0
        if cfg["min_members"] and members < cfg["min_members"]:
            await message.reply(view=error_layout("Server too small", f"Your server has **{members}** members and we need at least **{cfg['min_members']}**."), mention_author=False)
            return False
        recent = await store.recent_post_for_code(message.guild.id, code)
        if recent:
            await message.reply(view=error_layout("Already partnered", f"This server was posted less than **{config.AUTOPARTNER_REPEAT_DAYS}** days ago."), mention_author=False)
            return False
        name = invite.guild.name if invite.guild is not None else code
        await store.update_ticket(message.channel.id, ad=store.clean_ad(message.content), invite_code=code, invite_guild=name)
        try:
            await message.add_reaction("✅")
        except discord.HTTPException:
            pass
        note = "\n-# Files uploaded with the ad are not copied. Put image or gif links in the text instead." if message.attachments else ""
        await message.reply(view=info_layout("Ad saved", f"Your ad for **{name}** is saved exactly as you sent it. Now send the **screenshot** of our ad in your server.{note}"), mention_author=False)
        return True

    async def check_screenshot(self, message: discord.Message, ticket: dict, cfg: dict, attachment: discord.Attachment) -> None:
        e = emoji_manager.get
        if not ticket["ad"]:
            return await message.reply(view=error_layout("Send your ad first", "I need your ad with your server invite before I check the screenshot."), mention_author=False)
        if attachment.size > config.AUTOPARTNER_MAX_IMAGE_BYTES:
            return await message.reply(view=error_layout("Image too large", "Send a screenshot under 8 MB."), mention_author=False)
        if not store.ocr_available():
            await message.reply(view=info_layout("Waiting for staff", "I cannot read screenshots right now, so a staff member will approve this ticket."), mention_author=False)
            return await self.ping_staff(message.channel, cfg)
        data = await attachment.read()
        value = store.digest(data)
        if await store.hash_used(message.guild.id, value):
            return await message.reply(view=error_layout("Screenshot already used", "This exact screenshot was used before. Send a fresh one."), mention_author=False)
        async with message.channel.typing():
            try:
                text = await store.read_image(data)
            except Exception:
                log.warning("OCR failed", exc_info=True)
                await message.reply(view=error_layout("Could not read it", "I could not read that image. A staff member can approve it instead."), mention_author=False)
                return await self.ping_staff(message.channel, cfg)
        our_code = store.extract_invite(cfg["ad"]) or ""
        names = tuple([message.guild.name] + store.link_texts(cfg["ad"]))
        result = store.verify(text, cfg["ad"], our_code, names)
        if result["ok"]:
            await store.save_hash(message.guild.id, value)
            return await self.publish(message.channel, ticket, cfg)
        attempts = ticket["attempts"] + 1
        await store.update_ticket(message.channel.id, attempts=attempts)
        left = config.AUTOPARTNER_MAX_ATTEMPTS - attempts
        missing = []
        if result["score"] < config.AUTOPARTNER_OCR_THRESHOLD:
            missing.append(f"our ad text was only **{int(result['score'] * 100)}%** visible")
        if not result["code"]:
            missing.append(f"our invite `{our_code}` or server name was not found")
        body = "I could not verify the screenshot: " + " and ".join(missing) + ".\nMake sure the whole ad and its invite are visible, then send it again."
        if left > 0:
            return await message.reply(view=error_layout(f"{e('cross')} Not verified", f"{body}\n-# {left} {'try' if left == 1 else 'tries'} left."), mention_author=False)
        await message.reply(view=error_layout(f"{e('cross')} Not verified", f"{body}\nYou are out of tries, so staff will look at this ticket."), mention_author=False)
        await self.ping_staff(message.channel, cfg)

    async def ping_staff(self, channel: discord.TextChannel, cfg: dict) -> None:
        role = channel.guild.get_role(cfg["staff_role_id"]) if cfg.get("staff_role_id") else None
        if role is not None:
            await channel.send(f"{role.mention} this ticket needs a manual check. Press **Approve** if the ad was posted.", allowed_mentions=discord.AllowedMentions(roles=[role]))
        else:
            await channel.send("Staff: this ticket needs a manual check. Press **Approve** if the ad was posted.")

    async def publish(self, channel: discord.TextChannel, ticket: dict, cfg: dict, approver: Optional[discord.Member] = None) -> bool:
        e = emoji_manager.get
        guild = channel.guild
        target = guild.get_channel(cfg["partner_channel_id"] or 0)
        if target is None:
            await channel.send(view=error_layout("Partner channel missing", "The partner channel was deleted. Tell an admin to set it again."))
            return False
        ping = guild.get_role(cfg["ping_role_id"]) if cfg.get("ping_role_id") else None
        user_id = ticket["user_id"]
        content = store.render_ad(ticket["ad"], ping.mention if ping else "")
        try:
            posted = await target.send(content, allowed_mentions=discord.AllowedMentions(roles=[ping] if ping else [], users=[], everyone=False))
        except discord.HTTPException:
            await channel.send(view=error_layout("Could not post", f"I cannot send messages in {target.mention}. Tell an admin."))
            return False
        post_id = await store.add_post(guild.id, user_id, ticket["invite_code"], ticket["invite_guild"], target.id, posted.id)
        await store.update_ticket(channel.id, status="approved")
        self.open_channels.discard(channel.id)
        by = f" Approved by {approver.mention}." if approver else ""
        await channel.send(view=success_layout(f"{e('check')} Partnership posted", f"Your ad is live in {target.mention}.{by}\nThis ticket closes in **{config.AUTOPARTNER_CLOSE_DELAY}** seconds."), allowed_mentions=NO_PINGS)
        await self.log_to(guild, cfg, f"{e('epartner')} Partner posted", f"**{ticket['invite_guild']}** (`{ticket['invite_code']}`) by <@{user_id}>\nPost ID: `{post_id}` · {posted.jump_url}", SUCCESS)
        await self.delete_later(channel)
        return True

    async def delete_later(self, channel: discord.TextChannel) -> None:
        await asyncio.sleep(config.AUTOPARTNER_CLOSE_DELAY)
        try:
            await channel.delete(reason="[Zyro Auto Partner] Ticket finished")
        except discord.HTTPException:
            pass

    async def button_approve(self, interaction: discord.Interaction) -> None:
        ticket = await store.get_ticket(interaction.channel.id)
        cfg = await store.get_config(interaction.guild.id)
        if ticket is None or ticket["status"] != "open":
            return await interaction.response.send_message(view=error_layout("Not open", "This is not an open partner ticket."), ephemeral=True)
        if not self.is_staff(interaction.user, cfg):
            return await interaction.response.send_message(view=error_layout("Staff only", "Only staff can approve a partnership."), ephemeral=True)
        if not ticket["ad"]:
            return await interaction.response.send_message(view=error_layout("No ad yet", "The partner has not sent their ad with an invite."), ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        done = await self.publish(interaction.channel, ticket, cfg, approver=interaction.user)
        await interaction.followup.send("Posted." if done else "Could not post.", ephemeral=True)

    async def button_close(self, interaction: discord.Interaction) -> None:
        ticket = await store.get_ticket(interaction.channel.id)
        cfg = await store.get_config(interaction.guild.id)
        if ticket is None:
            return await interaction.response.send_message(view=error_layout("Not a ticket", "This is not a partner ticket."), ephemeral=True)
        if interaction.user.id != ticket["user_id"] and not self.is_staff(interaction.user, cfg):
            return await interaction.response.send_message(view=error_layout("Not allowed", "Only the partner or staff can close this ticket."), ephemeral=True)
        await store.update_ticket(interaction.channel.id, status="closed")
        self.open_channels.discard(interaction.channel.id)
        await interaction.response.send_message(view=info_layout("Closing", f"This ticket closes in **{config.AUTOPARTNER_CLOSE_DELAY}** seconds."))
        await self.delete_later(interaction.channel)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if channel.id in self.open_channels:
            self.open_channels.discard(channel.id)
            await store.update_ticket(channel.id, status="closed")

    @commands.group(name="autopartner", aliases=["apartner", "partnerbot"], invoke_without_command=True, help="Automatic partnerships. Partners post your ad, send a screenshot and get posted.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def autopartner(self, ctx: commands.Context):
        await self.status(ctx)

    @autopartner.command(name="status", aliases=["settings"], help="Show the auto partner setup.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def status(self, ctx: commands.Context):
        e = emoji_manager.get
        cfg = await store.get_config(ctx.guild.id)
        def ref(kind: str, value):
            if not value:
                return "not set"
            return f"<{kind}{value}>"
        ocr = "ready" if store.ocr_available() else "**not installed**, staff must approve every ticket"
        lines = [
            f"**Open for partners:** {'yes' if cfg['enabled'] else 'no'}",
            f"**Our ad:** {'set' if cfg['ad'] else 'not set'} · invite {'found' if store.extract_invite(cfg['ad']) else 'missing'}",
            f"**Partner channel:** {ref('#', cfg['partner_channel_id'])}",
            f"**Ticket category:** {ref('#', cfg['category_id'])}",
            f"**Staff role:** {ref('@&', cfg['staff_role_id'])}",
            f"**Ping role:** {ref('@&', cfg['ping_role_id'])}",
            f"**Log channel:** {ref('#', cfg['log_channel_id'])}",
            f"**Minimum members:** {cfg['min_members'] or 'none'}",
            f"**Screenshot reading:** {ocr}",
            "",
            "-# `autopartner ad <text>`, `channel`, `category`, `staff`, `ping`, `log`, `minmembers`, `enable`, `disable`, then `autopartner panel #channel`.",
        ]
        await ctx.send(view=info_layout(f"{e('epartner')} Auto partner", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @autopartner.command(name="ad", help="Set your server's ad. It must contain your invite. Usage: autopartner ad <text>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def set_ad(self, ctx: commands.Context, *, text: str):
        e = emoji_manager.get
        if not store.extract_invite(text):
            return await ctx.send(view=error_layout("Invite needed", "Your ad must contain your server invite, for example `discord.gg/yourcode`."))
        await store.update_config(ctx.guild.id, ad=store.clean_ad(text))
        await ctx.send(view=success_layout(f"{e('check')} Ad saved", f"Partners will be asked to post this ad:\n```\n{store.clean_ad(text)}\n```"))

    async def set_value(self, ctx: commands.Context, field: str, value, label: str, shown: str):
        e = emoji_manager.get
        await store.update_config(ctx.guild.id, **{field: value})
        await ctx.send(view=success_layout(f"{e('check')} {label}", shown), allowed_mentions=NO_PINGS)

    @autopartner.command(name="channel", help="Set where partner ads are posted. Usage: autopartner channel <#channel>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await self.set_value(ctx, "partner_channel_id", channel.id, "Partner channel", f"Partner ads will be posted in {channel.mention}.")

    @autopartner.command(name="category", help="Set the category for partner tickets. Usage: autopartner category <category|off>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def set_category(self, ctx: commands.Context, category: Optional[discord.CategoryChannel] = None):
        await self.set_value(ctx, "category_id", category.id if category else None, "Ticket category", f"Tickets open in **{category.name}**." if category else "Tickets open without a category.")

    @autopartner.command(name="staff", help="Set the role that can see and approve partner tickets. Usage: autopartner staff <@role|off>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def set_staff(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        await self.set_value(ctx, "staff_role_id", role.id if role else None, "Staff role", f"{role.mention} can see and approve partner tickets." if role else "No staff role. Only people with Manage Server can approve.")

    @autopartner.command(name="ping", help="Set a role to ping on each new partner post. Usage: autopartner ping <@role|off>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def set_ping(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        await self.set_value(ctx, "ping_role_id", role.id if role else None, "Ping role", f"{role.mention} is pinged on every new partner post." if role else "No role is pinged.")

    @autopartner.command(name="log", help="Set the log channel. Usage: autopartner log <#channel|off>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def set_log(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        await self.set_value(ctx, "log_channel_id", channel.id if channel else None, "Log channel", f"Partner activity is logged in {channel.mention}." if channel else "Partner logging is off.")

    @autopartner.command(name="minmembers", aliases=["minimum"], help="Require a minimum member count. Usage: autopartner minmembers <number|0>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def set_min(self, ctx: commands.Context, count: commands.Range[int, 0, 1000000]):
        await self.set_value(ctx, "min_members", count, "Minimum members", f"Partner servers need at least **{count}** members." if count else "There is no minimum.")

    @autopartner.command(name="enable", help="Open partnerships.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def enable(self, ctx: commands.Context):
        await self.set_value(ctx, "enabled", 1, "Open", "Partner tickets can be opened.")

    @autopartner.command(name="disable", help="Close partnerships. Open tickets keep working.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def disable(self, ctx: commands.Context):
        await self.set_value(ctx, "enabled", 0, "Closed", "New partner tickets cannot be opened.")

    @autopartner.command(name="panel", aliases=["post", "send"], help="Post the partner ticket button. Usage: autopartner panel [#channel]")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        e = emoji_manager.get
        channel = channel or ctx.channel
        cfg = await store.get_config(ctx.guild.id)
        if not cfg["ad"] or not cfg["partner_channel_id"]:
            return await ctx.send(view=error_layout("Finish setup first", "Set `autopartner ad` and `autopartner channel` before posting the panel."))
        try:
            await channel.send(view=panel_view(ctx.guild.name))
        except discord.HTTPException:
            return await ctx.send(view=error_layout("Cannot post", f"I cannot send messages in {channel.mention}."))
        await ctx.send(view=success_layout(f"{e('check')} Panel posted", f"The partner panel is in {channel.mention}."))

    @autopartner.command(name="list", aliases=["partners", "posts"], help="Show recent partner posts.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def list_posts(self, ctx: commands.Context):
        e = emoji_manager.get
        posts = await store.recent_posts(ctx.guild.id)
        if not posts:
            return await ctx.send(view=info_layout(f"{e('epartner')} Partners", "No partners have been posted yet."))
        lines = [f"`{p['post_id']}` **{p['invite_guild']}** · <@{p['user_id']}> · <t:{int(p['created_at'])}:R>" for p in posts]
        await ctx.send(view=info_layout(f"{e('epartner')} Recent partners", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @autopartner.command(name="remove", aliases=["delete"], help="Delete a partner post. Usage: autopartner remove <post id>")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def remove_post(self, ctx: commands.Context, post_id: str):
        e = emoji_manager.get
        post = await store.get_post(ctx.guild.id, post_id.lower())
        if post is None:
            return await ctx.send(view=error_layout("Not found", "Use `autopartner list` to see post IDs."))
        channel = ctx.guild.get_channel(post["channel_id"])
        if channel is not None:
            try:
                await (await channel.fetch_message(post["message_id"])).delete()
            except discord.HTTPException:
                pass
        await store.delete_post(post["post_id"])
        await ctx.send(view=success_layout(f"{e('check')} Removed", f"Removed the post for **{post['invite_guild']}**."))


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoPartner(bot))
