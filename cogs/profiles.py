import discord
from discord.ext import commands

from utils import db, emoji_manager, profiles as store
from utils.components import error_layout, info_layout, success_layout

NO_MENTIONS = discord.AllowedMentions.none()


class ProfileModal(discord.ui.Modal, title="Your profile"):
    def __init__(self, current: dict | None):
        super().__init__(timeout=600)
        current = current or {}
        self.bio = discord.ui.TextInput(label="About you", style=discord.TextStyle.paragraph, required=False, max_length=store.LIMITS["bio"], default=current.get("bio") or None)
        self.interests = discord.ui.TextInput(label="Interests (comma separated)", required=False, max_length=200, default=", ".join(current.get("interests") or []) or None)
        self.looking = discord.ui.TextInput(label="Looking for", required=False, max_length=store.LIMITS["looking_for"], default=current.get("looking_for") or None)
        self.relationship = discord.ui.TextInput(label="Relationship status", required=False, max_length=store.LIMITS["relationship"], default=current.get("relationship") or None)
        self.pronouns = discord.ui.TextInput(label="Pronouns", required=False, max_length=store.LIMITS["pronouns"], default=current.get("pronouns") or None)
        for item in (self.bio, self.interests, self.looking, self.relationship, self.pronouns):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await store.save(
            interaction.guild.id, interaction.user.id, bio=str(self.bio.value), interests=store.parse_interests(str(self.interests.value)),
            looking_for=str(self.looking.value), relationship=str(self.relationship.value), pronouns=str(self.pronouns.value))
        await interaction.response.send_message(f"{emoji_manager.get('check')} Your profile was saved. Use `profile` to see it.", ephemeral=True)


class EditLayout(discord.ui.LayoutView):
    def __init__(self, owner: discord.Member, current: dict | None):
        super().__init__(timeout=300)
        self.owner = owner
        self.current = current
        container = discord.ui.Container()
        container.add_item(discord.ui.TextDisplay("## Edit your profile\nOnly people in this server can see it. You can hide it any time with `profile hide`. Links are removed."))
        row = discord.ui.ActionRow()
        button = discord.ui.Button(label="Edit profile", style=discord.ButtonStyle.primary)
        button.callback = self.open
        row.add_item(button)
        container.add_item(row)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.owner.id:
            await interaction.response.send_message("This is not your profile.", ephemeral=True)
            return False
        return True

    async def open(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ProfileModal(await store.get(interaction.guild.id, interaction.user.id)))


class Profiles(commands.Cog):
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="profile", aliases=["card"], invoke_without_command=True, help="Show a member's profile card.")
    @commands.guild_only()
    async def profile(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        data = await store.get(ctx.guild.id, member.id)
        staff = ctx.author.guild_permissions.manage_messages
        if data is None:
            who = "You have" if member.id == ctx.author.id else f"{member.display_name} has"
            return await ctx.send(view=info_layout("No profile", f"{who} no profile yet. Use `profile edit` to make one."))
        if data["hidden"] and member.id != ctx.author.id and not staff:
            return await ctx.send(view=info_layout("Private profile", f"{member.display_name} keeps their profile private."))
        xp = await db.raw_fetchone("SELECT level, total_messages FROM member_xp WHERE guild_id=? AND user_id=?", (ctx.guild.id, member.id))
        birthday = await db.raw_fetchone("SELECT month, day FROM birthdays WHERE guild_id=? AND user_id=?", (ctx.guild.id, member.id))
        lines = []
        if data["pronouns"]:
            lines.append(f"**Pronouns:** {data['pronouns']}")
        if data["relationship"]:
            lines.append(f"**Status:** {data['relationship']}")
        if data["bio"]:
            lines.append(f"\n{data['bio']}")
        if data["interests"]:
            lines.append("\n**Interests:** " + " · ".join(data["interests"]))
        if data["looking_for"]:
            lines.append(f"**Looking for:** {data['looking_for']}")
        facts = []
        if xp:
            facts.append(f"Level {xp['level']}")
        if birthday:
            facts.append(f"Birthday {birthday['day']}/{birthday['month']}")
        if member.joined_at:
            facts.append(f"Joined <t:{int(member.joined_at.timestamp())}:D>")
        if facts:
            lines.append("\n-# " + " · ".join(facts))
        if data["hidden"]:
            lines.append("-# Hidden from members")
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=member.accent_color.value if member.accent_color else 0x5865F2)
        container.add_item(discord.ui.Section(f"## {member.display_name}", "\n".join(lines) or "Empty profile.", accessory=discord.ui.Thumbnail(media=member.display_avatar.url)))
        view.add_item(container)
        await ctx.send(view=view, allowed_mentions=NO_MENTIONS)

    @profile.command(name="edit", aliases=["set", "create"], help="Create or edit your profile.")
    async def profile_edit(self, ctx: commands.Context):
        await ctx.send(view=EditLayout(ctx.author, await store.get(ctx.guild.id, ctx.author.id)))

    @profile.command(name="hide", help="Hide your profile from other members.")
    async def profile_hide(self, ctx: commands.Context):
        if not await store.set_hidden(ctx.guild.id, ctx.author.id, True):
            return await ctx.send(view=error_layout("No profile", "Create one first with `profile edit`."))
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Profile", "Your profile is hidden. You will also be skipped by matchmaking."))

    @profile.command(name="show", help="Show your profile to other members again.")
    async def profile_show(self, ctx: commands.Context):
        if not await store.set_hidden(ctx.guild.id, ctx.author.id, False):
            return await ctx.send(view=error_layout("No profile", "Create one first with `profile edit`."))
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Profile", "Your profile is visible again."))

    @profile.command(name="clear", aliases=["delete"], help="Delete your profile.")
    async def profile_clear(self, ctx: commands.Context):
        await store.clear(ctx.guild.id, ctx.author.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Profile", "Your profile was deleted."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Profiles(bot))
