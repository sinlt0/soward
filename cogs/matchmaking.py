import time
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import emoji_manager, matchmaking as store, profiles
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

NO_MENTIONS = discord.AllowedMentions.none()
USERS = discord.AllowedMentions(users=True)
EXTEND_SECONDS = 300


def session_layout(session: dict, state: str = "live", note: str = "") -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=0xEB459E if state == "live" else 0x95A5A6)
    if state == "live":
        body = (f"## Speed date\n<@{session['user_a']}> and <@{session['user_b']}>, you were matched on shared interests.\n"
                f"This private room closes <t:{int(session['ends_at'])}:R>. Be kind. You can leave at any time.")
        if note:
            body += f"\n\n{note}"
        container.add_item(discord.ui.TextDisplay(body))
        row = discord.ui.ActionRow()
        sid = session["session_id"]
        row.add_item(discord.ui.Button(label="Interested", style=discord.ButtonStyle.success, custom_id=f"match:yes:{sid}"))
        row.add_item(discord.ui.Button(label="Not for me", style=discord.ButtonStyle.secondary, custom_id=f"match:no:{sid}"))
        if not session.get("extended"):
            row.add_item(discord.ui.Button(label="+5 min", style=discord.ButtonStyle.primary, custom_id=f"match:more:{sid}"))
        row.add_item(discord.ui.Button(label="Report", style=discord.ButtonStyle.danger, custom_id=f"match:report:{sid}"))
        container.add_item(row)
    else:
        container.add_item(discord.ui.TextDisplay(f"## Speed date ended\n{note}"))
    view.add_item(container)
    return view


def panel_layout(minutes: int) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=0xEB459E)
    container.add_item(discord.ui.TextDisplay(
        f"## Speed dating\nPress **Join** and the bot pairs you with someone who shares your interests. You both get a private voice room for {minutes} minutes. "
        "Afterwards you only learn about each other if you **both** pressed Interested.\n\nYou need a profile first (`profile edit`)."))
    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="Join queue", style=discord.ButtonStyle.success, custom_id="match:join:0"))
    row.add_item(discord.ui.Button(label="Leave queue", style=discord.ButtonStyle.secondary, custom_id="match:leave:0"))
    container.add_item(row)
    view.add_item(container)
    return view


class ReportModal(discord.ui.Modal, title="Report your match"):
    reason = discord.ui.TextInput(label="What happened?", style=discord.TextStyle.paragraph, min_length=5, max_length=500)

    def __init__(self, cog: "Matchmaking", session: dict, target_id: int):
        super().__init__(timeout=300)
        self.cog = cog
        self.session = session
        self.target_id = target_id

    async def on_submit(self, interaction: discord.Interaction):
        reports = self.cog.bot.get_cog("Reports")
        report_id = None
        if reports is not None:
            report_id = await reports.report_manual(
                interaction.guild, interaction.user.id, self.target_id, str(self.reason.value), "match",
                [{"id": 0, "author": interaction.user.id, "content": "Speed date session " + self.session["session_id"], "at": int(time.time())}])
        await interaction.response.send_message(
            "Your report was sent to the staff." if report_id else "Reports are not set up here, but the match was ended and blocked.", ephemeral=True)
        await self.cog.close_session(interaction.guild, self.session["session_id"], "A report was filed, so the room was closed.", block_pair=True)


