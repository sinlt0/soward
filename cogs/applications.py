import csv
import io
import time
from datetime import datetime, timezone
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import applications as store
from utils import db, emoji_manager, premium_limits
from utils.applications import MAX_OPTIONS, QUESTION_TYPES, ROLE_LISTS, STATUS_LABELS
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

NO_MENTIONS = discord.AllowedMentions.none()
CLOSED_COLOR = 0xED4245
STATUS_COLORS = {"accepted": 0x57F287, "denied": 0xED4245, "withdrawn": 0x95A5A6}
SETTING_KEYS = {
    "title": ("text", "title", 100), "description": ("text", "description", 300), "color": ("color", "color", 7),
    "dm_submit": ("text", "dm_submit", 1000), "dm_accept": ("text", "dm_accept", 1000), "dm_deny": ("text", "dm_deny", 1000),
    "cooldown": ("int", "cooldown_hours", 8760), "account_age": ("int", "min_account_days", 3650), "join_age": ("int", "min_join_days", 3650),
    "slots": ("int", "slots", 1000), "thread": ("bool", "thread", 0), "votes": ("bool", "votes", 0), "require_reason": ("bool", "require_reason", 0),
    "autodeny_leave": ("bool", "autodeny_leave", 0), "enabled": ("bool", "enabled", 0), "channel": ("channel", "channel_id", 0),
    "interview_category": ("category", "interview_category_id", 0),
    "interview_delete": ("bool", "interview_delete", 0), "interview_delay": ("int", "interview_delay_minutes", 1440),
}


def _clip(text: str, limit: int) -> str:
    text = str(text)
    return text if len(text) <= limit else text[: max(1, limit - 3)] + "..."


def _stamp(value: Optional[datetime], style: str = "R") -> str:
    return f"<t:{int(value.timestamp())}:{style}>" if value else "unknown"


def build_pages(questions: list) -> list[dict]:
    pages: list[dict] = []
    for index, question in enumerate(questions):
        if question["type"] in ("text", "paragraph"):
            if pages and pages[-1]["kind"] == "text" and len(pages[-1]["qs"]) < 5:
                pages[-1]["qs"].append(index)
            else:
                pages.append({"kind": "text", "qs": [index]})
        else:
            pages.append({"kind": "pick", "qs": [index]})
    return pages


def answers_list(questions: list, raw: dict) -> list[dict]:
    result = []
    for index, question in enumerate(questions):
        value = raw.get(index)
        text = ", ".join(value) if isinstance(value, list) else (value or "")
        result.append({"q": question["text"], "type": question["type"], "a": text.strip() or "No answer"})
    return result


def form_problem(form: dict) -> Optional[str]:
    if not form["questions"]:
        return "This application has no questions yet."
    for number, question in enumerate(form["questions"], 1):
        if question["type"] in ("choice", "multi") and len(question["options"]) < 2:
            return f"Question {number} needs at least 2 options."
    return None


def panel_layout(entries: list[tuple[str, dict]], title: str = "Applications", description: str = "") -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    all_closed = bool(entries) and not any(form["enabled"] for _, form in entries)
    container = discord.ui.Container(accent_color=CLOSED_COLOR if all_closed else store.color_int(entries[0][1]["color"]) if entries else 0x5865F2)
    lines = [f"## {title}"]
    if description:
        lines.append(description)
    for name, form in entries:
        state = "Open" if form["enabled"] else "Closed"
        extra = f"\n{form['description']}" if form["description"] else ""
        lines.append(f"**{form['title'] or name}** ({state}){extra}")
    container.add_item(discord.ui.TextDisplay("\n\n".join(lines)))
    container.add_item(discord.ui.Separator())
    if len(entries) <= 5:
        row = discord.ui.ActionRow()
        for name, form in entries:
            if form["enabled"]:
                row.add_item(discord.ui.Button(label=_clip(f"Apply: {form['title'] or name}", 80), style=discord.ButtonStyle.primary, custom_id=f"app:go:{name}"))
            else:
                row.add_item(discord.ui.Button(label=_clip(f"{form['title'] or name}: Closed", 80), style=discord.ButtonStyle.danger, custom_id=f"app:go:{name}"))
        container.add_item(row)
    else:
        select = discord.ui.Select(
            custom_id="app:pick", placeholder="Choose an application",
            options=[discord.SelectOption(label=_clip((f["title"] or n) + ("" if f["enabled"] else " (Closed)"), 100), value=n, description=_clip(f["description"], 100) or None) for n, f in entries[:25]],
        )
        container.add_item(discord.ui.ActionRow(select))
    view.add_item(container)
    return view


def review_layout(guild: discord.Guild, form: dict, sub: dict, user, votes: tuple[int, int], ping: str = "") -> discord.ui.LayoutView:
    status = sub["status"]
    view = discord.ui.LayoutView(timeout=None)
    if ping:
        view.add_item(discord.ui.TextDisplay(ping))
    color = STATUS_COLORS.get(status) or store.color_int(form["color"])
    container = discord.ui.Container(accent_color=color)
    member = guild.get_member(sub["user_id"])
    info = [f"## {form['title'] or sub['form']} - Application #{sub['app_id']}", f"**Applicant:** <@{sub['user_id']}> (`{sub['user_id']}`)"]
    if user is not None:
        info.append(f"**Account created:** {_stamp(user.created_at)}")
    if member is not None and member.joined_at:
        info.append(f"**Joined server:** {_stamp(member.joined_at)}")
    elif member is None:
        info.append("**Joined server:** not in the server")
    info.append(f"**Submitted:** <t:{int(sub['created_at'])}:R>")
    header = "\n".join(info)
    footer = f"**Status:** {STATUS_LABELS.get(status, status)}"
    if status != "pending":
        who = f" by <@{sub['reviewer_id']}>" if sub.get("reviewer_id") else ""
        when = f" <t:{int(sub['decided_at'])}:R>" if sub.get("decided_at") else ""
        footer += f"{who}{when}"
        if sub.get("reason"):
            footer += f"\n**Reason:** {_clip(sub['reason'], 400)}"
    if sub.get("interview_channel_id"):
        footer += f"\n**Interview:** <#{sub['interview_channel_id']}>"
    budget = max(600, 3500 - len(header) - len(footer))
    per = max(120, budget // max(1, len(sub["answers"])))
    body = []
    for number, item in enumerate(sub["answers"], 1):
        body.append(f"**{number}. {_clip(item['q'], 150)}**\n{_clip(item['a'], max(60, per - 160))}")
    container.add_item(discord.ui.TextDisplay(header))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay("\n\n".join(body) or "No answers."))
    container.add_item(discord.ui.Separator())
    container.add_item(discord.ui.TextDisplay(footer))
    if status == "pending":
        row = discord.ui.ActionRow()
        row.add_item(discord.ui.Button(label="Accept", style=discord.ButtonStyle.success, custom_id=f"app:acc:{sub['app_id']}"))
        row.add_item(discord.ui.Button(label="Deny", style=discord.ButtonStyle.danger, custom_id=f"app:den:{sub['app_id']}"))
        if not sub.get("interview_channel_id"):
            row.add_item(discord.ui.Button(label="Interview", style=discord.ButtonStyle.secondary, custom_id=f"app:int:{sub['app_id']}"))
        container.add_item(row)
        if form["votes"]:
            vote_row = discord.ui.ActionRow()
            vote_row.add_item(discord.ui.Button(label=f"Upvote ({votes[0]})", style=discord.ButtonStyle.secondary, custom_id=f"app:up:{sub['app_id']}"))
            vote_row.add_item(discord.ui.Button(label=f"Downvote ({votes[1]})", style=discord.ButtonStyle.secondary, custom_id=f"app:dn:{sub['app_id']}"))
            container.add_item(vote_row)
    elif form["votes"] and (votes[0] or votes[1]):
        container.add_item(discord.ui.TextDisplay(f"-# Staff votes: {votes[0]} up, {votes[1]} down"))
    view.add_item(container)
    return view


