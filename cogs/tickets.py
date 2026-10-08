import asyncio
import json
import logging
import re
import time
import typing
from typing import Optional

import discord
from discord.ext import commands, tasks

import config
from utils import db, emoji_manager, tickets
from utils.checks import has_guild_permission
from utils.colors import ERROR, NEUTRAL, SUCCESS
from utils.components import ConfirmLayout, error_layout, footer_block, info_layout, success_layout
from utils.events_bus import LOG_EVENT, bus

log = logging.getLogger("soward.tickets")

_TOUCH_INTERVAL = 60.0
_CLOSE_DELAY = 5


def _emoji(key: str) -> Optional[str]:
    return emoji_manager.get(key) or None


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9_-]+", "-", text.lower().strip()).strip("-")
    return cleaned[:90]


def _layout(title: str, body: str, *, color: int = NEUTRAL, attachment: Optional[str] = None) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(f"## {title}\n{body}"))
    if attachment:
        container.add_item(discord.ui.File(f"attachment://{attachment}"))
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


def build_panel_view(panel: dict) -> discord.ui.LayoutView:
    e = emoji_manager.get
    body = panel.get("welcome_text") or "Click the button below to open a private support ticket."
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=NEUTRAL)
    container.add_item(discord.ui.TextDisplay(f"## {e('ticket')} {panel['name']}\n{body}"))
    container.add_item(discord.ui.Separator())
    container.add_item(TicketOpenRow(panel["panel_id"], panel["button_label"]))
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


def build_control_view(
    *, number: int, owner: discord.abc.User, staff_mentions: str, subject: Optional[str],
    welcome: Optional[str], answers: Optional[list] = None,
) -> discord.ui.LayoutView:
    e = emoji_manager.get
    lines = [f"{owner.mention} {staff_mentions}".strip(), ""]
    if subject:
        lines.append(f"**Subject:** {subject}")
        lines.append("")
    if answers:
        budget = 2400
        for entry in answers:
            question = str(entry.get("question", ""))[:100]
            answer = (str(entry.get("answer", "")) or "*No answer provided.*")[:400]
            block = f"**{question}**\n{answer}\n"
            if budget - len(block) < 0:
                break
            budget -= len(block)
            lines.append(block)
    lines.append(welcome or "Describe your issue and a staff member will be with you shortly.")
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=SUCCESS)
    container.add_item(discord.ui.TextDisplay(f"## {e('ticket')} Ticket #{number:04d}\n" + "\n".join(lines)))
    container.add_item(discord.ui.Separator())
    container.add_item(TicketControlRow())
    container.add_item(discord.ui.Separator())
    for item in footer_block():
        container.add_item(item)
    view.add_item(container)
    return view


async def _post_log(
    guild: discord.Guild,
    view: discord.ui.LayoutView,
    file: Optional[discord.File] = None,
    override_channel_id: Optional[int] = None,
) -> None:
    channel = guild.get_channel(override_channel_id) if override_channel_id else None
    if channel is None:
        settings = await tickets.get_settings(guild.id)
        channel_id = settings.get("log_channel_id")
        channel = guild.get_channel(channel_id) if channel_id else None
    if channel is None:
        return
    try:
        if file is not None:
            await channel.send(view=view, file=file)
        else:
            await channel.send(view=view)
    except discord.HTTPException:
        log.warning("Could not post to ticket log channel %s in guild %s", channel_id, guild.id, exc_info=True)


async def _announce(bot: commands.Bot, guild: discord.Guild, user_id: Optional[int], detail: str) -> None:
    await bus.publish(LOG_EVENT, guild_id=guild.id, action="ticket_action", user_id=user_id, detail=detail)


async def close_ticket(
    bot: commands.Bot,
    guild: discord.Guild,
    channel: Optional[discord.abc.GuildChannel],
    ticket: dict,
    closer: Optional[discord.abc.User],
    reason: Optional[str],
) -> None:
    e = emoji_manager.get
    cog = bot.get_cog("Tickets")
    if cog is not None:
        if ticket["channel_id"] in cog.closing:
            return
        cog.closing.add(ticket["channel_id"])

    reason_text = (reason or "No reason provided")[:500]
    data = None
    if channel is not None:
        try:
            data = await tickets.build_transcript(channel, f"Ticket #{ticket['number']:04d}")
        except discord.HTTPException:
            log.warning("Transcript failed for ticket %s", ticket["ticket_id"], exc_info=True)

    await tickets.update_ticket(
        ticket["ticket_id"],
        status="closed",
        closed_at=time.time(),
        closed_by=closer.id if closer else None,
        close_reason=reason_text,
    )
    if cog is not None:
        cog.open_channels.discard(ticket["channel_id"])

    owner = guild.get_member(ticket["owner_id"])
    panel = await tickets.get_panel(ticket["panel_id"]) if ticket.get("panel_id") else None
    transcript_target = panel["transcript_channel_id"] if panel else None
    summary = (
        f"**Ticket:** #{ticket['number']:04d}\n"
        f"**Opened by:** <@{ticket['owner_id']}>\n"
        f"**Closed by:** {closer.mention if closer else 'System'}\n"
        f"**Reason:** {reason_text}"
    )
    if data is not None:
        name = tickets.transcript_name(ticket["channel_id"])
        await _post_log(
            guild,
            _layout(f"{e('lock')} Ticket Closed", summary, color=ERROR, attachment=name),
            tickets.transcript_file(data, ticket["channel_id"]),
            transcript_target,
        )
        if owner is not None:
            try:
                await owner.send(
                    view=_layout(f"{e('lock')} Your ticket was closed", f"{summary}\n\nYour transcript is attached.", color=ERROR, attachment=name),
                    file=tickets.transcript_file(data, ticket["channel_id"]),
                )
            except discord.HTTPException:
                pass
    else:
        await _post_log(guild, _layout(f"{e('lock')} Ticket Closed", summary, color=ERROR), None, transcript_target)

    await _announce(bot, guild, closer.id if closer else None, f"Closed ticket #{ticket['number']:04d} ({reason_text})")

    if channel is not None:
        try:
            await channel.send(view=_layout(f"{e('lock')} Closing", f"This ticket will be deleted in {_CLOSE_DELAY} seconds.", color=ERROR))
            await asyncio.sleep(_CLOSE_DELAY)
            await channel.delete(reason=f"[Soward Tickets] Ticket #{ticket['number']:04d} closed")
        except discord.HTTPException:
            log.warning("Could not delete ticket channel %s", ticket["channel_id"], exc_info=True)
    if cog is not None:
        cog.closing.discard(ticket["channel_id"])


