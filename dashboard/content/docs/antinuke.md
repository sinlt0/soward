---
title: AntiNuke
description: Stop mass bans, channel deletion, permission escalation and other destructive actions, and undo the damage.
order: 21
group: Security
---

## How AntiNuke works

AntiNuke watches your server's audit log for destructive actions such as deleting channels, deleting roles, banning or kicking members, creating webhooks and giving out dangerous permissions. It counts how many times each person does each kind of action. If one person reaches the limit for an action inside the detection window (**10 seconds** by default), AntiNuke punishes them right away, undoes what it can and warns your staff.

Some actions are **immediate**: a single occurrence is enough. These are tampering with quarantined members, changing [protected roles](/docs/security-center), giving `@everyone` dangerous channel permissions, changing the vanity URL, and any dangerous permission grant when strict mode or `@everyone` protection applies.

Things to know first:

- AntiNuke is **off by default**. Turn it on with `!antinuke enable` (Extra Owner or server owner), or apply a preset such as `!security preset balanced`.
- The bot needs **View Audit Log**. Without it AntiNuke cannot see who did what and does nothing.
- The bot ignores its own actions.
- Counting is per person and per action. Counts are kept in memory and reset if the bot restarts.
- Raid and threat systems are connected: a punishment raises the server's [incident state](#incident-state), adds to the [threat score](/docs/security-center), can start [AntiRaid](/docs/antiraid) raid mode and can start a server lockdown (`security.lockdown_on_nuke`).
- Beast Mode (a high [threat score](/docs/security-center)) halves every limit.

## Who is exempt

AntiNuke never punishes:

- The server owner, the bot's owners, Extra Owners and Trusted Admins.
- Members on the AntiNuke trusted list (`!antinuke trust add`).
- Members and roles on the [whitelist](/docs/security-center) for AntiNuke.
- Administrators, **only if** `admin_bypass` is on. It is **off by default**, so ordinary Administrators are watched. A trusted member who is currently quarantined is watched too.

Whether AutoMod and AntiRaid skip Administrators is separate: they always do.

## Setup

1. Move the bot's role high in your role list. It can only change people below its top role.
2. Create a role for quarantined members with no permissions, and deny it access to your channels.
3. Set that role and turn AntiNuke on:

```
!antinuke quarantinerole @Quarantined
!antinuke enable
```

4. Optionally pick a punishment and change limits:

```
!antinuke punishment ban
!antinuke threshold channel_delete 2
!antinuke trust add @TrustedBot
```

5. Run `!antinuke` on its own to open the overview panel, `!antinuke limits` to see every limit and `!antinuke settings` to see every setting.

## What AntiNuke watches

Each action has a **short limit** (inside the window) and an optional **hourly limit** (`0` turns it off). Each can be switched off with `enabled_<action>`. Change them with `!antinuke threshold <action> <number>` and `!antinuke hourly <action> <number>`.

| Action | What is counted | Default limit |
| --- | --- | --- |
| `channel_delete` | Channels deleted | 3 |
| `channel_create` | Channels created | 5 |
| `channel_update` | Channels edited | 5 |
| `role_delete` | Roles deleted | 3 |
| `role_create` | Roles created | 5 |
| `role_update` | Role edits that change permissions | 3 |
| `ban` | Members banned | 5 |
| `kick` | Members kicked | 5 |
| `prune` | Member prunes | 1 |
| `webhook_create` | Webhooks created | 3 |
| `webhook_delete` | Webhooks deleted | 3 |
| `emoji_change` | Emojis created or deleted | 5 |
| `sticker_change` | Stickers created or deleted | 5 |
| `invite_delete` | Invites deleted | 5 |
| `bot_add` | Bots added | 1 |
| `permission_escalation` | Dangerous permission grants to a role | 2 |
| `guild_update` | Changes to server settings | 2 |
| `integration_change` | Integration changes | 2 |
| `vanity_change` | Vanity URL changes | 1 (immediate) |
| `quarantine_touch` | Changing a quarantined member's roles | 1 (immediate) |
| `protected_role` | Giving or removing a protected role | 1 (immediate) |
| `channel_permission` | Giving `@everyone` Manage Channels, Manage Roles, Manage Webhooks or Mention Everyone in a channel | 1 (immediate) |