class AnswerModal(discord.ui.Modal):
    def __init__(self, wizard: "Wizard", page: dict):
        super().__init__(title=_clip(wizard.form["title"] or "Application", 45), timeout=900)
        self.wizard = wizard
        self.page = page
        self.fields: dict[int, discord.ui.TextInput] = {}
        for index in page["qs"]:
            question = wizard.form["questions"][index]
            long = question["type"] == "paragraph"
            field = discord.ui.TextInput(
                label=_clip(f"{index + 1}. {question.get('label') or question['text']}", 45), placeholder=_clip(question["text"], 100),
                style=discord.TextStyle.paragraph if long else discord.TextStyle.short, required=question["required"],
                max_length=1000 if long else 200, default=wizard.answers.get(index) or None,
            )
            self.fields[index] = field
            self.add_item(field)

    async def on_submit(self, interaction: discord.Interaction):
        for index, field in self.fields.items():
            self.wizard.answers[index] = field.value.strip()
        self.wizard.idx += 1
        await interaction.response.edit_message(view=self.wizard.build())


class ReasonModal(discord.ui.Modal):
    def __init__(self, cog: "Applications", app_id: int, required: bool):
        super().__init__(title=f"Deny application #{app_id}", timeout=600)
        self.cog = cog
        self.app_id = app_id
        self.reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, required=required, max_length=500, placeholder="Sent to the applicant")
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message("Processing...", ephemeral=True)
        ok, message = await self.cog.decide(interaction.guild, self.app_id, False, interaction.user, self.reason.value.strip())
        await interaction.edit_original_response(content=message)


class Wizard(discord.ui.LayoutView):
    def __init__(self, cog: "Applications", guild: discord.Guild, member: discord.Member, name: str, form: dict):
        super().__init__(timeout=1800)
        self.cog = cog
        self.guild = guild
        self.member = member
        self.name = name
        self.form = form
        self.pages = build_pages(form["questions"])
        self.idx = 0
        self.answers: dict[int, object] = {}
        self.build()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.member.id

    def _button(self, label: str, style, callback) -> discord.ui.Button:
        button = discord.ui.Button(label=label, style=style)
        button.callback = callback
        return button

    def _page_answered(self, page: dict) -> bool:
        return all(
            (self.answers.get(i) not in (None, "", [])) or not self.form["questions"][i]["required"] for i in page["qs"]
        ) and any(i in self.answers for i in page["qs"])

    def build(self) -> "Wizard":
        self.clear_items()
        form = self.form
        container = discord.ui.Container(accent_color=store.color_int(form["color"]))
        total = len(self.pages)
        title = form["title"] or self.name
        row = discord.ui.ActionRow()
        if self.idx >= total:
            lines = [f"## {title}", "**Review your answers**"]
            for number, item in enumerate(answers_list(form["questions"], self.answers), 1):
                lines.append(f"**{number}. {_clip(item['q'], 100)}**\n{_clip(item['a'], 160)}")
            container.add_item(discord.ui.TextDisplay(_clip("\n\n".join(lines), 3800)))
            container.add_item(discord.ui.Separator())
            row.add_item(self._button("Submit", discord.ButtonStyle.success, self._submit))
        else:
            page = self.pages[self.idx]
            lines = [f"## {title}", f"-# Step {self.idx + 1} of {total + 1}"]
            if self.idx == 0 and form["description"]:
                lines.append(form["description"])
            for i in page["qs"]:
                question = form["questions"][i]
                tag = "" if question["required"] else " (optional)"
                lines.append(f"**{i + 1}. {question['text']}**{tag}")
                if page["kind"] == "text" and self.answers.get(i):
                    lines.append(f"> {_clip(self.answers[i], 120)}")
            container.add_item(discord.ui.TextDisplay(_clip("\n\n".join(lines), 3800)))
            container.add_item(discord.ui.Separator())
            if page["kind"] == "text":
                row.add_item(self._button("Edit answers" if self._page_answered(page) else "Answer", discord.ButtonStyle.primary, self._answer))
                if self._page_answered(page):
                    row.add_item(self._button("Next", discord.ButtonStyle.secondary, self._next))
            else:
                container.add_item(discord.ui.ActionRow(self._select(page["qs"][0])))
                if not form["questions"][page["qs"][0]]["required"]:
                    row.add_item(self._button("Skip", discord.ButtonStyle.secondary, self._next))
        if self.idx > 0:
            row.add_item(self._button("Back", discord.ButtonStyle.secondary, self._back))
        row.add_item(self._button("Cancel", discord.ButtonStyle.danger, self._cancel))
        container.add_item(row)
        self.add_item(container)
        return self

    def _select(self, index: int) -> discord.ui.Select:
        question = self.form["questions"][index]
        multi = question["type"] == "multi"
        chosen = self.answers.get(index) or []
        if not isinstance(chosen, list):
            chosen = [chosen]
        options = [discord.SelectOption(label=_clip(o, 100), value=str(n), default=o in chosen) for n, o in enumerate(question["options"][:MAX_OPTIONS])]
        select = discord.ui.Select(
            placeholder="Choose several" if multi else "Choose one", options=options,
            min_values=1 if question["required"] else 0, max_values=len(options) if multi else 1,
        )

        async def picked(interaction: discord.Interaction):
            values = [question["options"][int(v)] for v in select.values]
            self.answers[index] = values if multi else (values[0] if values else "")
            self.idx += 1
            await interaction.response.edit_message(view=self.build())

        select.callback = picked
        return select

    async def _answer(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AnswerModal(self, self.pages[self.idx]))

    async def _next(self, interaction: discord.Interaction):
        self.idx += 1
        await interaction.response.edit_message(view=self.build())

    async def _back(self, interaction: discord.Interaction):
        self.idx = max(0, self.idx - 1)
        await interaction.response.edit_message(view=self.build())

    async def _cancel(self, interaction: discord.Interaction):
        self.stop()
        await interaction.response.edit_message(view=info_layout("Application cancelled", "Nothing was sent. You can start again any time."))

    async def _submit(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=info_layout("Sending", "Submitting your application..."))
        self.stop()
        result = await self.cog.create_submission(self.guild, self.member, self.name, answers_list(self.form["questions"], self.answers))
        await interaction.edit_original_response(view=result)


