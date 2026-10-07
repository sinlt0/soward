import discord

from utils import db, emoji_manager, guild_settings, incident, security
from utils.colors import NEUTRAL
from utils.components import footer_block
import config

def _toggle_style(enabled: bool) -> discord.ButtonStyle:
    return discord.ButtonStyle.success if enabled else discord.ButtonStyle.danger

def _toggle_label(enabled: bool, on: str = "Enabled", off: str = "Disabled") -> str:
    return on if enabled else off

class AntiNukeActionRow(discord.ui.ActionRow):
    def __init__(self, layout: "AntiNukeOverviewLayout" = None):
        super().__init__()
        self.layout_ref = layout

    @discord.ui.button(custom_id="an:toggle", style=discord.ButtonStyle.secondary, label="AntiNuke")
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.layout_ref
        new_state = not view.enabled
        await guild_settings.set(view.guild_id, "antinuke_enabled", new_state)
        view.enabled = new_state
        await view.refresh(interaction)

    @discord.ui.button(label="Strict mode", custom_id="an:strict", style=discord.ButtonStyle.secondary)
    async def strict_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.layout_ref
        new_state = not view.strict_mode
        await guild_settings.set(view.guild_id, "antinuke_strict_mode", new_state)
        view.strict_mode = new_state
        await view.refresh(interaction)

    @discord.ui.button(label="View thresholds", custom_id="an:thresholds", style=discord.ButtonStyle.primary)
    async def thresholds_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.layout_ref
        view.showing_thresholds = not view.showing_thresholds
        await view.refresh(interaction)


PUNISHMENT_OVERRIDE_OPTIONS = [
    "channel_delete", "channel_create", "role_delete", "role_create",
    "ban", "kick", "webhook_create", "permission_grant", "bot_add", "prune",
]


class PunishmentValueModal(discord.ui.Modal, title="Set Punishment Override"):
    def __init__(self, action_type: str, on_saved):
        super().__init__()
        self.action_type = action_type
        self.on_saved = on_saved
        self.value_input = discord.ui.TextInput(
            label=f"Punishment for '{action_type}'",
            placeholder="ban, kick, kick_bot, strip_roles, or quarantine",
            max_length=20,
        )
        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.on_saved(interaction, self.action_type, self.value_input.value.strip().lower())


class PunishmentOverrideSelect(discord.ui.Select):
    def __init__(self, layout: "AntiNukeOverviewLayout"):
        options = [discord.SelectOption(label=a.replace("_", " ").title(), value=a) for a in PUNISHMENT_OVERRIDE_OPTIONS]
        super().__init__(placeholder="Set a per-action punishment override...", options=options, custom_id="an:punishment_select")
        self.layout_ref = layout

    async def callback(self, interaction: discord.Interaction):
        action_type = self.values[0]
        valid_punishments = ("ban", "kick", "kick_bot", "strip_roles", "quarantine")

        async def on_saved(modal_interaction: discord.Interaction, action: str, punishment: str):
            if punishment not in valid_punishments:
                return await modal_interaction.response.send_message(
                    f"Invalid punishment `{punishment}`. Choose from: {', '.join(valid_punishments)}", ephemeral=True
                )
            await security.set_action_punishment(self.layout_ref.guild_id, action, punishment)
            self.layout_ref.action_overrides[action] = punishment
            self.layout_ref._render()
            await modal_interaction.response.edit_message(view=self.layout_ref)

        modal = PunishmentValueModal(action_type, on_saved)
        await interaction.response.send_modal(modal)


class AntiNukeSecondaryRow(discord.ui.ActionRow):
    def __init__(self, layout: "AntiNukeOverviewLayout" = None):
        super().__init__()
        self.layout_ref = layout

    @discord.ui.button(label="View Permits", custom_id="an:permits", style=discord.ButtonStyle.secondary)
    async def permits_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.layout_ref
        view.showing_permits = not view.showing_permits
        view.showing_panic = False
        await view.refresh(interaction)

    @discord.ui.button(label="Panic Mode", custom_id="an:panic", style=discord.ButtonStyle.secondary)
    async def panic_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.layout_ref
        view.showing_panic = not view.showing_panic
        view.showing_permits = False
        if view.showing_panic:
            view.panic_active = await security.is_panic_mode_active(view.guild_id)
        await view.refresh(interaction)

    @discord.ui.button(label="End Panic Mode", custom_id="an:panic_end", style=discord.ButtonStyle.danger, row=1)
    async def panic_end_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.layout_ref
        await security.end_panic_mode(view.guild_id, ended_by=str(interaction.user.id))
        view.panic_active = False
        await view.refresh(interaction)

