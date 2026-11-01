import time
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import appeals as store
from utils import cases, db, emoji_manager
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import LOG_EVENT, bus

NO_MENTIONS = discord.AllowedMentions.none()
STATUS_COLORS = {"accepted": 0x57F287, "denied": 0xED4245, "withdrawn": 0x95A5A6}
NOTICE_WINDOW = 120.0


def _clip(text: str, limit: int) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def is_reviewer(member: discord.Member) -> bool:
    perms = member.guild_permissions
    return perms.administrator or perms.ban_members or perms.manage_guild or member.id in config.ALL_PRIVILEGED_IDS


def notice_layout(guild: discord.Guild, reason: str, until: Optional[float], notice: str, url: str) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=0xED4245)
    lines = [f"## You were banned from {guild.name}"]
    if reason:
        lines.append(f"**Reason:** {_clip(reason, 300)}")
    if until:
        lines.append(f"**Your ban ends:** <t:{int(until)}:F> (<t:{int(until)}:R>)")
    if notice:
        lines.append(_clip(notice, 600))
    if url:
        lines.append("If you think this was a mistake or you have changed, you can appeal. You will need to sign in with Discord so staff know the appeal is really from you.")
    container.add_item(discord.ui.TextDisplay("\n".join(lines)))
    if url:
        row = discord.ui.ActionRow()
        row.add_item(discord.ui.Button(label="Appeal this ban", style=discord.ButtonStyle.link, url=url))
        container.add_item(row)
    view.add_item(container)
    return view