Limits are whole numbers from 1 to 1000.

## Protections beyond counting

| Setting | Default | What it does |
| --- | --- | --- |
| `strict_mode` | Off | Any dangerous permission added to a role by someone not exempt is punished at once and reverted. The dangerous permissions are Administrator, Manage Server, Manage Roles, Manage Channels, Manage Webhooks, Ban Members and Kick Members |
| `protect_everyone` | On | The same, but only for the `@everyone` role |
| `monitor_overwrites` | On | Reverts dangerous channel permissions given to `@everyone` |
| `quarantine_hold` | On | Punishes anyone who tries to change a quarantined member's roles, and puts the roles back |
| `watch_quarantined` | On | Keeps watching trusted members while they are quarantined |
| `bot_add_block` | On | Kicks a bot added by someone who is not trusted |
| `restore` | On | Rolls back what a punished person did in the last `rollback_window` (120 seconds): deleted channels and roles are recreated, created ones are deleted |
| `restore_from_backup` | Off | After a punishment, also recreates missing roles, channels and bans from the latest [backup](/docs/security-center) |
| `punish_cooldown` | 30 seconds | A person is not punished again within this time |
| `alert_owner` | On | Messages the server owner when AntiNuke triggers |

Restoring recreates objects, so channel and role IDs change, and members' role assignments are not brought back.

## Punishments

| Punishment | What happens |
| --- | --- |
| `quarantine` | Saves the member's roles, removes every role below the bot's top role and adds the quarantine role |
| `strip_roles` | Removes every role below the bot's top role. Nothing is saved |
| `kick` | Kicks the member |
| `ban` | Bans the member |
| `kick_bot` | Kicks the member only if it is a bot. A human gets their roles stripped instead. Available as a per-action override |

If someone with 3 or more quarantine offenses in the last 24 hours triggers a `kick`, `strip_roles` or `quarantine` punishment, it becomes a **ban**. A person who has already left the server is banned by ID.

Which punishment applies is decided in this order:

1. A per-action override from `!antinuke punishmentaction <action> <type>`.
2. The general punishment you set with `!antinuke punishment <type>`.
3. The built-in default: `bot_add` is `kick_bot` and everything else is `quarantine`.

Every punishment is saved to the AntiNuke log with an 8-character case ID, posted to the alert channel, sent to your [security log](/docs/logging) and (with `alert_owner`) sent to the server owner.

## Quarantine

Quarantine is the safest punishment because it can be undone. The bot saves the member's roles, removes the ones it can and adds the quarantine role. While quarantined, a member cannot use moderation or security commands, and nobody can change their roles except the server owner, Extra Owners and members whitelisted for `quarantine`.

**Only the server owner and Extra Owners can release** a quarantined member, with `!release @member` or from the dashboard. Trusted Admins and administrators cannot, and a quarantined member cannot release anyone, including themselves. Released members get back the saved roles that are still below the bot's top role.

If you do not set a quarantine role, quarantined members still lose their roles but get no replacement role. A quarantined member who leaves and rejoins is locked again.

## Permit tiers

Permit tiers are trusted levels on top of Discord permissions. See [Security Center](/docs/security-center) for what each level can change.

| Tier | Who can give or take it | Limit |
| --- | --- | --- |
| Extra Owner | The server owner only | 5 per server |
| Trusted Admin | The server owner or an Extra Owner | 5 per server |

Both tiers are exempt from AntiNuke, AutoMod and AntiRaid. A member holds one tier at a time.

## Incident state

Each punishment raises the server's incident state one step: `normal`, `elevated`, `lockdown`. At `lockdown`, Verification switches to manual approval until the state is reset.

## Commands

Everything with a setting is also available through `!antinuke set <setting> <value>`.

