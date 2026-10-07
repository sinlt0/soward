import re
from typing import Optional

import discord
from discord.ext import commands

class DurationConverter(commands.Converter):
    UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}

    async def convert(self, ctx: commands.Context, argument: str) -> int:
        total = 0
        matches = re.findall(r"(\d+)([smhdw])", argument.lower())
        if not matches:
            raise commands.BadArgument(
                "Invalid duration format. Use combinations like `10m`, `2h`, `1d`."
            )
        for amount, unit in matches:
            total += int(amount) * self.UNITS[unit]
        return total

class MemberOrIdConverter(commands.Converter):
    async def convert(self, ctx: commands.Context, argument: str) -> discord.Member | int:
        try:
            return await commands.MemberConverter().convert(ctx, argument)
        except commands.BadArgument:
            pass
        if argument.isdigit():
            return int(argument)
        raise commands.BadArgument(f"Could not find member: `{argument}`")

def format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    if seconds < 86400:
        h = seconds // 3600
        m = (seconds % 3600) // 60
        return f"{h}h {m}m"
    d = seconds // 86400
    h = (seconds % 86400) // 3600
    return f"{d}d {h}h"
