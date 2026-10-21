from datetime import date, datetime, timezone
from typing import Optional

import discord
from discord.ext import commands

from utils import db, emoji_manager
from utils.components import error_layout, info_layout
from utils.wordle_words import ANSWERS

PLAY_ID = "wordle:play"
MAX_GUESSES = 6
EPOCH = date(2026, 1, 1)
SQUARES = {"g": "🟩", "y": "🟨", "b": "⬛"}


def today_number() -> int:
    return (datetime.now(timezone.utc).date() - EPOCH).days + 1


def answer_for(number: int) -> str:
    return ANSWERS[(number * 37 + 11) % len(ANSWERS)]


def score(guess: str, answer: str) -> str:
    result = ["b"] * 5
    remaining = {}
    for i in range(5):
        if guess[i] == answer[i]:
            result[i] = "g"
        else:
            remaining[answer[i]] = remaining.get(answer[i], 0) + 1
    for i in range(5):
        if result[i] == "g":
            continue
        if remaining.get(guess[i], 0) > 0:
            result[i] = "y"
            remaining[guess[i]] -= 1
    return "".join(result)


def board_text(guesses: list[str], answer: str, reveal_letters: bool = True) -> str:
    lines = []
    for guess in guesses:
        squares = "".join(SQUARES[c] for c in score(guess, answer))
        lines.append(f"{squares}  `{guess.upper()}`" if reveal_letters else squares)
    for _ in range(MAX_GUESSES - len(guesses)):
        lines.append("⬜⬜⬜⬜⬜")
    return "\n".join(lines)


def play_row(label: str = "Guess") -> discord.ui.ActionRow:
    row = discord.ui.ActionRow()
    row.add_item(discord.ui.Button(label=label, emoji="🔤", style=discord.ButtonStyle.primary, custom_id=PLAY_ID))
    return row


def private_view(text: str, color: int, button: bool) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    container = discord.ui.Container(accent_color=color)
    container.add_item(discord.ui.TextDisplay(text))
    if button:
        container.add_item(discord.ui.Separator())
        container.add_item(play_row())
    view.add_item(container)
    return view


class GuessModal(discord.ui.Modal, title="Wordle"):
    word = discord.ui.TextInput(label="Your 5 letter guess", min_length=5, max_length=5)

    def __init__(self, cog: "Wordle"):
        super().__init__(timeout=600)
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.handle_guess(interaction, str(self.word.value).strip().lower())


