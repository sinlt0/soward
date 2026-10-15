---
title: Logging
description: Send moderation, security, member, message and server logs to your own channels.
order: 11
group: Moderation
---

## How logging works

Soward sorts events into five **categories**. Each category posts to its own channel through a webhook, so logs look separate and the bot does not need to be able to talk in that channel. You can set up all channels in one command, or point each category at a channel you already have.

| Category | Default channel | What it covers |
| --- | --- | --- |
| `mod` | `mod-logs` | Bans, softbans, unbans, kicks, mutes, unmutes, warnings, purges, lockdowns, unlocks, slowmode |
| `security` | `security-logs` | AutoMod actions, AntiNuke actions and quarantines, AntiRaid actions and raid mode, verification events |
| `member` | `member-logs` | Members joining and leaving, AutoRole actions |
| `message` | `message-logs` | Edited, deleted and bulk-deleted messages |
| `server` | `server-logs` | Channels and roles created or deleted, NSFW events, ticket events |

Messages from bots are not logged. Edited and deleted message text is shortened (500 characters for edits, 1000 for deletes), and log messages never ping anyone.

## Set it up

```
!logging setup
```

This creates a private `soward-logs` category with one channel per log category, and a webhook in each. The category is hidden from `@everyone`. Categories that are already set up are left alone, so it is safe to run again.

The bot needs **Manage Channels** and **Manage Webhooks** for this.

To use your own channels instead:

```
!logging channel mod #moderation-log
!logging channel message #message-log
```

## Command reference

All logging commands need Administrator. `!logs` works as a short name for `!logging`.

| Command | What it does | Needs |
| --- | --- | --- |
| `!logging` | Opens the logging overview panel. | Administrator |
| `!logging setup` | Creates the `soward-logs` category with a channel and webhook for each category. | Administrator, bot needs Manage Channels and Manage Webhooks |
| `!logging channel <category> <channel>` | Sets the channel for one category. Category is `mod`, `security`, `member`, `message` or `server`. | Administrator, bot needs Manage Webhooks |
| `!logging toggle <event>` | Turns a single event type off, or back on if it is off. | Administrator |
| `!logging remove <category>` | Stops logging a category and deletes its webhook. | Administrator |

## Turning off single events

Each category contains several events. A category with a channel posts all of its events unless you disable some. Disabled events are skipped even when their category has a channel.

```
!logging toggle message_edit
```

Run the command again to enable the event. If you type an unknown name, the bot replies with the list of valid events. Event names include `ban`, `softban`, `unban`, `kick`, `mute`, `unmute`, `warn`, `purge`, `lockdown`, `unlock`, `slowmode`, `message_edit`, `message_delete`, `message_bulk_delete`, `member_join`, `member_leave`, `channel_create`, `channel_delete`, `role_create`, `role_delete`, `automod_action`, `antinuke_action`, `antinuke_quarantine`, `antiraid_action`, `antiraid_raid_mode`, `verification_action`, `autorole_action`, `nsfw_action` and `ticket_action`.

## From the dashboard

The Logging page on the web dashboard lets you:

- See which channel each category uses, set or change it, or remove it.
- Run the one-click setup that creates the `soward-logs` category and any missing channels.
- Enable or disable each event type.

It does the same thing as the commands above.

## Troubleshooting

- **Nothing is logged**: the category needs a channel (`!logging` shows what is set), and the event must not be disabled.
- **"Could not create webhook"**: give the bot Manage Webhooks in that channel. A channel can hold at most 15 webhooks.
- **Logs stopped after someone deleted the webhook**: the bot clears the old webhook when it notices. Run `!logging channel <category> <channel>` again to create a new one.
- **Invalid category**: use one of `mod`, `security`, `member`, `message`, `server`.
