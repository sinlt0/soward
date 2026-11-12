import secrets
import time
import typing
from typing import Optional

import discord
from discord.ext import commands, tasks

from utils import coins as coin_store, crypto_pay as crypto_store, db, embeds, emoji_manager, premium_limits, premium_trials, prefix as prefix_utils
from utils.checks import has_guild_permission, is_privileged
import config

def _generate_key() -> str:
    part = lambda: secrets.token_hex(4).upper()
    return f"ZYRO-{part()}-{part()}-{part()}"

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

class PremiumCoinsView(discord.ui.View):
    def __init__(self, author_id: int):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.confirmed = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This is not your purchase.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Buy", style=discord.ButtonStyle.success)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(view=None)
        self.stop()


class Premium(commands.Cog):
    category = "Premium"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.trial_reminders.start()

    async def cog_unload(self):
        self.trial_reminders.cancel()

    @tasks.loop(minutes=10)
    async def trial_reminders(self):
        e = emoji_manager.get
        for trial in await premium_trials.due_reminders():
            await premium_trials.mark_reminded(trial["guild_id"])
            if not await premium_trials.still_trial_only(trial["guild_id"], trial["ends_at"]):
                continue
            guild = self.bot.get_guild(trial["guild_id"])
            if guild is None:
                continue
            embed = embeds.neutral(
                f"{e('warning')} Premium trial ending soon",
                f"The premium trial for **{guild.name}** ends <t:{int(trial['ends_at'])}:R>.\n"
                "Use `premium buy` to keep premium, or `premium claim <key>` if you have a key.",
            )
            sent = False
            owner = guild.get_member(trial["claimed_by"])
            if owner is not None:
                try:
                    await owner.send(embed=embed)
                    sent = True
                except discord.HTTPException:
                    pass
            if not sent:
                channel = guild.system_channel
                if channel is not None and channel.permissions_for(guild.me).send_messages:
                    try:
                        await channel.send(embed=embed)
                    except discord.HTTPException:
                        pass

    @trial_reminders.before_loop
    async def before_trial_reminders(self):
        await self.bot.wait_until_ready()

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
                f"{e('premium_cat')} Zyro Premium",
                "This server does not have premium.\n\n"
                "Premium unlocks **no-prefix mode**, letting the server use commands without typing a prefix.\n\n"
                f"Use `premium buy` to pay with Bitcoin or Litecoin, or `premium claim <key>` to activate premium with a key.\n\nAvailable durations: {preset_list}",
            )
        else:
            expires_text = f"<t:{int(expires)}:R>" if expires else "Never"
            if not await prefix_utils.np_master_enabled(ctx.guild.id):
                np_text = "Off (use `premium np enable`)"
            else:
                np_text = "On for everyone" if np_enabled else "On for chosen roles and members (`premium np list`)"
            embed = embeds.success(
                f"{e('premium_cat')} Premium Active",
                f"**Expires:** {expires_text}\n"
                f"**No-Prefix Mode:** {np_text}",
            )
        await ctx.send(embed=embed)

    @premium_group.command(name="limits", aliases=["perks", "compare"], help='See what premium raises, system by system.')
    @commands.guild_only()
    async def premium_limits_cmd(self, ctx: commands.Context):
        e = emoji_manager.get
        active = await premium_limits.is_premium(ctx.guild.id)
        tickets = config.TICKET_LIMITS
        lines = [
            f"Ticket panels: **{tickets['free']['panels']}** → **{tickets['premium']['panels']}**",
            f"Open tickets per server: **{tickets['free']['active']}** → **{tickets['premium']['active']}**",
        ]
        for free, premium, label in config.PREMIUM_LIMITS.values():
            lines.append(f"{label}: **{free}** → **{premium}**")
        lines.append(f"Audit vault history (`vault`): **{config.VAULT_RETENTION_DAYS[0]} days** → **{config.VAULT_RETENTION_DAYS[1]} days** and CSV export")
        lines.append("Premium only: no-prefix mode, `nbot`, `schedule`, `deepbackup`, ticket `canned` replies, `ratings` and `archive`")
        state = "This server has **Premium**, so the higher numbers apply." if active else "This server is on the free plan. Use `premium buy` to get the higher numbers."
        await ctx.send(embed=embeds.neutral(f"{e('premium_cat')} What Premium raises", state + "\n\n" + "\n".join(lines)))

    @premium_group.command(name="buy", aliases=["purchase", "pay"], help='Buy premium for this server with Bitcoin or Litecoin. Usage: premium buy [gift]')
    @commands.guild_only()
    async def premium_buy(self, ctx: commands.Context, mode: str = ""):
        cog = self.bot.get_cog("CryptoPay")
        if cog is None:
            return await ctx.send(embed=embeds.error("Unavailable", "Crypto payments are not available right now."))
        if mode.lower() in ("coins", "diamonds"):
            return await cog.start_coins(ctx, None)
        await cog.start_purchase(ctx, mode.lower() == "gift")

    async def buy_with(self, ctx: commands.Context, plan: str, currency: str):
        e = emoji_manager.get
        diamonds = currency == "diamonds"
        unit = "diamonds" if diamonds else "coins"
        icon = e("ediamond") if diamonds else e("ecoin")
        plans = config.PREMIUM_DIAMOND_PLANS if diamonds else {config.PREMIUM_COIN_PLAN: config.PREMIUM_DIAMOND_PLANS[config.PREMIUM_COIN_PLAN]}
        prices = {key: item["diamonds"] * (1 if diamonds else config.DIAMOND_TO_COINS) for key, item in plans.items()}
        wallet = await coin_store.diamonds(ctx.author.id) if diamonds else await coin_store.balance(ctx.author.id)
        key = plan.lower()
        if key not in prices:
            lines = [f"{icon} Your wallet: **{coin_store.fmt(wallet)}** {unit}", ""]
            for name, item in plans.items():
                lines.append(f"`{name}` · {item['label']} · **{coin_store.fmt(prices[name])}** {unit}")
            if not diamonds:
                ready = await coin_store.premium_ready_at(ctx.author.id)
                lines.append(f"\nWith coins you can only buy **{plans[config.PREMIUM_COIN_PLAN]['label']}**, once every **{config.PREMIUM_COIN_COOLDOWN_DAYS} days**. " + (f"You can buy again <t:{int(ready)}:R>." if ready > time.time() else "You can buy one now."))
            if diamonds:
                lines.append("\nLifetime premium is only sold with crypto or a key. Diamonds have no purchase limit.")
            other = "coins" if diamonds else "diamonds"
            lines.append(f"\nUse `premium {unit} <plan>` to buy. You can also pay with {other} using `premium {other} <plan>`." + ("" if diamonds else " Earn coins with `reward`, `work` and `vote`, or convert diamonds with `coins convert`."))
            return await ctx.send(embed=embeds.neutral(f"{e('premium_cat')} Premium with {unit}", "\n".join(lines)))
        item = plans[key]
        price = prices[key]
        row = await db.raw_fetchone("SELECT premium, premium_expires_at FROM guilds WHERE guild_id=?", (ctx.guild.id,))
        if row and row["premium"] and row["premium_expires_at"] is None:
            return await ctx.send(embed=embeds.error(f"{e('cross')} Already Lifetime", "This server already has premium with no end date."))
        if not diamonds:
            ready = await coin_store.premium_ready_at(ctx.author.id)
            if ready > time.time():
                return await ctx.send(embed=embeds.error(f"{e('cross')} Too Soon", f"Premium bought with coins is limited to once every **{config.PREMIUM_COIN_COOLDOWN_DAYS} days**. You can buy again <t:{int(ready)}:R>."))
        if wallet < price:
            return await ctx.send(embed=embeds.error(f"{e('cross')} Not Enough {unit.title()}", f"**{item['label']}** costs **{coin_store.fmt(price)}** {unit} and you have **{coin_store.fmt(wallet)}**."))
        view = PremiumCoinsView(ctx.author.id)
        msg = await ctx.send(embed=embeds.neutral(f"{e('premium_cat')} Confirm Purchase", f"Spend **{coin_store.fmt(price)}** {unit} on **{item['label']}** of premium for **{ctx.guild.name}**?"), view=view)
        await view.wait()
        if not view.confirmed:
            return
        previous = None
        if not diamonds:
            previous = await coin_store.claim_premium_slot(ctx.author.id)
            if previous is None:
                return await msg.edit(embed=embeds.error(f"{e('cross')} Too Soon", f"Premium bought with coins is limited to once every **{config.PREMIUM_COIN_COOLDOWN_DAYS} days**."), view=None)
        paid = await coin_store.spend_diamonds(ctx.author.id, price) if diamonds else await coin_store.spend(ctx.author.id, price)
        if not paid:
            if previous is not None:
                await coin_store.release_premium_slot(ctx.author.id, previous)
            return await msg.edit(embed=embeds.error(f"{e('cross')} Not Enough {unit.title()}", "Your balance changed. Try again."), view=None)
        expires = await crypto_store.grant_server(ctx.guild.id, item["days"])
        when = f"until <t:{int(expires)}:F>" if expires else "with no end date"
        await msg.edit(embed=embeds.success(f"{e('premium_cat')} Premium Activated!", f"**{item['label']}** of premium is now active {when}."), view=None)

    @premium_group.command(name="coins", aliases=["coinbuy"], help='Buy 1 month of premium for this server with coins, once every 90 days. Usage: premium coins [plan]')
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def premium_coins(self, ctx: commands.Context, plan: str = ""):
        await self.buy_with(ctx, plan, "coins")

    @premium_group.command(name="diamonds", aliases=["gems", "diamondbuy"], help='Buy premium for this server with diamonds (1m, 3m or 1y). Usage: premium diamonds [plan]')
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def premium_diamonds(self, ctx: commands.Context, plan: str = ""):
        await self.buy_with(ctx, plan, "diamonds")

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
            f"You are about to activate **Zyro Premium** for this server.\n\n"
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
                f"**Zyro Premium** is now active for **{ctx.guild.name}**!\n"
                f"**Expires:** <t:{int(expires_at)}:R>\n\n"
                "No-prefix mode is enabled for everyone by default. Use `premium np server disable` and `premium np add <role or member>` to limit it, or `premium np disable` to turn it off.",
            ),
            view=None,
        )

    @premium_group.group(name="trial", invoke_without_command=True, help='Check or claim the free 3-day premium trial for this server.')
    @commands.guild_only()
    async def premium_trial(self, ctx: commands.Context):
        e = emoji_manager.get
        trial = await premium_trials.get(ctx.guild.id)
        if trial is None:
            return await ctx.send(embed=embeds.neutral(
                f"{e('gift')} Premium Trial",
                f"Every server gets one free **{premium_trials.TRIAL_DAYS}-day** premium trial. Use `premium trial claim` to start it. You get a reminder 24 hours before it ends.",
            ))
        if trial["ends_at"] > time.time():
            return await ctx.send(embed=embeds.success(f"{e('premium_cat')} Trial Active", f"This server's trial ends <t:{int(trial['ends_at'])}:R>."))
        await ctx.send(embed=embeds.neutral(f"{e('gift')} Trial Used", "This server has already used its free trial. Use `premium buy` to get premium."))

    @premium_trial.command(name="claim", help='Start the free 3-day premium trial for this server.')
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def premium_trial_claim(self, ctx: commands.Context):
        e = emoji_manager.get
        if await premium_trials.get(ctx.guild.id):
            return await ctx.send(embed=embeds.error(f"{e('cross')} Trial Already Used", "This server has already claimed its free trial."))
        row = await db.raw_fetchone("SELECT premium, premium_expires_at FROM guilds WHERE guild_id=?", (ctx.guild.id,))
        if row and row["premium"] and (row["premium_expires_at"] is None or row["premium_expires_at"] > time.time()):
            return await ctx.send(embed=embeds.error(f"{e('cross')} Already Premium", "This server already has premium, so there is no need for a trial."))
        ends_at = await premium_trials.start(ctx.guild.id, ctx.author.id)
        prefix_utils.invalidate_premium_cache(ctx.guild.id)
        await ctx.send(embed=embeds.success(
            f"{e('premium_cat')} Trial Started!",
            f"**Zyro Premium** is now active for **{ctx.guild.name}** for {premium_trials.TRIAL_DAYS} days.\n"
            f"**Ends:** <t:{int(ends_at)}:R>\n\n"
            "I will remind you 24 hours before it ends. No-prefix mode is on for everyone by default; use `premium np` to change it.",
        ))

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

    async def _np_premium(self, ctx: commands.Context) -> bool:
        e = emoji_manager.get
        if await premium_limits.is_premium(ctx.guild.id):
            return True
        await ctx.send(embed=embeds.error(f"{e('cross')} No Premium", "This server needs premium to use no-prefix mode."))
        return False

    @premium_group.group(name="np", invoke_without_command=True, help="View or manage no-prefix mode: everyone, or only chosen roles and members.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def premium_np_group(self, ctx: commands.Context):
        e = emoji_manager.get
        if not await self._np_premium(ctx):
            return
        master = await prefix_utils.np_master_enabled(ctx.guild.id)
        server_wide = await prefix_utils._is_server_np_enabled(ctx.guild.id)
        targets = await prefix_utils.list_np_targets(ctx.guild.id)
        roles = sum(1 for t in targets if t["target_type"] == "role")
        users = len(targets) - roles
        who = "Everyone in the server" if server_wide else (f"Only {roles} role(s) and {users} member(s) you added" if targets else "Nobody yet. Add roles or members with `premium np add`.")
        await ctx.send(embed=embeds.neutral(
            f"{e('premium_cat')} No-Prefix Mode",
            f"**Status:** {'On' if master else 'Off'}\n**Server-wide:** {'On' if server_wide else 'Off'}\n**Who can skip the prefix:** {who if master else 'Nobody, no-prefix mode is off'}\n\n"
            "`premium np enable` · `premium np disable` turn no-prefix mode on or off completely\n"
            "`premium np server enable` · `premium np server disable` let everyone use it, or only chosen roles and members\n"
            "`premium np add <role or member>` · `premium np remove <role or member>` · `premium np list`",
        ))

    @premium_np_group.command(name="enable", help="Turn no-prefix mode back on for this server.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def premium_np_enable(self, ctx: commands.Context):
        e = emoji_manager.get
        if not await self._np_premium(ctx):
            return
        await prefix_utils.set_np_master(ctx.guild.id, True)
        await ctx.send(embed=embeds.success(f"{e('check')} No-Prefix Enabled", "No-prefix mode is on again. Who can use it follows your server-wide and role/member settings."))

    @premium_np_group.command(name="disable", help="Turn no-prefix mode off completely for this server.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def premium_np_disable(self, ctx: commands.Context):
        e = emoji_manager.get
        await prefix_utils.set_np_master(ctx.guild.id, False)
        await ctx.send(embed=embeds.success(f"{e('check')} No-Prefix Disabled", "No-prefix mode is off for everyone. Your roles and members stay saved. Use `premium np enable` to turn it back on."))

    @premium_np_group.group(name="server", aliases=["all", "everyone"], invoke_without_command=True, help="Let everyone use no-prefix mode, or only chosen roles and members.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def premium_np_server(self, ctx: commands.Context):
        e = emoji_manager.get
        state = await prefix_utils._is_server_np_enabled(ctx.guild.id)
        await ctx.send(embed=embeds.neutral(f"{e('premium_cat')} Server-wide No-Prefix", f"Server-wide is **{'on' if state else 'off'}**.\nUse `premium np server enable` or `premium np server disable`."))

    @premium_np_server.command(name="enable", help="Everyone in the server can skip the prefix (premium).")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def premium_np_server_enable(self, ctx: commands.Context):
        e = emoji_manager.get
        if not await self._np_premium(ctx):
            return
        await prefix_utils.set_server_np_enabled(ctx.guild.id, True)
        note = "" if await prefix_utils.np_master_enabled(ctx.guild.id) else "\nNo-prefix mode itself is off, so run `premium np enable` to use it."
        await ctx.send(embed=embeds.success(f"{e('check')} Server-wide No-Prefix Enabled", "Everyone in this server can use commands without a prefix." + note))

    @premium_np_server.command(name="disable", help="Only chosen roles and members can skip the prefix.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def premium_np_server_disable(self, ctx: commands.Context):
        e = emoji_manager.get
        await prefix_utils.set_server_np_enabled(ctx.guild.id, False)
        await ctx.send(embed=embeds.success(f"{e('check')} Server-wide No-Prefix Disabled", "Only the roles and members you add with `premium np add` can skip the prefix."))

    @premium_np_group.command(name="add", aliases=["give", "grant"], help="Let a role or member skip the prefix. Usage: premium np add <role or member>")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def premium_np_add(self, ctx: commands.Context, target: typing.Union[discord.Role, discord.Member, discord.User]):
        e = emoji_manager.get
        if not await self._np_premium(ctx):
            return
        if isinstance(target, discord.Role):
            if target.is_default():
                return await ctx.send(embed=embeds.error(f"{e('cross')} Use server-wide", "Use `premium np server enable` to give no-prefix mode to everyone."))
            kind = "role"
        else:
            if target.bot:
                return await ctx.send(embed=embeds.error(f"{e('cross')} Invalid", "Bots cannot be added."))
            kind = "user"
        if len(await prefix_utils.list_np_targets(ctx.guild.id)) >= config.NP_TARGETS_MAX:
            return await ctx.send(embed=embeds.error(f"{e('cross')} Limit reached", f"You can add up to {config.NP_TARGETS_MAX} roles and members."))
        if not await prefix_utils.add_np_target(ctx.guild.id, target.id, kind, ctx.author.id):
            return await ctx.send(embed=embeds.error(f"{e('cross')} Already added", f"{target.mention} already has no-prefix mode."), allowed_mentions=discord.AllowedMentions.none())
        notes = []
        if await prefix_utils._is_server_np_enabled(ctx.guild.id):
            notes.append("Server-wide is on, so everyone can already skip the prefix. Run `premium np server disable` to limit it to your list.")
        if not await prefix_utils.np_master_enabled(ctx.guild.id):
            notes.append("No-prefix mode is off. Run `premium np enable` to use it.")
        await ctx.send(embed=embeds.success(f"{e('check')} No-Prefix Added", f"{target.mention} can now use commands without a prefix." + ("\n\n" + "\n".join(notes) if notes else "")), allowed_mentions=discord.AllowedMentions.none())

    @premium_np_group.command(name="remove", aliases=["revoke", "delete"], help="Take no-prefix mode away from a role or member. Usage: premium np remove <role or member>")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def premium_np_remove(self, ctx: commands.Context, target: typing.Union[discord.Role, discord.Member, discord.User]):
        e = emoji_manager.get
        if not await prefix_utils.remove_np_target(ctx.guild.id, target.id):
            return await ctx.send(embed=embeds.error(f"{e('cross')} Not on the list", f"{target.mention} was not added."), allowed_mentions=discord.AllowedMentions.none())
        await ctx.send(embed=embeds.success(f"{e('check')} No-Prefix Removed", f"{target.mention} must use the prefix again."), allowed_mentions=discord.AllowedMentions.none())

    @premium_np_group.command(name="list", aliases=["targets"], help="Show the roles and members that can skip the prefix.")
    @has_guild_permission("administrator")
    @commands.guild_only()
    async def premium_np_list(self, ctx: commands.Context):
        e = emoji_manager.get
        targets = await prefix_utils.list_np_targets(ctx.guild.id)
        if not targets:
            return await ctx.send(embed=embeds.neutral(f"{e('premium_cat')} No-Prefix List", "No roles or members added. Use `premium np add <role or member>`."))
        lines = [f"{'<@&' if t['target_type'] == 'role' else '<@'}{t['target_id']}> · added <t:{int(t['added_at'])}:R>" for t in targets]
        await ctx.send(embed=embeds.neutral(f"{e('premium_cat')} No-Prefix List", "\n".join(lines)), allowed_mentions=discord.AllowedMentions.none())


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

    @np_group.command(name="add", help='Give a user global no-prefix access.')
    @is_privileged()
    async def np_add(self, ctx: commands.Context, user: discord.User):
        e = emoji_manager.get
        await prefix_utils.add_global_no_prefix(user.id, ctx.author.id)
        await ctx.send(embed=embeds.success(
            f"{e('check')} Global No-Prefix Granted",
            f"{user.mention} can now use Zyro commands without a prefix in any server the bot is in.",
        ))

    @np_group.command(name="remove", help='Take global no-prefix access from a user.')
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
