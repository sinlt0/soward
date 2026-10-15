---
title: Moderation
description: Bans, kicks, timeouts, warnings, notes, channel locks and case history.
order: 10
group: Moderation
---

## How moderation works

Moderation commands act on members and record what happened. Bans, kicks, mutes and similar actions are saved as **cases** with a case ID, the moderator, the reason and the time. Warnings are stored separately with a short 8-character ID. Every action is also sent to your [logging](/docs/logging) channels if you have them set up.

There is nothing to switch on. The commands work as soon as the bot is in your server and has the matching Discord permissions.

## Rules that apply to every action

- You need the Discord permission listed for the command, or a fake permission granted with `!fakeperm` (see below). Administrators and the bot's owners are always allowed.
- Members can only be moderated by someone whose top role is **higher** than theirs.
- The bot also needs the matching permission, and its top role must be above the target's top role.
- Reasons are optional. Without one the reason is saved as "No reason provided".
- Durations combine numbers and units: `s` seconds, `m` minutes, `h` hours, `d` days, `w` weeks. Examples: `30m`, `2h`, `1d12h`.

## Bans and kicks

```
!ban @user Spamming links
!tempban @user 3d Cooling off
!softban @user 7 Clean up their messages
!unban 123456789012345678 Appeal accepted
!kick @user Please read the rules
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!ban <member or ID> [reason]` | Bans a member. You can use a user ID for someone who is not in the server. | Ban Members |
| `!tempban <member or ID> <duration> [reason]` | Bans for a set time. The bot unbans automatically, checking once a minute. | Ban Members |
| `!softban <member> [days] [reason]` | Bans and immediately unbans, which deletes their recent messages. `days` is how many days of messages to delete, from 0 to 7. Default is 1. | Ban Members |
| `!unban <user ID> [reason]` | Unbans a user by ID and cancels any pending temp-ban. | Ban Members |
| `!kick <member> [reason]` | Kicks a member. | Kick Members |
| `!masskick <members...> [reason]` | Kicks several mentioned members at once after you confirm. Members you cannot act on are skipped. | Kick Members |

## Timeouts

| Command | What it does | Needs |
| --- | --- | --- |
| `!mute <member> <duration> [reason]` | Times a member out. Alias: `!timeout`. | Moderate Members |
| `!unmute <member> [reason]` | Removes a timeout. | Moderate Members |

Discord limits timeouts to 28 days.

## Warnings and notes

```
!warn @user Third reminder about spam
!warnings @user
!delwarn 3F9A1C2B
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!warn <member> [reason]` | Issues a warning and sends the member a direct message with the reason and case ID. | Manage Messages |
| `!warnings <member>` | Shows a member's warnings, newest first (up to 15). Alias: `!warns`. | Manage Messages |
| `!delwarn <case ID>` | Deletes one warning by its case ID. | Manage Messages |
| `!warnclear <member>` | Deletes all of a member's warnings after you confirm. | Manage Messages |
| `!note <member> <text>` | Saves a private moderator note about a member. | Manage Messages |
| `!notes <member>` | Shows a member's notes, newest first (up to 10). | Manage Messages |

Warnings do not trigger punishments on their own. They are a record for your team.

## Case history and stats

| Command | What it does | Needs |
| --- | --- | --- |
| `!cases [member]` | Shows recent moderation cases for a member, or for the whole server. Shows up to 10 and tells you how many more exist. | Manage Messages |
| `!modstats [member]` | Shows how many actions of each kind a moderator has taken. Defaults to you. | Manage Messages |

`!cases` lists bans, kicks, mutes and similar actions. Warnings are listed by `!warnings`.

## Cleaning up messages

| Command | What it does | Needs |
| --- | --- | --- |
| `!purge <amount> [member]` | Deletes up to 1000 recent messages in the current channel, optionally only from one member. Alias: `!clear`. | Manage Messages |
| `!purgebots [amount]` | Deletes recent messages sent by bots. Default 50, maximum 1000. | Manage Messages |

