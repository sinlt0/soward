---
title: AutoRole
description: Give roles automatically when humans or bots join, or after they verify.
order: 12
group: Moderation
---

## How AutoRole works

AutoRole gives roles to new arrivals without any manual work. There are three lists:

- **Human join roles** are given to people who join.
- **Bot join roles** are given to bots that join.
- **Verify roles** are given when a member passes [verification](/docs/verification).

If verification is turned on for your server, humans do not get their join roles when they arrive. They receive the join roles and the verify roles together once they pass verification. Bots are never held back.

The bot can only give roles that sit below its own top role in Server Settings, then Roles.

## Set it up

```
!autorole add human @Member
!autorole add bot @Bots
!autorole verifyrole @Verified
```

You can add more than one role to each list. To give existing members the roles too, run a sync:

```
!autorole sync human
```

## Command reference

`!arole` works as a short name for `!autorole`. All commands need Manage Roles.

| Command | What it does | Needs |
| --- | --- | --- |
| `!autorole` | Shows the three role lists with a menu to switch between them. | Manage Roles |
| `!autorole add <human\|bot> <role>` | Adds a join role. | Manage Roles |
| `!autorole remove <human\|bot> <role>` | Removes a join role. | Manage Roles |
| `!autorole clear <human\|bot>` | Removes every join role in that list. | Manage Roles |
| `!autorole sync [human\|bot\|all]` | Gives the configured join roles to existing members who do not have them, after you confirm. Default is `all`. | Manage Roles, bot needs Manage Roles |
| `!autorole verifyrole <role>` | Adds a role that is given after verification. | Manage Roles |
| `!autorole removeverifyrole <role>` | Removes a verify role. | Manage Roles |

## Delay

Join roles can be delayed by a number of seconds after someone joins, up to one hour. This delay is part of the join greeting settings, see the Greetings page of the dashboard. If no delay is set, roles are given right away.

## Limits and notes

- Adding a role that is already in a list, or removing one that is not, gives an error and changes nothing.
- `!autorole sync` can be slow on large servers. Members the bot cannot update because of role hierarchy are counted as failed in the result.
- Each time join roles are applied, an entry is sent to the `member` log category (event `autorole_action`) if logging is set up.
- The Verified role from `!verification role` is separate from verify roles here. Both are given after verification.

## From the dashboard

The AutoRole page on the web dashboard has three role pickers: roles for new members, roles for new bots, and roles after verifying. Changes apply the same way as the commands. Syncing existing members is a command only.

## Troubleshooting

- **A new member got no role**: check whether verification is on. If so they receive roles only after verifying. Also check the delay setting.
- **A role is never applied**: the role is probably above the bot's top role, or was deleted.
- **Bots do not get roles**: bots need to be added with `!autorole add bot`, separate from the human list.
