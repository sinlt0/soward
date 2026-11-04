import asyncio
import io
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import coins, emoji_manager, family, family_tree, names as names_util
from utils.components import ConfirmLayout, error_layout, info_layout, success_layout

NO_PINGS = discord.AllowedMentions.none()


def mention(user_id: int) -> str:
    return f"<@{user_id}>"


class Family(commands.Cog):
    category = "Family"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.locks: dict[int, asyncio.Lock] = {}

    def lock_for(self, user_id: int) -> asyncio.Lock:
        return self.locks.setdefault(user_id, asyncio.Lock())

    async def ask(self, ctx: commands.Context, target: discord.User, title: str, body: str) -> Optional[bool]:
        view = ConfirmLayout(title, body, author_id=target.id, timeout=float(config.FAMILY_REQUEST_SECONDS))
        message = await ctx.send(view=view, allowed_mentions=discord.AllowedMentions(users=[target]))
        await view.wait()
        for item in view.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
        try:
            await message.edit(view=view)
        except discord.HTTPException:
            pass
        return view.value

    def invalid_target(self, ctx: commands.Context, user: discord.User) -> Optional[str]:
        if user.bot:
            return "Bots cannot join a family."
        if user.id == ctx.author.id:
            return "You cannot do that with yourself."
        return None

    @commands.command(name="marry", aliases=["propose"], help="Propose to someone. Usage: marry <user>")
    async def marry(self, ctx: commands.Context, user: discord.User):
        e = emoji_manager.get
        problem = self.invalid_target(ctx, user)
        if problem:
            return await ctx.send(view=error_layout("Cannot propose", problem))
        first, second = sorted((ctx.author.id, user.id))
        async with self.lock_for(first), self.lock_for(second):
            blocker = await family.marry_blocker(ctx.author.id, user.id)
            if blocker:
                return await ctx.send(view=error_layout("Cannot propose", self.describe_blocker(blocker, ctx, user)))
        answer = await self.ask(ctx, user, f"{e('gift')} Proposal", f"{user.mention}, {ctx.author.mention} is asking you to marry them. Do you accept?")
        if answer is not True:
            return await ctx.send(view=info_layout("Proposal", f"{user.mention} did not accept." if answer is False else "The proposal timed out."), allowed_mentions=NO_PINGS)
        async with self.lock_for(first), self.lock_for(second):
            blocker = await family.marry_blocker(ctx.author.id, user.id)
            if blocker:
                return await ctx.send(view=error_layout("Cannot marry", self.describe_blocker(blocker, ctx, user)))
            await family.marry(ctx.author.id, user.id)
        await ctx.send(view=success_layout(f"{e('star')} Married", f"{ctx.author.mention} and {user.mention} are now married. Congratulations!"), allowed_mentions=NO_PINGS)

    def describe_blocker(self, blocker: str, ctx: commands.Context, user: discord.User) -> str:
        if blocker.startswith("marriage_full:"):
            who = int(blocker.split(":")[1])
            if who == ctx.author.id:
                return f"You have no free marriage slot. Divorce first or use `family upgrade marriage` ({coins.fmt(config.MARRIAGE_SLOT_COST)} coins)."
            return f"{user.mention} has no free marriage slot."
        if blocker == "adopt_full":
            return f"You have no free adoption slot. Use `family upgrade adopt` ({coins.fmt(config.ADOPT_SLOT_COST)} coins) or `disown` someone."
        return blocker

    @commands.command(name="divorce", help="End a marriage. Usage: divorce [user]")
    async def divorce(self, ctx: commands.Context, user: Optional[discord.User] = None):
        e = emoji_manager.get
        spouses = await family.partners(ctx.author.id)
        if not spouses:
            return await ctx.send(view=error_layout("Not married", "You are not married."))
        if user is None:
            if len(spouses) > 1:
                return await ctx.send(view=error_layout("Who?", "You have more than one partner. Use `divorce <user>`."))
            target_id = spouses[0]
        else:
            target_id = user.id
        if target_id not in spouses:
            return await ctx.send(view=error_layout("Not married", "You are not married to that person."))
        view = ConfirmLayout("Divorce", f"End your marriage with {mention(target_id)}?", author_id=ctx.author.id, timeout=30.0)
        message = await ctx.send(view=view, allowed_mentions=NO_PINGS)
        await view.wait()
        if view.value is not True:
            return
        await family.divorce(ctx.author.id, target_id)
        await message.edit(view=success_layout(f"{e('check')} Divorced", f"Your marriage with {mention(target_id)} has ended."))

    @commands.command(name="adopt", help="Ask someone to become your child. Usage: adopt <user>")
    async def adopt(self, ctx: commands.Context, user: discord.User):
        e = emoji_manager.get
        problem = self.invalid_target(ctx, user)
        if problem:
            return await ctx.send(view=error_layout("Cannot adopt", problem))
        async with self.lock_for(ctx.author.id):
            blocker = await family.adopt_blocker(ctx.author.id, user.id)
            if blocker:
                return await ctx.send(view=error_layout("Cannot adopt", self.describe_blocker(blocker, ctx, user)))
        answer = await self.ask(ctx, user, f"{e('gift')} Adoption", f"{user.mention}, {ctx.author.mention} wants to adopt you. Do you accept?")
        if answer is not True:
            return await ctx.send(view=info_layout("Adoption", f"{user.mention} did not accept." if answer is False else "The request timed out."), allowed_mentions=NO_PINGS)
        async with self.lock_for(ctx.author.id), self.lock_for(user.id):
            blocker = await family.adopt_blocker(ctx.author.id, user.id)
            if blocker:
                return await ctx.send(view=error_layout("Cannot adopt", self.describe_blocker(blocker, ctx, user)))
            await family.adopt(ctx.author.id, user.id)
        await ctx.send(view=success_layout(f"{e('star')} Adopted", f"{ctx.author.mention} adopted {user.mention}. Welcome to the family!"), allowed_mentions=NO_PINGS)

    @commands.command(name="disown", help="Remove a child from your family. Usage: disown <user>")
    async def disown(self, ctx: commands.Context, user: discord.User):
        if await family.parent_of(user.id) != ctx.author.id:
            return await ctx.send(view=error_layout("Not your child", "That person is not one of your children."))
        await family.release(user.id)
        await ctx.send(view=success_layout("Disowned", f"{user.mention} is no longer your child."), allowed_mentions=NO_PINGS)

    @commands.command(name="runaway", aliases=["leavefamily"], help="Leave the person who adopted you.")
    async def runaway(self, ctx: commands.Context):
        parent = await family.parent_of(ctx.author.id)
        if parent is None:
            return await ctx.send(view=error_layout("No parent", "Nobody has adopted you."))
        await family.release(ctx.author.id)
        await ctx.send(view=success_layout("You left", f"You are no longer {mention(parent)}'s child."), allowed_mentions=NO_PINGS)

    @commands.group(name="family", aliases=["fam"], invoke_without_command=True, help="Show a family. Usage: family [user]")
    async def family_group(self, ctx: commands.Context, user: Optional[discord.User] = None):
        e = emoji_manager.get
        target = user or ctx.author
        spouses = await family.partners(target.id)
        parent = await family.parent_of(target.id)
        kids = await family.children_of(target.id)
        siblings = [kid for kid in await family.children_of(parent) if kid != target.id] if parent else []
        limits = await family.slots(target.id)
        lines = [
            f"**Partners** ({len(spouses)}/{limits['marriage']}): " + (", ".join(mention(i) for i in spouses) or "none"),
            f"**Parent:** {mention(parent) if parent else 'none'}",
            f"**Children** ({len(kids)}/{limits['adopt']}): " + (", ".join(mention(i) for i in kids) or "none"),
        ]
        if siblings:
            lines.append("**Siblings:** " + ", ".join(mention(i) for i in siblings))
        await ctx.send(view=info_layout(f"{e('star')} {target.display_name}'s family", "\n".join(lines)), allowed_mentions=NO_PINGS)

    async def send_tree(self, ctx: commands.Context, target: discord.abc.User):
        e = emoji_manager.get
        comp = await family.component(target.id, config.FAMILY_TREE_LIMIT)
        if len(comp["nodes"]) < 2:
            return await ctx.send(view=info_layout(f"{e('star')} {target.display_name}'s family tree", "No family yet. Use `marry` or `adopt` to start one."))
        async with ctx.typing():
            names, usernames = await names_util.resolve(self.bot, comp["nodes"])
            image = await asyncio.to_thread(family_tree.render, comp, names, target.id, usernames)
            buffer = io.BytesIO()
            image.save(buffer, "PNG")
            buffer.seek(0)
            info = family_tree.stats(comp)
        summary = f"{info['members']} members · {info['generations']} generations · {info['couples']} marriages · {info['adoptions']} adoptions"
        if comp["truncated"]:
            summary += f"\nShowing the closest {config.FAMILY_TREE_LIMIT} people."
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=0x2B2D31)
        container.add_item(discord.ui.TextDisplay(f"## {e('star')} {target.display_name}'s family tree\n{summary}"))
        container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://family_tree.png")))
        view.add_item(container)
        await ctx.send(view=view, file=discord.File(buffer, "family_tree.png"), allowed_mentions=NO_PINGS)

    @commands.command(name="tree", aliases=["familytree"], help="Show a family tree picture. Usage: tree [user]")
    @commands.cooldown(1, 10.0, commands.BucketType.user)
    async def tree(self, ctx: commands.Context, user: Optional[discord.User] = None):
        await self.send_tree(ctx, user or ctx.author)

    @family_group.command(name="tree", help="Show a family tree picture. Usage: family tree [user]")
    @commands.cooldown(1, 10.0, commands.BucketType.user)
    async def family_tree_command(self, ctx: commands.Context, user: Optional[discord.User] = None):
        await self.send_tree(ctx, user or ctx.author)

    async def send_size(self, ctx: commands.Context, target: discord.abc.User):
        e = emoji_manager.get
        comp = await family.component(target.id, config.FAMILY_TREE_LIMIT)
        if len(comp["nodes"]) < 2:
            return await ctx.send(view=info_layout(f"{e('star')} {target.display_name}'s family", "No family yet. Use `marry` or `adopt` to start one."))
        info = family_tree.stats(comp)
        async with ctx.typing():
            names, _ = await names_util.resolve(self.bot, comp["nodes"])

        def label(user_id: int) -> str:
            return discord.utils.escape_markdown(names.get(user_id, f"User {str(user_id)[-4:]}"))

        header = (f"**{info['members']}** members · **{info['generations']}** generations · **{info['couples']}** marriages · **{info['adoptions']}** adoptions"
                  + (f"\nShowing the closest {config.FAMILY_TREE_LIMIT} people." if comp["truncated"] else ""))
        blocks = []
        for number, generation in enumerate(family_tree.report(comp), 1):
            lines = [f"**Generation {number}**"]
            for person in generation:
                bits = []
                if person["parent"]:
                    bits.append(f"child of {label(person['parent'])}")
                if person["partners"]:
                    bits.append("partner of " + ", ".join(label(i) for i in person["partners"]))
                you = " (you)" if person["id"] == ctx.author.id else ""
                lines.append(f"{label(person['id'])}{you}" + (f" · {', '.join(bits)}" if bits else ""))
            blocks.append("\n".join(lines))
        pages, current = [], header
        for block in blocks:
            if len(current) + len(block) + 2 > 3400:
                pages.append(current)
                current = ""
            current = f"{current}\n\n{block}" if current else block
        pages.append(current)
        for index, page in enumerate(pages[:4]):
            title = f"{e('star')} {target.display_name}'s family" + (f" ({index + 1}/{min(len(pages), 4)})" if len(pages) > 1 else "")
            await ctx.send(view=info_layout(title, page), allowed_mentions=NO_PINGS)
        if len(pages) > 4:
            await ctx.send(view=info_layout("More members", "The list is too long to show in full. Use `tree` to see everyone."))

    @commands.command(name="familysize", aliases=["familymembers", "fsize"], help="List everyone in a family, including relatives by marriage. Usage: familysize [user]")
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def familysize(self, ctx: commands.Context, user: Optional[discord.User] = None):
        await self.send_size(ctx, user or ctx.author)

    @family_group.command(name="size", aliases=["stats", "members"], help="List everyone in a family, including relatives by marriage. Usage: family size [user]")
    @commands.cooldown(1, 5.0, commands.BucketType.user)
    async def family_size(self, ctx: commands.Context, user: Optional[discord.User] = None):
        await self.send_size(ctx, user or ctx.author)

    @family_group.command(name="upgrade", aliases=["buy"], help="Buy another marriage or adoption slot with coins. Usage: family upgrade <marriage|adopt>")
    async def family_upgrade(self, ctx: commands.Context, kind: str = ""):
        e = emoji_manager.get
        kind = kind.lower()
        if kind in ("marriage", "marry", "partner"):
            kind, cost, maximum = "marriage", config.MARRIAGE_SLOT_COST, config.MARRIAGE_SLOTS_MAX
        elif kind in ("adopt", "adoption", "child", "children"):
            kind, cost, maximum = "adopt", config.ADOPT_SLOT_COST, config.ADOPT_SLOTS_MAX
        else:
            limits = await family.slots(ctx.author.id)
            return await ctx.send(view=info_layout(f"{e('ecoin')} Family slots", (
                f"**Marriage slots:** {limits['marriage']}/{config.MARRIAGE_SLOTS_MAX} · {coins.fmt(config.MARRIAGE_SLOT_COST)} coins each\n"
                f"**Adoption slots:** {limits['adopt']}/{config.ADOPT_SLOTS_MAX} · {coins.fmt(config.ADOPT_SLOT_COST)} coins each\n\n"
                "Use `family upgrade marriage` or `family upgrade adopt`.")))
        async with self.lock_for(ctx.author.id):
            ok, detail = await family.upgrade(ctx.author.id, kind)
        if not ok:
            if detail == "maxed":
                return await ctx.send(view=error_layout("Maxed out", f"You already have the most {kind} slots ({maximum})."))
            return await ctx.send(view=error_layout("Not enough coins", f"That costs **{coins.fmt(cost)}** coins. You have **{coins.fmt(await coins.balance(ctx.author.id))}**."))
        await ctx.send(view=success_layout(f"{e('check')} Upgraded", f"You now have **{detail}** {kind} slots. **{coins.fmt(cost)}** coins were spent."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Family(bot))
