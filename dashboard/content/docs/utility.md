---
title: Utility
description: Ping, bot info, member, server, role and channel lookups, avatars and the prefix.
order: 60
group: Utility
---

## What the utility commands do

These commands show information about the bot, your members, roles, channels and your server, and let you view or change the command prefix. There is nothing to set up. Everyone can run them except changing the prefix, which needs Administrator.

Most commands only work inside a server. `!ping`, `!uptime`, `!about`, `!owners` and `!avatar` are the exceptions.

## Quick start

```
!ping
!userinfo @user
!serverinfo
!avatar @user
!prefix
```

## Bot status

| Command | What it does | Needs |
| --- | --- | --- |
| `!ping` | Shows gateway latency, REST API latency and database latency in milliseconds. | Nothing |
| `!uptime` | Shows how long the bot has been running and when it started. | Nothing |
| `!about` | Shows the bot version, developer, server and user counts, memory and CPU use, uptime and latency. It has an **Owners & Devs** button that lists the team privately to you. Aliases: `!credits`, `!botinfo`, `!bi`. | Nothing |
| `!owners` | Lists the bot's owners and developers. Aliases: `!devs`, `!developers`. | Nothing |

## Member, server, role and channel info

| Command | What it does | Needs |
| --- | --- | --- |
| `!userinfo [member]` | Shows ID, nickname, status, badges (server owner, bot, booster), account creation and join dates, top role and up to 10 roles. Defaults to you. Aliases: `!whois`, `!ui`. | Nothing |
| `!serverinfo` | Shows ID, owner, creation date, member counts (humans and bots), channel counts, roles, emojis, boosts and verification level. Aliases: `!si`, `!guildinfo`. | Nothing |
| `!roleinfo <role>` | Shows ID, color, position, creation date, member count, whether it is hoisted, mentionable or managed, and its key permissions. Alias: `!ri`. | Nothing |
| `!channelinfo [channel]` | Shows ID, type, category, position and creation date. Text channels also show topic, NSFW state, slowmode and how many members can see them. Voice channels also show bitrate, user limit and how many people are connected. Defaults to the current channel. Alias: `!ci`. | Nothing |

`!roleinfo` takes the role name, a mention or an ID. Role names can contain spaces. The key permissions it lists are Administrator, Manage Server, Manage Roles, Manage Channels, Manage Messages, Kick Members, Ban Members, Manage Webhooks, Mention Everyone, Manage Nicknames and Moderate Members.

## Avatars and icons

| Command | What it does | Needs |
| --- | --- | --- |
| `!avatar [member]` | Shows a member's avatar in full size. Defaults to you. Aliases: `!av`, `!pfp`. | Nothing |
| `!servericon` | Shows this server's icon. Replies with an error if the server has no icon. Alias: `!icon`. | Nothing |

## Prefix

```
!prefix
!prefix ?
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!prefix` | Shows the current prefix for this server. | Nothing |
| `!prefix <new prefix>` | Changes the prefix for this server. | Administrator |

- The default prefix is `!`.
- A prefix can be up to 5 characters and cannot be empty or only spaces.
- Mentioning the bot always works as a prefix, for example `@Soward help`. Use this if you forget a custom prefix.
- The prefix permission check is strict. Fake permissions from `!fakeperm` do not allow changing the prefix.
- Servers with Premium can also let members run commands with no prefix at all. See [Premium](/docs/premium).

## From the dashboard

You can also change the prefix from your server's settings page. See [Using the dashboard](/docs/dashboard).

## Troubleshooting

- **A command says it only works in a server.** `!userinfo`, `!serverinfo`, `!roleinfo`, `!channelinfo`, `!servericon` and `!prefix` cannot be used in direct messages.
- **I forgot my prefix.** Mention the bot and run `@Soward prefix`.
- **"Prefix must be 5 characters or fewer."** Pick a shorter prefix.
- **`!userinfo` shows a member's status as Offline or Unknown.** Status depends on what Discord shares with the bot, so it can be inaccurate.