def review_layout(guild: discord.Guild, appeal: dict, cfg: dict, counts: tuple[int, int], ping: str = "") -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    if ping:
        view.add_item(discord.ui.TextDisplay(ping))
    status = appeal["status"]
    container = discord.ui.Container(accent_color=STATUS_COLORS.get(status, 0xFEE75C))
    header = [
        f"## Ban appeal #{appeal['appeal_id']}",
        f"**User:** <@{appeal['user_id']}> (`{appeal['user_id']}`) · {appeal.get('user_name') or 'unknown'}",
        f"**Submitted:** <t:{int(appeal['created_at'])}:R>",
    ]
    if appeal.get("ban_reason"):
        header.append(f"**Ban reason:** {_clip(appeal['ban_reason'], 300)}")
    container.add_item(discord.ui.TextDisplay("\n".join(header)))
    container.add_item(discord.ui.Separator())
    budget = max(120, 3200 // max(1, len(appeal["answers"])))
    body = [f"**{n}. {_clip(item.get('q', ''), 140)}**\n{_clip(item.get('a', ''), budget)}" for n, item in enumerate(appeal["answers"], 1)]
    container.add_item(discord.ui.TextDisplay("\n\n".join(body) or "No answers."))
    container.add_item(discord.ui.Separator())
    footer = f"**Status:** {store.STATUS_LABELS.get(status, status)}"
    if status != "pending":
        footer += (f" by <@{appeal['reviewer_id']}>" if appeal.get("reviewer_id") else "") + (f" <t:{int(appeal['decided_at'])}:R>" if appeal.get("decided_at") else "")
        if appeal.get("decision_note"):
            footer += f"\n**Note:** {_clip(appeal['decision_note'], 300)}"
    elif cfg["votes"] > 1:
        footer += f"\n**Votes needed:** {cfg['votes']} · Accept {counts[0]} · Deny {counts[1]}"
    container.add_item(discord.ui.TextDisplay(footer))
    if status == "pending":
        row = discord.ui.ActionRow()
        accept = f"Accept ({counts[0]}/{cfg['votes']})" if cfg["votes"] > 1 else "Accept and unban"
        deny = f"Deny ({counts[1]}/{cfg['votes']})" if cfg["votes"] > 1 else "Deny"
        row.add_item(discord.ui.Button(label=accept, style=discord.ButtonStyle.success, custom_id=f"appeal:acc:{appeal['appeal_id']}"))
        row.add_item(discord.ui.Button(label=deny, style=discord.ButtonStyle.danger, custom_id=f"appeal:den:{appeal['appeal_id']}"))
        container.add_item(row)
    view.add_item(container)
    return view


class NoteModal(discord.ui.Modal, title="Deny appeal"):
    note = discord.ui.TextInput(label="Reason (sent to the user)", style=discord.TextStyle.paragraph, required=False, max_length=500)

    def __init__(self, cog: "Appeals", appeal_id: str):
        super().__init__(timeout=300)
        self.cog = cog
        self.appeal_id = appeal_id

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        ok, message = await self.cog.cast(interaction.guild, self.appeal_id, False, interaction.user, str(self.note.value or ""))
        if message:
            await interaction.followup.send(message, ephemeral=True)


class Appeals(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.recent: dict[tuple[int, int], float] = {}

    async def notify_ban(self, guild: discord.Guild, user, reason: str = "", until: Optional[float] = None, clean: bool = False) -> bool:
        cfg = await store.get_config(guild.id)
        if not cfg["dm"] or user is None or getattr(user, "bot", False):
            return False
        key = (guild.id, user.id)
        now = time.time()
        if now - self.recent.get(key, 0) < NOTICE_WINDOW:
            return False
        self.recent[key] = now
        if len(self.recent) > 500:
            for stale in [k for k, t in self.recent.items() if now - t > NOTICE_WINDOW]:
                self.recent.pop(stale, None)
        url = store.appeal_url(guild.id) if cfg["enabled"] else ""
        shown = (reason[:300] if clean else store.ban_reason_text(reason)) if cfg["show_reason"] else ""
        try:
            await user.send(view=notice_layout(guild, shown, until, cfg["notice"], url), allowed_mentions=NO_MENTIONS)
            return True
        except (discord.HTTPException, AttributeError):
            return False

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        if (guild.id, user.id) in self.recent and time.time() - self.recent[(guild.id, user.id)] < NOTICE_WINDOW:
            return
        reason = ""
        try:
            entry = await guild.fetch_ban(user)
            reason = entry.reason or ""
        except discord.HTTPException:
            pass
        until = None
        row = await db.raw_fetchone("SELECT unban_at FROM temp_bans WHERE guild_id=? AND user_id=?", (guild.id, user.id))
        if row:
            until = row["unban_at"]
        await self.notify_ban(guild, user, reason, until)

    async def _render(self, guild: discord.Guild, appeal: dict, ping: str = "") -> discord.ui.LayoutView:
        cfg = await store.get_config(guild.id)
        return review_layout(guild, appeal, cfg, await store.votes(appeal["appeal_id"]), ping)

    async def _refresh(self, guild: discord.Guild, appeal: dict) -> None:
        if not appeal.get("channel_id") or not appeal.get("message_id"):
            return
        channel = guild.get_channel(appeal["channel_id"])
        if channel is None:
            return
        try:
            message = await channel.fetch_message(appeal["message_id"])
            await message.edit(view=await self._render(guild, appeal), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass

    async def _post_review(self, guild: discord.Guild, appeal: dict) -> None:
        cfg = await store.get_config(guild.id)
        channel = guild.get_channel(int(cfg["channel"])) if cfg["channel"] else None
        if channel is None:
            return
        role = guild.get_role(int(cfg["role"])) if cfg["role"] else None
        ping = role.mention if role else ""
        try:
            message = await channel.send(
                view=review_layout(guild, appeal, cfg, (0, 0), ping),
                allowed_mentions=discord.AllowedMentions(roles=[role]) if role else NO_MENTIONS,
            )
        except discord.HTTPException:
            return
        await store.remember_message(appeal["appeal_id"], channel.id, message.id)

    async def web_info(self, guild_id: int, user_id: int) -> dict:
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise ValueError("Soward is not in that server.")
        cfg = await store.get_config(guild.id)
        info = {
            "guild": guild.name, "icon": guild.icon.replace(size=128).url if guild.icon else "",
            "questions": cfg["questions"], "max_answer": store.MAX_ANSWER, "state": "open", "reason": "", "ready_at": None,
        }
        if not cfg["enabled"]:
            info["state"] = "disabled"
            return info
        try:
            ban = await guild.fetch_ban(discord.Object(id=user_id))
        except discord.NotFound:
            info["state"] = "not_banned"
            return info
        except discord.HTTPException:
            info["state"] = "unavailable"
            return info
        if cfg["show_reason"]:
            info["reason"] = store.ban_reason_text(ban.reason)
        waiting = await store.waiting_state(guild.id, user_id, cfg["cooldown"])
        if waiting is not None:
            info["state"], info["ready_at"] = waiting
        return info

    async def web_submit(self, guild_id: int, user_id: int, user_name: str, answers: list) -> dict:
        info = await self.web_info(guild_id, user_id)
        if info["state"] != "open":
            return {"ok": False, "state": info["state"], "message": {
                "disabled": "Appeals are turned off for this server.",
                "not_banned": "You are not banned from this server.",
                "pending": "You already have an appeal waiting for review.",
                "cooldown": "You have to wait before appealing again.",
            }.get(info["state"], "Appeals are unavailable right now. Try again later.")}
        questions = info["questions"]
        if not isinstance(answers, list) or len(answers) != len(questions):
            return {"ok": False, "state": "open", "message": "Answer every question."}
        cleaned = []
        for question, raw in zip(questions, answers):
            text = str(raw or "").strip()
            if len(text) < 10:
                return {"ok": False, "state": "open", "message": "Each answer needs at least a sentence."}
            if len(text) > store.MAX_ANSWER:
                return {"ok": False, "state": "open", "message": f"Answers can be at most {store.MAX_ANSWER} characters."}
            cleaned.append({"q": question, "a": text})
        guild = self.bot.get_guild(guild_id)
        appeal_id = await store.create(guild_id, user_id, user_name, cleaned, info["reason"])
        appeal = await store.get(guild_id, appeal_id)
        await self._post_review(guild, appeal)
        await bus.publish(LOG_EVENT, guild_id=guild_id, action="security_change", actor_id=user_id, detail=f"Ban appeal `{appeal_id}` submitted by <@{user_id}>.")
        return {"ok": True, "state": "pending", "message": "Your appeal was sent to the staff. You will get a message from the bot when they decide, so keep your direct messages open."}

    async def cast(self, guild: discord.Guild, appeal_id: str, accept: bool, reviewer: discord.Member, note: str) -> tuple[bool, str]:
        appeal = await store.get(guild.id, appeal_id)
        if appeal is None:
            return False, "That appeal no longer exists."
        if appeal["status"] != "pending":
            return False, f"This appeal was already {store.STATUS_LABELS.get(appeal['status'], appeal['status']).lower()}."
        if not isinstance(reviewer, discord.Member) or not is_reviewer(reviewer):
            return False, "You need Ban Members or Manage Server to review appeals."
        cfg = await store.get_config(guild.id)
        if cfg["votes"] > 1:
            await store.set_vote(appeal["appeal_id"], reviewer.id, 1 if accept else -1)
            up, down = await store.votes(appeal["appeal_id"])
            if up >= cfg["votes"]:
                return await self.decide(guild, appeal["appeal_id"], True, reviewer, note)
            if down >= cfg["votes"]:
                return await self.decide(guild, appeal["appeal_id"], False, reviewer, note)
            await self._refresh(guild, appeal)
            return True, "Your vote was counted."
        return await self.decide(guild, appeal["appeal_id"], accept, reviewer, note)

    async def decide(self, guild: discord.Guild, appeal_id: str, accept: bool, reviewer, note: str) -> tuple[bool, str]:
        appeal = await store.get(guild.id, appeal_id)
        if appeal is None or appeal["status"] != "pending":
            return False, "This appeal was already decided."
        user_id = appeal["user_id"]
        reviewer_id = getattr(reviewer, "id", None)
        cfg = await store.get_config(guild.id)
        invite_url = ""
        if accept:
            try:
                await guild.unban(discord.Object(id=user_id), reason=f"Ban appeal {appeal['appeal_id']} accepted by {reviewer}")
            except discord.NotFound:
                pass
            except discord.HTTPException:
                return False, "I could not unban them. Check that I have Ban Members."
            await db.raw_execute("DELETE FROM temp_bans WHERE guild_id=? AND user_id=?", (guild.id, user_id))
            case_id = await cases.create_mod_case(guild.id, "unban", user_id, reviewer_id or self.bot.user.id, f"Appeal {appeal['appeal_id']} accepted")
            await bus.publish(LOG_EVENT, guild_id=guild.id, action="unban", user_id=user_id, moderator_id=reviewer_id, reason=f"Appeal {appeal['appeal_id']} accepted", case_id=case_id)
            channel = guild.get_channel(int(cfg["rejoin"])) if cfg["rejoin"] else None
            if channel is not None:
                try:
                    invite = await channel.create_invite(max_age=7 * 86400, max_uses=1, unique=True, reason="Accepted ban appeal")
                    invite_url = invite.url
                except discord.HTTPException:
                    invite_url = ""
        status = "accepted" if accept else "denied"
        await store.finish(appeal["appeal_id"], status, reviewer_id, note)
        appeal = await store.get(guild.id, appeal["appeal_id"])
        await self._refresh(guild, appeal)
        await self._tell_user(guild, appeal, accept, note, invite_url, cfg)
        return True, f"Appeal #{appeal['appeal_id']} {status}."

    async def _tell_user(self, guild: discord.Guild, appeal: dict, accept: bool, note: str, invite_url: str, cfg: dict) -> None:
        try:
            user = await self.bot.fetch_user(appeal["user_id"])
        except discord.HTTPException:
            return
        if accept:
            body = f"Staff accepted your appeal and you were unbanned from **{guild.name}**."
            body += f"\nYou can rejoin here: {invite_url}" if invite_url else "\nYou can use any invite link to rejoin."
            view = success_layout("Your appeal was accepted", body)
        else:
            body = f"Staff reviewed your appeal for **{guild.name}** and decided to keep the ban."
            if note:
                body += f"\n**Reason:** {_clip(note, 500)}"
            if cfg["cooldown"]:
                body += f"\nYou can appeal again in {cfg['cooldown']} day(s)."
            view = error_layout("Your appeal was denied", body)
        try:
            await user.send(view=view, allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if not custom_id.startswith("appeal:"):
            return
        parts = custom_id.split(":", 2)
        if len(parts) != 3 or parts[1] not in ("acc", "den"):
            return
        member = interaction.user
        if not isinstance(member, discord.Member) or not is_reviewer(member):
            return await interaction.response.send_message("Only staff with Ban Members or Manage Server can review appeals.", ephemeral=True)
        appeal = await store.get(interaction.guild.id, parts[2])
        if appeal is None or appeal["status"] != "pending":
            return await interaction.response.send_message("This appeal was already decided.", ephemeral=True)
        if parts[1] == "den":
            return await interaction.response.send_modal(NoteModal(self, appeal["appeal_id"]))
        await interaction.response.defer()
        ok, message = await self.cast(interaction.guild, appeal["appeal_id"], True, member, "")
        if message and (not ok or "counted" in message):
            await interaction.followup.send(message, ephemeral=True)

    @commands.group(name="appeal", aliases=["appeals"], invoke_without_command=True, help="Ban appeals through the web dashboard.")
    @commands.guild_only()
    async def appeal(self, ctx: commands.Context):
        e = emoji_manager.get
        cfg = await store.get_config(ctx.guild.id)
        url = store.appeal_url(ctx.guild.id)
        channel = ctx.guild.get_channel(int(cfg["channel"])) if cfg["channel"] else None
        body = (
            f"**Status:** {'on' if cfg['enabled'] else 'off'} · **Review channel:** {channel.mention if channel else 'not set'}\n"
            f"**Votes needed:** {cfg['votes']} · **Cooldown after a denial:** {cfg['cooldown']} day(s)\n"
            f"**Appeal page:** {url or 'set SOWARD_DASHBOARD_URL on the bot to enable the link'}\n\n"
            "Banned members get a message with an **Appeal this ban** button. They sign in with Discord on the dashboard, answer the questions and staff review it in the review channel or on the dashboard.\n\n"
            "`appeal on|off` · `appeal channel <#channel>` · `appeal questions` · `appeal question add|remove|reset` · `appeal votes <n>` · `appeal cooldown <days>` · "
            "`appeal notice <text|reset>` · `appeal role <@role|none>` · `appeal rejoin <#channel|none>` · `appeal reason on|off` · `appeal dm on|off` · "
            "`appeal list [status]` · `appeal view <id>` · `appeal accept <id> [note]` · `appeal deny <id> [note]` · `appeal link`"
        )
        await ctx.send(view=info_layout(f"{e('ban')} Ban appeals", body))

    async def _set(self, ctx: commands.Context, name: str, value, text: str):
        e = emoji_manager.get
        await store.set_config(ctx.guild.id, name, value)
        await ctx.send(view=success_layout(f"{e('check')} Appeals", text))

    @appeal.command(name="on", aliases=["enable"], help="Turn ban appeals on.")
    @has_guild_permission("manage_guild")
    async def appeal_on(self, ctx: commands.Context):
        await self._set(ctx, "enabled", True, "Ban appeals are **on**. Banned members get an appeal button.")

    @appeal.command(name="off", aliases=["disable"], help="Turn ban appeals off.")
    @has_guild_permission("manage_guild")
    async def appeal_off(self, ctx: commands.Context):
        await self._set(ctx, "enabled", False, "Ban appeals are **off**. Ban messages are still sent without the button.")

    @appeal.command(name="channel", help="Set where new appeals are posted for review.")
    @has_guild_permission("manage_guild")
    async def appeal_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await self._set(ctx, "channel", channel.id, f"New appeals are posted in {channel.mention}.")

    @appeal.command(name="votes", help="How many staff votes decide an appeal (1 means one reviewer decides).")
    @has_guild_permission("manage_guild")
    async def appeal_votes(self, ctx: commands.Context, amount: int):
        if not 1 <= amount <= 10:
            return await ctx.send(view=error_layout("Invalid number", "Use a number from 1 to 10."))
        await self._set(ctx, "votes", amount, f"An appeal is decided after **{amount}** matching staff vote(s).")

    @appeal.command(name="cooldown", help="Days a member must wait after a denied appeal.")
    @has_guild_permission("manage_guild")
    async def appeal_cooldown(self, ctx: commands.Context, days: int):
        if not 0 <= days <= 365:
            return await ctx.send(view=error_layout("Invalid number", "Use 0 to 365 days."))
        await self._set(ctx, "cooldown", days, f"Denied members wait **{days}** day(s) before appealing again.")

    @appeal.command(name="notice", help="Extra text added to the ban message, or `reset`.")
    @has_guild_permission("manage_guild")
    async def appeal_notice(self, ctx: commands.Context, *, text: str):
        if text.lower() in ("reset", "none", "off"):
            return await self._set(ctx, "notice", None, "The extra ban message text was removed.")
        await self._set(ctx, "notice", text[:600], "The ban message now includes your text.")

    @appeal.command(name="role", help="Role pinged for new appeals, or `none`.")
    @has_guild_permission("manage_guild")
    async def appeal_role(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        await self._set(ctx, "role", role.id if role else None, f"New appeals ping {role.mention}." if role else "New appeals no longer ping a role.")

    @appeal.command(name="rejoin", help="Channel Soward makes a one-use invite for when an appeal is accepted, or `none`.")
    @has_guild_permission("manage_guild")
    async def appeal_rejoin(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        await self._set(ctx, "rejoin", channel.id if channel else None, f"Accepted members get a one-use invite to {channel.mention}." if channel else "Accepted members are told to use any invite.")

    @appeal.command(name="reason", help="Show the ban reason in the ban message and on the appeal page.")
    @has_guild_permission("manage_guild")
    async def appeal_reason(self, ctx: commands.Context, toggle: bool):
        await self._set(ctx, "show_reason", toggle, f"The ban reason is now **{'shown' if toggle else 'hidden'}** to banned members.")

    @appeal.command(name="dm", help="Send banned members a message when they are banned.")
    @has_guild_permission("manage_guild")
    async def appeal_dm(self, ctx: commands.Context, toggle: bool):
        await self._set(ctx, "dm", toggle, f"Ban messages are now **{'sent' if toggle else 'not sent'}**.")

    @appeal.command(name="link", help="Show the appeal page address.")
    async def appeal_link(self, ctx: commands.Context):
        url = store.appeal_url(ctx.guild.id)
        if not url:
            return await ctx.send(view=error_layout("No dashboard address", "Set `SOWARD_DASHBOARD_URL` on the bot so ban messages can link to the appeal page."))
        await ctx.send(view=info_layout("Appeal page", url))

    @appeal.command(name="questions", help="Show the appeal questions.")
    async def appeal_questions(self, ctx: commands.Context):
        cfg = await store.get_config(ctx.guild.id)
        await ctx.send(view=info_layout("Appeal questions", "\n".join(f"**{n}.** {q}" for n, q in enumerate(cfg["questions"], 1))))

    @appeal.group(name="question", invoke_without_command=True, help="Edit the appeal questions.")
    @has_guild_permission("manage_guild")
    async def appeal_question(self, ctx: commands.Context):
        await self.appeal_questions(ctx)

    @appeal_question.command(name="add", help="Add a question.")
    @has_guild_permission("manage_guild")
    async def question_add(self, ctx: commands.Context, *, text: str):
        cfg = await store.get_config(ctx.guild.id)
        questions = list(cfg["questions"])
        if len(questions) >= store.MAX_QUESTIONS:
            return await ctx.send(view=error_layout("Too many questions", f"Appeals can have up to {store.MAX_QUESTIONS} questions."))
        if len(text) > store.MAX_QUESTION:
            return await ctx.send(view=error_layout("Too long", f"Questions can be at most {store.MAX_QUESTION} characters."))
        questions.append(text.strip())
        await self._set(ctx, "questions", questions, f"Added question {len(questions)}.")

    @appeal_question.command(name="remove", help="Remove a question by number.")
    @has_guild_permission("manage_guild")
    async def question_remove(self, ctx: commands.Context, number: int):
        cfg = await store.get_config(ctx.guild.id)
        questions = list(cfg["questions"])
        if not 1 <= number <= len(questions) or len(questions) == 1:
            return await ctx.send(view=error_layout("Cannot remove", "Pick an existing question. At least one question must stay."))
        removed = questions.pop(number - 1)
        await self._set(ctx, "questions", questions, f"Removed: {_clip(removed, 120)}")

    @appeal_question.command(name="reset", help="Go back to the default questions.")
    @has_guild_permission("manage_guild")
    async def question_reset(self, ctx: commands.Context):
        await self._set(ctx, "questions", None, "The questions were reset to the defaults.")

    @appeal.command(name="list", help="List appeals. Usage: appeal list [pending|accepted|denied|all]")
    @has_guild_permission("ban_members")
    async def appeal_list(self, ctx: commands.Context, status: str = "pending"):
        status = status.lower()
        rows = await store.listing(ctx.guild.id, None if status == "all" else status)
        if not rows:
            return await ctx.send(view=info_layout("Appeals", "No appeals found."))
        lines = [f"`{r['appeal_id']}` <@{r['user_id']}> · {store.STATUS_LABELS.get(r['status'], r['status'])} · <t:{int(r['created_at'])}:R>" for r in rows]
        await ctx.send(view=info_layout(f"Appeals · {status}", "\n".join(lines)[:3500]), allowed_mentions=NO_MENTIONS)

    @appeal.command(name="view", help="Read one appeal.")
    @has_guild_permission("ban_members")
    async def appeal_view(self, ctx: commands.Context, appeal_id: str):
        appeal = await store.get(ctx.guild.id, appeal_id)
        if appeal is None:
            return await ctx.send(view=error_layout("Not found", "No appeal with that id."))
        await ctx.send(view=await self._render(ctx.guild, appeal), allowed_mentions=NO_MENTIONS)

    @appeal.command(name="accept", help="Accept an appeal and unban the member.")
    @has_guild_permission("ban_members")
    async def appeal_accept(self, ctx: commands.Context, appeal_id: str, *, note: str = ""):
        ok, message = await self.cast(ctx.guild, appeal_id, True, ctx.author, note)
        await ctx.send(view=(success_layout if ok else error_layout)("Appeals", message))

    @appeal.command(name="deny", help="Deny an appeal.")
    @has_guild_permission("ban_members")
    async def appeal_deny(self, ctx: commands.Context, appeal_id: str, *, note: str = ""):
        ok, message = await self.cast(ctx.guild, appeal_id, False, ctx.author, note)
        await ctx.send(view=(success_layout if ok else error_layout)("Appeals", message))


async def setup(bot: commands.Bot):
    await bot.add_cog(Appeals(bot))
