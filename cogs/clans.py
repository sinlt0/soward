import asyncio
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import clans, coins, emoji_manager
from utils.components import ConfirmLayout, error_layout, info_layout, success_layout

NO_PINGS = discord.AllowedMentions.none()
ROLE_LABELS = {"owner": "Owner", "officer": "Officer", "member": "Member"}


class Clans(commands.Cog):
    category = "Family"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.lock = asyncio.Lock()

    async def own(self, ctx: commands.Context, need: str = "member") -> Optional[tuple[dict, dict]]:
        mine = await clans.membership(ctx.author.id)
        if mine is None:
            await ctx.send(view=error_layout("No clan", "You are not in a clan. Use `clan create <name>` or ask for an invite."))
            return None
        if clans.ROLE_ORDER[mine["role"]] < clans.ROLE_ORDER[need]:
            await ctx.send(view=error_layout("Not allowed", f"Only the clan {'owner' if need == 'owner' else 'owner and officers'} can do that."))
            return None
        return mine, await clans.get(mine["clan_id"])

    @commands.group(name="clan", aliases=["clans"], invoke_without_command=True, help="Show your clan or another one. Usage: clan [name]")
    async def clan_group(self, ctx: commands.Context, *, name: Optional[str] = None):
        await self.show(ctx, name)

    async def show(self, ctx: commands.Context, name: Optional[str]):
        e = emoji_manager.get
        if name:
            clan = await clans.find(name)
        else:
            mine = await clans.membership(ctx.author.id)
            clan = await clans.get(mine["clan_id"]) if mine else None
            if clan is None:
                return await ctx.send(view=error_layout("No clan", "You are not in a clan. Use `clan create <name>`, or `clan <name>` to look one up."))
        if clan is None:
            return await ctx.send(view=error_layout("Not found", "No clan has that name."))
        size = await clans.member_count(clan["clan_id"])
        lines = [
            clan["description"] or "*No description.*",
            "",
            f"**Owner:** <@{clan['owner_id']}>",
            f"**Members:** {size}/{clans.capacity(clan['level'])}",
            f"**Level:** {clan['level']}/{config.CLAN_MAX_LEVEL}",
            f"{e('bank')} **Bank:** {coins.fmt(clan['bank'])} coins",
            f"**Founded:** <t:{int(clan['created_at'])}:D>",
        ]
        await ctx.send(view=info_layout(f"{e('shield')} {clan['name']}", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @clan_group.command(name="create", aliases=["found"], help="Start a clan. Usage: clan create <name>")
    async def clan_create(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        name = clans.clean_name(name)
        if not clans.NAME_RULE.match(name):
            return await ctx.send(view=error_layout("Invalid name", "Clan names are 3 to 20 characters: letters, numbers, spaces, `-` and `_`."))
        async with self.lock:
            if await clans.membership(ctx.author.id):
                return await ctx.send(view=error_layout("Already in a clan", "Leave your current clan first with `clan leave`."))
            if await clans.find(name):
                return await ctx.send(view=error_layout("Name taken", "A clan with that name already exists."))
            if not await coins.spend(ctx.author.id, config.CLAN_CREATE_COST):
                return await ctx.send(view=error_layout("Not enough coins", f"Creating a clan costs **{coins.fmt(config.CLAN_CREATE_COST)}** coins. You have **{coins.fmt(await coins.balance(ctx.author.id))}**."))
            clan = await clans.create(ctx.author.id, name)
            if clan is None:
                await coins.add(ctx.author.id, config.CLAN_CREATE_COST)
                return await ctx.send(view=error_layout("Name taken", "A clan with that name already exists."))
        await ctx.send(view=success_layout(f"{e('shield')} Clan created", f"**{clan['name']}** is ready. Invite people with `clan invite <user>`."))

    @clan_group.command(name="members", aliases=["roster"], help="List a clan's members. Usage: clan members [name]")
    async def clan_members(self, ctx: commands.Context, *, name: Optional[str] = None):
        e = emoji_manager.get
        if name:
            clan = await clans.find(name)
        else:
            mine = await clans.membership(ctx.author.id)
            clan = await clans.get(mine["clan_id"]) if mine else None
        if clan is None:
            return await ctx.send(view=error_layout("Not found", "Use a clan name, or join a clan first."))
        rows = await clans.members(clan["clan_id"])
        lines = [f"{ROLE_LABELS[row['role']]} · <@{row['user_id']}>" for row in rows]
        await ctx.send(view=info_layout(f"{e('shield')} {clan['name']} members", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @clan_group.command(name="top", aliases=["leaderboard", "lb", "list"], help="Show the top clans.")
    async def clan_top(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await clans.top(10)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('trophy')} Top clans", "No clans yet. Start one with `clan create <name>`."))
        lines = [f"**{i}.** {row['name']} · level {row['level']} · {row['size']} members" for i, row in enumerate(rows, 1)]
        await ctx.send(view=info_layout(f"{e('trophy')} Top clans", "\n".join(lines)))

    @clan_group.command(name="invite", help="Invite someone to your clan. Usage: clan invite <user>")
    async def clan_invite(self, ctx: commands.Context, user: discord.User):
        found = await self.own(ctx, "officer")
        if not found:
            return
        mine, clan = found
        if user.bot or user.id == ctx.author.id:
            return await ctx.send(view=error_layout("Cannot invite", "Pick another person."))
        if await clans.membership(user.id):
            return await ctx.send(view=error_layout("Already in a clan", f"{user.mention} is already in a clan."), allowed_mentions=NO_PINGS)
        if await clans.member_count(clan["clan_id"]) >= clans.capacity(clan["level"]):
            return await ctx.send(view=error_layout("Clan is full", "Upgrade the clan with `clan upgrade` to fit more members."))
        await clans.invite(clan["clan_id"], user.id, ctx.author.id)
        await ctx.send(view=success_layout("Invite sent", f"{user.mention}, you were invited to **{clan['name']}**. Use `clan join {clan['name']}` within {config.CLAN_INVITE_HOURS} hours."), allowed_mentions=discord.AllowedMentions(users=[user]))

    @clan_group.command(name="join", help="Join a clan you were invited to. Usage: clan join <name>")
    async def clan_join(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        async with self.lock:
            if await clans.membership(ctx.author.id):
                return await ctx.send(view=error_layout("Already in a clan", "Leave your current clan first with `clan leave`."))
            clan = await clans.find(name)
            if clan is None or not await clans.has_invite(clan["clan_id"], ctx.author.id):
                return await ctx.send(view=error_layout("No invite", "You do not have a valid invite to that clan."))
            if await clans.member_count(clan["clan_id"]) >= clans.capacity(clan["level"]):
                return await ctx.send(view=error_layout("Clan is full", "That clan has no free spots."))
            await clans.add_member(clan["clan_id"], ctx.author.id)
        await ctx.send(view=success_layout(f"{e('shield')} Joined", f"You joined **{clan['name']}**."))

    @clan_group.command(name="leave", help="Leave your clan.")
    async def clan_leave(self, ctx: commands.Context):
        found = await self.own(ctx)
        if not found:
            return
        mine, clan = found
        if mine["role"] == "owner":
            return await ctx.send(view=error_layout("You own this clan", "Use `clan transfer <user>` to hand it over, or `clan disband`."))
        await clans.remove_member(ctx.author.id)
        await ctx.send(view=success_layout("Left", f"You left **{clan['name']}**."))

    @clan_group.command(name="kick", help="Remove a member. Usage: clan kick <user>")
    async def clan_kick(self, ctx: commands.Context, user: discord.User):
        found = await self.own(ctx, "officer")
        if not found:
            return
        mine, clan = found
        target = await clans.membership(user.id)
        if target is None or target["clan_id"] != clan["clan_id"]:
            return await ctx.send(view=error_layout("Not a member", "That person is not in your clan."))
        if clans.ROLE_ORDER[target["role"]] >= clans.ROLE_ORDER[mine["role"]]:
            return await ctx.send(view=error_layout("Not allowed", "You can only remove members ranked below you."))
        await clans.remove_member(user.id)
        await ctx.send(view=success_layout("Removed", f"{user.mention} was removed from **{clan['name']}**."), allowed_mentions=NO_PINGS)

    async def change_role(self, ctx: commands.Context, user: discord.User, role: str):
        found = await self.own(ctx, "owner")
        if not found:
            return
        mine, clan = found
        target = await clans.membership(user.id)
        if target is None or target["clan_id"] != clan["clan_id"] or user.id == ctx.author.id:
            return await ctx.send(view=error_layout("Not a member", "Pick another member of your clan."))
        await clans.set_role(user.id, role)
        await ctx.send(view=success_layout("Updated", f"{user.mention} is now **{ROLE_LABELS[role]}**."), allowed_mentions=NO_PINGS)

    @clan_group.command(name="promote", help="Make a member an officer. Usage: clan promote <user>")
    async def clan_promote(self, ctx: commands.Context, user: discord.User):
        await self.change_role(ctx, user, "officer")

    @clan_group.command(name="demote", help="Make an officer a member. Usage: clan demote <user>")
    async def clan_demote(self, ctx: commands.Context, user: discord.User):
        await self.change_role(ctx, user, "member")

    @clan_group.command(name="transfer", help="Hand your clan to another member. Usage: clan transfer <user>")
    async def clan_transfer(self, ctx: commands.Context, user: discord.User):
        found = await self.own(ctx, "owner")
        if not found:
            return
        mine, clan = found
        target = await clans.membership(user.id)
        if target is None or target["clan_id"] != clan["clan_id"] or user.id == ctx.author.id:
            return await ctx.send(view=error_layout("Not a member", "Pick another member of your clan."))
        view = ConfirmLayout("Transfer clan", f"Make {user.mention} the owner of **{clan['name']}**?", author_id=ctx.author.id, timeout=30.0)
        message = await ctx.send(view=view, allowed_mentions=NO_PINGS)
        await view.wait()
        if view.value is not True:
            return
        await clans.transfer(clan["clan_id"], ctx.author.id, user.id)
        await message.edit(view=success_layout("Transferred", f"{user.mention} now owns **{clan['name']}**."))

    @clan_group.command(name="disband", help="Delete your clan. The bank is lost.")
    async def clan_disband(self, ctx: commands.Context):
        found = await self.own(ctx, "owner")
        if not found:
            return
        mine, clan = found
        view = ConfirmLayout("Disband clan", f"Delete **{clan['name']}** and remove all members? Its bank of **{coins.fmt(clan['bank'])}** coins is lost.", author_id=ctx.author.id, timeout=30.0)
        message = await ctx.send(view=view)
        await view.wait()
        if view.value is not True:
            return
        await clans.disband(clan["clan_id"])
        await message.edit(view=success_layout("Disbanded", f"**{clan['name']}** no longer exists."))

    @clan_group.command(name="deposit", aliases=["donate"], help="Put coins in the clan bank. Usage: clan deposit <amount>")
    async def clan_deposit(self, ctx: commands.Context, amount: int):
        e = emoji_manager.get
        found = await self.own(ctx)
        if not found:
            return
        mine, clan = found
        if amount < config.COIN_TRANSFER_MIN:
            return await ctx.send(view=error_layout("Too small", f"The smallest deposit is **{config.COIN_TRANSFER_MIN}** coins."))
        if not await clans.deposit(clan["clan_id"], ctx.author.id, amount):
            return await ctx.send(view=error_layout("Not enough coins", f"You have **{coins.fmt(await coins.balance(ctx.author.id))}** coins."))
        await ctx.send(view=success_layout(f"{e('bank')} Deposited", f"You added **{coins.fmt(amount)}** coins to the bank of **{clan['name']}**."))

    @clan_group.command(name="upgrade", help="Spend bank coins to raise the clan level and member limit.")
    async def clan_upgrade(self, ctx: commands.Context):
        e = emoji_manager.get
        found = await self.own(ctx, "officer")
        if not found:
            return
        mine, clan = found
        cost = clans.upgrade_cost(clan["level"])
        ok, detail = await clans.upgrade(clan["clan_id"])
        if not ok:
            if detail == "maxed":
                return await ctx.send(view=error_layout("Max level", "Your clan is already at the top level."))
            return await ctx.send(view=error_layout("Not enough in the bank", f"The next level costs **{coins.fmt(cost)}** coins. The bank has **{coins.fmt(clan['bank'])}**. Add more with `clan deposit`."))
        await ctx.send(view=success_layout(f"{e('shield')} Level up", f"**{clan['name']}** is now level **{detail}** and holds **{clans.capacity(int(detail))}** members."))

    @clan_group.command(name="description", aliases=["desc"], help="Set the clan description. Usage: clan description <text>")
    async def clan_description(self, ctx: commands.Context, *, text: str):
        found = await self.own(ctx, "officer")
        if not found:
            return
        mine, clan = found
        await clans.set_description(clan["clan_id"], text)
        await ctx.send(view=success_layout("Updated", "The clan description was changed."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Clans(bot))
