---
title: Audit Vault
description: Search and export the history of moderation actions and server events.
order: 23
group: Moderation
---

## How it works

Zyro saves every moderation action, security change and logged server event in the **Audit Vault**. It records them whether or not you set up a log channel, so you can look back later and ask "what happened to this member?" or "what did this moderator do last month?".

Free servers keep **7 days** of history. Premium servers keep **365 days** and can export it as a CSV file.

## Quick start

```
!vault
!vault search user:@member
!vault search action:ban days:30
!vault stats days:7
!vault export action:warn
```

## Commands

All commands need Manage Server. Alias for `!vault`: `!auditvault`.

| Command | What it does |
| --- | --- |
| `!vault` | Shows how long history is kept and how many entries are stored. |
| `!vault search [filters]` | Lists matching entries, newest first, 10 per page with Previous and Next buttons. Aliases: `find`, `list`. |
| `!vault stats [filters]` | Counts matching entries by type. Alias: `summary`. |
| `!vault export [filters]` | Sends matching entries as a CSV file, up to 20,000 rows. Premium only. Aliases: `csv`, `download`. |

## Filters

Add any of these after the command. You can combine them.

| Filter | Meaning |
| --- | --- |
| `user:@member` | Entries about this member (a mention or an ID). |
| `by:@staff` | Entries caused by this moderator or staff member. |
| `action:ban` | Entries whose type starts with this word, such as `ban`, `warn`, `kick`, `role_add` or `security`. |
| `days:30` | Only the last 30 days, up to the history limit of your plan. |

## Limits

| Setting | Free | Premium |
| --- | --- | --- |
| History kept | 7 days | 365 days |
| CSV export | No | Yes |

When Premium ends, entries older than 7 days are removed at the next hourly cleanup.

## Troubleshooting

- **"Unknown filter."** Filters look like `name:value` with no spaces, for example `days:30`.
- **No entries match.** History only starts from when the bot began recording, and free servers only see the last 7 days.
- **Export says Premium feature.** Exporting needs an active Premium subscription. See [Premium](/docs/premium).
