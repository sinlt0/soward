import time
from datetime import datetime

import discord
from discord.ext import commands, tasks

import config
from utils import emoji_manager, reminders as store
from utils.components import error_layout, info_layout, success_layout

NO_PINGS = discord.AllowedMentions.none()


def when_text(due: float) -> str:
    return f"<t:{int(due)}:f> (<t:{int(due)}:R>)"


def every_text(seconds: int) -> str:
    if seconds % 604800 == 0:
        return f"{seconds // 604800}w"
    if seconds % 86400 == 0:
        return f"{seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"{seconds // 3600}h"
    return f"{seconds // 60}m"


class Reminders(commands.Cog):
    category = "Utility"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.deliver.start()

    async def cog_unload(self):
        self.deliver.cancel()

    @tasks.loop(seconds=config.REMINDER_CHECK_SECONDS)
    async def deliver(self):
        now = time.time()
        for reminder in await store.due(now):
            await store.advance(reminder, now)
            try:
                await self.send_reminder(reminder)
            except Exception:
                continue

    @deliver.before_loop
    async def before_deliver(self):
        await self.bot.wait_until_ready()

    async def send_reminder(self, reminder: dict):
        e = emoji_manager.get
        text = reminder["message"] or "Time is up."
        late = time.time() - reminder["due_at"] > 600
        body = f"{text}\n\n-# Set <t:{int(reminder['created_at'])}:R>" + (" · repeats" if reminder["repeat_seconds"] else "") + (" · this one is late, the bot was offline" if late else "")
        view = info_layout(f"{e('calendar')} Reminder", body)
        user = self.bot.get_user(reminder["user_id"])
        if user is None:
            try:
                user = await self.bot.fetch_user(reminder["user_id"])
            except discord.HTTPException:
                return
        try:
            await user.send(view=view)
            return
        except discord.HTTPException:
            pass
        channel = self.bot.get_channel(reminder["channel_id"]) if reminder["channel_id"] else None
        if channel is not None:
            try:
                await channel.send(view=info_layout(f"{e('calendar')} Reminder for {user.mention}", body), allowed_mentions=discord.AllowedMentions(users=[user]))
            except discord.HTTPException:
                pass

    async def create(self, ctx: commands.Context, due: float, message: str, repeat: int = 0):
        e = emoji_manager.get
        now = time.time()
        if await store.count(ctx.author.id) >= config.REMINDER_LIMIT:
            return await ctx.send(view=error_layout("Too many reminders", f"You can have up to {config.REMINDER_LIMIT}. Remove some with `remind delete <id>`."))
        if due - now < config.REMINDER_MIN_SECONDS:
            return await ctx.send(view=error_layout("Too soon", f"Reminders must be at least {config.REMINDER_MIN_SECONDS} seconds away."))
        if due - now > config.REMINDER_MAX_DAYS * 86400:
            return await ctx.send(view=error_layout("Too far away", f"Reminders can be up to {config.REMINDER_MAX_DAYS} days ahead."))
        if not message:
            return await ctx.send(view=error_layout("What should I remind you of?", "Add a message after the time, for example `remind 2h call mum`."))
        guild_id = ctx.guild.id if ctx.guild else 0
        reminder = await store.add(ctx.author.id, guild_id, ctx.channel.id, message, due, repeat)
        extra = f"\nRepeats every **{every_text(repeat)}**." if repeat else ""
        await ctx.send(view=success_layout(f"{e('check')} Reminder set", f"{when_text(due)}\n{reminder['message']}{extra}\n-# ID `{reminder['reminder_id']}` · Delete it with `remind delete {reminder['reminder_id']}`"), allowed_mentions=NO_PINGS)

    @commands.group(name="remind", aliases=["remindme", "reminder"], invoke_without_command=True, help="Set a reminder. Usage: remind <time> <message>, for example remind 2h call mum or remind tomorrow 8pm exam")
    async def remind(self, ctx: commands.Context, *, text: str = ""):
        if not text.strip():
            return await ctx.send(view=info_layout("Reminders", (
                "`remind 2h call mum`\n`remind in 1h30m stretch`\n`remind tomorrow 8pm exam`\n`remind friday 5:30pm | pay rent`\n"
                "`remind every 1d drink water`\n`remind list` · `remind delete <id>` · `remind clear`\n`remind tz Asia/Dhaka` sets your timezone for clock times")))
        name, tz = await store.get_timezone(ctx.author.id)
        due, message = store.split_when(text, time.time(), tz)
        if due is None:
            return await ctx.send(view=error_layout("I could not read the time", "Try `remind 2h call mum`, `remind tomorrow 8pm exam` or `remind friday 5:30pm | pay rent`. Clock times use your timezone (`remind tz`)."))
        await self.create(ctx, due, message)

    @remind.command(name="every", aliases=["repeat"], help="Repeat a reminder. Usage: remind every <interval> <message>")
    async def remind_every(self, ctx: commands.Context, *, text: str):
        seconds, message = store.split_interval(text)
        if seconds is None:
            return await ctx.send(view=error_layout("Invalid interval", "Use something like `remind every 1d drink water` or `remind every 12h stretch`."))
        if seconds < config.REMINDER_MIN_REPEAT_SECONDS:
            return await ctx.send(view=error_layout("Too often", "Repeating reminders must be at least 1 hour apart."))
        await self.create(ctx, time.time() + seconds, message, seconds)

    @remind.command(name="list", aliases=["all", "show"], help="Show your reminders.")
    async def remind_list(self, ctx: commands.Context):
        e = emoji_manager.get
        rows = await store.of(ctx.author.id)
        if not rows:
            return await ctx.send(view=info_layout(f"{e('calendar')} Your reminders", "You have no reminders. Try `remind 2h call mum`."))
        lines = []
        for row in rows:
            repeat = f" · every {every_text(row['repeat_seconds'])}" if row["repeat_seconds"] else ""
            text = row["message"] if len(row["message"]) <= 60 else row["message"][:57] + "..."
            lines.append(f"`{row['reminder_id']}` · <t:{int(row['due_at'])}:R> · {text}{repeat}")
        await ctx.send(view=info_layout(f"{e('calendar')} Your reminders", "\n".join(lines)), allowed_mentions=NO_PINGS)

    @remind.command(name="delete", aliases=["remove", "del", "cancel"], help="Delete a reminder. Usage: remind delete <id>")
    async def remind_delete(self, ctx: commands.Context, reminder_id: str):
        if not await store.remove(ctx.author.id, reminder_id):
            return await ctx.send(view=error_layout("Not found", "You have no reminder with that ID. See `remind list`."))
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Deleted", "That reminder was removed."))

    @remind.command(name="clear", help="Delete all your reminders.")
    async def remind_clear(self, ctx: commands.Context):
        removed = await store.clear(ctx.author.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Cleared", f"Removed **{removed}** reminder(s)."))

    @remind.command(name="tz", aliases=["timezone"], help="Set your timezone for clock times. Usage: remind tz <zone>, for example Asia/Dhaka or UTC+6")
    async def remind_tz(self, ctx: commands.Context, zone: str = ""):
        if not zone:
            name, tz = await store.get_timezone(ctx.author.id)
            now = datetime.now(tz).strftime("%a %H:%M")
            return await ctx.send(view=info_layout("Your timezone", f"**{name}** · it is {now} for you.\nChange it with `remind tz Asia/Dhaka` or `remind tz UTC+6`."))
        if not await store.set_timezone(ctx.author.id, zone):
            return await ctx.send(view=error_layout("Unknown timezone", "Use a name like `Asia/Dhaka` or `Europe/London`, or an offset like `UTC+6`."))
        name, tz = await store.get_timezone(ctx.author.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Timezone set", f"Your timezone is **{name}**. It is {datetime.now(tz).strftime('%a %H:%M')} for you."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Reminders(bot))
