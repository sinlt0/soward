---
title: Reports and Trust
description: Members report messages with context, staff act with one click, and every member gets a trust score.
order: 21
group: Moderation
---

## Reporting a message

Members can **right-click a message, choose Apps, then Report message**, or reply to a message with `!report <reason>`. Soward saves the message and the messages around it, so staff still see what happened if it is deleted. The reported member is never told who reported them.

Reports go to your report channel with buttons: **Warn**, **Timeout 1h**, **Ban**, **Dismiss**, **Delete message** and **Discuss in thread**. When several different members report the same person within 24 hours, the report is marked as repeated and the role is pinged.

## Setup

```
!report channel #reports
!report role @Moderator
!report on
```

| Command | What it does |
| --- | --- |
| `!report alert <number>` | Different reporters in 24 hours before a report is marked repeated. Default 3. |
| `!report limit <number>` | Reports one member can send per day. Default 10. |
| `!report notify on` / `off` | Tell the reporter when staff handled it. |
| `!report list [open\|actioned\|dismissed\|all]` | List reports. |
| `!report view <id>` | Show one report with its context. |
| `!report about @member` | Every report against a member. |

The right-click command appears after the bot restarts once. Discord can take a little while to show it.

## Trust score

`!trust @member` shows a score from 0 to 100 for staff. It grows with account age, time in the server, verification and level, and drops with warnings, timeouts, kicks and reports that staff acted on. Staff can add or remove points with `!trust adjust @member <-50 to 50> <reason>`. `!trust low` lists the lowest scores among the newest members. Staff also see the score in `!userinfo`.

## Staff activity

`!staff stats [@member] [days]` shows what each moderator did: actions, warns, tickets, applications, appeals and reports. `!staff channel #channel` and `!staff weekly on` post a weekly report, and `!staff report` posts it right away. `!staff spike <number>` alerts you when one moderator bans or kicks that many members in an hour.
