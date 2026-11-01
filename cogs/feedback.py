import time

import discord
from discord.ext import commands

from utils import emoji_manager, feedback as store
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout

NO_MENTIONS = discord.AllowedMentions.none()
BUTTON_ID = "feedback:open"


def panel_layout() -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=0x5865F2)
    container.add_item(discord.ui.TextDisplay(
        "## Staff feedback\nPraise, a complaint or an idea about how the server or its staff work. It is **anonymous**: staff see what you write, never who sent it. "
        "Do not include details that would identify you.\n-# Up to 3 per day. For urgent problems or reports about a member, open a ticket instead."))
    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label="Send feedback", style=discord.ButtonStyle.primary, custom_id=BUTTON_ID))
    container.add_item(row)
    view.add_item(container)
    return view


def entry_layout(entry: dict) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    done = entry["status"] == "resolved"
    container = discord.ui.Container(accent_color=0x57F287 if done else 0xFEE75C)
    lines = [f"## Feedback `{entry['feedback_id']}`" + (f" · {entry['topic']}" if entry["topic"] else ""),
             f"**About:** {entry['about']}" if entry["about"] else "**About:** general",
             "", entry["body"], f"\n-# Anonymous · <t:{int(entry['created_at'])}:R>"]
    if done:
        lines.append(f"**Resolved** by <@{entry['handler_id']}>")
    container.add_item(discord.ui.TextDisplay("\n".join(lines)))
    if not done:
        row = discord.ui.ActionRow()
        row.add_item(discord.ui.Button(label="Mark resolved", style=discord.ButtonStyle.success, custom_id=f"feedback:done:{entry['feedback_id']}"))
        row.add_item(discord.ui.Button(label="Block this sender", style=discord.ButtonStyle.danger, custom_id=f"feedback:block:{entry['feedback_id']}"))
        container.add_item(row)
    view.add_item(container)
    return view


class FeedbackModal(discord.ui.Modal, title="Anonymous feedback"):
    topic = discord.ui.TextInput(label="Type", placeholder="praise, complaint or idea", max_length=30, required=False)
    about = discord.ui.TextInput(label="About which staff member? (optional)", max_length=60, required=False)
    body = discord.ui.TextInput(label="Your feedback", style=discord.TextStyle.paragraph, min_length=15, max_length=1500)

    def __init__(self, cog: "Feedback"):
        super().__init__(timeout=600)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(await self.cog.submit(interaction.guild, interaction.user.id, str(self.topic.value), str(self.about.value), str(self.body.value)), ephemeral=True)


class Feedback(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def submit(self, guild: discord.Guild, user_id: int, topic: str, about: str, body: str) -> str:
        cfg = await store.get_config(guild.id)
        channel = guild.get_channel(int(cfg["channel"])) if cfg["channel"] else None
        if not cfg["enabled"] or channel is None:
            return "Feedback is not set up in this server."
        digest = await store.author_hash(guild.id, user_id)
        if await store.blocked(guild.id, digest):
            return "You can no longer send feedback in this server."
        if await store.sent_today(guild.id, digest) >= store.DAILY_LIMIT:
            return "You have sent enough feedback for today. Try again tomorrow."
        feedback_id = await store.create(guild.id, digest, topic, about, body)
        entry = await store.get(guild.id, feedback_id)
        try:
            message = await channel.send(view=entry_layout(entry), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            return "I could not deliver it to the staff. Please try again later."
        await store.remember_message(feedback_id, channel.id, message.id)
        return "Your feedback was sent. Staff cannot see who wrote it."

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if custom_id == BUTTON_ID:
            return await interaction.response.send_modal(FeedbackModal(self))
        if not custom_id.startswith("feedback:"):
            return
        parts = custom_id.split(":", 2)
        if len(parts) != 3 or parts[1] not in ("done", "block"):
            return
        member = interaction.user
        if not isinstance(member, discord.Member) or not (member.guild_permissions.manage_guild or member.guild_permissions.administrator):
            return await interaction.response.send_message("Only managers can handle feedback.", ephemeral=True)
        entry = await store.get(interaction.guild.id, parts[2])
        if entry is None:
            return await interaction.response.send_message("That feedback no longer exists.", ephemeral=True)
        if parts[1] == "block":
            await store.block(interaction.guild.id, entry["author_hash"])
            await store.resolve(entry["feedback_id"], member.id)
            note = "The sender is blocked from sending more feedback. You still do not know who they are."
        else:
            await store.resolve(entry["feedback_id"], member.id)
            note = "Marked as resolved."
        entry = await store.get(interaction.guild.id, entry["feedback_id"])
        await interaction.response.edit_message(view=entry_layout(entry), allowed_mentions=NO_MENTIONS)
        await interaction.followup.send(note, ephemeral=True)

    @commands.group(name="feedback", invoke_without_command=True, help="Anonymous feedback about staff and the server.")
    @commands.guild_only()
    async def feedback(self, ctx: commands.Context):
        cfg = await store.get_config(ctx.guild.id)
        if cfg["enabled"]:
            await ctx.send(view=info_layout("Feedback", "Press the button on the feedback panel to send anonymous feedback to the staff."))
        else:
            await ctx.send(view=info_layout("Feedback", "Anonymous feedback is not turned on here."))

    @feedback.command(name="channel", help="Private channel where feedback arrives. Use a channel only managers can see.")
    @has_guild_permission("manage_guild")
    async def feedback_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await store.set_config(ctx.guild.id, "channel", channel.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Feedback", f"Feedback arrives in {channel.mention}. Make sure only managers can see it."))

    @feedback.command(name="on", help="Turn feedback on.")
    @has_guild_permission("manage_guild")
    async def feedback_on(self, ctx: commands.Context):
        await store.set_config(ctx.guild.id, "enabled", True)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Feedback", "Feedback is **on**. Post the panel with `feedback panel`."))

    @feedback.command(name="off", help="Turn feedback off.")
    @has_guild_permission("manage_guild")
    async def feedback_off(self, ctx: commands.Context):
        await store.set_config(ctx.guild.id, "enabled", False)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Feedback", "Feedback is **off**."))

    @feedback.command(name="panel", help="Post the Send feedback button here.")
    @has_guild_permission("manage_guild")
    async def feedback_panel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        try:
            await channel.send(view=panel_layout())
        except discord.HTTPException:
            return await ctx.send(view=error_layout("Could not post", f"I cannot send messages in {channel.mention}."))

    @feedback.command(name="summary", help="Repeated themes and staff mentioned more than once. Usage: feedback summary [days]")
    @has_guild_permission("manage_guild")
    async def feedback_summary(self, ctx: commands.Context, days: int = 30):
        days = max(1, min(365, days))
        data = store.summarize(await store.since(ctx.guild.id, time.time() - days * 86400))
        if not data["total"]:
            return await ctx.send(view=info_layout("Feedback summary", "No feedback in this period."))
        lines = [f"**{data['total']}** received, **{data['open']}** still open."]
        if data["topics"]:
            lines.append("**Types:** " + ", ".join(f"{k} ({v})" for k, v in data["topics"]))
        if data["about"]:
            lines.append("**Mentioned more than once:** " + ", ".join(f"{k} ({v})" for k, v in data["about"]))
        if data["themes"]:
            lines.append("**Repeated words:** " + ", ".join(f"{k} ({v})" for k, v in data["themes"]))
        await ctx.send(view=info_layout(f"Feedback summary · {days} days", "\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(Feedback(bot))
