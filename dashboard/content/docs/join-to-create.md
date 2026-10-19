---
title: Join to Create
description: Temporary voice channels that members create by joining a hub, with owner controls and automatic cleanup.
order: 42
group: Community
---

## How it works

Members join a **hub** voice channel. Soward creates a private voice channel for them, moves them into it, and deletes it when everyone has left. Each channel has a control panel in its text chat so the owner can lock, rename and manage it.

## Set up

```
!jtc setup
```

This creates a **Temporary Voice** category and a **Join to Create** hub. Soward needs Manage Channels and Move Members. You can also use any voice channel you already have:

```
!jtc add #Create-a-room [category]
!jtc remove #Create-a-room
!jtc list
```

A server can have 2 hubs, or 10 with Premium.

## Hub settings

| Command | What it does |
|---|---|
| `!jtc name <hub> <template>` | Channel name. Variables: `{user}` display name, `{username}`, `{count}` |
| `!jtc limit <hub> <0-99>` | Default user limit, 0 for none |
| `!jtc bitrate <hub> <kbps>` | Default bitrate, capped by your boost level |
| `!jtc category <hub> <category>` | Where new channels are created |

New channels copy the hub's permissions, so a role restriction on the hub applies to every channel it creates.

## Controlling your channel

The owner uses the buttons in the channel's chat, or `!voice` commands.

| Control | What it does |
|---|---|
| Lock / Unlock | Stop or allow new members from joining |
| Hide / Unhide | Hide the channel from everyone else |
| Rename, Limit | Change the name or the user limit |
| Permit | Let a member in even when locked or hidden |
| Block / Unblock | Keep a member out and remove them if they are inside |
| Kick | Remove someone from the channel |
| Transfer | Give the channel to a member who is in it |
| Claim | Take a channel whose owner left |
| Delete | Delete the channel |

Commands: `!voice lock`, `unlock`, `hide`, `unhide`, `rename <name>`, `limit <n>`, `permit`, `block`, `unblock`, `kick`, `transfer <member>`, `claim`, `delete`, `panel`.

Soward remembers each member's name, limit and lock choice and applies them to their next channel. If the owner leaves while others stay, ownership moves to someone still inside. Members with Manage Channels can use the controls in any temporary channel.

## Good to know

- Empty channels are deleted right away, and a cleanup runs every few minutes in case an event was missed.
- A member who already has a channel from the same hub is moved back into it instead of getting a second one.
- Joining repeatedly is rate limited, and a server can hold up to 150 temporary channels at once.
- Soward needs View Channel, Connect, Manage Channels and Move Members in the hub's category.
