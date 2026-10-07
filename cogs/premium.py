import secrets
import time
from typing import Optional

import discord
from discord.ext import commands

from utils import db, embeds, emoji_manager, prefix as prefix_utils
from utils.checks import has_guild_permission, is_privileged
import config

def _generate_key() -> str:
    part = lambda: secrets.token_hex(4).upper()
    return f"SOWARD-{part()}-{part()}-{part()}"

def _resolve_duration_days(raw: str) -> Optional[int]:
    raw = raw.lower().strip()
    if raw in config.PREMIUM_DURATION_PRESETS:
        return config.PREMIUM_DURATION_PRESETS[raw]
    if raw.endswith("d") and raw[:-1].isdigit():
        return int(raw[:-1])
    if raw.endswith("w") and raw[:-1].isdigit():
        return int(raw[:-1]) * 7
    if raw.endswith("mo") and raw[:-2].isdigit():
        return int(raw[:-2]) * 30
    if raw.endswith("m") and raw[:-1].isdigit():
        return int(raw[:-1]) * 30
    if raw.endswith("y") and raw[:-1].isdigit():
        return int(raw[:-1]) * 365
    if raw.isdigit():
        return int(raw)
    return None

class PremiumClaimView(discord.ui.View):
    def __init__(self, author_id: int, key: str, duration_days: int, duration_label: str):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.key = key
        self.duration_days = duration_days
        self.duration_label = duration_label
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        await interaction.response.defer()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        await interaction.response.edit_message(embed=embeds.neutral("Cancelled", "Premium claim cancelled."), view=None)

