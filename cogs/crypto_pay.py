import asyncio
import io
import logging
import time
from typing import Optional

import aiohttp
import discord
from discord.ext import commands, tasks

import config
from utils import coins as coin_store, crypto_pay as store, emoji_manager, hdwallet, supporters
from utils.checks import is_privileged
from utils.components import error_layout, info_layout, success_layout

log = logging.getLogger("soward.crypto")
NO_MENTIONS = discord.AllowedMentions.none()
TEST_KEY = "zpub6rFR7y4Q2AijBEqTUquhVz398htDFrtymD9xYYfG1m4wAcvPhXNfE3EfH1r1ADqtfSdVCToUG868RvUUkgDKf31mGDtKsAYz2oz2AGutZYs"
GOLD = 0xF7931A
GREEN = 0x57F287
RED = 0xED4245
GREY = 0x95A5A6
CHECK_GAP = 15


def qr_available() -> bool:
    try:
        import qrcode
    except ImportError:
        return False
    return True


def qr_file(uri: str) -> Optional[discord.File]:
    if not qr_available():
        return None
    import qrcode
    try:
        buffer = io.BytesIO()
        qrcode.make(uri).save(buffer)
        buffer.seek(0)
        return discord.File(buffer, filename="pay.png")
    except Exception:
        return None


def money(usd: float) -> str:
    return f"${usd:g}"


def invoice_layout(invoice: dict, guild_name: str, with_qr: bool) -> discord.ui.LayoutView:
    coin = config.CRYPTO_COINS[invoice["coin"]]
    plan = store.plan_for(invoice["plan"]) or {"label": invoice["plan"]}
    status = invoice["status"]
    color = {"paid": GREEN, "expired": GREY, "cancelled": GREY, "review": RED}.get(status, GOLD)
    target = "a gift key" if invoice["kind"] == "key" else f"**{guild_name}**"
    if invoice["kind"] == "tip":
        lines = [f"## Pay with {coin}", f"Invoice `{invoice['invoice_id']}` · {plan['label']} to support {config.BOT_NAME}"]
    elif invoice["kind"] == "coins":
        lines = [f"## Pay with {coin}", f"Invoice `{invoice['invoice_id']}` · {plan['label']} ({money(invoice['usd'])})"]
    else:
        lines = [f"## Pay with {coin}", f"Invoice `{invoice['invoice_id']}` · Premium {plan['label']} ({money(invoice['usd'])}) for {target}"]
    if status in ("pending", "seen"):
        lines.append(f"\nSend **exactly** this amount:\n`{store.fmt_amount(invoice['amount_units'])} {invoice['coin'].upper()}`\nto this address:\n`{invoice['address']}`")
        if status == "seen":
            lines.append(f"\n**Payment seen:** {store.fmt_amount(invoice['received_units'])} received, {store.fmt_amount(invoice['confirmed_units'])} confirmed. Waiting for {config.CRYPTO_CONFIRMATIONS.get(invoice['coin'], 1)} confirmation(s).")
        else:
            lines.append("\n**Status:** waiting for payment")
        lines.append(f"-# Valid until <t:{int(invoice['expires_at'])}:t> (<t:{int(invoice['expires_at'])}:R>). This address belongs to this invoice only. Send only {invoice['coin'].upper()} on its own network, and send the full amount in one or more payments. It is checked automatically.")
    elif status == "paid":
        result = store.result_of(invoice)
        if result.get("type") == "coins":
            lines.append(f"\n**Paid.** **{coin_store.fmt(result.get('diamonds', result.get('coins', 0)))}** diamonds were added to your wallet.")
        elif result.get("type") == "tip":
            lines.append("\n**Paid.** Thank you for supporting " + config.BOT_NAME + f". **{coin_store.fmt(result.get('coins', 0))}** coins were added to your wallet. Use `support public on` if you would like your name on the supporters page.")
        elif result.get("type") == "key":
            lines.append("\n**Paid.** Your premium key was sent to your DMs. You can also press the button below to see it.")
        elif result.get("expires"):
            lines.append(f"\n**Paid.** Premium is active until <t:{int(result['expires'])}:F>.")
        else:
            lines.append("\n**Paid.** Premium is active with no end date.")
    elif status == "expired":
        lines.append("\n**This invoice expired.** If you already sent the payment, it is still checked for 24 hours and premium is added when it confirms.")
    elif status == "cancelled":
        lines.append("\nThis invoice was cancelled.")
    elif status == "review":
        lines.append("\nA payment arrived but did not match the invoice. The bot owner will review it. Keep your transaction id.")
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay("\n".join(lines)))
    if with_qr and status in ("pending", "seen"):
        container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://pay.png")))
    row = discord.ui.ActionRow()
    if status in ("pending", "seen"):
        row.add_item(discord.ui.Button(label="Check payment", style=discord.ButtonStyle.primary, custom_id=f"pay:check:{invoice['invoice_id']}"))
        if status == "pending":
            row.add_item(discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id=f"pay:cancel:{invoice['invoice_id']}"))
    elif status == "expired":
        row.add_item(discord.ui.Button(label="I already paid, check again", style=discord.ButtonStyle.primary, custom_id=f"pay:check:{invoice['invoice_id']}"))
    elif status == "paid" and invoice["kind"] == "key":
        row.add_item(discord.ui.Button(label="Show my key", style=discord.ButtonStyle.success, custom_id=f"pay:key:{invoice['invoice_id']}"))
    if row.children:
        container.add_item(row)
    view.add_item(container)
    return view


