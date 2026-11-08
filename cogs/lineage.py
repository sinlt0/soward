import time
from typing import Optional

import discord
from discord.ext import commands

from cogs.cultivation import NO_PINGS, bloodline_text, fight_layout
from cogs.economy import duration
from rpg import engine as cult, settings
from utils import coins, emoji_manager, family as family_utils
from utils.colors import NEUTRAL
from utils.components import error_layout, footer_block, info_layout, success_layout


def mention(user_id: int) -> str:
    return f"<@{user_id}>"


class JoinRow(discord.ui.ActionRow):
    def __init__(self, owner: "DungeonView"):
        super().__init__(
            discord.ui.Button(label="Join", style=discord.ButtonStyle.primary),
            discord.ui.Button(label="Start", style=discord.ButtonStyle.success),
            discord.ui.Button(label="Cancel", style=discord.ButtonStyle.danger),
        )
        self.owner = owner
        self.children[0].callback = self.join
        self.children[1].callback = self.start
        self.children[2].callback = self.cancel

    async def join(self, interaction: discord.Interaction):
        await self.owner.join(interaction)

    async def start(self, interaction: discord.Interaction):
        await self.owner.start(interaction)

    async def cancel(self, interaction: discord.Interaction):
        await self.owner.cancel(interaction)


class DungeonView(discord.ui.LayoutView):
    def __init__(self, leader: int, family: set, cog: "Lineage"):
        super().__init__(timeout=120)
        self.leader = leader
        self.family = family
        self.cog = cog
        self.members: list[int] = [leader]
        self.row = JoinRow(self)
        self.render()

    def render(self) -> None:
        e = emoji_manager.get
        self.clear_items()
        container = discord.ui.Container(accent_color=NEUTRAL)
        names = "\n".join(mention(uid) for uid in self.members)
        container.add_item(discord.ui.TextDisplay(
            f"## {e('esword')} Family dungeon\n{mention(self.leader)} is gathering family to enter a dungeon.\n\n"
            f"**Party ({len(self.members)}/{settings.DUNGEON_MAX_PARTY}):**\n{names}\n\n"
            f"-# Family members press Join. The leader presses Start with at least 2 members. Each member can enter {settings.DUNGEON_DAILY} dungeons a day."))
        container.add_item(discord.ui.Separator())
        container.add_item(self.row)
        for item in footer_block():
            container.add_item(item)
        self.add_item(container)

    async def join(self, interaction: discord.Interaction):
        uid = interaction.user.id
        if uid in self.members:
            return await interaction.response.send_message("You are already in the party.", ephemeral=True)
        if uid not in self.family:
            return await interaction.response.send_message("Only the leader's family can join.", ephemeral=True)
        if len(self.members) >= settings.DUNGEON_MAX_PARTY:
            return await interaction.response.send_message("The party is full.", ephemeral=True)
        character = await cult.get(uid)
        if character is None or not character["path"]:
            return await interaction.response.send_message("You have not awakened yet. Use `cultivate awaken`.", ephemeral=True)
        self.members.append(uid)
        self.render()
        await interaction.response.edit_message(view=self, allowed_mentions=NO_PINGS)

    async def cancel(self, interaction: discord.Interaction):
        if interaction.user.id != self.leader:
            return await interaction.response.send_message("Only the leader can cancel.", ephemeral=True)
        self.cog.cultivation_active().discard(self.leader)
        self.stop()
        await interaction.response.edit_message(view=info_layout("Dungeon cancelled", "The party disbanded."))

    async def start(self, interaction: discord.Interaction):
        if interaction.user.id != self.leader:
            return await interaction.response.send_message("Only the leader can start.", ephemeral=True)
        result = await cult.dungeon_start(self.leader, self.members[1:])
        if not result["ok"]:
            reasons = {
                "size": f"You need between 2 and {settings.DUNGEON_MAX_PARTY} members.",
                "hurt": f"{mention(result.get('user', 0))} is injured.",
                "limit": f"{mention(result.get('user', 0))} has no dungeon runs left today.",
                "none": f"{mention(result.get('user', 0))} has not awakened.",
                "stranger": f"{mention(result.get('user', 0))} is not family.",
            }
            return await interaction.response.send_message(reasons.get(result["reason"], "That did not work."), ephemeral=True, allowed_mentions=NO_PINGS)
        self.stop()
        view = fight_layout(result["state"], self.leader, 0, self.cog.cultivation_active())
        await interaction.response.edit_message(view=view, allowed_mentions=NO_PINGS)

    async def on_timeout(self) -> None:
        self.cog.cultivation_active().discard(self.leader)


