---
title: Help and support
description: Browse commands, give the Soward team temporary help access, and control the web dashboard.
order: 63
group: Utility
---

## The help command

`!help` opens a menu of every command you can use, sorted by category.

```
!help
!help moderation
!help ban
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!help` | Opens the help menu. Aliases: `!commands`, `!h`. | Nothing |
| `!help <category>` | Opens that category or module directly. | Nothing |
| `!help <command>` | Shows the description, usage, aliases and subcommands of one command. | Nothing |

How the menu works:

- Pick a category from the drop-down. Some categories have modules you can pick from a second drop-down.
- Long lists are split into pages of 8 commands with arrow buttons. **Back** goes up one level.
- Only the person who opened the menu can use it. It stops responding after 2 minutes. Run `!help` again to get a new one.
- If a name matches nothing, you get a "Not found" message.
- Premium, owner and developer tools are not shown to regular members.

## Support access

If you need hands-on help, you can give the Soward team temporary Administrator access to your server.

```
!supportaccess
!supportstatus
!revokesupport
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!supportaccess` | Asks you to confirm, then creates a role called **Soward Support** with Administrator permission and gives it to the bot and to any Soward team members who are in your server. Alias: `!grantsupport`. | Administrator |
| `!supportstatus` | Shows whether the role exists and who has it. | Nothing |
| `!revokesupport` | Deletes the **Soward Support** role and ends the access. | Administrator |

What to know:

- Nothing is granted until you press the confirm button. You can cancel.
- The access does not expire on its own. Run `!revokesupport` when you are done.
- If the role already exists, `!supportaccess` tells you to revoke it first.
- The bot needs the Manage Roles permission, and its role must be high enough to create and assign the role.

## Web dashboard command

`!dashboard` shows the dashboard link and whether the dashboard is on for your server.

```
!dashboard
!dashboard off
!dashboard on
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!dashboard` | Shows the status and the link. Aliases: `!dash`, `!web`. | Nothing |
| `!dashboard on` | Allows the dashboard to manage this server. Alias: `!dashboard enable`. | Manage Server |
| `!dashboard off` | Blocks the dashboard from changing this server until you turn it back on. Alias: `!dashboard disable`. | Manage Server |

The status can be:

- **On for this server** or **Off for this server**, which you control with `on` and `off`.
- **Off for every server**, which the bot owner controls.
- **Disabled**, which means the web server is not running for this bot.

Turning the dashboard on or off from Discord is recorded in the dashboard's audit log. Members still need Manage Server to sign in and change settings. See [Using the dashboard](/docs/dashboard).

## Troubleshooting

- **The dashboard says it is off.** Run `!dashboard` to see why. If it is off for your server, run `!dashboard on`.
- **No dashboard link is shown.** The bot's owner has not set the dashboard address.
- **`!supportaccess` fails to create the role.** Check the bot's Manage Roles permission and that your server has room for another role.
- **A command is missing from `!help`.** Some commands are hidden from regular members, or you are looking in the wrong category. Try `!help <command name>`.
