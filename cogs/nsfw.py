import asyncio
import logging
import typing

import discord
from discord.ext import commands

import config
from utils import emoji_manager, nsfw
from utils.checks import has_guild_permission
from utils.components import ConfirmLayout, error_layout, info_layout, success_layout
from utils.events_bus import LOG_EVENT, bus

log = logging.getLogger("soward.nsfw")

ChannelArg = typing.Union[discord.TextChannel, discord.ForumChannel]
RESET_WORDS = {"reset", "clear", "remove", "none", "off", "disable"}
_API_DELAY = 0.35


def _reason(ctx: commands.Context, action: str) -> str:
    return f"[Soward NSFW] {action} - requested by {ctx.author} ({ctx.author.id})"


def _fmt_error(exc: Exception) -> str:
    if isinstance(exc, discord.Forbidden):
        return "missing permissions (I need **Manage Channels** and **Manage Roles**, and my role must be above the NSFW role)"
    return str(exc)[:120] or type(exc).__name__


class NSFW(commands.Cog):
    category = "Config"

    def __init__(self, bot: commands.Bot):
        self.bot = bot


    async def _log(self, guild_id: int, detail: str, user_id: typing.Optional[int] = None):
        await bus.publish(LOG_EVENT, guild_id=guild_id, action="nsfw_action", user_id=user_id, detail=detail)

    async def _overview(self, guild: discord.Guild) -> discord.ui.LayoutView:
        e = emoji_manager.get
        role_id = await nsfw.get_role_id(guild.id)
        role = guild.get_role(role_id) if role_id else None
        ids = await nsfw.get_channel_ids(guild.id)

        if role:
            role_line = f"**NSFW role:** {role.mention}"
        elif role_id:
            role_line = "**NSFW role:** *(deleted - set a new one with* `nsfw role`*)*"
        else:
            role_line = "**NSFW role:** *not set - run* `nsfw role <@role>`"

        lines = []
        for cid in ids:
            channel = guild.get_channel(cid)
            if channel is None:
                lines.append(f"{e('cross')} `{cid}` - channel no longer exists")
            elif role and nsfw.is_locked(channel):
                lines.append(f"{e('lock')} {channel.mention} - locked to the NSFW role")
            else:
                lines.append(f"{e('warn')} {channel.mention} - **not locked** (run `nsfw sync`)")
        channels_block = "\n".join(lines) if lines else "*No channels registered. Use* `nsfw addchannel #channel`"

        footer = (
            f"\n\n-# {len(ids)}/{config.NSFW_MAX_CHANNELS} channels · "
            "NSFW commands only run in registered channels that are locked to the role."
        )
        return info_layout(f"{e('lock')} NSFW Channels", f"{role_line}\n\n{channels_block}{footer}")

    async def _apply_to_all(self, guild, role, snapshots, ids, reason):
        ok, failed = [], []
        for cid in ids:
            channel = guild.get_channel(cid)
            if channel is None:
                continue
            try:
                await nsfw.lock_channel(channel, role, snapshots, reason)
                ok.append(channel)
            except Exception as exc:
                failed.append((channel, exc))
            await asyncio.sleep(_API_DELAY)
        return ok, failed


    @commands.group(name="nsfw", invoke_without_command=True,
                    help="Role-gated NSFW channels. Shows the current setup.")
    @has_guild_permission("manage_channels")
    @commands.guild_only()
    async def nsfw_group(self, ctx: commands.Context):
        await ctx.send(view=await self._overview(ctx.guild))

    @nsfw_group.command(name="viewchannels", aliases=["view", "channels", "list"],
                        help="Show the NSFW role and every registered NSFW channel.")
    @has_guild_permission("manage_channels")
    @commands.guild_only()
    async def nsfw_view(self, ctx: commands.Context):
        await ctx.send(view=await self._overview(ctx.guild))

    @nsfw_group.command(name="role", help="Set the NSFW role (or `reset` to unlock everything and clear it).")
    @has_guild_permission("administrator")
    @commands.bot_has_guild_permissions(manage_channels=True, manage_roles=True)
    @commands.guild_only()
    async def nsfw_role(self, ctx: commands.Context, *, role: typing.Optional[str] = None):
        e = emoji_manager.get
        guild = ctx.guild

        if role is None:
            current_id = await nsfw.get_role_id(guild.id)
            current = guild.get_role(current_id) if current_id else None
            text = f"Current NSFW role: {current.mention}" if current else "No NSFW role is set."
            return await ctx.send(view=info_layout(f"{e('lock')} NSFW Role", f"{text}\nSet one with `nsfw role <@role>`."))

        if role.strip().lower() in RESET_WORDS:
            return await self._reset(ctx)

        try:
            target = await commands.RoleConverter().convert(ctx, role)
        except commands.BadArgument:
            return await ctx.send(view=error_layout(f"{e('cross')} Role not found", f"I couldn't find a role matching `{role[:50]}`."))

        me = guild.me
        if target.is_default() or target.managed:
            return await ctx.send(view=error_layout(f"{e('cross')} Invalid role", "Pick a normal role that can be given to members (not @everyone or a bot/integration role)."))
        if not me.guild_permissions.administrator and target >= me.top_role:
            return await ctx.send(view=error_layout(f"{e('cross')} Role too high", f"{target.mention} is above my highest role. Move my role higher, then try again."))

        async with nsfw.guild_lock(guild.id):
            old_id = await nsfw.get_role_id(guild.id)
            ids = await nsfw.get_channel_ids(guild.id)
            snapshots = await nsfw.get_snapshots(guild.id)

            if old_id == target.id:
                return await ctx.send(view=info_layout(f"{e('info')} Already set", f"{target.mention} is already the NSFW role. Use `nsfw sync` to re-apply permissions."))

            ok, failed = await self._apply_to_all(guild, target, snapshots, ids, _reason(ctx, "NSFW role set"))
            await nsfw.set_role_id(guild.id, target.id)
            await nsfw.save_channels(guild.id, ids, snapshots)

        await self._log(guild.id, f"NSFW role set to **{target.name}** ({len(ok)} channel(s) updated)", ctx.author.id)
        body = f"NSFW role is now {target.mention}."
        if ids:
            body += f"\nUpdated **{len(ok)}** channel(s)."
        if failed:
            body += "\n\n" + "\n".join(f"{e('warn')} {c.mention}: {_fmt_error(x)}" for c, x in failed) + "\n\nFix the problem, then run `nsfw sync`."
        elif not ids:
            body += "\nNow add channels with `nsfw addchannel #channel`."
        await ctx.send(view=(error_layout if failed else success_layout)(f"{e('check')} NSFW role set" if not failed else f"{e('warn')} NSFW role set with problems", body))

    async def _reset(self, ctx: commands.Context):
        e = emoji_manager.get
        guild = ctx.guild
        if await nsfw.get_role_id(guild.id) is None:
            return await ctx.send(view=info_layout(f"{e('info')} Nothing to reset", "No NSFW role is set."))

        confirm = ConfirmLayout(
            f"{e('warn')} Reset NSFW role?",
            "This restores every registered channel to the permissions it had **before** it was locked, "
            "which can make those channels visible to everyone again.\n"
            "The channels stay registered, but NSFW commands will refuse to run until a role is set.",
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "NSFW role left unchanged."))

        async with nsfw.guild_lock(guild.id):
            ids = await nsfw.get_channel_ids(guild.id)
            snapshots = await nsfw.get_snapshots(guild.id)
            failed = []
            for cid in ids:
                try:
                    await nsfw.unlock_channel(guild, guild.get_channel(cid), snapshots, _reason(ctx, "NSFW role reset"))
                except Exception as exc:
                    failed.append((cid, exc))
                await asyncio.sleep(_API_DELAY)
            await nsfw.set_role_id(guild.id, None)
            await nsfw.save_channels(guild.id, ids, snapshots)

        await self._log(guild.id, "NSFW role reset - channel permissions restored", ctx.author.id)
        body = "NSFW role cleared and channel permissions restored."
        if failed:
            body += "\n\n" + "\n".join(f"{e('warn')} <#{c}>: {_fmt_error(x)}" for c, x in failed)
        await msg.edit(view=success_layout(f"{e('check')} NSFW role reset", body))

    @nsfw_group.command(name="addchannel", aliases=["add"],
                        help="Register channel(s) as NSFW and lock them to the NSFW role.")
    @has_guild_permission("administrator")
    @commands.bot_has_guild_permissions(manage_channels=True, manage_roles=True)
    @commands.guild_only()
    async def nsfw_addchannel(self, ctx: commands.Context, channels: commands.Greedy[ChannelArg]):
        e = emoji_manager.get
        guild = ctx.guild
        if not channels:
            return await ctx.send(view=error_layout(f"{e('cross')} No channels", "Mention one or more text or forum channels: `nsfw addchannel #channel`."))

        async with nsfw.guild_lock(guild.id):
            role_id = await nsfw.get_role_id(guild.id)
            role = guild.get_role(role_id) if role_id else None
            ids = await nsfw.get_channel_ids(guild.id)
            snapshots = await nsfw.get_snapshots(guild.id)

            added, already, failed, skipped = [], [], [], []
            for channel in dict.fromkeys(channels):
                if channel.id in ids:
                    already.append(channel)
                    continue
                if len(ids) >= config.NSFW_MAX_CHANNELS:
                    skipped.append(channel)
                    continue
                if role is not None:
                    try:
                        await nsfw.lock_channel(channel, role, snapshots, _reason(ctx, "NSFW channel added"))
                    except Exception as exc:
                        failed.append((channel, exc))
                        continue
                    await asyncio.sleep(_API_DELAY)
                ids.append(channel.id)
                added.append(channel)
            await nsfw.save_channels(guild.id, ids, snapshots, ctx.author.id)

        if added:
            await self._log(guild.id, "NSFW channel(s) added: " + ", ".join(c.mention for c in added), ctx.author.id)

        parts = []
        if added:
            parts.append(f"{e('check')} Added: " + ", ".join(c.mention for c in added))
            parts.append(
                "Each is now hidden from @everyone and visible only to " + role.mention + "."
                if role else
                f"{e('warn')} **No NSFW role is set yet**, so nothing is locked. Run `nsfw role <@role>` to enforce it."
            )
        if already:
            parts.append(f"{e('info')} Already registered: " + ", ".join(c.mention for c in already))
        if skipped:
            parts.append(f"{e('warn')} Limit of {config.NSFW_MAX_CHANNELS} reached, skipped: " + ", ".join(c.mention for c in skipped))
        for c, x in failed:
            parts.append(f"{e('cross')} {c.mention}: {_fmt_error(x)}")
        ok = bool(added) and not failed
        await ctx.send(view=(success_layout if ok else error_layout)(f"{e('lock')} NSFW channels", "\n".join(parts)))

    @nsfw_group.command(name="removechannel", aliases=["remove", "delchannel"],
                        help="Unregister channel(s) and restore their original permissions.")
    @has_guild_permission("administrator")
    @commands.bot_has_guild_permissions(manage_channels=True, manage_roles=True)
    @commands.guild_only()
    async def nsfw_removechannel(self, ctx: commands.Context, channels: commands.Greedy[ChannelArg]):
        e = emoji_manager.get
        guild = ctx.guild
        if not channels:
            return await ctx.send(view=error_layout(f"{e('cross')} No channels", "Mention one or more channels: `nsfw removechannel #channel`."))

        async with nsfw.guild_lock(guild.id):
            ids = await nsfw.get_channel_ids(guild.id)
            snapshots = await nsfw.get_snapshots(guild.id)
            removed, missing, failed = [], [], []
            for channel in dict.fromkeys(channels):
                if channel.id not in ids:
                    missing.append(channel)
                    continue
                try:
                    await nsfw.unlock_channel(guild, channel, snapshots, _reason(ctx, "NSFW channel removed"))
                except Exception as exc:
                    failed.append((channel, exc))
                ids.remove(channel.id)
                removed.append(channel)
                await asyncio.sleep(_API_DELAY)
            await nsfw.save_channels(guild.id, ids, snapshots, ctx.author.id)

        if removed:
            await self._log(guild.id, "NSFW channel(s) removed: " + ", ".join(c.mention for c in removed), ctx.author.id)

        parts = []
        if removed:
            parts.append(f"{e('check')} Removed: " + ", ".join(c.mention for c in removed) + "\nTheir permissions were restored to what they were before locking.")
        if missing:
            parts.append(f"{e('info')} Not registered: " + ", ".join(c.mention for c in missing))
        for c, x in failed:
            parts.append(f"{e('warn')} {c.mention}: couldn't fully restore permissions - {_fmt_error(x)}. Check them manually.")
        ok = bool(removed) and not failed
        await ctx.send(view=(success_layout if ok else error_layout)(f"{e('lock')} NSFW channels", "\n".join(parts)))

    @nsfw_group.command(name="sync", help="Re-apply the NSFW lock to every registered channel.")
    @has_guild_permission("administrator")
    @commands.bot_has_guild_permissions(manage_channels=True, manage_roles=True)
    @commands.guild_only()
    async def nsfw_sync(self, ctx: commands.Context):
        e = emoji_manager.get
        guild = ctx.guild
        async with nsfw.guild_lock(guild.id):
            role_id = await nsfw.get_role_id(guild.id)
            role = guild.get_role(role_id) if role_id else None
            if role is None:
                return await ctx.send(view=error_layout(f"{e('cross')} No NSFW role", "Set one first with `nsfw role <@role>`."))
            ids = await nsfw.get_channel_ids(guild.id)
            snapshots = await nsfw.get_snapshots(guild.id)
            ok, failed = await self._apply_to_all(guild, role, snapshots, ids, _reason(ctx, "NSFW sync"))
            await nsfw.save_channels(guild.id, ids, snapshots)

        body = f"Re-applied the lock to **{len(ok)}** channel(s)."
        if failed:
            body += "\n\n" + "\n".join(f"{e('warn')} {c.mention}: {_fmt_error(x)}" for c, x in failed)
        await ctx.send(view=(error_layout if failed else success_layout)(f"{e('lock')} NSFW sync", body))


    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        async with nsfw.guild_lock(channel.guild.id):
            ids = await nsfw.get_channel_ids(channel.guild.id)
            if channel.id not in ids:
                return
            snapshots = await nsfw.get_snapshots(channel.guild.id)
            ids.remove(channel.id)
            snapshots.pop(str(channel.id), None)
            await nsfw.save_channels(channel.guild.id, ids, snapshots)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        async with nsfw.guild_lock(role.guild.id):
            if await nsfw.get_role_id(role.guild.id) != role.id:
                return
            snapshots = await nsfw.get_snapshots(role.guild.id)
            for entry in snapshots.values():
                if entry.get("role_id") == role.id:
                    entry["role_id"] = None
            await nsfw.set_role_id(role.guild.id, None)
            await nsfw.save_channels(role.guild.id, await nsfw.get_channel_ids(role.guild.id), snapshots)
        await self._log(role.guild.id, f"The NSFW role **{role.name}** was deleted. NSFW channels stay locked; set a new role with `nsfw role`.")


async def setup(bot: commands.Bot):
    await bot.add_cog(NSFW(bot))
