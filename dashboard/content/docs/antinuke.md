---
title: AntiNuke
description: Stop mass bans, channel deletion and other destructive actions with limits, punishments and quarantine.
order: 21
group: Security
---

## How AntiNuke works

AntiNuke watches your server's audit log for destructive actions such as deleting channels, deleting roles, banning or kicking members and creating webhooks. It counts how many times each person does each kind of action. If one person reaches the limit for an action inside the detection window (**10 seconds** by default, change it with `!antinuke window`), AntiNuke punishes them right away. The default punishment is **quarantine**: the member loses their roles until the server owner releases them.

A few things to know first:

- AntiNuke is **off by default**. Turn it on with `!antinuke enable`.
- The bot needs the **View Audit Log** permission. Without it AntiNuke cannot see who did what and does nothing.
- The bot ignores its own actions.
- Counting is per person, per action type. Counts are kept in memory, so they reset if the bot restarts.
- Some members are never checked. See [Who is exempt](#who-is-exempt).
- After every punishment the server's **incident state** goes up one step (normal, elevated, lockdown). If [AntiRaid](/docs/antiraid) is enabled, a punishment also starts raid mode.

## Setup

1. Move the bot's role high in your role list. It can only remove, kick or ban people below its top role.
2. Create a role for quarantined members. Give it no permissions and deny it access to your channels.
3. Set that role and turn AntiNuke on:

```
!antinuke quarantinerole @Quarantined
!antinuke enable
```

4. Optionally pick a different default punishment and change limits:

```
!antinuke punishment ban
!antinuke threshold channel_delete 2
!antinuke trust add @TrustedBot
```

5. Run `!antinuke` on its own to open the overview panel and check the result. Only the person who ran the command can use its buttons.

## What AntiNuke watches

Each action has its own limit. Reaching the limit (counting the action that hits it) inside the window triggers the punishment. Change a limit with `!antinuke threshold <action> <number>`, or set an hourly limit with `!antinuke hourly <action> <number>`. See [Security Center](/docs/security-center) for tiers, the whitelist and all settings.

| Action name | What is counted | Default limit |
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
| `emoji_change` | Emojis created | 5 |
| `sticker_change` | Stickers created | 5 |
| `bot_add` | Bots added to the server | 1 |
| `permission_escalation` | Dangerous permission grants (see strict mode) | 2 |
| `guild_update` | Changes to the server name, icon or vanity URL | 2 |
| `integration_change` | Integration updates | 2 |

Notes on the table:

- `prune` can be configured, but the bot does not currently watch for prunes, so it never triggers.
- Strict mode punishes a dangerous permission grant immediately and does not use the `permission_escalation` limit.
- Limits must be at least 1. A smaller number is saved as 1.

## Punishments

| Punishment | What happens |
| --- | --- |
| `quarantine` | Saves the member's roles, removes every role below the bot's top role and adds the quarantine role (if you set one). |
| `strip_roles` | Removes every role below the bot's top role. Nothing is saved for later. |
| `kick` | Kicks the member. If they already have 3 or more quarantine offenses in the last 24 hours, the kick becomes a ban. |
| `ban` | Bans the member. |
| `kick_bot` | Kicks the member only if it is a bot. A human gets their roles stripped instead. Only available as a per-action override. |

Which punishment is used for an action is decided in this order:

1. A per-action override you set with `!antinuke punishmentaction`.
2. The general punishment you set with `!antinuke punishment`, if you have set one.
3. The built-in default for that action.

Built-in defaults: `bot_add` is `kick_bot`. Every other action is `quarantine`.

Every punishment is saved to the AntiNuke log with an 8-character ID, and a security log entry is sent if you have [logging](/docs/logging) set up.

## Who is exempt

These members are never punished by AntiNuke (and are also skipped by AutoMod and AntiRaid):

- Anyone with the **Administrator** permission, including the server owner.
- The bot's own owners.
- Extra Owners and Trusted Admins.
- Members on the trusted list (`!antinuke trust add`).

If a member with Administrator carries out a mass delete, AntiNuke will not act. Protect your server by giving staff narrower permissions such as Manage Channels, rather than Administrator.

## Strict mode

```
!antinuke strict on
```

Strict mode watches role edits. When someone who is not exempt changes a role's permissions and the role then has any of these permissions, they are punished at once, whatever the limits are, and the role's permissions are cleared:

Administrator, Manage Server, Manage Roles, Manage Channels, Manage Webhooks, Ban Members, Kick Members.

Strict mode is off by default.

## Command reference

Commands in this table that need Administrator also work for members who were granted the `administrator` fake permission (see [Moderation](/docs/moderation)).

| Command | What it does | Needs |
| --- | --- | --- |
| `!antinuke` | Opens the overview panel with status, thresholds, overrides, permits and panic mode. Alias: `!an`. | Administrator |
| `!antinuke enable` | Turns AntiNuke on. | Administrator |
| `!antinuke disable` | Turns AntiNuke off. | Administrator |
| `!antinuke strict <on/off>` | Turns strict mode on or off. | Administrator |
| `!antinuke punishment <type>` | Sets the general punishment: `ban`, `kick`, `strip_roles` or `quarantine`. | Administrator |
| `!antinuke punishmentaction <action> <type>` | Sets a punishment for one action: `ban`, `kick`, `kick_bot`, `strip_roles` or `quarantine`. Alias: `punishfor`. | Administrator |
| `!antinuke removepunishmentaction <action>` | Removes an override so the action uses the general setting again. | Administrator |
| `!antinuke punishmentactions` | Lists your overrides, or the built-in defaults if you have none. Alias: `listpunishments`. | Anyone |
| `!antinuke threshold <action> <number>` | Sets the limit for an action. Only the actions in the table above are accepted. | Administrator |
| `!antinuke quarantinerole <role>` | Sets the role given to quarantined members. | Administrator |
| `!antinuke trust add <member>` | Adds a member to the trusted list. Alias: `!antinuke whitelist`. | Owner or Extra Owner |
| `!antinuke trust remove <member>` | Removes a member from the trusted list. | Owner or Extra Owner |
| `!antinuke incident status` | Shows the incident state. | Administrator |
| `!antinuke incident elevate` | Raises the incident state by one step. | Administrator |
| `!antinuke incident reset` | Sets the incident state back to normal. | Administrator |
| `!quarantine <member> [reason]` | Quarantines a member by hand. The default reason is "Manually quarantined". | Administrator |
| `!release <member>` | Releases a quarantined member and gives their roles back. | Server owner only |
| `!quarantinelist` | Lists everyone currently quarantined, with the reason and time. Alias: `!qlist`. | Administrator |
| `!extraowner add <member>` | Gives Extra Owner. Alias: `!eo`. | Server owner |
| `!extraowner remove <member>` | Takes Extra Owner away. | Server owner |
| `!trustedadmin add <member>` | Gives Trusted Admin. Alias: `!ta`. | Server owner or Extra Owner |
| `!trustedadmin remove <member>` | Takes Trusted Admin away. | Server owner or Extra Owner |
| `!permits` | Lists every Extra Owner and Trusted Admin. Alias: `!securitytiers`. | Anyone |

The incident states are `normal`, `elevated` and `lockdown`. Each punishment raises the state one step, up to `lockdown`.

## Quarantine

Quarantine is the safest punishment because it can be undone. The bot saves the member's roles, removes the ones it can, and adds the quarantine role. Only the real server owner (or the bot's own owners) can run `!release`. This cannot be delegated, not even to Extra Owners or administrators. Released members get back the saved roles that are still below the bot's top role, and the quarantine role is removed.

