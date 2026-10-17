---
title: Leveling
description: XP from messages and voice, levels, role rewards, multipliers and leaderboards.
order: 44
group: Community
---

## How leveling works

Members earn **XP** by chatting and by spending time in voice channels. XP adds up to a **level**. When a member levels up, the bot can announce it and hand out role rewards. Leveling is **off** until you turn it on.

| Source | Default |
| --- | --- |
| Messages | 15 to 25 XP per message, at most once every 60 seconds per member |
| Voice | 10 XP per minute, only while unmuted and not alone |

- Bots and direct messages never earn XP.
- XP is per server. Multipliers (see below) can raise or lower what members earn.
- Every XP gain is at least 1 XP.

### Level curve

To reach level `n` a member needs a total of `5 x n x n + 50 x n + 100` XP.

| Level | Total XP needed |
| --- | --- |
| 1 | 155 |
| 5 | 475 |
| 10 | 1,100 |
| 20 | 3,100 |
| 50 | 15,100 |

## Quick start

```
!leveling enable
!leveling channel #level-ups
!leveling levelrole 10 @Active
!leveling message {user} just hit level {level}!
```

Until you pick an announcement channel, level-ups are not announced, because the default announce mode is `channel` with no channel set.

Members then use `!rank` and `!leaderboard`. `!leveling` on its own shows the current settings.

## Member commands

These work for everyone, once leveling is enabled.

| Command | What it does | Needs |
| --- | --- | --- |
| `!rank [member]` | Shows a rank card image with level, XP progress, leaderboard position and prestige if any. Defaults to you. Aliases: `!level`, `!lvl`. | Anyone |
| `!leaderboard [period]` | Shows the top 10. The period is `alltime` (default), `weekly` or `monthly`. Aliases: `!lb`, `!top`. | Anyone |
| `!leveling levelroles` | Lists the configured role rewards. | Manage Server |
| `!leveling variables` | Lists the level-up message placeholders. Alias: `!leveling vars`. | Anyone |

If a member has no XP yet, `!rank` says they have not earned any.

## Settings commands

All of these need **Manage Server** (or the matching fake permission, see [moderation](/docs/moderation)). Bot owners are always allowed. The main command is `!leveling`, with the alias `!lvlconfig`.

| Command | What it does | Needs |
| --- | --- | --- |
| `!leveling` | Shows status, text XP, voice XP, role reward mode, announce mode and reset settings. | Manage Server |
| `!leveling enable` | Turns leveling on. | Manage Server |
| `!leveling disable` | Pauses XP. Saved XP and settings are kept. | Manage Server |
| `!leveling channel <#channel>` | Sets the level-up channel and switches the announce mode to `channel`. | Manage Server |
| `!leveling announce <channel\|dm\|off>` | Sends level-ups in the channel, by direct message, or not at all. | Manage Server |
| `!leveling message <text>` | Sets the level-up message and shows a preview. | Manage Server |
| `!leveling setxp <member> <amount>` | Sets a member's total XP. Their level is recalculated. Negative numbers become 0. | Manage Server |
| `!leveling resetxp <member>` | Sets a member's XP and level to 0. | Manage Server |
| `!leveling levelrole <level> <role>` | Gives a role when a member reaches a level. | Manage Server |
| `!leveling removelevelrole <level> <role>` | Removes one role reward. | Manage Server |
| `!leveling rolestack <stack\|nonstack>` | Chooses how role rewards combine. | Manage Server |
| `!leveling multiplier` | Lists XP multipliers with their IDs. Alias: `!leveling mult`. | Manage Server |
| `!leveling multiplier add <global\|channel\|role> [target] <value>` | Adds an XP multiplier. Global needs no target. | Manage Server |
| `!leveling multiplier remove <ID>` | Removes a multiplier by its ID. | Manage Server |
| `!leveling noxp` | Lists the no-XP channels and roles. | Manage Server |
| `!leveling noxp channel <#channel>` | Toggles a text channel as no-XP. | Manage Server |
| `!leveling noxp role <role>` | Toggles a role as no-XP. | Manage Server |
| `!leveling weeklyreset` | Turns the automatic weekly leaderboard reset on or off. | Manage Server |
| `!leveling monthlyreset` | Turns the automatic monthly leaderboard reset on or off. | Manage Server |

## Level-up messages

The default message is `{user} just reached **level {level}**!`. Change it with `!leveling message`. Set where it goes with `!leveling channel` or `!leveling announce`.

- `channel` posts in the level-up channel. If no channel is set, nothing is posted.
- `dm` sends it to the member by direct message. It is skipped if their DMs are closed.
- `off` turns announcements off. XP and role rewards still work.

Level-up placeholders:

| Placeholder | Output |
| --- | --- |
| `{level}` | The member's new level. |
| `{oldlevel}` | The level before. |
| `{xp}` | The member's total XP. |
| `{rank}` | The member's leaderboard position. |

The usual member and server placeholders also work, such as `{user}`, `{username}`, `{userid}`, `{server}` and `{membercount}`. The channel placeholders are not filled in. Run `!leveling variables` for the full list.

## Role rewards

```
!leveling levelrole 5 @Regular
!leveling levelrole 10 @Active
!leveling rolestack nonstack
!leveling levelroles
```

