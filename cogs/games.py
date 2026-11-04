import asyncio
import html
import io
import random
import textwrap
import time
import urllib.parse
from typing import Optional

import aiohttp
import discord
from discord.ext import commands
from PIL import Image, ImageDraw

import config
from utils import blacklist, emoji_manager, games
from utils.components import error_layout, info_layout, success_layout
from utils.profile_card import font

GAME_NAMES = {
    "tictactoe": "Tic-Tac-Toe",
    "connect4": "Connect 4",
    "rps": "Rock Paper Scissors",
    "hangman": "Hangman",
    "trivia": "Trivia",
    "typerace": "Typing Race",
}
TTT_MARKS = {1: "❌", 2: "⭕"}
C4_MARKS = {0: "⚪", 1: "🔴", 2: "🟡"}
C4_HEADER = "1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣"
RPS_ICONS = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
LETTERS = "ABCD"
TRIVIA_COLORS = {"easy": 0x57F287, "medium": 0xFEE75C, "hard": 0xED4245}


def mention(user_id: int) -> str:
    return f"<@{user_id}>"


def only(*ids: int) -> discord.AllowedMentions:
    return discord.AllowedMentions(users=[discord.Object(id=i) for i in ids])


class TurnGame(discord.ui.LayoutView):
    game = ""
    title = ""

    def __init__(self, ids: list[int], bot_id: int):
        super().__init__(timeout=config.GAME_MOVE_SECONDS)
        self.ids = ids
        self.bot_id = bot_id
        self.turn = 0
        self.over = False
        self.note = ""
        self.message: Optional[discord.Message] = None

    def versus_bot(self) -> bool:
        return self.bot_id in self.ids

    def head(self) -> str:
        raise NotImplementedError

    def board_text(self) -> str:
        return ""

    def rows(self) -> list[discord.ui.ActionRow]:
        return []

    def draw(self):
        self.clear_items()
        status = self.note if self.over else f"{mention(self.ids[self.turn])}'s turn" if self.ids[self.turn] != self.bot_id else "My turn"
        body = f"## {emoji_manager.get('star')} {self.title}\n{self.head()}\n\n{self.board_text()}\n{status}".replace("\n\n\n", "\n\n")
        container = discord.ui.Container(accent_color=0x5865F2 if not self.over else 0x2B2D31)
        container.add_item(discord.ui.TextDisplay(body))
        for row in self.rows():
            container.add_item(row)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in self.ids:
            await interaction.response.send_message("You are not part of this game.", ephemeral=True)
            return False
        if self.over:
            await interaction.response.send_message("This game is over.", ephemeral=True)
            return False
        if interaction.user.id != self.ids[self.turn]:
            await interaction.response.send_message("It is not your turn.", ephemeral=True)
            return False
        return True

    async def finish(self, winner: Optional[int]):
        self.over = True
        humans = [i for i in self.ids if i != self.bot_id]
        if winner is None:
            self.note = f"{emoji_manager.get('info')} It is a draw."
            for i in humans:
                await games.record(i, self.game, "draw")
        else:
            self.note = f"{emoji_manager.get('crown')} {mention(self.ids[winner])} wins!"
            for index, user_id in enumerate(self.ids):
                if user_id in humans:
                    await games.record(user_id, self.game, "win" if index == winner else "loss")
        self.stop()

    async def on_timeout(self):
        if self.over:
            return
        self.over = True
        self.note = f"{emoji_manager.get('warning')} Game ended because nobody moved for a while."
        self.draw()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass

    async def start(self, ctx: commands.Context):
        self.draw()
        self.message = await ctx.send(view=self, allowed_mentions=only(*[i for i in self.ids if i != self.bot_id]))