class Premium(commands.Cog):
    category = "Premium"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="premium", invoke_without_command=True, help='View premium status or manage premium keys.')
    @commands.guild_only()
    async def premium_group(self, ctx: commands.Context):
        e = emoji_manager.get
        row = await db.raw_fetchone(
            "SELECT premium, premium_expires_at, server_np_enabled FROM guilds WHERE guild_id=?",
            (ctx.guild.id,),
        )

        is_premium = bool(row["premium"]) if row else False
        expires = row["premium_expires_at"] if row else None
        np_enabled = bool(row["server_np_enabled"]) if row else config.SERVER_NO_PREFIX_ENABLED_DEFAULT

        if not is_premium:
            preset_list = ", ".join(f"`{k}`" for k in config.PREMIUM_DURATION_PRESETS)
            embed = embeds.neutral(
                f"{e('premium_cat')} Soward Premium",
                "This server does not have premium.\n\n"
                "Premium unlocks **no-prefix mode**, letting the server use commands without typing a prefix.\n\n"
                f"Use `premium claim <key>` to activate premium.\n\nAvailable durations: {preset_list}",
            )
        else:
            expires_text = f"<t:{int(expires)}:R>" if expires else "Never"
            embed = embeds.success(
                f"{e('premium_cat')} Premium Active",
                f"**Expires:** {expires_text}\n"
                f"**No-Prefix Mode:** {'Enabled' if np_enabled else 'Disabled (use `premium np enable`)'}",
            )
        await ctx.send(embed=embed)

    @premium_group.command(name="generate", aliases=["gen"], help='Generate a redeemable premium key (owner/dev only).')
    @is_privileged()
    async def premium_generate(self, ctx: commands.Context, duration: str):
        e = emoji_manager.get
        days = _resolve_duration_days(duration)
        if days is None:
            preset_list = ", ".join(f"`{k}`" for k in config.PREMIUM_DURATION_PRESETS)
            return await ctx.send(embed=embeds.error(
                "Invalid Duration",
                f"Use a preset ({preset_list}) or a custom value like `45d`, `5w`, `2mo`, `1y`.",
            ))

        key = _generate_key()
        await db.raw_execute(
            "INSERT INTO premium_keys (key_id, duration_days, duration_label, used, created_by, created_at) VALUES (?, ?, ?, 0, ?, ?)",
            (key, days, duration, ctx.author.id, time.time()),
        )

        embed = embeds.success(
            f"{e('premium_cat')} Premium Key Generated",
            f"**Key:** `{key}`\n**Duration:** {duration} ({days} days)",
        )
        try:
            await ctx.author.send(embed=embed)
            await ctx.send(embed=embeds.success(f"{e('check')} Key Generated", "The premium key has been sent to your DMs."))
        except discord.HTTPException:
            await ctx.send(embed=embed)

    @premium_group.command(name="claim", help='Claim a premium key to activate premium for this server.')
    @commands.guild_only()
    async def premium_claim(self, ctx: commands.Context, key: str):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT * FROM premium_keys WHERE key_id=?", (key.upper(),))

        if not row:
            return await ctx.send(embed=embeds.error(f"{e('cross')} Invalid Key", "That key does not exist."))
        if row["used"]:
            return await ctx.send(embed=embeds.error(f"{e('cross')} Key Already Used", "That key has already been redeemed."))

        duration_days = row["duration_days"]
        duration_label = row["duration_label"]

        embed = embeds.neutral(
            f"{e('premium_cat')} Confirm Premium Claim",
            f"You are about to activate **Soward Premium** for this server.\n\n"
            f"**Duration:** {duration_label} ({duration_days} days)\n\n"
            "This will unlock no-prefix mode for the server. Are you sure?",
        )

        view = PremiumClaimView(ctx.author.id, key.upper(), duration_days, duration_label)
        msg = await ctx.send(embed=embed, view=view)
        await view.wait()

        if not view.confirmed:
            return

        existing = await db.raw_fetchone(
            "SELECT premium_expires_at FROM guilds WHERE guild_id=?", (ctx.guild.id,)
        )
        base_time = time.time()
        if existing and existing["premium_expires_at"] and existing["premium_expires_at"] > base_time:
            base_time = existing["premium_expires_at"]

        expires_at = base_time + duration_days * 86400

        await db.raw_execute(
            "UPDATE premium_keys SET used=1, used_by=?, used_at=? WHERE key_id=?",
            (ctx.author.id, time.time(), key.upper()),
        )
        await db.raw_execute(
            "INSERT INTO guilds (guild_id, premium, premium_expires_at) VALUES (?, 1, ?)"
            " ON CONFLICT(guild_id) DO UPDATE SET premium=1, premium_expires_at=excluded.premium_expires_at",
            (ctx.guild.id, expires_at),
        )
        prefix_utils.invalidate_premium_cache(ctx.guild.id)

        await msg.edit(
            embed=embeds.success(
                f"{e('premium_cat')} Premium Activated!",
                f"**Soward Premium** is now active for **{ctx.guild.name}**!\n"
                f"**Expires:** <t:{int(expires_at)}:R>\n\n"
                "No-prefix mode is enabled by default — use `premium np disable` to turn it off.",
            ),
            view=None,
        )

    @premium_group.command(name="revoke", help='Revoke premium from a server (owner/dev only).')
    @is_privileged()
    @commands.guild_only()
    async def premium_revoke(self, ctx: commands.Context, guild_id: int = None):
        e = emoji_manager.get
        target_guild = guild_id or ctx.guild.id
        await db.raw_execute(
            "UPDATE guilds SET premium=0, premium_expires_at=NULL WHERE guild_id=?",
            (target_guild,),
        )
        prefix_utils.invalidate_premium_cache(target_guild)
        await ctx.send(embed=embeds.success(f"{e('check')} Premium Revoked", f"Premium revoked from guild `{target_guild}`."))

    @premium_group.command(name="keys", help='List all generated premium keys (owner/dev only).')
    @is_privileged()
    async def premium_keys_list(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await db.raw_fetch(
            "SELECT key_id, duration_label, used FROM premium_keys ORDER BY created_at DESC LIMIT 20"
        )
        if not rows:
            return await ctx.send(embed=embeds.neutral(f"{e('premium_cat')} No Keys", "No premium keys have been generated yet."))

        desc = "\n".join(
            f"`{r['key_id']}` — {r['duration_label']} — "
            + (f"{e('cross')} Used" if r["used"] else f"{e('check')} Available")
            for r in rows
        )
        try:
            await ctx.author.send(embed=embeds.neutral(f"{e('premium_cat')} Premium Keys", desc))
            await ctx.send(embed=embeds.success(f"{e('check')} Keys Sent", "Premium keys list sent to your DMs."))
        except discord.HTTPException:
            await ctx.send(embed=embeds.neutral(f"{e('premium_cat')} Premium Keys", desc))

    @premium_group.group(name="np", invoke_without_command=True, help="View or manage server no-prefix mode settings.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def premium_np_group(self, ctx: commands.Context):
        e = emoji_manager.get
        row = await db.raw_fetchone(
            "SELECT premium, server_np_enabled FROM guilds WHERE guild_id=?", (ctx.guild.id,)
        )
        is_premium = bool(row["premium"]) if row else False
        np_enabled = bool(row["server_np_enabled"]) if row else config.SERVER_NO_PREFIX_ENABLED_DEFAULT

        if not is_premium:
            return await ctx.send(embed=embeds.error(f"{e('cross')} No Premium", "This server needs premium to use no-prefix mode."))

        embed = embeds.neutral(
            f"{e('premium_cat')} Server No-Prefix Mode",
            f"**Status:** {'Enabled' if np_enabled else 'Disabled'}\n\n"
            "Use `premium np enable` or `premium np disable` to change this.",
        )
        await ctx.send(embed=embed)

    @premium_np_group.command(name="enable", help='Enable AntiNuke protection.')
    @has_guild_permission("administrator")
    async def premium_np_enable(self, ctx: commands.Context):
        e = emoji_manager.get
        row = await db.raw_fetchone("SELECT premium FROM guilds WHERE guild_id=?", (ctx.guild.id,))
        if not row or not row["premium"]:
            return await ctx.send(embed=embeds.error(f"{e('cross')} No Premium", "This server needs premium to enable no-prefix mode."))

        await prefix_utils.set_server_np_enabled(ctx.guild.id, True)
        await ctx.send(embed=embeds.success(f"{e('check')} No-Prefix Enabled", "Server-wide no-prefix mode is now enabled."))

    @premium_np_group.command(name="disable", help='Disable AntiNuke protection.')
    @has_guild_permission("administrator")
    async def premium_np_disable(self, ctx: commands.Context):
        e = emoji_manager.get
        await prefix_utils.set_server_np_enabled(ctx.guild.id, False)
        await ctx.send(embed=embeds.success(f"{e('check')} No-Prefix Disabled", "Server-wide no-prefix mode is now disabled."))

class NoPrefix(commands.Cog, name="GlobalNoPrefix"):
    category = "Premium"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="globalnp", aliases=["gnp"], invoke_without_command=True, help='Manage global no-prefix access for users.')
    @is_privileged()
    async def np_group(self, ctx: commands.Context):
        e = emoji_manager.get
        ids = await prefix_utils.list_global_no_prefix()
        desc = "\n".join(f"<@{uid}> (`{uid}`)" for uid in ids) or "No users have global no-prefix access."
        embed = embeds.neutral(f"{e('premium_cat')} Global No-Prefix Users", desc)
        await ctx.send(embed=embed)

    @np_group.command(name="add", help='Add a role to assign to all new members on join.')
    @is_privileged()
    async def np_add(self, ctx: commands.Context, user: discord.User):
        e = emoji_manager.get
        await prefix_utils.add_global_no_prefix(user.id, ctx.author.id)
        await ctx.send(embed=embeds.success(
            f"{e('check')} Global No-Prefix Granted",
            f"{user.mention} can now use Soward commands without a prefix in any server the bot is in.",
        ))

    @np_group.command(name="remove", help='Remove a track from the queue by position.')
    @is_privileged()
    async def np_remove(self, ctx: commands.Context, user: discord.User):
        e = emoji_manager.get
        removed = await prefix_utils.remove_global_no_prefix(user.id)
        if removed:
            await ctx.send(embed=embeds.success(f"{e('check')} Global No-Prefix Revoked", f"{user.mention} no longer has global no-prefix access."))
        else:
            await ctx.send(embed=embeds.error(f"{e('cross')} Not Found", f"{user.mention} did not have global no-prefix access."))

    @np_group.command(name="list", help='List all users with global no-prefix access.')
    @is_privileged()
    async def np_list(self, ctx: commands.Context):
        await self.np_group(ctx)

async def setup(bot: commands.Bot):
    await bot.add_cog(Premium(bot))
    await bot.add_cog(NoPrefix(bot))
