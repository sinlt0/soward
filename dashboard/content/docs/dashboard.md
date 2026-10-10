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
