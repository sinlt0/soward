---
title: Bot identity
description: Give Soward its own nickname, avatar, banner and bio in your server.
order: 62
group: Utility
---

## What this does

Bot identity lets you change how Soward looks in your server only: its nickname, avatar, banner and About Me. Other servers are not affected.

This feature needs **Soward Premium** on the server. See [Premium](/docs/premium).

## Quick start

```
!nbot name Guardian
!nbot bio Keeping the server safe.
!nbot avatar https://example.com/avatar.png
!nbot banner https://example.com/banner.png
!nbot
!nbot reset
```

For an image you can attach the file to your message instead of giving a link.

## Commands

The main command is `!nbot`. Its alias is `!nexus`.

| Command | What it does | Needs |
| --- | --- | --- |
| `!nbot` | Shows the current identity: nickname, bio, whether a server avatar and banner are set. | Premium |
| `!nbot name <name>` | Changes the bot's nickname in this server. Maximum 32 characters. | Premium, Manage Server |
| `!nbot bio <text>` | Changes the bot's server-specific About Me. Maximum 190 characters. | Premium, Manage Server |
| `!nbot avatar [image URL]` | Changes the bot's avatar in this server. Use a link or attach an image. | Premium, Manage Server |
| `!nbot banner [image URL]` | Changes the bot's profile banner in this server. Use a link or attach an image. | Premium, Manage Server |
| `!nbot reset` | Clears the nickname, avatar, banner and bio one by one and goes back to the defaults. If one part fails, the rest are still reset and the failed part is listed. | Premium, Manage Server |

Administrators and the bot's owners can use every command. Fake permissions granted for Manage Server also work.

## Images

- Attach an image, or give a link that loads within 10 seconds. If both are given, the attachment is used.
- Images must be under 8 MB.
- The file must really be a PNG, JPEG, GIF or WebP image. Links that point to private or internal addresses are refused.
- If Discord rejects a change, the bot shows what Discord said. Try a smaller file or a common format such as PNG or JPG.
- Banners may need your server to have enough boosts, depending on Discord's rules.

## Limits and defaults

| Setting | Value |
| --- | --- |
| Nickname length | 32 characters |
| Bio length | 190 characters |
| Image size | 8 MB |
| Needs Premium | Yes, for every command |

## Troubleshooting

- **"This feature requires Soward Premium."** Your server does not have active Premium.
- **"Failed to update nickname."** The bot needs the **Change Nickname** permission.
- **"Provide an image URL or attach an image under 8MB."** The link did not load, or the file was too large.
- **The banner fails.** Discord may require a higher boost level for it.
