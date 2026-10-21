import copy
from typing import Optional

VIEW = "view_channel"
SEND = ["send_messages", "add_reactions", "create_public_threads", "create_private_threads", "send_messages_in_threads"]
STAFF = ("admin", "mod", "helper")

PERMS = {
    "admin": ["administrator"],
    "mod": ["kick_members", "ban_members", "moderate_members", "manage_messages", "manage_nicknames", "view_audit_log",
            "mute_members", "deafen_members", "move_members", "manage_threads"],
    "helper": ["moderate_members", "manage_messages", "manage_nicknames", "mute_members"],
    "member": ["view_channel", "send_messages", "read_message_history", "add_reactions", "connect", "speak", "embed_links",
               "attach_files", "use_external_emojis", "create_public_threads", "send_messages_in_threads", "change_nickname"],
}


def _ow(allow=(), deny=()):
    return {"allow": list(allow), "deny": list(deny)}


def access(kind: str, staff: tuple = STAFF) -> Optional[dict]:
    if kind == "public":
        return {}
    if kind.startswith("roles:"):
        keys = kind[6:].split(",")
        grant = _ow([VIEW, "send_messages", "connect", "speak", "add_reactions", "read_message_history"])
        return {"everyone": _ow(deny=[VIEW]), "member": _ow(deny=[VIEW]), **{k: _ow([VIEW, "send_messages", "connect", "speak"]) for k in staff}, **{k: grant for k in keys}}
    if kind.startswith("only:"):
        keys = kind[5:].split(",")
        return {"everyone": _ow(deny=[VIEW]), "member": _ow(deny=[VIEW]), **{k: _ow([VIEW, "send_messages", "connect", "speak", "read_message_history"]) for k in keys}}
    staff_view = {k: _ow([VIEW, "send_messages", "connect", "speak"]) for k in staff}
    if kind == "members":
        return {"everyone": _ow(deny=[VIEW]), "member": _ow([VIEW]), **staff_view}
    if kind == "readonly":
        return {"everyone": _ow(deny=[VIEW] + SEND), "member": _ow([VIEW], SEND), **staff_view}
    if kind == "staff":
        return {"everyone": _ow(deny=[VIEW]), **staff_view}
    if kind == "gate":
        return {"everyone": _ow(deny=[VIEW] + SEND), "unverified": _ow([VIEW, "read_message_history"], SEND), "member": _ow([VIEW], SEND), **staff_view}
    if kind == "verify":
        return {"everyone": _ow([VIEW], SEND), "member": _ow(deny=[VIEW])}
    if kind == "publicread":
        return {"everyone": _ow([VIEW], SEND), **staff_view}
    if kind == "supporter":
        return {"everyone": _ow(deny=[VIEW]), "sub": _ow([VIEW, "send_messages", "connect", "speak"]), "creator": _ow([VIEW, "send_messages"]), **staff_view}
    if kind == "hub":
        return {"everyone": _ow(deny=[VIEW]), "member": _ow([VIEW, "connect"], ["speak"]), **staff_view}
    if kind == "voice":
        return {"everyone": _ow(deny=[VIEW]), "member": _ow([VIEW, "connect", "speak"]), **staff_view}
    raise ValueError(kind)


class Builder:
    def __init__(self):
        self.roles: list[dict] = []
        self.categories: list[dict] = []
        self.embeds: list[dict] = []
        self.messages: list[dict] = []
        self.panels: list[dict] = []
        self.tickets: list[dict] = []
        self.settings: dict = {}
        self.tables: dict = {}
        self.greetings: list[dict] = []
        self.flags: dict = {}
        self.logs: dict = {}
        self.commands: list[dict] = []
        self.fixed_order = False
        self.staff: tuple = STAFF
        self._cat: Optional[dict] = None
        self._n = 0

    def role(self, key, name, color=0, perms=None, hoist=False, mentionable=False):
        self.roles.append({
            "key": key, "name": name, "color": color, "hoist": hoist, "mentionable": mentionable,
            "perms": PERMS.get(perms, perms) if isinstance(perms, str) else (perms or []),
        })

    def category(self, name, kind="members"):
        self._n += 1
        self._cat = {"key": f"cat{self._n}", "name": name, "overwrites": access(kind, self.staff), "channels": []}
        self.categories.append(self._cat)
        return self._cat["key"]

    def channel(self, key, name, kind="text", topic=None, access_kind=None, slowmode=0, user_limit=0, merge=True):
        entry = {"key": key, "name": name, "type": kind, "overwrites": access(access_kind, self.staff) if access_kind else None}
        if not merge:
            entry["merge"] = False
        if topic:
            entry["topic"] = topic
        if slowmode:
            entry["slowmode"] = slowmode
        if user_limit:
            entry["user_limit"] = user_limit
        self._cat["channels"].append(entry)

    def embed(self, name, title, description, color=0x5865F2, fields=None, footer=None, thumb=None):
        self.embeds.append({
            "name": name, "title": title, "description": description, "color": f"#{color:06X}",
            "footer_text": footer, "thumbnail_url": thumb, "use_timestamp": 0,
            "fields": [{"name": n, "value": v, "inline": bool(i)} for n, v, i in (fields or [])],
        })

    def command(self, trigger, response, embed=False, color=None, title=None, options=(), placeholder="", allowed_roles=(), cooldown=0, allowed_channels=()):
        self.commands.append({"trigger": trigger, "data": {
            "trigger_text": trigger, "trigger_type": "command", "responses": [response], "embed": embed, "embed_color": color, "embed_title": title,
            "cooldown": cooldown, "cooldown_type": "user", "allowed_roles": [{"$role": k} for k in allowed_roles], "denied_roles": [],
            "allowed_channels": [{"$channel": k} for k in allowed_channels], "denied_channels": [], "enabled": True, "description": "",
            "menu": {"placeholder": placeholder, "options": [dict(o) for o in options]},
        }})

    def post_special(self, channel_key, special, pin=False):
        self.messages.append({"channel": channel_key, "special": special, "pin": pin})

    def post_command(self, channel_key, trigger, pin=False):
        self.messages.append({"channel": channel_key, "command": trigger, "pin": pin})

    def post(self, channel_key, embed, pin=False):
        self.messages.append({"channel": channel_key, "embed": embed, "pin": pin})

    def panel(self, channel_key, embed, ptype, roles, mode="normal", max_roles=0):
        self.panels.append({
            "channel": {"$channel": channel_key}, "embed": embed, "type": ptype, "mode": mode, "max_roles": max_roles,
            "roles": [{"emoji": e, "role": {"$role": r}, "label": label} for e, r, label in roles],
        })

    def levels(self, rewards, announce_key=None, **extra):
        row = {"enabled": 1, "role_stack_mode": "nonstack", "announce_mode": "channel" if announce_key else "off"}
        if announce_key:
            row["announce_channel_id"] = {"$channel": announce_key}
        row.update(extra)
        self.tables["guild_leveling_config"] = [row]
        self.tables["level_role_rewards"] = [{"level": lvl, "role_id": {"$role": key}} for lvl, key in rewards]

    def greeting(self, trigger, channel_key, text, enabled=1, delete_after=None, embed=None):
        self.greetings.append({
            "trigger_type": trigger, "enabled": enabled, "channel_id": {"$channel": channel_key}, "message_text": text,
            "embed_name": embed, "send_as_dm": 0, "dm_fallback_to_channel": 1, "use_card": 0, "card_layout": "classic",
            "card_background_url": None, "card_accent_color": None, "join_role_delay_seconds": 0, "delete_after_seconds": delete_after,
        })

    def ticket(self, channel_key, name, staff, category=None, transcript=None, welcome=None, button=None, questions=None):
        self.tickets.append({
            "channel": channel_key, "name": name, "staff": list(staff), "category": category, "transcript": transcript,
            "welcome": welcome, "button": button, "questions": list(questions or []), "one_per_user": 1, "ask_subject": 1,
        })

    def _tier(self, key: str) -> int:
        if key in self.staff or key in ("admin", "hmod", "mod", "helper", "verifier"):
            return 0
        if key == "bot":
            return 1
        if key in ("member", "verified", "age18", "vgirl", "vguy", "vnb", "creator", "dev", "streamer", "sub", "tutor"):
            return 2
        if key in ("booster", "vip", "vipplus", "partner") or key.startswith("tier"):
            return 3
        if key.startswith("lvl"):
            return 4
        return 5

    def result(self, meta: dict) -> dict:
        if not self.fixed_order:
            self.roles.sort(key=lambda r: self._tier(r["key"]))
        return {
            "version": 1, "meta": meta, "roles": self.roles, "categories": self.categories, "settings": self.settings,
            "tables": self.tables, "greetings": self.greetings, "logs": self.logs, "commands": self.commands, "nsfw": None, "embeds": self.embeds,
            "panels": self.panels, "tickets": self.tickets, "messages": self.messages, "flags": self.flags, "prefix": None,
        }


def _staff_roles(b: Builder, colors=(0xE74C3C, 0xE67E22, 0xF1C40F)):
    b.role("admin", "Admin", colors[0], "admin", hoist=True)
    b.role("mod", "Moderator", colors[1], "mod", hoist=True)
    b.role("helper", "Helper", colors[2], "helper", hoist=True)


def _base_roles(b: Builder, member_name="Member", member_color=0x95A5A6):
    b.role("bot", "Bots", 0x7289DA, [VIEW, "send_messages"], hoist=False)
    b.role("member", member_name, member_color, "member")


def _levels(b: Builder, names=("Regular", "Active", "Veteran", "Elite", "Legend"), levels=(5, 10, 20, 35, 50)):
    colors = (0x1ABC9C, 0x2ECC71, 0x3498DB, 0x9B59B6, 0xF1C40F)
    keys = []
    for i, n in enumerate(names):
        c = colors[i % len(colors)]
        key = f"lvl{i + 1}"
        b.role(key, n, c, "member")
        keys.append(key)
    return list(zip(levels, keys))


def _ping_roles(b: Builder, items):
    for key, name, color in items:
        b.role(key, name, color, "member", mentionable=True)


def _color_roles(b: Builder):
    palette = [("c_red", "Red", 0xE74C3C), ("c_blue", "Blue", 0x3498DB), ("c_green", "Green", 0x2ECC71),
               ("c_purple", "Purple", 0x9B59B6), ("c_pink", "Pink", 0xFF69B4), ("c_orange", "Orange", 0xE67E22)]
    for key, name, color in palette:
        b.role(key, name, color, "member")
    return palette


def _pronouns(b: Builder):
    for key, name in (("p_he", "He/Him"), ("p_she", "She/Her"), ("p_they", "They/Them"), ("p_any", "Any Pronouns")):
        b.role(key, name, 0xBDC3C7, "member")


def _rules_embed(b: Builder, name, rules, color=0xE74C3C, intro="Read these before you chat. Staying here means you agree to them."):
    text = intro + "\n\n" + "\n".join(f"**{i + 1}.** {r}" for i, r in enumerate(rules))
    b.embed(name, "📜 Server Rules", text, color, footer="Staff decisions are final. Ask a moderator if anything is unclear.")