class TicTacToe(TurnGame):
    game = "tictactoe"
    title = "Tic-Tac-Toe"

    def __init__(self, ids: list[int], bot_id: int):
        super().__init__(ids, bot_id)
        self.cells = [0] * 9

    def head(self) -> str:
        return f"{TTT_MARKS[1]} {mention(self.ids[0])}   {TTT_MARKS[2]} {mention(self.ids[1])}"

    def rows(self) -> list[discord.ui.ActionRow]:
        out = []
        for r in range(3):
            row = discord.ui.ActionRow()
            for c in range(3):
                i = r * 3 + c
                value = self.cells[i]
                button = discord.ui.Button(
                    label="·" if not value else None, emoji=TTT_MARKS.get(value),
                    style=discord.ButtonStyle.secondary if not value else discord.ButtonStyle.success if value == 1 else discord.ButtonStyle.danger,
                    disabled=bool(value) or self.over)
                button.callback = self.make(i)
                row.add_item(button)
            out.append(row)
        return out

    def make(self, index: int):
        async def callback(interaction: discord.Interaction):
            if self.cells[index]:
                return await interaction.response.send_message("That square is taken.", ephemeral=True)
            await self.play(index)
            self.draw()
            await interaction.response.edit_message(view=self)
        return callback

    async def play(self, index: int):
        mark = self.turn + 1
        self.cells[index] = mark
        if games.ttt_winner(self.cells):
            return await self.finish(self.turn)
        if games.ttt_full(self.cells):
            return await self.finish(None)
        self.turn = 1 - self.turn
        if self.ids[self.turn] == self.bot_id:
            await self.play(games.ttt_bot_move(self.cells, self.turn + 1))


class Connect4(TurnGame):
    game = "connect4"
    title = "Connect 4"

    def __init__(self, ids: list[int], bot_id: int):
        super().__init__(ids, bot_id)
        self.grid = games.c4_new()

    def head(self) -> str:
        return f"{C4_MARKS[1]} {mention(self.ids[0])}   {C4_MARKS[2]} {mention(self.ids[1])}"

    def board_text(self) -> str:
        lines = ["".join(C4_MARKS[v] for v in row) for row in self.grid]
        return C4_HEADER + "\n" + "\n".join(lines)

    def rows(self) -> list[discord.ui.ActionRow]:
        out = []
        for chunk in ((0, 1, 2, 3), (4, 5, 6)):
            row = discord.ui.ActionRow()
            for col in chunk:
                button = discord.ui.Button(label=str(col + 1), style=discord.ButtonStyle.primary, disabled=self.over or not games.c4_open(self.grid, col))
                button.callback = self.make(col)
                row.add_item(button)
            out.append(row)
        return out

    def make(self, col: int):
        async def callback(interaction: discord.Interaction):
            if not games.c4_open(self.grid, col):
                return await interaction.response.send_message("That column is full.", ephemeral=True)
            await self.play(col)
            self.draw()
            await interaction.response.edit_message(view=self)
        return callback

    async def play(self, col: int):
        piece = self.turn + 1
        games.c4_drop(self.grid, col, piece)
        if games.c4_winner(self.grid):
            return await self.finish(self.turn)
        if games.c4_full(self.grid):
            return await self.finish(None)
        self.turn = 1 - self.turn
        if self.ids[self.turn] == self.bot_id:
            await self.play(games.c4_bot_move(self.grid, self.turn + 1))


