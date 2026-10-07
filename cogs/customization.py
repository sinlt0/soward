import base64

import aiohttp
import discord
from discord.ext import commands

from utils import embeds, guild_settings
from utils.checks import has_guild_permission, premium_only
import config

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

    async def _to_data_uri(self, data: bytes, content_type: str = "image/png") -> str:
        b64 = base64.b64encode(data).decode("utf-8")
        return f"data:{content_type};base64,{b64}"

    async def _patch_member(self, guild_id: int, payload: dict) -> tuple[bool, str]:
        url = f"https://discord.com/api/v10/guilds/{guild_id}/members/@me"
        headers = {
            "Authorization": f"Bot {self.bot.http.token}",
            "Content-Type": "application/json",
        }
        session = self._get_session()
        async with session.patch(url, json=payload, headers=headers) as resp:
            if resp.status == 200:
                return True, ""
            text = await resp.text()
            return False, text

    async def _resolve_image_bytes(self, ctx: commands.Context, url: str | None) -> tuple[bytes | None, str | None]:
        if ctx.message.attachments:
            attachment = ctx.message.attachments[0]
            if attachment.size > 8 * 1024 * 1024:
                return None, None
            return await attachment.read(), attachment.url
        if url:
            session = self._get_session()
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    if r.status == 200:
                        content_length = r.headers.get("Content-Length")
                        if content_length and int(content_length) > 8 * 1024 * 1024:
                            return None, None
                        return await r.read(), url
            except (aiohttp.ClientError, TimeoutError):
                return None, None
        return None, None

    @commands.group(name="nbot", aliases=["nexus"], invoke_without_command=True,
                    help="View this server's custom bot identity (Premium only).")
    @premium_only()
    @commands.guild_only()
    async def identity_group(self, ctx: commands.Context):
        cfg: dict = await guild_settings.get(ctx.guild.id, "bot_identity", {})
        embed = embeds.neutral(
            title="Bot Identity Configuration",
            description=(
                f"**Nickname:** `{ctx.guild.me.display_name}`\n"
                f"**Custom Bio:** {cfg.get('bio', 'Not Set')}\n"
                f"**Guild Avatar:** {'Set ✅' if ctx.guild.me.guild_avatar else 'Default ❌'}\n"
                f"**Guild Banner:** {'Set ✅' if cfg.get('banner_url') else 'Default ❌'}"
            ),
        )
        await ctx.reply(embed=embed, mention_author=False)

    @identity_group.command(name="name", help="Change the bot's nickname in this server.")
    @premium_only()
    @has_guild_permission("manage_guild")
    async def name_cmd(self, ctx: commands.Context, *, name: str):
        if len(name) > 32:
            return await ctx.reply(embed=embeds.error(description="Name must be 32 characters or fewer."), mention_author=False)

        ok, err = await self._patch_member(ctx.guild.id, {"nick": name})
        if not ok:
            return await ctx.reply(embed=embeds.error(description="Failed to update nickname. Make sure I have the **Change Nickname** permission."), mention_author=False)

        cfg: dict = await guild_settings.get(ctx.guild.id, "bot_identity", {})
        cfg["nickname"] = name
        await guild_settings.set(ctx.guild.id, "bot_identity", cfg)
        await ctx.reply(embed=embeds.success(description=f"My nickname has been updated to **{name}**."), mention_author=False)

    @identity_group.command(name="bio", help="Change the bot's About Me in this server.")
    @premium_only()
    @has_guild_permission("manage_guild")
    async def bio_cmd(self, ctx: commands.Context, *, bio: str):
        if len(bio) > 190:
            return await ctx.reply(embed=embeds.error(description="Bio must be 190 characters or fewer."), mention_author=False)

        ok, err = await self._patch_member(ctx.guild.id, {"bio": bio})
        if not ok:
            return await ctx.reply(embed=embeds.error(description="Failed to update bio."), mention_author=False)

        cfg: dict = await guild_settings.get(ctx.guild.id, "bot_identity", {})
        cfg["bio"] = bio
        await guild_settings.set(ctx.guild.id, "bot_identity", cfg)
        await ctx.reply(embed=embeds.success(description="My server-specific About Me has been updated."), mention_author=False)

    @identity_group.command(name="avatar", help="Change the bot's avatar in this server.")
    @premium_only()
    @has_guild_permission("manage_guild")
    async def avatar_cmd(self, ctx: commands.Context, url: str = None):
        image_data, resolved_url = await self._resolve_image_bytes(ctx, url)
        if not image_data:
            return await ctx.reply(embed=embeds.error(description="Provide an image URL or attach an image under 8MB."), mention_author=False)

        data_uri = await self._to_data_uri(image_data)
        ok, err = await self._patch_member(ctx.guild.id, {"avatar": data_uri})
        if not ok:
            return await ctx.reply(embed=embeds.error(description="Failed to update avatar. Discord may have rejected the image format or size."), mention_author=False)

        cfg: dict = await guild_settings.get(ctx.guild.id, "bot_identity", {})
        cfg["avatar_url"] = resolved_url
        await guild_settings.set(ctx.guild.id, "bot_identity", cfg)
        await ctx.reply(embed=embeds.success(description="My server-specific avatar has been updated."), mention_author=False)

    @identity_group.command(name="banner", help="Change the bot's profile banner in this server.")
    @premium_only()
    @has_guild_permission("manage_guild")
    async def banner_cmd(self, ctx: commands.Context, url: str = None):
        image_data, resolved_url = await self._resolve_image_bytes(ctx, url)
        if not image_data:
            return await ctx.reply(embed=embeds.error(description="Provide an image URL or attach an image under 8MB."), mention_author=False)

        data_uri = await self._to_data_uri(image_data)
        ok, err = await self._patch_member(ctx.guild.id, {"banner": data_uri})
        if not ok:
            return await ctx.reply(embed=embeds.error(description="Failed to update banner. This may require the server to have sufficient boost level."), mention_author=False)

        cfg: dict = await guild_settings.get(ctx.guild.id, "bot_identity", {})
        cfg["banner_url"] = resolved_url
        await guild_settings.set(ctx.guild.id, "bot_identity", cfg)
        await ctx.reply(embed=embeds.success(description="My server-specific banner has been updated."), mention_author=False)

    @identity_group.command(name="reset", help="Revert all identity customizations back to default.")
    @premium_only()
    @has_guild_permission("manage_guild")
    async def reset_cmd(self, ctx: commands.Context):
        ok, err = await self._patch_member(ctx.guild.id, {"nick": None, "avatar": None, "banner": None, "bio": None})
        if not ok:
            return await ctx.reply(embed=embeds.error(description="Failed to reset identity."), mention_author=False)

        await guild_settings.set(ctx.guild.id, "bot_identity", {})
        await ctx.reply(embed=embeds.success(description="My server identity has been reset to default."), mention_author=False)

async def setup(bot: commands.Bot):
    await bot.add_cog(Customization(bot))
