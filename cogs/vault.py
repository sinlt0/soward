import io
import time

import discord
from discord.ext import commands, tasks

import config
from utils import emoji_manager, premium_limits, vault as store
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
from utils.events_bus import LOG_EVENT, bus

NO_MENTIONS = discord.AllowedMentions.none()
USAGE = "Filters: `user:@member`, `by:@staff`, `action:ban`, `days:30`. Example: `vault search user:@member action:warn days:30`."


class PagerRow(discord.ui.ActionRow):
    def __init__(self, pager: "Pager"):
        super().__init__()
        self.pager = pager

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.pager.offset = max(0, self.pager.offset - config.VAULT_PAGE_SIZE)
        await self.pager.refresh(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.pager.offset += config.VAULT_PAGE_SIZE
        await self.pager.refresh(interaction)


class Pager(discord.ui.LayoutView):
    def __init__(self, guild_id: int, author_id: int, filters: dict, total: int, title: str):
        super().__init__(timeout=180)
        self.guild_id = guild_id
        self.author_id = author_id
        self.filters = filters
        self.total = total
        self.title = title
        self.offset = 0

    async def build(self) -> "Pager":
        rows = await store.page(self.guild_id, self.filters, self.offset, config.VAULT_PAGE_SIZE)
        self.clear_items()
        container = discord.ui.Container(accent_color=0x5865F2)
        last = min(self.total, self.offset + config.VAULT_PAGE_SIZE)
        body = "\n".join(store.line(r) for r in rows) or "Nothing found."
        container.add_item(discord.ui.TextDisplay(f"## {self.title}\n{body}\n\n-# {self.offset + 1 if rows else 0}-{last} of {self.total}"))
        if self.total > config.VAULT_PAGE_SIZE:
            row = PagerRow(self)
            row.previous.disabled = self.offset <= 0
            row.next.disabled = self.offset + config.VAULT_PAGE_SIZE >= self.total
            container.add_item(row)
        self.add_item(container)
        return self

    async def refresh(self, interaction: discord.Interaction):
        await self.build()
        await interaction.response.edit_message(view=self, allowed_mentions=NO_MENTIONS)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This is not your search.", ephemeral=True)
            return False
        return True


class Vault(commands.Cog):
    category = "Moderation"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bus.subscribe(LOG_EVENT, self._on_log)
        self.cleanup.start()

    def cog_unload(self):
        bus.unsubscribe(LOG_EVENT, self._on_log)
        self.cleanup.cancel()

    async def _on_log(self, *, guild_id: int, action: str, **kwargs):
        await store.record(guild_id, action, **kwargs)

    @tasks.loop(hours=1)
    async def cleanup(self):
        await store.prune()

    @cleanup.before_loop
    async def _before_cleanup(self):
        await self.bot.wait_until_ready()

    async def _parse(self, ctx: commands.Context, query: str):
        filters, problems = store.parse_query(query)
        if problems:
            await ctx.send(view=error_layout("Unknown filter", f"Could not read: {', '.join(f'`{p[:40]}`' for p in problems[:5])}.\n{USAGE}"))
            return None
        return filters

    @commands.group(name="vault", aliases=["auditvault"], invoke_without_command=True, help="Searchable history of moderation and server events.")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def vault(self, ctx: commands.Context):
        e = emoji_manager.get
        days = await store.retention_days(ctx.guild.id)
        paid = await premium_limits.is_premium(ctx.guild.id)
        totals = await store.totals(ctx.guild.id)
        since = f"<t:{int(totals['first'])}:R>" if totals["first"] else "nothing recorded yet"
        lines = [
            f"Every moderation action, security change and logged server event is saved here, whether or not you set up a log channel.",
            f"\n**History kept:** {days} days{'' if paid else f' (Premium keeps {config.VAULT_RETENTION_DAYS[1]})'}",
            f"**Entries stored:** {totals['count']} · oldest {since}",
            f"\n`vault search [filters]` · `vault stats [filters]` · `vault export [filters]` (Premium)\n{USAGE}",
        ]
        await ctx.send(view=info_layout(f"{e('case')} Audit Vault", "\n".join(lines)))

    @vault.command(name="search", aliases=["find", "list"], help="Search the history. Usage: vault search [user:@x] [by:@x] [action:ban] [days:30]")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def search(self, ctx: commands.Context, *, query: str = ""):
        filters = await self._parse(ctx, query)
        if filters is None:
            return
        total = await store.count(ctx.guild.id, filters)
        if not total:
            return await ctx.send(view=info_layout("Audit Vault", "No entries match in the last " + str(await store.retention_days(ctx.guild.id)) + " days."))
        pager = await Pager(ctx.guild.id, ctx.author.id, filters, total, "Audit Vault").build()
        await ctx.send(view=pager, allowed_mentions=NO_MENTIONS)

    @vault.command(name="stats", aliases=["summary"], help="Count events by type. Usage: vault stats [filters]")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    async def stats(self, ctx: commands.Context, *, query: str = ""):
        filters = await self._parse(ctx, query)
        if filters is None:
            return
        total = await store.count(ctx.guild.id, filters)
        rows = await store.summary(ctx.guild.id, filters)
        if not rows:
            return await ctx.send(view=info_layout("Audit Vault", "No entries match."))
        body = "\n".join(f"`{name}` · **{n}**" for name, n in rows)
        await ctx.send(view=info_layout("Audit Vault stats", f"{body}\n\n-# {total} entries in range"))

    @vault.command(name="export", aliases=["csv", "download"], help="Download matching history as CSV (Premium). Usage: vault export [filters]")
    @commands.guild_only()
    @has_guild_permission("manage_guild")
    @commands.cooldown(1, 30, commands.BucketType.guild)
    async def export(self, ctx: commands.Context, *, query: str = ""):
        if not await premium_limits.gate(ctx, "Exporting the audit vault"):
            return
        filters = await self._parse(ctx, query)
        if filters is None:
            return
        async with ctx.typing():
            data, count = await store.export_csv(ctx.guild.id, filters)
        if not count:
            return await ctx.send(view=info_layout("Audit Vault", "No entries match."))
        name = f"vault-{ctx.guild.id}-{int(time.time())}.csv"
        await ctx.send(view=success_layout("Vault export", f"**{count}** entries" + (f" (limited to the newest {config.VAULT_EXPORT_MAX})" if count >= config.VAULT_EXPORT_MAX else "") + "."), file=discord.File(io.BytesIO(data), filename=name))


async def setup(bot: commands.Bot):
    await bot.add_cog(Vault(bot))
