import io
import json
import time
from typing import Optional

import discord
from discord.ext import commands

import config
from utils import db, emoji_manager, security_cmds, template_presets, tickets
from utils import server_templates as engine
from utils.colors import ERROR, NEUTRAL
from utils.components import ConfirmLayout, error_layout, info_layout, success_layout
from utils.security_access import security_owner

MAX_PER_USER = 5
VISIBILITY = ("private", "unlisted", "public")
PART_ALIASES = {"roles": "roles", "channels": "channels", "settings": "settings", "content": "content", "messages": "content", "all": "all", "clean": "clean", "wipe": "clean", "reset": "clean", "fullclean": "full", "full": "full", "nuke": "full"}


class ServerTemplates(commands.Cog):
    category = "Server"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.running: set[int] = set()

    async def _row(self, code: str) -> Optional[dict]:
        row = await db.raw_fetchone("SELECT * FROM server_templates WHERE code=?", (code.strip().upper(),))
        return dict(row) if row else None

    async def _resolve(self, ctx: commands.Context, ref: str) -> tuple[Optional[dict], Optional[dict], str]:
        preset = template_presets.get(ref)
        if preset:
            return preset, {"code": ref.lower(), "name": preset["meta"]["name"], "owner_id": 0, "visibility": "public", "uses": 0, "description": preset["meta"]["summary"]}, "builtin"
        if engine.is_code(ref):
            row = await self._row(ref)
            if row and (row["visibility"] != "private" or row["owner_id"] == ctx.author.id or ctx.author.id in config.ALL_PRIVILEGED_IDS):
                try:
                    return engine.validate(json.loads(row["data"])), row, "saved"
                except (ValueError, json.JSONDecodeError):
                    return None, row, "damaged"
        return None, None, "missing"

    async def _not_found(self, ctx: commands.Context, state: str):
        if state == "damaged":
            return await ctx.send(view=error_layout("Template damaged", "This template could not be read."))
        names = ", ".join(f"`{i}`" for i in template_presets.ids())
        await ctx.send(view=error_layout("Template not found", f"Use a preset name ({names}) or an 8 character template code. Private templates only work for their owner."))

    @commands.group(name="template", aliases=["servertemplate", "tpl"], invoke_without_command=True, help="Server presets and templates. Browse, preview, apply and publish.")
    @commands.guild_only()
    async def template_group(self, ctx: commands.Context):
        e = emoji_manager.get
        body = (
            "Build a whole server in one command, or save your own server as a template.\n\n"
            "`template presets` Built-in presets\n"
            "`template browse` Community published templates\n"
            "`template preview <preset or code>` See what it contains\n"
            "`template apply <preset or code> [parts]` Set up this server *(owner / Extra Owner)*\n"
            "`template publish <name>` Save this server as a template *(owner / Extra Owner)*\n"
            "`template list` Your templates\n"
            "`template update | delete | visibility <code>`\n\n"
            "Parts for apply: `roles`, `channels`, `settings`, `content`. Leave them out for everything. Add `clean` to also delete old channels and roles, or `fullclean` to wipe and rebuild the whole server."
        )
        await ctx.send(view=info_layout(f"{e('info')} Server templates", body))

    @template_group.command(name="presets", aliases=["builtin"], help="List Soward's built-in presets.")
    async def presets(self, ctx: commands.Context):
        lines = []
        for meta in template_presets.all_meta():
            data = template_presets.get(meta["id"])
            c = engine.summary_counts(data)
            star = "⭐ " if meta.get("premium") else ""
            lines.append(f"{meta['emoji']} {star}**{meta['name']}** (`{meta['id']}`)\n{meta['summary']}\n-# {c['roles']} roles, {c['channels']} channels, {c['embeds']} embeds, {c['panels']} self-role and ticket panels")
        lines.append("Preview one with `template preview <id>`. Apply with `template apply <id>`.")
        await ctx.send(view=info_layout("Built-in presets", "\n\n".join(lines)))

    @template_group.command(name="browse", aliases=["public", "search"], help="Browse templates other servers published.")
    async def browse(self, ctx: commands.Context, *, query: Optional[str] = None):
        sql = "SELECT code, name, description, uses FROM server_templates WHERE visibility='public'"
        params: tuple = ()
        if query:
            sql += " AND (name LIKE ? OR description LIKE ?)"
            params = (f"%{query}%", f"%{query}%")
        rows = await db.raw_fetch(sql + " ORDER BY uses DESC, updated_at DESC LIMIT 10", params)
        if not rows:
            return await ctx.send(view=info_layout("Public templates", "Nothing published yet. Use `template publish` and `template visibility <code> public` to share yours."))
        lines = [f"**{r['name']}** `{r['code']}` ({r['uses']} uses)\n{(r['description'] or 'No description')[:120]}" for r in rows]
        await ctx.send(view=info_layout("Public templates", "\n\n".join(lines)))

    @template_group.command(name="preview", aliases=["show"], help="See what a template contains. Usage: template preview <preset or code>")
    async def preview(self, ctx: commands.Context, ref: str):
        data, row, state = await self._resolve(ctx, ref)
        if data is None:
            return await self._not_found(ctx, state)
        c = engine.summary_counts(data)
        header = f"**{row['name']}**\n{row.get('description') or ''}\n\n{c['roles']} roles, {c['categories']} categories, {c['channels']} channels, {c['settings']} saved settings, {c['embeds']} embeds, {c['panels']} panels, {c['messages']} messages"
        tree = []
        for cat in data["categories"]:
            names = ", ".join(ch["name"] for ch in cat["channels"])
            tree.append(f"**{cat['name'] or 'No category'}**: {names}")
        role_line = ", ".join(r["name"] for r in data["roles"])
        text = f"{header}\n\n**Roles**\n{role_line}\n\n**Channels**\n" + "\n".join(tree)
        await security_cmds.chunked(ctx, "Template preview", text.split("\n"))

    @template_group.command(name="info", help="Details about a saved template. Usage: template info <code>")
    async def info(self, ctx: commands.Context, code: str):
        data, row, state = await self._resolve(ctx, code)
        if data is None or state == "builtin":
            return await self._not_found(ctx, state)
        body = (
            f"**{row['name']}** `{row['code']}`\n{row.get('description') or 'No description'}\n\n"
            f"Visibility: `{row['visibility']}`\nUses: {row['uses']}\nCreated by: <@{row['owner_id']}>\n"
            f"Last saved: <t:{int(row['updated_at'])}:R>"
        )
        await ctx.send(view=info_layout("Template info", body))

    @template_group.command(name="list", aliases=["mine"], help="Templates you published.")
    async def list_mine(self, ctx: commands.Context):
        rows = await db.raw_fetch("SELECT code, name, visibility, uses FROM server_templates WHERE owner_id=? ORDER BY updated_at DESC", (ctx.author.id,))
        if not rows:
            return await ctx.send(view=info_layout("Your templates", "You have no templates. Server owners can save one with `template publish <name>`."))
        lines = [f"**{r['name']}** `{r['code']}` {r['visibility']}, {r['uses']} uses" for r in rows]
        await ctx.send(view=info_layout("Your templates", "\n".join(lines)))

    @template_group.command(name="apply", aliases=["use", "load"], help="Set up this server from a template. Usage: template apply <preset or code> [roles channels settings content] [clean]")
    @security_owner()
    async def apply(self, ctx: commands.Context, ref: str, *parts: str):
        e = emoji_manager.get
        data, row, state = await self._resolve(ctx, ref)
        if data is None:
            return await self._not_found(ctx, state)
        if state == "builtin" and (data.get("meta") or {}).get("premium") and not await tickets.is_premium(ctx.guild.id) and ctx.author.id not in config.ALL_PRIVILEGED_IDS:
            return await ctx.send(view=error_layout("Premium preset", f"**{row['name']}** uses more than the free limits (seven ticket panels, 100+ roles and 14 self role panels), so it needs Soward Premium on this server. You can still preview it with `template preview {ref.lower()}`."))
        chosen = set()
        wipe = False
        full = False
        for part in parts:
            key = PART_ALIASES.get(part.lower())
            if key is None:
                return await ctx.send(view=error_layout("Unknown part", "Use `roles`, `channels`, `settings`, `content`, `all`, `clean` or `fullclean`."))
            if key == "full":
                wipe = full = True
            elif key == "clean":
                wipe = True
            else:
                chosen.update(engine.PARTS if key == "all" else {key})
        chosen = chosen or set(engine.PARTS)
        if full:
            if ctx.author.id != ctx.guild.owner_id and ctx.author.id not in config.ALL_PRIVILEGED_IDS:
                return await ctx.send(view=error_layout("Owner only", "Only the server owner can run a full clean."))
            chosen = set(engine.PARTS)
        guild = ctx.guild
        if guild.id in self.running:
            return await ctx.send(view=error_layout("Already running", "A template is already being applied here."))
        me = guild.me.guild_permissions
        missing = [n for n, ok in (("Manage Roles", me.manage_roles), ("Manage Channels", me.manage_channels), ("Manage Webhooks", me.manage_webhooks)) if not ok]
        if missing:
            return await ctx.send(view=error_layout("Missing permissions", "Soward needs: " + ", ".join(missing) + "."))
        foreign = state == "saved" and row["owner_id"] != ctx.author.id
        c = engine.summary_counts(data)
        body = (
            f"**{row['name']}** will add up to {c['roles']} roles, {c['categories']} categories, {c['channels']} channels, "
            f"{c['embeds']} embeds, {c['panels']} panels and {c['messages']} messages.\n"
            f"Parts: {', '.join(sorted(chosen))}.\n\n"
            "Roles and channels with the same name are reused. Settings in the template replace your current values."
        )
        if full:
            bots, old_channels, old_roles = engine.predict_full(guild)
            body += (
                f"\n\n**FULL CLEAN.** Soward will kick **{bots} bots**, delete **all {old_channels} channels and categories** and **{old_roles} roles** "
                "(including the quarantine role), then rebuild everything from the template with a fresh Quarantined role. "
                "Every member loses their roles and must verify again. Messages in deleted channels, open tickets, log channels and saved panels are lost. A backup is taken first (`backup restore <id>`).\n"
                "Kept: Soward, the rules and updates channels Discord requires, roles above Soward and integration roles."
            )
        elif wipe:
            old_channels, old_roles = await engine.predict_clean(guild, data, chosen)
            body += (
                f"\n\n**Clean mode is on.** After building, Soward deletes about **{old_channels} channels and categories** and **{old_roles} roles** "
                "that are not in the template. This cannot be undone, but a backup is taken first (`backup restore <id>`).\n"
                "Kept: log channels, open tickets, the rules and updates channels, Soward's quarantine role, bot roles and roles above Soward."
            )
        else:
            body += "\nNothing is deleted. Add `clean` to remove old channels and roles that are not in the template."
        if foreign:
            body += "\nThis is another server's template, so dangerous permissions are removed and lock and bypass settings are skipped."
        confirm = ConfirmLayout(f"{e('shield')} Apply template", body, author_id=ctx.author.id, color=ERROR if wipe else NEUTRAL, timeout=120.0)
        message = await ctx.send(view=confirm)
        await confirm.wait()
        if not confirm.value:
            return await message.edit(view=error_layout("Cancelled", "Nothing was changed."))
        self.running.add(guild.id)
        backup_line = None
        if wipe:
            lockdown = self.bot.get_cog("Lockdown")
            if lockdown is None:
                self.running.discard(guild.id)
                return await message.edit(view=error_layout("Backup unavailable", "Clean mode needs the backup system. Nothing was changed."))
            try:
                backup_id = await lockdown.create_backup(guild, "before template clean", ctx.author.id)
            except Exception as exc:
                self.running.discard(guild.id)
                return await message.edit(view=error_layout("Backup failed", f"Nothing was changed: {str(exc)[:150]}"))
            backup_line = f"Backup `{backup_id}` was taken first. Restore with `backup restore {backup_id}`."
        await message.edit(view=info_layout(f"{e('shield')} Applying template", "Building your server. Large templates take a few minutes."))
        try:
            pre = engine.Report()
            if full:
                await engine.full_clean(guild, pre, ctx.channel.id)
            report = await engine.apply(self.bot, guild, data, actor_id=ctx.author.id, parts=chosen, foreign=foreign)
            report.merge(pre)
            if wipe and not full:
                await engine.clean(guild, report, chosen, ctx.channel.id)
        except Exception as exc:
            return await message.edit(view=error_layout("Template failed", f"Stopped part-way: {str(exc)[:200]}"))
        finally:
            self.running.discard(guild.id)
        if state == "saved":
            await db.raw_execute("UPDATE server_templates SET uses=uses+1 WHERE code=?", (row["code"],))
        k = report.counts
        lines = [
            f"Roles created: **{k['roles']}** ({k['roles_reused']} reused)",
            f"Channels created: **{k['channels']}** ({k['channels_reused']} reused)",
            f"Settings saved: **{k['settings']}**",
            f"Embeds: **{k['embeds']}**, panels: **{k['panels']}**, messages: **{k['messages']}**",
        ] + report.lines
        if wipe:
            if full:
                lines.append(f"Kicked **{k['kicked_bots']}** bots")
            lines.append(f"Deleted: **{k['deleted_channels']}** channels and categories, **{k['deleted_roles']}** roles")
            lines.append(backup_line)
        if report.failed:
            lines.append("\n**Skipped**\n" + "\n".join(report.failed[:10]))
        result = success_layout("Template applied", "\n".join(lines))
        removing = wipe and "channels" in chosen and ctx.channel.id not in set(report.cmap.values()) and ctx.channel.id not in await engine._protected_channels(guild)
        if not removing:
            return await message.edit(view=result)
        target = next((guild.get_channel(i) for i in report.cmap.values() if isinstance(guild.get_channel(i), discord.TextChannel)
                       and guild.get_channel(i).permissions_for(guild.me).send_messages), None)
        old = ctx.channel
        if target is None:
            return await message.edit(view=result)
        await target.send(view=result)
        try:
            await old.delete(reason="Soward server template clean")
        except discord.HTTPException:
            await message.edit(view=result)

    @template_group.command(name="publish", aliases=["save", "create"], help="Save this server as a template. Usage: template publish <name>")
    @security_owner()
    async def publish(self, ctx: commands.Context, *, name: str):
        name = name.strip()[:60]
        count = await db.raw_fetchone("SELECT COUNT(*) AS n FROM server_templates WHERE owner_id=?", (ctx.author.id,))
        if count["n"] >= MAX_PER_USER:
            return await ctx.send(view=error_layout("Limit reached", f"You can keep {MAX_PER_USER} templates. Delete one first."))
        async with ctx.typing():
            try:
                data = await engine.snapshot(ctx.guild)
            except ValueError as exc:
                return await ctx.send(view=error_layout("Too large", str(exc)))
        now = time.time()
        data["meta"] = {"name": name, "source": ctx.guild.name}
        code = engine.new_code()
        await db.raw_execute(
            "INSERT INTO server_templates (code, name, description, owner_id, source_guild_id, visibility, data, uses, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?, 'private', ?, 0, ?, ?)",
            (code, name, f"Saved from {ctx.guild.name}", ctx.author.id, ctx.guild.id, json.dumps(data), now, now),
        )
        c = engine.summary_counts(data)
        await ctx.send(view=success_layout("Template saved", (
            f"**{name}** `{code}` is saved as **private**.\n{c['roles']} roles, {c['channels']} channels, {c['settings']} settings, {c['embeds']} embeds, {c['panels']} panels.\n\n"
            f"Share it with `template visibility {code} unlisted` (anyone with the code) or `public` (listed in browse).\n"
            "Custom commands, giveaways, alerts, tickets and member data are not saved. Logs, security, leveling, greetings, NSFW and self roles are."
        )))

    @template_group.command(name="update", aliases=["resave"], help="Re-save this server into one of your templates. Usage: template update <code>")
    @security_owner()
    async def update(self, ctx: commands.Context, code: str):
        row = await self._row(code)
        if not row or (row["owner_id"] != ctx.author.id and ctx.author.id not in config.ALL_PRIVILEGED_IDS):
            return await self._not_found(ctx, "missing")
        async with ctx.typing():
            try:
                data = await engine.snapshot(ctx.guild)
            except ValueError as exc:
                return await ctx.send(view=error_layout("Too large", str(exc)))
        data["meta"] = {"name": row["name"], "source": ctx.guild.name}
        await db.raw_execute("UPDATE server_templates SET data=?, source_guild_id=?, updated_at=? WHERE code=?", (json.dumps(data), ctx.guild.id, time.time(), row["code"]))
        await ctx.send(view=success_layout("Template updated", f"**{row['name']}** now matches this server."))

    @template_group.command(name="visibility", aliases=["share"], help="Set who can use a template. Usage: template visibility <code> <private|unlisted|public>")
    async def visibility(self, ctx: commands.Context, code: str, mode: str):
        row = await self._row(code)
        if not row or row["owner_id"] != ctx.author.id:
            return await self._not_found(ctx, "missing")
        mode = mode.lower()
        if mode not in VISIBILITY:
            return await ctx.send(view=error_layout("Invalid", "Choose `private`, `unlisted` or `public`."))
        await db.raw_execute("UPDATE server_templates SET visibility=?, updated_at=? WHERE code=?", (mode, time.time(), row["code"]))
        await ctx.send(view=success_layout("Visibility changed", f"**{row['name']}** is now `{mode}`."))

    @template_group.command(name="describe", help="Set a template description. Usage: template describe <code> <text>")
    async def describe(self, ctx: commands.Context, code: str, *, text: str):
        row = await self._row(code)
        if not row or row["owner_id"] != ctx.author.id:
            return await self._not_found(ctx, "missing")
        await db.raw_execute("UPDATE server_templates SET description=?, updated_at=? WHERE code=?", (text[:300], time.time(), row["code"]))
        await ctx.send(view=success_layout("Description saved", text[:300]))

    @template_group.command(name="export", help="Download a template as JSON. Usage: template export <code>")
    async def export(self, ctx: commands.Context, code: str):
        row = await self._row(code)
        if not row or row["owner_id"] != ctx.author.id:
            return await self._not_found(ctx, "missing")
        await ctx.send(file=discord.File(io.BytesIO(row["data"].encode()), filename=f"template-{row['code']}.json"))

    @template_group.command(name="delete", aliases=["remove"], help="Delete one of your templates. Usage: template delete <code>")
    async def delete(self, ctx: commands.Context, code: str):
        row = await self._row(code)
        if not row or (row["owner_id"] != ctx.author.id and ctx.author.id not in config.ALL_PRIVILEGED_IDS):
            return await self._not_found(ctx, "missing")
        await db.raw_execute("DELETE FROM server_templates WHERE code=?", (row["code"],))
        await ctx.send(view=success_layout("Template deleted", f"**{row['name']}** was removed."))


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerTemplates(bot))
