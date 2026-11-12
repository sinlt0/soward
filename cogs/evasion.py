import asyncio
import datetime
import time
from typing import Optional

import discord
from discord.ext import commands

from utils import cases, emoji_manager, evasion as store, security, security_intel, security_master
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import LOG_EVENT, MOD_ACTION, bus

NO_MENTIONS = discord.AllowedMentions.none()


def link_layout(link: dict, banned: Optional[dict]) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    color = {"open": 0xED4245, "banned": 0x95A5A6, "dismissed": 0x57F287}.get(link["status"], 0xED4245)
    container = discord.ui.Container(accent_color=color)
    when = f"<t:{int(banned['banned_at'])}:R>" if banned else "earlier"
    name = f" ({banned['name']})" if banned and banned.get("name") else ""
    lines = [f"## Possible ban evasion · {link['score']}/100",
             f"<@{link['user_id']}> may be the same person as banned <@{link['banned_id']}>{name}, banned {when}.",
             "**Why:** " + ", ".join(link["reasons"])]
    if banned and banned.get("reason"):
        lines.append(f"**Original ban reason:** {banned['reason']}")
    lines.append("-# This is a signal, not proof. Check the account before acting.")
    if link["status"] != "open":
        who = f" by <@{link['handler_id']}>" if link.get("handler_id") else ""
        lines.append(f"\n**Status:** {'Banned' if link['status'] == 'banned' else 'Marked as a different person'}{who}")
    container.add_item(discord.ui.TextDisplay("\n".join(lines)))
    if link["status"] == "open":
        row = discord.ui.ActionRow()
        row.add_item(discord.ui.Button(label="Ban", style=discord.ButtonStyle.danger, custom_id=f"evasion:ban:{link['link_id']}"))
        row.add_item(discord.ui.Button(label="Not the same person", style=discord.ButtonStyle.secondary, custom_id=f"evasion:ok:{link['link_id']}"))
        container.add_item(row)
    view.add_item(container)
    return view