_user_locks: dict[tuple[int, int], asyncio.Lock] = {}


async def open_ticket(interaction: discord.Interaction, panel_id: str, subject: Optional[str], answers: Optional[list] = None) -> None:
    e = emoji_manager.get
    guild = interaction.guild
    member = interaction.user
    panel = await tickets.get_panel(panel_id)
    if panel is None:
        return await interaction.followup.send(view=error_layout("Panel removed", "This ticket panel no longer exists."), ephemeral=True)

    staff_ids = tickets.parse_ids(panel["staff_role_ids"])
    staff_roles = [r for r in (guild.get_role(rid) for rid in staff_ids) if r is not None]
    if not staff_roles:
        return await interaction.followup.send(view=error_layout("Panel not ready", "This panel has no staff role set up yet. Please tell an admin."), ephemeral=True)

    lock = _user_locks.setdefault((guild.id, member.id), asyncio.Lock())
    async with lock:
        settings = await tickets.get_settings(guild.id)
        current = await tickets.open_count(guild.id, member.id)
        if current >= settings["max_open"]:
            return await interaction.followup.send(
                view=error_layout("Ticket limit reached", f"You already have **{current}** open ticket(s). The limit is **{settings['max_open']}**."),
                ephemeral=True,
            )
        if panel["one_per_user"] and await tickets.has_open_in_panel(panel["panel_id"], member.id):
            return await interaction.followup.send(
                view=error_layout("Already open", "You already have an open ticket for this panel."), ephemeral=True
            )
        active_limit = await tickets.limit_for(guild.id, "active")
        if await tickets.active_count(guild.id) >= active_limit:
            return await interaction.followup.send(
                view=error_layout(
                    "Server ticket limit reached",
                    f"This server has reached its limit of **{active_limit}** open tickets. Close some tickets or upgrade to Premium for **{tickets.premium_limit('active')}**.",
                ),
                ephemeral=True,
            )

        category, all_full = tickets.pick_category(guild, panel)
        if all_full:
            return await interaction.followup.send(
                view=error_layout("No room", "Every ticket category on this panel is full. An admin needs to add another category."),
                ephemeral=True,
            )

        number = await tickets.next_number(guild.id)
        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{number:04d}",
                category=category,
                overwrites=tickets.build_overwrites(guild, member, staff_roles),
                topic=f"Ticket #{number:04d} - opened by {member} ({member.id})",
                reason=f"[Soward Tickets] Ticket opened by {member} ({member.id})",
            )
        except discord.HTTPException as exc:
            hint = "I need **Manage Channels** and **Manage Roles**." if isinstance(exc, discord.Forbidden) else "The category may be full."
            return await interaction.followup.send(view=error_layout("Could not create ticket", hint), ephemeral=True)

        await tickets.create_ticket(guild.id, channel.id, member.id, panel["panel_id"], number, subject, answers)
        cog = interaction.client.get_cog("Tickets")
        if cog is not None:
            cog.open_channels.add(channel.id)

    mentions = " ".join(r.mention for r in staff_roles)
    await channel.send(
        view=build_control_view(
            number=number, owner=member, staff_mentions=mentions, subject=subject,
            welcome=panel.get("welcome_text"), answers=answers,
        )
    )
    await interaction.followup.send(
        view=success_layout(f"{e('check')} Ticket opened", f"Your ticket is ready: {channel.mention}"), ephemeral=True
    )
    await _post_log(
        guild,
        _layout(f"{e('ticket')} Ticket Opened", f"**Ticket:** {channel.mention} (#{number:04d})\n**Opened by:** {member.mention}\n**Panel:** {panel['name']}", color=SUCCESS),
    )
    await _announce(interaction.client, guild, member.id, f"Opened ticket #{number:04d} via panel **{panel['name']}**")


