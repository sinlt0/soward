---
title: Tickets
description: Support tickets with panels, intake forms, claiming, transcripts and limits.
order: 43
group: Community
---

## How tickets work

A **panel** is a message with an **Open a Ticket** button. When a member presses it, the bot can ask intake questions, then creates a private channel such as `ticket-0001` that only the member, the panel's staff roles and the bot can see. Staff help the member there, then close the ticket. Closing saves an HTML transcript and deletes the channel.

You can have several panels, for example one for support and one for reports, each with its own staff, categories and questions. Panels are found by **name** (not case sensitive) or by their 8-character **panel ID**.

Ticket numbers count up for the whole server and are shown as `#0001`.

## Quick start

```
!ticket panel create Support
!ticket panel staff Support @Moderators
!ticket panel category add Support #tickets
!ticket log #ticket-logs
!ticket panel send Support #open-a-ticket
```

1. Create the panel.
2. Add at least one staff role. A panel with no staff role cannot be posted and members cannot open tickets from it.
3. Optionally add a category so tickets are created under it (see "Categories").
4. Optionally set a log channel for ticket events and transcripts.
5. Post the panel in a channel.

The bot needs **Manage Channels** and **Manage Roles** to create ticket channels.

If a panel name has spaces, put it in quotes whenever more arguments follow it, for example `!ticket panel staff "VIP Support" @Staff`. You can also use the panel ID instead of the name.

## Who can do what

Commands marked **Manage Server** also accept the matching fake permission (see [moderation](/docs/moderation)). Bot owners are always allowed.

- **Staff** means a member with one of the panel's staff roles, or anyone with Administrator, Manage Server or Manage Channels.
- **Ticket owner** is the member who opened the ticket.

## Panel commands

All panel commands need **Manage Server**. `!ticket panel` on its own lists the panels, the same as `!ticket panel list`.

| Command | What it does | Needs |
| --- | --- | --- |
| `!ticket panel create <name>` | Creates a panel. Names are up to 60 characters and must be unique. | Manage Server |
| `!ticket panel list` | Lists panels with their ID, where they are posted and how many staff roles they have, plus your panel limit. | Manage Server |
| `!ticket panel info <name>` | Shows everything about a panel: ID, channel, button, staff roles, categories, questions, subject prompt, one-per-member and transcript channel. | Manage Server |
| `!ticket panel send <name> [#channel]` | Posts the panel in a channel (default is the current one). If it was posted before, the old message is deleted. | Manage Server |
| `!ticket panel delete <name>` | Deletes the panel and its message, after you confirm. Open tickets are not affected. | Manage Server |
| `!ticket panel staff <name> <role>` | Adds a staff role. Run it again with the same role to remove it. Open tickets from this panel are updated straight away. | Manage Server |
| `!ticket panel category <name>` | Shows the panel's categories and how full each is. | Manage Server |
| `!ticket panel category add <name> <category>` | Adds a category where new tickets are created. | Manage Server |
| `!ticket panel category remove <name> <category>` | Removes a category from the panel. | Manage Server |
| `!ticket panel question <name>` | Lists the intake questions. | Manage Server |
| `!ticket panel question add <name> <text>` | Adds an intake question. | Manage Server |
| `!ticket panel question remove <name> <number>` | Removes a question by its number in the list. | Manage Server |
| `!ticket panel label <name> <text>` | Changes the button label (up to 80 characters). | Manage Server |
| `!ticket panel text <name> <text>` | Changes the text on the panel and the welcome message in new tickets (up to 1000 characters). Use `reset` to go back to the default. | Manage Server |
| `!ticket panel subject <name> <on\|off>` | Asks the member for a subject when they open a ticket. | Manage Server |
| `!ticket panel unique <name> <on\|off>` | Allows only one open ticket per member on this panel. | Manage Server |
| `!ticket panel transcript <name> <#channel\|reset>` | Sends this panel's close logs and transcripts to a channel. `reset` uses the server log channel instead. | Manage Server |

Defaults for a new panel: button **Open a Ticket**, subject prompt **on**, one open ticket per member **on**, no questions, no categories. The default panel text is "Click the button below to open a private support ticket." and new tickets say "Describe your issue and a staff member will be with you shortly."

Label and text changes update the posted panel message straight away. Staff role changes affect open tickets from that panel. Other changes apply to tickets opened afterwards.

### Intake form

If a panel has questions, members get a form when they press the button. Each page shows up to 5 questions, and members continue to the next page with a **Continue** button. They have 10 minutes to finish. The answers are shown at the top of the new ticket.

- Question text is cut to 45 characters, because that is what Discord allows on a form label. Answers can be up to 1000 characters and are required.
- When a panel has questions, the subject prompt is skipped. Without questions, and with the subject prompt on, members are asked "What do you need help with?" (up to 500 characters). It is shown in the ticket as the subject.
- With no questions and the subject prompt off, the ticket opens immediately.

### Categories

Add one or more Discord categories to a panel and new tickets are created in the one with the most room. A Discord category holds at most 50 channels, so a full category is skipped. If every category on the panel is full, members see "Every ticket category on this panel is full" and an admin needs to add another. With no categories set, tickets are created at the top of the channel list.

## Inside a ticket

Run these in an open ticket channel. The ticket also has **Claim** and **Close** buttons.

