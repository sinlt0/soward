import random
import re
from typing import Optional

import discord

DEFAULT_VARIABLE_DOCS = {
    "user": "Mentions the member (@Username)",
    "username": "The member's display name",
    "usertag": "The member's full tag (Username#0001 or Username)",
    "userid": "The member's Discord user ID",
    "useravatar": "URL of the member's avatar",
    "userjoindate": "When the member joined this server",
    "usercreated": "When the member's account was created",
    "server": "The server's name",
    "serverid": "The server's ID",
    "servericon": "URL of the server's icon",
    "membercount": "Total member count of the server",
    "boostcount": "Number of boosts the server currently has",
    "channel": "Mentions the channel the event happened in",
    "channelname": "Name of the channel the event happened in",
    "channelid": "ID of the channel the event happened in",
}


def build_base_variables(member: discord.Member, guild: Optional[discord.Guild] = None, channel: Optional[discord.abc.GuildChannel] = None) -> dict:
    guild = guild or member.guild

    var_map = {
        "user": member.mention,
        "username": member.display_name,
        "usertag": str(member),
        "userid": str(member.id),
        "useravatar": member.display_avatar.url,
        "userjoindate": f"<t:{int(member.joined_at.timestamp())}:f>" if member.joined_at else "Unknown",
        "usercreated": f"<t:{int(member.created_at.timestamp())}:f>",
        "server": guild.name,
        "serverid": str(guild.id),
        "servericon": guild.icon.url if guild.icon else "",
        "membercount": str(guild.member_count),
        "boostcount": str(guild.premium_subscription_count or 0),
    }

    if channel:
        var_map["channel"] = channel.mention
        var_map["channelname"] = channel.name
        var_map["channelid"] = str(channel.id)

    return var_map


def apply_conditionals(text: str, var_map: dict) -> str:
    def eval_condition(cond: str) -> bool:
        cond = cond.strip()
        parts = cond.split()
        if len(parts) == 3:
            left = var_map.get(parts[0].strip("{}"), parts[0])
            op = parts[1]
            right = parts[2]
            if op == "==":
                return str(left) == right
            if op == "!=":
                return str(left) != right
            if op in (">", ">=", "<", "<="):
                try:
                    l, r = float(left), float(right)
                    if op == ">":
                        return l > r
                    if op == ">=":
                        return l >= r
                    if op == "<":
                        return l < r
                    if op == "<=":
                        return l <= r
                except (ValueError, TypeError):
                    pass
        return bool(cond)

    pattern = re.compile(r"\{if ([^}]+)\}(.*?)(?:\{else\}(.*?))?\{end\}", re.DOTALL)

    def replacer(m: re.Match) -> str:
        cond_str, if_body, else_body = m.group(1), m.group(2), m.group(3) or ""
        return if_body.strip() if eval_condition(cond_str) else else_body.strip()

    for _ in range(5):
        new_text = pattern.sub(replacer, text)
        if new_text == text:
            break
        text = new_text
    return text


def apply_random_blocks(text: str) -> str:
    pattern = re.compile(r"\{random\}(.*?)\{endrandom\}", re.DOTALL)

    def replacer(m: re.Match) -> str:
        options = [o.strip() for o in m.group(1).split("{|}") if o.strip()]
        return random.choice(options) if options else ""

    return pattern.sub(replacer, text)


def substitute(template: str, var_map: dict) -> str:
    text = apply_conditionals(template, var_map)
    text = apply_random_blocks(text)
    for key, value in var_map.items():
        text = text.replace(f"{{{key}}}", str(value))
    return text


def variables_doc_block(extra_docs: Optional[dict] = None) -> str:
    lines = [f"`{{{k}}}` — {v}" for k, v in DEFAULT_VARIABLE_DOCS.items()]
    if extra_docs:
        lines.append("")
        lines.extend(f"`{{{k}}}` — {v}" for k, v in extra_docs.items())
    return "\n".join(lines)
