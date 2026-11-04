---
title: Reminders and To-do
description: Personal reminders that follow you to every server, repeating reminders, and a simple to-do list.
order: 56
group: Utility
---

## Reminders

`!remind <time> <message>` sends you a reminder at the right moment. It arrives in your DMs, or in the channel you set it in if your DMs are closed.

Examples:

- `!remind 2h call mum`
- `!remind in 1h30m stretch`
- `!remind tomorrow 8pm exam`
- `!remind friday 5:30pm | pay rent` (the `|` marks where the message starts)

Reminders must be at least 30 seconds away and up to two years ahead. You can keep up to 25 at a time.

### Repeating reminders

`!remind every 1d drink water` repeats the reminder. The shortest interval is one hour.

### Managing reminders

- `!remind list` shows your reminders with their IDs.
- `!remind delete <id>` removes one.
- `!remind clear` removes all of them.

### Your timezone

Clock times such as `8pm` use your own timezone. Set it with `!remind tz Asia/Dhaka` or an offset like `!remind tz UTC+6`. Without one, the bot uses UTC.

Reminders belong to you, not to a server, so they work everywhere the bot is.

## To-do list

`!todo` shows your personal list.

- `!todo add <text>` adds an item.
- `!todo done <number>` and `!todo undo <number>` tick and untick it.
- `!todo edit <number> <text>` changes it.
- `!todo remove <number>` deletes it.
- `!todo clear` removes everything you have finished.

You can keep up to 50 items. The list is private to you and global.
