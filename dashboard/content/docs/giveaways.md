---
title: Giveaways
description: Timed giveaways with entry requirements, bonus entries, rerolls and polls.
order: 40
group: Community
---

## How giveaways work

A giveaway is a message with an **Enter Giveaway** button. Members press the button to enter and press it again to leave. When the timer runs out, the bot picks random winners from the entries, announces them in the same channel and edits the giveaway message to show the result.

- There is nothing to turn on. The commands work as soon as the bot is in your server.
- Each member can enter once. Bonus entries (see below) only change their chance of winning.
- The bot checks for finished giveaways every 10 seconds, so a giveaway can end a few seconds after its timer.
- If nobody entered, the bot posts "No one entered this giveaway."
- If there are fewer entrants than winners, the number of winners is lowered to match.
- Giveaways keep working after the bot restarts.

Every giveaway command needs **Manage Server** (or the matching fake permission, see [moderation](/docs/moderation)), except `ginfo`, `glist` and `pollresults`, which anyone can use. Bot owners are always allowed.

## Quick start

```
!giveaway start 1h 2 Discord Nitro
!grequire 123456789012345678 @Member
!gbonus 123456789012345678 @Booster 2
!gend 123456789012345678
```

1. Run `!giveaway start <duration> <winners> <prize>` in the channel where the giveaway should appear. The bot posts the giveaway and replies with its **message ID** for 30 seconds.
2. Optionally add requirements with `!grequire`, `!gminage` and `!gbonus`, using that message ID.
3. Wait for the timer, or end it early with `!gend`.

Durations combine numbers and units: `s` seconds, `m` minutes, `h` hours, `d` days, `w` weeks. Examples: `30m`, `2h`, `1d12h`.

You can also write `!giveaway <duration> <winners> <prize>` without the word `start`. The alias `!gstart` works the same way.

## Giveaway commands

`<giveaway>` below is the **message ID** of the giveaway message. You can get it from the reply when you start the giveaway, from `!glist`, or by copying the message ID in Discord.

| Command | What it does | Needs |
| --- | --- | --- |
| `!giveaway start <duration> <winners> <prize>` | Starts a giveaway in the current channel. Winners must be at least 1. Aliases: `!giveaway`, `!gstart`. | Manage Server |
| `!grequire <giveaway> [role]` | Requires entrants to have a role. Run it without a role to remove the requirement. | Manage Server |
| `!gminage <giveaway> <days>` | Requires accounts to be at least this many days old. `0` removes the requirement. | Manage Server |
| `!gbonus <giveaway> <role> <extra>` | Gives members with the role extra entries. `0` removes the bonus for that role. | Manage Server |
| `!gend <giveaway>` | Ends an active giveaway now, picks winners and announces them. | Manage Server |
| `!gcancel <giveaway>` | Cancels an active giveaway without picking a winner, after you confirm. The message is changed to "Giveaway Cancelled". | Manage Server |
| `!greroll <giveaway>` | Picks one new random winner from all entries and announces it. | Manage Server |
| `!gentries <giveaway>` | Lists who entered. Shows the first 30 and how many more there are. | Manage Server |
| `!ginfo <giveaway>` | Shows status, host, winners, entry count, end time, required role, minimum account age and bonus roles. | Anyone |
| `!glist` | Lists active giveaways in this server (up to 10) with their message IDs. | Anyone |

### Requirements and bonus entries

- **Required role.** A member without the role gets a message saying they need it. The check happens when they press the button.
- **Minimum account age.** Measured in days from the date the Discord account was created.
- **Bonus entries.** `!gbonus <giveaway> @Role 2` gives members with that role 2 extra entries, so they count as 3 in the draw. You can set a bonus for several roles. A member with several bonus roles gets all of them added up. Bonus entries are counted when winners are drawn, using the roles the member has at that moment.
- `!grequire`, `!gminage` and `!gbonus` only work on giveaways that have not ended.
- The member's own entry total is shown to them when they enter.

### Rerolling

`!greroll` draws one new winner from everyone who entered, using the same bonus entries. It does not remove earlier winners from the pool, so a previous winner can be drawn again. It also works on a giveaway that has not ended yet.

## Polls

Polls live in the same module. A poll is a message with a drop-down menu. Members pick an option, and picking again changes their vote.

```
!poll "Which game next?" Minecraft | Valorant | Rocket League
!pollresults 123456789012345678
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!poll <question> <option> \| <option> ...` | Posts a poll with 2 to 10 options separated by `\|`. Put the question in quotes if it has spaces. | Manage Server |
| `!pollresults <message ID>` | Shows the current vote counts and percentages. | Anyone |

Polls do not end on their own and there is no command to close one. Use `!pollresults` to see the latest numbers. Option names are cut to 100 characters.

## Limits and defaults

| Setting | Value |
| --- | --- |
| Giveaways per server | No limit |
| Winners (commands) | 1 or more |
| Winners (dashboard) | 1 to 20 |
| Duration (commands) | Any combination of `s`, `m`, `h`, `d`, `w` |
| Duration (dashboard) | 10 seconds to 365 days |
| Minimum account age (dashboard) | 0 to 3650 days |
| Bonus entries per role (dashboard) | 0 to 50 |
| Prize length (dashboard) | 100 characters |
| Poll options | 2 to 10 |

Giveaways and polls have no Premium limits.

## From the dashboard

Open your server, then **Giveaways**. The table shows active giveaways first, then recent ones (up to 25), with prize, channel, winners, end time and entry count.

You can do these from the web:

- **Start giveaway.** Prize, channel, duration (for example `1h30m`), winners, required role and minimum account age.
- **Requirements.** On an active giveaway, change the required role and minimum account age, and set the bonus entries for one role at a time. Saving with an empty required role removes the requirement.
- **End now.** Ends the giveaway and announces winners, like `!gend`.
- **Cancel.** Cancels without picking a winner.
- **Reroll.** On an ended giveaway, picks one new winner and announces it in the giveaway channel. It only works if at least one person entered.

Still needs commands: polls, `!gentries`, `!ginfo`, `!glist`, and minimum age or bonus changes beyond the dashboard ranges. See [using the dashboard](/docs/dashboard) for how to sign in.

## Troubleshooting

- **"No active giveaway found with that message ID."** The giveaway has already ended or the ID is wrong. Copy the ID of the giveaway message itself, not the bot's reply.
- **Members say the button does nothing.** They may be missing the required role or be below the minimum account age. The bot tells them privately which one.
- **Winner was announced but the giveaway message looks unchanged.** The bot could not edit the message, for example because it was deleted. The announcement is still posted.
- **Nothing was posted when the timer ended.** The giveaway channel was deleted, or the bot lost permission to send messages there.