If you do not set a quarantine role, quarantined members still lose their roles but get no replacement role.

## Permit tiers

Permit tiers are two levels of trusted people on top of Discord permissions.

| Tier | Who can give or take it | Limit |
| --- | --- | --- |
| Extra Owner | The server owner only | 5 per server |
| Trusted Admin | The server owner or an Extra Owner | 5 per server |

Both tiers are exempt from AntiNuke, AutoMod and AntiRaid. A member holds one tier at a time. Giving someone a tier they already hold is refused.

## Settings and defaults

| Setting | Default |
| --- | --- |
| AntiNuke | Off |
| Detection window | 10 seconds, adjustable with `!antinuke window` |
| General punishment | Quarantine |
| Strict mode | Off |
| Quarantine role | Not set |
| Offense window for kick to ban upgrade | 24 hours |
| Permit tier limit | 5 Extra Owners and 5 Trusted Admins |

## From the dashboard

Open **AntiNuke** under the Security modules. You need to be the server owner or have Manage Server or Administrator (see [Using the dashboard](/docs/dashboard)).

- **Module settings:** on/off switch, strict mode, the default punishment (quarantine, strip roles, kick or ban) and a switch named "Keep watching quarantined members".
- **Trusted members:** add a member by ID or remove them.
- **Permit tiers:** grant or revoke Extra Owner and Trusted Admin by member ID. The same rules about who can grant apply.
- **Punishment per action:** set or remove an override for each action. This list also offers `kick_bot`.
- **Action thresholds:** edit the limit for each action, from 1 to 1000. The table shows the default next to your value.
- **Quarantine role:** pick the role.
- **Quarantined members:** see who is quarantined, quarantine someone by ID with an optional reason (up to 300 characters), or release them. Releasing is only allowed for the server owner. The dashboard will not quarantine the server owner or someone whose top role is at or above the bot's.

The dashboard does not manage the incident state. Use `!antinuke incident` for that.

## Troubleshooting

**Nothing happens when someone deletes lots of channels.** Check that AntiNuke is on, the bot has View Audit Log, and the person is not an administrator or on the trusted list.

**The punishment did not remove roles.** The bot can only change roles below its own top role. Move the bot's role higher.

**A kick turned into a ban.** The member already had 3 or more quarantine offenses in the last 24 hours.

**`!release` says Owner Only.** This is intentional. Only the server owner can release members.

**Someone lost their roles after adding a bot.** `bot_add` has a limit of 1 and the default punishment `kick_bot`. The punishment lands on the person who added the bot, and `kick_bot` only kicks bots, so a human gets their roles stripped. Add trusted people to the trusted list, or raise the limit.
