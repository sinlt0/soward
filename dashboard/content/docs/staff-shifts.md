---
title: Staff Shifts
description: Clock in and out, leave handover notes, and get alerted when nobody is covering the server.
order: 22
group: Moderation
---

## How it works

Staff run `!shift start` when they begin moderating and `!shift end` when they finish. When someone starts, Soward shows what is waiting (open reports, pending appeals, open tickets and pending applications) and the **last handover notes** left by someone else. When they end, Soward posts a **handover** in your handover channel: how long they were on, what they did during the shift (actions, warns, tickets, applications, appeals and reports), what is still open and their notes.

Shifts are for human staff. Soward ends any shift that runs longer than 12 hours by itself and posts the handover as ended automatically.

## Quick start

```
!shift channel #shift-handover
!shift role @On duty
!shift on
```

The on-duty role is optional. It is given on `!shift start` and removed on `!shift end`, so you can use it as the ping role for reports, appeals and tickets (`!report role`, `!appeal role`) and only the people on duty get pinged. Soward's role must be above it.

## Commands

| Command | What it does | Needs |
| --- | --- | --- |
| `!shift start` (aliases `in`, `clockin`) | Clock in and read the last handover | Manage Messages or the shift staff role |
| `!shift note <text>` | Add a note for the next person | On shift |
| `!shift end [notes]` (aliases `out`, `clockout`) | Clock out and post the handover | On shift |
| `!shift status` (aliases `who`, `list`) | Who is on duty and what is waiting | Anyone |
| `!shift handover` | The last three handover notes | Anyone |
| `!shift log [@member]` | Recent finished shifts | Manage Server |
| `!shift hours [days]` | Time on shift per staff member, default 30 days | Manage Server |
| `!shift on` / `off` | Turns shifts on or off | Manage Server |
| `!shift channel #channel` | Where handovers and alerts are posted | Manage Server |
| `!shift role [@role]` | On-duty role, left empty to remove | Manage Server |
| `!shift staffrole [@role]` | Role that can clock in besides members with Manage Messages. It is also pinged for coverage alerts | Manage Server |
| `!shift coverage <start> <end> [minimum]` | Coverage alerts. `off` turns them off | Manage Server |

Aliases: `!shifts`, `!duty`.

## Coverage alerts

`!shift coverage 18 23 1` means that between 18:00 and 23:00 (server timezone, set with `!event timezone`) Soward posts an alert in the handover channel if fewer than 1 staff member is on duty. The alert says what is waiting and pings the shift staff role. Hours can be written `18`, `6pm` or `6:00pm`, and a window that crosses midnight such as `22 4` works. Soward alerts at most once every 2 hours.

## Good to know

- Soward cannot tell whether someone really is at their desk. Shifts are a tool for staff to coordinate, and the hours come only from clock in and clock out.
- The activity counts are the same ones as in `!staff stats` (see [Reports and Trust](/docs/reports)), limited to the time of the shift.
- Notes can be up to 1500 characters per shift. Only the most recent are kept.
- If the bot cannot manage the on-duty role, the shift still starts and ends normally.
