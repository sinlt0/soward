import asyncio
import io
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from utils import db, embed_templates, emoji_manager, greeting_card, greeting_config, message_vars
from utils.checks import has_guild_permission
from utils.components import error_layout, info_layout, success_layout
import config

TRIGGER_LABELS = {"join": "Welcome", "leave": "Leave", "boost": "Boost", "ban": "Ban"}


def _accent_rgb(hex_str: Optional[str]) -> tuple[int, int, int]:
    if not hex_str:
        return (127, 179, 213)
    try:
        h = hex_str.lstrip("#")
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except (ValueError, IndexError):
        return (127, 179, 213)


class Greetings(commands.Cog):
    category = "Config"
    submodule = True

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.session: Optional[aiohttp.ClientSession] = None

    async def cog_load(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "Soward/1.0"})

    async def cog_unload(self):
        if self.session:
            await self.session.close()

    async def _resolve_text_and_embeds(self, guild_id: int, template_text: Optional[str], embed_name: Optional[str], var_map: dict) -> tuple[Optional[str], list[discord.Embed]]:
        embeds: list[discord.Embed] = []
        text: Optional[str] = None

        if template_text:
            resolved_text, ref_embeds = await embed_templates.resolve_embed_refs(guild_id, template_text, var_map)
            text = resolved_text
            embeds.extend(ref_embeds)

        if embed_name:
            template = await embed_templates.get_template(guild_id, embed_name)
            if template:
                fields = await embed_templates.get_fields(guild_id, embed_name)
                embeds.append(embed_templates.build_discord_embed(template, var_map, fields))

        return text, embeds

    async def _render_card_bytes(self, member: discord.Member, cfg: dict, title_text: str, subtitle_text: str) -> Optional[bytes]:
        if not cfg["use_card"]:
            return None

        avatar_url = member.display_avatar.with_format("png").with_size(256).url
        try:
            async with self.session.get(avatar_url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
                if resp.status != 200:
                    return None
                avatar_bytes = await resp.read()
        except aiohttp.ClientError:
            return None

        background_bytes = None
        if cfg["card_background_url"]:
            try:
                async with self.session.get(cfg["card_background_url"], timeout=aiohttp.ClientTimeout(total=6)) as resp:
                    if resp.status == 200:
                        background_bytes = await resp.read()
            except aiohttp.ClientError:
                pass

        buffer = await asyncio.to_thread(
            greeting_card.render_greeting_card,
            avatar_bytes, member.display_name, title_text, subtitle_text,
            cfg["card_layout"], _accent_rgb(cfg["card_accent_color"]), background_bytes,
        )
        return buffer.getvalue()

    async def _dispatch(self, member: discord.Member, guild: discord.Guild, trigger_type: str, ban_reason: Optional[str] = None) -> None:
        cfg = await greeting_config.get_config(guild.id, trigger_type)
        if not cfg["enabled"]:
            return

        var_map = greeting_config.build_greeting_variables(member, guild, trigger_type, ban_reason)
        text, embeds = await self._resolve_text_and_embeds(guild.id, cfg["message_text"], cfg["embed_name"], var_map)

        default_title = {
            "join": f"Welcome to {guild.name}!",
            "leave": f"{member.display_name} has left the server.",
            "boost": f"Thank you for boosting, {member.display_name}!",
            "ban": f"{member.display_name} was banned.",
        }[trigger_type]

        card_bytes = await self._render_card_bytes(member, cfg, default_title, var_map.get("membercount_ordinal", ""))

        if not text and not embeds and not card_bytes:
            text = default_title

        card_filename = "greeting-card.png"
        if card_bytes and embeds:
            embeds[-1].set_image(url=f"attachment://{card_filename}")

        sent_to_dm = False
        if cfg["send_as_dm"] and trigger_type in ("join", "leave", "boost"):
            try:
                dm_file = discord.File(io.BytesIO(card_bytes), filename=card_filename) if card_bytes else None
                await member.send(
                    content=text, embeds=embeds or None, file=dm_file,
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
                )
                sent_to_dm = True
            except discord.HTTPException:
                sent_to_dm = False

        if cfg["send_as_dm"]:
            should_send_channel = (not sent_to_dm) or cfg["dm_fallback_to_channel"]
        else:
            should_send_channel = True

        if should_send_channel and cfg["channel_id"]:
            channel = guild.get_channel(cfg["channel_id"])
            if channel:
                try:
                    kwargs = {
                        "content": text, "embeds": embeds or None,
                        "allowed_mentions": discord.AllowedMentions(users=True, roles=False, everyone=False),
                    }
                    if card_bytes:
                        kwargs["file"] = discord.File(io.BytesIO(card_bytes), filename=card_filename)
                    if cfg["delete_after_seconds"]:
                        kwargs["delete_after"] = cfg["delete_after_seconds"]
                    await channel.send(**kwargs)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        await self._dispatch(member, member.guild, "join")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot:
            return

        try:
            ban_entry = await member.guild.fetch_ban(member)
        except discord.NotFound:
            await self._dispatch(member, member.guild, "leave")
            return
        except discord.HTTPException:
            await self._dispatch(member, member.guild, "leave")
            return

        await self._dispatch(member, member.guild, "ban", ban_reason=ban_entry.reason)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.bot:
            return
        if before.premium_since is None and after.premium_since is not None:
            await self._dispatch(after, after.guild, "boost")

    @commands.group(name="greetings", aliases=["welcome", "greet"], invoke_without_command=True, help="Configure welcome, leave, boost, and ban messages.")
    @has_guild_permission("manage_guild")
    @commands.guild_only()
    async def greetings_group(self, ctx: commands.Context):
        e = emoji_manager.get
        lines = []
        for trigger in config.GREETING_TRIGGER_TYPES:
            cfg = await greeting_config.get_config(ctx.guild.id, trigger)
            channel = ctx.guild.get_channel(cfg["channel_id"]) if cfg["channel_id"] else None
            status = "🟢 Enabled" if cfg["enabled"] else "🔴 Disabled"
            lines.append(f"**{TRIGGER_LABELS[trigger]}** — {status} · {channel.mention if channel else 'No channel'}")

        body = (
            "\n".join(lines) +
            "\n\n-# Configure each with `greetings <join|leave|boost|ban> ...` subcommands. "
            "Use `greetings variables` to see all placeholders."
        )
        await ctx.send(view=info_layout(f"{e('wave')} Greeting Messages", body))

    @greetings_group.command(name="channel", help="Set the channel for a trigger. Usage: greetings channel <join|leave|boost|ban> <#channel>")
    @has_guild_permission("manage_guild")
    async def greetings_channel(self, ctx: commands.Context, trigger: str, channel: discord.TextChannel):
        e = emoji_manager.get
        trigger = trigger.lower()
        if trigger not in config.GREETING_TRIGGER_TYPES:
            return await ctx.send(view=error_layout("Invalid Trigger", f"Choose from: {', '.join(config.GREETING_TRIGGER_TYPES)}"))

        await greeting_config.set_config_fields(ctx.guild.id, trigger, channel_id=channel.id)
        await ctx.send(view=success_layout(f"{e('check')} Channel Set", f"{TRIGGER_LABELS[trigger]} messages will post in {channel.mention}."))

    @greetings_group.command(name="toggle", help="Enable or disable a trigger. Usage: greetings toggle <join|leave|boost|ban>")
    @has_guild_permission("manage_guild")
    async def greetings_toggle(self, ctx: commands.Context, trigger: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        if trigger not in config.GREETING_TRIGGER_TYPES:
            return await ctx.send(view=error_layout("Invalid Trigger", f"Choose from: {', '.join(config.GREETING_TRIGGER_TYPES)}"))

        cfg = await greeting_config.get_config(ctx.guild.id, trigger)
        new_state = not cfg["enabled"]
        if new_state and not cfg["channel_id"] and not cfg["send_as_dm"]:
            return await ctx.send(view=error_layout("No Destination", f"Set a channel first with `greetings channel {trigger} #channel`, or enable DM delivery."))

        await greeting_config.set_config_fields(ctx.guild.id, trigger, enabled=new_state)
        state_text = "enabled" if new_state else "disabled"
        await ctx.send(view=success_layout(f"{e('check')} {TRIGGER_LABELS[trigger]} {state_text.title()}", f"{TRIGGER_LABELS[trigger]} messages are now {state_text}."))

    @greetings_group.command(name="message", help="Set the text/embed for a trigger. Usage: greetings message <join|leave|boost|ban> <text or {embed:name}>")
    @has_guild_permission("manage_guild")
    async def greetings_message(self, ctx: commands.Context, trigger: str, *, text: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        if trigger not in config.GREETING_TRIGGER_TYPES:
            return await ctx.send(view=error_layout("Invalid Trigger", f"Choose from: {', '.join(config.GREETING_TRIGGER_TYPES)}"))

        await greeting_config.set_config_fields(ctx.guild.id, trigger, message_text=text)

        preview_member = ctx.author
        var_map = greeting_config.build_greeting_variables(preview_member, ctx.guild, trigger, ban_reason="Example reason")
        preview_text, preview_embeds = await self._resolve_text_and_embeds(ctx.guild.id, text, None, var_map)

        await ctx.send(
            view=success_layout(f"{e('check')} Message Set", f"**Preview:**\n{preview_text or '*(embed only)*'}"),
            embeds=preview_embeds or None,
        )

    @greetings_group.command(name="embed", help="Attach a saved embed template to a trigger, or 'off' to remove it. Usage: greetings embed <join|leave|boost|ban> <embed_name|off>")
    @has_guild_permission("manage_guild")
    async def greetings_embed(self, ctx: commands.Context, trigger: str, embed_name: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        if trigger not in config.GREETING_TRIGGER_TYPES:
            return await ctx.send(view=error_layout("Invalid Trigger", f"Choose from: {', '.join(config.GREETING_TRIGGER_TYPES)}"))

        if embed_name.lower() == "off":
            await greeting_config.set_config_fields(ctx.guild.id, trigger, embed_name=None)
            return await ctx.send(view=success_layout(f"{e('check')} Embed Removed", f"{TRIGGER_LABELS[trigger]} no longer uses an embed template."))

        template = await embed_templates.get_template(ctx.guild.id, embed_name)
        if not template:
            return await ctx.send(view=error_layout("Not Found", f"No embed template named `{embed_name}`. Create one with `embed create {embed_name}` first."))

        await greeting_config.set_config_fields(ctx.guild.id, trigger, embed_name=embed_name)
        await ctx.send(view=success_layout(f"{e('check')} Embed Attached", f"{TRIGGER_LABELS[trigger]} will now include the `{embed_name}` embed template."))

    @greetings_group.command(name="dm", help="Configure DM delivery. Usage: greetings dm <join|leave|boost> <on|off> [fallback_on|fallback_off]")
    @has_guild_permission("manage_guild")
    async def greetings_dm(self, ctx: commands.Context, trigger: str, toggle: str, fallback: Optional[str] = None):
        e = emoji_manager.get
        trigger = trigger.lower()
        if trigger not in ("join", "leave", "boost"):
            return await ctx.send(view=error_layout("Invalid Trigger", "DM delivery is only available for `join`, `leave`, or `boost` — bans can't be DMed since the member is already removed."))

        toggle = toggle.lower()
        if toggle not in ("on", "off"):
            return await ctx.send(view=error_layout("Invalid Value", "Use `on` or `off`."))

        fields = {"send_as_dm": toggle == "on"}
        if fallback:
            fallback = fallback.lower()
            if fallback not in ("fallback_on", "fallback_off"):
                return await ctx.send(view=error_layout("Invalid Fallback", "Use `fallback_on` or `fallback_off`."))
            fields["dm_fallback_to_channel"] = fallback == "fallback_on"

        await greeting_config.set_config_fields(ctx.guild.id, trigger, **fields)
        await ctx.send(view=success_layout(f"{e('check')} DM Setting Updated", f"{TRIGGER_LABELS[trigger]} DM delivery is now `{toggle}`."))

    @greetings_group.command(name="card", help="Toggle the rendered welcome card image. Usage: greetings card <join|leave|boost|ban> <on|off> [layout]")
    @has_guild_permission("manage_guild")
    async def greetings_card(self, ctx: commands.Context, trigger: str, toggle: str, layout: Optional[str] = None):
        e = emoji_manager.get
        trigger = trigger.lower()
        if trigger not in config.GREETING_TRIGGER_TYPES:
            return await ctx.send(view=error_layout("Invalid Trigger", f"Choose from: {', '.join(config.GREETING_TRIGGER_TYPES)}"))

        toggle = toggle.lower()
        if toggle not in ("on", "off"):
            return await ctx.send(view=error_layout("Invalid Value", "Use `on` or `off`."))

        fields = {"use_card": toggle == "on"}
        if layout:
            layout = layout.lower()
            if layout not in config.GREETING_CARD_LAYOUTS:
                return await ctx.send(view=error_layout("Invalid Layout", f"Choose from: {', '.join(config.GREETING_CARD_LAYOUTS)}"))
            fields["card_layout"] = layout

        await greeting_config.set_config_fields(ctx.guild.id, trigger, **fields)
        await ctx.send(view=success_layout(f"{e('check')} Card Setting Updated", f"{TRIGGER_LABELS[trigger]} card is now `{toggle}`" + (f" using the `{layout}` layout." if layout else ".")))

    @greetings_group.command(name="cardcolor", help="Set the accent color for a trigger's card. Usage: greetings cardcolor <join|leave|boost|ban> <#hex>")
    @has_guild_permission("manage_guild")
    async def greetings_cardcolor(self, ctx: commands.Context, trigger: str, hex_color: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        if trigger not in config.GREETING_TRIGGER_TYPES:
            return await ctx.send(view=error_layout("Invalid Trigger", f"Choose from: {', '.join(config.GREETING_TRIGGER_TYPES)}"))

        cleaned = hex_color.lstrip("#")
        if len(cleaned) != 6 or any(c not in "0123456789abcdefABCDEF" for c in cleaned):
            return await ctx.send(view=error_layout("Invalid Color", "Provide a hex color like `#7FB3D5`."))

        await greeting_config.set_config_fields(ctx.guild.id, trigger, card_accent_color=cleaned)
        await ctx.send(view=success_layout(f"{e('check')} Color Set", f"{TRIGGER_LABELS[trigger]} card accent color set to `#{cleaned}`."))

    @greetings_group.command(name="cardbackground", help="Set a custom background image URL for a trigger's card, or 'off' to remove it.")
    @has_guild_permission("manage_guild")
    async def greetings_cardbackground(self, ctx: commands.Context, trigger: str, url: str):
        e = emoji_manager.get
        trigger = trigger.lower()
        if trigger not in config.GREETING_TRIGGER_TYPES:
            return await ctx.send(view=error_layout("Invalid Trigger", f"Choose from: {', '.join(config.GREETING_TRIGGER_TYPES)}"))

        value = None if url.lower() == "off" else url
        if value and not (value.startswith("http://") or value.startswith("https://")):
            return await ctx.send(view=error_layout("Invalid URL", "Provide a direct image URL, or `off` to remove it."))

        await greeting_config.set_config_fields(ctx.guild.id, trigger, card_background_url=value)
        if value:
            await ctx.send(view=success_layout(f"{e('check')} Background Set", f"{TRIGGER_LABELS[trigger]} card will use your custom background."))
        else:
            await ctx.send(view=success_layout(f"{e('check')} Background Removed", f"{TRIGGER_LABELS[trigger]} card will use the default background."))

    @greetings_group.command(name="joinroledelay", help="Delay auto-role assignment on join by N seconds (0 to disable). Usage: greetings joinroledelay <seconds>")
    @has_guild_permission("manage_guild")
    async def greetings_joinroledelay(self, ctx: commands.Context, seconds: int):
        e = emoji_manager.get
        if seconds < 0 or seconds > config.GREETING_MAX_JOIN_ROLE_DELAY_SECONDS:
            return await ctx.send(view=error_layout("Invalid Delay", f"Delay must be between 0 and {config.GREETING_MAX_JOIN_ROLE_DELAY_SECONDS} seconds."))

        await greeting_config.set_config_fields(ctx.guild.id, "join", join_role_delay_seconds=seconds)
        if seconds == 0:
            await ctx.send(view=success_layout(f"{e('check')} Delay Removed", "Join role delay disabled."))
        else:
            await ctx.send(view=success_layout(f"{e('check')} Delay Set", f"Auto-role assignment on join will be delayed by **{seconds} second(s)**."))

    @greetings_group.command(name="deleteafter", help="Auto-delete a trigger's channel message after N seconds (0 to disable). Usage: greetings deleteafter <join|leave|boost|ban> <seconds>")
    @has_guild_permission("manage_guild")
    async def greetings_deleteafter(self, ctx: commands.Context, trigger: str, seconds: int):
        e = emoji_manager.get
        trigger = trigger.lower()
        if trigger not in config.GREETING_TRIGGER_TYPES:
            return await ctx.send(view=error_layout("Invalid Trigger", f"Choose from: {', '.join(config.GREETING_TRIGGER_TYPES)}"))

        if seconds < 0:
            return await ctx.send(view=error_layout("Invalid Value", "Seconds must be 0 or greater."))

        value = seconds if seconds > 0 else None
        await greeting_config.set_config_fields(ctx.guild.id, trigger, delete_after_seconds=value)
        if value:
            await ctx.send(view=success_layout(f"{e('check')} Auto-Delete Set", f"{TRIGGER_LABELS[trigger]} messages will delete after **{value} second(s)**."))
        else:
            await ctx.send(view=success_layout(f"{e('check')} Auto-Delete Removed", f"{TRIGGER_LABELS[trigger]} messages will stay until manually deleted."))

    @greetings_group.command(name="variables", aliases=["vars"], help="Show all available placeholders for greeting messages.")
    async def greetings_variables(self, ctx: commands.Context):
        e = emoji_manager.get
        body = message_vars.variables_doc_block(greeting_config.GREETING_VARIABLE_DOCS)
        await ctx.send(view=info_layout(f"{e('info')} Greeting Variables", body))

    @greetings_group.command(name="test", help="Send a test of a trigger's message to yourself using your own account. Usage: greetings test <join|leave|boost|ban>")
    @has_guild_permission("manage_guild")
    async def greetings_test(self, ctx: commands.Context, trigger: str):
        trigger = trigger.lower()
        if trigger not in config.GREETING_TRIGGER_TYPES:
            return await ctx.send(view=error_layout("Invalid Trigger", f"Choose from: {', '.join(config.GREETING_TRIGGER_TYPES)}"))

        await self._dispatch(ctx.author, ctx.guild, trigger, ban_reason="Test reason")
        await ctx.message.add_reaction("✅")


async def setup(bot: commands.Bot):
    await bot.add_cog(Greetings(bot))
