from typing import Optional

import discord
from discord.ext import commands

from utils import emoji_manager, guild_settings
from utils.security_access import security_owner
from utils.components import ConfirmLayout, error_layout, success_layout
from utils.events_bus import LOG_EVENT, bus
import config

SUPPORT_ROLE_NAME = "Soward Support"


async def _support_role(guild: discord.Guild) -> Optional[discord.Role]:
    role_id = await guild_settings.get(guild.id, "support_role_id")
    return guild.get_role(int(role_id)) if role_id else None


class SupportAccess(commands.Cog):
    category = "Config"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="supportaccess", aliases=["grantsupport"], help="Grant the Soward development team temporary Administrator access to this server for support/troubleshooting. Only the server owner or an Extra Owner can grant it.")
    @security_owner()
    @commands.guild_only()
    async def supportaccess(self, ctx: commands.Context):
        e = emoji_manager.get

        existing = await _support_role(ctx.guild)
        if existing:
            return await ctx.send(view=error_layout(
                "Already Granted",
                f"The **{SUPPORT_ROLE_NAME}** role already exists in this server. Use `revokesupport` to remove it first if you want to re-grant it.",
            ))

        dev_ids = set(config.OWNER_IDS) | set(config.DEV_IDS)
        dev_members = [ctx.guild.get_member(uid) for uid in dev_ids]
        dev_members = [m for m in dev_members if m]

        confirm = ConfirmLayout(
            f"{e('warning')} Confirm Support Access Grant",
            (
                f"This will create a **{SUPPORT_ROLE_NAME}** role with **Administrator** permissions "
                f"and assign it to the bot and the Soward dev team ({len(dev_members)} currently in this server).\n\n"
                "This is meant for troubleshooting issues you're having with the bot. "
                f"You can remove this access at any time with `revokesupport`, and only the server owner or an Extra Owner can grant or revoke it.\n\n"
                "Do you want to proceed?"
            ),
            author_id=ctx.author.id,
        )
        msg = await ctx.send(view=confirm)
        await confirm.wait()

        if not confirm.value:
            return await msg.edit(view=error_layout("Cancelled", "Support access was not granted."))

        try:
            role = await ctx.guild.create_role(
                name=SUPPORT_ROLE_NAME,
                permissions=discord.Permissions(administrator=True),
                colour=discord.Colour(0x5865F2),
                hoist=True,
                mentionable=False,
                reason=f"Soward support access granted by {ctx.author} ({ctx.author.id})",
            )
        except discord.HTTPException as ex:
            return await msg.edit(view=error_layout("Failed", f"Couldn't create the support role: {ex}"))

        await guild_settings.set(ctx.guild.id, "support_role_id", role.id)
        granted_to = []
        try:
            await ctx.guild.me.add_roles(role, reason="Soward support access self-assignment")
            granted_to.append(str(ctx.guild.me))
        except discord.HTTPException:
            pass

        for member in dev_members:
            try:
                await member.add_roles(role, reason=f"Soward support access granted by {ctx.author} ({ctx.author.id})")
                granted_to.append(str(member))
            except discord.HTTPException:
                continue

        await bus.publish(
            LOG_EVENT, guild_id=ctx.guild.id, action="support_access_granted",
            granted_by=ctx.author.id, role_id=role.id, member_count=len(granted_to),
        )

        body = (
            f"Created {role.mention} with Administrator permissions.\n"
            f"**Assigned to:** {', '.join(granted_to) if granted_to else 'No one (dev team members are not currently in this server)'}\n\n"
            f"Run `revokesupport` at any time to remove this access."
        )
        await msg.edit(view=success_layout(f"{e('check')} Support Access Granted", body))

    @commands.command(name="revokesupport", help="Remove the Soward support access role from this server.")
    @security_owner()
    @commands.guild_only()
    async def revokesupport(self, ctx: commands.Context):
        e = emoji_manager.get
        role = await _support_role(ctx.guild)
        if not role:
            return await ctx.send(view=error_layout("Not Found", f"There is no **{SUPPORT_ROLE_NAME}** role in this server."))

        try:
            await role.delete(reason=f"Soward support access revoked by {ctx.author} ({ctx.author.id})")
        except discord.HTTPException as ex:
            return await ctx.send(view=error_layout("Failed", f"Couldn't remove the support role: {ex}"))

        await guild_settings.delete(ctx.guild.id, "support_role_id")
        await bus.publish(LOG_EVENT, guild_id=ctx.guild.id, action="support_access_revoked", revoked_by=ctx.author.id)
        await ctx.send(view=success_layout(f"{e('check')} Support Access Revoked", f"The **{SUPPORT_ROLE_NAME}** role has been removed."))

    @commands.command(name="supportstatus", help="Check whether Soward support access is currently active in this server.")
    @commands.guild_only()
    async def supportstatus(self, ctx: commands.Context):
        e = emoji_manager.get
        role = await _support_role(ctx.guild)
        if not role:
            return await ctx.send(view=error_layout("Inactive", f"No **{SUPPORT_ROLE_NAME}** role exists in this server."))

        members = ", ".join(str(m) for m in role.members) or "No one currently holds this role."
        await ctx.send(view=success_layout(
            f"{e('info')} Support Access Active",
            f"{role.mention} exists in this server.\n**Members:** {members}\n\nUse `revokesupport` to remove it.",
        ))


async def setup(bot: commands.Bot):
    await bot.add_cog(SupportAccess(bot))
