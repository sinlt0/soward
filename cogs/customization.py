import asyncio
import base64
import ipaddress
import socket
from urllib.parse import urlparse

import aiohttp
import discord
from discord.ext import commands

from utils import emoji_manager, guild_settings
from utils.checks import has_guild_permission, premium_only
from utils.components import error_layout, info_layout, success_layout

MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _image_type(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _short(text: str) -> str:
    text = (text or "").strip().replace("`", "'")
    return text[:300] if text else "no details"


async def _url_is_public(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return False
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved or address.is_multicast:
            return False
    return True


class Customization(commands.Cog):
    category = "Customization"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._session: aiohttp.ClientSession | None = None

    def cog_unload(self):
        if self._session and not self._session.closed:
            self.bot.loop.create_task(self._session.close())

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _patch_member(self, guild_id: int, payload: dict) -> tuple[bool, str]:
        url = f"https://discord.com/api/v10/guilds/{guild_id}/members/@me"
        headers = {
            "Authorization": f"Bot {self.bot.http.token}",
            "Content-Type": "application/json",
        }
        try:
            async with self._get_session().patch(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    return True, ""
                return False, await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            return False, str(exc)

    async def _resolve_image(self, ctx: commands.Context, url: str | None) -> tuple[bytes | None, str | None, str]:
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.size > MAX_IMAGE_BYTES:
                return None, None, "That attachment is larger than 8MB."
            data = await attachment.read()
            source = attachment.url
        elif url:
            if not await _url_is_public(url):
                return None, None, "That link isn't a public web address."
            try:
                async with self._get_session().get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status != 200:
                        return None, None, f"The link returned status {r.status}."
                    length = r.headers.get("Content-Length")
                    if length and length.isdigit() and int(length) > MAX_IMAGE_BYTES:
                        return None, None, "That image is larger than 8MB."
                    data = await r.content.read(MAX_IMAGE_BYTES + 1)
            except (aiohttp.ClientError, asyncio.TimeoutError):
                return None, None, "Couldn't download that link."
            if len(data) > MAX_IMAGE_BYTES:
                return None, None, "That image is larger than 8MB."
            source = url
        else:
            return None, None, "Provide an image URL or attach an image under 8MB."
        if _image_type(data) is None:
            return None, None, "That file isn't a PNG, JPEG, GIF or WebP image."
        return data, source, ""

    async def _apply_image(self, ctx: commands.Context, field: str, config_key: str, url: str | None, label: str, failure_hint: str):
        e = emoji_manager.get
        data, source, problem = await self._resolve_image(ctx, url)
        if data is None:
            return await ctx.send(view=error_layout("Image Problem", problem))
        mime = _image_type(data)
        data_uri = f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
        ok, err = await self._patch_member(ctx.guild.id, {field: data_uri})
        if not ok:
            return await ctx.send(view=error_layout(f"Couldn't Update {label}", f"{failure_hint}\n\n-# Discord said: {_short(err)}"))
        cfg: dict = await guild_settings.get(ctx.guild.id, "bot_identity", {})
        cfg[config_key] = source
        await guild_settings.set(ctx.guild.id, "bot_identity", cfg)
        await ctx.send(view=success_layout(f"{e('check')} {label} Updated", f"My server-specific {label.lower()} has been updated."))

    @commands.group(name="nbot", aliases=["nexus"], invoke_without_command=True,
                    help="View this server's custom bot identity (Premium only).")
    @premium_only()
    @commands.guild_only()
    async def identity_group(self, ctx: commands.Context):
        e = emoji_manager.get
        cfg: dict = await guild_settings.get(ctx.guild.id, "bot_identity", {})
        body = (
            f"**Nickname:** `{ctx.guild.me.display_name}`\n"
            f"**Custom Bio:** {cfg.get('bio', 'Not Set')}\n"
            f"**Guild Avatar:** {e('check') + ' Set' if ctx.guild.me.guild_avatar else e('cross') + ' Default'}\n"
            f"**Guild Banner:** {e('check') + ' Set' if cfg.get('banner_url') else e('cross') + ' Default'}"
        )
        await ctx.send(view=info_layout("Bot Identity Configuration", body))

    @identity_group.command(name="name", help="Change the bot's nickname in this server.")
    @premium_only()
    @has_guild_permission("manage_guild")
    async def name_cmd(self, ctx: commands.Context, *, name: str):
        e = emoji_manager.get
        if len(name) > 32:
            return await ctx.send(view=error_layout("Name Too Long", "Name must be 32 characters or fewer."))
        ok, err = await self._patch_member(ctx.guild.id, {"nick": name})
        if not ok:
            return await ctx.send(view=error_layout("Couldn't Update Nickname", f"Make sure I have the **Change Nickname** permission.\n\n-# Discord said: {_short(err)}"))
        cfg: dict = await guild_settings.get(ctx.guild.id, "bot_identity", {})
        cfg["nickname"] = name
        await guild_settings.set(ctx.guild.id, "bot_identity", cfg)
        await ctx.send(view=success_layout(f"{e('check')} Nickname Updated", f"My nickname is now **{discord.utils.escape_markdown(name)}**."))

    @identity_group.command(name="bio", help="Change the bot's About Me in this server.")
    @premium_only()
    @has_guild_permission("manage_guild")
    async def bio_cmd(self, ctx: commands.Context, *, bio: str):
        e = emoji_manager.get
        if len(bio) > 190:
            return await ctx.send(view=error_layout("Bio Too Long", "Bio must be 190 characters or fewer."))
        ok, err = await self._patch_member(ctx.guild.id, {"bio": bio})
        if not ok:
            return await ctx.send(view=error_layout("Couldn't Update Bio", f"-# Discord said: {_short(err)}"))
        cfg: dict = await guild_settings.get(ctx.guild.id, "bot_identity", {})
        cfg["bio"] = bio
        await guild_settings.set(ctx.guild.id, "bot_identity", cfg)
        await ctx.send(view=success_layout(f"{e('check')} Bio Updated", "My server-specific About Me has been updated."))

    @identity_group.command(name="avatar", help="Change the bot's avatar in this server.")
    @premium_only()
    @has_guild_permission("manage_guild")
    async def avatar_cmd(self, ctx: commands.Context, url: str = None):
        await self._apply_image(ctx, "avatar", "avatar_url", url, "Avatar", "Discord may have rejected the image format or size.")

    @identity_group.command(name="banner", help="Change the bot's profile banner in this server.")
    @premium_only()
    @has_guild_permission("manage_guild")
    async def banner_cmd(self, ctx: commands.Context, url: str = None):
        await self._apply_image(ctx, "banner", "banner_url", url, "Banner", "This may need a higher server boost level.")

    @identity_group.command(name="reset", help="Revert all identity customizations back to default.")
    @premium_only()
    @has_guild_permission("manage_guild")
    async def reset_cmd(self, ctx: commands.Context):
        e = emoji_manager.get
        cfg: dict = await guild_settings.get(ctx.guild.id, "bot_identity", {})
        cleared, failed = [], []
        for field in ("nick", "avatar", "banner", "bio"):
            ok, err = await self._patch_member(ctx.guild.id, {field: None})
            (cleared if ok else failed).append(field if ok else f"{field} ({_short(err)[:80]})")
            if ok:
                cfg.pop({"nick": "nickname", "avatar": "avatar_url", "banner": "banner_url", "bio": "bio"}[field], None)
        await guild_settings.set(ctx.guild.id, "bot_identity", cfg)
        if failed:
            return await ctx.send(view=error_layout(
                "Partly Reset", f"**Reset:** {', '.join(cleared) or 'nothing'}\n**Failed:** {', '.join(failed)}",
            ))
        await ctx.send(view=success_layout(f"{e('check')} Identity Reset", "My server identity has been reset to default."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Customization(bot))