class Matchmaking(commands.Cog):
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    async def eligibility(self, guild: discord.Guild, member: discord.Member) -> Optional[str]:
        cfg = await store.get_config(guild.id)
        if not cfg["enabled"]:
            return "Speed dating is not turned on here."
        if cfg["role"] and not any(r.id == int(cfg["role"]) for r in member.roles):
            return "You do not have the role needed for speed dating."
        age = (time.time() - member.created_at.timestamp()) / 86400
        if age < cfg["age"]:
            return f"Your account must be at least {cfg['age']} days old."
        data = await profiles.get(member.id)
        if data is None or data["hidden"]:
            return "Make a visible profile first with `profile edit`."
        if not data["interests"]:
            return "Add at least one interest to your profile so I can match you."
        if await store.active_for(guild.id, member.id):
            return "You are already in a speed date."
        return None

    async def join_queue(self, guild: discord.Guild, member: discord.Member) -> str:
        problem = await self.eligibility(guild, member)
        if problem:
            return problem
        if await store.in_queue(guild.id, member.id):
            return "You are already in the queue."
        await store.join(guild.id, member.id)
        return "You are in the queue. I will pair you as soon as someone fitting joins. Leave any time with `match leave`."

    async def leave_queue(self, guild: discord.Guild, member: discord.Member) -> str:
        if not await store.in_queue(guild.id, member.id):
            return "You are not in the queue."
        await store.leave(guild.id, member.id)
        return "You left the queue."

    async def start_session(self, guild: discord.Guild, cfg: dict, a: discord.Member, b: discord.Member) -> bool:
        category = guild.get_channel(int(cfg["category"])) if cfg["category"] else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, connect=True, manage_channels=True, send_messages=True),
        }
        for person in (a, b):
            overwrites[person] = discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, send_messages=True, read_message_history=True)
        try:
            voice = await guild.create_voice_channel(
                "speed-date", category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites, user_limit=2, reason="Speed dating match")
        except discord.HTTPException:
            return False
        session_id = await store.create_session(guild.id, a.id, b.id, voice.id, cfg["minutes"])
        session = await store.get_session(session_id)
        try:
            message = await voice.send(content=f"{a.mention} {b.mention}", view=session_layout(session), allowed_mentions=USERS)
            await store.remember_message(session_id, message.id)
        except discord.HTTPException:
            pass
        link = f"Your speed date is ready: {voice.mention}. It closes in {cfg['minutes']} minutes."
        channel = guild.get_channel(int(cfg["channel"])) if cfg["channel"] else None
        if channel is not None:
            try:
                await channel.send(f"{a.mention} {b.mention} {link}", allowed_mentions=USERS, delete_after=120)
            except discord.HTTPException:
                pass
        return True

    async def close_session(self, guild: discord.Guild, session_id: str, note: str, block_pair: bool = False) -> None:
        session = await store.get_session(session_id)
        if session is None or session["status"] != "active":
            return
        await store.finish(session_id)
        if block_pair:
            await store.block(guild.id, session["user_a"], session["user_b"])
            await store.block(guild.id, session["user_b"], session["user_a"])
        mutual = session.get("choice_a") == 1 and session.get("choice_b") == 1
        voice = guild.get_channel(session["voice_id"]) if session["voice_id"] else None
        if mutual and not block_pair:
            for me, other in ((session["user_a"], session["user_b"]), (session["user_b"], session["user_a"])):
                user = guild.get_member(me)
                if user is None:
                    continue
                try:
                    await user.send(view=success_layout("It is a match", f"You and <@{other}> both pressed Interested after your speed date in **{guild.name}**. Say hi!"))
                except discord.HTTPException:
                    pass
        if voice is not None:
            try:
                await voice.delete(reason="Speed date ended")
            except discord.HTTPException:
                pass

    @tasks.loop(seconds=15)
    async def loop(self):
        for guild in self.bot.guilds:
            cfg = await store.get_config(guild.id)
            for session in await store.active(guild.id):
                voice = guild.get_channel(session["voice_id"]) if session["voice_id"] else None
                if voice is None or time.time() >= session["ends_at"]:
                    await self.close_session(guild, session["session_id"], "Time is up.")
            if not cfg["enabled"]:
                continue
            entries = []
            for entry in await store.queue(guild.id):
                member = guild.get_member(entry["user_id"])
                if member is None or await store.active_for(guild.id, member.id):
                    await store.leave(guild.id, entry["user_id"])
                    continue
                entries.append(entry)
            if len(entries) < 2:
                continue
            interests = {}
            for entry in entries:
                data = await profiles.get(entry["user_id"])
                if data is None or data["hidden"]:
                    await store.leave(guild.id, entry["user_id"])
                    continue
                interests[entry["user_id"]] = data["interests"]
            entries = [e for e in entries if e["user_id"] in interests]
            banned = await store.blocks(guild.id) | await store.recent_pairs(guild.id)
            for a_id, b_id in store.pick_pairs(entries, interests, banned):
                a, b = guild.get_member(a_id), guild.get_member(b_id)
                await store.leave(guild.id, a_id)
                await store.leave(guild.id, b_id)
                if a and b:
                    await self.start_session(guild, cfg, a, b)

    @loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if not custom_id.startswith("match:"):
            return
        parts = custom_id.split(":", 2)
        if len(parts) != 3:
            return
        act, sid = parts[1], parts[2]
        guild, member = interaction.guild, interaction.user
        if act == "join":
            return await interaction.response.send_message(await self.join_queue(guild, member), ephemeral=True)
        if act == "leave":
            return await interaction.response.send_message(await self.leave_queue(guild, member), ephemeral=True)
        session = await store.get_session(sid)
        if session is None or session["status"] != "active" or member.id not in (session["user_a"], session["user_b"]):
            return await interaction.response.send_message("This speed date is not yours or has ended.", ephemeral=True)
        other = session["user_b"] if member.id == session["user_a"] else session["user_a"]
        if act == "report":
            return await interaction.response.send_modal(ReportModal(self, session, other))
        if act == "more":
            if session["extended"]:
                return await interaction.response.send_message("The room was already extended once.", ephemeral=True)
            await store.extend(sid, EXTEND_SECONDS)
            session = await store.get_session(sid)
            await interaction.response.edit_message(view=session_layout(session, note="The room was extended by 5 minutes."), allowed_mentions=USERS)
            return
        if act in ("yes", "no"):
            session = await store.choose(session, member.id, 1 if act == "yes" else 0)
            if act == "no":
                await interaction.response.send_message("Okay, closing the room.", ephemeral=True)
                return await self.close_session(guild, sid, "One of you ended the date.")
            if session.get("choice_a") == 1 and session.get("choice_b") == 1:
                await interaction.response.edit_message(view=session_layout(session, note="You are both interested. Stay as long as you like until the timer ends. I will DM you both."), allowed_mentions=USERS)
                return
            return await interaction.response.send_message("Saved. The other person only learns this if they feel the same.", ephemeral=True)

    @commands.group(name="match", aliases=["speeddate"], invoke_without_command=True, help="Speed dating: join the queue.")
    @commands.guild_only()
    async def match(self, ctx: commands.Context):
        await ctx.send(view=info_layout("Speed dating", "`match join` · `match leave` · `match status` · `match block <member>` · `match unblock <member>`"))

    @match.command(name="join", help="Join the speed dating queue.")
    async def match_join(self, ctx: commands.Context):
        text = await self.join_queue(ctx.guild, ctx.author)
        await ctx.send(view=info_layout("Speed dating", text))

    @match.command(name="leave", help="Leave the queue.")
    async def match_leave(self, ctx: commands.Context):
        await ctx.send(view=info_layout("Speed dating", await self.leave_queue(ctx.guild, ctx.author)))

    @match.command(name="status", help="See how many people are waiting.")
    async def match_status(self, ctx: commands.Context):
        queue = await store.queue(ctx.guild.id)
        mine = any(e["user_id"] == ctx.author.id for e in queue)
        await ctx.send(view=info_layout("Speed dating", f"**{len(queue)}** waiting. You are {'in' if mine else 'not in'} the queue."))

    @match.command(name="block", help="Never be matched with a member.")
    async def match_block(self, ctx: commands.Context, member: discord.Member):
        if member.id == ctx.author.id:
            return await ctx.send(view=error_layout("Invalid", "You cannot block yourself."))
        await store.block(ctx.guild.id, ctx.author.id, member.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Speed dating", f"You will not be matched with {member.display_name}."))

    @match.command(name="unblock", help="Allow matches with a member again.")
    async def match_unblock(self, ctx: commands.Context, member: discord.Member):
        await store.unblock(ctx.guild.id, ctx.author.id, member.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Speed dating", f"{member.display_name} can be matched with you again."))

    @match.command(name="panel", help="Post the join panel in this channel.")
    @has_guild_permission("manage_guild")
    async def match_panel(self, ctx: commands.Context):
        cfg = await store.get_config(ctx.guild.id)
        await ctx.send(view=panel_layout(cfg["minutes"]))

    @match.command(name="on", help="Turn speed dating on.")
    @has_guild_permission("manage_guild")
    async def match_on(self, ctx: commands.Context):
        await self._set(ctx, "enabled", True, "Speed dating is **on**.")

    @match.command(name="off", help="Turn speed dating off.")
    @has_guild_permission("manage_guild")
    async def match_off(self, ctx: commands.Context):
        await self._set(ctx, "enabled", False, "Speed dating is **off**.")

    @match.command(name="channel", help="Channel where match pings are posted.")
    @has_guild_permission("manage_guild")
    async def match_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await self._set(ctx, "channel", channel.id, f"Matches are announced in {channel.mention}.")

    @match.command(name="category", help="Category where private rooms are created.")
    @has_guild_permission("manage_guild")
    async def match_category(self, ctx: commands.Context, category: discord.CategoryChannel):
        await self._set(ctx, "category", category.id, f"Private rooms are created in **{category.name}**.")

    @match.command(name="role", help="Role required to take part. Leave empty for everyone.")
    @has_guild_permission("manage_guild")
    async def match_role(self, ctx: commands.Context, role: Optional[discord.Role] = None):
        await self._set(ctx, "role", role.id if role else None, f"Required role: {role.mention}." if role else "No role is required.")

    @match.command(name="age", help="Minimum account age in days.")
    @has_guild_permission("manage_guild")
    async def match_age(self, ctx: commands.Context, days: int):
        if not 0 <= days <= 3650:
            return await ctx.send(view=error_layout("Invalid number", "Use 0 to 3650."))
        await self._set(ctx, "age", days, f"Accounts must be **{days}** days old.")

    @match.command(name="minutes", help="Length of each speed date (3 to 60).")
    @has_guild_permission("manage_guild")
    async def match_minutes(self, ctx: commands.Context, minutes: int):
        if not 3 <= minutes <= 60:
            return await ctx.send(view=error_layout("Invalid number", "Use 3 to 60."))
        await self._set(ctx, "minutes", minutes, f"Speed dates last **{minutes}** minutes.")

    async def _set(self, ctx: commands.Context, name: str, value, text: str):
        await store.set_config(ctx.guild.id, name, value)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Speed dating", text), allowed_mentions=NO_MENTIONS)


async def setup(bot: commands.Bot):
    await bot.add_cog(Matchmaking(bot))
