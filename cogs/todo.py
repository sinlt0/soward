import discord
from discord.ext import commands

import config
from utils import emoji_manager, todos
from utils.components import error_layout, info_layout, success_layout

NO_PINGS = discord.AllowedMentions.none()


def render(listing: list[dict]) -> str:
    lines = []
    for number, item in enumerate(listing, 1):
        mark = "`[x]`" if item["done"] else "`[ ]`"
        text = f"~~{item['text']}~~" if item["done"] else item["text"]
        lines.append(f"`{number}.` {mark} {text}")
    return "\n".join(lines)


class Todo(commands.Cog):
    category = "Utility"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def show(self, ctx: commands.Context):
        e = emoji_manager.get
        listing = await todos.items(ctx.author.id)
        if not listing:
            return await ctx.send(view=info_layout(f"{e('case')} Your to-do list", "It is empty. Add something with `todo add buy milk`."))
        done = sum(1 for item in listing if item["done"])
        body = render(listing) + f"\n\n-# {done}/{len(listing)} done · `todo done <n>` · `todo add <text>` · `todo remove <n>`"
        await ctx.send(view=info_layout(f"{e('case')} Your to-do list", body), allowed_mentions=NO_PINGS)

    @commands.group(name="todo", aliases=["todos", "tasks"], invoke_without_command=True, help="Show your to-do list.")
    async def todo(self, ctx: commands.Context):
        await self.show(ctx)

    @todo.command(name="add", aliases=["new", "+"], help="Add an item. Usage: todo add <text>")
    async def todo_add(self, ctx: commands.Context, *, text: str):
        if not todos.clean(text):
            return await ctx.send(view=error_layout("Empty item", "Write what you need to do."))
        item = await todos.add(ctx.author.id, text)
        if item is None:
            return await ctx.send(view=error_layout("List is full", f"You can keep up to {config.TODO_LIMIT} items. Remove some with `todo remove <n>` or `todo clear`."))
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Added", item["text"]), allowed_mentions=NO_PINGS)

    async def pick(self, ctx: commands.Context, number: int):
        item = await todos.at(ctx.author.id, number)
        if item is None:
            await ctx.send(view=error_layout("Not found", "There is no item with that number. See `todo`."))
        return item

    @todo.command(name="done", aliases=["check", "finish", "complete"], help="Mark an item done. Usage: todo done <n>")
    async def todo_done(self, ctx: commands.Context, number: int):
        item = await self.pick(ctx, number)
        if item is None:
            return
        await todos.set_done(item["todo_id"], True)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Done", f"~~{item['text']}~~"), allowed_mentions=NO_PINGS)

    @todo.command(name="undo", aliases=["uncheck", "reopen"], help="Mark an item not done. Usage: todo undo <n>")
    async def todo_undo(self, ctx: commands.Context, number: int):
        item = await self.pick(ctx, number)
        if item is None:
            return
        await todos.set_done(item["todo_id"], False)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Reopened", item["text"]), allowed_mentions=NO_PINGS)

    @todo.command(name="edit", help="Change an item. Usage: todo edit <n> <text>")
    async def todo_edit(self, ctx: commands.Context, number: int, *, text: str):
        item = await self.pick(ctx, number)
        if item is None:
            return
        if not todos.clean(text):
            return await ctx.send(view=error_layout("Empty item", "Write the new text."))
        await todos.edit(item["todo_id"], text)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Updated", todos.clean(text)), allowed_mentions=NO_PINGS)

    @todo.command(name="remove", aliases=["delete", "del", "rm"], help="Remove an item. Usage: todo remove <n>")
    async def todo_remove(self, ctx: commands.Context, number: int):
        item = await self.pick(ctx, number)
        if item is None:
            return
        await todos.remove(item["todo_id"])
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Removed", item["text"]), allowed_mentions=NO_PINGS)

    @todo.command(name="clear", help="Remove all finished items.")
    async def todo_clear(self, ctx: commands.Context):
        removed = await todos.clear_done(ctx.author.id)
        await ctx.send(view=success_layout(f"{emoji_manager.get('check')} Cleared", f"Removed **{removed}** finished item(s)."))


async def setup(bot: commands.Bot):
    await bot.add_cog(Todo(bot))