def _verify(b: Builder, channel_key, level=2):
    b.settings["verification_level"] = level
    b.settings["verification_role_id"] = {"$role": "member"}
    b.flags["verification_panel"] = channel_key


def _common_setup(b: Builder, security="balanced", verify_level=2):
    b.flags["logging"] = True
    b.flags["security_preset"] = security
    b.settings["autorole_bot_join"] = [{"$role": "bot"}]
    _verify(b, "verify", verify_level)


def _welcome(b: Builder, text, channel="welcome", boost_channel="general"):
    b.embed("tpl-welcome", "👋 Welcome to {server}!", text, 0x57F287, footer="Member #{membercount}")
    b.greeting("join", channel, "{user}", embed="tpl-welcome")
    b.greeting("leave", channel, "**{username}** has left **{server}**. We are now **{membercount}** members.", enabled=0)
    b.greeting("boost", boost_channel, "💜 Thank you {user} for boosting **{server}**!")


def _ticket_area(b: Builder, name, button, welcome, questions=(), cat_name="🎫 HELP DESK", tickets_name="🎟️ TICKETS"):
    b.category(cat_name, "readonly")
    b.channel("open_ticket", "🎫-open-a-ticket", topic="Press the button to open a private ticket with staff.")
    tickets_cat = b.category(tickets_name, "staff")
    b.channel("transcripts", "📄-ticket-transcripts", access_kind="staff")
    b.ticket("open_ticket", name, STAFF, category=tickets_cat, transcript="transcripts", welcome=welcome, button=button, questions=questions)


def _self_roles(b: Builder, ping_items, extra_panels=()):
    b.embed("tpl-self-pings", "🔔 Ping Roles", "Choose which announcements you want to be pinged for. Click a button again to remove the role.", 0x3498DB)
    b.embed("tpl-self-colors", "🎨 Name Colors", "Pick one colour for your name. Choosing a new one swaps the old one.", 0xFF69B4)
    b.embed("tpl-self-pronouns", "🏷️ Pronouns", "Show your pronouns on your profile. Pick any that fit.", 0xBDC3C7)
    b.panel("self_roles", "tpl-self-pings", "button", ping_items)
    colors = _color_roles_items()
    b.panel("self_roles", "tpl-self-colors", "select", colors, mode="unique")
    b.panel("self_roles", "tpl-self-pronouns", "reaction", [("🔵", "p_he", "He/Him"), ("🔴", "p_she", "She/Her"), ("🟢", "p_they", "They/Them"), ("⚪", "p_any", "Any Pronouns")])
    for item in extra_panels:
        b.panel("self_roles", *item[:3], mode=item[3] if len(item) > 3 else "normal")


def _color_roles_items():
    return [("🔴", "c_red", "Red"), ("🔵", "c_blue", "Blue"), ("🟢", "c_green", "Green"), ("🟣", "c_purple", "Purple"), ("💗", "c_pink", "Pink"), ("🟠", "c_orange", "Orange")]


def _core_channels(b: Builder, rules, welcome_text, announcements=True):
    b.category("📌 START HERE", "publicread")
    b.channel("verify", "✅-verify", topic="Verify here to unlock the rest of the server.", access_kind="verify")
    b.channel("rules", "📜-rules", topic="Read the rules before chatting.", access_kind="publicread")
    b.channel("welcome", "👋-welcome", topic="New members are greeted here.", access_kind="members")
    b.category("📣 INFORMATION", "readonly")
    if announcements:
        b.channel("announcements", "📢-announcements", "announcement", "Official news and updates.")
    b.channel("self_roles", "🎭-self-roles", topic="Pick ping, colour and pronoun roles.")
    b.channel("levels", "📈-level-ups", topic="Level up messages and rewards.")
    b.post("rules", "tpl-rules", pin=True)
    b.post("self_roles", "tpl-self-intro")


def _staff_category(b: Builder):
    b.category("🛡️ STAFF", "staff")
    b.channel("staff_chat", "🛡️-staff-chat")
    b.channel("staff_cmds", "🤖-staff-commands")
    b.channel("reports", "🚨-reports", topic="Reports and incidents.")
    b.category("🎙️ STAFF VOICE", "staff")
    b.channel("staff_vc", "Staff Room", "voice")


def community() -> dict:
    b = Builder()
    _staff_roles(b)
    _base_roles(b)
    b.role("booster", "Booster", 0xF47FFF, "member", hoist=True)
    b.role("vip", "VIP", 0xFFD700, "member", hoist=True)
    lv = _levels(b)
    _ping_roles(b, [("ping_news", "📢 Announcements", 0x3498DB), ("ping_events", "🎉 Events", 0xE91E63), ("ping_giveaways", "🎁 Giveaways", 0xF1C40F),
                    ("ping_polls", "📊 Polls", 0x1ABC9C), ("ping_revive", "💬 Chat Revive", 0x95A5A6)])
    _color_roles(b)
    _pronouns(b)
    _rules_embed(b, "tpl-rules", ["Be respectful. No harassment, hate speech or personal attacks.", "No spam, self promotion or unsolicited DMs.",
                                  "Keep topics in the right channels.", "No NSFW, gore or illegal content anywhere.",
                                  "Follow Discord's Terms of Service and Community Guidelines.", "Listen to staff and use tickets or reports for problems."])
    b.embed("tpl-self-intro", "🎭 Self Roles", "Use the panels below to pick your roles. Everything here is optional.", 0x5865F2)
    _core_channels(b, None, None)
    b.category("💬 COMMUNITY", "members")
    b.channel("general", "💬-general", topic="Talk about anything.", slowmode=2)
    b.channel("media", "📸-media", topic="Share images, clips and art.")
    b.channel("memes", "😂-memes")
    b.channel("introductions", "🙋-introductions", topic="Tell us about yourself.")
    b.channel("suggestions", "💡-suggestions", topic="Ideas to improve the server.")
    b.channel("bots", "🤖-bot-commands", topic="Use bot commands here.")
    b.category("🎮 FUN", "members")
    b.channel("games", "🎮-games")
    b.channel("counting", "🔢-counting", topic="Count upward together. No double counting.")
    b.channel("polls", "📊-polls")
    b.category("🔊 VOICE", "voice")
    b.channel("vc1", "💬 Lounge", "voice")
    b.channel("vc2", "🎵 Music", "voice")
    b.channel("vc3", "🎮 Gaming", "voice")
    b.channel("vc4", "🔒 Private", "voice", user_limit=2)
    b.channel("stage", "🎤 Community Stage", "stage")
    _ticket_area(b, "Support", "Contact Staff", "Thanks for reaching out. A staff member will be with you shortly.", ("What do you need help with?",))
    _staff_category(b)
    _self_roles(b, [("📢", "ping_news", "Announcements"), ("🎉", "ping_events", "Events"), ("🎁", "ping_giveaways", "Giveaways"),
                    ("📊", "ping_polls", "Polls"), ("💬", "ping_revive", "Chat Revive")])
    _welcome(b, "Welcome to **{server}**, {user}! You are member **#{membercount}**. Read the rules and enjoy your stay.")
    b.levels(lv, "levels")
    _common_setup(b, "balanced", 2)
    b.settings["autorole_human_join"] = []
    return b.result({"id": "community", "name": "Community Server", "emoji": "🌐", "summary": "A friendly general-purpose community with levels, self roles and staff tools."})


def gaming() -> dict:
    b = Builder()
    _staff_roles(b, (0xE74C3C, 0x9B59B6, 0x3498DB))
    _base_roles(b, "Gamer", 0x2ECC71)
    b.role("booster", "Booster", 0xF47FFF, "member", hoist=True)
    b.role("streamer", "Streamer", 0x9146FF, "member", hoist=True)
    lv = _levels(b, ("Rookie", "Player", "Pro", "Master", "Legend"))
    _ping_roles(b, [("ping_news", "📢 News", 0x3498DB), ("ping_lfg", "🎮 LFG", 0x2ECC71), ("ping_tourney", "🏆 Tournaments", 0xF1C40F),
                    ("ping_stream", "📺 Streams", 0x9146FF), ("ping_giveaways", "🎁 Giveaways", 0xE91E63)])
    for key, name, color in (("g_valorant", "Valorant", 0xFF4655), ("g_minecraft", "Minecraft", 0x62B47A), ("g_fortnite", "Fortnite", 0x7D5FFF),
                             ("g_cod", "Call of Duty", 0x555555), ("g_apex", "Apex Legends", 0xDA292A), ("g_lol", "League of Legends", 0xC89B3C),
                             ("g_roblox", "Roblox", 0xE2231A), ("g_gta", "GTA", 0x3CB371)):
        b.role(key, name, color, "member")
    for key, name in (("pc", "PC"), ("console", "Console"), ("mobile", "Mobile")):
        b.role(f"plat_{key}", name, 0x7F8C8D, "member")
    _color_roles(b)
    _pronouns(b)
    _rules_embed(b, "tpl-rules", ["Respect every player. Trash talk is fine, toxicity is not.", "No cheating, exploits, boosting or account selling.",
                                  "Use the right channel for each game and LFG.", "No spam, advertising or unsolicited DMs.",
                                  "No NSFW, hate speech or doxxing.", "Follow staff instructions in voice and text."])
    b.embed("tpl-self-intro", "🎮 Pick Your Roles", "Choose your games, platforms and pings below.", 0x5865F2)
    b.embed("tpl-games", "🕹️ Your Games", "Select the games you play so teammates can find you.", 0x2ECC71)
    b.embed("tpl-platform", "🖥️ Platform", "Pick the platforms you play on.", 0x7F8C8D)
    _core_channels(b, None, None)
    b.category("💬 LOBBY", "members")
    b.channel("general", "💬-general", slowmode=2)
    b.channel("clips", "🎬-clips-and-highlights", topic="Post your best plays.")
    b.channel("memes", "😂-gaming-memes")
    b.channel("setups", "🖥️-setups")
    b.channel("bots", "🤖-bot-commands")
    b.category("🤝 LOOKING FOR GROUP", "members")
    b.channel("lfg", "🎮-lfg-general", topic="Ping @LFG and say what you want to play.")
    b.channel("lfg_comp", "🏆-lfg-competitive")
    b.channel("tourney", "🏅-tournaments", topic="Tournament signups and brackets.")
    b.category("🎯 GAME CHATS", "members")
    for key, name in (("valorant", "🎯-valorant"), ("minecraft", "⛏️-minecraft"), ("fortnite", "🪂-fortnite"), ("cod", "🔫-call-of-duty"),
                      ("apex", "🦅-apex-legends"), ("other_games", "🕹️-other-games")):
        b.channel(key, name)
    b.category("📺 STREAMING", "members")
    b.channel("live", "🔴-live-now", topic="Streamers post their live links here.")
    b.channel("streamer_chat", "🎥-streamer-chat")
    b.category("🔊 VOICE", "voice")
    for i in range(1, 4):
        b.channel(f"squad{i}", f"🎮 Squad {i}", "voice", user_limit=5)
    b.channel("duo", "👥 Duo", "voice", user_limit=2)
    b.channel("chill", "🎧 Chill", "voice")
    b.channel("stage", "🎤 Arena Stage", "stage")
    _ticket_area(b, "Support", "Contact Staff", "Thanks for reaching out. A staff member will be with you shortly.", ("What do you need help with?",))
    _staff_category(b)
    _self_roles(b, [("📢", "ping_news", "News"), ("🎮", "ping_lfg", "LFG"), ("🏆", "ping_tourney", "Tournaments"), ("📺", "ping_stream", "Streams"), ("🎁", "ping_giveaways", "Giveaways")])
    b.panel("self_roles", "tpl-games", "select", [("🎯", "g_valorant", "Valorant"), ("⛏️", "g_minecraft", "Minecraft"), ("🪂", "g_fortnite", "Fortnite"),
                                                    ("🔫", "g_cod", "Call of Duty"), ("🦅", "g_apex", "Apex Legends"), ("⚔️", "g_lol", "League of Legends"),
                                                    ("🧱", "g_roblox", "Roblox"), ("🚗", "g_gta", "GTA")])
    b.panel("self_roles", "tpl-platform", "button", [("🖥️", "plat_pc", "PC"), ("🎮", "plat_console", "Console"), ("📱", "plat_mobile", "Mobile")])
    _welcome(b, "Welcome to **{server}**, {user}! Grab your games in the self roles channel and jump into LFG.")
    b.levels(lv, "levels", voice_xp_per_minute=12)
    _common_setup(b, "balanced", 2)
    return b.result({"id": "gaming", "name": "Gaming Server", "emoji": "🎮", "summary": "Game chats, LFG, tournaments, streaming and platform or game self roles."})


