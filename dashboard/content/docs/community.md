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
3. Optional: `!confess log #staff-channel` sends a copy to a private channel so staff can moderate. The author is never shown there.

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

## Templates

The Dating v2 template sets up the birthdays channel and birthday role, a read-only confessions channel with the Confess button, and the suggestions channel for you.