class BuyView(discord.ui.LayoutView):
    def __init__(self, cog: "CryptoPay", ctx: commands.Context, kind: str, coins: list[str], lifetime: bool):
        super().__init__(timeout=300)
        self.cog = cog
        self.ctx = ctx
        self.kind = kind
        self.coins = coins
        self.lifetime = lifetime
        self.plan: Optional[str] = None
        self.render()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Only the person who started this can use these buttons.", ephemeral=True)
            return False
        return True

    def render(self):
        self.clear_items()
        container = discord.ui.Container(accent_color=GOLD)
        target = "a gift key anyone can redeem" if self.kind == "key" else f"**{self.ctx.guild.name}**" if self.ctx.guild else "this chat"
        if self.kind in ("tip", "coins"):
            coins_mode = self.kind == "coins"
            title = "Buy diamonds" if coins_mode else f"Support {config.BOT_NAME}"
            if self.plan is None:
                if coins_mode:
                    intro = f"Pay with Bitcoin or Litecoin, no account needed. **{money(1)} = {coin_store.fmt(config.DIAMOND_PER_USD)} diamonds**, added to your wallet when the payment confirms.\n\n**Choose an amount**"
                    amounts = config.COIN_TOPUP_AMOUNTS
                    note = f"-# Want a different amount? Use `coins topup <amount>` with {money(config.COIN_TOPUP_MIN_USD)} to {money(config.COIN_TOPUP_MAX_USD)}."
                else:
                    intro = f"Tips help cover hosting. Pay with Bitcoin or Litecoin, no account needed. Every tip gives **{coin_store.fmt(config.SUPPORT_COINS)} coins**, whatever the amount, plus a thank-you role in the support server and an optional place on the supporters page.\n\n**Choose an amount**"
                    amounts = config.SUPPORT_AMOUNTS
                    note = f"-# Want a different amount? Use `support <amount>` with {money(config.SUPPORT_MIN_USD)} to {money(config.SUPPORT_MAX_USD)}."
                container.add_item(discord.ui.TextDisplay(f"## {title}\n{intro}"))
                row = discord.ui.ActionRow()
                for amount in amounts:
                    label = f"{money(amount)} · {coin_store.fmt(coin_store.usd_to_diamonds(amount))}" if coins_mode else money(amount)
                    button = discord.ui.Button(label=label, style=discord.ButtonStyle.primary)
                    button.callback = self._plan_callback(f"{self.kind}:{amount}")
                    row.add_item(button)
                container.add_item(row)
                container.add_item(discord.ui.TextDisplay(note))
            else:
                plan = store.plan_for(self.plan)
                summary = f"**{plan['label']}** for {money(plan['usd'])}." if coins_mode else f"**{money(plan['usd'])}** tip."
                container.add_item(discord.ui.TextDisplay(f"## {title}\n{summary}\n\n**Choose a coin**"))
                row = discord.ui.ActionRow()
                for coin in self.coins:
                    button = discord.ui.Button(label=config.CRYPTO_COINS[coin], style=discord.ButtonStyle.success)
                    button.callback = self._coin_callback(coin)
                    row.add_item(button)
                back = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary)
                back.callback = self._back
                row.add_item(back)
                container.add_item(row)
            self.add_item(container)
            return
        if self.plan is None:
            lines = [f"## Soward Premium", f"You are buying premium for {target}. Pay with Bitcoin or Litecoin, no account or KYC. Premium turns on automatically once the payment confirms.", "", "**Choose a plan**"]
            container.add_item(discord.ui.TextDisplay("\n".join(lines)))
            row = discord.ui.ActionRow()
            for key, plan in config.CRYPTO_PLANS.items():
                if plan["days"] is None and self.lifetime:
                    continue
                button = discord.ui.Button(label=f"{plan['label']} · {money(plan['usd'])}", style=discord.ButtonStyle.primary)
                button.callback = self._plan_callback(key)
                row.add_item(button)
            container.add_item(row)
        else:
            plan = store.plan_for(self.plan)
            container.add_item(discord.ui.TextDisplay(f"## Soward Premium\n**{plan['label']}** for {money(plan['usd'])} for {target}.\n\n**Choose a coin**"))
            row = discord.ui.ActionRow()
            for coin in self.coins:
                button = discord.ui.Button(label=config.CRYPTO_COINS[coin], style=discord.ButtonStyle.success)
                button.callback = self._coin_callback(coin)
                row.add_item(button)
            back = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary)
            back.callback = self._back
            row.add_item(back)
            container.add_item(row)
        self.add_item(container)

    def _plan_callback(self, key: str):
        async def callback(interaction: discord.Interaction):
            self.plan = key
            self.render()
            await interaction.response.edit_message(view=self)
        return callback

    async def _back(self, interaction: discord.Interaction):
        self.plan = None
        self.render()
        await interaction.response.edit_message(view=self)

    def _coin_callback(self, coin: str):
        async def callback(interaction: discord.Interaction):
            await interaction.response.defer()
            try:
                invoice = await store.create_invoice(self.cog.session, self.ctx.guild.id if self.ctx.guild else 0, self.ctx.author.id, self.plan, coin, self.kind)
            except store.PayError as exc:
                return await interaction.edit_original_response(view=error_layout("Cannot create invoice", str(exc)))
            file = qr_file(store.uri_for(invoice))
            view = invoice_layout(invoice, self.ctx.guild.name if self.ctx.guild else "this chat", file is not None)
            message = await interaction.edit_original_response(view=view, attachments=[file] if file else [])
            await store.remember_message(invoice["invoice_id"], message.channel.id, message.id)
            self.stop()
        return callback


