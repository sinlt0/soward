---
title: Ban Appeals
description: Banned members get a message with an Appeal button that opens a web form. They log in with Discord, answer your questions and staff decide in Discord or the dashboard.
order: 20
group: Moderation
---

## How it works

When Soward bans someone (ban, tempban, massban, a report action or an anti-raid ban), it first sends them a direct message with the reason and an **Appeal this ban** button. The button opens a web page on your dashboard. The member must **log in with Discord** before they can see or send anything, and the bot checks that they are really banned before accepting the appeal.

Appeals land in your appeal channel with **Accept** and **Deny** buttons. Accepting unbans the member, logs a case and sends them a direct message, with a one-use invite if you set a rejoin channel.

## Quick start

```
!appeal channel #appeal-review
!appeal on
```

Appeals need the dashboard to be available on this bot. If the ban message has no Appeal button, the dashboard is not available.

## Settings

| Command | What it does |
| --- | --- |
| `!appeal on` / `off` | Turns appeals on or off. |
| `!appeal channel #channel` | Where appeals are posted for staff. |
| `!appeal role @role` | Role pinged for new appeals. |
| `!appeal votes <number>` | Number of staff votes needed. 1 means the first click decides. |
| `!appeal cooldown <days>` | Days a member must wait after a denial. |
| `!appeal rejoin #channel` | Channel used for the one-use invite sent after an accepted appeal. |
| `!appeal notice <text>` | Extra text shown in the ban message. |
| `!appeal reason on` / `off` | Show or hide the ban reason to the banned member. |
| `!appeal dm on` / `off` | Send the ban message by direct message. |
| `!appeal questions` | Show the questions. Use `!appeal question add <text>`, `!appeal question remove <number>` and `!appeal question reset`. Up to 5 questions. |
| `!appeal list` / `view <id>` / `accept <id>` / `deny <id>` | Handle appeals from commands. |

You can do all of this in the dashboard under **Moderation, Appeals** as well.

## Good to know

- A member can have one open appeal at a time.
- The ban message cannot be delivered if the member blocks direct messages. They can still open the appeal page directly from the link in `!appeal link`.
- Appeals are only possible for members who are banned in your server.