class RPSView(discord.ui.LayoutView):
    def __init__(self, ids: list[int], bot_id: int):
        super().__init__(timeout=60)
        self.ids = ids
        self.bot_id = bot_id
        self.picks: dict[int, str] = {}
        self.done = False
        self.message: Optional[discord.Message] = None
        self.draw()

    def draw(self, result: str = ""):
        self.clear_items()
        container = discord.ui.Container(accent_color=0x5865F2 if not self.done else 0x2B2D31)
        waiting = ", ".join(mention(i) for i in self.ids if i not in self.picks and i != self.bot_id)
        text = result or f"{mention(self.ids[0])} vs {mention(self.ids[1])}\nPick one. Your choice stays hidden until both have picked.\nWaiting for: {waiting}"
        container.add_item(discord.ui.TextDisplay(f"## {emoji_manager.get('star')} Rock Paper Scissors\n{text}"))
        if not self.done:
            row = discord.ui.ActionRow()
            for choice in games.RPS_CHOICES:
                button = discord.ui.Button(label=choice.title(), emoji=RPS_ICONS[choice], style=discord.ButtonStyle.primary)
                button.callback = self.make(choice)
                row.add_item(button)
            container.add_item(row)
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in self.ids:
            await interaction.response.send_message("You are not part of this game.", ephemeral=True)
            return False
        return True

    def make(self, choice: str):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id in self.picks:
                return await interaction.response.send_message(f"You already picked {self.picks[interaction.user.id]}.", ephemeral=True)
            self.picks[interaction.user.id] = choice
            if self.bot_id in self.ids:
                self.picks[self.bot_id] = random.choice(games.RPS_CHOICES)
            if len(self.picks) < 2:
                self.draw()
                await interaction.response.send_message(f"You picked {RPS_ICONS[choice]} {choice}. Waiting for your opponent.", ephemeral=True)
                if self.message is not None:
                    await self.message.edit(view=self)
                return
            await self.resolve()
            await interaction.response.edit_message(view=self)
        return callback

    async def resolve(self):
        self.done = True
        a, b = self.ids
        pa, pb = self.picks[a], self.picks[b]
        outcome = games.rps_result(pa, pb)
        line = f"{mention(a)} {RPS_ICONS[pa]} **{pa}**   vs   {mention(b)} {RPS_ICONS[pb]} **{pb}**\n\n"
        if outcome == 0:
            line += f"{emoji_manager.get('info')} It is a draw."
        else:
            winner = self.ids[outcome - 1]
            line += f"{emoji_manager.get('crown')} {mention(winner)} wins!"
        humans = [i for i in self.ids if i != self.bot_id]
        for user_id in humans:
            result = "draw" if outcome == 0 else "win" if self.ids[outcome - 1] == user_id else "loss"
            await games.record(user_id, "rps", result)
        self.draw(line)
        self.stop()

    async def on_timeout(self):
        if self.done:
            return
        self.done = True
        self.draw(f"{emoji_manager.get('warning')} Nobody answered in time.")
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class GuessModal(discord.ui.Modal, title="Hangman guess"):
    def __init__(self, game: "Hangman"):
        super().__init__(timeout=120)
        self.game = game
        self.guess = discord.ui.TextInput(label="A letter, or the whole word", min_length=1, max_length=20)
        self.add_item(self.guess)

    async def on_submit(self, interaction: discord.Interaction):
        await self.game.handle(interaction, str(self.guess.value).strip().lower())


class Hangman(discord.ui.LayoutView):
    def __init__(self, starter: int):
        super().__init__(timeout=300)
        self.word = random.choice(games.WORDS)
        self.guessed: set[str] = set()
        self.wrong: list[str] = []
        self.over = False
        self.note = ""
        self.starter = starter
        self.message: Optional[discord.Message] = None
        self.draw()

    def draw(self):
        self.clear_items()
        stage = games.HANGMAN_STAGES[len(self.wrong)]
        wrong = " ".join(x.upper() for x in self.wrong) or "none"
        lives = config.HANGMAN_LIVES - len(self.wrong)
        text = f"## {emoji_manager.get('star')} Hangman\n{stage}\n`{games.mask(self.word, self.guessed)}`\nWrong: {wrong} · Lives: {lives}\n"
        text += self.note if self.over else "Anyone in the channel can guess."
        container = discord.ui.Container(accent_color=0x5865F2 if not self.over else 0x2B2D31)
        container.add_item(discord.ui.TextDisplay(text))
        if not self.over:
            row = discord.ui.ActionRow()
            button = discord.ui.Button(label="Guess", emoji="🔤", style=discord.ButtonStyle.primary)
            button.callback = self.open
            row.add_item(button)
            container.add_item(row)
        self.add_item(container)

    async def open(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GuessModal(self))

    async def handle(self, interaction: discord.Interaction, guess: str):
        if self.over:
            return await interaction.response.send_message("This game is over.", ephemeral=True)
        if not guess.isalpha():
            return await interaction.response.send_message("Only letters please.", ephemeral=True)
        solved = False
        if len(guess) == 1:
            if guess in self.guessed or guess in self.wrong:
                return await interaction.response.send_message("That letter was already guessed.", ephemeral=True)
            if guess in self.word:
                self.guessed.add(guess)
                solved = all(ch in self.guessed for ch in self.word)
            else:
                self.wrong.append(guess)
        elif guess == self.word:
            self.guessed.update(self.word)
            solved = True
        else:
            self.wrong.append(guess)
        if solved:
            self.over = True
            self.note = f"{emoji_manager.get('crown')} {mention(interaction.user.id)} solved it! The word was **{self.word}**."
            await games.record(interaction.user.id, "hangman", "win")
            self.stop()
        elif len(self.wrong) >= config.HANGMAN_LIVES:
            self.over = True
            self.note = f"{emoji_manager.get('cross')} Out of lives. The word was **{self.word}**."
            self.stop()
        self.draw()
        await interaction.response.edit_message(view=self)

    async def on_timeout(self):
        if self.over:
            return
        self.over = True
        self.note = f"{emoji_manager.get('warning')} Game ended. The word was **{self.word}**."
        self.draw()
        if self.message is not None:
            try:
                await self.message.edit(view=self)
            except discord.HTTPException:
                pass