class CryptoPay(commands.Cog):
    category = "Premium"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_check: dict[str, float] = {}
        self.grace_checked: dict[str, float] = {}
        self.gate = asyncio.Semaphore(4)

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "SowardBot/1.0"})
        self.watch.start()

    async def cog_unload(self):
        self.watch.cancel()
        if self.session:
            await self.session.close()

    async def start_purchase(self, ctx: commands.Context, gift: bool = False):
        coins = await store.enabled_coins()
        if not coins:
            return await ctx.send(view=error_layout("Crypto payments are not set up", "The bot owner has not added a wallet yet. Ask them to run `crypto setup`."))
        kind = "key" if gift else "server"
        row = await store.db.raw_fetchone("SELECT premium, premium_expires_at FROM guilds WHERE guild_id=?", (ctx.guild.id,))
        lifetime = bool(row and row["premium"] and row["premium_expires_at"] is None) and not gift
        if lifetime:
            return await ctx.send(view=info_layout("Already lifetime", "This server already has premium with no end date."))
        await ctx.send(view=BuyView(self, ctx, kind, coins, lifetime))

    async def start_tip(self, ctx: commands.Context, amount: Optional[float]):
        coins = await store.enabled_coins()
        if not coins:
            return await ctx.send(view=error_layout("Tips are not set up", "The bot owner has not added a wallet yet."))
        view = BuyView(self, ctx, "tip", coins, False)
        if amount is not None:
            if store.plan_for(f"tip:{amount}") is None:
                return await ctx.send(view=error_layout("Invalid amount", f"Choose an amount from {money(config.SUPPORT_MIN_USD)} to {money(config.SUPPORT_MAX_USD)}."))
            view.plan = f"tip:{round(amount, 2)}"
            view.render()
        await ctx.send(view=view)

    async def start_coins(self, ctx: commands.Context, amount: Optional[float]):
        coins = await store.enabled_coins()
        if not coins:
            return await ctx.send(view=error_layout("Coin top-ups are not set up", "The bot owner has not added a wallet yet."))
        view = BuyView(self, ctx, "coins", coins, False)
        if amount is not None:
            if store.plan_for(f"coins:{amount}") is None:
                return await ctx.send(view=error_layout("Invalid amount", f"Choose an amount from {money(config.COIN_TOPUP_MIN_USD)} to {money(config.COIN_TOPUP_MAX_USD)}."))
            view.plan = f"coins:{round(amount, 2)}"
            view.render()
        await ctx.send(view=view)

    async def grant_supporter_role(self, user_id: int):
        if not (config.SUPPORT_GUILD_ID and config.SUPPORTER_ROLE_ID):
            return
        guild = self.bot.get_guild(config.SUPPORT_GUILD_ID)
        role = guild.get_role(config.SUPPORTER_ROLE_ID) if guild else None
        member = guild.get_member(user_id) if guild else None
        if role is None or member is None:
            return
        try:
            await member.add_roles(role, reason="Supporter")
        except discord.HTTPException:
            pass

    async def log(self, text: str):
        channel_id = await store.log_channel()
        channel = self.bot.get_channel(channel_id) if channel_id else None
        if channel is None:
            return
        try:
            await channel.send(view=info_layout("Crypto payments", text), allowed_mentions=NO_MENTIONS)
        except discord.HTTPException:
            pass

    async def refresh_message(self, invoice: dict, final: bool = False):
        if not invoice.get("channel_id") or not invoice.get("message_id"):
            return
        channel = self.bot.get_channel(int(invoice["channel_id"]))
        if channel is None:
            return
        guild = self.bot.get_guild(int(invoice["guild_id"]))
        view = invoice_layout(invoice, guild.name if guild else "this server", qr_available())
        try:
            kwargs = {"view": view}
            if final or invoice["status"] not in ("pending", "seen"):
                kwargs["attachments"] = []
            await channel.get_partial_message(int(invoice["message_id"])).edit(**kwargs)
        except discord.HTTPException:
            pass

    async def deliver(self, invoice: dict):
        result = invoice["result_data"]
        user = self.bot.get_user(int(invoice["user_id"]))
        if user is None:
            try:
                user = await self.bot.fetch_user(int(invoice["user_id"]))
            except discord.HTTPException:
                user = None
        plan = store.plan_for(invoice["plan"]) or {"label": invoice["plan"]}
        if result["type"] == "coins":
            body = f"Thank you. **{coin_store.fmt(result.get('diamonds', result.get('coins', 0)))}** diamonds were added to your wallet for {money(result['usd'])}."
        elif result["type"] == "tip":
            body = f"Thank you for your {money(result['usd'])} tip. It goes straight to hosting, and **{coin_store.fmt(result.get('coins', 0))}** coins were added to your wallet.\nUse `support public on` if you would like your name on the supporters page."
            await self.grant_supporter_role(int(invoice["user_id"]))
        elif result["type"] == "key":
            body = f"Thank you. Here is your premium key for **{plan['label']}**:\n`{result['key']}`\nRedeem it in a server with `premium claim {result['key']}`."
        elif result.get("expires"):
            body = f"Thank you. Premium **{plan['label']}** is now active until <t:{int(result['expires'])}:F>."
        else:
            body = f"Thank you. Premium **{plan['label']}** is now active with no end date."
        body += f"\n\n-# Invoice {invoice['invoice_id']} · {store.fmt_amount(invoice['received_units'])} {invoice['coin'].upper()}"
        if user is not None:
            try:
                await user.send(view=success_layout("Payment confirmed", body))
            except discord.HTTPException:
                pass
        what = "diamonds" if result["type"] == "coins" else "a tip" if result["type"] == "tip" else "gift key" if result["type"] == "key" else f"server `{invoice['guild_id']}`"
        await self.log(f"Invoice `{invoice['invoice_id']}` paid by <@{invoice['user_id']}> for {what}: {plan['label']}, {store.fmt_amount(invoice['received_units'])} {invoice['coin'].upper()} ({money(invoice['usd'])}).")

    @commands.group(name="support", aliases=["tip", "donate"], invoke_without_command=True, help="Support hosting with a Bitcoin or Litecoin tip. Usage: support [amount in USD]")
    async def support(self, ctx: commands.Context, amount: Optional[float] = None):
        await self.start_tip(ctx, amount)

    @support.command(name="public", help="Show or hide your name on the supporters page. Usage: support public on|off")
    async def support_public(self, ctx: commands.Context, mode: str = ""):
        mode = mode.lower()
        if mode not in ("on", "off"):
            return await ctx.send(view=info_layout("Supporters page", "Use `support public on` to show your name on the supporters page, or `support public off` to hide it."))
        if not await supporters.set_public(ctx.author.id, mode == "on", ctx.author.display_name):
            return await ctx.send(view=error_layout("Not a supporter yet", "Only people who have sent a tip can be listed. Use `support` to send one."))
        await ctx.send(view=success_layout("Updated", "Your name is now on the supporters page." if mode == "on" else "Your name is hidden from the supporters page."))

    @support.command(name="status", aliases=["me"], help="See your supporter status.")
    async def support_status(self, ctx: commands.Context):
        row = await supporters.get(ctx.author.id)
        if not row:
            return await ctx.send(view=info_layout("Supporter", "You have not sent a tip yet. Use `support` to help cover hosting."))
        await ctx.send(view=info_layout("Supporter", f"You are a supporter. Total tipped: **{money(round(row['total_usd'], 2))}** across **{row['tips']}** tip(s).\nSupporters page: **{'visible' if row['public'] else 'hidden'}**."))

    async def check_invoice(self, invoice: dict, force: bool = False) -> dict:
        async with self.gate:
            observations = await store.observe(self.session, invoice["coin"], invoice["address"])
        txs, responders = store.consensus(observations)
        invoice["_responders"] = responders
        invoice["_hint"] = store.unconfirmed_hint(observations)
        if responders < config.CRYPTO_MIN_AGREE:
            return invoice
        verdict = store.evaluate(invoice, txs)
        await store.record_txs(invoice, txs)
        if verdict["state"] == "paid":
            settled = await store.settle(invoice["invoice_id"], verdict["received"], verdict["confirmed"])
            if settled:
                await self.refresh_message(settled, True)
                await self.deliver(settled)
                return settled
            return await store.get_invoice(invoice["invoice_id"])
        changed = verdict["received"] != invoice["received_units"] or verdict["confirmed"] != invoice["confirmed_units"]
        if changed or verdict["state"] != invoice["status"]:
            status = verdict["state"] if invoice["status"] in ("pending", "seen") else invoice["status"]
            await store.update(invoice["invoice_id"], status=status, received_units=verdict["received"], confirmed_units=verdict["confirmed"])
            fresh = await store.get_invoice(invoice["invoice_id"])
            await self.refresh_message(fresh)
            return fresh
        return invoice

    @tasks.loop(seconds=config.CRYPTO_POLL_SECONDS)
    async def watch(self):
        invoices = await store.watchable()
        now = time.time()
        for invoice in invoices:
            if invoice["status"] == "pending" and now > invoice["expires_at"]:
                await store.update(invoice["invoice_id"], status="expired")
                invoice["status"] = "expired"
                await self.refresh_message(invoice, True)
        stale = await store.db.raw_fetch("SELECT * FROM crypto_invoices WHERE status='seen' AND expires_at<?", (now - config.CRYPTO_GRACE_HOURS * 3600,))
        for row in stale:
            await store.update(row["invoice_id"], status="review")
            fresh = await store.get_invoice(row["invoice_id"])
            await self.refresh_message(fresh, True)
            await self.log(f"Invoice `{row['invoice_id']}` from <@{row['user_id']}> received a partial payment and was not completed in time. Review it with `crypto verify {row['invoice_id']}`.")
        due = []
        for invoice in invoices:
            if invoice["status"] == "expired":
                if now - self.grace_checked.get(invoice["invoice_id"], 0) < config.CRYPTO_GRACE_POLL_SECONDS:
                    continue
                self.grace_checked[invoice["invoice_id"]] = now
            due.append(invoice)
        results = await asyncio.gather(*[self.check_invoice(i) for i in due], return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                log.error("Crypto check failed: %s", result)

    @watch.before_loop
    async def before_watch(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component:
            return
        custom_id = str((interaction.data or {}).get("custom_id", ""))
        if not custom_id.startswith("pay:"):
            return
        parts = custom_id.split(":", 2)
        if len(parts) != 3:
            return
        action, invoice_id = parts[1], parts[2]
        invoice = await store.get_invoice(invoice_id)
        if invoice is None:
            return await interaction.response.send_message("That invoice no longer exists.", ephemeral=True)
        owner = interaction.user.id in config.ALL_PRIVILEGED_IDS
        if interaction.user.id != invoice["user_id"] and not owner:
            return await interaction.response.send_message("Only the person who created this invoice can use these buttons.", ephemeral=True)
        if action == "key":
            result = store.result_of(invoice)
            if invoice["status"] != "paid" or result.get("type") != "key":
                return await interaction.response.send_message("There is no key for this invoice.", ephemeral=True)
            return await interaction.response.send_message(f"Your premium key: `{result['key']}`\nRedeem it with `premium claim {result['key']}`.", ephemeral=True)
        if action == "cancel":
            if invoice["status"] != "pending":
                return await interaction.response.send_message("This invoice can no longer be cancelled.", ephemeral=True)
            await store.update(invoice["invoice_id"], status="cancelled")
            invoice["status"] = "cancelled"
            return await interaction.response.edit_message(view=invoice_layout(invoice, interaction.guild.name if interaction.guild else "this server", False), attachments=[])
        if action == "check":
            if invoice["status"] not in ("pending", "seen", "expired"):
                return await interaction.response.send_message(f"This invoice is {invoice['status']}.", ephemeral=True)
            wait = CHECK_GAP - (time.time() - self.last_check.get(invoice["invoice_id"], 0))
            if wait > 0:
                return await interaction.response.send_message(f"Checked a moment ago. Try again in {int(wait) + 1} seconds.", ephemeral=True)
            self.last_check[invoice["invoice_id"]] = time.time()
            await interaction.response.defer(ephemeral=True)
            fresh = await self.check_invoice(invoice, True)
            if fresh.get("_responders", 9) < config.CRYPTO_MIN_AGREE:
                text = "Not enough blockchain explorers are answering right now, so I cannot confirm yet. It is checked again automatically." + (" A payment may already be visible to one of them." if fresh.get("_hint") else "")
            elif fresh["status"] == "paid":
                text = "Payment confirmed. Premium is active."
            elif fresh["received_units"]:
                text = f"Payment seen: {store.fmt_amount(fresh['received_units'])} of {store.fmt_amount(fresh['amount_units'])} {fresh['coin'].upper()}. Waiting for confirmations."
            elif fresh.get("_hint"):
                text = "A payment is visible to one explorer and is waiting for a second one to agree. This usually takes a minute."
            else:
                text = "No payment found yet. It can take a minute after you send."
            await interaction.followup.send(text, ephemeral=True)

    async def _invoice(self, ctx: commands.Context, invoice_id: str) -> Optional[dict]:
        invoice = await store.get_invoice(invoice_id)
        if invoice is None:
            await ctx.send(view=error_layout("Not found", "No invoice with that id."))
        return invoice

    @commands.group(name="crypto", invoke_without_command=True, help="Owner tools for crypto premium payments.")
    @is_privileged()
    async def crypto(self, ctx: commands.Context):
        await ctx.send(view=info_layout("Crypto payments", "`crypto setup <btc|ltc> <xpub>` · `crypto off <coin>` · `crypto status` · `crypto invoices [status]` · `crypto verify <id>` · `crypto approve <id>` · `crypto cancel <id>` · `crypto log [#channel]`"))

    @crypto.command(name="setup", help="Add a wallet. Usage: crypto setup <btc|ltc> <extended public key>")
    @is_privileged()
    async def crypto_setup(self, ctx: commands.Context, coin: str, xpub: str):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        coin = coin.lower()
        if coin not in config.CRYPTO_COINS:
            return await ctx.send(view=error_layout("Unknown coin", "Use `btc` or `ltc`."))
        try:
            first = hdwallet.derive_address(xpub, coin, 0)
        except hdwallet.WalletError as exc:
            return await ctx.send(view=error_layout("Invalid key", str(exc)))
        await store.set_xpub(coin, xpub.strip())
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} {config.CRYPTO_COINS[coin]} wallet saved",
                                           f"Address number 1 is `{first}`.\n\n**Check that this is the first receiving address in your wallet.** If it is not, remove the wallet with `crypto off {coin}` and export the key again. Run `crypto status` to test the explorers before taking payments."))

    @crypto.command(name="off", help="Remove a wallet and stop selling in that coin.")
    @is_privileged()
    async def crypto_off(self, ctx: commands.Context, coin: str):
        if coin.lower() not in config.CRYPTO_COINS:
            return await ctx.send(view=error_layout("Unknown coin", "Use `btc` or `ltc`."))
        await store.set_xpub(coin.lower(), None)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Removed", f"{config.CRYPTO_COINS[coin.lower()]} is no longer offered. Open invoices keep being checked."))

    @crypto.command(name="status", help="Wallets, explorers, prices and open invoices.")
    @is_privileged()
    async def crypto_status(self, ctx: commands.Context):
        lines = []
        for coin, name in config.CRYPTO_COINS.items():
            xpub = await store.get_xpub(coin)
            lines.append(f"**{name}:** " + ("wallet set" if xpub else "no wallet"))
            probe = hdwallet.derive_address(xpub or TEST_KEY, coin, 0)
            healthy = 0
            for kind, base in config.CRYPTO_PROVIDERS.get(coin, []):
                host = base.split("/")[2]
                took = await store.health(self.session, kind, base, probe)
                healthy += 1 if took is not None else 0
                lines.append(f"- {host}: " + (f"ok ({took} ms)" if took is not None else "not reachable"))
            need = config.CRYPTO_MIN_AGREE
            lines.append(f"- explorers: {healthy} working, {need} must agree" + ("" if healthy >= need else " (**not enough, payments cannot confirm automatically**)"))
            try:
                lines.append(f"- price: ${await store.fetch_rate(self.session, coin):,.2f}")
            except store.PayError as exc:
                lines.append(f"- price: {exc}")
        open_now = await store.db.raw_fetchone("SELECT COUNT(*) AS c FROM crypto_invoices WHERE status IN ('pending','seen')")
        review = await store.db.raw_fetchone("SELECT COUNT(*) AS c FROM crypto_invoices WHERE status='review'")
        lines.append(f"\n**Open invoices:** {open_now['c']} · **Needing review:** {review['c']}")
        lines.append("**Plans:** " + ", ".join(f"{p['label']} {money(p['usd'])}" for p in config.CRYPTO_PLANS.values()))
        log_id = await store.log_channel()
        lines.append(f"**Log channel:** {f'<#{log_id}>' if log_id else 'not set'}")
        await ctx.send(view=info_layout("Crypto status", "\n".join(lines)))

    @crypto.command(name="invoices", aliases=["list"], help="Recent invoices. Usage: crypto invoices [status]")
    @is_privileged()
    async def crypto_invoices(self, ctx: commands.Context, status: str = None):
        rows = await store.recent(status.lower() if status else None)
        if not rows:
            return await ctx.send(view=info_layout("Invoices", "No invoices."))
        lines = [f"`{r['invoice_id']}` · {r['status']} · {r['coin'].upper()} {store.fmt_amount(r['amount_units'])} · <@{r['user_id']}> · <t:{int(r['created_at'])}:R>" for r in rows]
        await ctx.send(view=info_layout("Invoices", "\n".join(lines)), allowed_mentions=NO_MENTIONS)

    @crypto.command(name="verify", help="Check the chain for an invoice now, even if it expired. Usage: crypto verify <id>")
    @is_privileged()
    async def crypto_verify(self, ctx: commands.Context, invoice_id: str):
        invoice = await self._invoice(ctx, invoice_id)
        if invoice is None:
            return
        if invoice["status"] in ("paid", "cancelled"):
            return await ctx.send(view=info_layout("Invoice", f"Invoice is already {invoice['status']}."))
        observations = await store.observe(self.session, invoice["coin"], invoice["address"])
        txs, responders = store.consensus(observations)
        if responders < config.CRYPTO_MIN_AGREE:
            return await ctx.send(view=error_layout("Not enough explorers", f"Only {responders} explorer(s) answered and {config.CRYPTO_MIN_AGREE} must agree. Try again shortly, or check `crypto status`."))
        verdict = store.evaluate(invoice, txs)
        await store.record_txs(invoice, txs)
        lines = [f"Responders: {responders}", f"Received: {store.fmt_amount(verdict['received'])} / {store.fmt_amount(invoice['amount_units'])} {invoice['coin'].upper()}", f"Confirmed: {store.fmt_amount(verdict['confirmed'])} (needs {verdict['required']} confirmation(s))"]
        lines += [f"- `{t.txid[:16]}…` {store.fmt_amount(t.units)} · {t.confirmations} conf" for t in txs]
        if verdict["state"] == "paid":
            settled = await store.settle(invoice["invoice_id"], verdict["received"], verdict["confirmed"], ctx.author.id)
            if settled:
                await self.refresh_message(settled, True)
                await self.deliver(settled)
                lines.append("\n**Fully paid. Premium granted.**")
        elif verdict["received"]:
            await store.update(invoice["invoice_id"], received_units=verdict["received"], confirmed_units=verdict["confirmed"])
            lines.append(f"\nNot enough yet. Use `crypto approve {invoice['invoice_id']}` to grant it anyway.")
        await ctx.send(view=info_layout(f"Invoice {invoice['invoice_id']}", "\n".join(lines)))

    @crypto.command(name="approve", help="Grant an invoice manually, for example after a short payment. Usage: crypto approve <id>")
    @is_privileged()
    async def crypto_approve(self, ctx: commands.Context, invoice_id: str):
        invoice = await self._invoice(ctx, invoice_id)
        if invoice is None:
            return
        received = max(invoice["received_units"], invoice["confirmed_units"])
        if received <= 0:
            return await ctx.send(view=error_layout("No payment recorded", f"Run `crypto verify {invoice['invoice_id']}` first. Nothing has been received on this invoice."))
        settled = await store.settle(invoice["invoice_id"], invoice["received_units"], invoice["confirmed_units"], ctx.author.id)
        if settled is None:
            return await ctx.send(view=error_layout("Cannot approve", "That invoice is already paid or cancelled."))
        await self.refresh_message(settled, True)
        await self.deliver(settled)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Approved", f"Granted for the {store.fmt_amount(received)} {invoice['coin'].upper()} received."))

    @crypto.command(name="cancel", help="Cancel an unpaid invoice. Usage: crypto cancel <id>")
    @is_privileged()
    async def crypto_cancel(self, ctx: commands.Context, invoice_id: str):
        invoice = await self._invoice(ctx, invoice_id)
        if invoice is None:
            return
        if invoice["status"] in ("paid", "cancelled"):
            return await ctx.send(view=error_layout("Cannot cancel", f"Invoice is already {invoice['status']}."))
        await store.update(invoice["invoice_id"], status="cancelled")
        invoice["status"] = "cancelled"
        await self.refresh_message(invoice, True)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Cancelled", f"Invoice `{invoice['invoice_id']}` was cancelled."))

    @crypto.command(name="log", help="Channel for payment logs. Usage: crypto log [#channel]")
    @is_privileged()
    async def crypto_log(self, ctx: commands.Context, channel: discord.TextChannel = None):
        await store.set_log_channel(channel.id if channel else None)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Log", f"Payments are logged in {channel.mention}." if channel else "Payment log removed."))


async def setup(bot: commands.Bot):
    await bot.add_cog(CryptoPay(bot))