| Command | What it does | Needs |
| --- | --- | --- |
| `!ticket close [reason]` | Closes the ticket, saves the transcript and deletes the channel after 5 seconds. | Ticket owner or staff |
| `!ticket claim` | Marks you as the staff member handling the ticket. Only one person can claim it. | Staff |
| `!ticket unclaim` | Releases a claim. Alias: `!ticket release`. Only the claimer or someone with Manage Server can release it. | Staff |
| `!ticket add <member>` | Gives a member access to the ticket. | Staff |
| `!ticket remove <member>` | Removes a member's access. The ticket owner cannot be removed. | Staff |
| `!ticket rename <name>` | Renames the channel. The name is changed to lowercase letters, numbers, dashes and underscores. | Staff |
| `!ticket priority <level>` | Sets the priority to `low`, `normal`, `high` or `urgent`. New tickets are `normal`. | Staff |
| `!ticket transcript` | Generates an HTML transcript of the ticket so far without closing it. | Staff |
| `!ticket info` | Shows number, owner, claimer, priority, panel, opened time and subject. | Ticket owner or staff |

The **Close** button asks for an optional reason (up to 500 characters). Closing is allowed for the ticket owner and staff.

## Closing and transcripts

When a ticket is closed, by command, button, dashboard or auto-close:

1. The bot builds an HTML transcript of up to 1,500 messages.
2. It posts a "Ticket Closed" summary with the transcript to the panel's transcript channel, or to the server log channel if the panel has none.
3. It sends the same summary and transcript to the member who opened the ticket by direct message, if their DMs are open.
4. It tells the channel it will be deleted in 5 seconds and deletes it.

If there is no transcript channel and no log channel, only the ticket owner receives the transcript. If a ticket channel is deleted by hand, the ticket is marked closed with the reason "Channel deleted" and no transcript is made.

The log channel also receives "Ticket Opened" and "Ticket Claimed" notices. Ticket actions are also sent to your [logging](/docs/logging) setup in the Server Changes category.

## Server settings

| Command | What it does | Needs |
| --- | --- | --- |
| `!ticket log <#channel\|reset>` | Sets the channel for ticket logs and transcripts. `reset` clears it. | Manage Server |
| `!ticket limit <n>` | Sets how many tickets one member can have open at once, from 1 to 25. Default is 3. | Manage Server |
| `!ticket autoclose <hours\|off>` | Closes tickets after this many hours without a message, from 1 to 720. Default is off. | Manage Server |
| `!ticket settings` | Shows your plan, log channel, per-member limit, auto-close, panel count, limits and how many tickets are open. | Manage Server |
| `!ticket list` | Lists open tickets (up to 15) with owner, priority, claimer and age. | Manage Channels or Manage Server |
| `!ticket stats` | Shows total, open, closed and claimed tickets, and the top 5 staff by claimed tickets. | Manage Channels or Manage Server |

`!ticket` on its own shows a short list of the commands. The alias `!tickets` works too.

Auto-close checks every 10 minutes. A ticket counts as inactive when nobody (other than bots) has posted in it for that long. The close is logged as done by the bot, with the reason "Closed automatically after N hour(s) of inactivity".

## What happens when someone presses the button

The bot checks these in order and tells the member privately if one fails:

1. The panel still exists and has a staff role.
2. The member is under the per-member limit (`!ticket limit`).
3. If the panel is set to one open ticket per member, they have no open ticket on it.
4. The server is under its open-ticket limit (see below).
5. The panel has room in at least one of its categories.

## Limits

| | Free | Premium |
| --- | --- | --- |
| Panels per server | 3 | 10 |
| Staff roles per panel | 10 | 20 |
| Categories per panel | 5 | 10 |
| Questions per panel | 5 | 10 |
| Open tickets in the server at once | 25 | 250 |

Other limits: 1 to 25 open tickets per member (default 3), panel names up to 60 characters, 50 channels per Discord category, 1,500 messages per transcript. If you hit a limit, the bot says so and mentions the Premium amount. See [premium](/docs/premium).

## From the dashboard

Open your server, then **Tickets**.

**Settings**

- Log channel
- Open tickets per member (1 to 25)
- Close inactive tickets after (hours, 0 is off, up to 720)

**Panels** (shown as "Panels (used/limit)")

- **Create panel** and **Edit** with one form: name, button label, panel and welcome text, staff roles, ticket categories, intake questions (one per line, 45 characters each), transcript channel, ask for a subject, and one open ticket per member. The form shows the limits for your plan. Saving updates the posted panel and open tickets.
- **Post** or **Repost** to a channel. Reposting deletes the old message. A panel needs a staff role before it can be posted.
- **Delete** removes the panel and its message. Open tickets are not affected.

**Open tickets** (the first 25)

- **Priority** to change the priority.
- **Close** with an optional reason. The default reason is "Closed from the dashboard". The transcript is sent the same way as a normal close.

Still needs commands, in the ticket: claim, unclaim, add or remove members, rename, and transcript. `!ticket stats` and `!ticket settings` are also commands only. See [using the dashboard](/docs/dashboard) for how to sign in.

## Troubleshooting

- **"Panel not ready".** The panel has no staff role. Add one with `!ticket panel staff`.
- **"Could not create ticket".** The bot needs Manage Channels and Manage Roles, or the category is full.
- **Members do not get a transcript by DM.** They have direct messages closed. The transcript still goes to the log channel.
- **"Ticket limit reached".** The member is at the per-member limit. Raise it with `!ticket limit` or ask them to close a ticket.
- **"Server ticket limit reached".** The server has hit its open-ticket limit. Close old tickets, use auto-close, or upgrade to Premium.
- **Staff cannot see a ticket.** Their role is not on that panel. Add it with `!ticket panel staff`. Open tickets are updated right away.
