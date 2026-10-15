---
title: AFK
description: Let people know you are away and see who mentioned you when you return.
order: 61
group: Utility
---

## How AFK works

When you go AFK, Soward tells anyone who mentions you that you are away and shows your message. When you send any message again, you are marked as back, and the bot shows a short summary of who mentioned you while you were gone.

You can go AFK in one server, in several servers, or globally in every server you share with the bot.

## Quick start

```
!afk
!afk 2h Out for lunch
!afk Studying for exams
```

After you run the command, choose a scope with the buttons:

- **Global** puts you AFK in every server you share with the bot.
- **Server** lets you pick specific servers from a list, then press **Go AFK**. If you select none, you go AFK only in the server where you ran the command.

Only the person who ran the command can use those buttons, and they stop working after 2 minutes.

## Commands

| Command | What it does | Needs |
| --- | --- | --- |
| `!afk [duration] [message]` | Sets you as AFK. The duration and message are both optional. Without a message, it is saved as "AFK". | Nothing |
| `!afkcheck [member]` | Shows whether a member is AFK, the scope, their message, how long they have been away, and the time left if they set a duration. Defaults to you. Alias: `!isafk`. | Nothing |

Both commands only work inside a server.

## Duration and message

- Put the duration first. Units are `s` seconds, `m` minutes, `h` hours, `d` days and `w` weeks. You can combine them, for example `1h30m`.
- If you set a duration, you are brought back automatically when it ends. The bot checks once a minute, so it can be up to a minute late.
- The maximum duration is 24 hours. Longer or zero durations are rejected.
- Without a duration, you stay AFK until you send a message.
- Your message can use variables such as `{username}` and `{server}`. They are filled in for you when someone mentions you.

## What happens while you are AFK

- In a server where you are AFK, your nickname gets the prefix `[AFK] `. The result is cut to Discord's 32 character limit. Your old nickname is restored when you return. If the bot cannot change your nickname, for example because you are the server owner or your top role is above the bot's, you are still marked AFK but the nickname stays the same.
- When someone mentions you, the bot replies with your AFK message. That reply disappears after 15 seconds and does not ping you. Mentions of bots and mentions of yourself are ignored.
- The bot saves a short preview (up to 150 characters) of each message that mentioned you.
- Any message you send clears your AFK, global or server.

## When you come back

The bot posts a "Welcome Back" message that deletes itself after 30 seconds. It shows how long you were away and who mentioned you, with the channel and a preview. For global AFK it also shows the server name.

- The bot keeps the 15 most recent mentions.
- The summary lists up to 10 of them and says how many more there are.
- The saved mentions are cleared once you have seen the summary.

## Limits and defaults

| Setting | Value |
| --- | --- |
| Maximum auto-return duration | 24 hours |
| Default message | AFK |
| Nickname prefix | `[AFK] ` |
| Servers in the picker | Up to 25 |
| Mentions kept | 15 |
| Mentions shown on return | 10 |
| AFK notice lifetime | 15 seconds |
| Welcome back lifetime | 30 seconds |

## Troubleshooting

- **"Invalid Duration".** Keep the duration between 1 second and 24 hours.
- **My duration was read as part of the message.** The duration must be the first word, with no spaces inside it. `!afk 2h lunch` works, `!afk lunch 2h` does not.
- **My nickname did not change.** The bot cannot rename the server owner or members whose top role is above the bot's. Move the bot's role higher and make sure it has Manage Nicknames.
- **I am AFK in a server but `!afkcheck` says Globally.** A global AFK takes priority over a server AFK when both exist.
