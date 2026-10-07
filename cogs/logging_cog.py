import time
from typing import Optional

import discord
from discord.ext import commands

from utils import db, emoji_manager, guild_settings
from utils.colors import ERROR, NEUTRAL, SUCCESS
from utils.components import footer_block
from utils.events_bus import LOG_EVENT, bus
from utils.checks import has_guild_permission
import config


def _event_category(event: str) -> Optional[str]:
    for category, meta in config.LOG_CATEGORIES.items():
        if event in meta["events"]:
            return category
    return None


class Logging(commands.Cog):
    category = "Config"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._webhook_cache: dict[tuple, discord.Webhook] = {}
        bus.subscribe(LOG_EVENT, self._on_log_event)

    async def _get_disabled_events(self, guild_id: int) -> set:
        rows = await db.raw_fetch("SELECT event FROM log_disabled_events WHERE guild_id=?", (guild_id,))
        return {r["event"] for r in rows}

    async def _get_category_row(self, guild_id: int, category: str) -> Optional[dict]:
        return await db.raw_fetchone(
            "SELECT * FROM log_channels WHERE guild_id=? AND category=?",
            (guild_id, category),
        )

    async def _get_webhook(self, guild_id: int, category: str) -> Optional[discord.Webhook]:
        cache_key = (guild_id, category)
        if cache_key in self._webhook_cache:
            return self._webhook_cache[cache_key]

        row = await self._get_category_row(guild_id, category)
        if not row:
            return None

        if row["webhook_url"]:
            try:
                webhook = discord.Webhook.from_url(row["webhook_url"], client=self.bot)
                self._webhook_cache[cache_key] = webhook
                return webhook
            except (discord.InvalidData, ValueError):
                pass

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return None
        channel = guild.get_channel(int(row["channel_id"]))
        if not channel or not isinstance(channel, discord.TextChannel):
            return None

        try:
            webhook = await channel.create_webhook(name=f"{config.BOT_NAME} Logs")
        except discord.HTTPException:
            return None

        await db.raw_execute(
            "UPDATE log_channels SET webhook_url=? WHERE guild_id=? AND category=?",
            (webhook.url, guild_id, category),
        )
        self._webhook_cache[cache_key] = webhook
        return webhook

    async def _send_log_view(self, guild_id: int, category: str, view: discord.ui.LayoutView):
        webhook = await self._get_webhook(guild_id, category)
        if not webhook:
            return
        try:
            await webhook.send(
                view=view,
                username=f"{config.BOT_NAME} · {config.LOG_CATEGORIES[category]['label']}",
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except discord.NotFound:
            self._webhook_cache.pop((guild_id, category), None)
            await db.raw_execute(
                "UPDATE log_channels SET webhook_url=NULL WHERE guild_id=? AND category=?",
                (guild_id, category),
            )
        except discord.HTTPException:
            pass

    def _make_log_view(self, color: int, body: str) -> discord.ui.LayoutView:
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=color)
        container.add_item(discord.ui.TextDisplay(body))
        for item in footer_block():
            container.add_item(item)
        view.add_item(container)
        return view

    async def _on_log_event(self, *, guild_id: int, action: str, **kwargs):
        e = emoji_manager.get

        disabled = await self._get_disabled_events(guild_id)
        if action in disabled:
            return

        category = _event_category(action)
        if not category:
            return

        row = await self._get_category_row(guild_id, category)
        if not row:
            return

        ts = f"<t:{int(time.time())}:T>"
        color = NEUTRAL
        body = None

        MOD_ACTION_LABELS = {
            "ban": "Member banned", "softban": "Member softbanned", "unban": "Member unbanned", "kick": "Member kicked",
            "mute": "Member muted", "unmute": "Member unmuted", "warn": "Member warned",
            "purge": "Messages purged", "lockdown": "Channel locked", "unlock": "Channel unlocked",
            "slowmode": "Slowmode changed",
        }

        if action in MOD_ACTION_LABELS:
            color = NEUTRAL
            user_id = kwargs.get("user_id")
            mod_id = kwargs.get("moderator_id")
            reason = kwargs.get("reason", "No reason provided")
            case_id = kwargs.get("case_id", "N/A")
            body = (
                f"## {e('case')} {MOD_ACTION_LABELS[action]} · {ts}\n"
                f"**User:** <@{user_id}>\n"
                f"**Moderator:** <@{mod_id}>\n"
                "\n"
                f"**Reason:** {reason}\n"
                f"**Case:** `{case_id}`"
            )
        elif action == "automod_action":
            color = NEUTRAL
            user_id = kwargs.get("user_id")
            channel_id = kwargs.get("channel_id")
            detail = kwargs.get("detail", "")
            channel_text = f"<#{channel_id}>" if channel_id else "unknown channel"
            body = (
                f"## {e('automod_cat')} AutoMod · {ts}\n"
                f"**User:** <@{user_id}>\n"
                f"**Channel:** {channel_text}\n"
                "\n"
                f"**Detail:** {detail}"
            )
        elif action in ("antinuke_triggered", "antinuke_action"):
            color = ERROR
            actor_id = kwargs.get("actor_id")
            reason = kwargs.get("reason", "")
            punishment = kwargs.get("punishment", "")
            body = (
                f"## {e('antinuke_cat')} AntiNuke triggered · {ts}\n"
                f"**Actor:** <@{actor_id}>\n"
                "\n"
                f"**Reason:** {reason}\n"
                f"**Punishment:** `{punishment}`"
            )
        elif action == "antinuke_quarantine":
            color = ERROR
            user_id = kwargs.get("user_id")
            reason = kwargs.get("reason", "")
            body = (
                f"## {e('quarantine')} Quarantine · {ts}\n"
                f"**Member:** <@{user_id}>\n"
                "\n"
                f"**Reason:** {reason}"
            )
        elif action == "antinuke_quarantine_release":
            color = SUCCESS
            user_id = kwargs.get("user_id")
            body = f"## {e('check')} Quarantine released · {ts}\n**Member:** <@{user_id}>"
        elif action == "antiraid_action":
            color = ERROR
            user_id = kwargs.get("user_id")
            reason = kwargs.get("reason", "")
            action_taken = kwargs.get("action_taken", "")
            body = (
                f"## {e('antiraid')} AntiRaid · {ts}\n"
                f"**Member:** <@{user_id}>\n"
                "\n"
                f"**Reason:** {reason}\n"
                f"**Action:** `{action_taken}`"
            )
        elif action == "antiraid_raid_mode":
            active = kwargs.get("active", False)
            triggered_by = kwargs.get("triggered_by", "")
            ended_by = kwargs.get("ended_by")
            color = ERROR if active else SUCCESS
            if active:
                body = f"## {e('panic')} Raid mode activated · {ts}\n**Triggered by:** `{triggered_by}`"
            else:
                ended_text = f"<@{ended_by}>" if ended_by else "automatic expiry"
                body = f"## {e('check')} Raid mode deactivated · {ts}\n**Ended by:** {ended_text}"
        elif action == "member_join":
            color = SUCCESS
            user_id = kwargs.get("user_id")
            account_age = kwargs.get("account_age", "")
            body = (
                f"## {e('members')} Member joined · {ts}\n"
                f"**Member:** <@{user_id}>"
                + (f"\n\n**Account age:** {account_age}" if account_age else "")
            )
        elif action == "member_leave":
            color = NEUTRAL
            user_id = kwargs.get("user_id")
            body = f"## {e('members')} Member left · {ts}\n<@{user_id}>"
        elif action == "member_update":
            color = NEUTRAL
            user_id = kwargs.get("user_id")
            detail = kwargs.get("detail", "")
            body = f"## {e('members')} Member updated · {ts}\n**Member:** <@{user_id}>\n\n{detail}"
        elif action == "voice_state_update":
            color = NEUTRAL
            user_id = kwargs.get("user_id")
            detail = kwargs.get("detail", "")
            body = f"## {e('members')} Voice update · {ts}\n**Member:** <@{user_id}>\n\n{detail}"
        elif action == "autorole_action":
            color = NEUTRAL
            user_id = kwargs.get("user_id")
            detail = kwargs.get("detail", "")
            body = f"## {e('members')} AutoRole · {ts}\n**Member:** <@{user_id}>\n\n{detail}"
        elif action == "message_edit":
            color = NEUTRAL
            user_id = kwargs.get("user_id")
            channel_id = kwargs.get("channel_id")
            before = str(kwargs.get("before", ""))[:500]
            after = str(kwargs.get("after", ""))[:500]
            body = (
                f"## {e('info')} Message edited · {ts}\n"
                f"**Author:** <@{user_id}> in <#{channel_id}>\n"
                "\n"
                f"**Before:** {before}\n"
                "\n"
                f"**After:** {after}"
            )
        elif action == "message_delete":
            color = NEUTRAL
            user_id = kwargs.get("user_id")
            channel_id = kwargs.get("channel_id")
            content = str(kwargs.get("content", ""))[:1000]
            body = (
                f"## {e('purge')} Message deleted · {ts}\n"
                f"**Author:** <@{user_id}> in <#{channel_id}>\n"
                "\n"
                f"**Content:** {content or '*(empty or attachment)*'}"
            )
        elif action == "message_bulk_delete":
            color = NEUTRAL
            channel_id = kwargs.get("channel_id")
            count = kwargs.get("count", 0)
            body = f"## {e('purge')} Bulk delete · {ts}\n**Channel:** <#{channel_id}>\n**Messages removed:** {count}"
        elif action in ("channel_create", "channel_delete", "channel_change"):
            color = NEUTRAL
            channel_name = kwargs.get("channel_name", "unknown")
            actor_id = kwargs.get("actor_id")
            label = {"channel_create": "Channel created", "channel_delete": "Channel deleted", "channel_change": "Channel updated"}[action]
            body = f"## {e('info')} {label} · {ts}\n**Channel:** `#{channel_name}`" + (f"\n**By:** <@{actor_id}>" if actor_id else "")
        elif action in ("role_create", "role_delete", "role_change"):
            color = NEUTRAL
            role_name = kwargs.get("role_name", "unknown")
            actor_id = kwargs.get("actor_id")
            label = {"role_create": "Role created", "role_delete": "Role deleted", "role_change": "Role updated"}[action]
            body = f"## {e('info')} {label} · {ts}\n**Role:** `@{role_name}`" + (f"\n**By:** <@{actor_id}>" if actor_id else "")
        elif action == "verification_action":
            color = SUCCESS
            user_id = kwargs.get("user_id")
            detail = kwargs.get("detail", "")
            body = f"## {e('verification_cat')} Verification · {ts}\n**Member:** <@{user_id}>\n\n**Detail:** {detail}"

        if body:
            await self._send_log_view(guild_id, category, self._make_log_view(color, body))

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild:
            return
        if before.content == after.content:
            return
        await bus.publish(LOG_EVENT, guild_id=before.guild.id, action="message_edit",
                          user_id=before.author.id, channel_id=before.channel.id,
                          before=before.content, after=after.content)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        await bus.publish(LOG_EVENT, guild_id=message.guild.id, action="message_delete",
                          user_id=message.author.id, channel_id=message.channel.id,
                          content=message.content)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages or not messages[0].guild:
            return
        await bus.publish(LOG_EVENT, guild_id=messages[0].guild.id, action="message_bulk_delete",
                          channel_id=messages[0].channel.id, count=len(messages))

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        age_days = (discord.utils.utcnow() - member.created_at).days
        await bus.publish(LOG_EVENT, guild_id=member.guild.id, action="member_join",
                          user_id=member.id, account_age=f"{age_days} day(s)")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        await bus.publish(LOG_EVENT, guild_id=member.guild.id, action="member_leave", user_id=member.id)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await bus.publish(LOG_EVENT, guild_id=channel.guild.id, action="channel_create", channel_name=channel.name)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await bus.publish(LOG_EVENT, guild_id=channel.guild.id, action="channel_delete", channel_name=channel.name)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await bus.publish(LOG_EVENT, guild_id=role.guild.id, action="role_create", role_name=role.name)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await bus.publish(LOG_EVENT, guild_id=role.guild.id, action="role_delete", role_name=role.name)

    @commands.group(name="logging", aliases=["logs"], invoke_without_command=True, help="View or configure the audit log system.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def logging_group(self, ctx: commands.Context):
        from utils.security_panels import LoggingOverviewLayout
        view = await LoggingOverviewLayout.create(ctx.author.id, ctx.guild.id)
        await ctx.send(view=view)

    @logging_group.command(name="setup", help="Auto-create a logging category with a channel per event group.")
    @has_guild_permission("administrator")
    @commands.bot_has_permissions(manage_channels=True, manage_webhooks=True)
    async def log_setup(self, ctx: commands.Context):
        e = emoji_manager.get

        existing_category = discord.utils.get(ctx.guild.categories, name=config.LOG_CATEGORY_NAME)
        category = existing_category or await ctx.guild.create_category(
            config.LOG_CATEGORY_NAME,
            overwrites={
                ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                ctx.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_webhooks=True),
            },
        )

        created_lines = []
        for category_key, meta in config.LOG_CATEGORIES.items():
            existing_row = await self._get_category_row(ctx.guild.id, category_key)
            if existing_row:
                channel = ctx.guild.get_channel(int(existing_row["channel_id"]))
                if channel:
                    created_lines.append(f"`{meta['channel_name']}` — already set up")
                    continue

            channel = discord.utils.get(category.channels, name=meta["channel_name"])
            if not channel:
                channel = await ctx.guild.create_text_channel(meta["channel_name"], category=category)

            webhook = await channel.create_webhook(name=f"{config.BOT_NAME} Logs")
            await db.raw_execute(
                "INSERT INTO log_channels (guild_id, category, channel_id, webhook_url) VALUES (?, ?, ?, ?)"
                " ON CONFLICT(guild_id, category) DO UPDATE SET channel_id=excluded.channel_id, webhook_url=excluded.webhook_url",
                (ctx.guild.id, category_key, channel.id, webhook.url),
            )
            self._webhook_cache.pop((ctx.guild.id, category_key), None)
            created_lines.append(f"{channel.mention} — **{meta['label']}**")

        body = "\n".join(created_lines)
        await ctx.send(view=self._make_log_view(SUCCESS,
            f"## {e('logging_cat')} Logging setup complete\n{body}\n\n"
            "Each category logs independently via webhook. Use `logging toggle <event>` to disable individual events."
        ))

    @logging_group.command(name="channel", help="Manually set the channel for a specific log category.")
    @has_guild_permission("administrator")
    @commands.bot_has_permissions(manage_webhooks=True)
    async def log_channel(self, ctx: commands.Context, category: str, channel: discord.TextChannel):
        e = emoji_manager.get
        category = category.lower()
        if category not in config.LOG_CATEGORIES:
            names = ", ".join(f"`{c}`" for c in config.LOG_CATEGORIES)
            return await ctx.send(view=self._make_log_view(ERROR, f"## {e('cross')} Invalid category\nChoose from: {names}"))

        try:
            webhook = await channel.create_webhook(name=f"{config.BOT_NAME} Logs")
        except discord.HTTPException as ex:
            return await ctx.send(view=self._make_log_view(ERROR, f"## {e('cross')} Could not create webhook\n{ex}"))

        await db.raw_execute(
            "INSERT INTO log_channels (guild_id, category, channel_id, webhook_url) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(guild_id, category) DO UPDATE SET channel_id=excluded.channel_id, webhook_url=excluded.webhook_url",
            (ctx.guild.id, category, channel.id, webhook.url),
        )
        self._webhook_cache.pop((ctx.guild.id, category), None)
        label = config.LOG_CATEGORIES[category]["label"]
        await ctx.send(view=self._make_log_view(SUCCESS,
            f"## {e('check')} Channel set\n**{label}** logs will be sent to {channel.mention}."
        ))

    @logging_group.command(name="toggle", help="Enable or disable a specific log event type.")
    @has_guild_permission("administrator")
    async def log_toggle(self, ctx: commands.Context, event: str):
        e = emoji_manager.get
        if event not in config.LOG_EVENTS:
            names = ", ".join(f"`{ev}`" for ev in config.LOG_EVENTS)
            return await ctx.send(view=self._make_log_view(ERROR, f"## {e('cross')} Invalid event\nValid events: {names}"))

        disabled = await self._get_disabled_events(ctx.guild.id)
        if event in disabled:
            await db.raw_execute("DELETE FROM log_disabled_events WHERE guild_id=? AND event=?", (ctx.guild.id, event))
            state = "enabled"
        else:
            await db.raw_execute("INSERT INTO log_disabled_events (guild_id, event) VALUES (?, ?)", (ctx.guild.id, event))
            state = "disabled"

        await ctx.send(view=self._make_log_view(SUCCESS, f"## {e('check')} Log event updated\n`{event}` logging is now {state}."))

    @logging_group.command(name="remove", help="Remove logging for a category and delete its webhook.")
    @has_guild_permission("administrator")
    async def log_remove(self, ctx: commands.Context, category: str):
        e = emoji_manager.get
        category = category.lower()
        row = await self._get_category_row(ctx.guild.id, category)
        if not row:
            return await ctx.send(view=self._make_log_view(ERROR, f"## {e('cross')} Not configured\nNo logging set up for `{category}`."))

        if row["webhook_url"]:
            try:
                webhook = discord.Webhook.from_url(row["webhook_url"], client=self.bot)
                await webhook.delete()
            except discord.HTTPException:
                pass

        await db.raw_execute("DELETE FROM log_channels WHERE guild_id=? AND category=?", (ctx.guild.id, category))
        self._webhook_cache.pop((ctx.guild.id, category), None)
        await ctx.send(view=self._make_log_view(SUCCESS, f"## {e('check')} Removed\nLogging for `{category}` has been removed."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Logging(bot))
