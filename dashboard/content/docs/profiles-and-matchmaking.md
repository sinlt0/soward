---
title: Profiles and Speed Dating
description: Member profile cards and an interest-based speed dating queue with private voice rooms.
order: 55
group: Fun
---

## Profiles

`!profile edit` opens a form for a short bio, interests, what you are looking for, relationship status and pronouns. `!profile [@member]` shows the card with level, birthday and join date. `!profile hide` keeps it private, `!profile show` makes it visible again and `!profile clear` deletes it. Links are removed from profiles.

## Speed dating

Members press **Join queue** on the panel (or use `!match join`). Soward pairs two people who share interests and have not been matched in the last 7 days. They get a **private voice room for two** for a few minutes with buttons to say **Interested**, **Not for me**, add 5 minutes or **Report**. Only if both pressed Interested do they hear about it, by direct message. Reporting ends the date, blocks the pair and sends a report to your staff.

```
!match category #Speed Dates
!match channel #speed-dating
!match role @Verified
!match on
!match panel
```

| Command | What it does |
| --- | --- |
| `!match age <days>` | Minimum account age. Default 7. |
| `!match minutes <3-60>` | Length of a date. Default 10. |
| `!match block @member` / `unblock` | Members choose who they never meet. |
| `!match status` | How many people are waiting. |
| `!match leave` | Leave the queue. |
| `!match off` | Turn speed dating off. |

Members need a visible profile with at least one interest. Reports need the report system set up (`!report channel`).

## Events

`!event create Movie night | tomorrow 8pm | Bring snacks` posts an event with **Going**, **Maybe** and **Can't go** buttons. Times follow the server timezone (`!event timezone Asia/Dhaka`). Soward reminds everyone an hour before and when it starts.

| Command | What it does |
| --- | --- |
| `!event list` / `info <id>` / `who <id>` | See events and who answered. |
| `!event time <id> <when>` | Reschedule. |
| `!event repeat <id> daily\|weekly\|none` | Repeat the event. |
| `!event capacity <id> <number>` | Limit attendees. The rest are waitlisted and move up. |
| `!event voice <id> #channel` | Where it takes place. |
| `!event role <id> @role` | Only this role can RSVP going. |
| `!event duration <id> <minutes>` | How long the event lasts. |
| `!event channel #channel` | Where events are posted. |
| `!event pingrole @role` | Default role pinged for reminders. |
| `!event timezone <zone>` | Timezone used to read times, such as `Asia/Dhaka` or `UTC+6`. |
| `!event cancel <id>` | Cancel and notify. |

Accepted times: `in 3h`, `tomorrow 8pm`, `fri 20:00`, `2026-11-05 19:30`, `5 nov 7pm`, `05/11 18:00` (day first).