- A member gets the role when they reach the level. You can give more than one role at the same level.
- Rewards are checked each time someone levels up, and all rewards at or below their new level are given, so skipped ones are caught up.
- Adding a reward does not give it to members who are already past that level. It is given at their next level-up.
- `stack` (default) lets members keep every reward role they earned.
- `nonstack` keeps only the reward role for the highest level reached and removes their other reward roles.
- The bot's top role must be above the reward roles.
- `!leveling setxp` and `!leveling resetxp` do not change a member's roles, and removing a reward does not take the role from members who have it.

## Multipliers

A multiplier scales the XP a member earns, for both messages and voice.

```
!leveling multiplier add channel #events 2
!leveling multiplier add role @Booster 1.5
!leveling multiplier add global 2
!leveling multiplier remove 3F9A1C2B
```

- **Scopes.** `global` applies server-wide, `channel` applies in one channel (for voice, the voice channel), `role` applies to members with a role.
- **Value.** Any number above 0. `2` doubles XP, `0.5` halves it.
- For `global`, the target is ignored, but the command still needs something in that spot, such as `all`.
- **Combining.** Within one scope the highest multiplier that applies is used. Different scopes multiply together. A global `2` plus a role `1.5` gives `3`.
- The result is rounded down, with a minimum of 1 XP.

## Excluding channels and roles

```
!leveling noxp channel #bot-spam
!leveling noxp role @Muted
```

The commands toggle: run it again to remove the exclusion. Messages in a no-XP channel earn nothing, and neither do members who have a no-XP role, in text or in voice. Only text channels can be added, so voice channels cannot be excluded.

## Voice XP

Members earn voice XP once a minute while they are in a voice channel. By default they must be unmuted and undeafened, and have at least one other person (not a bot) in the channel. The text cooldown does not apply to voice. Voice XP follows the multipliers and the no-XP rules. A member who was already in voice when the bot started is counted again after they next join a voice channel.

Voice settings can be changed from the dashboard (see below).

## Leaderboards and resets

`!leaderboard` shows the all-time top 10, or the weekly or monthly one. Weekly and monthly XP is always counted. Turn on the automatic resets to clear it on a schedule:

- **Weekly reset.** Mondays at 00:00 UTC.
- **Monthly reset.** The 1st of the month at 00:00 UTC.

Resets only clear the weekly or monthly board. All-time XP and levels are untouched. Both are off by default.

## Limits and defaults

| Setting | Default | Range |
| --- | --- | --- |
| Leveling | Off | On or off |
| XP per message | 15 to 25 | 1 to 500 (dashboard) |
| Message cooldown | 60 seconds | 0 to 3600 seconds (dashboard) |
| Voice XP | On, 10 per minute | 0 to 500 per minute (dashboard) |
| Voice needs unmuted | On | On or off (dashboard) |
| Voice needs others present | On | On or off (dashboard) |
| Role reward mode | `stack` | `stack` or `nonstack` |
| Announce mode | `channel` (no channel set) | `channel`, `dm`, `off` |
| Weekly and monthly reset | Off | On or off |
| Multiplier value | None | Above 0 (commands), above 0 up to 100 (dashboard) |
| Reward level (dashboard) | None | 1 to 1000 |
| Set XP (dashboard) | None | 0 to 1,000,000,000 |

Minimum XP cannot be higher than maximum XP. Leveling has no Premium limits.

## From the dashboard

Open your server, then **Leveling**. Use the switch at the top to enable or disable leveling. The settings form has these groups. XP per message, the cooldown and all voice settings can only be changed here, because there is no command for them.

**Text XP**, **Voice XP**, **Rewards** and **Announcements**

- XP per message (min and max) and the cooldown between XP gains
- Voice XP on or off, XP per minute, require unmuted, require other members present
- Role rewards: stack all earned roles, or keep only the highest
- Weekly and monthly leaderboard reset
- Level-up announcements: in a channel, direct message, or off, and the announcement channel

**Tables**

- **Level role rewards.** Add a reward (level 1 to 1000 and a role) or remove one. Removing does not take the role from members who have it. Integration roles, roles above the bot or above you, and roles with dangerous permissions such as Administrator are refused. Quarantined members receive no rewards.
- **No-XP channels** and **No-XP roles.** Add or remove.
- **XP multipliers.** Add a server-wide, channel or role multiplier (above 0, up to 100), or remove one. The table shows each multiplier's ID.
- **Member XP.** Shows the top members. Set XP or reset a member from the row, or by member ID for anyone else. As with the commands, role rewards are not re-synced.

Still needs commands: the level-up message text (`!leveling message`), and `!rank`, `!leaderboard` for members. See [using the dashboard](/docs/dashboard) for how to sign in.

## Troubleshooting

- **No one earns XP.** Leveling is off by default. Run `!leveling enable`.
- **No level-up messages.** Set a channel with `!leveling channel #channel`, or use `!leveling announce dm`.
- **Role reward not given.** The bot's top role must be above the reward role, and the role must be a normal role. Rewards are given at the member's next level-up.
- **A member gets less XP than expected.** Check `!leveling noxp` and `!leveling multiplier`, and remember the cooldown of one XP gain per 60 seconds by default.
- **`!rank` says leveling is disabled.** Leveling is off in this server.
