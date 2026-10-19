---
title: NSFW channels
description: Lock NSFW channels to a role so only members who opt in can see them.
order: 24
group: Security
---

## How NSFW channels work

Instead of a one-click age gate, Soward hides your NSFW channels from everyone except one role. You pick the **NSFW role**, then **register** each NSFW channel. When a channel is registered and a role is set, the bot:

- denies **View Channel** to `@everyone`,
- allows View Channel for the NSFW role (and for the bot itself, so it can keep managing the channel).

Soward does not use Discord's own age-restricted setting. A channel counts as an NSFW channel for the bot when it is registered here, a role is set, and the channel is locked to that role. Commands with adult content, such as the `nsfw` option in the [anime](/docs/anime) commands and the `r` rating in [truth or dare](/docs/games-and-quotes), check this.

Before changing anything the bot saves what the channel looked like. Removing the channel, or clearing the role, restores those original permissions.

You decide how members get the NSFW role. Give it by hand, with a reaction role or with a ticket.

## Setup

1. Create a role for access, for example `NSFW`. The bot's top role must be above it.
2. Make sure the bot has **Manage Channels** and **Manage Roles**.
3. Set the role and register your channels:

```
!nsfw role @NSFW
!nsfw addchannel #nsfw-art #nsfw-chat
```

4. Check the result with `!nsfw`. Locked channels show a lock. A channel that shows "not locked" needs `!nsfw sync`.

You can register channels before setting a role. They are saved but nothing is locked until you set a role, and then every registered channel is locked at once.

## Command reference

| Command | What it does | Needs |
| --- | --- | --- |
| `!nsfw` | Shows the NSFW role and every registered channel with its lock state. | Manage Channels |
| `!nsfw viewchannels` | Same as `!nsfw`. Aliases: `view`, `channels`, `list`. | Manage Channels |
| `!nsfw role` | Shows the current NSFW role. | Administrator |
| `!nsfw role <role>` | Sets the NSFW role and locks every registered channel to it. Accepts a mention, ID or name. | Administrator |
| `!nsfw role reset` | Clears the role and restores every registered channel's original permissions, after you confirm. Also accepts `clear`, `remove`, `none`, `off` and `disable`. | Administrator |
| `!nsfw addchannel <channels...>` | Registers one or more text or forum channels and locks them if a role is set. Alias: `add`. | Administrator |
| `!nsfw removechannel <channels...>` | Unregisters channels and restores their original permissions. Aliases: `remove`, `delchannel`. | Administrator |
| `!nsfw sync` | Re-applies the lock to every registered channel. Use it after the bot's permissions or someone's edits broke the lock. | Administrator |

The bot itself needs **Manage Channels** and **Manage Roles** for `role`, `addchannel`, `removechannel` and `sync`. Commands that need Administrator also work for members who were granted the `administrator` fake permission, and `!nsfw` and `!nsfw viewchannels` accept the `manage_channels` fake permission (see [Moderation](/docs/moderation)).

## Rules for the NSFW role

- It cannot be `@everyone`, and it cannot be a bot or integration role.
- It must be below the bot's top role, unless the bot has Administrator.
- Setting the same role again does nothing. Use `!nsfw sync` to re-apply permissions.
- Changing to a different role moves all registered channels to the new role.

## Limits

| Limit | Value |
| --- | --- |
| Registered channels per server | 25 |
| Channel types | Text channels and forum channels |
| Delay between channel edits | About a third of a second, so large changes take a moment |

If you try to register more than 25 channels, the extras are skipped and listed in the reply.

## Automatic cleanup

- If a registered channel is **deleted**, it is removed from the list.
- If the NSFW role is **deleted**, the role setting is cleared but the channels stay locked, which means nobody can see them. A message is logged. Set a new role with `!nsfw role <role>` to give access back.

NSFW changes are recorded under the **Server Changes** log category as `nsfw_action` if you have [logging](/docs/logging) set up.

## From the dashboard

Open **NSFW Channels** (in the Utility category). You need to be the server owner or have Manage Server or Administrator (see [Using the dashboard](/docs/dashboard)). This module has no on/off switch or settings form. It has two tables:

- **NSFW role:** shows the current role. **Set role** picks a new one and locks every registered channel. **Clear** restores every channel's original permissions after you confirm.
- **NSFW channels:** shows each channel, up to 25, and whether it is locked to the role. **Add channel** registers a channel, **Remove** unregisters one and restores its permissions, and **Sync** re-applies the lock to all of them.

The dashboard uses the same checks as the commands, including the role hierarchy rule and the bot permissions.

## Troubleshooting

**The reply says missing permissions.** The bot needs Manage Channels and Manage Roles, and its role must be above the NSFW role.

**A channel shows "not locked".** Someone changed the channel's permissions, or no role is set. Run `!nsfw sync`.

**"Role too high".** Drag the bot's role above the NSFW role in Server Settings, then try again.

**Nobody can see the channels.** The NSFW role may have been deleted. Set a new one with `!nsfw role`, then give it to the members who should have access.

**A channel was made visible again after removing it.** Removing restores what the channel looked like when it was first registered. If it was visible to everyone then, it is visible again.