def support() -> dict:
    b = Builder()
    b.role("admin", "Admin", 0xE74C3C, "admin", hoist=True)
    b.role("mod", "Support Manager", 0xE67E22, "mod", hoist=True)
    b.role("helper", "Support Agent", 0xF1C40F, "helper", hoist=True)
    _base_roles(b, "Customer", 0x95A5A6)
    b.role("verified", "Verified Customer", 0x2ECC71, "member")
    b.role("dev", "Developer", 0x3498DB, "member", hoist=True)
    lv = _levels(b, ("Newcomer", "Contributor", "Helper", "Expert", "Guru"), (3, 8, 15, 30, 50))
    _ping_roles(b, [("ping_updates", "📢 Product Updates", 0x3498DB), ("ping_status", "🟢 Status Alerts", 0x2ECC71), ("ping_betas", "🧪 Beta Testing", 0x9B59B6),
                    ("ping_news", "📰 Announcements", 0xE67E22)])
    _color_roles(b)
    _pronouns(b)
    _rules_embed(b, "tpl-rules", ["Be polite to support staff and other members.", "Search before asking and post in the correct channel.",
                                  "Never share passwords, tokens or personal data.", "Do not ping staff for faster replies.",
                                  "Use tickets for private or account issues.", "No advertising or unrelated promotion."])
    b.embed("tpl-self-intro", "🔔 Notifications", "Pick which updates you want to be notified about.", 0x5865F2)
    b.embed("tpl-faq", "❓ Frequently Asked Questions", "Quick answers to common questions.", 0x3498DB,
            [("How do I get help?", "Open a ticket in the support channel or ask in the help forum.", 0),
             ("How fast do you reply?", "Agents usually reply within a few hours.", 0),
             ("Where do I report a bug?", "Post it in the bug reports channel with steps to reproduce.", 0)])
    _core_channels(b, None, None)
    b.category("🎫 SUPPORT", "members")
    b.channel("open_ticket", "🎫-open-a-ticket", topic="Press the button to open a private ticket.", access_kind="readonly")
    b.channel("help", "🆘-help-forum", "forum", "Ask a question. Search before posting.")
    b.channel("faq", "❓-faq", access_kind="readonly")
    b.channel("status", "🟢-status", "announcement", "Service status and incidents.", access_kind="readonly")
    b.category("💡 FEEDBACK", "members")
    b.channel("suggestions", "💡-suggestions")
    b.channel("bugs", "🐛-bug-reports")
    b.channel("changelog", "📝-changelog", access_kind="readonly")
    b.category("💬 COMMUNITY", "members")
    b.channel("general", "💬-general", slowmode=2)
    b.channel("showcase", "🏆-showcase")
    b.channel("bots", "🤖-bot-commands")
    tickets_cat = b.category("🎟️ TICKETS", "staff")
    b.channel("transcripts", "📄-ticket-transcripts", access_kind="staff")
    _staff_category(b)
    b.post("faq", "tpl-faq", pin=True)
    _self_roles(b, [("📢", "ping_updates", "Product Updates"), ("🟢", "ping_status", "Status Alerts"), ("🧪", "ping_betas", "Beta Testing"), ("📰", "ping_news", "Announcements")])
    b.ticket("open_ticket", "Support", ("admin", "mod", "helper"), category=tickets_cat, transcript="transcripts",
             welcome="Thanks for contacting support. Describe your issue and an agent will reply shortly.",
             button="Open a Ticket", questions=("What do you need help with?", "What have you already tried?"))
    _welcome(b, "Welcome to **{server}**, {user}! Need help? Open a ticket in the support channel.")
    b.levels(lv, "levels")
    _common_setup(b, "balanced", 2)
    return b.result({"id": "support", "name": "Support Server", "emoji": "🎫", "summary": "A help desk with tickets, FAQ, a help forum, status updates and feedback channels."})


def dating() -> dict:
    b = Builder()
    _staff_roles(b, (0xE74C3C, 0xE91E63, 0xFF69B4))
    b.role("bot", "Bots", 0x7289DA, [VIEW, "send_messages"])
    b.role("member", "Verified", 0xFF69B4, "member")
    b.role("booster", "Booster", 0xF47FFF, "member", hoist=True)
    b.role("age18", "18+", 0xBDC3C7, "member")
    b.role("sa_straight", "Straight", 0x95A5A6, "member")
    for key, name in (("o_gay", "Gay"), ("o_lesbian", "Lesbian"), ("o_bi", "Bisexual"), ("o_pan", "Pansexual"), ("o_other", "Other")):
        b.role(key, name, 0xBDC3C7, "member")
    for key, name, color in (("st_single", "Single", 0x2ECC71), ("st_taken", "Taken", 0xE74C3C), ("st_mingle", "Mingling", 0xF1C40F), ("st_friends", "Looking for Friends", 0x3498DB)):
        b.role(key, name, color, "member")
    for key, name in (("dm_open", "DMs Open"), ("dm_ask", "Ask to DM"), ("dm_closed", "DMs Closed")):
        b.role(key, name, 0x7F8C8D, "member")
    for key, name in (("reg_na", "North America"), ("reg_eu", "Europe"), ("reg_asia", "Asia"), ("reg_sa", "South America"), ("reg_af", "Africa"), ("reg_oce", "Oceania")):
        b.role(key, name, 0x95A5A6, "member")
    lv = _levels(b, ("Friendly", "Social", "Charming", "Popular", "Icon"), (5, 10, 20, 35, 50))
    _ping_roles(b, [("ping_news", "📢 Announcements", 0x3498DB), ("ping_events", "💞 Events", 0xE91E63), ("ping_vc", "🎙️ VC Hangouts", 0x9B59B6),
                    ("ping_revive", "💬 Chat Revive", 0x95A5A6)])
    _color_roles(b)
    _pronouns(b)
    _rules_embed(b, "tpl-rules", [
        "You must be 18 or older. Underage users are banned on sight.", "Consent and respect always. No harassment, pressure or stalking.",
        "No NSFW, sexual content or explicit images in any channel.", "Do not share anyone's photos, personal info or private messages.",
        "No scams, money requests, catfishing or fake profiles.", "Respect DM role choices. Ask before messaging and accept a no.",
        "Meeting offline is your responsibility. Be careful and tell a friend.", "Report anything suspicious to staff immediately."],
        0xE91E63, "This server is for adults only. Please keep it safe and kind.")
    b.embed("tpl-self-intro", "💞 About You", "Choose roles that describe you. Everything is optional except age verification.", 0xE91E63)
    b.embed("tpl-age", "🔞 Age Confirmation", "By taking this role you confirm that you are **18 or older**. False claims lead to an immediate ban.", 0xE74C3C)
    b.embed("tpl-status", "💘 Relationship Status", "Show your status. Pick one.", 0xFF69B4)
    b.embed("tpl-dm", "📨 DM Preferences", "Let people know how you like to be contacted. Pick one.", 0x7F8C8D)
    b.embed("tpl-region", "🌍 Region", "Pick your region so you can meet people in your timezone.", 0x3498DB)
    b.embed("tpl-orient", "🌈 Orientation", "Optional. Pick any that fit.", 0x9B59B6)
    _core_channels(b, None, None)
    b.category("💬 SOCIAL", "members")
    b.channel("general", "💬-general", slowmode=3)
    b.channel("introductions", "🙋-introductions", topic="Tell us about yourself. Keep it clean and safe.")
    b.channel("selfies", "📸-sfw-photos", topic="SFW photos only. No faces required.")
    b.channel("memes", "😂-memes")
    b.channel("advice", "❤️-dating-advice")
    b.channel("bots", "🤖-bot-commands")
    b.category("🎲 GAMES AND ICEBREAKERS", "members")
    b.channel("tod", "🎲-truth-or-dare", topic="Clean truth or dare only.")
    b.channel("wyr", "🤔-would-you-rather")
    b.channel("rate", "⭐-rate-and-ship")
    b.channel("counting", "🔢-counting")
    b.category("🌍 REGIONS", "members")
    b.channel("r_na", "🌎-north-america")
    b.channel("r_eu", "🌍-europe")
    b.channel("r_asia", "🌏-asia-and-oceania")
    b.category("🔊 VOICE", "voice")
    b.channel("vc1", "💬 Lounge", "voice")
    b.channel("vc2", "🎵 Music", "voice")
    b.channel("vc3", "🎮 Gaming Date", "voice", user_limit=4)
    b.channel("vc4", "🌙 Late Night", "voice")
    b.channel("stage", "🎤 Speed Meeting", "stage")
    b.category("🛡️ SAFETY", "staff")
    b.channel("safety", "🚨-safety-reports", topic="Private reports about unsafe behaviour.")
    b.channel("verify_log", "✅-verification-log")
    _ticket_area(b, "Safety Report", "Report a Problem", "Thank you for reporting. Staff will review this privately. Include usernames and what happened.",
                 ("Who are you reporting?", "What happened?"), "🚨 REPORTS", "🎟️ REPORT TICKETS")
    _staff_category(b)
    _self_roles(b, [("📢", "ping_news", "Announcements"), ("💞", "ping_events", "Events"), ("🎙️", "ping_vc", "VC Hangouts"), ("💬", "ping_revive", "Chat Revive")])
    b.panel("self_roles", "tpl-age", "button", [("✅", "age18", "I am 18 or older")])
    b.panel("self_roles", "tpl-status", "select", [("💚", "st_single", "Single"), ("❤️", "st_taken", "Taken"), ("💛", "st_mingle", "Mingling"), ("💙", "st_friends", "Looking for Friends")], mode="unique")
    b.panel("self_roles", "tpl-dm", "button", [("📬", "dm_open", "DMs Open"), ("❓", "dm_ask", "Ask to DM"), ("📪", "dm_closed", "DMs Closed")], mode="unique")
    b.panel("self_roles", "tpl-region", "select", [("🌎", "reg_na", "North America"), ("🌍", "reg_eu", "Europe"), ("🌏", "reg_asia", "Asia"),
                                                     ("🌎", "reg_sa", "South America"), ("🌍", "reg_af", "Africa"), ("🌏", "reg_oce", "Oceania")], mode="unique")
    b.panel("self_roles", "tpl-orient", "select", [("🏳️", "sa_straight", "Straight"), ("🏳️‍🌈", "o_gay", "Gay"), ("💗", "o_lesbian", "Lesbian"), ("💜", "o_bi", "Bisexual"),
                                                     ("💛", "o_pan", "Pansexual"), ("✨", "o_other", "Other")])
    _welcome(b, "Welcome to **{server}**, {user}! Confirm you are 18+ in self roles, read the safety rules and say hi.")
    b.levels(lv, "levels")
    _common_setup(b, "strict", 3)
    return b.result({"id": "dating", "name": "Dating and Social 18+", "emoji": "💞", "summary": "An adults-only social server with strict security, captcha verification, safety reports and profile roles."})