class Applications(commands.Cog):
    category = "Community"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.interview_loop.start()
        self.panel_sync.start()

    async def cog_unload(self):
        self.interview_loop.cancel()
        self.panel_sync.cancel()

    async def refresh_panels(self, guild_id: int = None):
        for panel in await store.panels(guild_id):
            guild = self.bot.get_guild(int(panel["guild_id"]))
            if guild is None:
                continue
            entries = []
            for name in panel["forms"]:
                form = await store.get_form(guild.id, name)
                if form is not None:
                    entries.append((name, form))
            if not entries:
                continue
            state = store.panel_state(entries)
            if state == panel["state"]:
                continue
            channel = guild.get_channel(int(panel["channel_id"]))
            if channel is None:
                await store.delete_panel(int(panel["message_id"]))
                continue
            try:
                await channel.get_partial_message(int(panel["message_id"])).edit(view=panel_layout(entries))
            except discord.NotFound:
                await store.delete_panel(int(panel["message_id"]))
                continue
            except discord.HTTPException:
                continue
            await store.set_panel_state(int(panel["message_id"]), state)

    @tasks.loop(minutes=1)
    async def panel_sync(self):
        await self.refresh_panels()

    @panel_sync.before_loop
    async def before_panel_sync(self):
        await self.bot.wait_until_ready()

    @tasks.loop(minutes=1)
    async def interview_loop(self):
        rows = await db.raw_fetch("SELECT guild_id, app_id FROM app_submissions WHERE status!='pending' AND interview_channel_id IS NOT NULL")
        for row in rows:
            try:
                guild = self.bot.get_guild(row["guild_id"])
                sub = await store.get_sub(row["guild_id"], row["app_id"])
                if guild is None or sub is None:
                    continue
                form = await store.get_form(guild.id, sub["form"])
                if form is None or not form["interview_delete"]:
                    continue
                if time.time() >= (sub["decided_at"] or 0) + form["interview_delay_minutes"] * 60:
                    await self._delete_interview(guild, sub)
            except Exception:
                continue

    @interview_loop.before_loop
    async def before_interview_loop(self):
        await self.bot.wait_until_ready()

    async def _delete_interview(self, guild: discord.Guild, sub: dict):
        channel = guild.get_channel(sub["interview_channel_id"]) if sub.get("interview_channel_id") else None
        if channel is not None:
            try:
                await channel.delete(reason=f"Application #{sub['app_id']} was decided")
            except discord.HTTPException:
                return
        await store.update_sub(guild.id, sub["app_id"], interview_channel_id=None)
        sub["interview_channel_id"] = None
        await self._refresh_review(guild, sub)

    def is_reviewer(self, member: discord.Member, form: dict) -> bool:
        if member.guild_permissions.manage_guild:
            return True
        reviewers = set(form["roles"]["reviewers"])
        return any(r.id in reviewers for r in member.roles)

    async def eligibility(self, guild: discord.Guild, member: discord.Member, name: str, form: dict) -> Optional[str]:
        if not form["enabled"]:
            return f"Applications for **{form['title'] or name}** are currently closed. Check back later."
        problem = form_problem(form)
        if problem:
            return f"This application is not ready yet. {problem}"
        channel = guild.get_channel(form["channel_id"]) if form["channel_id"] else None
        if not isinstance(channel, discord.TextChannel):
            return "This application is not set up yet. Ask an admin to set the review channel."
        if form["slots"] and form["accepted"] >= form["slots"]:
            return "All spots for this application have been filled."
        have = {r.id for r in member.roles}
        if any(r not in have for r in form["roles"]["required"]):
            return "You do not have the roles needed to apply."
        if any(r in have for r in form["roles"]["blocked"]):
            return "You cannot apply for this right now."
        now = datetime.now(timezone.utc)
        if form["min_account_days"] and (now - member.created_at).days < form["min_account_days"]:
            return f"Your Discord account must be at least {form['min_account_days']} day(s) old."
        if form["min_join_days"] and member.joined_at and (now - member.joined_at).days < form["min_join_days"]:
            return f"You must be in this server for at least {form['min_join_days']} day(s)."
        pending = await db.raw_fetchone("SELECT app_id FROM app_submissions WHERE guild_id=? AND form=? AND user_id=? AND status='pending'", (guild.id, name, member.id))
        if pending:
            return f"You already have a pending application (#{pending['app_id']}). Wait for a decision or withdraw it with `application withdraw {pending['app_id']}`."
        latest = await db.raw_fetchone("SELECT status, created_at, decided_at FROM app_submissions WHERE guild_id=? AND form=? AND user_id=? ORDER BY app_id DESC LIMIT 1", (guild.id, name, member.id))
        if latest:
            if latest["status"] == "accepted":
                return "You were already accepted for this application."
            if form["cooldown_hours"]:
                until = (latest["decided_at"] or latest["created_at"]) + form["cooldown_hours"] * 3600
                if time.time() < until:
                    return f"You can apply again <t:{int(until)}:R>."
        return None

    async def begin(self, interaction: discord.Interaction, name: str):
        guild = interaction.guild
        form = await store.get_form(guild.id, name)
        if form is None:
            return await interaction.response.send_message(view=error_layout("Not found", "That application no longer exists."), ephemeral=True)
        member = interaction.user
        if not isinstance(member, discord.Member):
            return
        problem = await self.eligibility(guild, member, name, form)
        if problem:
            return await interaction.response.send_message(view=error_layout("Applications closed" if not form["enabled"] else "Cannot apply", problem), ephemeral=True)
        await interaction.response.send_message(view=Wizard(self, guild, member, name, form), ephemeral=True)

    async def _render_review(self, guild: discord.Guild, sub: dict, ping: str = "") -> discord.ui.LayoutView:
        form = await store.get_form(guild.id, sub["form"]) or store._merge({})
        votes = await store.vote_counts(guild.id, sub["app_id"])
        user = guild.get_member(sub["user_id"]) or self.bot.get_user(sub["user_id"])
        return review_layout(guild, form, sub, user, votes, ping)

    async def _refresh_review(self, guild: discord.Guild, sub: dict):
        channel = guild.get_channel_or_thread(sub["channel_id"]) if sub.get("channel_id") else None
        if channel is None or not sub.get("message_id"):
            return
        try:
            message = await channel.fetch_message(sub["message_id"])
            await message.edit(view=await self._render_review(guild, sub))
        except discord.HTTPException:
            pass

    async def create_submission(self, guild: discord.Guild, member: discord.Member, name: str, answers: list[dict]) -> discord.ui.LayoutView:
        form = await store.get_form(guild.id, name)
        if form is None:
            return error_layout("Not found", "That application no longer exists.")
        problem = await self.eligibility(guild, member, name, form)
        if problem:
            return error_layout("Cannot apply", problem)
        channel = guild.get_channel(form["channel_id"])
        app_id = await store.next_id(guild.id)
        sub = {"guild_id": guild.id, "app_id": app_id, "form": name, "user_id": member.id, "answers": answers, "status": "pending",
               "created_at": time.time(), "channel_id": channel.id}
        pings = [guild.get_role(r) for r in form["roles"]["ping"]]
        pings = [r for r in pings if r is not None]
        ping_text = " ".join(r.mention for r in pings)
        try:
            message = await channel.send(view=review_layout(guild, form, sub, member, (0, 0), ping_text), allowed_mentions=discord.AllowedMentions(roles=pings, users=False, everyone=False))
        except discord.HTTPException:
            return error_layout("Could not send", "I could not post your application. Tell an admin to check my permissions in the review channel.")
        sub["message_id"] = message.id
        if form["thread"]:
            try:
                thread = await message.create_thread(name=_clip(f"Application #{app_id} {member.name}", 100), auto_archive_duration=10080)
                sub["thread_id"] = thread.id
            except discord.HTTPException:
                pass
        await store.insert_sub(sub)
        try:
            await member.send(store.fill(form["dm_submit"], user=member.mention, username=member.name, server=guild.name, form=form["title"] or name, id=app_id, reason=""), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass
        return success_layout("Application sent", f"Your application **#{app_id}** was sent to the staff. You will get a direct message when it is reviewed, so keep your DMs open.")

    async def decide(self, guild: discord.Guild, app_id: int, accept: bool, reviewer, reason: str, automatic: bool = False) -> tuple[bool, str]:
        sub = await store.get_sub(guild.id, app_id)
        if sub is None:
            return False, f"There is no application #{app_id}."
        if sub["status"] != "pending":
            return False, f"Application #{app_id} was already {STATUS_LABELS.get(sub['status'], sub['status']).lower()}."
        form = await store.get_form(guild.id, sub["form"]) or store._merge({})
        if not automatic:
            if not self.is_reviewer(reviewer, form):
                return False, "You are not allowed to review this application."
            if reviewer.id == sub["user_id"] and not reviewer.guild_permissions.administrator:
                return False, "You cannot review your own application."
        status = "accepted" if accept else "denied"
        await store.update_sub(guild.id, app_id, status=status, reviewer_id=getattr(reviewer, "id", None), reason=reason or None, decided_at=time.time())
        sub.update(status=status, reviewer_id=getattr(reviewer, "id", None), reason=reason or None, decided_at=time.time())
        member = guild.get_member(sub["user_id"])
        notes = []
        if member is not None:
            add_ids = form["roles"]["accept_add" if accept else "deny_add"]
            remove_ids = form["roles"]["accept_remove" if accept else "deny_remove"]
            top = guild.me.top_role
            add = [r for r in (guild.get_role(i) for i in add_ids) if r and r < top and not r.managed]
            remove = [r for r in (guild.get_role(i) for i in remove_ids) if r and r < top and not r.managed]
            try:
                if add:
                    await member.add_roles(*add, reason=f"Application #{app_id} {status}")
                if remove:
                    await member.remove_roles(*remove, reason=f"Application #{app_id} {status}")
            except discord.HTTPException:
                notes.append("I could not change some roles. Check that my role is above them.")
        if not automatic:
            template = form["dm_accept" if accept else "dm_deny"]
            suffix = f"\nNote: {reason}" if reason else ""
            text = store.fill(template, user=f"<@{sub['user_id']}>", username=member.name if member else "there", server=guild.name, form=form["title"] or sub["form"], id=app_id, reason=suffix)
            target = member or self.bot.get_user(sub["user_id"])
            if target is not None:
                try:
                    await target.send(text, allowed_mentions=NO_MENTIONS)
                except discord.HTTPException:
                    notes.append("The applicant has direct messages closed, so they were not notified.")
        if accept:
            form["accepted"] += 1
            if form["slots"] and form["accepted"] >= form["slots"]:
                form["enabled"] = False
                notes.append("All spots are filled, so this application was closed.")
            await store.save_form(guild.id, sub["form"], form)
            await self.refresh_panels(guild.id)
        await self._refresh_review(guild, sub)
        if sub.get("interview_channel_id") and form["interview_delete"]:
            delay = form["interview_delay_minutes"]
            if delay <= 0:
                await self._delete_interview(guild, sub)
            else:
                channel = guild.get_channel(sub["interview_channel_id"])
                if channel is not None:
                    try:
                        await channel.send(view=info_layout(f"Application {status}", f"This interview channel will be deleted in {delay} minute(s)."))
                    except discord.HTTPException:
                        pass
        return True, f"Application #{app_id} {status}." + ("\n" + "\n".join(notes) if notes else "")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        data = interaction.data or {}
        custom_id = str(data.get("custom_id", ""))
        if not custom_id.startswith("app:"):
            return
        parts = custom_id.split(":", 2)
        kind = parts[1] if len(parts) > 1 else ""
        arg = parts[2] if len(parts) > 2 else ""
        if kind == "go":
            return await self.begin(interaction, arg)
        if kind == "pick":
            values = data.get("values") or []
            return await self.begin(interaction, str(values[0])) if values else None
        if kind not in ("acc", "den", "int", "up", "dn") or not arg.isdigit():
            return
        guild = interaction.guild
        sub = await store.get_sub(guild.id, int(arg))
        if sub is None:
            return await interaction.response.send_message("This application no longer exists.", ephemeral=True)
        form = await store.get_form(guild.id, sub["form"]) or store._merge({})
        member = interaction.user
        if not isinstance(member, discord.Member) or not self.is_reviewer(member, form):
            return await interaction.response.send_message("Only reviewers can use these buttons.", ephemeral=True)
        if sub["status"] != "pending":
            return await interaction.response.send_message(f"This application was already {STATUS_LABELS.get(sub['status'], sub['status']).lower()}.", ephemeral=True)
        if kind == "den":
            return await interaction.response.send_modal(ReasonModal(self, sub["app_id"], form["require_reason"]))
        if kind == "acc":
            await interaction.response.defer()
            ok, message = await self.decide(guild, sub["app_id"], True, member, "")
            if not ok or "\n" in message:
                await interaction.followup.send(message, ephemeral=True)
            return
        if kind in ("up", "dn"):
            await store.toggle_vote(guild.id, sub["app_id"], member.id, 1 if kind == "up" else -1)
            return await interaction.response.edit_message(view=await self._render_review(guild, sub))
        await interaction.response.defer(ephemeral=True, thinking=True)
        channel = await self._open_interview(guild, sub, form)
        if channel is None:
            return await interaction.followup.send("I could not create the interview channel. Check that I have Manage Channels.", ephemeral=True)
        sub["interview_channel_id"] = channel.id
        await self._refresh_review(guild, sub)
        await interaction.followup.send(f"Interview channel created: {channel.mention}", ephemeral=True)

    async def _open_interview(self, guild: discord.Guild, sub: dict, form: dict) -> Optional[discord.TextChannel]:
        applicant = guild.get_member(sub["user_id"])
        review = guild.get_channel(sub["channel_id"])
        category = guild.get_channel(form["interview_category_id"]) if form["interview_category_id"] else getattr(review, "category", None)
        overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False)}
        view_send = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True)
        if applicant is not None:
            overwrites[applicant] = view_send
        for role_id in form["roles"]["reviewers"]:
            role = guild.get_role(role_id)
            if role is not None:
                overwrites[role] = view_send
        overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, embed_links=True)
        try:
            channel = await guild.create_text_channel(
                _clip(f"interview-{sub['app_id']}", 100), category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites, topic=f"Interview for application #{sub['app_id']}", reason=f"Application #{sub['app_id']} interview",
            )
            mention = applicant.mention if applicant else f"<@{sub['user_id']}>"
            await channel.send(
                view=info_layout(f"Interview for application #{sub['app_id']}", f"{mention}, staff would like to talk to you about your **{form['title'] or sub['form']}** application. Please answer here."),
                allowed_mentions=discord.AllowedMentions(users=[applicant] if applicant else False),
            )
        except discord.HTTPException:
            return None
        await store.update_sub(guild.id, sub["app_id"], interview_channel_id=channel.id)
        return channel

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        rows = await db.raw_fetch("SELECT app_id, form FROM app_submissions WHERE guild_id=? AND user_id=? AND status='pending'", (member.guild.id, member.id))
        for row in rows:
            form = await store.get_form(member.guild.id, row["form"])
            if form is not None and form["autodeny_leave"]:
                await self.decide(member.guild, row["app_id"], False, None, "The applicant left the server.", automatic=True)

    async def _form(self, ctx: commands.Context, name: str) -> Optional[dict]:
        form = await store.get_form(ctx.guild.id, name)
        if form is None:
            await ctx.send(view=error_layout("Not found", f"There is no application called `{name.lower()}`. Use `application forms` to see them."))
        return form

    async def _question(self, ctx: commands.Context, name: str, number: int):
        form = await self._form(ctx, name)
        if form is None:
            return None, None
        if not 1 <= number <= len(form["questions"]):
            await ctx.send(view=error_layout("Not found", f"`{name.lower()}` has {len(form['questions'])} question(s)."))
            return None, None
        return form, form["questions"][number - 1]

    @commands.group(name="application", aliases=["app", "apps", "applications"], invoke_without_command=True, help="Application forms, reviews and panels.")
    @commands.guild_only()
    async def application(self, ctx: commands.Context):
        e = emoji_manager.get
        body = (
            "Members apply through a private step-by-step form. Staff review each one with buttons, votes, threads and interview channels.\n\n"
            "**Everyone:** `application mine` `application withdraw <id>`\n"
            "**Reviewers:** `application list [form] [status]` `application view <id>` `application accept <id> [note]` `application deny <id> [reason]` `application stats [form]` `application export [form]`\n"
            "**Setup (Manage Server):** `application create <name>` `application forms` `application info <form>` `application set <form> <setting> <value>` "
            "`application roles <form> <list> <add|remove|clear> [roles]` `application question ...` `application toggle <form>` `application autodelete <form> <on|off> [minutes]` `application delete <form>` "
            "`application panel #channel <forms>` `application apply <form>`"
        )
        await ctx.send(view=info_layout(f"{e('settings')} Applications", body))

    @application.command(name="create", help="Create an application form. Usage: application create <name> [title]")
    @has_guild_permission("manage_guild")
    async def app_create(self, ctx: commands.Context, name: str, *, title: str = ""):
        e = emoji_manager.get
        name = name.lower()
        if not name.replace("-", "").replace("_", "").isalnum() or len(name) > 32:
            return await ctx.send(view=error_layout("Invalid name", "Use up to 32 letters, numbers, `-` or `_`."))
        forms = await store.list_forms(ctx.guild.id)
        if name in forms:
            return await ctx.send(view=error_layout("Already exists", f"`{name}` already exists."))
        limit = await premium_limits.get(ctx.guild.id, "application_forms")
        if len(forms) >= limit:
            return await ctx.send(view=error_layout("Limit reached", f"This server can have {limit} applications. Delete one." + await premium_limits.hint(ctx.guild.id, "application_forms")))
        await store.save_form(ctx.guild.id, name, store.new_form(title.strip()[:100] or name.replace("-", " ").title()))
        await ctx.send(view=success_layout(f"{e('check')} Application created", f"Next: `application question add {name} paragraph <question>` and `application set {name} channel #review-channel`."))

    @application.command(name="delete", aliases=["remove"], help="Delete an application form. Past submissions are kept.")
    @has_guild_permission("manage_guild")
    async def app_delete(self, ctx: commands.Context, name: str):
        e = emoji_manager.get
        if await self._form(ctx, name) is None:
            return
        await store.delete_form(ctx.guild.id, name)
        await ctx.send(view=success_layout(f"{e('check')} Application deleted", f"`{name.lower()}` was deleted. Existing submissions are kept."))

    @application.command(name="autodelete", aliases=["interviewdelete"], help="Delete interview channels after a decision. Usage: application autodelete <form> <on|off> [minutes]")
    @has_guild_permission("manage_guild")
    async def app_autodelete(self, ctx: commands.Context, name: str, state: str, minutes: Optional[int] = None):
        e = emoji_manager.get
        form = await self._form(ctx, name)
        if form is None:
            return
        if state.lower() not in ("on", "off") or (minutes is not None and not 0 <= minutes <= 1440):
            return await ctx.send(view=error_layout("Invalid", "Usage: `application autodelete <form> <on|off> [minutes 0-1440]`. Use 0 minutes to delete right away."))
        form["interview_delete"] = state.lower() == "on"
        if minutes is not None:
            form["interview_delay_minutes"] = minutes
        await store.save_form(ctx.guild.id, name, form)
        detail = f"after **{form['interview_delay_minutes']}** minute(s)" if form["interview_delay_minutes"] else "right away"
        await ctx.send(view=success_layout(f"{e('check')} Saved", f"Interview channels for `{name.lower()}` are {'deleted ' + detail + ' once the application is accepted or denied' if form['interview_delete'] else 'kept until you delete them'}."))

    async def _set_open(self, ctx: commands.Context, name: str, state: bool = None):
        e = emoji_manager.get
        form = await self._form(ctx, name)
        if form is None:
            return
        form["enabled"] = (not form["enabled"]) if state is None else state
        await store.save_form(ctx.guild.id, name, form)
        await self.refresh_panels(ctx.guild.id)
        text = "open" if form["enabled"] else "closed"
        extra = "" if form["enabled"] else " Its panel button turns red and members who press it are told it is closed."
        await ctx.send(view=success_layout(f"{e('check')} Application {'opened' if form['enabled'] else 'closed'}", f"`{name.lower()}` is now **{text}**.{extra}"))

    @application.command(name="toggle", help="Switch an application between open and closed.")
    @has_guild_permission("manage_guild")
    async def app_toggle(self, ctx: commands.Context, name: str):
        await self._set_open(ctx, name)

    @application.command(name="open", aliases=["on", "enable"], help="Open an application so members can apply.")
    @has_guild_permission("manage_guild")
    async def app_open(self, ctx: commands.Context, name: str):
        await self._set_open(ctx, name, True)

    @application.command(name="close", aliases=["off", "disable"], help="Close an application. Its panel button turns red.")
    @has_guild_permission("manage_guild")
    async def app_close(self, ctx: commands.Context, name: str):
        await self._set_open(ctx, name, False)

    @application.command(name="forms", aliases=["all"], help="List the application forms.")
    @commands.guild_only()
    async def app_forms(self, ctx: commands.Context):
        forms = await store.list_forms(ctx.guild.id)
        if not forms:
            return await ctx.send(view=info_layout("Applications", "No applications yet. Create one with `application create <name>`."))
        lines = [f"`{n}` - {f['title']} ({'open' if f['enabled'] else 'closed'}, {len(f['questions'])} question(s))" for n, f in forms.items()]
        await ctx.send(view=info_layout("Applications", "\n".join(lines)))

    @application.command(name="info", help="Show an application's settings.")
    @has_guild_permission("manage_guild")
    async def app_info(self, ctx: commands.Context, name: str):
        form = await self._form(ctx, name)
        if form is None:
            return
        channel = f"<#{form['channel_id']}>" if form["channel_id"] else "not set"
        category = f"<#{form['interview_category_id']}>" if form["interview_category_id"] else "same as review channel"
        cleanup = "yes, after " + str(form["interview_delay_minutes"]) + "m" if form["interview_delete"] else "no"
        roles = "\n".join(f"{key}: {' '.join(f'<@&{r}>' for r in ids) or 'none'}" for key, ids in form["roles"].items())
        questions = "\n".join(f"{n}. [{q['type']}] {_clip(q['text'], 80)}{'' if q['required'] else ' (optional)'}" for n, q in enumerate(form["questions"], 1)) or "none"
        body = (
            f"**Title:** {form['title']}\n**Status:** {'open' if form['enabled'] else 'closed'}\n**Review channel:** {channel}\n**Interview category:** {category}, **delete after decision:** {cleanup}\n"
            f"**Cooldown:** {form['cooldown_hours']}h, **account age:** {form['min_account_days']}d, **join age:** {form['min_join_days']}d, **slots:** {form['slots'] or 'unlimited'} ({form['accepted']} accepted)\n"
            f"**Thread:** {form['thread']}, **votes:** {form['votes']}, **deny reason required:** {form['require_reason']}, **auto deny on leave:** {form['autodeny_leave']}\n\n"
            f"**Roles**\n{roles}\n\n**Questions**\n{questions}"
        )
        await ctx.send(view=info_layout(f"Application: {name.lower()}", _clip(body, 3800)))

    @application.command(name="set", help="Change a setting. Usage: application set <form> <setting> <value>")
    @has_guild_permission("manage_guild")
    async def app_set(self, ctx: commands.Context, name: str, key: str, *, value: str):
        e = emoji_manager.get
        form = await self._form(ctx, name)
        if form is None:
            return
        spec = SETTING_KEYS.get(key.lower())
        if spec is None:
            return await ctx.send(view=error_layout("Unknown setting", "Settings: " + ", ".join(f"`{k}`" for k in SETTING_KEYS)))
        kind, field, limit = spec
        value = value.strip()
        try:
            if kind == "text":
                parsed = value[:limit]
            elif kind == "color":
                parsed = "#" + value.lstrip("#").upper()
                int(parsed[1:], 16)
                if len(parsed) != 7:
                    raise ValueError
            elif kind == "int":
                parsed = int(value)
                if not 0 <= parsed <= limit:
                    raise ValueError
            elif kind == "bool":
                if value.lower() not in ("on", "off", "true", "false", "yes", "no"):
                    raise ValueError
                parsed = value.lower() in ("on", "true", "yes")
            elif kind == "channel":
                parsed = None if value.lower() in ("none", "off") else (await commands.TextChannelConverter().convert(ctx, value)).id
            else:
                parsed = None if value.lower() in ("none", "off") else (await commands.CategoryChannelConverter().convert(ctx, value)).id
        except (ValueError, commands.BadArgument):
            return await ctx.send(view=error_layout("Invalid value", {"int": f"Use a whole number from 0 to {limit}.", "bool": "Use `on` or `off`.", "color": "Use a hex colour like `#FF69B4`.", "channel": "Mention a text channel or use `none`.", "category": "Give a category or use `none`."}.get(kind, "That value is not valid.")))
        form[field] = parsed
        await store.save_form(ctx.guild.id, name, form)
        await ctx.send(view=success_layout(f"{e('check')} Saved", f"`{key.lower()}` was updated for `{name.lower()}`."))

    @application.command(name="roles", help="Edit a role list. Usage: application roles <form> <list> <add|remove|clear> [roles]")
    @has_guild_permission("manage_guild")
    async def app_roles(self, ctx: commands.Context, name: str, which: str, action: str, roles: commands.Greedy[discord.Role]):
        e = emoji_manager.get
        form = await self._form(ctx, name)
        if form is None:
            return
        which = which.lower().replace("-", "_")
        if which not in ROLE_LISTS or action.lower() not in ("add", "remove", "clear"):
            return await ctx.send(view=error_layout("Invalid", "Lists:\n" + "\n".join(f"`{k}` - {v}" for k, v in ROLE_LISTS.items()) + "\nActions: `add`, `remove`, `clear`."))
        current = form["roles"][which]
        if action.lower() == "clear":
            current.clear()
        else:
            if not roles:
                return await ctx.send(view=error_layout("No roles", "Mention at least one role."))
            for role in roles:
                if action.lower() == "add" and role.id not in current:
                    current.append(role.id)
                elif action.lower() == "remove" and role.id in current:
                    current.remove(role.id)
        await store.save_form(ctx.guild.id, name, form)
        await ctx.send(view=success_layout(f"{e('check')} Saved", f"`{which}`: {' '.join(f'<@&{r}>' for r in current) or 'none'}"), allowed_mentions=NO_MENTIONS)

    @application.group(name="question", aliases=["q", "questions"], invoke_without_command=True, help="Manage questions.")
    @has_guild_permission("manage_guild")
    async def app_question(self, ctx: commands.Context):
        types = "\n".join(f"`{k}` - {v}" for k, v in QUESTION_TYPES.items())
        await ctx.send(view=info_layout("Questions", f"`application question add <form> <type> <text>`\n`edit <form> <n> <text>` `remove <form> <n>` `move <form> <n> <to>`\n`required <form> <n> <on|off>` `options <form> <n> <a | b | c>` `list <form>`\n\n**Types**\n{types}"))

    @app_question.command(name="add", help="Add a question. Usage: application question add <form> <type> <text>")
    async def q_add(self, ctx: commands.Context, name: str, qtype: str, *, text: str):
        e = emoji_manager.get
        form = await self._form(ctx, name)
        if form is None:
            return
        qtype = qtype.lower()
        if qtype not in QUESTION_TYPES:
            return await ctx.send(view=error_layout("Unknown type", "Types: " + ", ".join(f"`{k}`" for k in QUESTION_TYPES)))
        cap = await premium_limits.get(ctx.guild.id, "application_questions")
        if len(form["questions"]) >= cap:
            return await ctx.send(view=error_layout("Limit reached", f"An application can have {cap} questions." + await premium_limits.hint(ctx.guild.id, "application_questions")))
        if len(text) > 300:
            return await ctx.send(view=error_layout("Too long", "Questions must be 300 characters or fewer."))
        form["questions"].append({"type": qtype, "text": text.strip(), "required": True, "options": ["Yes", "No"] if qtype == "yesno" else []})
        await store.save_form(ctx.guild.id, name, form)
        hint = f" Now set its options: `application question options {name.lower()} {len(form['questions'])} first | second | third`." if qtype in ("choice", "multi") else ""
        await ctx.send(view=success_layout(f"{e('check')} Question added", f"`{name.lower()}` now has **{len(form['questions'])}** question(s).{hint}"))

    @app_question.command(name="edit", help="Change a question's text.")
    async def q_edit(self, ctx: commands.Context, name: str, number: int, *, text: str):
        e = emoji_manager.get
        form, question = await self._question(ctx, name, number)
        if question is None:
            return
        question["text"] = text.strip()[:300]
        await store.save_form(ctx.guild.id, name, form)
        await ctx.send(view=success_layout(f"{e('check')} Question updated", f"Question {number} was updated."))

    @app_question.command(name="remove", aliases=["delete"], help="Remove a question.")
    async def q_remove(self, ctx: commands.Context, name: str, number: int):
        e = emoji_manager.get
        form, question = await self._question(ctx, name, number)
        if question is None:
            return
        form["questions"].pop(number - 1)
        await store.save_form(ctx.guild.id, name, form)
        await ctx.send(view=success_layout(f"{e('check')} Question removed", f"`{name.lower()}` has {len(form['questions'])} question(s) left."))

    @app_question.command(name="move", help="Move a question. Usage: application question move <form> <n> <to>")
    async def q_move(self, ctx: commands.Context, name: str, number: int, to: int):
        e = emoji_manager.get
        form, question = await self._question(ctx, name, number)
        if question is None:
            return
        to = max(1, min(to, len(form["questions"])))
        form["questions"].insert(to - 1, form["questions"].pop(number - 1))
        await store.save_form(ctx.guild.id, name, form)
        await ctx.send(view=success_layout(f"{e('check')} Question moved", f"Question {number} is now number {to}."))

    @app_question.command(name="required", help="Make a question required or optional.")
    async def q_required(self, ctx: commands.Context, name: str, number: int, state: str):
        e = emoji_manager.get
        form, question = await self._question(ctx, name, number)
        if question is None:
            return
        if state.lower() not in ("on", "off"):
            return await ctx.send(view=error_layout("Invalid", "Use `on` or `off`."))
        question["required"] = state.lower() == "on"
        await store.save_form(ctx.guild.id, name, form)
        await ctx.send(view=success_layout(f"{e('check')} Saved", f"Question {number} is now {'required' if question['required'] else 'optional'}."))

    @app_question.command(name="options", help="Set the options of a choice question. Usage: application question options <form> <n> <a | b | c>")
    async def q_options(self, ctx: commands.Context, name: str, number: int, *, options: str):
        e = emoji_manager.get
        form, question = await self._question(ctx, name, number)
        if question is None:
            return
        if question["type"] not in ("choice", "multi"):
            return await ctx.send(view=error_layout("Not a choice question", "Only `choice` and `multi` questions have options."))
        values = [o.strip() for o in options.split("|") if o.strip()]
        if not 2 <= len(values) <= MAX_OPTIONS or any(len(v) > 100 for v in values):
            return await ctx.send(view=error_layout("Invalid options", f"Give 2 to {MAX_OPTIONS} options separated by `|`, each 100 characters or fewer."))
        question["options"] = values
        await store.save_form(ctx.guild.id, name, form)
        await ctx.send(view=success_layout(f"{e('check')} Options saved", f"Question {number} has {len(values)} options."))

    @app_question.command(name="list", help="List an application's questions.")
    async def q_list(self, ctx: commands.Context, name: str):
        form = await self._form(ctx, name)
        if form is None:
            return
        lines = []
        for n, q in enumerate(form["questions"], 1):
            extra = f" - {' | '.join(q['options'])}" if q["options"] and q["type"] != "yesno" else ""
            lines.append(f"**{n}.** [{q['type']}] {_clip(q['text'], 150)}{'' if q['required'] else ' (optional)'}{_clip(extra, 150)}")
        await ctx.send(view=info_layout(f"Questions for {name.lower()}", _clip("\n".join(lines) or "No questions yet.", 3800)))

    @application.command(name="panel", help="Post an apply panel. Usage: application panel #channel <form> [form...]")
    @has_guild_permission("manage_guild")
    async def app_panel(self, ctx: commands.Context, channel: discord.TextChannel, *names: str):
        e = emoji_manager.get
        entries = []
        for name in names[:25]:
            form = await store.get_form(ctx.guild.id, name)
            if form is None:
                return await ctx.send(view=error_layout("Not found", f"There is no application called `{name.lower()}`."))
            entries.append((name.lower(), form))
        if not entries:
            return await ctx.send(view=error_layout("No forms", "Name at least one application."))
        try:
            message = await channel.send(view=panel_layout(entries))
        except discord.HTTPException:
            return await ctx.send(view=error_layout("Can't post", f"I cannot send messages in {channel.mention}."))
        await store.record_panel(ctx.guild.id, channel.id, message.id, [n for n, _ in entries], store.panel_state(entries))
        await ctx.send(view=success_layout(f"{e('check')} Panel posted", f"The apply panel is in {channel.mention}."))

    @application.command(name="apply", help="Start an application. Usage: application apply <form>")
    @commands.guild_only()
    async def app_apply(self, ctx: commands.Context, name: str):
        form = await self._form(ctx, name)
        if form is None:
            return
        await ctx.send(view=panel_layout([(name.lower(), form)]))

    @application.command(name="mine", aliases=["my", "status"], help="Show your applications.")
    @commands.guild_only()
    async def app_mine(self, ctx: commands.Context):
        rows = await db.raw_fetch("SELECT app_id, form, status, created_at FROM app_submissions WHERE guild_id=? AND user_id=? ORDER BY app_id DESC LIMIT 15", (ctx.guild.id, ctx.author.id))
        if not rows:
            return await ctx.send(view=info_layout("Your applications", "You have not applied yet."))
        lines = [f"**#{r['app_id']}** `{r['form']}` - {STATUS_LABELS.get(r['status'], r['status'])} (<t:{int(r['created_at'])}:R>)" for r in rows]
        await ctx.send(view=info_layout("Your applications", "\n".join(lines)))

    @application.command(name="withdraw", aliases=["cancel"], help="Withdraw a pending application. Usage: application withdraw <id>")
    @commands.guild_only()
    async def app_withdraw(self, ctx: commands.Context, app_id: int):
        e = emoji_manager.get
        sub = await store.get_sub(ctx.guild.id, app_id)
        if sub is None or sub["user_id"] != ctx.author.id:
            return await ctx.send(view=error_layout("Not found", "You have no application with that number."))
        if sub["status"] != "pending":
            return await ctx.send(view=error_layout("Already decided", "Only pending applications can be withdrawn."))
        await store.update_sub(ctx.guild.id, app_id, status="withdrawn", decided_at=time.time(), reviewer_id=ctx.author.id, reason="Withdrawn by the applicant")
        sub.update(status="withdrawn", decided_at=time.time(), reviewer_id=ctx.author.id, reason="Withdrawn by the applicant")
        await self._refresh_review(ctx.guild, sub)
        await ctx.send(view=success_layout(f"{e('check')} Withdrawn", f"Application #{app_id} was withdrawn."))

    async def _reviewer_sub(self, ctx: commands.Context, app_id: int):
        sub = await store.get_sub(ctx.guild.id, app_id)
        if sub is None:
            await ctx.send(view=error_layout("Not found", f"There is no application #{app_id}."))
            return None, None
        form = await store.get_form(ctx.guild.id, sub["form"]) or store._merge({})
        if not self.is_reviewer(ctx.author, form):
            await ctx.send(view=error_layout("No permission", "Only reviewers can do that."))
            return None, None
        return sub, form

    @application.command(name="view", aliases=["show"], help="Show an application with all answers. Usage: application view <id>")
    @commands.guild_only()
    async def app_view(self, ctx: commands.Context, app_id: int):
        sub, form = await self._reviewer_sub(ctx, app_id)
        if sub is None:
            return
        head = f"**Applicant:** <@{sub['user_id']}>\n**Form:** {form['title'] or sub['form']}\n**Status:** {STATUS_LABELS.get(sub['status'], sub['status'])}\n**Submitted:** <t:{int(sub['created_at'])}:R>"
        chunks, current = [], head
        for number, item in enumerate(sub["answers"], 1):
            block = f"\n\n**{number}. {_clip(item['q'], 200)}**\n{_clip(item['a'], 1000)}"
            if len(current) + len(block) > 3500:
                chunks.append(current)
                current = block.strip()
            else:
                current += block
        chunks.append(current)
        for index, chunk in enumerate(chunks):
            await ctx.send(view=info_layout(f"Application #{app_id}" + (f" ({index + 1}/{len(chunks)})" if len(chunks) > 1 else ""), chunk), allowed_mentions=NO_MENTIONS)

    @application.command(name="accept", help="Accept an application. Usage: application accept <id> [note]")
    @commands.guild_only()
    async def app_accept(self, ctx: commands.Context, app_id: int, *, note: str = ""):
        ok, message = await self.decide(ctx.guild, app_id, True, ctx.author, note.strip()[:500])
        await ctx.send(view=(success_layout if ok else error_layout)("Application" if ok else "Cannot accept", message))

    @application.command(name="deny", help="Deny an application. Usage: application deny <id> [reason]")
    @commands.guild_only()
    async def app_deny(self, ctx: commands.Context, app_id: int, *, reason: str = ""):
        sub = await store.get_sub(ctx.guild.id, app_id)
        form = await store.get_form(ctx.guild.id, sub["form"]) if sub else None
        if form is not None and form["require_reason"] and not reason.strip():
            return await ctx.send(view=error_layout("Reason needed", "This application needs a reason when denying. Usage: `application deny <id> <reason>`."))
        ok, message = await self.decide(ctx.guild, app_id, False, ctx.author, reason.strip()[:500])
        await ctx.send(view=(success_layout if ok else error_layout)("Application" if ok else "Cannot deny", message))

    @application.command(name="list", help="List applications. Usage: application list [form] [pending|accepted|denied|withdrawn]")
    @commands.guild_only()
    async def app_list(self, ctx: commands.Context, name: Optional[str] = None, status: str = "pending"):
        if name and name.lower() in STATUS_LABELS:
            name, status = None, name.lower()
        if not ctx.author.guild_permissions.manage_guild:
            forms = await store.list_forms(ctx.guild.id)
            if not any(self.is_reviewer(ctx.author, f) for f in forms.values()):
                return await ctx.send(view=error_layout("No permission", "Only reviewers can do that."))
        if status.lower() not in STATUS_LABELS:
            return await ctx.send(view=error_layout("Invalid status", "Use pending, accepted, denied or withdrawn."))
        query = "SELECT app_id, form, user_id, created_at FROM app_submissions WHERE guild_id=? AND status=?"
        params: list = [ctx.guild.id, status.lower()]
        if name:
            query += " AND form=?"
            params.append(name.lower())
        rows = await db.raw_fetch(query + " ORDER BY app_id DESC LIMIT 15", tuple(params))
        if not rows:
            return await ctx.send(view=info_layout("Applications", f"No {status.lower()} applications."))
        lines = [f"**#{r['app_id']}** `{r['form']}` <@{r['user_id']}> (<t:{int(r['created_at'])}:R>)" for r in rows]
        await ctx.send(view=info_layout(f"{STATUS_LABELS[status.lower()]} applications", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @application.command(name="stats", help="Show application statistics. Usage: application stats [form]")
    @has_guild_permission("manage_guild")
    async def app_stats(self, ctx: commands.Context, name: Optional[str] = None):
        query = "SELECT status, COUNT(*) AS n FROM app_submissions WHERE guild_id=?"
        params: list = [ctx.guild.id]
        if name:
            query += " AND form=?"
            params.append(name.lower())
        rows = await db.raw_fetch(query + " GROUP BY status", tuple(params))
        tally = {r["status"]: r["n"] for r in rows}
        total = sum(tally.values())
        decided = tally.get("accepted", 0) + tally.get("denied", 0)
        rate = f"{round(tally.get('accepted', 0) / decided * 100)}%" if decided else "n/a"
        body = "\n".join(f"**{label}:** {tally.get(key, 0)}" for key, label in STATUS_LABELS.items()) + f"\n**Total:** {total}\n**Acceptance rate:** {rate}"
        await ctx.send(view=info_layout(f"Application stats{' for ' + name.lower() if name else ''}", body))

    @application.command(name="export", help="Export applications to CSV. Usage: application export [form]")
    @has_guild_permission("manage_guild")
    async def app_export(self, ctx: commands.Context, name: Optional[str] = None):
        query = "SELECT * FROM app_submissions WHERE guild_id=?"
        params: list = [ctx.guild.id]
        if name:
            query += " AND form=?"
            params.append(name.lower())
        rows = await db.raw_fetch(query + " ORDER BY app_id LIMIT 5000", tuple(params))
        if not rows:
            return await ctx.send(view=error_layout("Nothing to export", "No applications found."))

        def safe(value) -> str:
            text = "" if value is None else str(value)
            return "'" + text if text[:1] in ("=", "+", "-", "@") else text

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "form", "user_id", "status", "reviewer_id", "reason", "submitted", "decided", "answers"])
        for row in rows:
            sub = store._sub(row)
            answers = " || ".join(f"{a['q']}: {a['a']}" for a in sub["answers"])
            writer.writerow([sub["app_id"], safe(sub["form"]), sub["user_id"], sub["status"], sub["reviewer_id"] or "", safe(sub["reason"]), datetime.fromtimestamp(sub["created_at"], timezone.utc).isoformat(), datetime.fromtimestamp(sub["decided_at"], timezone.utc).isoformat() if sub["decided_at"] else "", safe(answers)])
        await ctx.send(file=discord.File(io.BytesIO(buffer.getvalue().encode("utf-8")), "applications.csv"))


async def setup(bot: commands.Bot):
    await bot.add_cog(Applications(bot))
