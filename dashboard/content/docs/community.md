---
title: Community
description: Birthdays, anonymous confessions, suggestions and the starboard.
order: 45
group: Community
---

## Birthdays

Members save their birthday and Soward announces it, gives them a birthday role for the day and shows who is next.

| Command | What it does |
| --- | --- |
| `!birthday set <date>` | Saves your birthday, for example `15 March`, `March 15` or `15/03`. Only the day and month are stored, never the year. |
| `!birthday [member]` | Shows a birthday. |
| `!birthday today` | Shows who has a birthday today. |
| `!birthday upcoming` | Shows the next ten birthdays. |
| `!birthday remove` | Deletes your birthday. |
| `!birthday forget <member>` | Staff: removes a member's birthday. |

Setup needs Manage Server:

- `!birthday config channel #channel` sets where birthdays are announced.
- `!birthday config role @role` sets the role members wear on their birthday. It is removed when the day ends.
- `!birthday config message <text>` sets the message. Variables are `{user}`, `{username}` and `{server}`.
- `!birthday config offset <hours>` sets the time zone as a UTC offset, for example `6` or `-5`. Birthdays change at midnight in that zone.
- `!birthday config toggle` turns announcements on or off and `!birthday config reset` clears the settings.

People born on February 29 are celebrated on February 28 in years without a leap day. A member's birthday is deleted when they leave the server.

## Confessions

Members send anonymous messages that are posted by the bot.

1. `!confess channel #confessions` sets where confessions are posted.
2. `!confess panel` posts a **Confess** button. Members press it, write in the form and the bot posts the confession as a numbered message.
3. Every confession gets its own public thread named after its number, so members can reply without touching the channel. `!confess threads on|off` turns this on or off. Soward needs Create Public Threads and Send Messages in Threads in the channel.
4. Optional: `!confess log #staff-channel` sends a copy to a private channel so staff can moderate. The author is never shown there.

Confessions are anonymous to members and to staff. The bot does keep the sender in its database so abuse can be handled without revealing anyone:

- `!confess ban <number>` blocks the sender of that confession from confessing again. Their name is not shown.
- `!confess unban <number>` unblocks them.
- `!confess delete <number>` removes the message.
- `!confess toggle` turns confessions on or off.

Invite links are rejected and there is a one minute cooldown per member. Mentions in confessions never ping anyone.

## Suggestions

Members use `!suggest <idea>`. The bot posts it in the suggestions channel with 👍 and 👎 buttons. Pressing a button again removes the vote.

- `!suggestions channel #channel` sets the channel.
- `!suggestions staffrole @role` lets a role review besides members with Manage Server.
- `!suggestions approve <number> [reason]`, `deny`, `consider` and `implement` update the status, color and reason. The author gets a DM when their suggestion is reviewed.

## Starboard

Messages that get enough reactions are copied to a starboard channel.

- `!starboard channel #channel` sets the channel.
- `!starboard emoji <emoji>` sets the reaction. The default is ⭐.
- `!starboard threshold <number>` sets how many reactions are needed. The default is 3.
- `!starboard toggle` turns it on or off and `!starboard top` shows the most starred messages.

Reactions from the author and from bots do not count. Messages in NSFW channels are never copied. The count is updated live and the post is removed if the reactions drop too low.

## Milestones

Soward can celebrate members without anyone running a command. Set a channel first:

```
!milestones channel #level-up
```

| Feature | What it does |
| --- | --- |
| Anniversaries | Once a day, after 09:00 server time (`!event timezone`), posts everyone who joined on that date in an earlier year, with the number of years. `!milestones anniversary on` or `off` |
| Level milestones | Posts when a member reaches one of your chosen levels, even if level-up messages are off. Default 10, 25, 50, 75 and 100. `!milestones levels 10 25 50` sets them and `!milestones levels off` turns them off |
| Welcome back | When a member sends a message after a long silence, welcomes them with a short digest: new members since they left and events in the next 7 days. `!milestones welcomeback channel`, `dm` or `off` (default off). `!milestones away <days>` sets the silence (7 to 365, default 30) |

All commands need Manage Server. Welcome back only knows about activity from the moment you turn it on, and it updates a member's last-seen time at most every 6 hours, so it is accurate to within a few hours. Join dates come from Discord's last join date, so a member who left and rejoined is counted from the rejoin. Anniversaries and welcome back are not shown for bots.

## Templates

The Dating v2 template sets up the birthdays channel and birthday role, a read-only confessions channel with the Confess button, and the suggestions channel for you.
