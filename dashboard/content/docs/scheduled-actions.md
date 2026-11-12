---
title: Scheduled Actions
description: Post messages, lock channels and change roles later or on a repeat. Premium.
order: 65
group: Utility
---

## How it works

Scheduled actions run things at a time you choose, or on a repeat, even when nobody is online. This is a **Premium** feature. A server can hold up to 25 scheduled actions.

You can schedule four kinds of action: posting a message (or a saved embed), locking a channel, unlocking a channel, and giving or removing a role.

## Quick start

```
!schedule say #announcements Game night starts in one hour! | fri 19:00
!schedule say #general {embed:weekly-rules} | monday 9am repeat weekly
!schedule lock #chat tonight 11pm repeat daily
!schedule unlock #chat tomorrow 7am repeat daily
!schedule role add @Event @member fri 20:00
!schedule list
```

## Commands

All commands need Manage Server.

| Command | What it does |
| --- | --- |
| `!schedule` | Shows the commands and how many of the 25 slots are used. |
| `!schedule say <#channel> <message> \| <when>` | Posts a message. Use `{embed:name}` to post a saved [embed template](/docs/embeds). Aliases: `post`, `announce`. |
| `!schedule lock <#channel> <when>` | Stops everyone from sending messages in the channel. |
| `!schedule unlock <#channel> <when>` | Lets everyone send messages again. |
| `!schedule role <add\|remove> <@role> <@member> <when>` | Gives or removes a role. You can only schedule roles below your own highest role. |
| `!schedule list` | Lists everything scheduled. |
| `!schedule info <id>` | Shows one action, how many times it has run and the last problem. |
| `!schedule cancel <id>` | Removes an action. |

## Times and repeats

- Examples: `tomorrow 8pm`, `fri 20:00`, `in 3h`, `2026-11-05 19:30`, `5 nov 7pm`.
- Times use the server timezone. Set it with `!event timezone`.
- Add `repeat daily`, `repeat weekly`, `repeat hourly` or `repeat 6h` at the end to repeat. The smallest repeat is 5 minutes.
- A one-off action is removed after it runs.

## Good to know

- If the bot was offline and the time passed by more than 10 minutes, that run is skipped. A repeating action carries on at its next time.
- If Premium ends, scheduled actions are paused and nothing runs. They are kept, and run again when Premium returns.
- Each run is saved in the [Audit Vault](/docs/audit-vault).
- A run fails safely when a channel, role or member no longer exists, or when Zyro's role is below the role it needs to change. The reason shows in `!schedule info <id>`.

## Limits

| Setting | Value |
| --- | --- |
| Scheduled actions per server | 25 |
| Message length | 1900 characters |
| Smallest repeat | 5 minutes |