| Command | What it does | Needs |
| --- | --- | --- |
| `!antinuke` (alias `!an`) | Opens the overview panel | Administrator |
| `!antinuke settings [group]`, `get <key>`, `list <key>` | View settings | Administrator |
| `!antinuke trusted` | Lists trusted members | Administrator |
| `!antinuke logs` | Recent detections | Administrator |
| `!quarantinelist` (alias `!qlist`) | Who is quarantined | Administrator |
| `!antinuke limits` | Every short and hourly limit | Anyone |
| `!antinuke punishmentactions` | Per-action overrides | Anyone |
| `!permits` (alias `!securitytiers`) | Extra Owners and Trusted Admins | Anyone |
| `!antinuke set / add / remove <key> <value>` | Change any setting or list | Trusted Admin |
| `!antinuke strict <on/off>` | Strict mode | Trusted Admin |
| `!antinuke punishment <type>` | General punishment | Trusted Admin |
| `!antinuke punishmentaction <action> <type>` (alias `punishfor`) | Override for one action | Trusted Admin |
| `!antinuke removepunishmentaction <action>` | Remove an override | Trusted Admin |
| `!antinuke threshold <action> <number>` | Short limit | Trusted Admin |
| `!antinuke hourly <action> <number>` | Hourly limit | Trusted Admin |
| `!antinuke window <3-120>` | Detection window in seconds | Trusted Admin |
| `!antinuke quarantinerole <role>` | Role for quarantined members | Trusted Admin |
| `!antinuke restore`, `botblock`, `ownerdm <on/off>` | Toggle those protections | Trusted Admin |
| `!antinuke alertchannel <channel>` | Where alerts go | Trusted Admin |
| `!antinuke incident <status/elevate/reset>` | View or change the incident state | Trusted Admin |
| `!quarantine <member> [reason]` | Quarantine someone by hand. Cannot target yourself, the owner, the bot, anyone at or above your tier or role, or anyone the bot cannot manage | Trusted Admin |
| `!antinuke enable` / `disable` | Turn AntiNuke on or off | Extra Owner |
| `!antinuke reset <key or all>` | Restore defaults | Extra Owner |
| `!antinuke trust add / remove <member>` (alias `whitelist`) | Trusted list | Extra Owner |
| `!antinuke adminbypass <on/off>` | Let Administrators skip AntiNuke | Extra Owner |
| `!release <member>` | Release a quarantined member | Extra Owner |
| `!trustedadmin add / remove <member>` (alias `!ta`) | Trusted Admin tier | Extra Owner |
| `!extraowner add / remove <member>` (alias `!eo`) | Extra Owner tier | Server owner |

"Extra Owner" in the Needs column means an Extra Owner or the server owner. While the tier lock is on (the default), plain Administrators can only view.

## From the dashboard

Open **AntiNuke** under Security. You need to be the server owner or have Manage Server or Administrator (see [Using the dashboard](/docs/dashboard)).

- **Module settings:** the on/off switch, strict mode, the default punishment and whether to keep watching quarantined members.
- **Trusted members** and **permit tiers:** add or remove members by ID, under the same rules as the commands.
- **Punishment per action** and **action thresholds:** set overrides and the short limit for each action.
- **Quarantine role** and **quarantined members:** pick the role, quarantine someone by ID, or release them (server owner and Extra Owners only). The dashboard will not quarantine the server owner, anyone at or above your tier, or someone whose top role is at or above the bot's.

Hourly limits, restore options, the incident state and the other settings are commands for now.

## Troubleshooting

**Nothing happens when someone deletes lots of channels.** Check that AntiNuke is on, the bot has View Audit Log, and the person is not trusted or whitelisted. An Administrator is only exempt when `admin_bypass` is on.

**The punishment did not remove roles.** The bot can only change roles below its own top role. Move the bot's role higher.

**A kick turned into a ban.** The member already had 3 or more quarantine offenses in the last 24 hours.

**`!release` says Owner Only.** Only the server owner and Extra Owners can release members, and a quarantined member cannot release anyone.

**Someone lost their roles after adding a bot.** `bot_add` has a limit of 1. The bot is kicked if the person was not trusted, and the person is punished. With the default `kick_bot` override a human only has their roles stripped. Add trusted people to the trusted list, or raise the limit.

**Deleted channels came back with new IDs.** That is how restore works. Webhooks, integrations and member roles are not restored.
