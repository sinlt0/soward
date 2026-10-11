---
title: Using the dashboard
description: Sign in, pick a server, and manage modules from the web.
order: 2
---

## Sign in

Open the dashboard and choose **Sign in with Discord**. The site asks only for your identity and the list of servers you are in. It never sees your password.

You can manage a server if you are its owner or have **Manage Server** or **Administrator** there, and the bot is in that server.

## Server page

Each server has a page with three parts:

1. **Server settings** for the prefix, no-prefix mode (Premium) and dashboard access.
2. **Module search** to find a module by name or description, with category chips to narrow the list.
3. **Module grid** with an on/off switch and a **Configure** button for each module.

## Module pages

Configure opens a form for that module. Make your changes and a bar appears at the bottom. Press **Save changes** to apply them or **Discard** to go back. Changes take effect immediately in Discord.

Every change is recorded in the **Audit log** on the server page.

## Create, edit and delete

Many modules show tables with buttons instead of only switches. Use them to do from the web what you would do with commands:

| Module | What you can manage |
| --- | --- |
| Tickets | Create, edit, post and delete panels, change ticket priority, close tickets |
| Leveling | Level rewards, no-XP channels and roles, XP multipliers, set or reset member XP |
| Giveaways | Start, edit, end, cancel and reroll |
| Reaction roles | Create, edit, post and delete panels, add or remove bindings |
| Custom commands | Create, edit, enable or disable, delete |
| Alerts | Add, edit and remove |
| Embeds | Create, edit, copy, rename, send and delete reusable embeds |
| Greetings | Pick a saved embed for the welcome, leave, boost and ban messages |
| Music | Start and stop 24/7 lofi radio, switch stations, 24/7 voice mode, add or remove custom stations |
| Moderation | Warn, mute, unmute, kick, ban, unban, delete warnings, browse cases |
| Security | NSFW, logging, anti-nuke, anti-raid, automod and verification settings |

Each button opens a form. Mistakes such as a missing channel or a role above the bot show as a message in the form so you can fix them and try again. Role hierarchy rules are the same as in Discord, so you cannot act on someone with an equal or higher role.

Some things still need commands, such as purge, lockdown, slowmode, playing songs and extra custom command options.

## Turn the dashboard on or off from Discord

Server managers can control web access from chat:

| Command | What it does |
| --- | --- |
| `!dashboard` | Shows whether web access is on for this server |
| `!dashboard on` | Allows the dashboard to manage this server |
| `!dashboard off` | Blocks the dashboard for this server |
| `!dashboard global on` / `off` | Bot owners only. Switches the dashboard on or off everywhere |

Turning it off does not change any settings. Commands keep working either way.

## Troubleshooting

- **No servers listed.** You need Manage Server in that server.
- **Server shows Add instead of Manage.** The bot is not in that server yet.
- **Dashboard is off.** Run `!dashboard on` in the server, or ask the bot team if it was turned off globally.
