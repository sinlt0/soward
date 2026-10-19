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
        return {"everyone": _ow(deny=[VIEW]), **{k: grant for k in keys}, **{k: _ow([VIEW, "send_messages", "connect", "speak"]) for k in staff}}
    staff_view = {k: _ow([VIEW, "send_messages", "connect", "speak"]) for k in staff}
    if kind == "members":
        return {"everyone": _ow(deny=[VIEW]), "member": _ow([VIEW]), **staff_view}
    if kind == "readonly":
        return {"everyone": _ow(deny=[VIEW] + SEND), "member": _ow([VIEW], SEND), **staff_view}
    if kind == "staff":
        return {"everyone": _ow(deny=[VIEW]), **staff_view}
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

    def channel(self, key, name, kind="text", topic=None, access_kind=None, slowmode=0, user_limit=0):
        entry = {"key": key, "name": name, "type": kind, "overwrites": access(access_kind, self.staff) if access_kind else None}
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

    def result(self, meta: dict) -> dict:
        return {
            "version": 1, "meta": meta, "roles": self.roles, "categories": self.categories, "settings": self.settings,
            "tables": self.tables, "greetings": self.greetings, "logs": {}, "nsfw": None, "embeds": self.embeds,
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


def _group(b: Builder, channel, embed_name, title, desc, items, ptype="select", mode="normal", color=0x5865F2, max_roles=0, ping=False):
    for emoji, key, label, rcolor in items:
        b.role(key, label, rcolor, "member", mentionable=ping)
    b.embed(embed_name, title, desc, color)
    b.panel(channel, embed_name, ptype, [(emoji, key, label) for emoji, key, label, _ in items], mode=mode, max_roles=max_roles)


def datingv2() -> dict:
    b = Builder()
    b.staff = ("admin", "hmod", "mod", "verifier", "helper")
    b.role("admin", "Admin", 0xE74C3C, "admin", hoist=True)
    b.role("hmod", "Head Moderator", 0xE91E63, "mod", hoist=True)
    b.role("mod", "Moderator", 0xFF69B4, "mod", hoist=True)
    b.role("verifier", "Verifier", 0x1ABC9C, ["moderate_members", "manage_messages", "manage_roles", "manage_nicknames"], hoist=True)
    b.role("helper", "Helper", 0xF1C40F, "helper", hoist=True)
    b.role("bot", "Bots", 0x7289DA, [VIEW, "send_messages"])
    b.role("member", "Verified", 0xFF69B4, "member")
    b.role("age18", "18+", 0xBDC3C7, "member")
    b.role("vgirl", "Verified Girl", 0xFF4DA6, "member", hoist=True)
    b.role("vguy", "Verified Guy", 0x4DA6FF, "member", hoist=True)
    b.role("vnb", "Verified Non-Binary", 0xB57EDC, "member", hoist=True)
    b.role("booster", "Booster", 0xF47FFF, "member", hoist=True)
    b.role("vip", "VIP", 0xFFD700, "member", hoist=True)
    b.role("vipplus", "VIP+", 0xFFA500, "member", hoist=True)
    b.role("tier1", "Rich", 0xF1C40F, "member", hoist=True)
    b.role("tier2", "Wealthy", 0xF39C12, "member", hoist=True)
    lv = _levels(b, ("Friendly", "Social", "Charming", "Popular", "Trending", "Star", "Icon", "Legend"), (5, 10, 20, 30, 45, 60, 80, 100))
    lv = [(lvl, key) for lvl, key in lv]
    _rules_embed(b, "tpl-rules", [
        "You must be 18 or older. Underage users are banned immediately and reported where required.",
        "Consent and respect always. No harassment, pressure, stalking or unwanted DMs.",
        "No NSFW, sexual content or explicit images anywhere. Keep everything SFW.",
        "Never share anyone's photos, personal details or private messages.",
        "No scams, money requests, catfishing, fake or stolen photos.",
        "Respect DM roles. Ask before messaging and accept a no.",
        "No hate speech, discrimination or outing anyone's identity.",
        "Never post ID documents in any channel. Verification happens only in private tickets.",
        "No advertising, invite links or self promotion outside the allowed channels.",
        "Meeting offline is your own responsibility. Read the safety tips and tell a friend.",
        "Report anything suspicious through a ticket. Staff decisions are final."],
        0xE91E63, "This server is for adults only. Please keep it safe and kind.")
    b.embed("tpl-self-intro", "💞 Make Your Profile", "Pick roles that describe you in the self roles channel. Everything is optional except age confirmation.", 0xE91E63)
    b.embed("tpl-guide", "🧭 Server Guide", "Here is where to find everything.", 0x9B59B6, [
        ("🪪 Verification", "Open a ticket in the verification channel to get **Verified Girl**, **Verified Guy** or **Verified Non-Binary**.", 0),
        ("🎭 Self Roles", "Pick your age range, interests, region, status and DM preferences.", 0),
        ("💘 Matchmaking", "Post a profile in the looking-for-date channel using the format shown there.", 0),
        ("🎲 Games", "Truth or dare, would you rather and ship games with Soward.", 0),
        ("🎟️ Tickets", "Support, reports, appeals, partnerships and VIP requests all use tickets.", 0)])
    b.embed("tpl-safety-tips", "🛡️ Safety Tips", "Dating online needs care.", 0x2ECC71, [
        ("Protect your details", "Never share your address, workplace, full name or financial info.", 0),
        ("Verify before you trust", "Look for the Verified roles and ask for a video call before meeting.", 0),
        ("Meeting in person", "Meet in a public place, tell a friend and arrange your own transport.", 0),
        ("Never send money", "Anyone asking for money, gift cards or crypto is a scammer. Report them.", 0),
        ("Trust your instincts", "If something feels wrong, stop talking and open a safety ticket.", 0)])
    b.embed("tpl-verify-info", "🪪 How Verification Works", "Verified roles show other members that a real person is behind the profile.", 0xFF4DA6, [
        ("1. Open a ticket", "Press the button below and answer the questions.", 0),
        ("2. Send a verification photo", "Staff will give you a code to write on paper and hold next to your face. Photos stay inside the private ticket.", 0),
        ("3. Get your role", "A verifier checks it and gives you **Verified Girl**, **Verified Guy** or **Verified Non-Binary**. The ticket is then closed.", 0),
        ("Privacy", "Only verifiers can see the ticket. Never post your photo or any ID in a public channel.", 0)], "Verification is optional but unlocks gender lounges and voice rooms.")
    b.embed("tpl-profile", "💘 Profile Format", "Copy this and fill it in. One post per member, edit instead of reposting.", 0xE91E63, [
        ("Template", "**Name:**\n**Age:**\n**Region:**\n**Looking for:**\n**Interests:**\n**About me:**", 0),
        ("Rules", "SFW only. No contact details. No photos of other people.", 0)])
    b.embed("tpl-ticket-info", "🎟️ Open a Ticket", "Choose the button that matches your need. Tickets are private between you and staff.", 0x3498DB)
    b.embed("tpl-vip", "💎 Booster Perks", "Boost the server to unlock perks:", 0xFFD700, [
        ("Tier roles", "**Rich** for 1 boost and **Wealthy** for 2 boosts, shown in the member list.", 0),
        ("Custom role", "Boosters can make their own role with `!booster role create <name> [colour]`, then change its name, colour and icon.", 0),
        ("Lounges", "Access to the VIP lounge and VIP voice room, plus a bonus to level XP.", 0),
        ("Keep it", "If you stop boosting your roles are removed after 24 hours and come back if you boost again.", 0)])

    b.category("📌 START HERE", "publicread")
    b.channel("verify", "✅-verify", topic="Verify here to unlock the server.", access_kind="verify")
    b.channel("rules", "📜-rules", access_kind="publicread")
    b.channel("welcome", "👋-welcome", access_kind="members")
    b.channel("safety_tips", "🛡️-safety-tips", access_kind="members")
    b.channel("guide", "🧭-server-guide", access_kind="members")
    b.category("📣 INFORMATION", "readonly")
    b.channel("announcements", "📢-announcements", "announcement", "Official news.")
    b.channel("updates", "🆕-updates")
    b.channel("self_roles", "🎭-self-roles", topic="Pick roles that describe you.")
    b.channel("levels", "📈-level-ups")
    b.channel("vip_info", "💎-booster-perks")
    b.category("🪪 VERIFICATION", "readonly")
    b.channel("verify_info", "🪪-how-to-verify")
    b.channel("verify_ticket", "📸-get-verified", topic="Open a private verification ticket.")
    b.category("💬 SOCIAL", "members")
    b.channel("general", "💬-general", slowmode=3)
    b.channel("introductions", "🙋-introductions", topic="Tell us about yourself. Keep it clean and safe.")
    b.channel("photos", "📸-sfw-photos", topic="SFW photos only.")
    b.channel("flirt", "💘-flirt-zone", topic="Light and respectful flirting. Keep it SFW.")
    b.channel("advice", "❤️-dating-advice")
    b.channel("relationships", "💍-relationship-talk")
    b.channel("vent", "🫂-vent-and-support", topic="Be kind. Report anything concerning.")
    b.channel("memes", "😂-memes")
    b.channel("pets", "🐾-pets")
    b.channel("food", "🍕-food-and-cooking")
    b.channel("bots", "🤖-bot-commands")
    b.category("💘 MATCHMAKING", "members")
    b.channel("lfd", "💞-looking-for-date", topic="Post your profile using the format below.")
    b.channel("friends", "🤝-friend-finder", topic="Looking for friends only.")
    b.channel("profiles", "🗂️-profile-cards")
    b.channel("taken", "💑-taken-and-happy", access_kind="roles:st_taken,vgirl,vguy,vnb")
    b.category("🌈 VERIFIED LOUNGES", "members")
    b.channel("girls", "👩-girls-lounge", topic="Verified Girls only.", access_kind="roles:vgirl")
    b.channel("guys", "👨-guys-lounge", topic="Verified Guys only.", access_kind="roles:vguy")
    b.channel("nb", "🌈-non-binary-lounge", topic="Verified Non-Binary members only.", access_kind="roles:vnb")
    b.channel("verified_chat", "✅-verified-chat", topic="All verified members.", access_kind="roles:vgirl,vguy,vnb")
    b.channel("vip_lounge", "💎-vip-lounge", access_kind="roles:vip,vipplus,booster")
    b.category("🎮 HOBBIES", "members")
    for key, name in (("gaming", "🎮-gaming"), ("anime", "🎌-anime-and-manga"), ("music", "🎵-music-share"), ("movies", "🎬-movies-and-shows"),
                      ("books", "📚-books"), ("fitness", "💪-fitness"), ("travel", "✈️-travel"), ("art", "🎨-art-and-creativity"), ("tech", "💻-tech-talk")):
        b.channel(key, name)
    b.category("🎲 GAMES", "members")
    for key, name in (("tod", "🎲-truth-or-dare"), ("wyr", "🤔-would-you-rather"), ("rate", "⭐-rate-and-ship"), ("counting", "🔢-counting"),
                      ("wordchain", "🔤-word-chain"), ("polls", "📊-polls")):
        b.channel(key, name)
    b.category("🌍 REGIONS", "members")
    for key, name in (("r_na", "🌎-north-america"), ("r_sa", "🌎-south-america"), ("r_eu", "🌍-europe"), ("r_af", "🌍-africa"),
                      ("r_asia", "🌏-asia"), ("r_oce", "🌏-oceania")):
        b.channel(key, name)
    b.category("🔊 VOICE", "voice")
    for i in (1, 2, 3):
        b.channel(f"vc{i}", f"💬 Lounge {i}", "voice")
    b.channel("vc_music", "🎵 Music Room", "voice")
    b.channel("vc_movie", "🎬 Movie Night", "voice")
    b.channel("vc_game", "🎮 Game Night", "voice", user_limit=6)
    b.channel("vc_late", "🌙 Late Night", "voice")
    for i in (1, 2, 3, 4):
        b.channel(f"date{i}", f"💞 Date Room {i}", "voice", user_limit=2)
    b.channel("vc_girls", "👩 Girls VC", "voice", access_kind="roles:vgirl")
    b.channel("vc_vip", "💎 VIP Room", "voice", access_kind="roles:vip,vipplus,booster")
    b.channel("stage", "🎤 Speed Dating Stage", "stage")
    jtc_cat = b.category("🎙️ TEMP VOICE", "voice")
    b.channel("jtc_hub", "➕ Join to Create", "voice", access_kind="hub")
    b.category("🎟️ HELP DESK", "readonly")
    b.channel("open_ticket", "🎫-open-a-ticket", topic="Support, reports, appeals, partnerships and VIP.")
    tickets_cat = b.category("🗃️ TICKETS", "staff")
    b.channel("transcripts", "📄-ticket-transcripts", access_kind="staff")
    verify_cat = b.category("🪪 VERIFICATION TICKETS", "staff")
    b.channel("verify_transcripts", "📄-verification-log", access_kind="staff")
    b.category("🛡️ SAFETY", "staff")
    b.channel("safety", "🚨-safety-reports")
    b.channel("verify_queue", "🪪-verification-queue")
    b.channel("appeals", "⚖️-appeals")
    b.channel("blacklist", "🚫-banned-scammers", topic="Known bad actors to watch for.")
    b.category("🛡️ STAFF", "staff")
    b.channel("staff_chat", "🛡️-staff-chat")
    b.channel("staff_cmds", "🤖-staff-commands")
    b.channel("staff_notes", "📝-staff-notes")
    b.channel("staff_vc", "Staff Room", "voice")

    b.post("rules", "tpl-rules", pin=True)
    b.post("safety_tips", "tpl-safety-tips", pin=True)
    b.post("guide", "tpl-guide", pin=True)
    b.post("self_roles", "tpl-self-intro")
    b.post("verify_info", "tpl-verify-info", pin=True)
    b.post("lfd", "tpl-profile", pin=True)
    b.post("vip_info", "tpl-vip")
    b.post("open_ticket", "tpl-ticket-info")

    b.embed("tpl-age", "🔞 Age Confirmation", "By taking this role you confirm that you are **18 or older**. False claims lead to an immediate ban.", 0xE74C3C)
    b.panel("self_roles", "tpl-age", "button", [("✅", "age18", "I am 18 or older")])
    _group(b, "self_roles", "tpl-ping", "🔔 Ping Roles", "Choose what you want to be pinged for.", [
        ("📢", "ping_news", "📢 Announcements", 0x3498DB), ("💞", "ping_events", "💞 Events", 0xE91E63), ("🎙️", "ping_vc", "🎙️ VC Hangouts", 0x9B59B6),
        ("💬", "ping_revive", "💬 Chat Revive", 0x95A5A6), ("🎮", "ping_game", "🎮 Game Night", 0x2ECC71), ("🎬", "ping_movie", "🎬 Movie Night", 0xE67E22),
        ("🎁", "ping_giveaways", "🎁 Giveaways", 0xF1C40F), ("📊", "ping_polls", "📊 Polls", 0x1ABC9C)], "button", color=0x3498DB, ping=True)
    _group(b, "self_roles", "tpl-status", "💘 Relationship Status", "Show your status. Pick one.", [
        ("💚", "st_single", "Single", 0x2ECC71), ("❤️", "st_taken", "Taken", 0xE74C3C), ("💛", "st_mingle", "Mingling", 0xF1C40F),
        ("💙", "st_friends", "Looking for Friends", 0x3498DB), ("💔", "st_complicated", "It's Complicated", 0x95A5A6)], "select", "unique", 0xFF69B4)
    _group(b, "self_roles", "tpl-looking", "🔎 Looking For", "What are you here for? Pick any.", [
        ("🤝", "lf_friends", "Friendship", 0x3498DB), ("💞", "lf_dating", "Dating", 0xE91E63), ("💍", "lf_serious", "Serious Relationship", 0xE74C3C),
        ("💬", "lf_chat", "Casual Chatting", 0x95A5A6), ("🎙️", "lf_voice", "Voice Calls", 0x9B59B6), ("🎮", "lf_gaming", "Gaming Partners", 0x2ECC71)], "select", color=0xE91E63)
    _group(b, "self_roles", "tpl-dm", "📨 DM Preferences", "Let people know how you like to be contacted. Pick one.", [
        ("📬", "dm_open", "DMs Open", 0x2ECC71), ("❓", "dm_ask", "Ask to DM", 0xF1C40F), ("📪", "dm_closed", "DMs Closed", 0xE74C3C)], "button", "unique", 0x7F8C8D)
    _group(b, "self_roles", "tpl-age-range", "🎂 Age Range", "Pick your age range. One only.", [
        ("🔹", "age_18", "18-20", 0x95A5A6), ("🔸", "age_21", "21-24", 0x95A5A6), ("🔷", "age_25", "25-29", 0x95A5A6),
        ("🔶", "age_30", "30-39", 0x95A5A6), ("🟦", "age_40", "40+", 0x95A5A6)], "select", "unique", 0x95A5A6)
    _group(b, "self_roles", "tpl-gender", "🏷️ Identity", "Optional. Pick any that fit. Verified roles come from verification tickets.", [
        ("👩", "id_woman", "Woman", 0xBDC3C7), ("👨", "id_man", "Man", 0xBDC3C7), ("🌈", "id_nb", "Non-Binary", 0xBDC3C7),
        ("⚧️", "id_trans", "Trans", 0xBDC3C7), ("🤐", "id_private", "Prefer Not to Say", 0xBDC3C7)], "select", color=0xBDC3C7)
    _group(b, "self_roles", "tpl-orient", "🌈 Orientation", "Optional. Pick any that fit.", [
        ("🏳️", "o_straight", "Straight", 0xBDC3C7), ("🏳️‍🌈", "o_gay", "Gay", 0xBDC3C7), ("💗", "o_lesbian", "Lesbian", 0xBDC3C7),
        ("💜", "o_bi", "Bisexual", 0xBDC3C7), ("💛", "o_pan", "Pansexual", 0xBDC3C7), ("🖤", "o_ace", "Asexual", 0xBDC3C7), ("✨", "o_other", "Other", 0xBDC3C7)], "select", color=0x9B59B6)
    _group(b, "self_roles", "tpl-pronouns", "🏷️ Pronouns", "Show your pronouns.", [
        ("🔵", "p_he", "He/Him", 0xBDC3C7), ("🔴", "p_she", "She/Her", 0xBDC3C7), ("🟢", "p_they", "They/Them", 0xBDC3C7), ("⚪", "p_any", "Any Pronouns", 0xBDC3C7)], "reaction", color=0xBDC3C7)
    _group(b, "self_roles", "tpl-region", "🌍 Region", "Pick your region. One only.", [
        ("🌎", "reg_na", "North America", 0x95A5A6), ("🌎", "reg_sa", "South America", 0x95A5A6), ("🌍", "reg_eu", "Europe", 0x95A5A6),
        ("🌍", "reg_af", "Africa", 0x95A5A6), ("🌏", "reg_asia", "Asia", 0x95A5A6), ("🌏", "reg_oce", "Oceania", 0x95A5A6)], "select", "unique", 0x3498DB)
    _group(b, "self_roles", "tpl-lang", "🗣️ Languages", "Pick the languages you speak.", [
        ("🇬🇧", "lang_en", "English", 0x95A5A6), ("🇪🇸", "lang_es", "Spanish", 0x95A5A6), ("🇮🇳", "lang_hi", "Hindi", 0x95A5A6),
        ("🇧🇩", "lang_bn", "Bengali", 0x95A5A6), ("🇸🇦", "lang_ar", "Arabic", 0x95A5A6), ("🇫🇷", "lang_fr", "French", 0x95A5A6),
        ("🇧🇷", "lang_pt", "Portuguese", 0x95A5A6), ("🇩🇪", "lang_de", "German", 0x95A5A6), ("🌐", "lang_other", "Other", 0x95A5A6)], "select", color=0x95A5A6)
    _group(b, "self_roles", "tpl-interests", "⭐ Interests", "Pick what you enjoy.", [
        ("🎮", "i_gaming", "Gaming", 0x1ABC9C), ("🎌", "i_anime", "Anime", 0x1ABC9C), ("🎵", "i_music", "Music", 0x1ABC9C), ("🎬", "i_movies", "Movies", 0x1ABC9C),
        ("📚", "i_books", "Books", 0x1ABC9C), ("💪", "i_fitness", "Fitness", 0x1ABC9C), ("✈️", "i_travel", "Travel", 0x1ABC9C), ("🎨", "i_art", "Art", 0x1ABC9C),
        ("💻", "i_tech", "Tech", 0x1ABC9C), ("🍳", "i_cooking", "Cooking", 0x1ABC9C), ("🐶", "i_pets", "Pets", 0x1ABC9C), ("📸", "i_photo", "Photography", 0x1ABC9C)], "select", color=0x1ABC9C)
    _group(b, "self_roles", "tpl-zodiac", "♈ Zodiac", "Pick your sign. One only.", [
        ("♈", "z_aries", "Aries", 0x95A5A6), ("♉", "z_taurus", "Taurus", 0x95A5A6), ("♊", "z_gemini", "Gemini", 0x95A5A6), ("♋", "z_cancer", "Cancer", 0x95A5A6),
        ("♌", "z_leo", "Leo", 0x95A5A6), ("♍", "z_virgo", "Virgo", 0x95A5A6), ("♎", "z_libra", "Libra", 0x95A5A6), ("♏", "z_scorpio", "Scorpio", 0x95A5A6),
        ("♐", "z_sag", "Sagittarius", 0x95A5A6), ("♑", "z_capricorn", "Capricorn", 0x95A5A6), ("♒", "z_aquarius", "Aquarius", 0x95A5A6), ("♓", "z_pisces", "Pisces", 0x95A5A6)],
        "select", "unique", 0x9B59B6)
    _group(b, "self_roles", "tpl-colors", "🎨 Name Colors", "Pick one colour for your name.", [
        ("🔴", "c_red", "Red", 0xE74C3C), ("🟠", "c_orange", "Orange", 0xE67E22), ("🟡", "c_yellow", "Yellow", 0xF1C40F), ("🟢", "c_green", "Green", 0x2ECC71),
        ("🔵", "c_blue", "Blue", 0x3498DB), ("🟣", "c_purple", "Purple", 0x9B59B6), ("💗", "c_pink", "Pink", 0xFF69B4), ("🤍", "c_white", "White", 0xECF0F1),
        ("🩵", "c_cyan", "Cyan", 0x1ABC9C), ("🖤", "c_black", "Charcoal", 0x2C3E50)], "select", "unique", 0xFF69B4)

    b.ticket("verify_ticket", "Verification", ("admin", "hmod", "mod", "verifier"), category=verify_cat, transcript="verify_transcripts",
             welcome="Thanks for starting verification. A verifier will send you a code to write on paper and hold next to your face. Only staff can see this ticket. Never share ID documents.",
             button="Get Verified", questions=("Which role: Girl, Guy or Non-Binary?", "How old are you?", "Anything we should know?"))
    b.ticket("open_ticket", "Support", ("admin", "hmod", "mod", "helper"), category=tickets_cat, transcript="transcripts",
             welcome="Thanks for reaching out. A staff member will help you shortly.", button="Get Support", questions=("What do you need help with?",))
    b.ticket("open_ticket", "Safety Report", ("admin", "hmod", "mod"), category=tickets_cat, transcript="transcripts",
             welcome="Thank you for reporting. This is private. Include usernames, links and what happened.", button="Report a Problem",
             questions=("Who are you reporting?", "What happened?", "Do you have message links?"))
    b.ticket("open_ticket", "Ban Appeal", ("admin", "hmod"), category=tickets_cat, transcript="transcripts",
             welcome="Tell us why you think the action should be reviewed. Be honest and respectful.", button="Appeal an Action",
             questions=("What was the action?", "Why should it be reviewed?"))
    b.ticket("open_ticket", "Partnership", ("admin", "hmod"), category=tickets_cat, transcript="transcripts",
             welcome="Thanks for your interest. Share your server details and what you propose.", button="Partner With Us",
             questions=("Server name and invite?", "Member count?", "What do you propose?"))
    b.ticket("open_ticket", "VIP Request", ("admin", "hmod", "mod"), category=tickets_cat, transcript="transcripts",
             welcome="Tell us how you qualify for VIP and which perk you want.", button="Request VIP", questions=("How do you qualify?",))
    b.ticket("open_ticket", "Profile Review", ("admin", "hmod", "mod", "helper"), category=tickets_cat, transcript="transcripts",
             welcome="Share your profile and we will give friendly tips.", button="Review My Profile", questions=("Paste your profile text.",))

    b.embed("tpl-welcome", "👋 Welcome to {server}!", "Verify, confirm you are 18+, pick your roles and read the safety tips. Get **Verified Girl, Guy or Non-Binary** from the verification channel.", 0xFF69B4, footer="Member #{membercount}")
    b.greeting("join", "welcome", "{user}", embed="tpl-welcome")
    b.greeting("leave", "welcome", "**{username}** has left **{server}**. We are now **{membercount}** members.", enabled=0)
    b.greeting("boost", "general", "💜 Thank you {user} for boosting **{server}**! You unlocked the VIP lounge.")
    b.levels(lv, "levels", voice_xp_per_minute=12)
    b.tables["jtc_hubs"] = [{"channel_id": {"$channel": "jtc_hub"}, "category_id": {"$channel": jtc_cat}, "name_template": "🔊 {user}'s room", "user_limit": 0, "bitrate": 0}]
    b.tables["booster_config"] = [{
        "enabled": 1, "tier_mode": "count", "stack_mode": "highest", "base_role_id": {"$role": "booster"}, "grace_hours": 24, "custom_enabled": 1,
        "custom_min": 1, "allow_name": 1, "allow_color": 1, "allow_icon": 1, "allow_hoist": 0, "allow_perms": 0, "position_mode": "below",
        "position_ref_id": {"$role": "booster"}, "cooldown_hours": 6, "name_filter": 1, "max_name_len": 24, "remove_on_unboost": 1, "restore_on_reboost": 1,
    }]
    b.tables["booster_tiers"] = [{"boosts": 1, "role_id": {"$role": "tier1"}}, {"boosts": 2, "role_id": {"$role": "tier2"}}]
    b.tables["xp_multipliers"] = [
        {"scope_type": "role", "scope_id": {"$role": "tier1"}, "multiplier": 1.25, "label": "booster"},
        {"scope_type": "role", "scope_id": {"$role": "tier2"}, "multiplier": 1.5, "label": "booster"},
    ]
    b.settings["booster_blocked_names"] = ["admin", "mod", "staff", "owner", "verified", "moderator", "support", "verifier", "official"]
    _common_setup(b, "strict", 3)
    return b.result({"id": "datingv2", "name": "Dating and Social 18+ v2 (Premium)", "emoji": "💞", "premium": True,
                     "summary": "Premium. Verified Girl, Guy and Non-Binary roles with a verification ticket, seven ticket panels, gender lounges, matchmaking, 14 self role panels, 8 level roles, Join to Create voice and Booster Perks."})



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
