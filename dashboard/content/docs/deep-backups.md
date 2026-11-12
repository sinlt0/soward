---
title: Deep Backups
description: Full server backups with settings, automatic scheduling and one-command restore. Premium.
order: 25
group: Security
---

## How it works

A **deep backup** saves your whole setup: roles and their permissions, categories and channels and their permission overwrites, plus Zyro's settings, embeds, panels and custom commands. You can take one by hand or let Zyro take one automatically, then restore it with one command if something goes wrong. This is a **Premium** feature.

The free `!backup` command only saves roles and channels. Deep backups also save your bot configuration. See [the Security Center](/docs/security-center) for `!backup`.

Members, messages and bans are not saved. Only the server owner and Extra Owners can use these commands.

## Quick start

```
!deepbackup create before-redesign
!deepbackup auto on 24
!deepbackup list
!deepbackup restore a1b2c3d4
```

## Commands

Aliases for `!deepbackup`: `!dbackup`, `!fullbackup`.

| Command | What it does |
| --- | --- |
| `!deepbackup` | Shows the commands and whether automatic backups are on. |
| `!deepbackup create [label]` | Takes a backup now. Up to 10 manual backups are kept. |
| `!deepbackup list` | Lists your backups. |
| `!deepbackup info <id>` | Shows what a backup holds. |
| `!deepbackup auto <on\|off> [hours]` | Turns automatic backups on or off. The interval is 6 to 168 hours (default 24). The newest 14 automatic backups are kept. |
| `!deepbackup restore <id> [roles\|channels\|settings\|content\|all]` | Restores a backup after you confirm. Default is `all`. |
| `!deepbackup export <id>` | Sends the backup as a JSON file. |
| `!deepbackup delete <id>` | Deletes a backup. |

## Restoring

Restoring asks you to confirm, takes a **safety backup** of the current server first, then:

- Creates roles and channels that were deleted.
- Updates roles and channels that still exist so they match the backup.
- Puts back settings, embeds, panels and custom commands.
- Does **not** delete anything that is not in the backup.

Large servers take a few minutes. If Discord rate limits Zyro, it pauses and tells you to run the restore again. Items that already exist are reused.

## Good to know

- Backups are only created while Premium is active. Existing backups can still be listed, exported and deleted after it ends. Restoring needs Premium.
- Restores and backups cannot run at the same time as a template being applied.
- Each backup is also logged in your security log.