class Wordle(commands.Cog):
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _game(self, guild_id: int, user_id: int, number: int) -> dict:
        row = await db.raw_fetchone("SELECT * FROM wordle_games WHERE guild_id=? AND user_id=? AND day=?", (guild_id, user_id, number))
        if row:
            data = dict(row)
            data["list"] = data["guesses"].split() if data["guesses"] else []
            return data
        return {"guesses": "", "list": [], "status": 0}

    async def _save_game(self, guild_id: int, user_id: int, number: int, guesses: list[str], status: int):
        await db.raw_execute(
            "INSERT INTO wordle_games (guild_id, user_id, day, guesses, status) VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id, day) DO UPDATE SET guesses=excluded.guesses, status=excluded.status",
            (guild_id, user_id, number, " ".join(guesses), status),
        )

    async def _finish(self, guild_id: int, user_id: int, number: int, won: bool):
        row = await db.raw_fetchone("SELECT * FROM wordle_stats WHERE guild_id=? AND user_id=?", (guild_id, user_id))
        stats = dict(row) if row else {"played": 0, "won": 0, "streak": 0, "max_streak": 0, "last_won_day": 0}
        stats["played"] += 1
        if won:
            stats["won"] += 1
            stats["streak"] = stats["streak"] + 1 if stats["last_won_day"] == number - 1 else 1
            stats["last_won_day"] = number
            stats["max_streak"] = max(stats["max_streak"], stats["streak"])
        else:
            stats["streak"] = 0
        await db.raw_execute(
            "INSERT INTO wordle_stats (guild_id, user_id, played, won, streak, max_streak, last_won_day) VALUES (?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(guild_id, user_id) DO UPDATE SET played=excluded.played, won=excluded.won, streak=excluded.streak,"
            " max_streak=excluded.max_streak, last_won_day=excluded.last_won_day",
            (guild_id, user_id, stats["played"], stats["won"], stats["streak"], stats["max_streak"], stats["last_won_day"]),
        )
        return stats

    async def handle_play(self, interaction: discord.Interaction):
        number = today_number()
        game = await self._game(interaction.guild.id, interaction.user.id, number)
        if game["status"] != 0:
            answer = answer_for(number)
            text = f"## Wordle #{number}\n{board_text(game['list'], answer)}\n\nYou already finished today's puzzle. Come back tomorrow."
            return await interaction.response.send_message(view=private_view(text, 0x57F287 if game["status"] == 1 else 0xED4245, False), ephemeral=True)
        await interaction.response.send_modal(GuessModal(self))

    async def handle_guess(self, interaction: discord.Interaction, guess: str):
        number = today_number()
        guild_id, user_id = interaction.guild.id, interaction.user.id
        game = await self._game(guild_id, user_id, number)
        answer = answer_for(number)
        if game["status"] != 0:
            return await interaction.response.send_message("You already finished today's puzzle.", ephemeral=True)
        if len(guess) != 5 or not guess.isascii() or not guess.isalpha():
            return await interaction.response.send_message("Use exactly 5 letters from A to Z.", ephemeral=True)
        if guess in game["list"]:
            return await interaction.response.send_message("You already tried that word.", ephemeral=True)
        guesses = game["list"] + [guess]
        won = guess == answer
        lost = not won and len(guesses) >= MAX_GUESSES
        status = 1 if won else 2 if lost else 0
        await self._save_game(guild_id, user_id, number, guesses, status)
        text = f"## Wordle #{number}\n{board_text(guesses, answer)}"
        if status == 0:
            text += f"\n\n{MAX_GUESSES - len(guesses)} guess(es) left."
            return await interaction.response.send_message(view=private_view(text, 0x5865F2, True), ephemeral=True)
        stats = await self._finish(guild_id, user_id, number, won)
        if won:
            text += f"\n\nSolved in **{len(guesses)}/{MAX_GUESSES}**. Streak: **{stats['streak']}**."
        else:
            text += f"\n\nThe word was **{answer.upper()}**. Better luck tomorrow."
        await interaction.response.send_message(view=private_view(text, 0x57F287 if won else 0xED4245, False), ephemeral=True)
        public = f"{interaction.user.mention} {'solved' if won else 'failed'} Wordle #{number} " + (f"in **{len(guesses)}/{MAX_GUESSES}**" if won else f"**X/{MAX_GUESSES}**")
        try:
            await interaction.channel.send(f"{public}\n{board_text(guesses, answer, False)}", allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or interaction.guild is None:
            return
        if (interaction.data or {}).get("custom_id") != PLAY_ID:
            return
        await self.handle_play(interaction)

    @commands.group(name="wordle", invoke_without_command=True, help="Play today's Wordle. Everyone gets the same word.")
    @commands.guild_only()
    async def wordle(self, ctx: commands.Context):
        number = today_number()
        view = discord.ui.LayoutView(timeout=None)
        container = discord.ui.Container(accent_color=0x57F287)
        container.add_item(discord.ui.TextDisplay(
            f"## 🔤 Wordle #{number}\nGuess the 5 letter word in {MAX_GUESSES} tries. 🟩 right spot, 🟨 wrong spot, ⬛ not in the word.\n"
            "Press the button to guess. Your board is private and the result is posted here without spoilers. A new word comes every day at 00:00 UTC."
        ))
        container.add_item(discord.ui.Separator())
        container.add_item(play_row("Play"))
        view.add_item(container)
        await ctx.send(view=view)

    @wordle.command(name="stats", help="Show Wordle stats. Usage: wordle stats [member]")
    @commands.guild_only()
    async def wordle_stats(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        target = member or ctx.author
        row = await db.raw_fetchone("SELECT * FROM wordle_stats WHERE guild_id=? AND user_id=?", (ctx.guild.id, target.id))
        if row is None:
            return await ctx.send(view=error_layout("No Stats", f"{target.display_name} has not finished a Wordle yet."))
        rate = round(row["won"] / row["played"] * 100) if row["played"] else 0
        body = f"**Played:** {row['played']}\n**Won:** {row['won']} ({rate}%)\n**Streak:** {row['streak']}\n**Best streak:** {row['max_streak']}"
        await ctx.send(view=info_layout(f"🔤 Wordle stats for {target.display_name}", body))

    @wordle.command(name="top", aliases=["leaderboard", "lb"], help="Show the Wordle leaderboard.")
    @commands.guild_only()
    async def wordle_top(self, ctx: commands.Context):
        rows = await db.raw_fetch(
            "SELECT user_id, won, played, streak, max_streak FROM wordle_stats WHERE guild_id=? ORDER BY won DESC, max_streak DESC LIMIT 10", (ctx.guild.id,)
        )
        if not rows:
            return await ctx.send(view=info_layout("🔤 Wordle Leaderboard", "Nobody has finished a puzzle yet."))
        lines = [f"**{i}.** <@{r['user_id']}> - {r['won']} wins, best streak {r['max_streak']}" for i, r in enumerate(rows, 1)]
        await ctx.send(view=info_layout("🔤 Wordle Leaderboard", "\n".join(lines)), allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(Wordle(bot))