class TriviaView(discord.ui.LayoutView):
    def __init__(self, data: dict):
        super().__init__(timeout=None)
        self.category = data["category"]
        self.difficulty = data["difficulty"]
        self.question = data["question"]
        options = data["incorrect"] + [data["correct"]]
        random.shuffle(options)
        self.options = options
        self.correct = options.index(data["correct"])
        self.answers: dict[int, int] = {}
        self.revealed = False
        self.ends = int(time.time()) + config.TRIVIA_SECONDS
        self.draw()

    def draw(self):
        self.clear_items()
        container = discord.ui.Container(accent_color=TRIVIA_COLORS.get(self.difficulty, 0x5865F2))
        lines = [f"## {emoji_manager.get('star')} Trivia", f"-# {self.category} · {self.difficulty}", f"**{self.question}**", ""]
        for i, option in enumerate(self.options):
            mark = ""
            if self.revealed:
                mark = " ✅" if i == self.correct else ""
            lines.append(f"**{LETTERS[i]}.** {option}{mark}")
        if self.revealed:
            right = [mention(u) for u, a in self.answers.items() if a == self.correct]
            wrong = [mention(u) for u, a in self.answers.items() if a != self.correct]
            lines.append("")
            lines.append(f"{emoji_manager.get('crown')} Correct: {' '.join(right) if right else 'nobody'}")
            if wrong:
                lines.append(f"{emoji_manager.get('cross')} Wrong: {' '.join(wrong)}")
        else:
            lines.append("")
            lines.append(f"Answer before <t:{self.ends}:R>. You get one try.")
        container.add_item(discord.ui.TextDisplay("\n".join(lines)))
        if not self.revealed:
            row = discord.ui.ActionRow()
            for i in range(len(self.options)):
                button = discord.ui.Button(label=LETTERS[i], style=discord.ButtonStyle.primary)
                button.callback = self.make(i)
                row.add_item(button)
            container.add_item(row)
        self.add_item(container)

    def make(self, index: int):
        async def callback(interaction: discord.Interaction):
            if self.revealed:
                return await interaction.response.send_message("Time is up.", ephemeral=True)
            if interaction.user.id in self.answers:
                return await interaction.response.send_message("You already answered.", ephemeral=True)
            self.answers[interaction.user.id] = index
            await interaction.response.send_message(f"Locked in **{LETTERS[index]}**.", ephemeral=True)
        return callback

    async def reveal(self, message: discord.Message):
        self.revealed = True
        for user_id, answer in self.answers.items():
            await games.record(user_id, "trivia", "win" if answer == self.correct else "loss")
        self.draw()
        self.stop()
        try:
            await message.edit(view=self)
        except discord.HTTPException:
            pass


def race_image(text: str) -> io.BytesIO:
    lines = textwrap.wrap(text, 38)
    fnt = font(40, "Medium")
    height = 120 + 62 * len(lines)
    image = Image.new("RGB", (1100, height), (30, 31, 34))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((14, 14, 1086, height - 14), 24, outline=(88, 101, 242), width=4)
    y = 55
    for line in lines:
        draw.text((50, y), line, font=fnt, fill=(235, 236, 240))
        y += 62
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    return buffer


