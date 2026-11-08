import asyncio
import io
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import clans, coins, emoji_manager, family_tree, names as names_util
from cogs.economy import duration
from utils.components import ConfirmLayout, error_layout, info_layout, success_layout

NO_PINGS = discord.AllowedMentions.none()
ROLE_LABELS = {"owner": "Young Master", "officer": "Elder", "member": "Member"}


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
            f"**Tier:** {clans.tier(clan['level'])['name']} ({min(clan['level'], clans.top_level())}/{clans.top_level()})",
            f"**Members:** {size}/{clans.capacity(clan['level'])}",
            f"**Families:** {await clans.family_count(clan)}/{clans.family_limit(clan['level'])}",
            f"**Member bonus:** +{clans.tier(clan['level'])['bonus']}% coins from reward, work and trips · **Stipend:** {clans.tier(clan['level'])['stipend']} coins a day",
            f"{e('ebank')} **Bank:** {coins.fmt(clan['bank'])} coins" + (f" · next tier costs {coins.fmt(clans.upgrade_cost(clan['level']))} and needs {clans.next_tier(clan['level'])['need']} members" if clans.next_tier(clan['level']) else " · top tier"),
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
        names = {item["branch_key"]: item["name"] for item in await clans.branches(clan["clan_id"])}
        lines = [f"{ROLE_LABELS[row['role']]} · <@{row['user_id']}>" + (f" · {names[row['branch']]} Branch" if row.get("branch") in names else "") for row in rows]
        await ctx.send(view=info_layout(f"{e('shield')} {clan['name']} members", "\n".join(lines)), allowed_mentions=NO_PINGS)

    async def target_clan(self, ctx: commands.Context, name: Optional[str]) -> Optional[dict]:
        if name:
            clan = await clans.find(name)
        else:
            mine = await clans.membership(ctx.author.id)
            clan = await clans.get(mine["clan_id"]) if mine else None
        if clan is None:
            await ctx.send(view=error_layout("Not found", "Use a clan name, or join a clan first."))
        return clan

    def family_labels(self, found: dict, names: dict[int, str]) -> list[tuple[dict, str]]:
        out = []
        for group in found["families"]:
            if group["main"]:
                label = "Main family"
            else:
                head = discord.utils.escape_markdown(names.get(group["head"], "someone"))
                label = f"Branch of {head}"
            out.append((group, label))
        return out

    @clan_group.command(name="families", help="Show the families inside a clan. Usage: clan families [name]")
    async def clan_families(self, ctx: commands.Context, *, name: Optional[str] = None):
        e = emoji_manager.get
        clan = await self.target_clan(ctx, name)
        if clan is None:
            return
        async with ctx.typing():
            found = await clans.families(clan, config.CLAN_TREE_LIMIT)
            roles = {m["user_id"]: m["role"] for m in await clans.members(clan["clan_id"])}
            ids = set(roles)
            names, _ = await names_util.resolve(self.bot, ids | {g["head"] for g in found["families"]})

        def who(user_id: int) -> str:
            tag = " (owner)" if roles[user_id] == "owner" else " (officer)" if roles[user_id] == "officer" else ""
            return discord.utils.escape_markdown(names.get(user_id, f"User {str(user_id)[-4:]}")) + tag

        lines = []
        for group, label in self.family_labels(found, names):
            lines.append(f"**{label}** · {len(group['members'])} in the clan · {len(group['comp']['nodes'])} in the family")
            lines.append(", ".join(who(m) for m in group["members"]))
            lines.append("")
        if found["unattached"]:
            lines.append(f"**No family yet** · {len(found['unattached'])}")
            lines.append(", ".join(who(m) for m in found["unattached"]))
        if not found["families"]:
            lines.insert(0, "Nobody in this clan has a family yet. Members who marry or adopt form families, and every connected family becomes a branch of the clan.")
        body = "\n".join(lines).strip()
        await ctx.send(view=info_layout(f"{e('shield')} {clan['name']} families", body[:3800] + ("\n..." if len(body) > 3800 else "") + "\n-# See them all with `clan tree`."), allowed_mentions=NO_PINGS)

    @clan_group.command(name="branch", aliases=["branches", "house"], help="Found or join a named branch of your clan. Usage: clan branch [create|join|leave|disband|list] [name]")
    async def clan_branch(self, ctx: commands.Context, action: Optional[str] = None, *, name: str = ""):
        e = emoji_manager.get
        mine = await clans.membership(ctx.author.id)
        if mine is None:
            return await ctx.send(view=error_layout("No clan", "Join or start a clan first."))
        clan = await clans.get(mine["clan_id"])
        found = await clans.branches(clan["clan_id"])
        action = (action or "list").lower()
        if action == "list":
            limit = clans.branch_limit(clan["level"])
            lines = [f"**{item['name']} Branch** · {item['members']} member{'s' if item['members'] != 1 else ''} · founded by <@{item['founder_id']}>" for item in found]
            if not lines:
                lines = ["No branches yet. An Elder or the Young Master can found one with `clan branch create <name>`."]
            lines.append(f"\n-# {len(found)}/{limit} branches. A higher clan tier allows more. Join one with `clan branch join <name>`.")
            return await ctx.send(view=info_layout(f"{e('shield')} {clan['name']} branches", "\n".join(lines)), allowed_mentions=NO_PINGS)
        if action == "leave":
            if not mine.get("branch"):
                return await ctx.send(view=error_layout("No branch", "You are not in a branch."))
            await clans.set_branch(ctx.author.id, "")
            return await ctx.send(view=success_layout("Left the branch", "You are back in the main family."))
        if not name.strip():
            return await ctx.send(view=error_layout("Name needed", "Use `clan branch create <name>`, `join <name>` or `disband <name>`."))
        if action in ("create", "found", "start"):
            if clans.ROLE_ORDER[mine["role"]] < clans.ROLE_ORDER["officer"]:
                return await ctx.send(view=error_layout("Elders only", "Only an Elder or the Young Master can found a branch."))
            result = await clans.create_branch(clan["clan_id"], ctx.author.id, name)
            reasons = {
                "name": ("Bad name", "Use 3 to 20 letters, numbers, spaces, dashes or underscores."),
                "taken": ("Name taken", "Your clan already has a branch with that name."),
                "limit": ("Too many branches", f"Your clan tier allows **{clans.branch_limit(clan['level'])}** branches. Upgrade the clan for more."),
            }
            if result != "ok":
                title, body = reasons[result]
                return await ctx.send(view=error_layout(title, body))
            return await ctx.send(view=success_layout("Branch founded", f"The **{clans.clean_name(name)} Branch** of the fallen {clan['name']} clan has been founded, and you lead it. Others can join with `clan branch join {clans.clean_name(name)}`."))
        branch = await clans.find_branch(clan["clan_id"], name)
        if branch is None:
            return await ctx.send(view=error_layout("Unknown branch", "See the list with `clan branch list`."))
        if action == "join":
            await clans.set_branch(ctx.author.id, branch["branch_key"])
            return await ctx.send(view=success_layout("Joined", f"You now belong to the **{branch['name']} Branch**."))
        if action in ("disband", "delete", "remove"):
            if clans.ROLE_ORDER[mine["role"]] < clans.ROLE_ORDER["owner"] and branch["founder_id"] != ctx.author.id:
                return await ctx.send(view=error_layout("Not yours", "Only the Young Master or the branch's founder can disband it."))
            await clans.remove_branch(clan["clan_id"], branch["branch_key"])
            return await ctx.send(view=success_layout("Branch disbanded", f"The **{branch['name']} Branch** is gone. Its members return to the main family."))
        await ctx.send(view=error_layout("Unknown action", "Use create, join, leave, disband or list."))

    @clan_group.command(name="tree", help="Draw every family in a clan. Usage: clan tree [name]")
    @commands.cooldown(1, 15.0, commands.BucketType.user)
    async def clan_tree(self, ctx: commands.Context, *, name: Optional[str] = None):
        e = emoji_manager.get
        clan = await self.target_clan(ctx, name)
        if clan is None:
            return
        async with ctx.typing():
            found = await clans.families(clan, config.CLAN_TREE_LIMIT)
            if not found["families"]:
                return await ctx.send(view=info_layout(f"{e('shield')} {clan['name']} family tree", "Nobody in this clan has a family yet."))
            comp = clans.merged(found)
            roles = await clans.members(clan["clan_id"])
            clan_ids = {m["user_id"] for m in roles}
            names, usernames = await names_util.resolve(self.bot, comp["nodes"])
            groups = {}
            for group, label in self.family_labels(found, names):
                for member in group["comp"]["nodes"]:
                    groups[member] = label
            image = await asyncio.to_thread(family_tree.render, comp, names, clan_ids, usernames, groups)
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            buffer.seek(0)
        summary = f"{len(found['families'])} families · {len(comp['nodes'])} people shown · clan members are blue"
        if found["truncated"]:
            summary += f"\nShowing the closest {config.CLAN_TREE_LIMIT} people."
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=0x2B2D31)
        container.add_item(discord.ui.TextDisplay(f"## {e('shield')} {clan['name']} family tree\n{summary}"))
        container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://clan_tree.png")))
        view.add_item(container)
        await ctx.send(view=view, file=discord.File(buffer, "clan_tree.png"), allowed_mentions=NO_PINGS)

    @clan_group.command(name="top", aliases=["leaderboard", "lb", "list"], help="Show the top clans.")
    async def clan_top(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await clans.top(10)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('trophy')} Top clans", "No clans yet. Start one with `clan create <name>`."))
        lines = [f"**{i}.** {row['name']} · {clans.tier(row['level'])['name']} · {row['size']} members" for i, row in enumerate(rows, 1)]
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
            return await ctx.send(view=error_layout("Clan is full", "Raise the clan tier with `clan upgrade` to fit more members."))
        if await clans.joins_new_family(clan, user.id) and await clans.family_count(clan) >= clans.family_limit(clan["level"]):
            return await ctx.send(view=error_layout("Family limit reached", f"{user.mention} belongs to a different family and your tier allows **{clans.family_limit(clan['level'])}** famil{'y' if clans.family_limit(clan['level']) == 1 else 'ies'}. Raise the clan tier with `clan upgrade`."), allowed_mentions=NO_PINGS)
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
            if await clans.joins_new_family(clan, ctx.author.id) and await clans.family_count(clan) >= clans.family_limit(clan["level"]):
                return await ctx.send(view=error_layout("Family limit reached", "Your family would be one more than that clan's tier allows. The clan needs a higher tier first."))
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

    @clan_group.command(name="deposit", aliases=["donate", "build", "contribute"], help="Put coins in the clan bank to build the clan up. Usage: clan deposit <amount>")
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
        await ctx.send(view=success_layout(f"{e('ebank')} Deposited", f"You added **{coins.fmt(amount)}** coins to the bank of **{clan['name']}**. Coins in the bank pay for tier upgrades and the daily stipend."))

    @clan_group.command(name="upgrade", aliases=["tier", "levelup"], help="Spend bank coins to raise the clan tier.")
    async def clan_upgrade(self, ctx: commands.Context):
        e = emoji_manager.get
        found = await self.own(ctx, "officer")
        if not found:
            return
        mine, clan = found
        nxt = clans.next_tier(clan["level"])
        ok, detail = await clans.upgrade(clan["clan_id"])
        if not ok:
            if detail == "maxed":
                return await ctx.send(view=error_layout("Top tier", "Your clan is already a Heavenly Clan."))
            if detail == "members":
                size = await clans.member_count(clan["clan_id"])
                return await ctx.send(view=error_layout("Not enough members", f"**{nxt['name']}** needs **{nxt['need']}** members and your clan has **{size}**."))
            return await ctx.send(view=error_layout("Not enough in the bank", f"**{nxt['name']}** costs **{coins.fmt(nxt['cost'])}** coins. The bank has **{coins.fmt(clan['bank'])}**. Members add coins with `clan deposit`."))
        new = clans.tier(int(detail))
        await ctx.send(view=success_layout(f"{e('shield')} Clan tier raised", f"**{clan['name']}** is now a **{new['name']}**.\n**{new['members']}** members · **{new['families']}** families · **+{new['bonus']}%** coins for members · **{new['stipend']}** coins stipend a day."))

    @clan_group.command(name="tiers", aliases=["levels", "benefits"], help="Show every clan tier and what it gives.")
    async def clan_tiers(self, ctx: commands.Context):
        e = emoji_manager.get
        mine = await clans.membership(ctx.author.id)
        clan = await clans.get(mine["clan_id"]) if mine else None
        lines = []
        for index, item in enumerate(config.CLAN_TIERS, 1):
            here = " **(your clan)**" if clan and min(clan["level"], clans.top_level()) == index else ""
            cost = "free" if not item["cost"] else f"{coins.fmt(item['cost'])} coins and {item['need']} members"
            lines.append(f"**{index}. {item['name']}**{here}\n{item['members']} members · {item['families']} famil{'y' if item['families'] == 1 else 'ies'} · +{item['bonus']}% coins · {item['stipend']} coin stipend · {cost}")
        lines.append("\n-# The bonus applies to coins from `reward`, `work`, `gather`, `hunt`, `mine` and `ruins`. Members add coins with `clan deposit`; officers raise the tier with `clan upgrade`.")
        await ctx.send(view=info_layout(f"{e('shield')} Clan tiers", "\n".join(lines)))

    @clan_group.command(name="stipend", aliases=["payout", "dividend"], help="Collect your clan stipend, or turn it on or off as owner. Usage: clan stipend [on|off]")
    async def clan_stipend(self, ctx: commands.Context, mode: Optional[str] = None):
        e = emoji_manager.get
        if mode:
            found = await self.own(ctx, "owner")
            if not found:
                return
            mine, clan = found
            if mode.lower() not in ("on", "off"):
                return await ctx.send(view=error_layout("Use on or off", "`clan stipend on` or `clan stipend off`."))
            await clans.set_stipend(clan["clan_id"], mode.lower() == "on")
            return await ctx.send(view=success_layout("Stipend updated", f"The clan stipend is now **{mode.lower()}**."))
        async with self.lock:
            result = await clans.claim_stipend(ctx.author.id)
        if result["ok"]:
            return await ctx.send(view=success_layout(f"{e('ebank')} Clan stipend", f"**{result['clan']['name']}** gave you {e('ecoin')} **{coins.fmt(result['amount'])}** coins from the clan bank."))
        reason = result["reason"]
        if reason == "no_clan":
            return await ctx.send(view=error_layout("No clan", "You are not in a clan."))
        if reason == "no_tier":
            return await ctx.send(view=error_layout("No stipend yet", "A Wandering Clan pays no stipend. Raise the tier with `clan upgrade`."))
        if reason == "off":
            return await ctx.send(view=error_layout("Stipend is off", "The clan owner turned the stipend off."))
        if reason == "cooldown":
            return await ctx.send(view=error_layout("Already collected", f"You can collect again in **{duration(result['wait'])}**."))
        await ctx.send(view=error_layout("The bank is too low", f"The stipend is **{coins.fmt(result['amount'])}** coins and the bank cannot pay it. Members can add coins with `clan deposit`."))

    @clan_group.command(name="contributions", aliases=["builders", "donors"], help="Show who built the clan up the most.")
    async def clan_contributions(self, ctx: commands.Context, *, name: Optional[str] = None):
        e = emoji_manager.get
        clan = await self.target_clan(ctx, name)
        if clan is None:
            return
        rows = await clans.contributions(clan["clan_id"])
        if not rows:
            return await ctx.send(view=info_layout(f"{e('ebank')} Clan builders", "Nobody has added coins yet. Use `clan deposit <amount>`."))
        lines = [f"**{i}.** <@{row['user_id']}> · {coins.fmt(row['amount'])} coins" for i, row in enumerate(rows, 1)]
        await ctx.send(view=info_layout(f"{e('ebank')} {clan['name']} builders", "\n".join(lines)), allowed_mentions=NO_PINGS)

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