Your command message is deleted and the result message disappears after a few seconds. Discord cannot bulk delete messages older than 14 days.

## Locking channels and slowmode

| Command | What it does | Needs |
| --- | --- | --- |
| `!lockdown [channel] [reason]` | Stops `@everyone` from sending messages in a channel (the current one by default). Alias: `!lock`. | Manage Channels |
| `!unlock [channel] [reason]` | Restores sending in a channel. | Manage Channels |
| `!lockdownall [reason]` | Locks every text channel after you confirm. | Administrator |
| `!unlockall [reason]` | Unlocks every text channel that was locked. | Administrator |
| `!slowmode <seconds> [channel]` | Sets slowmode from 0 (off) to 21600 seconds. | Manage Channels |

## Nicknames and roles

| Command | What it does | Needs |
| --- | --- | --- |
| `!nickname <member> [new nickname]` | Changes a nickname. Leave the name out to reset it. Alias: `!nick`. | Manage Nicknames |
| `!role add <member> <role>` | Gives a role. The role must be below the bot's top role. | Manage Roles |
| `!role remove <member> <role>` | Takes a role away. | Manage Roles |

Running `!role` on its own shows a short usage hint.

## Fake permissions

Fake permissions let you allow a specific member or role to use a moderation command without giving them the real Discord permission. For example, grant `ban_members` to a trusted role so it can use `!ban`, while the role does not get Ban Members in Discord itself. Granting `administrator` as a node allows every command.

```
!fakeperm grant @Helpers manage_messages
!fakeperm revoke @Helpers manage_messages
!fakeperm list @Helpers
!plist
!fpsetup
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!fakeperm grant <member or role> <node>` | Grants a permission node. | Administrator |
| `!fakeperm revoke <member or role> <node>` | Removes a granted node. | Administrator |
| `!fakeperm list <member or role>` | Lists the nodes a member or role has. Note: you still need to type a node after the target, for example `!fakeperm list @Helpers x`. | Administrator |
| `!plist` | Shows every valid node with paging buttons. Full name: `!fakepermplist`. | Administrator |
| `!fpsetup` | Guided setup with buttons and menus to grant or revoke. Full name: `!fakepermsetup`. | Administrator |

Nodes are Discord permission names such as `ban_members`, `kick_members`, `moderate_members`, `manage_messages`, `manage_channels`, `manage_roles` and `manage_nicknames`. `!warn` also accepts the node `warn`, so you can let someone warn without giving them Manage Messages.

## Defaults and limits

| Setting | Value |
| --- | --- |
| Purge amount | 1 to 1000 |
| Softban message deletion | 0 to 7 days, default 1 |
| Slowmode | 0 to 21600 seconds |
| Warnings shown by `!warnings` | 15 |
| Notes shown by `!notes` | 10 |
| Cases shown by `!cases` | 10 (most recent 50 are loaded for a server) |
| Temp-ban check interval | Every minute |

## From the dashboard

The Moderation page on the web dashboard lets you:

- Warn, timeout (up to 28 days), remove a timeout, kick, ban (optionally for a set time) and unban a member. You enter the member's user ID and a reason.
- Browse recent cases and recent warnings, and delete a warning.

Dashboard actions create the same cases and log entries as the commands and follow the same role rules. Purge, lockdown and slowmode stay as commands because they depend on a channel. Notes, `!masskick`, nicknames, roles and fake permissions are commands only.

## Troubleshooting

- **"You cannot ... someone with a higher or equal role"**: your top role must be above the target's.
- **The command fails silently or Discord refuses it**: check that the bot has the permission and that its role sits above the target's role in Server Settings, then Roles.
- **A member with a fake permission still cannot use a command**: the node must match the command's permission name, for example `ban_members` for `!ban`.
- **`!purge` does not delete old messages**: Discord only allows bulk deletion of messages newer than 14 days.