def study() -> dict:
    b = Builder()
    _staff_roles(b, (0xE74C3C, 0x3498DB, 0x1ABC9C))
    b.role("bot", "Bots", 0x7289DA, [VIEW, "send_messages"])
    b.role("member", "Student", 0x3498DB, "member")
    b.role("tutor", "Tutor", 0x2ECC71, "member", hoist=True)
    b.role("booster", "Booster", 0xF47FFF, "member", hoist=True)
    lv = _levels(b, ("Freshman", "Sophomore", "Junior", "Senior", "Graduate"), (5, 10, 20, 35, 50))
    _ping_roles(b, [("ping_news", "📢 Announcements", 0x3498DB), ("ping_sessions", "📚 Study Sessions", 0x2ECC71), ("ping_quiz", "🧠 Quizzes", 0x9B59B6),
                    ("ping_exams", "📝 Exam Alerts", 0xE74C3C)])
    for key, name in (("s_math", "Maths"), ("s_sci", "Science"), ("s_cs", "Computer Science"), ("s_lang", "Languages"), ("s_hum", "Humanities"), ("s_biz", "Business")):
        b.role(key, name, 0x3498DB, "member")
    for key, name in (("l_school", "High School"), ("l_college", "College"), ("l_grad", "Graduate"), ("l_self", "Self Learner")):
        b.role(key, name, 0x95A5A6, "member")
    _color_roles(b)
    _pronouns(b)
    _rules_embed(b, "tpl-rules", ["Be kind and supportive to every learner.", "Do not ask for or share answers to graded work.", "Keep study rooms quiet and on topic.",
                                  "No spam, advertising or unrelated chatter in subject channels.", "Credit sources and do not plagiarise.", "No NSFW or harmful content."],
                  0x3498DB)
    b.embed("tpl-self-intro", "🎓 Pick Your Roles", "Tell us what you study and what you want to be notified about.", 0x5865F2)
    b.embed("tpl-subjects", "📚 Subjects", "Pick the subjects you study.", 0x3498DB)
    b.embed("tpl-level", "🏫 Study Level", "Pick your level. One only.", 0x95A5A6)
    _core_channels(b, None, None)
    b.category("📚 SUBJECTS", "members")
    for key, name in (("math", "➗-maths"), ("science", "🔬-science"), ("cs", "💻-computer-science"), ("languages", "🌐-languages"),
                      ("humanities", "📖-humanities"), ("business", "💼-business"), ("homework", "🆘-homework-help")):
        b.channel(key, name)
    b.category("⏱️ FOCUS", "members")
    b.channel("goals", "🎯-daily-goals", topic="Post what you will finish today.")
    b.channel("progress", "✅-progress-log")
    b.channel("resources", "🔗-resources")
    b.channel("exams", "📝-exam-prep")
    b.category("💬 LOUNGE", "members")
    b.channel("general", "💬-general", slowmode=2)
    b.channel("breaks", "☕-break-room")
    b.channel("bots", "🤖-bot-commands")
    b.category("🔊 STUDY ROOMS", "voice")
    for i in range(1, 4):
        b.channel(f"room{i}", f"📖 Study Room {i}", "voice", user_limit=8)
    b.channel("silent", "🤫 Silent Focus", "voice")
    b.channel("pomodoro", "⏱️ Pomodoro", "voice")
    b.channel("stage", "🎤 Lecture Stage", "stage")
    _ticket_area(b, "Tutor Help", "Ask a Tutor", "A tutor will join shortly. Tell us the subject and what you are stuck on.",
                 ("Which subject?", "What are you stuck on?"), "🧑‍🏫 TUTORING", "🎟️ TUTOR TICKETS")
    _staff_category(b)
    _self_roles(b, [("📢", "ping_news", "Announcements"), ("📚", "ping_sessions", "Study Sessions"), ("🧠", "ping_quiz", "Quizzes"), ("📝", "ping_exams", "Exam Alerts")])
    b.panel("self_roles", "tpl-subjects", "select", [("➗", "s_math", "Maths"), ("🔬", "s_sci", "Science"), ("💻", "s_cs", "Computer Science"), ("🌐", "s_lang", "Languages"),
                                                       ("📖", "s_hum", "Humanities"), ("💼", "s_biz", "Business")])
    b.panel("self_roles", "tpl-level", "button", [("🏫", "l_school", "High School"), ("🎓", "l_college", "College"), ("🧑‍🎓", "l_grad", "Graduate"), ("📘", "l_self", "Self Learner")], mode="unique")
    _welcome(b, "Welcome to **{server}**, {user}! Pick your subjects in self roles and set a goal for today.")
    b.levels(lv, "levels", voice_xp_per_minute=15)
    _common_setup(b, "balanced", 2)
    return b.result({"id": "study", "name": "Study Server", "emoji": "📚", "summary": "Subject channels, focus rooms, daily goals and study level roles."})


def creator() -> dict:
    b = Builder()
    _staff_roles(b, (0xE74C3C, 0xE67E22, 0x1ABC9C))
    _base_roles(b, "Fan", 0x95A5A6)
    b.role("creator", "Creator", 0xFFD700, "member", hoist=True)
    b.role("sub", "Supporter", 0x9146FF, "member", hoist=True)
    b.role("booster", "Booster", 0xF47FFF, "member", hoist=True)
    lv = _levels(b, ("Viewer", "Fan", "Superfan", "Insider", "Legend"))
    _ping_roles(b, [("ping_live", "🔴 Live Streams", 0xE74C3C), ("ping_video", "🎬 New Videos", 0xFF0000), ("ping_posts", "📸 Social Posts", 0xE1306C),
                    ("ping_events", "🎉 Events", 0xF1C40F), ("ping_giveaways", "🎁 Giveaways", 0x2ECC71), ("ping_news", "📢 Announcements", 0x3498DB)])
    _color_roles(b)
    _pronouns(b)
    _rules_embed(b, "tpl-rules", ["Be kind to the creator and to other fans.", "No spam, self promotion or begging for follows.", "Keep spoilers in spoiler tags.",
                                  "No NSFW, hate or harassment.", "Respect copyright. Post only what you may share.", "Follow moderators and platform rules."], 0xFFD700)
    b.embed("tpl-self-intro", "🔔 Get Notified", "Pick which content you want a ping for.", 0x5865F2)
    _core_channels(b, None, None)
    b.category("🎬 CONTENT", "readonly")
    b.channel("live", "🔴-live-now", "announcement", "Stream alerts.")
    b.channel("videos", "🎬-new-videos", "announcement", "New upload alerts.")
    b.channel("socials", "📸-social-posts")
    b.channel("schedule", "📅-schedule")
    b.category("💬 FAN ZONE", "members")
    b.channel("general", "💬-general", slowmode=2)
    b.channel("fanart", "🎨-fan-art")
    b.channel("clips", "✂️-clips")
    b.channel("memes", "😂-memes")
    b.channel("suggestions", "💡-content-ideas")
    b.channel("bots", "🤖-bot-commands")
    b.category("⭐ SUPPORTERS", "supporter")
    b.channel("sup_chat", "⭐-supporter-lounge")
    b.category("🔊 VOICE", "voice")
    b.channel("vc1", "💬 Hangout", "voice")
    b.channel("vc2", "🎮 Play With Us", "voice")
    b.channel("stage", "🔴 Live Stage", "stage")
    _ticket_area(b, "Business Inquiry", "Contact the Team", "Thanks for getting in touch. Share the details and we will reply soon.",
                 ("What is this about?",), "📩 CONTACT", "🎟️ INQUIRIES")
    _staff_category(b)
    _self_roles(b, [("🔴", "ping_live", "Live Streams"), ("🎬", "ping_video", "New Videos"), ("📸", "ping_posts", "Social Posts"),
                    ("🎉", "ping_events", "Events"), ("🎁", "ping_giveaways", "Giveaways"), ("📢", "ping_news", "Announcements")])
    _welcome(b, "Welcome to **{server}**, {user}! Pick your pings in self roles so you never miss a stream.")
    b.levels(lv, "levels")
    _common_setup(b, "balanced", 2)
    return b.result({"id": "creator", "name": "Creator Server", "emoji": "🎬", "summary": "A fan hub with live and video alert channels, supporter lounge and content ping roles."})


def _dn(name: str, emoji: str) -> str:
    return f"♡﹒{name}﹒˚₊{emoji}𓂃﹗"


def _dc(name: str) -> str:
    return f"˚₊ {name} ₊˚"


def _rooms(b: "Builder", layout: list) -> Optional[str]:
    marked = None
    for entry in layout:
        title, kind, channels = entry[0], entry[1], entry[2]
        if title:
            key = b.category(title, kind)
            if len(entry) > 3 and entry[3]:
                marked = key
        for item in channels:
            ckey, name, emoji, ctype, access = item[:5]
            extra = item[5] if len(item) > 5 else {}
            b.channel(ckey, _dn(name, emoji), ctype, access_kind=access, **extra)
    return marked


