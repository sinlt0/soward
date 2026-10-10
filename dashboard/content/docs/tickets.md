---
title: Tickets
description: Panels, staff roles, forms, transcripts and limits.
order: 3
---

## How tickets work

A **panel** is a message with an Open ticket button. When a member presses it, the bot can ask intake questions, then creates a private channel visible to that member and the panel's staff roles.

## Create a panel

```
!ticket panel create Support
!ticket panel category add Support #tickets-category
!ticket panel staff Support @Moderators
!ticket panel send Support #open-a-ticket
```

Staff roles can be toggled on a panel. Run the staff command again with the same role to remove it.

## Customise a panel

| Command | What it does |
| --- | --- |
| `!ticket panel question add <panel> <text>` | Add an intake question |
| `!ticket panel transcript <panel> <channel>` | Send this panel's transcripts to a channel |
| `!ticket panel unique <panel>` | Allow only one open ticket per member |
| `!ticket panel label <panel> <text>` | Change the button label |
| `!ticket panel text <panel> <text>` | Change the welcome text |
| `!ticket panel subject <panel>` | Ask for a subject when opening |

## Inside a ticket

Staff can use `!ticket claim`, `!ticket unclaim`, `!ticket add`, `!ticket remove`, `!ticket rename`, `!ticket priority` and `!ticket close`. Closing saves an HTML transcript and sends it to the log channel and the member who opened the ticket.

Welcome messages ping the member and the panel's staff roles.

## Server settings

| Command | What it does |
| --- | --- |
| `!ticket log <channel>` | Set the default log channel |
| `!ticket limit <n>` | Set how many tickets a member can have open |
| `!ticket autoclose <hours>` | Close tickets after inactivity |
| `!ticket stats` | View ticket statistics |
| `!ticket list` | List open tickets |

## Limits

| | Free | Premium |
| --- | --- | --- |
| Panels | 3 | 10 |
| Staff roles per panel | 10 | 20 |
| Categories per panel | 5 | 10 |
| Questions per panel | 5 | 10 |
| Open tickets at once | 25 | 250 |