class Games(commands.Cog):
    category = "Fun"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.trivia_channels: set[int] = set()
        self.hangman_channels: set[int] = set()
        self.races: dict[int, dict] = {}

    async def opponent(self, ctx: commands.Context, user: Optional[discord.User]):
        if user is None:
            return self.bot.user.id
        if user.id == ctx.author.id:
            await ctx.send(view=error_layout("Pick someone else", "You cannot play against yourself."))
            return None
        if user.bot and user.id != self.bot.user.id:
            await ctx.send(view=error_layout("Pick a person", "Other bots cannot play."))
            return None
        return user.id

    @commands.command(name="tictactoe", aliases=["ttt"], help="Play Tic-Tac-Toe against a friend or me. Usage: tictactoe [user]")
    async def tictactoe(self, ctx: commands.Context, user: Optional[discord.User] = None):
        other = await self.opponent(ctx, user)
        if other is None:
            return
        await TicTacToe([ctx.author.id, other], self.bot.user.id).start(ctx)

    @commands.command(name="connect4", aliases=["c4", "connectfour"], help="Play Connect 4 against a friend or me. Usage: connect4 [user]")
    async def connect4(self, ctx: commands.Context, user: Optional[discord.User] = None):
        other = await self.opponent(ctx, user)
        if other is None:
            return
        await Connect4([ctx.author.id, other], self.bot.user.id).start(ctx)

    @commands.command(name="rps", aliases=["rockpaperscissors"], help="Play Rock Paper Scissors against a friend or me. Usage: rps [user]")
    async def rps(self, ctx: commands.Context, user: Optional[discord.User] = None):
        other = await self.opponent(ctx, user)
        if other is None:
            return
        view = RPSView([ctx.author.id, other], self.bot.user.id)
        view.message = await ctx.send(view=view, allowed_mentions=only(other))

    @commands.command(name="hangman", aliases=["hm"], help="Guess the hidden word with everyone in the channel.")
    @commands.guild_only()
    async def hangman(self, ctx: commands.Context):
        if ctx.channel.id in self.hangman_channels:
            return await ctx.send(view=error_layout("Already running", "Finish the hangman game in this channel first."))
        self.hangman_channels.add(ctx.channel.id)
        view = Hangman(ctx.author.id)
        view.message = await ctx.send(view=view)
        await view.wait()
        self.hangman_channels.discard(ctx.channel.id)

    async def fetch_question(self, difficulty: Optional[str]) -> Optional[dict]:
        url = "https://opentdb.com/api.php?amount=1&type=multiple&encode=url3986"
        if difficulty:
            url += f"&difficulty={difficulty}"
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get(url) as response:
                    payload = await response.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            return None
        if payload.get("response_code") != 0 or not payload.get("results"):
            return None
        item = payload["results"][0]
        clean = lambda text: html.unescape(urllib.parse.unquote(text))
        return {
            "category": clean(item["category"]),
            "difficulty": item["difficulty"],
            "question": clean(item["question"]),
            "correct": clean(item["correct_answer"]),
            "incorrect": [clean(x) for x in item["incorrect_answers"]],
        }

    @commands.command(name="trivia", help="Answer a trivia question. Usage: trivia [easy|medium|hard]")
    @commands.guild_only()
    async def trivia(self, ctx: commands.Context, difficulty: Optional[str] = None):
        if difficulty is not None and difficulty.lower() not in TRIVIA_COLORS:
            return await ctx.send(view=error_layout("Unknown difficulty", "Use `easy`, `medium` or `hard`."))
        if ctx.channel.id in self.trivia_channels:
            return await ctx.send(view=error_layout("Already running", "Answer the current question in this channel first."))
        self.trivia_channels.add(ctx.channel.id)
        try:
            async with ctx.typing():
                data = await self.fetch_question(difficulty.lower() if difficulty else None)
            if data is None:
                return await ctx.send(view=error_layout("No question", "The trivia service did not answer. Try again in a few seconds."))
            view = TriviaView(data)
            message = await ctx.send(view=view)
            await asyncio.sleep(config.TRIVIA_SECONDS)
            await view.reveal(message)
        finally:
            self.trivia_channels.discard(ctx.channel.id)

    @commands.command(name="typerace", aliases=["typingrace", "typing"], help="Be the first to type the sentence shown. Usage: typerace")
    @commands.guild_only()
    async def typerace(self, ctx: commands.Context):
        if ctx.channel.id in self.races:
            return await ctx.send(view=error_layout("Already running", "A typing race is already running in this channel."))
        text = random.choice(games.SENTENCES)
        race = {"text": games.normalize_text(text), "raw": text, "start": 0.0, "done": False}
        self.races[ctx.channel.id] = race
        try:
            await ctx.send(view=info_layout(f"{emoji_manager.get('star')} Typing race", "Get ready. The sentence appears in 3 seconds. Type it exactly, first one wins."))
            await asyncio.sleep(3)
            view = discord.ui.LayoutView(timeout=None)
            container = discord.ui.Container(accent_color=0x5865F2)
            container.add_item(discord.ui.TextDisplay(f"## {emoji_manager.get('star')} Type this now"))
            container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem("attachment://race.png")))
            view.add_item(container)
            race["start"] = time.monotonic()
            await ctx.send(view=view, file=discord.File(race_image(text), "race.png"))
            await asyncio.sleep(config.TYPERACE_SECONDS)
            if not race["done"]:
                race["done"] = True
                await ctx.send(view=error_layout("Time is up", "Nobody finished the sentence."))
        finally:
            self.races.pop(ctx.channel.id, None)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        race = self.races.get(message.channel.id)
        if race is None or race["done"] or not race["start"]:
            return
        if games.normalize_text(message.content) != race["text"]:
            return
        if await blacklist.is_user_blacklisted(message.author.id):
            return
        if race["done"]:
            return
        race["done"] = True
        seconds = time.monotonic() - race["start"]
        await games.record(message.author.id, "typerace", "win")
        await message.channel.send(
            view=success_layout(f"{emoji_manager.get('crown')} We have a winner", f"{mention(message.author.id)} finished in **{seconds:.1f}s** · **{games.wpm(race['raw'], seconds)} WPM**"),
            allowed_mentions=only(message.author.id))

    @commands.group(name="games", aliases=["game"], invoke_without_command=True, help="See the games you can play and your record.")
    async def games_group(self, ctx: commands.Context):
        lines = [
            "`tictactoe [user]` · `connect4 [user]` · `rps [user]`",
            "`hangman` · `trivia [easy|medium|hard]` · `typerace`",
            "Leave out the user to play against me.",
            "`games stats [user]` shows a record, `games top <game>` shows the best players.",
        ]
        await ctx.send(view=info_layout(f"{emoji_manager.get('star')} Games", "\n".join(lines)))

    @games_group.command(name="stats", aliases=["record", "profile"], help="Show a game record. Usage: games stats [user]")
    async def games_stats(self, ctx: commands.Context, user: Optional[discord.User] = None):
        target = user or ctx.author
        rows = await games.stats(target.id)
        if not rows:
            return await ctx.send(view=info_layout(f"{emoji_manager.get('star')} Game record", f"{target.display_name} has not played yet."))
        lines = [f"**{GAME_NAMES.get(r['game'], r['game'])}** · {r['wins']}W {r['losses']}L {r['draws']}D" for r in rows]
        await ctx.send(view=info_layout(f"{emoji_manager.get('star')} {target.display_name}'s record", "\n".join(lines)))

    @games_group.command(name="top", aliases=["leaderboard", "lb"], help="Show the best players of a game. Usage: games top <game>")
    async def games_top(self, ctx: commands.Context, game: str = "trivia"):
        key = game.lower().replace("-", "").replace(" ", "")
        key = {"ttt": "tictactoe", "c4": "connect4", "hm": "hangman", "typing": "typerace", "typingrace": "typerace"}.get(key, key)
        if key not in GAME_NAMES:
            return await ctx.send(view=error_layout("Unknown game", "Pick one of: " + ", ".join(f"`{k}`" for k in GAME_NAMES) + "."))
        rows = await games.top(key)
        if not rows:
            return await ctx.send(view=info_layout(f"{emoji_manager.get('star')} {GAME_NAMES[key]}", "Nobody has won yet."))
        lines = [f"`{i}.` {mention(r['user_id'])} · {r['wins']} wins" for i, r in enumerate(rows, 1)]
        await ctx.send(view=info_layout(f"{emoji_manager.get('crown')} {GAME_NAMES[key]} top players", "\n".join(lines)), allowed_mentions=discord.AllowedMentions.none())


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