class Evasion(commands.Cog):
    category = "Config"
    submodule = "Security"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _profile(self, user, guild_id: int) -> dict:
        return {
            "user_id": user.id, "name": user.name, "name_key": store.name_key(user.name), "global_key": store.name_key(getattr(user, "global_name", None)),
            "avatar": user.avatar.key if getattr(user, "avatar", None) is not None else None,
            "account_created": user.created_at.timestamp(), "invite": security_intel.invite_for(guild_id, user.id),
        }

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.abc.User):
        if user.bot:
            return
        cfg = await store.get_config(guild.id)
        if not cfg["enabled"]:
            return
        profile = self._profile(user, guild.id)
        reason = None
        try:
            reason = (await guild.fetch_ban(user)).reason
        except discord.HTTPException:
            pass
        await store.remember_ban(
            guild.id, user.id, name=profile["name"], global_name=getattr(user, "global_name", None), avatar=profile["avatar"],
            account_created=profile["account_created"], invite=profile["invite"], reason=reason)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        await store.forget_ban(guild.id, user.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        cfg = await store.get_config(member.guild.id)
        if not cfg["enabled"] or await security_master.is_off(member.guild.id):
            return
        await asyncio.sleep(3)
        await self.evaluate(member, cfg)

    async def evaluate(self, member: discord.Member, cfg: dict, manual: bool = False) -> list:
        guild = member.guild
        found = await store.matches(guild.id, self._profile(member, guild.id), cfg["threshold"])
        if manual:
            return found
        if not found or await security.is_exempt(guild.id, member, "antiraid"):
            return found
        points, banned, why = found[0]
        if await store.dismissed(guild.id, member.id, banned["user_id"]):
            return found
        link_id = await store.create_link(guild.id, member.id, banned["user_id"], points, why)
        link = await store.get_link(guild.id, link_id)
        channel = guild.get_channel(int(cfg["channel"])) if cfg["channel"] else None
        if channel is not None:
            try:
                message = await channel.send(view=link_layout(link, banned), allowed_mentions=NO_MENTIONS)
                await store.remember_message(link_id, channel.id, message.id)
            except discord.HTTPException:
                pass
        await bus.publish(LOG_EVENT, guild_id=guild.id, action="antiraid_action", user_id=member.id, reason=f"possible ban evasion of {banned['user_id']} ({points}/100: {', '.join(why)})", action_taken="flagged")
        if cfg["action"] == "timeout" and member.top_role < guild.me.top_role:
            try:
                await member.timeout(discord.utils.utcnow() + datetime.timedelta(hours=1), reason="Possible ban evasion")
            except discord.HTTPException:
                pass
        elif cfg["action"] == "kick" and member.top_role < guild.me.top_role:
            try:
                await member.kick(reason="Possible ban evasion")
            except discord.HTTPException:
                pass
        return found

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if not custom_id.startswith("evasion:"):
            return
        parts = custom_id.split(":", 2)
        if len(parts) != 3 or parts[1] not in ("ban", "ok"):
            return
        guild, handler = interaction.guild, interaction.user
        if not isinstance(handler, discord.Member) or not (handler.guild_permissions.ban_members or handler.guild_permissions.administrator):
            return await interaction.response.send_message("You need the Ban Members permission.", ephemeral=True)
        link = await store.get_link(guild.id, parts[2])
        if link is None or link["status"] != "open":
            return await interaction.response.send_message("This was already handled.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        banned = next((b for b in await store.banned_profiles(guild.id) if b["user_id"] == link["banned_id"]), None)
        if parts[1] == "ban":
            target = guild.get_member(link["user_id"])
            if target is not None and (target.top_role >= handler.top_role and handler.id != guild.owner_id or target.top_role >= guild.me.top_role):
                return await interaction.followup.send("Their role is too high for this action.", ephemeral=True)
            appeals = self.bot.get_cog("Appeals")
            user = target or await self._fetch(link["user_id"])
            if appeals is not None and user is not None:
                await appeals.notify_ban(guild, user, "Ban evasion", clean=True)
            try:
                await guild.ban(discord.Object(id=link["user_id"]), reason=f"{handler} | Ban evasion of {link['banned_id']}", delete_message_days=0)
            except discord.HTTPException:
                return await interaction.followup.send("I could not ban them. Check my permissions.", ephemeral=True)
            case_id = await cases.create_mod_case(guild.id, "ban", link["user_id"], handler.id, f"Ban evasion of {link['banned_id']}")
            await bus.publish(MOD_ACTION, guild_id=guild.id, action="ban", user_id=link["user_id"], moderator_id=handler.id, reason="Ban evasion", case_id=case_id)
            status = "banned"
        else:
            status = "dismissed"
        await store.resolve(link["link_id"], status, handler.id)
        link = await store.get_link(guild.id, link["link_id"])
        if link.get("channel_id") and link.get("message_id"):
            channel = guild.get_channel(link["channel_id"])
            if channel is not None:
                try:
                    message = await channel.fetch_message(link["message_id"])
                    await message.edit(view=link_layout(link, banned), allowed_mentions=NO_MENTIONS)
                except discord.HTTPException:
                    pass
        await interaction.followup.send("Done.", ephemeral=True)

    async def _fetch(self, user_id: int):
        try:
            return await self.bot.fetch_user(user_id)
        except discord.HTTPException:
            return None

    @commands.group(name="evasion", aliases=["altcheck"], invoke_without_command=True, help="Ban evasion detection.")
    @commands.guild_only()
    @has_guild_permission("ban_members")
    async def evasion(self, ctx: commands.Context):
        cfg = await store.get_config(ctx.guild.id)
        known = len(await store.banned_profiles(ctx.guild.id))
        channel = f"<#{cfg['channel']}>" if cfg["channel"] else "not set"
        await ctx.send(view=info_layout("Ban evasion", (
            f"**Status:** {'on' if cfg['enabled'] else 'off'} · **Alert channel:** {channel} · **Threshold:** {cfg['threshold']}/100 · **Action:** {cfg['action']}\n"
            f"**Banned accounts known:** {known}\n\n"
            "`evasion scan` · `evasion check @member` · `evasion list` · `evasion on|off` · `evasion channel #x` · `evasion threshold <30-100>` · `evasion action none|timeout|kick`")))

    @evasion.command(name="scan", help="Learn the accounts that are already banned in this server.")
    @has_guild_permission("ban_members")
    async def evasion_scan(self, ctx: commands.Context):
        added = 0
        try:
            async for entry in ctx.guild.bans(limit=1000):
                user = entry.user
                if user.bot:
                    continue
                profile = self._profile(user, ctx.guild.id)
                await store.remember_ban(
                    ctx.guild.id, user.id, name=profile["name"], global_name=getattr(user, "global_name", None), avatar=profile["avatar"],
                    account_created=profile["account_created"], invite=profile["invite"], reason=entry.reason)
                added += 1
        except discord.HTTPException:
            return await ctx.send(view=error_layout("Could not read bans", "I need the Ban Members permission."))
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Scan done", f"Learned **{added}** banned account(s). The original ban time is unknown for these, so the account-age signal is skipped for them."))

    @evasion.command(name="check", help="Compare a member with the banned accounts.")
    @has_guild_permission("ban_members")
    async def evasion_check(self, ctx: commands.Context, member: discord.Member):
        cfg = await store.get_config(ctx.guild.id)
        found = await self.evaluate(member, {**cfg, "threshold": 30}, manual=True)
        if not found:
            return await ctx.send(view=info_layout("No match", f"{member.mention} does not look like any banned account."), allowed_mentions=NO_MENTIONS)
        lines = [f"**{points}/100** <@{b['user_id']}> ({b.get('name') or 'unknown'}) · {', '.join(why)}" for points, b, why in found[:5]]
        await ctx.send(view=info_layout(f"Closest banned accounts for {member.display_name}", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @evasion.command(name="list", help="Recent evasion alerts.")
    @has_guild_permission("ban_members")
    async def evasion_list(self, ctx: commands.Context):
        rows = await store.recent_links(ctx.guild.id)
        if not rows:
            return await ctx.send(view=info_layout("Ban evasion", "No alerts yet."))
        lines = [f"`{r['link_id']}` <@{r['user_id']}> ↔ <@{r['banned_id']}> · {r['score']}/100 · {r['status']} · <t:{int(r['created_at'])}:R>" for r in rows]
        await ctx.send(view=info_layout("Ban evasion alerts", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    async def _set(self, ctx: commands.Context, name: str, value, text: str):
        await store.set_config(ctx.guild.id, name, value)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Ban evasion", text))

    @evasion.command(name="on", help="Turn detection on.")
    @has_guild_permission("manage_guild")
    async def evasion_on(self, ctx: commands.Context):
        await self._set(ctx, "enabled", True, "Detection is **on**.")

    @evasion.command(name="off", help="Turn detection off.")
    @has_guild_permission("manage_guild")
    async def evasion_off(self, ctx: commands.Context):
        await self._set(ctx, "enabled", False, "Detection is **off**.")

    @evasion.command(name="channel", help="Where alerts are posted.")
    @has_guild_permission("manage_guild")
    async def evasion_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        await self._set(ctx, "channel", channel.id, f"Alerts go to {channel.mention}.")

    @evasion.command(name="threshold", help="Score from 30 to 100 that triggers an alert. Default 60.")
    @has_guild_permission("manage_guild")
    async def evasion_threshold(self, ctx: commands.Context, value: int):
        if not 30 <= value <= 100:
            return await ctx.send(view=error_layout("Invalid number", "Use 30 to 100."))
        await self._set(ctx, "threshold", value, f"Alerts start at **{value}/100**.")

    @evasion.command(name="action", help="What happens besides the alert: none, timeout (1h) or kick.")
    @has_guild_permission("manage_guild")
    async def evasion_action(self, ctx: commands.Context, action: str):
        action = action.lower()
        if action not in store.ACTIONS:
            return await ctx.send(view=error_layout("Invalid action", "Use `none`, `timeout` or `kick`."))
        await self._set(ctx, "action", action, f"Action on a match: **{action}**.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Evasion(bot))