def _bold_sans(text: str) -> str:
    out = []
    depth = 0
    for c in text:
        if c == "{":
            depth += 1
        elif c == "}":
            depth = max(0, depth - 1)
        if depth or c in "{}":
            out.append(c)
        elif "A" <= c <= "Z":
            out.append(chr(0x1D5D4 + ord(c) - 65))
        elif "a" <= c <= "z":
            out.append(chr(0x1D5EE + ord(c) - 97))
        elif "0" <= c <= "9":
            out.append(chr(0x1D7EC + ord(c) - 48))
        else:
            out.append(c)
    return "".join(out)


def _split_emoji(name: str, seps=(" ", "-")) -> tuple[str, str]:
    index = len(name)
    for sep in seps:
        found = name.find(sep)
        if found != -1:
            index = min(index, found)
    head, tail = name[:index], name[index + 1:]
    if head and not head[0].isascii():
        return head, tail
    return "", name


def _style_embeds(embeds: list) -> None:
    for embed in embeds:
        emoji, rest = _split_emoji(embed["title"], seps=(" ",))
        embed["title"] = f"{emoji} {_bold_sans(rest)}" if emoji else _bold_sans(embed["title"])
        for field in embed["fields"]:
            f_emoji, f_rest = _split_emoji(field["name"], seps=(" ",))
            field["name"] = f"{f_emoji} {_bold_sans(f_rest)}" if f_emoji else _bold_sans(field["name"])


ALL_PERMS = [
    "create_instant_invite", "kick_members", "ban_members", "manage_channels", "manage_guild", "add_reactions", "view_audit_log", "priority_speaker",
    "stream", "view_channel", "send_messages", "send_tts_messages", "manage_messages", "embed_links", "attach_files", "read_message_history",
    "mention_everyone", "use_external_emojis", "connect", "speak", "mute_members", "deafen_members", "move_members", "use_voice_activation",
    "change_nickname", "manage_nicknames", "manage_roles", "manage_webhooks", "manage_expressions", "use_application_commands", "request_to_speak",
    "manage_events", "manage_threads", "create_public_threads", "create_private_threads", "use_external_stickers", "send_messages_in_threads",
    "use_embedded_activities", "moderate_members", "view_creator_monetization_analytics", "use_soundboard", "create_expressions", "create_events",
    "use_external_sounds", "send_voice_messages", "create_polls", "use_external_apps",
]

FAM_PERMS = [
    "view_channel", "change_nickname", "create_instant_invite", "send_messages", "send_messages_in_threads", "add_reactions", "read_message_history",
    "use_application_commands", "connect", "speak", "stream", "use_voice_activation", "request_to_speak", "use_embedded_activities",
]


COLOR_SPECS = (
    ("c_strawberry", "strawberry-milk", "🍓", 0xFFB3C6), ("c_peach", "peach-soda", "🍑", 0xFFCBA4), ("c_lemon", "lemon-fizz", "🍋", 0xFFF3A3),
    ("c_matcha", "matcha", "🍵", 0xC8E6C0), ("c_mint", "mint-chip", "🍃", 0xB8F2E6), ("c_babyblue", "baby-blue", "🫧", 0xB8E0FF),
    ("c_lavender", "lavender", "🪻", 0xD4C1FF), ("c_cotton", "cotton-candy", "🍭", 0xFFC1F3),
    ("c_cherry", "cherry-red", "🍒", 0xFF6B81), ("c_midnight", "midnight", "🌌", 0x7A8CFF),
)

COLOR_ITEMS = [(emoji, key, slug, slug.replace("-", " ").title()) for key, slug, emoji, color in COLOR_SPECS]


SR_IMG_MAIN = "https://cdn.discordapp.com/attachments/1226123389173760022/1465603206360072283/4e8e17102cfa7905.jpg?ex=6ad863d9&is=6ad71259&hm=40d524420e70ca16de73543015f152defaa35911d6ce88615c507d906df9d639&"
SR_IMG_PRONOUNS = "https://media.tenor.com/6cLc9EayQfEAAAAe/pronoun-roles-roles.png"
SR_IMG_PINGS = "https://media.discordapp.net/attachments/1226123389173760022/1465597506099347559/discord_ping_roles.jpeg?ex=6ad9074a&is=6ad7b5ca&hm=3acdb43211ff66164fe10f4c57b4a451d9478fb60b1b728f922c659dba5def0d&"
SR_IMG_COLORS = "https://media.tenor.com/MWLgxOmCWTQAAAAM/discord.gif"
SR_IMG_DM = "https://media.tenor.com/QotbLpGdtu4AAAAM/dm-status-dm.gif"
SR_IMG_STATUS = "https://media.tenor.com/-__ERCW9KIUAAAAM/dm-status.gif"
SR_IMG_REGION = "https://media.tenor.com/CA1dzXn-6C8AAAAM/lcation-roles-location.gif"
SR_DEFAULT_IMG = "https://c.tenor.com/Whj-rEanRfIAAAAd/roles.gif"


def _cc_panel(b: "Builder", channel, trigger, title, desc, items, unique=False, color="#FFB3D9", create_roles=True, placeholder="Make a selection", image=SR_DEFAULT_IMG):
    names = {key: _dn(slug, emoji) for emoji, key, slug, label in items}
    if create_roles:
        for key, name in names.items():
            b.role(key, name, 0, [])
    options = []
    for emoji, key, slug, label in items:
        if unique:
            drops = "".join(f"{{removerole:{names[k]}}}" for k in names if k != key)
            response = f"{drops}{{addrole:{names[key]}}}You are now **{label}**."
        else:
            response = f"{{togglerole:{names[key]}}}Toggled **{label}**. Pick it again to remove it."
        options.append({"label": label, "description": "", "emoji": emoji, "title": "", "response": response})
    b.command(trigger, f"{{setimage:{image}}}{desc}", embed=True, color=color, title=title, options=options, placeholder=placeholder, allowed_roles=b.staff)
    if channel:
        b.post_command(channel, trigger)


