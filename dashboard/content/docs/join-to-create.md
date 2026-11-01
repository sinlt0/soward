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

## Voice interface

Soward can keep one shared **voice-interface** text channel with a Components V2 panel. It has four dropdown menus, with plain text options and no emojis:

- **Channel settings:** Lock, Unlock, Hide, Unhide, Rename, Reset to defaults, Claim and Delete.
- **Member management:** Permit, Block, Unblock, Kick, Mute, Unmute and Transfer ownership. Mute stops a member speaking in your channel only.
- **Limits and quality:** Set user limit, Increase limit, Decrease limit, Remove user limit, bitrate (64, 96, 128 kbps or the server maximum) and video quality (auto or 720p).
- **Voice region:** Automatic or a specific region.

The menus act on the temporary channel you are currently in, and only its owner (or someone with Manage Channels) can use them. Rename and Set user limit open a small form, and member actions open a member picker.

When someone creates a temporary channel and no interface exists, Soward creates the channel in the hub's category and posts the panel. If one already exists it is reused, and the small panel inside each voice channel is skipped. When no temporary channel is active any more, the interface channel is deleted, and it is created again when the next one is made.

| Command | What it does | Needs |
| --- | --- | --- |
| `!jtc interface` | Shows the interface status. | Manage Channels |
| `!jtc interface create [#channel]` | Creates the interface, or posts the panel in a channel you choose. | Manage Channels |
| `!jtc interface remove` | Deletes the interface channel. | Manage Channels |
| `!jtc interface auto <on\|off>` | Turns automatic creation and cleanup on or off. | Manage Channels |

## Good to know

- Empty channels are deleted right away, and a cleanup runs every few minutes in case an event was missed.
- A member who already has a channel from the same hub is moved back into it instead of getting a second one.
- Joining repeatedly is rate limited, and a server can hold up to 150 temporary channels at once.
- Soward needs View Channel, Connect, Manage Channels and Move Members in the hub's category.