class QuestionModal(discord.ui.Modal):
    def __init__(self, panel: dict, page: int):
        questions = tickets.parse_list(panel["questions"])
        size = config.TICKET_MODAL_PAGE_SIZE
        pages = max(1, -(-len(questions) // size))
        title = panel["name"] if pages == 1 else f"{panel['name']} ({page + 1}/{pages})"
        super().__init__(title=title[:45] or "Open a ticket", timeout=300)
        self.panel_id = panel["panel_id"]
        self.page = page
        self.pages = pages
        self.total = len(questions)
        self.entries: list[tuple[int, str, discord.ui.TextInput]] = []
        for offset, question in enumerate(questions[page * size:(page + 1) * size]):
            index = page * size + offset
            field = discord.ui.TextInput(
                label=str(question)[:45],
                style=discord.TextStyle.paragraph,
                required=True,
                max_length=1000,
            )
            self.entries.append((index, str(question), field))
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        e = emoji_manager.get
        guild_id, user_id = interaction.guild.id, interaction.user.id
        recorded = tickets.record_answers(
            guild_id, user_id, self.panel_id, [(i, q, f.value) for i, q, f in self.entries]
        )
        if not recorded:
            return await interaction.response.send_message(
                view=error_layout("Form expired", "Your form session timed out. Click the panel button to start again."), ephemeral=True
            )
        if self.page + 1 < self.pages:
            panel = await tickets.get_panel(self.panel_id)
            if panel is None:
                tickets.clear_session(guild_id, user_id, self.panel_id)
                return await interaction.response.send_message(view=error_layout("Panel removed", "This ticket panel no longer exists."), ephemeral=True)
            view = discord.ui.LayoutView(timeout=600)
            container = discord.ui.Container(accent_color=NEUTRAL)
            container.add_item(discord.ui.TextDisplay(
                f"## {e('check')} Answers saved\nPage {self.page + 1} of {self.pages} done. Click continue for the next questions."
            ))
            container.add_item(ContinueRow(panel, self.page + 1, user_id))
            view.add_item(container)
            return await interaction.response.send_message(view=view, ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        answers = tickets.get_answers(guild_id, user_id, self.panel_id)
        tickets.clear_session(guild_id, user_id, self.panel_id)
        await open_ticket(interaction, self.panel_id, None, answers)


class ContinueRow(discord.ui.ActionRow):
    def __init__(self, panel: dict, next_page: int, user_id: int):
        super().__init__(discord.ui.Button(label="Continue", style=discord.ButtonStyle.primary))
        self.panel = panel
        self.next_page = next_page
        self.user_id = user_id
        self.children[0].callback = self._continue

    async def _continue(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message(view=error_layout("Not yours", "This form belongs to someone else."), ephemeral=True)
        await interaction.response.send_modal(QuestionModal(self.panel, self.next_page))


class SubjectModal(discord.ui.Modal, title="Open a ticket"):
    subject = discord.ui.TextInput(
        label="What do you need help with?",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=True,
    )

    def __init__(self, panel_id: str):
        super().__init__(timeout=300)
        self.panel_id = panel_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await open_ticket(interaction, self.panel_id, self.subject.value)


class CloseModal(discord.ui.Modal, title="Close ticket"):
    reason = discord.ui.TextInput(
        label="Reason (optional)",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    def __init__(self, ticket: dict):
        super().__init__(timeout=300)
        self.ticket = ticket

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(view=info_layout("Closing", "Saving the transcript and closing this ticket."), ephemeral=True)
        await close_ticket(interaction.client, interaction.guild, interaction.channel, self.ticket, interaction.user, self.reason.value or None)


class TicketOpenRow(discord.ui.ActionRow):
    def __init__(self, panel_id: str, label: str):
        super().__init__(
            discord.ui.Button(
                label=label[:80],
                style=discord.ButtonStyle.success,
                custom_id=f"ticket:open:{panel_id}",
                emoji=_emoji("ticket"),
            ),
        )
        self.panel_id = panel_id
        self.children[0].callback = self._open

    async def _open(self, interaction: discord.Interaction):
        panel = await tickets.get_panel(self.panel_id)
        if panel is None:
            return await interaction.response.send_message(view=error_layout("Panel removed", "This ticket panel no longer exists."), ephemeral=True)
        if tickets.parse_list(panel["questions"]):
            tickets.start_session(interaction.guild.id, interaction.user.id, self.panel_id)
            return await interaction.response.send_modal(QuestionModal(panel, 0))
        if panel["ask_subject"]:
            return await interaction.response.send_modal(SubjectModal(self.panel_id))
        await interaction.response.defer(ephemeral=True)
        await open_ticket(interaction, self.panel_id, None)


class TicketControlRow(discord.ui.ActionRow):
    def __init__(self):
        super().__init__(
            discord.ui.Button(label="Claim", style=discord.ButtonStyle.primary, custom_id="ticket:claim", emoji=_emoji("star")),
            discord.ui.Button(label="Close", style=discord.ButtonStyle.danger, custom_id="ticket:close", emoji=_emoji("lock")),
        )
        self.children[0].callback = self._claim
        self.children[1].callback = self._close

    async def _claim(self, interaction: discord.Interaction):
        ticket = await tickets.get_ticket_by_channel(interaction.channel.id)
        if ticket is None:
            return await interaction.response.send_message(view=error_layout("Not a ticket", "This channel is not an open ticket."), ephemeral=True)
        panel = await tickets.get_panel(ticket["panel_id"]) if ticket["panel_id"] else None
        if not tickets.is_staff(interaction.user, panel):
            return await interaction.response.send_message(view=error_layout("Staff only", "Only ticket staff can claim tickets."), ephemeral=True)
        await _do_claim(interaction.client, interaction.guild, interaction.channel, ticket, interaction.user, interaction)

    async def _close(self, interaction: discord.Interaction):
        ticket = await tickets.get_ticket_by_channel(interaction.channel.id)
        if ticket is None:
            return await interaction.response.send_message(view=error_layout("Not a ticket", "This channel is not an open ticket."), ephemeral=True)
        panel = await tickets.get_panel(ticket["panel_id"]) if ticket["panel_id"] else None
        if interaction.user.id != ticket["owner_id"] and not tickets.is_staff(interaction.user, panel):
            return await interaction.response.send_message(view=error_layout("Not allowed", "Only the ticket owner or staff can close this ticket."), ephemeral=True)
        await interaction.response.send_modal(CloseModal(ticket))


async def _do_claim(bot, guild, channel, ticket, member, interaction=None) -> None:
    e = emoji_manager.get
    if ticket["claimed_by"]:
        view = error_layout("Already claimed", f"This ticket is already claimed by <@{ticket['claimed_by']}>.")
        if interaction is not None:
            return await interaction.response.send_message(view=view, ephemeral=True)
        return await channel.send(view=view)
    await tickets.update_ticket(ticket["ticket_id"], claimed_by=member.id)
    notice = _layout(f"{e('star')} Ticket Claimed", f"{member.mention} is now handling this ticket.", color=SUCCESS)
    if interaction is not None:
        await interaction.response.send_message(view=notice)
    else:
        await channel.send(view=notice)
    await _post_log(guild, _layout(f"{e('star')} Ticket Claimed", f"**Ticket:** {channel.mention} (#{ticket['number']:04d})\n**Claimed by:** {member.mention}", color=SUCCESS))
    await _announce(bot, guild, member.id, f"Claimed ticket #{ticket['number']:04d}")


class Tickets(commands.Cog):
    category = "Tickets"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.open_channels: set[int] = set()
        self.closing: set[int] = set()
        self._last_touch: dict[int, float] = {}
        self.autoclose_loop.start()

    async def cog_load(self):
        self.open_channels = await tickets.open_channel_ids()
        control = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=SUCCESS)
        container.add_item(TicketControlRow())
        control.add_item(container)
        self.bot.add_view(control)
        for guild_panels in await db.raw_fetch("SELECT * FROM ticket_panels"):
            try:
                self.bot.add_view(build_panel_view(dict(guild_panels)))
            except Exception:
                log.warning("Could not register ticket panel %s", guild_panels["panel_id"], exc_info=True)

    def cog_unload(self):
        self.autoclose_loop.cancel()

    async def _refresh_panel(self, guild: discord.Guild, panel_id: str) -> None:
        panel = await tickets.get_panel(panel_id)
        if panel is None or not panel["channel_id"] or not panel["message_id"]:
            return
        channel = guild.get_channel(panel["channel_id"])
        if channel is None:
            return
        try:
            message = await channel.fetch_message(panel["message_id"])
            await message.edit(view=build_panel_view(panel))
        except discord.HTTPException:
            log.warning("Could not refresh ticket panel message %s", panel["message_id"], exc_info=True)

    async def _require_ticket(self, ctx: commands.Context, *, staff_only: bool = False) -> Optional[tuple[dict, Optional[dict]]]:
        ticket = await tickets.get_ticket_by_channel(ctx.channel.id)
        if ticket is None:
            await ctx.send(view=error_layout("Not a ticket", "Run this command inside an open ticket channel."))
            return None
        panel = await tickets.get_panel(ticket["panel_id"]) if ticket["panel_id"] else None
        staff = tickets.is_staff(ctx.author, panel)
        if staff_only and not staff:
            await ctx.send(view=error_layout("Staff only", "Only ticket staff can use this command."))
            return None
        if not staff and ctx.author.id != ticket["owner_id"]:
            await ctx.send(view=error_layout("Not allowed", "Only the ticket owner or staff can use this command."))
            return None
        return ticket, panel

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        channel_id = message.channel.id
        if channel_id not in self.open_channels:
            return
        now = time.monotonic()
        if now - self._last_touch.get(channel_id, 0.0) < _TOUCH_INTERVAL:
            return
        self._last_touch[channel_id] = now
        await tickets.touch(channel_id)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if channel.id not in self.open_channels or channel.id in self.closing:
            return
        ticket = await tickets.get_ticket_by_channel(channel.id)
        self.open_channels.discard(channel.id)
        if ticket is None:
            return
        await tickets.update_ticket(ticket["ticket_id"], status="closed", closed_at=time.time(), close_reason="Channel deleted")
        await _announce(self.bot, channel.guild, None, f"Ticket #{ticket['number']:04d} closed because its channel was deleted")

    @tasks.loop(minutes=config.TICKET_AUTOCLOSE_CHECK_MINUTES)
    async def autoclose_loop(self):
        for entry in await tickets.guilds_with_autoclose():
            guild = self.bot.get_guild(entry["guild_id"])
            if guild is None:
                continue
            for ticket in await tickets.stale_tickets(guild.id, entry["auto_close_hours"]):
                channel = guild.get_channel(ticket["channel_id"])
                reason = f"Closed automatically after {entry['auto_close_hours']} hour(s) of inactivity"
                try:
                    await close_ticket(self.bot, guild, channel, ticket, guild.me, reason)
                except Exception:
                    log.warning("Auto-close failed for ticket %s", ticket["ticket_id"], exc_info=True)

    @autoclose_loop.before_loop
    async def _before_autoclose(self):
        await self.bot.wait_until_ready()

    @commands.group(name="ticket", aliases=["tickets"], invoke_without_command=True, help="Support ticket system.")
    @commands.guild_only()
    async def ticket(self, ctx: commands.Context):
        e = emoji_manager.get
        body = (
            "**In a ticket:** `ticket close [reason]` · `claim` · `unclaim` · `add <member>` · `remove <member>` · "
            "`rename <name>` · `priority <level>` · `transcript` · `info`\n"
            "**Staff:** `ticket list` · `ticket stats`\n\n"
            "**Setup (Manage Server):** `ticket panel create|list|info|send|delete|staff|category|question|transcript|unique|label|text|subject` · "
            "`ticket log <#channel>` · `ticket limit <n>` · `ticket autoclose <hours|off>` · `ticket settings`"
        )
        await ctx.send(view=info_layout(f"{e('ticket')} Tickets", body))

    @ticket.command(name="close", help="Close this ticket and save a transcript.")
    @commands.guild_only()
    async def ticket_close(self, ctx: commands.Context, *, reason: Optional[str] = None):
        found = await self._require_ticket(ctx)
        if found is None:
            return
        ticket, _ = found
        await close_ticket(self.bot, ctx.guild, ctx.channel, ticket, ctx.author, reason)

    @ticket.command(name="claim", help="Claim this ticket.")
    @commands.guild_only()
    async def ticket_claim(self, ctx: commands.Context):
        found = await self._require_ticket(ctx, staff_only=True)
        if found is None:
            return
        await _do_claim(self.bot, ctx.guild, ctx.channel, found[0], ctx.author)

    @ticket.command(name="unclaim", aliases=["release"], help="Release your claim on this ticket.")
    @commands.guild_only()
    async def ticket_unclaim(self, ctx: commands.Context):
        e = emoji_manager.get
        found = await self._require_ticket(ctx, staff_only=True)
        if found is None:
            return
        ticket, panel = found
        if not ticket["claimed_by"]:
            return await ctx.send(view=error_layout("Not claimed", "This ticket has not been claimed."))
        if ticket["claimed_by"] != ctx.author.id and not ctx.author.guild_permissions.manage_guild:
            return await ctx.send(view=error_layout("Not yours", f"Only <@{ticket['claimed_by']}> or a server manager can release this claim."))
        await tickets.update_ticket(ticket["ticket_id"], claimed_by=None)
        await ctx.send(view=success_layout(f"{e('unlock')} Claim released", f"{ctx.author.mention} released this ticket."))
        await _announce(self.bot, ctx.guild, ctx.author.id, f"Released claim on ticket #{ticket['number']:04d}")

    @ticket.command(name="add", help="Add a member to this ticket.")
    @commands.guild_only()
    async def ticket_add(self, ctx: commands.Context, member: discord.Member):
        e = emoji_manager.get
        found = await self._require_ticket(ctx, staff_only=True)
        if found is None:
            return
        await ctx.channel.set_permissions(
            member,
            overwrite=discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            reason=f"[Soward Tickets] Added by {ctx.author}",
        )
        await ctx.send(view=success_layout(f"{e('check')} Member added", f"{member.mention} can now see this ticket."))
        await _announce(self.bot, ctx.guild, ctx.author.id, f"Added {member.mention} to ticket #{found[0]['number']:04d}")

    @ticket.command(name="remove", help="Remove a member from this ticket.")
    @commands.guild_only()
    async def ticket_remove(self, ctx: commands.Context, member: discord.Member):
        e = emoji_manager.get
        found = await self._require_ticket(ctx, staff_only=True)
        if found is None:
            return
        ticket = found[0]
        if member.id == ticket["owner_id"]:
            return await ctx.send(view=error_layout("Can't remove the owner", "The ticket owner can't be removed. Close the ticket instead."))
        await ctx.channel.set_permissions(member, overwrite=None, reason=f"[Soward Tickets] Removed by {ctx.author}")
        await ctx.send(view=success_layout(f"{e('check')} Member removed", f"{member.mention} no longer has access."))
        await _announce(self.bot, ctx.guild, ctx.author.id, f"Removed {member.mention} from ticket #{ticket['number']:04d}")

    @ticket.command(name="rename", help="Rename this ticket channel.")
    @commands.guild_only()
    async def ticket_rename(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        found = await self._require_ticket(ctx, staff_only=True)
        if found is None:
            return
        slug = _slug(name)
        if not slug:
            return await ctx.send(view=error_layout("Invalid name", "Use letters, numbers, dashes or underscores."))
        try:
            await ctx.channel.edit(name=slug, reason=f"[Soward Tickets] Renamed by {ctx.author}")
        except discord.HTTPException as exc:
            return await ctx.send(view=error_layout("Could not rename", str(exc)[:200]))
        await ctx.send(view=success_layout(f"{e('check')} Renamed", f"This ticket is now `{slug}`."))

    @ticket.command(name="priority", help="Set the ticket priority: low, normal, high or urgent.")
    @commands.guild_only()
    async def ticket_priority(self, ctx: commands.Context, level: str):
        e = emoji_manager.get
        found = await self._require_ticket(ctx, staff_only=True)
        if found is None:
            return
        level = level.lower()
        if level not in config.TICKET_PRIORITIES:
            return await ctx.send(view=error_layout("Invalid priority", "Choose one of: " + ", ".join(f"`{p}`" for p in config.TICKET_PRIORITIES)))
        await tickets.update_ticket(found[0]["ticket_id"], priority=level)
        await ctx.send(view=success_layout(f"{e('warning')} Priority set", f"This ticket is now **{level}** priority."))
        await _announce(self.bot, ctx.guild, ctx.author.id, f"Set ticket #{found[0]['number']:04d} priority to {level}")

    @ticket.command(name="transcript", help="Generate an HTML transcript of this ticket.")
    @commands.guild_only()
    async def ticket_transcript(self, ctx: commands.Context):
        e = emoji_manager.get
        found = await self._require_ticket(ctx, staff_only=True)
        if found is None:
            return
        data = await tickets.build_transcript(ctx.channel, f"Ticket #{found[0]['number']:04d}")
        name = tickets.transcript_name(ctx.channel.id)
        await ctx.send(
            view=_layout(f"{e('ticket')} Transcript", f"Transcript of ticket #{found[0]['number']:04d}.", attachment=name),
            file=tickets.transcript_file(data, ctx.channel.id),
        )

    @ticket.command(name="info", help="Show details about this ticket.")
    @commands.guild_only()
    async def ticket_info(self, ctx: commands.Context):
        e = emoji_manager.get
        found = await self._require_ticket(ctx)
        if found is None:
            return
        ticket, panel = found
        claimed = f"<@{ticket['claimed_by']}>" if ticket["claimed_by"] else "Nobody"
        lines = [
            f"**Ticket:** #{ticket['number']:04d}",
            f"**Owner:** <@{ticket['owner_id']}>",
            f"**Claimed by:** {claimed}",
            f"**Priority:** {ticket['priority']}",
            f"**Panel:** {panel['name'] if panel else 'Deleted panel'}",
            f"**Opened:** <t:{int(ticket['created_at'])}:R>",
        ]
        if ticket["subject"]:
            lines.append(f"**Subject:** {ticket['subject']}")
        await ctx.send(view=info_layout(f"{e('info')} Ticket Info", "\n".join(lines)))

    @ticket.group(name="panel", invoke_without_command=True, help="Manage ticket panels.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel(self, ctx: commands.Context):
        await self.panel_list(ctx)

    @panel.command(name="list", help="List this server's ticket panels.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_list(self, ctx: commands.Context):
        e = emoji_manager.get
        panels = await tickets.list_panels(ctx.guild.id)
        limit = await tickets.limit_for(ctx.guild.id, "panels")
        if not panels:
            return await ctx.send(view=info_layout(f"{e('ticket')} Ticket Panels", f"No panels yet (0/{limit}). Create one with `ticket panel create <name>`."))
        lines = [f"**Panels:** {len(panels)}/{limit}", ""]
        for p in panels:
            channel = ctx.guild.get_channel(p["channel_id"]) if p["channel_id"] else None
            state = f"posted in {channel.mention}" if channel else "not posted"
            roles = len(tickets.parse_ids(p["staff_role_ids"]))
            lines.append(f"`{p['panel_id']}` **{p['name']}** - {state} - {roles} staff role(s)")
        await ctx.send(view=info_layout(f"{e('ticket')} Ticket Panels", "\n".join(lines)))

    async def _limit_error(self, ctx: commands.Context, title: str, noun: str, key: str, limit: int) -> None:
        premium = await tickets.is_premium(ctx.guild.id)
        text = f"This server can have up to **{limit}** {noun}."
        if not premium:
            text += f" Soward Premium raises this to **{tickets.premium_limit(key)}**."
        await ctx.send(view=error_layout(title, text))

    @panel.command(name="create", help="Create a ticket panel.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_create(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        name = name.strip()[:60]
        if await tickets.find_panel(ctx.guild.id, name):
            return await ctx.send(view=error_layout("Name taken", "A panel with that name already exists."))
        limit = await tickets.limit_for(ctx.guild.id, "panels")
        if len(await tickets.list_panels(ctx.guild.id)) >= limit:
            return await self._limit_error(ctx, "Panel limit reached", "panels", "panels", limit)
        panel_id = await tickets.create_panel(ctx.guild.id, name)
        await ctx.send(
            view=success_layout(
                f"{e('check')} Panel created",
                f"**{name}** (`{panel_id}`). Add a staff role with `ticket panel staff {name} @role`, then post it with `ticket panel send {name} #channel`.",
            )
        )

    async def _panel_or_error(self, ctx: commands.Context, name: str) -> Optional[dict]:
        panel = await tickets.find_panel(ctx.guild.id, name)
        if panel is None:
            await ctx.send(view=error_layout("Panel not found", "Use `ticket panel list` to see your panels."))
        return panel

    @panel.command(name="send", help="Post a panel in a channel.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_send(self, ctx: commands.Context, name: str, channel: Optional[discord.TextChannel] = None):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        target = channel or ctx.channel
        if not tickets.parse_ids(panel["staff_role_ids"]):
            return await ctx.send(view=error_layout("No staff role", f"Add one first with `ticket panel staff {panel['name']} @role`."))
        if panel["channel_id"] and panel["message_id"]:
            old_channel = ctx.guild.get_channel(panel["channel_id"])
            if old_channel is not None:
                try:
                    old = await old_channel.fetch_message(panel["message_id"])
                    await old.delete()
                except discord.HTTPException:
                    pass
        try:
            message = await target.send(view=build_panel_view(panel))
        except discord.HTTPException as exc:
            return await ctx.send(view=error_layout("Could not post panel", str(exc)[:200]))
        await tickets.update_panel(panel["panel_id"], channel_id=target.id, message_id=message.id)
        await ctx.send(view=success_layout(f"{e('check')} Panel posted", f"**{panel['name']}** is live in {target.mention}."))

    @panel.command(name="delete", help="Delete a panel.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_delete(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        confirm = ConfirmLayout(
            f"{e('warning')} Delete panel?",
            f"**{panel['name']}** will stop working. Open tickets from this panel are not affected.",
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "The panel was kept."))
        if panel["channel_id"] and panel["message_id"]:
            channel = ctx.guild.get_channel(panel["channel_id"])
            if channel is not None:
                try:
                    old = await channel.fetch_message(panel["message_id"])
                    await old.delete()
                except discord.HTTPException:
                    pass
        await tickets.delete_panel(panel["panel_id"])
        await msg.edit(view=success_layout(f"{e('check')} Panel deleted", f"**{panel['name']}** was removed."))

    @panel.group(name="category", invoke_without_command=True, help="Show or manage the categories a panel creates tickets in.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_category(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        ids = tickets.parse_ids(panel["category_ids"])
        limit = await tickets.limit_for(ctx.guild.id, "categories")
        if not ids:
            body = f"No categories set (0/{limit}). Tickets are created at the top of the channel list.\nAdd one with `ticket panel category add {panel['name']} <category>`."
        else:
            lines = []
            for cid in ids:
                category = ctx.guild.get_channel(cid)
                lines.append(f"{category.name} ({len(category.channels)}/{config.TICKET_CATEGORY_CHANNEL_CAP})" if category else f"Deleted category `{cid}`")
            body = f"**Categories:** {len(ids)}/{limit}\n" + "\n".join(lines) + "\n\nNew tickets go to the category with the most room."
        await ctx.send(view=info_layout(f"{e('ticket')} {panel['name']} categories", body))

    @panel_category.command(name="add", help="Add a category for new tickets.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_category_add(self, ctx: commands.Context, name: str, category: discord.CategoryChannel):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        ids = tickets.parse_ids(panel["category_ids"])
        if category.id in ids:
            return await ctx.send(view=error_layout("Already added", "That category is already assigned to this panel."))
        limit = await tickets.limit_for(ctx.guild.id, "categories")
        if len(ids) >= limit:
            return await self._limit_error(ctx, "Category limit reached", "categories per panel", "categories", limit)
        ids.append(category.id)
        await tickets.update_panel(panel["panel_id"], category_ids=json.dumps(ids))
        await ctx.send(view=success_layout(f"{e('check')} Category added", f"**{category.name}** is now used by **{panel['name']}** ({len(ids)}/{limit})."))

    @panel_category.command(name="remove", help="Remove a category from a panel.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_category_remove(self, ctx: commands.Context, name: str, category: discord.CategoryChannel):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        ids = tickets.parse_ids(panel["category_ids"])
        if category.id not in ids:
            return await ctx.send(view=error_layout("Not assigned", "That category is not assigned to this panel."))
        ids.remove(category.id)
        await tickets.update_panel(panel["panel_id"], category_ids=json.dumps(ids))
        await ctx.send(view=success_layout(f"{e('check')} Category removed", f"**{category.name}** was removed from **{panel['name']}**."))

    async def _sync_staff_role(self, guild: discord.Guild, panel_id: str, role: discord.Role, add: bool) -> None:
        for ticket in await tickets.open_for_panel(panel_id):
            channel = guild.get_channel(ticket["channel_id"])
            if channel is None:
                continue
            try:
                if add:
                    await channel.set_permissions(
                        role,
                        overwrite=discord.PermissionOverwrite(
                            view_channel=True, send_messages=True, read_message_history=True,
                            attach_files=True, embed_links=True, manage_messages=True,
                        ),
                        reason="[Soward Tickets] Staff role added to panel",
                    )
                else:
                    await channel.set_permissions(role, overwrite=None, reason="[Soward Tickets] Staff role removed from panel")
            except discord.HTTPException:
                log.warning("Could not sync staff role %s on channel %s", role.id, channel.id, exc_info=True)

    @panel.command(name="staff", help="Add or remove a staff role for a panel (toggle).")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_staff(self, ctx: commands.Context, name: str, role: discord.Role):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        roles = tickets.parse_ids(panel["staff_role_ids"])
        adding = role.id not in roles
        limit = await tickets.limit_for(ctx.guild.id, "staff_roles")
        if adding:
            if len(roles) >= limit:
                return await self._limit_error(ctx, "Staff role limit reached", "staff roles per panel", "staff_roles", limit)
            roles.append(role.id)
        else:
            roles.remove(role.id)
        await tickets.update_panel(panel["panel_id"], staff_role_ids=json.dumps(roles))
        await self._sync_staff_role(ctx.guild, panel["panel_id"], role, adding)
        verb = "added to" if adding else "removed from"
        await ctx.send(view=success_layout(f"{e('check')} Staff updated", f"{role.mention} was {verb} **{panel['name']}** staff ({len(roles)}/{limit}). Open tickets were updated."))

    @panel.command(name="label", help="Set the panel button label.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_label(self, ctx: commands.Context, name: str, *, label: str):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        await tickets.update_panel(panel["panel_id"], button_label=label[:80])
        await self._refresh_panel(ctx.guild, panel["panel_id"])
        await ctx.send(view=success_layout(f"{e('check')} Label updated", f"The button now reads **{label[:80]}**."))

    @panel.command(name="text", help="Set the panel description and ticket welcome text (or 'reset').")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_text(self, ctx: commands.Context, name: str, *, text: str):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        value = None if text.lower() in {"reset", "none", "off"} else text[:1000]
        await tickets.update_panel(panel["panel_id"], welcome_text=value)
        await self._refresh_panel(ctx.guild, panel["panel_id"])
        await ctx.send(view=success_layout(f"{e('check')} Text updated", "Panel text saved." if value else "Panel text reset to the default."))

    @panel.command(name="subject", help="Ask for a subject when opening a ticket (on/off).")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_subject(self, ctx: commands.Context, name: str, state: bool):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        await tickets.update_panel(panel["panel_id"], ask_subject=int(state))
        await ctx.send(view=success_layout(f"{e('check')} Subject prompt {'enabled' if state else 'disabled'}", f"**{panel['name']}** updated."))

    @panel.group(name="question", invoke_without_command=True, help="Show or manage intake form questions for a panel.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_question(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        questions = tickets.parse_list(panel["questions"])
        limit = await tickets.limit_for(ctx.guild.id, "questions")
        if not questions:
            body = f"No questions (0/{limit}). Add one with `ticket panel question add {panel['name']} <question>`."
        else:
            body = f"**Questions:** {len(questions)}/{limit}\n" + "\n".join(f"`{i}.` {q}" for i, q in enumerate(questions, 1))
        await ctx.send(view=info_layout(f"{e('ticket')} {panel['name']} form", body))

    @panel_question.command(name="add", help="Add an intake question.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_question_add(self, ctx: commands.Context, name: str, *, question: str):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        questions = tickets.parse_list(panel["questions"])
        limit = await tickets.limit_for(ctx.guild.id, "questions")
        if len(questions) >= limit:
            return await self._limit_error(ctx, "Question limit reached", "intake questions per panel", "questions", limit)
        questions.append(question.strip()[:45])
        await tickets.update_panel(panel["panel_id"], questions=json.dumps(questions))
        await ctx.send(view=success_layout(f"{e('check')} Question added", f"Question {len(questions)}/{limit} saved. Forms show 5 questions per page."))

    @panel_question.command(name="remove", help="Remove an intake question by number.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_question_remove(self, ctx: commands.Context, name: str, number: int):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        questions = tickets.parse_list(panel["questions"])
        if not 1 <= number <= len(questions):
            return await ctx.send(view=error_layout("No such question", "No question exists at that position."))
        removed = questions.pop(number - 1)
        await tickets.update_panel(panel["panel_id"], questions=json.dumps(questions))
        await ctx.send(view=success_layout(f"{e('check')} Question removed", f"Removed: {removed}"))

    @panel.command(name="transcript", help="Set where this panel's transcripts go (or 'reset').")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_transcript(self, ctx: commands.Context, name: str, channel: typing.Union[discord.TextChannel, str]):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        if isinstance(channel, str):
            if channel.lower() not in {"reset", "none", "off"}:
                return await ctx.send(view=error_layout("Invalid channel", "Mention a text channel, or use `reset`."))
            await tickets.update_panel(panel["panel_id"], transcript_channel_id=None)
            return await ctx.send(view=success_layout(f"{e('check')} Transcript channel cleared", "This panel now uses the server's ticket log channel."))
        await tickets.update_panel(panel["panel_id"], transcript_channel_id=channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Transcript channel set", f"Transcripts for **{panel['name']}** go to {channel.mention}."))

    @panel.command(name="unique", help="Allow only one open ticket per member on this panel (on/off).")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_unique(self, ctx: commands.Context, name: str, state: bool):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        await tickets.update_panel(panel["panel_id"], one_per_user=int(state))
        await ctx.send(view=success_layout(f"{e('check')} One-per-member {'enabled' if state else 'disabled'}", f"**{panel['name']}** updated."))

    @panel.command(name="info", help="Show everything about a panel.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def panel_info(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        panel = await self._panel_or_error(ctx, name)
        if panel is None:
            return
        roles = tickets.parse_ids(panel["staff_role_ids"])
        categories = tickets.parse_ids(panel["category_ids"])
        questions = tickets.parse_list(panel["questions"])
        channel = ctx.guild.get_channel(panel["channel_id"]) if panel["channel_id"] else None
        transcript = ctx.guild.get_channel(panel["transcript_channel_id"]) if panel["transcript_channel_id"] else None
        role_limit = await tickets.limit_for(ctx.guild.id, "staff_roles")
        cat_limit = await tickets.limit_for(ctx.guild.id, "categories")
        q_limit = await tickets.limit_for(ctx.guild.id, "questions")
        body = (
            f"**ID:** `{panel['panel_id']}`\n"
            f"**Posted in:** {channel.mention if channel else 'not posted'}\n"
            f"**Button:** {panel['button_label']}\n"
            f"**Staff roles ({len(roles)}/{role_limit}):** {' '.join(f'<@&{r}>' for r in roles) or 'none'}\n"
            f"**Categories ({len(categories)}/{cat_limit}):** {len(categories)}\n"
            f"**Questions ({len(questions)}/{q_limit}):** {len(questions)}\n"
            f"**Subject prompt:** {'on' if panel['ask_subject'] else 'off'}\n"
            f"**One open ticket per member:** {'yes' if panel['one_per_user'] else 'no'}\n"
            f"**Transcripts:** {transcript.mention if transcript else 'server log channel'}"
        )
        await ctx.send(view=info_layout(f"{e('ticket')} {panel['name']}", body))

    @ticket.command(name="log", help="Set the ticket log and transcript channel (or 'reset').")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def ticket_log(self, ctx: commands.Context, channel: typing.Union[discord.TextChannel, str]):
        e = emoji_manager.get
        if isinstance(channel, str):
            if channel.lower() not in {"reset", "none", "off"}:
                return await ctx.send(view=error_layout("Invalid channel", "Mention a text channel, or use `reset`."))
            await tickets.update_settings(ctx.guild.id, log_channel_id=None)
            return await ctx.send(view=success_layout(f"{e('check')} Log channel cleared", "Transcripts will only be sent to the ticket owner."))
        await tickets.update_settings(ctx.guild.id, log_channel_id=channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Log channel set", f"Ticket logs and transcripts go to {channel.mention}."))

    @ticket.command(name="limit", help="Set how many tickets a member can have open.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def ticket_limit(self, ctx: commands.Context, amount: int):
        e = emoji_manager.get
        if not 1 <= amount <= config.TICKET_MAX_OPEN_LIMIT:
            return await ctx.send(view=error_layout("Invalid limit", f"Choose a number from 1 to {config.TICKET_MAX_OPEN_LIMIT}."))
        await tickets.update_settings(ctx.guild.id, max_open=amount)
        await ctx.send(view=success_layout(f"{e('check')} Limit set", f"Members can have **{amount}** open ticket(s) at once."))

    @ticket.command(name="autoclose", help="Close inactive tickets after N hours (or 'off').")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def ticket_autoclose(self, ctx: commands.Context, hours: typing.Union[int, str]):
        e = emoji_manager.get
        if isinstance(hours, str):
            if hours.lower() not in {"off", "none", "disable", "reset"}:
                return await ctx.send(view=error_layout("Invalid value", "Use a number of hours, or `off`."))
            hours = 0
        if hours < 0 or hours > 24 * 30:
            return await ctx.send(view=error_layout("Invalid value", "Choose between 1 and 720 hours, or `off`."))
        await tickets.update_settings(ctx.guild.id, auto_close_hours=hours)
        text = f"Inactive tickets close after **{hours}** hour(s)." if hours else "Auto-close is off."
        await ctx.send(view=success_layout(f"{e('check')} Auto-close updated", text))

    @ticket.command(name="settings", help="Show ticket settings.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def ticket_settings(self, ctx: commands.Context):
        e = emoji_manager.get
        settings = await tickets.get_settings(ctx.guild.id)
        log_channel = ctx.guild.get_channel(settings["log_channel_id"]) if settings["log_channel_id"] else None
        panels = await tickets.list_panels(ctx.guild.id)
        premium = await tickets.is_premium(ctx.guild.id)
        tier = config.TICKET_LIMITS["premium" if premium else "free"]
        auto = f"{settings['auto_close_hours']}h" if settings["auto_close_hours"] else "off"
        body = (
            f"**Plan:** {'Premium' if premium else 'Free'}\n"
            f"**Log channel:** {log_channel.mention if log_channel else 'not set'}\n"
            f"**Open ticket limit per member:** {settings['max_open']}\n"
            f"**Auto-close:** {auto}\n"
            f"**Panels:** {len(panels)}/{tier['panels']}\n"
            f"**Staff roles per panel:** up to {tier['staff_roles']}\n"
            f"**Categories per panel:** up to {tier['categories']}\n"
            f"**Questions per panel:** up to {tier['questions']}\n"
            f"**Open tickets (server):** {await tickets.active_count(ctx.guild.id)}/{tier['active']}\n"
            f"**Tickets opened so far:** {settings['counter']}"
        )
        await ctx.send(view=info_layout(f"{e('settings')} Ticket Settings", body))

    @ticket.command(name="list", help="List open tickets in this server.")
    @commands.guild_only()
    async def ticket_list(self, ctx: commands.Context):
        e = emoji_manager.get
        if not tickets.is_staff(ctx.author, None):
            return await ctx.send(view=error_layout("Staff only", "You need Manage Channels or Manage Server to list tickets."))
        open_tickets = await tickets.list_open(ctx.guild.id, config.TICKET_LIST_LIMIT)
        if not open_tickets:
            return await ctx.send(view=info_layout(f"{e('ticket')} Open Tickets", "There are no open tickets."))
        lines = []
        for t in open_tickets:
            channel = ctx.guild.get_channel(t["channel_id"])
            claimed = f"<@{t['claimed_by']}>" if t["claimed_by"] else "unclaimed"
            lines.append(f"{channel.mention if channel else '#deleted'} - <@{t['owner_id']}> - {t['priority']} - {claimed} - <t:{int(t['created_at'])}:R>")
        total = await tickets.active_count(ctx.guild.id)
        extra = f"\n\nShowing {len(open_tickets)} of {total}." if total > len(open_tickets) else ""
        await ctx.send(view=info_layout(f"{e('ticket')} Open Tickets", "\n".join(lines) + extra))

    @ticket.command(name="stats", help="Show ticket statistics for this server.")
    @commands.guild_only()
    async def ticket_stats(self, ctx: commands.Context):
        e = emoji_manager.get
        if not tickets.is_staff(ctx.author, None):
            return await ctx.send(view=error_layout("Staff only", "You need Manage Channels or Manage Server to view stats."))
        data = await tickets.stats(ctx.guild.id)
        limit = await tickets.limit_for(ctx.guild.id, "active")
        top = "\n".join(f"<@{uid}> - {n} claimed" for uid, n in data["top"]) or "No claimed tickets yet."
        body = (
            f"**Total:** {data['total']}\n**Open:** {data['open']}/{limit}\n**Closed:** {data['closed']}\n**Ever claimed:** {data['claimed']}\n\n"
            f"**Top staff**\n{top}"
        )
        await ctx.send(view=info_layout(f"{e('ticket')} Ticket Stats", body))


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
