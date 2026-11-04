import datetime
import time
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from utils import cases, db, emoji_manager, slash_sync, warn_ladder
from utils import reports as store
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import LOG_EVENT, MOD_ACTION, bus

NO_MENTIONS = discord.AllowedMentions.none()
MENU_VERSION = "reports-menu-1"
COOLDOWN = 20.0
STATUS_COLORS = {"open": 0xFEE75C, "actioned": 0xED4245, "dismissed": 0x95A5A6}


def _clip(text: str, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def can_handle(member: discord.Member, act: str) -> bool:
    perms = member.guild_permissions
    if perms.administrator:
        return True
    if act == "ban":
        return perms.ban_members
    if act == "timeout":
        return perms.moderate_members
    return perms.manage_messages or perms.moderate_members or perms.kick_members or perms.ban_members


def review_layout(guild: discord.Guild, report: dict, history: dict, ping: str = "", repeated: bool = False) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    if ping:
        view.add_item(discord.ui.TextDisplay(ping))
    status = report["status"]
    container = discord.ui.Container(accent_color=STATUS_COLORS.get(status, 0xFEE75C))
    head = [f"## Report #{report['report_id']}" + ("  ·  repeated reports" if repeated else ""),
            f"**Reported:** <@{report['target_id']}> (`{report['target_id']}`)",
            f"**Reported by:** <@{report['reporter_id']}>" if report["source"] == "message" else f"**Source:** {report['source']} · <@{report['reporter_id']}>",
            f"**Reason:** {_clip(report['reason'], 400)}"]
    if report.get("channel_id") and report.get("message_id"):
        head.append(f"**Message:** https://discord.com/channels/{guild.id}/{report['channel_id']}/{report['message_id']}")
    head.append(f"**This member:** {history['open']} open · {history['total']} report(s) in 30 days from {history['reporters']} member(s)")
    container.add_item(discord.ui.TextDisplay("\n".join(head)))
    container.add_item(discord.ui.Separator())
    shown = _clip(report.get("content") or "(no text)", 700)
    if report["attachments"]:
        shown += "\n" + "\n".join(f"-# attachment: {_clip(a, 120)}" for a in report["attachments"][:4])
    container.add_item(discord.ui.TextDisplay(f"**Reported message**\n{shown}"))
    if report["context"]:
        lines = []
        for item in report["context"][:9]:
            marker = "**»**" if item.get("id") == report.get("message_id") else "-"
            lines.append(f"{marker} <@{item.get('author')}>: {_clip(item.get('content') or '(attachment or embed)', 130)}")
        container.add_item(discord.ui.TextDisplay("**Context**\n" + "\n".join(lines)))
    container.add_item(discord.ui.Separator())
    if status == "open":
        container.add_item(discord.ui.TextDisplay("**Status:** Open"))
        first = discord.ui.ActionRow()
        for label, key, style in (("Warn", "warn", discord.ButtonStyle.primary), ("Timeout 1h", "timeout", discord.ButtonStyle.secondary),
                                  ("Ban", "ban", discord.ButtonStyle.danger), ("Dismiss", "dismiss", discord.ButtonStyle.secondary)):
            first.add_item(discord.ui.Button(label=label, style=style, custom_id=f"report:{key}:{report['report_id']}"))
        container.add_item(first)
        second = discord.ui.ActionRow()
        second.add_item(discord.ui.Button(label="Delete message", style=discord.ButtonStyle.secondary, custom_id=f"report:delete:{report['report_id']}"))
        if not report.get("thread_id"):
            second.add_item(discord.ui.Button(label="Discuss in thread", style=discord.ButtonStyle.secondary, custom_id=f"report:thread:{report['report_id']}"))
        container.add_item(second)
    else:
        who = f" by <@{report['handler_id']}>" if report.get("handler_id") else ""
        when = f" <t:{int(report['handled_at'])}:R>" if report.get("handled_at") else ""
        container.add_item(discord.ui.TextDisplay(f"**Status:** {store.OUTCOMES.get(report.get('outcome'), report.get('outcome') or status)}{who}{when}"))
    if report.get("thread_id"):
        container.add_item(discord.ui.TextDisplay(f"-# Discussion: <#{report['thread_id']}>"))
    view.add_item(container)
    return view


class ReportModal(discord.ui.Modal, title="Report message"):
    reason = discord.ui.TextInput(label="What is wrong with it?", style=discord.TextStyle.paragraph, min_length=5, max_length=500)

    def __init__(self, cog: "Reports", message: discord.Message):
        super().__init__(timeout=300)
        self.cog = cog
        self.message = message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        ok, text = await self.cog.report_message(interaction.guild, interaction.user, self.message, str(self.reason.value))
        await interaction.followup.send(text, ephemeral=True)


class Reports(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.last: dict[tuple[int, int], float] = {}
        self.menu = app_commands.ContextMenu(name="Report message", callback=self.report_menu)
        self.menu.guild_only = True
        self.synced = False

    async def cog_load(self):
        self.bot.tree.add_command(self.menu)

    async def cog_unload(self):
        self.bot.tree.remove_command(self.menu.name, type=self.menu.type)

    @commands.Cog.listener()
    async def on_ready(self):
        if self.synced:
            return
        self.synced = True
        if await db.get("reports", "menu_version") == MENU_VERSION:
            return
        try:
            await slash_sync.sync(self.bot)
        except discord.HTTPException:
            self.synced = False
            return
        await db.set("reports", "menu_version", MENU_VERSION)

    async def report_menu(self, interaction: discord.Interaction, message: discord.Message):
        if interaction.guild is None:
            return await interaction.response.send_message("Reports only work inside a server.", ephemeral=True)
        cfg = await store.get_config(interaction.guild.id)
        if not cfg["enabled"] or not cfg["channel"]:
            return await interaction.response.send_message("Reports are not set up in this server.", ephemeral=True)
        problem = self._problem(interaction.guild, interaction.user, message)
        if problem:
            return await interaction.response.send_message(problem, ephemeral=True)
        await interaction.response.send_modal(ReportModal(self, message))

    def _problem(self, guild: discord.Guild, reporter, message: discord.Message) -> Optional[str]:
        if message.author.id == reporter.id:
            return "You cannot report your own message."
        if message.author.bot:
            return "Bots cannot be reported. Contact staff directly if a bot is misbehaving."
        wait = COOLDOWN - (time.monotonic() - self.last.get((guild.id, reporter.id), -COOLDOWN))
        if wait > 0:
            return f"Please wait {wait:.0f}s before sending another report."
        return None

    async def _context(self, message: discord.Message) -> list[dict]:
        found: list[discord.Message] = []
        try:
            async for item in message.channel.history(limit=6, before=message):
                found.append(item)
            found.reverse()
            found.append(message)
            async for item in message.channel.history(limit=3, after=message, oldest_first=True):
                found.append(item)
        except (discord.HTTPException, AttributeError):
            found = [message]
        return [{"id": m.id, "author": m.author.id, "content": _clip(m.content, 300), "at": int(m.created_at.timestamp())} for m in found]

    async def report_message(self, guild: discord.Guild, reporter, message: discord.Message, reason: str) -> tuple[bool, str]:
        cfg = await store.get_config(guild.id)
        if not cfg["enabled"] or not cfg["channel"]:
            return False, "Reports are not set up in this server."
        problem = self._problem(guild, reporter, message)
        if problem:
            return False, problem
        if await store.duplicate(guild.id, reporter.id, message.id):
            return False, "You already reported this message. Staff will look at it."
        if await store.reporter_today(guild.id, reporter.id) >= cfg["daily"]:
            return False, "You have reached today's report limit. Contact staff directly if it is urgent."
        self.last[(guild.id, reporter.id)] = time.monotonic()
        attachments = [a.url for a in message.attachments]
        report_id = await store.create(
            guild.id, reporter.id, message.author.id, reason, channel_id=message.channel.id, message_id=message.id,
            content=message.content, attachments=attachments, context=await self._context(message),
        )
        await self._publish(guild, report_id)
        return True, f"Report **#{report_id}** was sent to the staff. The reported member is not told who reported them."

    async def report_manual(self, guild: discord.Guild, reporter_id: int, target_id: int, reason: str, source: str, context: Optional[list] = None) -> Optional[str]:
        cfg = await store.get_config(guild.id)
        if not cfg["enabled"] or not cfg["channel"]:
            return None
        report_id = await store.create(
            guild.id, reporter_id, target_id, reason, channel_id=None, message_id=None, content="", attachments=[], context=context or [], source=source)
        await self._publish(guild, report_id)
        return report_id

    async def _publish(self, guild: discord.Guild, report_id: str) -> None:
        cfg = await store.get_config(guild.id)
        report = await store.get(guild.id, report_id)
        channel = guild.get_channel(int(cfg["channel"])) if cfg["channel"] else None
        if report is None or channel is None:
            return
        history = await store.against(guild.id, report["target_id"], time.time() - 30 * 86400)
        day = await store.against(guild.id, report["target_id"], time.time() - 86400)
        repeated = day["reporters"] >= cfg["threshold"]
        role = guild.get_role(int(cfg["role"])) if cfg["role"] else None
        ping = role.mention if role and (repeated or day["total"] == 1) else ""
        try:
            message = await channel.send(
                view=review_layout(guild, report, history, ping, repeated),
                allowed_mentions=discord.AllowedMentions(roles=[role]) if role else NO_MENTIONS,
            )
        except discord.HTTPException:
            return
        await store.remember_review(report_id, channel.id, message.id)
        if repeated and day["reporters"] == cfg["threshold"]:
            await bus.publish(
                LOG_EVENT, guild_id=guild.id, action="security_change", actor_id=None,
                detail=f"Repeated reports: <@{report['target_id']}> was reported by {day['reporters']} different members in 24 hours.",
            )

    async def _refresh(self, guild: discord.Guild, report: dict) -> None:
        if not report.get("review_channel_id") or not report.get("review_message_id"):
            return
        channel = guild.get_channel(report["review_channel_id"])
        if channel is None:
            return
        cfg = await store.get_config(guild.id)
        history = await store.against(guild.id, report["target_id"], time.time() - 30 * 86400)
        day = await store.against(guild.id, report["target_id"], time.time() - 86400)
        try:
            message = await channel.fetch_message(report["review_message_id"])
            await message.edit(view=review_layout(guild, report, history, "", day["reporters"] >= cfg["threshold"]), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass

    async def handle(self, guild: discord.Guild, report_id: str, act: str, handler: discord.Member) -> tuple[bool, str]:
        report = await store.get(guild.id, report_id)
        if report is None:
            return False, "That report no longer exists."
        if act == "thread":
            return await self._thread(guild, report)
        if report["status"] != "open":
            return False, "This report was already handled."
        if not isinstance(handler, discord.Member) or not can_handle(handler, act):
            return False, "You do not have the permission this action needs."
        member = guild.get_member(report["target_id"])
        reason = f"Report {report['report_id']}: {_clip(report['reason'], 200)}"
        outcome = {"warn": "warned", "timeout": "timeout", "ban": "banned", "dismiss": "dismissed", "delete": "deleted"}.get(act)
        if outcome is None:
            return False, "Unknown action."
        if act in ("warn", "timeout") and member is None:
            return False, "That member is no longer in the server."
        if act in ("warn", "timeout", "ban") and member is not None and (member.top_role >= handler.top_role and handler.id != guild.owner_id or member.top_role >= guild.me.top_role):
            return False, "You cannot take action against someone with a higher or equal role."
        if act == "warn":
            case_id = await cases.create_warn(guild.id, member.id, handler.id, reason)
            await bus.publish(LOG_EVENT, guild_id=guild.id, action="warn", user_id=member.id, moderator_id=handler.id, reason=reason, case_id=case_id)
            await warn_ladder.apply(guild, member)
            try:
                await member.send(view=error_layout("You were warned", f"A moderator in **{guild.name}** warned you after a report.\n**Reason:** {_clip(report['reason'], 300)}"))
            except discord.HTTPException:
                pass
        elif act == "timeout":
            try:
                await member.timeout(discord.utils.utcnow() + datetime.timedelta(hours=1), reason=reason)
            except discord.HTTPException:
                return False, "I could not time them out. Check my permissions."
            case_id = await cases.create_mod_case(guild.id, "mute", member.id, handler.id, reason, 3600)
            await bus.publish(LOG_EVENT, guild_id=guild.id, action="mute", user_id=member.id, moderator_id=handler.id, reason=reason, duration=3600, case_id=case_id)
        elif act == "ban":
            appeals = self.bot.get_cog("Appeals")
            target = member or await self._fetch_user(report["target_id"])
            if appeals is not None and target is not None:
                await appeals.notify_ban(guild, target, _clip(report["reason"], 200), clean=True)
            try:
                await guild.ban(discord.Object(id=report["target_id"]), reason=f"{handler} | {reason}", delete_message_days=0)
            except discord.HTTPException:
                return False, "I could not ban them. Check my permissions and role position."
            case_id = await cases.create_mod_case(guild.id, "ban", report["target_id"], handler.id, reason)
            await bus.publish(LOG_EVENT, guild_id=guild.id, action="ban", user_id=report["target_id"], moderator_id=handler.id, reason=reason, case_id=case_id)
        elif act == "delete":
            channel = guild.get_channel(report["channel_id"]) if report.get("channel_id") else None
            if channel is None or not report.get("message_id"):
                return False, "The reported message is not available."
            try:
                await channel.get_partial_message(report["message_id"]).delete()
            except discord.NotFound:
                pass
            except discord.HTTPException:
                return False, "I could not delete that message."
        await bus.publish(MOD_ACTION, guild_id=guild.id, action=f"report_{act}", user_id=report["target_id"], moderator_id=handler.id, reason=reason)
        status = "dismissed" if act == "dismiss" else "actioned"
        await store.resolve(report["report_id"], status, outcome, handler.id)
        report = await store.get(guild.id, report["report_id"])
        await self._refresh(guild, report)
        await self._thank(guild, report)
        return True, f"Report #{report['report_id']}: {store.OUTCOMES[outcome].lower()}."

    async def _fetch_user(self, user_id: int):
        try:
            return await self.bot.fetch_user(user_id)
        except discord.HTTPException:
            return None

    async def _thank(self, guild: discord.Guild, report: dict) -> None:
        cfg = await store.get_config(guild.id)
        if not cfg["notify"] or report["source"] != "message":
            return
        user = await self._fetch_user(report["reporter_id"])
        if user is None:
            return
        taken = report["outcome"] in store.UPHELD
        body = "Staff reviewed your report and took action. Thank you for helping keep the server safe." if taken else "Staff reviewed your report and did not find a reason to act. Thank you for letting them know."
        try:
            await user.send(view=info_layout(f"Your report in {guild.name}", body))
        except discord.HTTPException:
            pass

    async def _thread(self, guild: discord.Guild, report: dict) -> tuple[bool, str]:
        if report.get("thread_id"):
            return True, f"A thread already exists: <#{report['thread_id']}>"
        channel = guild.get_channel(report["review_channel_id"]) if report.get("review_channel_id") else None
        if channel is None or not report.get("review_message_id"):
            return False, "The review message is not available."
        try:
            message = await channel.fetch_message(report["review_message_id"])
            thread = await message.create_thread(name=f"Report {report['report_id']}", auto_archive_duration=1440)
        except discord.HTTPException:
            return False, "I could not create a thread. I need Create Public Threads there."
        await store.remember_thread(report["report_id"], thread.id)
        report["thread_id"] = thread.id
        await self._refresh(guild, report)
        return True, f"Thread created: {thread.mention}"

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if not custom_id.startswith("report:"):
            return
        parts = custom_id.split(":", 2)
        if len(parts) != 3:
            return
        member = interaction.user
        if not isinstance(member, discord.Member) or not can_handle(member, parts[1]):
            return await interaction.response.send_message("You need moderator permissions to handle reports.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ok, message = await self.handle(interaction.guild, parts[2], parts[1], member)
        await interaction.followup.send(message, ephemeral=True)

    @commands.group(name="report", invoke_without_command=True, help="Report a message to staff. Reply to it with `report <reason>`, or give its link.")
    @commands.guild_only()
    async def report(self, ctx: commands.Context, message: Optional[discord.Message] = None, *, reason: str = ""):
        if message is None and ctx.message.reference and ctx.message.reference.message_id:
            try:
                message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
            except discord.HTTPException:
                message = None
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        if message is None:
            return await ctx.send(view=error_layout("Which message?", "Reply to the message with `report <reason>`, or use `report <message link> <reason>`. You can also right-click a message, choose Apps, then Report message."), delete_after=15)
        if len(reason.strip()) < 5:
            return await ctx.send(view=error_layout("Add a reason", "Say what is wrong with it, at least a few words."), delete_after=15)
        ok, text = await self.report_message(ctx.guild, ctx.author, message, reason.strip())
        try:
            await ctx.author.send(text)
        except discord.HTTPException:
            await ctx.send(f"{ctx.author.mention} {text}", delete_after=10)

    @report.command(name="channel", help="Set where reports are posted for staff.")
    @has_guild_permission("manage_guild")
    async def report_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await self._set(ctx, "channel", channel.id, f"Reports are posted in {channel.mention}.")

    @report.command(name="role", help="Role pinged for new reports, or leave empty to clear.")
    @has_guild_permission("manage_guild")
    async def report_role(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        await self._set(ctx, "role", role.id if role else None, f"New reports ping {role.mention}." if role else "New reports no longer ping a role.")

    @report.command(name="on", help="Turn reports on.")
    @has_guild_permission("manage_guild")
    async def report_on(self, ctx: commands.Context):
        await self._set(ctx, "enabled", True, "Reports are **on**.")

    @report.command(name="off", help="Turn reports off.")
    @has_guild_permission("manage_guild")
    async def report_off(self, ctx: commands.Context):
        await self._set(ctx, "enabled", False, "Reports are **off**.")

    @report.command(name="alert", help="How many different members must report someone in 24 hours to flag it as repeated.")
    @has_guild_permission("manage_guild")
    async def report_alert(self, ctx: commands.Context, amount: int):
        if not 2 <= amount <= 20:
            return await ctx.send(view=error_layout("Invalid number", "Use 2 to 20."))
        await self._set(ctx, "threshold", amount, f"A member is flagged after reports from **{amount}** different people in 24 hours.")

    @report.command(name="limit", help="Reports one member can send per day.")
    @has_guild_permission("manage_guild")
    async def report_limit(self, ctx: commands.Context, amount: int):
        if not 1 <= amount <= 100:
            return await ctx.send(view=error_layout("Invalid number", "Use 1 to 100."))
        await self._set(ctx, "daily", amount, f"Members can send **{amount}** report(s) per day.")

    @report.command(name="notify", help="Tell reporters when staff handled their report.")
    @has_guild_permission("manage_guild")
    async def report_notify(self, ctx: commands.Context, toggle: bool):
        await self._set(ctx, "notify", toggle, f"Reporters are {'told' if toggle else 'not told'} when their report is handled.")

    async def _set(self, ctx: commands.Context, name: str, value, text: str):
        e = emoji_manager.get
        await store.set_config(ctx.guild.id, name, value)
        await ctx.send(view=success_layout(f"{e('check')} Reports", text))

    @report.command(name="list", help="List reports. Usage: report list [open|actioned|dismissed|all]")
    @has_guild_permission("manage_messages")
    async def report_list(self, ctx: commands.Context, status: str = "open"):
        rows = await store.listing(ctx.guild.id, None if status == "all" else status.lower())
        if not rows:
            return await ctx.send(view=info_layout("Reports", "No reports found."))
        lines = [f"`{r['report_id']}` <@{r['target_id']}> · {store.OUTCOMES.get(r['outcome'], r['status'])} · <t:{int(r['created_at'])}:R>" for r in rows]
        await ctx.send(view=info_layout(f"Reports · {status}", "\n".join(lines)[:3500]), allowed_mentions=NO_MENTIONS)

    @report.command(name="view", help="Show a report with its context.")
    @has_guild_permission("manage_messages")
    async def report_view(self, ctx: commands.Context, report_id: str):
        report = await store.get(ctx.guild.id, report_id)
        if report is None:
            return await ctx.send(view=error_layout("Not found", "No report with that id."))
        history = await store.against(ctx.guild.id, report["target_id"], time.time() - 30 * 86400)
        await ctx.send(view=review_layout(ctx.guild, report, history), allowed_mentions=NO_MENTIONS)

    @report.command(name="about", help="Show every report against a member.")
    @has_guild_permission("manage_messages")
    async def report_about(self, ctx: commands.Context, member: discord.Member):
        counts = await store.received_counts(ctx.guild.id, member.id)
        rows = await db.raw_fetch("SELECT report_id, status, outcome, created_at FROM message_reports WHERE guild_id=? AND target_id=? ORDER BY created_at DESC LIMIT 15", (ctx.guild.id, member.id))
        lines = [f"`{r['report_id']}` · {store.OUTCOMES.get(r['outcome'], r['status'])} · <t:{int(r['created_at'])}:R>" for r in rows]
        head = f"**Open:** {counts['open']} · **Acted on:** {counts['upheld']} · **Dismissed:** {counts['dismissed']}"
        await ctx.send(view=info_layout(f"Reports about {member.display_name}", head + "\n" + ("\n".join(lines) or "No reports.")))


async def setup(bot: commands.Bot):
    await bot.add_cog(Reports(bot))
