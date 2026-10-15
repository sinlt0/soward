---
title: AntiRaid
description: Detect join floods and suspicious new accounts, and lock down joins with raid mode.
order: 22
group: Security
---

## How AntiRaid works

AntiRaid checks every new member (bots are ignored) in two ways:

1. **Suspicious accounts.** A new member is flagged if their account is younger than the minimum age, or if they have no avatar. Flagged members are kicked, banned or timed out.
2. **Join floods.** If too many people join within a short window, the server enters **raid mode**. While raid mode is on, every new member who is not trusted is actioned, flagged or not.

AntiRaid is **off by default**. While it is off, joins are only recorded and nobody is actioned.

Members who are exempt are never actioned: anyone with Administrator, the bot's owners, Extra Owners, Trusted Admins and members on the AntiNuke trusted list (see [AntiNuke](/docs/antinuke#who-is-exempt)).

## Setup

1. Make sure the bot has the permission it needs for your chosen action (Kick Members, Ban Members or Moderate Members) and that its role is above new members' roles.
2. Pick where raid alerts go and turn AntiRaid on:

```
!antiraid alertchannel #security-alerts
!antiraid enable
```

3. Adjust the checks to fit your server:

```
!antiraid minage 7
!antiraid velocity 10 30
!antiraid action kick
!antiraid noavatar on
```

4. Run `!antiraid` on its own to open the overview panel.

## Raid mode

Raid mode starts in these ways:

- **Join velocity.** The number of joins in the window reaches the limit (default 10 joins in 10 seconds).
- **Manually.** A staff member runs `!antiraid raidmode`, or presses the button in the panel or the dashboard.
- **AntiNuke.** When AntiNuke punishes someone, raid mode starts if AntiRaid is enabled.
- **Panic mode.** When AutoMod starts server-wide panic mode (3 or more different members reach panic-level heat within 60 seconds), raid mode starts if AntiRaid is enabled.

While raid mode is on, every new non-bot member who is not exempt gets the raid mode action, which is **kick** by default. A short alert is posted in the alert channel when raid mode starts.

Raid mode lasts **10 minutes** by default and ends by itself. Expiry is checked every 30 seconds. You can end it earlier with `!antiraid raidmode`. Starting raid mode also switches on the server-wide panic mode, which AutoMod and AntiNuke share, and ending raid mode switches it off.

Starting raid mode by hand works even when AntiRaid is switched off, but joins are only actioned while AntiRaid is enabled.

## What flagged members get

| Action | What happens |
| --- | --- |
| `kick` | The member is kicked. This is the default. |
| `ban` | The member is banned and their last day of messages is deleted. |
| `timeout` | The member is timed out for 1 hour. |

The action for suspicious accounts is set with `!antiraid action`. The action during raid mode is **kick**. It has no command or dashboard control.

Every flagged join is saved with the member, the action taken and the time, and sent to the security channel if you have [logging](/docs/logging) set up.

## Command reference

Commands that need Administrator also work for members who were granted the `administrator` fake permission (see [Moderation](/docs/moderation)).

| Command | What it does | Needs |
| --- | --- | --- |
| `!antiraid` | Opens the overview panel. Alias: `!raid`. | Administrator |
| `!antiraid enable` | Turns AntiRaid on. | Administrator |
| `!antiraid disable` | Turns AntiRaid off. | Administrator |
| `!antiraid minage <days>` | Sets the minimum account age in days. Younger accounts are flagged. Use `0` to stop flagging by age. | Administrator |
| `!antiraid velocity <count> [seconds]` | Raid mode starts after `count` joins within `seconds`. The window defaults to 10 seconds. | Administrator |
| `!antiraid action <kick/ban/timeout>` | Sets the action for flagged joins. | Administrator |
| `!antiraid noavatar <on/off>` | Turns flagging of accounts without an avatar on or off. Alias: `!antiraid avatar`. | Administrator |
| `!antiraid alertchannel <channel>` | Sets the text channel for raid mode alerts. | Administrator |
| `!antiraid raidmode` | Turns raid mode on if it is off, or off if it is on. | Administrator |
| `!antiraid status` | Shows whether raid mode and panic mode are active, what triggered raid mode, when it started and when it expires. | Anyone |
| `!antiraid logs` | Shows the 15 most recent flagged joins with the action taken. | Administrator |

## Settings and defaults

| Setting | Default | Notes |
| --- | --- | --- |
| AntiRaid | Off | |
| Minimum account age | 7 days | Dashboard allows 0 to 365 days |
| Flag accounts with no avatar | On | |
| Join velocity | 10 joins in 10 seconds | Dashboard allows 2 to 200 joins in 2 to 300 seconds |
| Action on flagged joins | Kick | Kick, ban or timeout |
| Action during raid mode | Kick | Not configurable by command |
| Raid mode length | 10 minutes | Dashboard allows 1 to 1440 minutes |
| Timeout length | 1 hour | Fixed |
| Alert channel | Not set | |

The bot keeps the 200 most recent joins to count velocity, so a join limit above 200 can never be reached.

## From the dashboard

Open **AntiRaid** under the Security modules. You need to be the server owner or have Manage Server or Administrator (see [Using the dashboard](/docs/dashboard)).

- **Module settings:** on/off switch, minimum account age in days, joins that trigger a raid, the window in seconds, flag accounts without an avatar, the action on flagged joins, raid mode length in minutes and the alert channel.
- **Raid mode:** shows whether raid mode is active, what triggered it, when it expires and whether server panic mode is active, with a button to start or end raid mode.
- **Recent flagged joins:** the latest 25 flagged members with the action and time.

## Troubleshooting

**Nobody is being kicked.** Check that AntiRaid is on, the account really is under the age limit or has no avatar, and the bot has the permission for the chosen action with a role above the member's.

**Real new members are being kicked.** Lower `!antiraid minage`, turn off `!antiraid noavatar`, or end raid mode with `!antiraid raidmode`. During raid mode every new member is kicked, not only suspicious ones.

**Raid mode keeps coming back.** Another system may be starting it. Run `!antiraid status` to see the trigger. `join_velocity` means the join limit was hit, `antinuke_incident` means AntiNuke punished someone, `automod_heat_panic` means AutoMod started panic mode, and `manual:<id>` means a staff member started it.

**No alert appeared.** Set one with `!antiraid alertchannel` and make sure the bot can send messages there.