def datingv2() -> dict:
    b = Builder()
    b.fixed_order = True
    b.staff = ("manager", "asstmanager", "mod", "trialmod", "partnermgr", "ticketteam", "eventhosts")

    def role(key, slug, emoji, color, perms=None, display=False):
        b.role(key, _dn(slug, emoji), color, perms or [], hoist=display)

    role("founders", "founders", "👑", 0xFFB3D9, ["administrator"], True)
    role("owner", "owner", "💎", 0xFFC2E0, ["administrator"], True)
    role("coowner", "co-owner", "💫", 0xFFD0E8, ["administrator"], True)
    role("quarantine", "quarantine", "🚫", 0x5C5C5C)
    role("admin", "admin", "🛡️", 0xE8A5FF, ["administrator"], True)
    role("manager", "manager", "🌸", 0xD9B3FF, [p for p in ALL_PERMS if p != "administrator"], True)
    role("asstmanager", "assistant-manager", "🌷", 0xC9C3FF, [
        "manage_channels", "manage_roles", "manage_nicknames", "manage_expressions", "manage_events", "manage_messages", "manage_threads",
        "kick_members", "ban_members", "moderate_members", "view_audit_log", "mention_everyone", "mute_members", "deafen_members", "move_members"], True)
    role("mod", "moderator", "🔨", 0xB3C6FF, [
        "kick_members", "ban_members", "moderate_members", "manage_messages", "manage_threads", "manage_nicknames", "mute_members", "deafen_members",
        "move_members", "view_audit_log"], True)
    role("trialmod", "trial-mod", "🌱", 0xB3E0FF, ["moderate_members", "manage_messages", "manage_nicknames", "mute_members"], True)
    role("partnermgr", "partnership-managers", "🤝", 0xFFD1A9, ["mention_everyone"], True)
    role("ticketteam", "ticket-team", "🎫", 0xB8F2E6, ["manage_threads"], True)
    role("eventhosts", "event-hosts", "🎉", 0xFFE0A3, ["create_events", "manage_events", "mute_members", "move_members"], True)
    role("staff", "staff", "⭐", 0xFFFFFF)
    for key, slug, emoji, color in COLOR_SPECS:
        role(key, slug, emoji, color)
    role("wealthy", "wealthy", "💸", 0xFFE29A, None, True)
    role("rich", "rich", "💰", 0xFFD1A9, None, True)
    role("partner", "partner-rep", "🤝", 0xFFCBA4, None, True)
    role("couples", "couples", "💑", 0xFFB3C6)
    role("birthday", "birthday", "🎂", 0xFFD6F0)
    lv = []
    for level, key, slug, emoji, perms in (
            (75, "lvl75", "lvl-75-servers-honey", "👑", None), (50, "lvl50", "lvl-50-sweetheart", "💎", None), (30, "lvl30", "lvl-30-heartthrob", "💘", None),
            (20, "lvl20", "lvl-20-charmer", "🌸", None), (10, "lvl10", "lvl-10-cutie", "🍓", ["attach_files"]), (5, "lvl5", "lvl-5-sweetie", "🍬", ["embed_links"])):
        role(key, slug, emoji, 0, perms, True)
        lv.append((level, key))
    lv.reverse()
    role("vgirl", "verified-girl", "🎀", 0xFFB3C6)
    role("vboy", "verified-boy", "🧢", 0xB8E0FF)
    role("vnb", "verified-nonbinary", "🌙", 0xD4C1FF)
    role("member", "fam", "🫶", 0xFFD6E8, FAM_PERMS)
    role("unverified", "unverified", "🔒", 0x9E9E9E)
    role("muted", "muted", "🔇", 0x7A7A7A)

    rule_options = [
        {"label": "Chat Rules", "description": "The rules you must follow while chatting", "emoji": "💬", "title": "Chat Rules", "response": (
            "**↪ | Good behavior**\n• Treat others with kindness, courtesy and respect. Listen when others speak and value different opinions.\n\n"
            "**↪ | Consent and respect**\n• No harassment, pressure, stalking or unwanted messages. A no is a no.\n\n"
            "**↪ | Spamming**\n• Spamming messages, links, files, emojis, stickers or GIFs is not allowed and leads to a mute.\n\n"
            "**↪ | Keep it SFW**\n• No NSFW, sexual content or explicit images anywhere.\n\n"
            "**↪ | Privacy**\n• Never share anyone's photos, personal details or screenshots of private conversations.\n\n"
            "**↪ | Scams and catfishing**\n• No scams, money requests or fake and stolen photos. Catfishing is a permanent ban.\n\n"
            "**↪ | Promoting and trading**\n• This server is not a marketplace. Advertising and invite links are only allowed in the places made for them.")},
        {"label": "DM Rules", "description": "How to message members respectfully", "emoji": "💌", "title": "DM Rules", "response": (
            "**↪ | Check the role**\n• Open DMs means you can message them. Ask First means use the ask-to-dm channel. Closed DMs means never.\n\n"
            "**↪ | Respect a no**\n• If someone declines or stops replying, leave them alone. Follow up once at most.\n\n"
            "**↪ | Keep it clean**\n• No explicit content, pressure or money requests in DMs. Report it with a ticket.")},
        {"label": "Voice Rules", "description": "The rules you must follow in voice channels", "emoji": "🎙️", "title": "Voice Chat Rules", "response": (
            "**↪ | Be respectful**\n• Do not shout, scream or talk over people. Abusing others in voice leads to a mute.\n\n"
            "**↪ | No adult content**\n• Streaming adult movies, videos, songs or any adult content leads to a ban.\n\n"
            "**↪ | No recording**\n• Recording people without their clear consent is not allowed.\n\n"
            "**↪ | Music and noise**\n• Do not play music with abusive terms in public rooms. Avoid loud or disruptive noise and mic spam.")},
        {"label": "Safety Rules", "description": "Stay safe and report problems", "emoji": "🛡️", "title": "Safety Rules", "response": (
            "**↪ | Never post ID**\n• Never post ID documents in any channel. Badge proof stays inside the private ticket.\n\n"
            "**↪ | Meeting offline**\n• Meeting offline is your own responsibility. Read the safety tips and tell a friend.\n\n"
            "**↪ | Reporting**\n• Report anything suspicious in the help desk. Use the safety desk for private or sensitive concerns.")},
        {"label": "Other Rules", "description": "More rules", "emoji": "✨", "title": "Other Rules", "response": (
            "**↪ | No hate**\n• No hate speech, discrimination or outing anyone's identity.\n\n"
            "**↪ | Ban evasion**\n• Evading a ban or mute with another account leads to a permanent ban.\n\n"
            "**↪ | Staff decisions**\n• Staff decisions are final. Ask a moderator politely if anything is unclear.")},
    ]
    b.command("rules-panel", (
        "As a valued member of our community, we kindly ask that you follow these rules to maintain a safe and enjoyable space for everyone 💖.\n\n"
        "**Discord Community Terms of Service and Guidelines**\n"
        "• As a part of Discord, please adhere to the Terms of Service and Community Guidelines.\n"
        "• You must be 18 or older to be a part of this server.\n\n"
        "**Server Rules Overview**\n"
        "• Use the menu below to read the detailed server rules. Staying here means you agree to them."),
        embed=True, color="#E91E63", title="Community Rules & Protocols", options=rule_options, allowed_roles=b.staff)
    def _decisions(here, items):
        return [{"label": label, "description": desc, "emoji": emoji, "title": "", "response": (
            f"{{sendchannel:{{{{channel:{here}}}}}|{emoji} **{label}** by {{user}} on {{msglink}}{extra}}}Recorded: {label}.")}
            for label, desc, emoji, extra in items]

    b.command("rq", (
        "{deletetrigger}**Requested by:** {user}\n\n{args}\n\n"
        "-# Moderators and managers: pick a decision below. Decisions are posted in this channel and never shown to the member."),
        embed=True, color="#3498DB", title="🔍 Review Request", placeholder="Record a decision", allowed_roles=("ticketteam", "trialmod", "mod", "asstmanager", "manager"),
        allowed_channels=("review_queue",), options=_decisions("review_queue", (
            ("Claim", "I am taking this one", "🙋", ""), ("Approve", "Approve the request", "✅", ""), ("Warn", "Warn the member", "⚠️", ""),
            ("Mute", "Mute the member", "🔇", ""), ("Ban", "Ban the member", "🔨", ""),
            ("Need more info", "Ask the ticket team for more", "❓", ""), ("Done", "Handled and closed", "✔️", ""))) + [
            {"label": "Escalate", "description": "Send to safety review", "emoji": "🚨", "title": "", "response": (
                "{sendchannel:{{channel:review_queue}}|🚨 **Escalate** by {user} on {msglink}}"
                "{sendchannel:{{channel:safety_review}}|🚨 **Escalated from review-queue** by {user}. Original request: {msglink}}Escalated to safety review.")}])
    b.command("safecase", (
        "{deletetrigger}**Opened by:** {user}\n\n{args}\n\n"
        "-# Assistant managers and managers only. Record the evidence, the decision, the follow-up with the reporter and the result."),
        embed=True, color="#E74C3C", title="🆘 Safety Case", placeholder="Record a decision", allowed_roles=("asstmanager", "manager"),
        allowed_channels=("safety_review",), options=_decisions("safety_review", (
            ("Claim", "I am leading this case", "🙋", ""), ("Need more evidence", "Collect more before deciding", "🔎", ""),
            ("Warn", "Warn the member", "⚠️", ""), ("Ban", "Ban the member", "🔨", ""), ("Quarantine", "Quarantine the member", "🚫", ""),
            ("Report to Discord", "Report to Discord Trust and Safety", "📨", ""), ("Follow up with reporter", "Contact the member who reported", "💬", ""),
            ("Close with result", "Case closed, result noted", "✔️", ""))))
    b.embed("tpl-self-intro", "💞 Make Your Profile", "Pick roles that describe you below. Everything is optional.", 0xFFB3D9)
    b.embed("tpl-guide", "🧭 Server Guide", "Here is where to find everything.", 0x9B59B6, [
        ("🥤 Verify", "Pass the quick check in the verify channel to get the Fam role and unlock the server.", 0),
        ("🌷 Roles", "Pick your DM status, what you are looking for, status, pronouns, age range, region, pings and a colour.", 0),
        ("🧸 Meet people", "Introduce yourself, make a post in the profiles forum and use looking-for and matchmaking.", 0),
        ("💌 DMs", "Check someone's DM role first. Use ask-to-dm when they are set to Ask First.", 0),
        ("🎀 Verified badge", "Optional. Open a ticket in the verified badge channel to get Verified Girl, Boy or Nonbinary.", 0),
        ("🎟️ Help desk", "Support, reports, safety concerns, partnerships and staff applications all use tickets.", 0)])
    b.embed("tpl-faq", "🍡 FAQ", "Quick answers to common questions.", 0xE91E63, [
        ("How do I get in?", "Press the button in the verify channel.", 0),
        ("How do I unlock GIFs and uploads?", "Level 5 unlocks GIFs and link previews. Level 10 unlocks attaching photos and videos.", 0),
        ("How do I DM someone?", "Check their DM role. If it says Ask First, use the ask-to-dm channel.", 0),
        ("Someone is bothering me", "Block them and open a report or safety ticket in the help desk.", 0),
        ("Are verified badges guaranteed?", "No. A badge lowers the catfishing risk but is not a guarantee.", 0)])
    b.embed("tpl-invite", "🔗 Invite Rewards", "Bring your friends and get rewarded.", 0xFF69B4, [
        ("How it works", "Share your own invite link. Staff reward active inviters with perks.", 0),
        ("Fair play", "Fake or bought invites are not counted and may lead to a ban.", 0)])
    b.embed("tpl-safety-tips", "🛡️ Safety Tips", "Dating online needs care.", 0x2ECC71, [
        ("Protect your details", "Never share your address, workplace, full name or financial info.", 0),
        ("Verify before you trust", "A verified badge helps, but ask for a video call before meeting.", 0),
        ("Meeting in person", "Meet in a public place, tell a friend and arrange your own transport.", 0),
        ("Never send money", "Anyone asking for money, gift cards or crypto is a scammer. Report them.", 0),
        ("Trust your instincts", "If something feels wrong, stop talking and open a safety ticket.", 0),
        ("In danger", "If you are in immediate danger, contact your local emergency services first.", 0)])
    b.embed("tpl-verify-info", "🎀 Verified Badge", "An optional badge that shows a real person is behind the profile.", 0xFFB3C6, [
        ("1. Open a ticket", "Press the button and say which badge you want: Girl, Boy or Nonbinary.", 0),
        ("2. Send proof", "The ticket team will tell you what to send. Proof stays inside the private ticket and is deleted after approval. No ID is ever needed.", 0),
        ("3. Get your badge", "The ticket team gives you the badge role and closes the ticket.", 0),
        ("Note", "A badge lowers the catfishing risk but is not a guarantee.", 0)])
    b.embed("tpl-profile", "💘 Profile Format", "Copy this into a post in the profiles forum. One post per member, edit instead of reposting.", 0xE91E63, [
        ("Template", "**Name or nickname:**\n**Age:**\n**Pronouns:**\n**Region:**\n**Interests:**\n**Looking for:**\n**About me:**\n**DM status:**", 0),
        ("Rules", "SFW only. No contact details. No photos of other people.", 0)])
    b.embed("tpl-dm-rules", "📌 DM Rules", "Direct messages are a privilege. Keep them respectful.", 0xE91E63, [
        ("Check the role", "Open DMs means you can message them. Ask First means use ask-to-dm. Closed DMs means never.", 0),
        ("Respect a no", "If someone declines or stops replying, leave them alone.", 0),
        ("Keep it SFW", "No explicit content, pressure or money requests in DMs. Report it with a ticket.", 0)])
    b.embed("tpl-dm-ask", "💌 Ask to DM", "Want to message someone who is set to Ask First? Ask here.", 0xE91E63, [
        ("How to ask", "Post `@member hi, I liked your intro. May I DM you?` with one friendly reason.", 0),
        ("If they say yes", "Send one respectful message and keep the chat kind.", 0),
        ("If they say no or ignore", "Leave it. Follow up once at most and never DM again.", 0)])
    b.embed("tpl-intro", "🙋 Introduce Yourself", "Say hi and tell us who you are.", 0x9B59B6, [
        ("Suggested format", "**Name:**\n**Age:**\n**Region:**\n**Interests:**\n**Looking for:**\n**Fun fact:**", 0),
        ("Keep it safe", "No contact details, no photos of other people and no explicit content.", 0)])
    b.embed("tpl-partner-info", "📋 Partnerships", "We partner with friendly, safe, 18+ communities.", 0x1ABC9C, [
        ("Requirements", "Active community, clear rules, adults only and a good moderation team.", 0),
        ("How to apply", "Open a ticket in the partnership channel of the help desk.", 0),
        ("Ad format", "Keep ads short, SFW and with a single invite link. Only partner reps can post in the ads channel.", 0),
        ("Removal", "Partnerships end if either server breaks the agreement.", 0)])
    b.embed("tpl-perks", "✨ Perks", "What you get for boosting, levelling and inviting.", 0xFFD700, [
        ("Boost perks", "**Rich** for 1 boost and **Wealthy** for 2 boosts, booster-only colours, a custom role request channel and the personal diary.", 0),
        ("Level perks", "Level 5 unlocks GIFs and link previews. Level 10 unlocks attaching media. Level 50 unlocks the personal diary.", 0),
        ("Invite rewards", "Invite friends with your own link and ask staff about rewards.", 0),
        ("Keep it", "If you stop boosting your roles are removed after 24 hours and come back if you boost again.", 0)])
    b.embed("tpl-custom-role", "🧵 Custom Roles", "Boosters can make their own role.", 0xF47FFF, [
        ("Create", "Use `!booster role create <name> [colour]`.", 0),
        ("Change", "Edit your role later with `!booster role name`, `colour` and `icon`.", 0),
        ("Need help", "Ask staff here if your role request is blocked.", 0)])
    b.embed("tpl-safety-desk", "🆘 Safety Desk", "For sensitive concerns. Only senior staff can see these tickets.", 0xE74C3C, [
        ("Use this for", "Harassment, unwanted DMs, catfishing or impersonation, threats or blackmail, scams and anything that feels unsafe.", 0),
        ("In danger", "If you are in immediate danger, contact your local emergency services first.", 0)])
    b.embed("tpl-staff-resources", "📂 Staff Resources", "Rules, training and guides for the team.", 0xE74C3C, [
        ("Be fair", "Treat every member equally and explain your actions.", 0),
        ("Second opinions", "Ticket team: in review-queue use `!rq <short summary>`. Moderators and managers pick a decision from the menu and it is logged there.", 0),
        ("Safety cases", "Assistant managers and managers: in safety-review use `!safecase <summary>` and record the decision, follow-up and result. Never discuss these in review-queue.", 0),
        ("Stay private", "Never share tickets, proof or reports outside staff channels. Discuss safety cases in safety-review.", 0),
        ("Log actions", "Use Soward moderation commands so every action is logged.", 0),
        ("Ask when unsure", "Ask a manager before big actions.", 0)])
    b.embed("tpl-ticket-info", "🛟 Support", "Press the button below to open a private ticket with staff.", 0x3498DB)

    voice_cat = _rooms(b, [
        ("˚₊ start here ₊˚", "members", [
            ("welcome", "welcome", "🎀", "text", "readonly"),
            ("rules", "rules", "📜", "text", "gate"),
            ("verify", "verify", "🥤", "text", "gate"),
            ("self_roles", "roles", "🌷", "text", "readonly"),
            ("guide", "server-guide", "🗺️", "text", "readonly"),
            ("announcements", "announcements", "📢", "announcement", "gate")]),
        ("˚₊ meet ₊˚", "members", [
            ("introductions", "introductions", "🧸", "text", None),
            ("profiles", "profiles", "🪞", "forum", None),
            ("lfd", "looking-for-dates", "💘", "text", None),
            ("friends", "looking-for-friends", "🫶", "text", None),
            ("matchmaking", "matchmaking", "💞", "text", None),
            ("lgbtq", "lgbtq-corner", "🌈", "text", None)]),
        ("˚₊ dm center ₊˚", "members", [
            ("dm_rules", "dm-rules", "📌", "text", "readonly"),
            ("dm_requests", "ask-to-dm", "💌", "text", None),
            ("socials", "share-socials", "📱", "text", None)]),
        ("˚₊ lounge ₊˚", "members", [
            ("general", "general", "☁️", "text", None),
            ("dq", "daily-question", "❓", "text", None),
            ("flirt", "flirty-chat", "😽", "text", None),
            ("selfies", "selfies", "📸", "text", None),
            ("media", "media", "🖼️", "text", None),
            ("memes", "memes", "🐸", "text", None),
            ("vent", "vent", "🫧", "text", None),
            ("diary", "personal-diary", "📔", "forum", "roles:wealthy,rich,lvl50,lvl75")]),
        ("˚₊ interests ₊˚", "members", [
            ("int_gaming", "gaming", "🎮", "text", None),
            ("int_anime", "anime", "🍥", "text", None),
            ("int_music", "music", "🎧", "text", None),
            ("int_movies", "movies-and-tv", "🍿", "text", None),
            ("int_food", "food", "🍜", "text", None),
            ("int_art", "art", "🎨", "text", None),
            ("int_fitness", "fitness", "🏋️", "text", None),
            ("int_travel", "travel", "✈️", "text", None),
            ("int_books", "books", "📚", "text", None)]),
        ("˚₊ couples ₊˚", "members", [
            ("couples_corner", "couples-corner", "💍", "text", None),
            ("rel_advice", "relationship-advice", "🕊️", "text", None),
            ("date_ideas", "date-ideas", "🌹", "text", None)]),
        ("˚₊ events ₊˚", "members", [
            ("events", "events", "🎉", "announcement", "readonly"),
            ("birthdays", "birthdays", "🎂", "text", None),
            ("giveaways", "giveaways", "🎁", "text", None),
            ("polls", "polls", "📊", "text", None),
            ("speed_dating", "speed-dating", "⏳", "voice", "voice"),
            ("game_night", "game-night", "🎲", "voice", "voice")]),
        ("˚₊ activities ₊˚", "members", [
            ("bots", "bot-commands", "🤖", "text", None),
            ("games", "games", "🕹️", "text", None),
            ("counting", "counting", "🔢", "text", None),
            ("icebreakers", "icebreakers", "🎯", "text", None),
            ("rizz", "rizz-and-ship", "😎", "text", None),
            ("confessions", "confessions", "🤫", "text", "readonly")]),
        ("˚₊ voice ₊˚", "voice", [
            ("vc1", "lounge", "🎙️", "voice", None),
            ("date1", "date night 1", "🕯️", "voice", None, {"user_limit": 2}),
            ("date2", "date night 2", "🍷", "voice", None, {"user_limit": 2}),
            ("couples_vc", "couples vc", "💑", "voice", "roles:couples"),
            ("vc_music", "music & chill", "🎶", "voice", None),
            ("vc_gaming", "gaming", "🎮", "voice", None),
            ("vc_movie", "movie night", "🍿", "voice", None),
            ("vc_late", "late night & sleep", "🌌", "voice", None),
            ("stage", "stage", "🎤", "stage", None),
            ("jtc_hub", "create vc", "➕", "voice", "hub"),
            ("vc_afk", "afk", "💤", "voice", None),
            ("vc_chat", "vc-chat", "💬", "text", "members")], True),
        ("˚₊ partners ₊˚", "members", [
            ("partner_info", "partner-info", "📋", "text", "readonly"),
            ("partners", "partners", "🤝", "announcement", "readonly"),
            ("ads", "ads", "📣", "text", "roles:partner,partnermgr"),
            ("partner_chat", "partner-chat", "🫂", "text", "roles:partner,partnermgr")]),
        ("˚₊ boosters & levels ₊˚", "members", [
            ("perks", "perks", "✨", "text", "readonly"),
            ("level_up", "level-up", "🆙", "text", "readonly"),
            ("custom_role_req", "custom-role-requests", "🧵", "text", "roles:wealthy,rich")]),
        ("˚₊ help desk ₊˚", "members", [
            ("support", "support", "🛟", "text", "readonly"),
            ("verified_badge", "verified-badge", "🎀", "text", "readonly"),
            ("report", "report", "🚨", "text", "readonly"),
            ("safety_desk", "safety-desk", "🆘", "text", "readonly"),
            ("partnership", "partnership", "🤝", "text", "readonly"),
            ("applications", "staff-applications", "📝", "text", "readonly"),
            ("suggestions", "suggestions", "💡", "text", None),
            ("safety_tips", "safety-tips", "🛡️", "text", "readonly")]),
    ])

    def ticket_category(title, kind, attach=False):
        key = b.category(_dc(title), kind)
        if attach:
            b._cat["overwrites"]["member"] = {"allow": ["attach_files", "embed_links"], "deny": [VIEW]}
        return key

    cat_support = ticket_category("support tickets", "only:ticketteam,mod,asstmanager,manager", True)
    cat_verify = ticket_category("verification tickets", "only:ticketteam,asstmanager,manager", True)
    cat_report = ticket_category("report tickets", "only:ticketteam,mod,asstmanager,manager", True)
    cat_safety = ticket_category("safety tickets", "only:asstmanager,manager", True)
    cat_partner = ticket_category("partner tickets", "only:partnermgr,manager")
    cat_app = ticket_category("application tickets", "only:asstmanager,manager")
    _rooms(b, [
        ("˚₊ ticket transcripts ₊˚", "staff", [
            ("transcripts", "ticket-transcripts", "🧾", "text", None),
            ("safety_tx", "safety-transcripts", "🔐", "text", "only:asstmanager,manager", {"merge": False})]),
        ("˚₊ logs ₊˚", "staff", [
            ("l_mod", "mod-logs", "🔨", "text", None),
            ("l_message", "message-logs", "✉️", "text", None),
            ("l_member", "member-logs", "👥", "text", None),
            ("l_security", "security-logs", "🛡️", "text", None),
            ("l_server", "server-logs", "🗄️", "text", None)]),
        ("˚₊ staff ₊˚", "staff", [
            ("staff_announcements", "staff-announcements", "🔔", "announcement", None),
            ("staff_chat", "staff-chat", "🔒", "text", None),
            ("mod_chat", "mod-chat", "🛠️", "text", None),
            ("staff_resources", "staff-resources", "📂", "text", None),
            ("review_queue", "review-queue", "🔍", "text", None),
            ("safety_review", "safety-review", "🆘", "text", "only:asstmanager,manager", {"merge": False}),
            ("partner_mgmt", "partner-management", "🤲", "text", None),
            ("event_planning", "event-planning", "🗓️", "text", None),
            ("staff_cmds", "staff-commands", "⌨️", "text", None),
            ("staff_meeting", "staff-meeting", "🎙️", "voice", None)]),
    ])
    b.logs = {"mod": {"$channel": "l_mod"}, "message": {"$channel": "l_message"}, "member": {"$channel": "l_member"},
              "security": {"$channel": "l_security"}, "server": {"$channel": "l_server"}}
    for cat in b.categories:
        if cat["overwrites"] is not None:
            cat["overwrites"]["muted"] = _ow(deny=SEND + ["speak"])

    b.post_command("rules", "rules-panel", pin=True)
    b.post("safety_tips", "tpl-safety-tips", pin=True)
    b.post("guide", "tpl-guide", pin=True)
    b.post("guide", "tpl-faq", pin=True)
    b.post("guide", "tpl-invite")
    b.post("self_roles", "tpl-self-intro")
    b.post("lfd", "tpl-profile", pin=True)
    b.post("dm_rules", "tpl-dm-rules", pin=True)
    b.post("dm_requests", "tpl-dm-ask", pin=True)
    b.post("introductions", "tpl-intro", pin=True)
    b.post("partner_info", "tpl-partner-info", pin=True)
    b.post("perks", "tpl-perks", pin=True)
    b.post("custom_role_req", "tpl-custom-role", pin=True)
    b.post("verified_badge", "tpl-verify-info", pin=True)
    b.post("safety_desk", "tpl-safety-desk", pin=True)
    b.post("staff_resources", "tpl-staff-resources", pin=True)
    b.post("support", "tpl-ticket-info")

    _cc_panel(b, None, "sr-dm", "💌 DM Status", "Let people know how you like to be contacted. Pick one.", [
        ("🟢", "dm_open", "open-dms", "Open DMs"), ("🟡", "dm_ask", "ask-first", "Ask First"), ("🔴", "dm_closed", "closed-dms", "Closed DMs")], True, "#7F8C8D", image=SR_IMG_DM)
    _cc_panel(b, None, "sr-looking", "🔎 Looking For", "What are you here for? Pick any. Pick again to remove one.", [
        ("💘", "lf_dates", "looking-for-dates", "Dates"), ("🫶", "lf_friends", "looking-for-friends", "Friends"),
        ("💞", "lf_any", "open-to-anything", "Open to Anything"), ("☁️", "lf_vibing", "just-vibing", "Just Vibing")], False, "#E91E63")
    _cc_panel(b, None, "sr-status", "💍 Relationship Status", "Show your status. Pick one.", [
        ("🕊️", "st_single", "single", "Single"), ("💍", "st_taken", "taken", "Taken"), ("🌀", "st_complicated", "its-complicated", "It's Complicated")], True, "#FF69B4", image=SR_IMG_STATUS)
    _cc_panel(b, None, "sr-pronouns", "🏷️ Pronouns", "Show your pronouns. Pick any. Pick again to remove one.", [
        ("🌷", "p_she", "she-her", "She/Her"), ("🌊", "p_he", "he-him", "He/Him"), ("🌙", "p_they", "they-them", "They/Them")], False, "#BDC3C7", image=SR_IMG_PRONOUNS)
    _cc_panel(b, None, "sr-orientation", "🌈 Orientation", "Optional. Pick any that fit. Pick again to remove one.", [
        ("🤍", "o_straight", "straight", "Straight"), ("💙", "o_gay", "gay", "Gay"), ("🧡", "o_lesbian", "lesbian", "Lesbian"),
        ("💜", "o_bi", "bisexual", "Bisexual"), ("💛", "o_pan", "pansexual", "Pansexual"), ("🖤", "o_ace", "asexual", "Asexual"),
        ("🤎", "o_questioning", "questioning", "Questioning")], False, "#9B59B6")
    _cc_panel(b, None, "sr-age", "🎂 Age Range", "Pick your age range. One only.", [
        ("🍬", "age_18", "18-20", "18-20"), ("🍓", "age_21", "21-24", "21-24"), ("🍷", "age_25", "25-plus", "25+")], True, "#95A5A6")
    _cc_panel(b, None, "sr-region", "🌍 Region", "Pick your region. One only.", [
        ("🏯", "reg_asia", "asia", "Asia"), ("🏰", "reg_eu", "europe", "Europe"), ("🗽", "reg_na", "north-america", "North America"),
        ("🌴", "reg_sa", "south-america", "South America"), ("🦁", "reg_af", "africa", "Africa"), ("🕌", "reg_me", "middle-east", "Middle East"),
        ("🏝️", "reg_oce", "oceania", "Oceania")], True, "#3498DB", image=SR_IMG_REGION)
    _cc_panel(b, None, "sr-pings", "🔔 Ping Roles", "Choose what you want to be pinged for. Pick again to remove one.", [
        ("📢", "ping_news", "announcement-ping", "Announcements"), ("🎉", "ping_events", "event-ping", "Events"),
        ("🎁", "ping_giveaways", "giveaway-ping", "Giveaways"), ("⏳", "ping_speed", "speed-dating-ping", "Speed Dating"),
        ("🎲", "ping_game", "game-night-ping", "Game Night"), ("🎬", "ping_movie", "movie-night-ping", "Movie Night"),
        ("❓", "ping_dq", "daily-question-ping", "Daily Question"), ("💬", "ping_revive", "chat-revive", "Chat Revive"),
        ("🤝", "ping_partner", "partner-ping", "Partner Ping")], False, "#3498DB", image=SR_IMG_PINGS)
    _cc_panel(b, None, "sr-colors", "🎨 Name Colors", "Pick one colour for your name. Choosing a new one swaps the old one.", COLOR_ITEMS[:8], True, "#FFB3C6", False, image=SR_IMG_COLORS)
    _cc_panel(b, "custom_role_req", "sr-boostcolors", "🍒 Booster Colors", "Exclusive colours for boosters. Choosing a new one swaps the old one.", COLOR_ITEMS[8:], True, "#FF6B81", False, image=SR_IMG_COLORS)

    b.command("sr-hub", (
        f"{{setimage:{SR_IMG_MAIN}}}Customize Your Profile With Our Self Roles"),
        embed=True, color="#FFB3D9", title="CUSTOMIZE", placeholder="Personization Options", allowed_roles=b.staff, options=[
        {"label": label, "description": desc, "emoji": emoji, "title": "", "response": "", "link": link} for label, desc, emoji, link in (
            ("Pronouns", "What are your pronouns?", "🏷️", "sr-pronouns"), ("DM Status", "How do you like to be contacted?", "💌", "sr-dm"),
            ("Relationship Status", "Are you single or taken?", "💍", "sr-status"), ("Looking For", "What are you here for?", "🔎", "sr-looking"),
            ("Orientation", "Optional", "🌈", "sr-orientation"), ("Age", "How old are you?", "🎂", "sr-age"),
            ("Region", "Where are you from?", "🌍", "sr-region"), ("Notifications", "Ping roles", "🔔", "sr-pings"),
            ("Name Colors", "Pick a colour for your name", "🎨", "sr-colors"))])
    b.post_command("self_roles", "sr-hub", pin=True)

    b.ticket("verified_badge", "Verified Badge", ("ticketteam", "asstmanager", "manager"), category=cat_verify, transcript="transcripts",
             welcome="Thanks for starting verification. The ticket team will tell you what to send. Proof stays in this ticket and is deleted after approval. Never share ID documents.",
             button="Get Verified", questions=("Which badge: Girl, Boy or Nonbinary?", "Anything we should know?"))
    b.ticket("support", "Support", ("ticketteam", "mod", "asstmanager", "manager"), category=cat_support, transcript="transcripts",
             welcome="Thanks for reaching out. A staff member will help you shortly.", button="Get Support", questions=("What do you need help with?",))
    b.ticket("report", "Report", ("ticketteam", "mod", "asstmanager", "manager"), category=cat_report, transcript="transcripts",
             welcome="Thank you for reporting. This is private. Include usernames, links and what happened.", button="Report a Member",
             questions=("Who are you reporting?", "Message link or where it happened?", "What happened?"))
    b.ticket("safety_desk", "Safety Desk", ("asstmanager", "manager"), category=cat_safety, transcript="safety_tx",
             welcome="Thank you for telling us. Only senior staff can see this ticket. If you are in immediate danger, contact your local emergency services first.",
             button="Open a Safety Ticket", questions=("What kind of issue is this?", "What happened?"))
    b.ticket("partnership", "Partnership", ("partnermgr", "manager"), category=cat_partner, transcript="transcripts",
             welcome="Thanks for your interest. Share your server details and what you propose.", button="Partner With Us",
             questions=("Server name and invite?", "Member count?", "What do you propose?"))
    b.ticket("applications", "Staff Application", ("asstmanager", "manager"), category=cat_app, transcript="transcripts",
             welcome="Thanks for applying. Answer the questions and a manager will review your application.", button="Apply for Staff",
             questions=("How old are you?", "Why do you want to join staff?", "Do you have moderation experience?", "How many hours can you give each week?"))

    b.embed("tpl-welcome", "👋 Welcome to {server}!", "Pass verification, pick your roles in the roles channel and read the safety tips. Get an optional **Verified Girl, Boy or Nonbinary** badge from the verified badge channel.", 0xFF69B4, footer="Member #{membercount}")
    b.greeting("join", "welcome", "{user}", embed="tpl-welcome")
    b.greeting("leave", "welcome", "**{username}** has left **{server}**. We are now **{membercount}** members.", enabled=0)
    b.greeting("boost", "general", "💜 Thank you {user} for boosting **{server}**! You unlocked the booster perks.")
    b.levels(lv, "level_up", voice_xp_per_minute=12)
    b.tables["jtc_hubs"] = [{"channel_id": {"$channel": "jtc_hub"}, "category_id": {"$channel": voice_cat}, "name_template": "♡﹒{user}'s room﹒˚₊🎧𓂃﹗", "user_limit": 0, "bitrate": 0}]
    b.tables["booster_config"] = [{
        "enabled": 1, "tier_mode": "count", "stack_mode": "highest", "base_role_id": None, "grace_hours": 24, "custom_enabled": 1,
        "custom_min": 1, "allow_name": 1, "allow_color": 1, "allow_icon": 1, "allow_hoist": 0, "allow_perms": 0, "position_mode": "below",
        "position_ref_id": None, "cooldown_hours": 6, "name_filter": 1, "max_name_len": 24, "remove_on_unboost": 1, "restore_on_reboost": 1,
    }]
    b.tables["booster_tiers"] = [{"boosts": 1, "role_id": {"$role": "rich"}}, {"boosts": 2, "role_id": {"$role": "wealthy"}}]
    b.tables["xp_multipliers"] = [
        {"scope_type": "role", "scope_id": {"$role": "rich"}, "multiplier": 1.25, "label": "booster"},
        {"scope_type": "role", "scope_id": {"$role": "wealthy"}, "multiplier": 1.5, "label": "booster"},
    ]
    b.settings["booster_blocked_names"] = ["admin", "mod", "staff", "owner", "founder", "verified", "fam", "moderator", "support", "verifier", "official", "manager"]
    b.settings["count_channel_id"] = {"$channel": "counting"}
    b.settings["dq_channel_id"] = {"$channel": "dq"}
    b.settings["dq_role_id"] = {"$role": "ping_dq"}
    b.settings["bday_channel_id"] = {"$channel": "birthdays"}
    b.settings["bday_role_id"] = {"$role": "birthday"}
    b.settings["confess_channel_id"] = {"$channel": "confessions"}
    b.settings["sug_channel_id"] = {"$channel": "suggestions"}
    b.post_special("confessions", "confess_panel", pin=True)
    b.settings["verification_gate_role_id"] = {"$role": "unverified"}
    b.settings["antinuke_quarantine_role_id"] = {"$role": "quarantine"}
    b.flags["security_preset"] = "strict"
    b.flags["everyone_perms"] = []
    b.flags["quarantine_role"] = "quarantine"
    _verify(b, "verify", 3)
    _style_embeds(b.embeds)
    return b.result({"id": "datingv2", "name": "Dating and Social 18+ v2 (Premium)", "emoji": "💞", "premium": True,
                     "summary": "Premium. A full 18+ dating blueprint: styled staff, colour, level, verified badge and self roles, gate and Fam permissions, six ticket panels with per-type categories and a private safety desk, DM center, partners, Join to Create voice and Booster Perks."})


BUILDERS = {"community": community, "gaming": gaming, "support": support, "dating": dating, "datingv2": datingv2, "study": study, "creator": creator}


def ids() -> list[str]:
    return list(BUILDERS)


def get(preset_id: str) -> Optional[dict]:
    fn = BUILDERS.get(preset_id.lower())
    return copy.deepcopy(fn()) if fn else None


PREMIUM = {"datingv2"}


def is_premium_preset(preset_id: str) -> bool:
    return preset_id.lower() in PREMIUM


def all_meta() -> list[dict]:
    return [BUILDERS[i]()["meta"] for i in BUILDERS]