class AntiNukeOverviewLayout(discord.ui.LayoutView):
    def __init__(self, cog, author_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.author_id = author_id
        self.guild_id = guild_id
        self.enabled = False
        self.strict_mode = False
        self.punishment = config.ANTINUKE_DEFAULT_PUNISHMENT
        self.thresholds: dict[str, int] = {}
        self.trusted_count = 0
        self.quarantined_count = 0
        self.showing_thresholds = False
        self.action_overrides: dict[str, str] = {}
        self.showing_permits = False
        self.showing_panic = False
        self.panic_active = False
        self.extra_owners: list[int] = []
        self.trusted_admins: list[int] = []

        self.container = discord.ui.Container(accent_color=NEUTRAL)
        self.text = discord.ui.TextDisplay("Loading...")
        self.container.add_item(self.text)
        self.container.add_item(discord.ui.Separator())
        self.action_row = AntiNukeActionRow(layout=self)
        self.container.add_item(self.action_row)
        self.punishment_select_row = discord.ui.ActionRow(PunishmentOverrideSelect(self))
        self.container.add_item(self.punishment_select_row)
        self.secondary_row = AntiNukeSecondaryRow(layout=self)
        self.container.add_item(self.secondary_row)
        self.add_item(self.container)

    @classmethod
    async def create(cls, cog, author_id: int, guild_id: int) -> "AntiNukeOverviewLayout":
        view = cls(cog, author_id, guild_id)
        await view._load()
        view._render()
        return view

    async def _load(self):
        self.enabled = await guild_settings.get(self.guild_id, "antinuke_enabled", False)
        self.strict_mode = await guild_settings.get(self.guild_id, "antinuke_strict_mode", config.ANTINUKE_STRICT_MODE_DEFAULT)
        self.punishment = await guild_settings.get(self.guild_id, "antinuke_punishment", config.ANTINUKE_DEFAULT_PUNISHMENT)
        self.thresholds = {}
        for action, default in config.ANTINUKE_DEFAULT_THRESHOLDS.items():
            self.thresholds[action] = await guild_settings.get(self.guild_id, f"antinuke_threshold_{action}", default)
        trusted_rows = await db.raw_fetch("SELECT 1 FROM antinuke_whitelist WHERE guild_id=?", (self.guild_id,))
        self.trusted_count = len(trusted_rows)
        quarantined_rows = await db.raw_fetch(
            "SELECT 1 FROM quarantine WHERE guild_id=? AND released_at IS NULL", (self.guild_id,)
        )
        self.quarantined_count = len(quarantined_rows)

        override_rows = await db.raw_fetch("SELECT action_type, punishment FROM antinuke_action_punishments WHERE guild_id=?", (self.guild_id,))
        self.action_overrides = {r["action_type"]: r["punishment"] for r in override_rows}

        permit_rows = await security.list_permit_tiers(self.guild_id)
        self.extra_owners = [r["user_id"] for r in permit_rows if r["tier"] == config.SECURITY_TIER_EXTRA_OWNER]
        self.trusted_admins = [r["user_id"] for r in permit_rows if r["tier"] == config.SECURITY_TIER_TRUSTED_ADMIN]

        self.panic_active = await security.is_panic_mode_active(self.guild_id)

    def _render(self):
        e = emoji_manager.get
        self.action_row.toggle_btn.label = f"AntiNuke: {_toggle_label(self.enabled)}"
        self.action_row.toggle_btn.style = _toggle_style(self.enabled)
        self.action_row.strict_btn.label = f"Strict: {_toggle_label(self.strict_mode)}"
        self.action_row.strict_btn.style = _toggle_style(self.strict_mode)
        self.action_row.thresholds_btn.label = "Hide thresholds" if self.showing_thresholds else "View thresholds"
        self.secondary_row.permits_btn.label = "Hide Permits" if self.showing_permits else "View Permits"
        self.secondary_row.panic_btn.label = "Hide Panic Info" if self.showing_panic else "Panic Mode"
        self.secondary_row.panic_btn.style = discord.ButtonStyle.danger if self.panic_active else discord.ButtonStyle.secondary
        self.secondary_row.panic_end_btn.disabled = not self.panic_active

        body = (
            f"## {e('antinuke_cat')} AntiNuke\n"
            f"**Status:** {'🟢 Enabled' if self.enabled else '🔴 Disabled'}\n"
            f"**Punishment:** `{self.punishment}` (general fallback)\n"
            f"**Strict mode:** {'On' if self.strict_mode else 'Off'}\n"
            f"**Trusted users:** {self.trusted_count}\n"
            f"**Currently quarantined:** {self.quarantined_count}\n"
            f"**Panic mode:** {'🔴 Active' if self.panic_active else '🟢 Inactive'}\n\n"
            f"Commands: `antinuke threshold <action> <n>` · `antinuke punishment <type>` · "
            f"`antinuke punishmentaction <action> <type>` · `antinuke trust add/remove @user` · "
            f"`extraowner add/remove @user` · `trustedadmin add/remove @user` · `permits` · "
            f"`antinuke quarantinerole @role` · `quarantine @user` · `release @user` · `quarantinelist`"
        )
        if self.showing_thresholds:
            lines = "\n".join(f"`{k}`: **{v}**" for k, v in self.thresholds.items())
            body += f"\n\n**Thresholds** (per {config.ANTINUKE_THRESHOLD_WINDOW_SECONDS}s):\n{lines}"
        if self.action_overrides:
            override_lines = "\n".join(f"`{k}` → `{v}`" for k, v in self.action_overrides.items())
            body += f"\n\n**Per-action punishment overrides:**\n{override_lines}"
        if self.showing_permits:
            eo_text = ", ".join(f"<@{uid}>" for uid in self.extra_owners) or "None"
            ta_text = ", ".join(f"<@{uid}>" for uid in self.trusted_admins) or "None"
            body += (
                f"\n\n**Extra Owners** (`{len(self.extra_owners)}/{config.SECURITY_TIER_MAX_PER_TIER}`): {eo_text}\n"
                f"**Trusted Admins** (`{len(self.trusted_admins)}/{config.SECURITY_TIER_MAX_PER_TIER}`): {ta_text}\n"
                f"-# Only the real server owner can grant Extra Owner; owner or Extra Owner can grant Trusted Admin.\n"
                f"-# Manage via `extraowner add/remove @user` and `trustedadmin add/remove @user`."
            )
        if self.showing_panic:
            if self.panic_active:
                body += "\n\n**Panic mode is currently active** — flagged raiders are being instantly actioned server-wide. Use **End Panic Mode** below to lift it early."
            else:
                body += f"\n\n**Panic mode is inactive.** It auto-triggers when {config.PANIC_MODE_RAIDER_COUNT}+ distinct users are flagged as raiders within {config.PANIC_MODE_WINDOW_SECONDS}s, from either AntiRaid joins or AutoMod heat violations."
        self.text.content = body

    async def refresh(self, interaction: discord.Interaction):
        self._render()
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

class AutoModSelect(discord.ui.Select):
    def __init__(self, layout: "AutoModOverviewLayout" = None):
        options = [
            discord.SelectOption(label="Overview", value="overview", description="Status and heat thresholds"),
            discord.SelectOption(label="Banned words", value="words", description="View the banned words list"),
            discord.SelectOption(label="Invite blocking", value="invites", description="Toggle invite link blocking"),
            discord.SelectOption(label="Link blocklist", value="links", description="View blocked domains"),
            discord.SelectOption(label="Panic status", value="panic", description="Shared server-wide panic mode state"),
        ]
        super().__init__(placeholder="Configure AutoMod...", options=options, custom_id="automod:select")
        self.layout_ref = layout

    async def callback(self, interaction: discord.Interaction):
        view = self.layout_ref
        view.page = self.values[0]
        if view.page == "panic":
            view.panic_active = await security.is_panic_mode_active(view.guild_id)
        await view.refresh(interaction)

class AutoModActionRow(discord.ui.ActionRow):
    def __init__(self, layout: "AutoModOverviewLayout" = None):
        super().__init__()
        self.layout_ref = layout

    @discord.ui.button(custom_id="automod:toggle", style=discord.ButtonStyle.secondary, label="AutoMod")
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.layout_ref
        new_state = not view.enabled
        await guild_settings.set(view.guild_id, "automod_enabled", new_state)
        view.enabled = new_state
        await view.refresh(interaction)

class AutoModOverviewLayout(discord.ui.LayoutView):
    def __init__(self, author_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.guild_id = guild_id
        self.enabled = False
        self.banned_words: list = []
        self.block_invites = False
        self.link_blocklist: list = []
        self.page = "overview"
        self.panic_active = False
        self.trusted_count = 0

        self.container = discord.ui.Container(accent_color=NEUTRAL)
        self.text = discord.ui.TextDisplay("Loading...")
        self.container.add_item(self.text)
        self.container.add_item(discord.ui.Separator())
        self.select_row = discord.ui.ActionRow()
        self.select_row.add_item(AutoModSelect(layout=self))
        self.container.add_item(self.select_row)
        self.action_row = AutoModActionRow(layout=self)
        self.container.add_item(self.action_row)
        self.add_item(self.container)

    @classmethod
    async def create(cls, author_id: int, guild_id: int) -> "AutoModOverviewLayout":
        view = cls(author_id, guild_id)
        await view._load()
        view._render()
        return view

    async def _load(self):
        self.enabled = await guild_settings.get(self.guild_id, "automod_enabled", False)
        self.banned_words = await guild_settings.get(self.guild_id, "automod_banned_words", [])
        self.block_invites = await guild_settings.get(self.guild_id, "automod_block_invites", False)
        self.link_blocklist = await guild_settings.get(self.guild_id, "automod_link_blocklist", [])
        trusted_rows = await db.raw_fetch("SELECT 1 FROM antinuke_whitelist WHERE guild_id=?", (self.guild_id,))
        self.trusted_count = len(trusted_rows)
        self.panic_active = await security.is_panic_mode_active(self.guild_id)

    def _render(self):
        e = emoji_manager.get
        self.action_row.toggle_btn.label = f"AutoMod: {_toggle_label(self.enabled)}"
        self.action_row.toggle_btn.style = _toggle_style(self.enabled)

        if self.page == "words":
            body = (
                f"## {e('automod_cat')} Banned words\n"
                + (", ".join(f"`{w}`" for w in self.banned_words) or "No banned words configured.")
                + "\n\nUse `automod banword <word>` / `automod unbanword <word>` to manage."
            )
        elif self.page == "invites":
            body = (
                f"## {e('automod_cat')} Invite blocking\n"
                f"**Status:** {'On' if self.block_invites else 'Off'}\n\n"
                "Use `automod blockinvites true/false` to change."
            )
        elif self.page == "links":
            body = (
                f"## {e('automod_cat')} Link blocklist\n"
                + (", ".join(f"`{d}`" for d in self.link_blocklist) or "No blocked domains configured.")
            )
        elif self.page == "panic":
            body = (
                f"## {e('automod_cat')} Panic Status\n"
                f"**Server-wide panic mode:** {'🔴 Active' if self.panic_active else '🟢 Inactive'}\n\n"
                f"AutoMod contributes to the shared panic mode: if {config.PANIC_MODE_RAIDER_COUNT}+ distinct users "
                f"hit panic-level heat within {config.PANIC_MODE_WINDOW_SECONDS}s, the whole server enters panic mode — "
                "shared with AntiRaid and AntiNuke, not just an AutoMod-local state.\n\n"
                "Manage panic mode from the AntiNuke panel or `antiraid raidmode` / `antiraid status`."
            )
        else:
            body = (
                f"## {e('automod_cat')} AutoMod\n"
                f"**Status:** {'🟢 Enabled' if self.enabled else '🔴 Disabled'}\n"
                f"**Heat decay:** {config.AUTOMOD_HEAT_DECAY_PER_SECOND}/s\n"
                f"**Mute threshold:** {config.AUTOMOD_HEAT_MUTE_THRESHOLD} heat · "
                f"**Panic threshold:** {config.AUTOMOD_HEAT_PANIC_THRESHOLD} heat\n"
                f"**Banned words:** {len(self.banned_words)} · "
                f"**Invite blocking:** {'On' if self.block_invites else 'Off'} · "
                f"**Blocked domains:** {len(self.link_blocklist)}\n"
                f"**Trusted users (shared list):** {self.trusted_count} · "
                f"**Panic mode:** {'🔴 Active' if self.panic_active else '🟢 Inactive'}\n\n"
                "AutoMod uses a decaying heat score per user so regulars who briefly burst-talk "
                "aren't punished the same way a real spammer is. Select a category above for details."
            )
        self.text.content = body

    async def refresh(self, interaction: discord.Interaction):
        self._render()
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

class AntiRaidActionRow(discord.ui.ActionRow):
    def __init__(self, layout: "AntiRaidOverviewLayout" = None):
        super().__init__()
        self.layout_ref = layout

    @discord.ui.button(custom_id="antiraid:toggle", style=discord.ButtonStyle.secondary, label="AntiRaid")
    async def toggle_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = self.layout_ref
        new_state = not view.enabled
        await guild_settings.set(view.guild_id, "antiraid_enabled", new_state)
        view.enabled = new_state
        await view.refresh(interaction)

    @discord.ui.button(label="Activate panic mode", custom_id="antiraid:panic", style=discord.ButtonStyle.danger)
    async def panic_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        from cogs.antiraid import AntiRaid as AntiRaidCog
        cog: AntiRaidCog = interaction.client.get_cog("AntiRaid")
        view = self.layout_ref
        if cog:
            if view.raid_mode_active:
                await cog.end_raid_mode(interaction.guild, ended_by=interaction.user.id)
                view.raid_mode_active = False
            else:
                await cog.start_raid_mode(interaction.guild, triggered_by=f"manual:{interaction.user.id}")
                view.raid_mode_active = True
        await view.refresh(interaction)

class AntiRaidOverviewLayout(discord.ui.LayoutView):
    def __init__(self, author_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.guild_id = guild_id
        self.enabled = config.ANTIRAID_ENABLED_DEFAULT
        self.min_age_seconds = config.ANTIRAID_MIN_ACCOUNT_AGE_SECONDS
        self.join_velocity_count = config.ANTIRAID_JOIN_VELOCITY_COUNT
        self.join_velocity_window = config.ANTIRAID_JOIN_VELOCITY_WINDOW_SECONDS
        self.flag_no_avatar = config.ANTIRAID_FLAG_NO_AVATAR
        self.join_action = config.ANTIRAID_JOIN_ACTION
        self.raid_mode_active = False
        self.panic_shared_active = False

        self.container = discord.ui.Container(accent_color=NEUTRAL)
        self.text = discord.ui.TextDisplay("Loading...")
        self.container.add_item(self.text)
        self.container.add_item(discord.ui.Separator())
        self.action_row = AntiRaidActionRow(layout=self)
        self.container.add_item(self.action_row)
        self.add_item(self.container)

    @classmethod
    async def create(cls, author_id: int, guild_id: int) -> "AntiRaidOverviewLayout":
        view = cls(author_id, guild_id)
        await view._load()
        view._render()
        return view

    async def _load(self):
        self.enabled = await guild_settings.get(self.guild_id, "antiraid_enabled", config.ANTIRAID_ENABLED_DEFAULT)
        self.min_age_seconds = await guild_settings.get(self.guild_id, "antiraid_min_age_seconds", config.ANTIRAID_MIN_ACCOUNT_AGE_SECONDS)
        self.join_velocity_count = await guild_settings.get(self.guild_id, "antiraid_join_velocity_count", config.ANTIRAID_JOIN_VELOCITY_COUNT)
        self.join_velocity_window = await guild_settings.get(self.guild_id, "antiraid_join_velocity_window", config.ANTIRAID_JOIN_VELOCITY_WINDOW_SECONDS)
        self.flag_no_avatar = await guild_settings.get(self.guild_id, "antiraid_flag_no_avatar", config.ANTIRAID_FLAG_NO_AVATAR)
        self.join_action = await guild_settings.get(self.guild_id, "antiraid_join_action", config.ANTIRAID_JOIN_ACTION)
        row = await db.raw_fetchone("SELECT raid_mode FROM antiraid_state WHERE guild_id=?", (self.guild_id,))
        self.raid_mode_active = bool(row["raid_mode"]) if row else False
        self.panic_shared_active = await security.is_panic_mode_active(self.guild_id)

    def _render(self):
        e = emoji_manager.get
        self.action_row.toggle_btn.label = f"AntiRaid: {_toggle_label(self.enabled)}"
        self.action_row.toggle_btn.style = _toggle_style(self.enabled)
        self.action_row.panic_btn.label = "Deactivate panic mode" if self.raid_mode_active else "Activate panic mode"
        self.action_row.panic_btn.style = discord.ButtonStyle.secondary if self.raid_mode_active else discord.ButtonStyle.danger

        age_days = self.min_age_seconds // 86400
        body = (
            f"## {e('antiraid')} AntiRaid\n"
            f"**Status:** {'🟢 Enabled' if self.enabled else '🔴 Disabled'}\n"
            f"**Raid mode:** {'🚨 ACTIVE' if self.raid_mode_active else 'Inactive'}\n"
            f"**Server-wide panic mode:** {'🔴 Active' if self.panic_shared_active else '🟢 Inactive'} (shared with AutoMod/AntiNuke)\n"
            f"**Join velocity trigger:** {self.join_velocity_count} joins / {self.join_velocity_window}s\n"
            f"**Minimum account age:** {age_days} day(s)\n"
            f"**Flag no-avatar accounts:** {'Yes' if self.flag_no_avatar else 'No'}\n"
            f"**Action on flagged joins:** `{self.join_action}`\n\n"
            "Commands: `antiraid minage <days>` · `antiraid velocity <count> <window>` · "
            "`antiraid action <kick|ban|timeout>` · `antiraid noavatar <true|false>` · "
            "`antiraid raidmode` to toggle manually · `antiraid status` for full detail."
        )
        self.text.content = body

    async def refresh(self, interaction: discord.Interaction):
        self._render()
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

class VerificationSelect(discord.ui.Select):
    def __init__(self, layout: "VerificationOverviewLayout" = None):
        options = [
            discord.SelectOption(label=name.title(), value=name, description=f"Level {num}")
            for name, num in config.VERIFICATION_LEVELS.items()
        ]
        super().__init__(placeholder="Set verification level...", options=options, custom_id="verification:level_select")
        self.layout_ref = layout

    async def callback(self, interaction: discord.Interaction):
        view = self.layout_ref
        level_name = self.values[0]
        level_int = config.VERIFICATION_LEVELS[level_name]
        await guild_settings.set(view.guild_id, "verification_level", level_int)
        await guild_settings.set(view.guild_id, "verification_level_base", level_int)
        view.level = level_int
        await view.refresh(interaction)

class VerificationOverviewLayout(discord.ui.LayoutView):
    def __init__(self, author_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.guild_id = guild_id
        self.level = 0
        self.channel_id = None
        self.role_id = None
        self.gate_role_id = None

        self.container = discord.ui.Container(accent_color=NEUTRAL)
        self.text = discord.ui.TextDisplay("Loading...")
        self.container.add_item(self.text)
        self.container.add_item(discord.ui.Separator())
        self.select_row = discord.ui.ActionRow()
        self.select_row.add_item(VerificationSelect(layout=self))
        self.container.add_item(self.select_row)
        self.add_item(self.container)

    @classmethod
    async def create(cls, author_id: int, guild_id: int) -> "VerificationOverviewLayout":
        view = cls(author_id, guild_id)
        await view._load()
        view._render()
        return view

    async def _load(self):
        self.level = await guild_settings.get(self.guild_id, "verification_level", 0)
        self.channel_id = await guild_settings.get(self.guild_id, "verification_channel_id")
        self.role_id = await guild_settings.get(self.guild_id, "verification_role_id")
        self.gate_role_id = await guild_settings.get(self.guild_id, "verification_gate_role_id")

    def _render(self):
        e = emoji_manager.get
        level_names = {v: k for k, v in config.VERIFICATION_LEVELS.items()}
        body = (
            f"## {e('verification_cat')} Verification\n"
            f"**Level:** `{level_names.get(self.level, 'unknown')}`\n"
            f"**Channel:** {f'<#{self.channel_id}>' if self.channel_id else 'Not set'}\n"
            f"**Verified role:** {f'<@&{self.role_id}>' if self.role_id else 'Not set'}\n"
            f"**Gate role:** {f'<@&{self.gate_role_id}>' if self.gate_role_id else 'Not set'}\n\n"
            "Use the dropdown above to change the verification type.\n\n"
            "**Setup flow:**\n"
            "1. `verification role @role` — role granted after passing\n"
            "2. `verification gaterole @role` — role held until verified (optional)\n"
            "3. `verification type <button|captcha|manual>` — pick the method\n"
            "4. `verification setup #channel` — posts the one static panel in that channel\n\n"
            "Make the verification channel invisible to your verified role so only "
            "new unverified members see it. Use `approve @member` for manual approvals.\n\n"
            "During an AntiNuke lockdown, verification auto-escalates to manual approval and "
            "reverts once the incident clears."
        )
        self.text.content = body

    async def refresh(self, interaction: discord.Interaction):
        self._render()
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True

class LoggingSelect(discord.ui.Select):
    def __init__(self, layout: "LoggingOverviewLayout" = None):
        options = [
            discord.SelectOption(label=ev.replace("_", " ").title(), value=ev)
            for ev in config.LOG_EVENTS[:25]
        ]
        super().__init__(
            placeholder="Toggle a log event...",
            options=options,
            custom_id="logging:event_select",
        )
        self.layout_ref = layout

    async def callback(self, interaction: discord.Interaction):
        view = self.layout_ref
        event = self.values[0]
        if event in view.disabled_events:
            await db.raw_execute("DELETE FROM log_disabled_events WHERE guild_id=? AND event=?", (view.guild_id, event))
            view.disabled_events.discard(event)
        else:
            await db.raw_execute("INSERT INTO log_disabled_events (guild_id, event) VALUES (?, ?)", (view.guild_id, event))
            view.disabled_events.add(event)
        await view.refresh(interaction)


class LoggingOverviewLayout(discord.ui.LayoutView):
    def __init__(self, author_id: int, guild_id: int):
        super().__init__(timeout=180)
        self.author_id = author_id
        self.guild_id = guild_id
        self.category_channels: dict[str, int] = {}
        self.disabled_events: set = set()

        e = emoji_manager.get
        self.container = discord.ui.Container(accent_color=NEUTRAL)
        self.container.add_item(discord.ui.TextDisplay(f"## {e('logging_cat')} Logging"))
        self.container.add_item(discord.ui.Separator())
        self.text = discord.ui.TextDisplay("Loading...")
        self.container.add_item(self.text)
        self.container.add_item(discord.ui.Separator())
        self.events_text = discord.ui.TextDisplay("")
        self.container.add_item(self.events_text)
        self.container.add_item(discord.ui.Separator())
        self.select_row = discord.ui.ActionRow()
        self.select_row.add_item(LoggingSelect(layout=self))
        self.container.add_item(self.select_row)
        self.container.add_item(discord.ui.Separator())
        for item in footer_block():
            self.container.add_item(item)
        self.add_item(self.container)

    @classmethod
    async def create(cls, author_id: int, guild_id: int) -> "LoggingOverviewLayout":
        view = cls(author_id, guild_id)
        await view._load()
        view._render()
        return view

    async def _load(self):
        rows = await db.raw_fetch("SELECT category, channel_id FROM log_channels WHERE guild_id=?", (self.guild_id,))
        self.category_channels = {r["category"]: r["channel_id"] for r in rows}
        disabled_rows = await db.raw_fetch("SELECT event FROM log_disabled_events WHERE guild_id=?", (self.guild_id,))
        self.disabled_events = {r["event"] for r in disabled_rows}

    def _render(self):
        channel_lines = []
        for category_key, meta in config.LOG_CATEGORIES.items():
            channel_id = self.category_channels.get(category_key)
            status = f"<#{channel_id}>" if channel_id else "Not set"
            channel_lines.append(f"**{meta['label']}:** {status}")
        self.text.content = "\n".join(channel_lines) + "\n\n-# Run `logging setup` to auto-create all channels at once."

        on_icon, off_icon = "🟢", "🔴"
        event_lines = "\n".join(
            f"{off_icon if ev in self.disabled_events else on_icon} `{ev}`"
            for ev in config.LOG_EVENTS
        )
        active_count = len(config.LOG_EVENTS) - len(self.disabled_events)
        self.events_text.content = (
            f"**Active events:** {active_count}/{len(config.LOG_EVENTS)}\n\n{event_lines}"
        )

    async def refresh(self, interaction: discord.Interaction):
        self._render()
        await interaction.response.edit_message(view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This panel is not for you.", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for item in self.walk_children():
            if isinstance(item, (discord.ui.Button, discord.ui.Select)):
                item.disabled = True