class Lineage(commands.Cog):
    category = "Cultivation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def cultivation_active(self) -> set:
        cog = self.bot.get_cog("Cultivation")
        return cog.active if cog else set()

    async def need_character(self, ctx: commands.Context) -> Optional[dict]:
        character = await cult.get(ctx.author.id)
        if character is None or not character["path"]:
            await ctx.send(view=error_layout("Not awakened", "You have not awakened yet. Use `cultivate awaken` to begin."))
            return None
        return character

    @commands.group(name="lineage", aliases=["household", "bloodline"], invoke_without_command=True, help="Your cultivating family: dual cultivation, treasury and dungeons.")
    async def lineage(self, ctx: commands.Context):
        await self.status(ctx)

    @lineage.command(name="status", aliases=["info"], help="Show your family's cultivation.")
    async def status(self, ctx: commands.Context):
        e = emoji_manager.get
        character = await self.need_character(ctx)
        if character is None:
            return
        circle = await cult.circle(ctx.author.id)
        vault = await cult.treasury(ctx.author.id)
        awake = [uid for uid in circle if await cult.get(uid)]
        heir = f"<@{vault['heir']}>" if vault["heir"] else "none"
        lines = [
            f"**Bloodline:** {bloodline_text(character)}",
            f"**Family circle:** {len(circle)} relatives, {len(awake)} cultivating",
            f"**Treasury:** {coins.fmt(vault['coins'])}/{coins.fmt(await cult.treasury_cap(ctx.author.id))} coins · heir {heir}",
            "",
            "`lineage dual [partner]` cultivate together with your partner",
            "`lineage treasury [deposit|withdraw] [amount] [owner]` the shared family coffer",
            "`lineage heir <user>` and `lineage inherit <user>` pass the treasury on",
            "`lineage dungeon` take your family into a dungeon",
        ]
        await ctx.send(view=info_layout(f"{e('ecult')} Your lineage", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @lineage.command(name="dual", aliases=["pair", "couple"], help="Cultivate together with your partner. Usage: lineage dual [partner]")
    async def dual(self, ctx: commands.Context, partner: Optional[discord.User] = None):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        if partner is None:
            options = await family_utils.partners(ctx.author.id)
            if len(options) != 1:
                return await ctx.send(view=error_layout("Pick a partner", "Use `lineage dual <partner>`. You must be married."))
            partner = await self.bot.fetch_user(options[0])
        if partner.bot or partner.id == ctx.author.id:
            return await ctx.send(view=error_layout("Not possible", "Pick your married partner."))
        if not await family_utils.marriage(ctx.author.id, partner.id):
            return await ctx.send(view=error_layout("Not married", "Dual cultivation is only for married partners."))
        if await cult.get(partner.id) is None:
            return await ctx.send(view=error_layout("Partner not awakened", "They need to use `cultivate awaken` first."))
        cog = self.bot.get_cog("Family")
        if cog is not None:
            agreed = await cog.ask(ctx, partner, "Dual cultivation", f"{ctx.author.mention} invites you to cultivate together. Both of you gain qi.")
            if not agreed:
                return
        result = await cult.dual(ctx.author.id, partner.id)
        if not result["ok"]:
            reasons = {
                "none": ("Not awakened", "You both need to have chosen a path."),
                "cooldown": ("Too soon", f"You can cultivate together again in **{duration(result.get('wait', 0))}**."),
                "full": ("Qi is full", "Neither of you can hold more qi. Break through first."),
            }
            title, body = reasons.get(result["reason"], ("Cannot do that", "That did not work."))
            return await ctx.send(view=error_layout(title, body))
        gains = result["gains"]
        await ctx.send(view=success_layout(f"{e('ecult')} Dual cultivation", "\n".join(f"<@{uid}> +**{coins.fmt(gain)}** qi" for uid, gain in gains.items())), allowed_mentions=NO_PINGS)

    @lineage.command(name="treasury", aliases=["coffer", "vault"], help="The family coffer. Usage: lineage treasury [deposit|withdraw] [amount] [owner]")
    async def treasury_cmd(self, ctx: commands.Context, action: Optional[str] = None, amount: Optional[int] = None, owner: Optional[discord.User] = None):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        owner_id = owner.id if owner else ctx.author.id
        if action in ("deposit", "withdraw") and amount:
            result = await cult.treasury_move(ctx.author.id, owner_id, amount, action == "deposit")
            if not result["ok"]:
                reasons = {
                    "stranger": ("Not family", "You can only add to the treasury of a relative."),
                    "owner": ("Owner only", "Only the owner can withdraw."),
                    "full": ("Treasury is full", f"It holds at most **{coins.fmt(result.get('cap', 0))}** coins."),
                    "coins": ("Not enough coins", "You do not have that many coins in your pouch."),
                    "empty": ("Not enough in the treasury", "The treasury has less than that."),
                    "amount": ("Invalid amount", "Use a positive number."),
                }
                title, body = reasons.get(result["reason"], ("Cannot do that", "That did not work."))
                return await ctx.send(view=error_layout(title, body))
            return await ctx.send(view=success_layout(f"{e('eshield')} {'Deposited' if action == 'deposit' else 'Withdrawn'}", f"The treasury holds **{coins.fmt(result['treasury']['coins'])}/{coins.fmt(result['cap'])}** coins."))
        vault = await cult.treasury(owner_id)
        cap = await cult.treasury_cap(owner_id)
        await ctx.send(view=info_layout(f"{e('eshield')} Family treasury", (
            f"<@{owner_id}>'s treasury holds **{coins.fmt(vault['coins'])}/{coins.fmt(cap)}** coins. It cannot be raided.\n\n"
            f"-# Family can add coins, only the owner can withdraw. If the owner is away for {settings.INHERIT_DAYS} days, their chosen heir can claim it.")), allowed_mentions=NO_PINGS)

    @lineage.command(name="heir", help="Choose who inherits your treasury. Usage: lineage heir <user>")
    async def heir(self, ctx: commands.Context, user: discord.User):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        result = await cult.set_heir(ctx.author.id, user.id)
        if not result["ok"]:
            reasons = {
                "not_family": ("Not family", "Your heir must be a partner, child, parent or sibling."),
                "heir_none": ("Not awakened", "Your heir must have awakened."),
            }
            title, body = reasons.get(result["reason"], ("Cannot do that", "That did not work."))
            return await ctx.send(view=error_layout(title, body))
        await ctx.send(view=success_layout(f"{e('ecult')} Heir chosen", f"{user.mention} will inherit your treasury if you are gone for {settings.INHERIT_DAYS} days."), allowed_mentions=NO_PINGS)

    @lineage.command(name="inherit", help="Claim a treasury you were named heir of. Usage: lineage inherit <user>")
    async def inherit(self, ctx: commands.Context, user: discord.User):
        e = emoji_manager.get
        if await self.need_character(ctx) is None:
            return
        result = await cult.inherit(ctx.author.id, user.id)
        if not result["ok"]:
            reasons = {
                "not_heir": ("Not your inheritance", "They have not named you their heir."),
                "active": ("Still active", f"They have been active recently. You can claim it after **{duration(result.get('wait', 0))}** of silence."),
                "empty": ("Nothing to claim", "The treasury is empty."),
            }
            title, body = reasons.get(result["reason"], ("Cannot do that", "That did not work."))
            return await ctx.send(view=error_layout(title, body))
        await ctx.send(view=success_layout(f"{e('ecult')} Inheritance", f"You claim **{coins.fmt(result['amount'])}** coins from {user.mention}'s treasury."), allowed_mentions=NO_PINGS)

    @lineage.command(name="dungeon", aliases=["delve"], help="Take your family into a dungeon boss fight.")
    async def dungeon(self, ctx: commands.Context):
        character = await self.need_character(ctx)
        if character is None:
            return
        active = self.cultivation_active()
        if ctx.author.id in active:
            return await ctx.send(view=error_layout("Already fighting", "Finish your current fight first."))
        family = set(await cult.circle(ctx.author.id))
        if not family:
            return await ctx.send(view=error_layout("No family", "You need a partner, children or a parent to enter a dungeon. Use `marry` or `adopt`."))
        active.add(ctx.author.id)
        await ctx.send(view=DungeonView(ctx.author.id, family, self), allowed_mentions=NO_PINGS)


async def setup(bot: commands.Bot):
    await bot.add_cog(Lineage(bot))
