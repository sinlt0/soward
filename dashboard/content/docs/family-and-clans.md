---
title: Family and clans
description: Marry, adopt and join global clans.
order: 56
group: Fun
---

Family and clans are global: they follow you into every server the bot is in. Everything that involves another person needs their consent.

## Marriage

`!marry <user>` sends a proposal and the other person presses a button to accept. `!divorce [user]` ends a marriage. You can have one marriage by default.

## Adoption

`!adopt <user>` asks someone to become your child. `!disown <user>` removes a child, and `!runaway` lets a child leave. You can adopt up to 5 children by default, and each person can only have one parent.

`!family [user]` shows partners, parent, children and siblings.

## More slots

`!family upgrade` shows the prices. Marriage and adoption slots cost coins, with a maximum for each. See [Coins and Diamonds](/docs/economy) for how to earn them.

## Clans

| Command | What it does |
| --- | --- |
| `!clan create <name>` | Starts a clan (costs coins) |
| `!clan [name]` | Shows a clan |
| `!clan members` | Lists members and ranks |
| `!clan invite <user>` | Invites someone (owner and officers) |
| `!clan join <name>` | Accepts an invite, valid for 24 hours |
| `!clan leave` | Leaves your clan |
| `!clan kick <user>` | Removes a member ranked below you |
| `!clan promote` / `demote <user>` | Sets officers (owner) |
| `!clan transfer <user>` | Gives the clan to another member |
| `!clan deposit <amount>` | Adds coins to the shared bank |
| `!clan upgrade` | Spends bank coins on a new level and more member spots |
| `!clan description <text>` | Sets the description |
| `!clan top` | Shows the top clans |
| `!clan disband` | Deletes the clan (owner) |

## Family tree and size

`!tree [user]` (or `!family tree`) draws the whole family as a picture. It follows every link: partners, their partners, children, and the partners and children of those children, so families merge as people marry or adopt. Partners sit side by side joined by a line, children hang below the parent who adopted them, and you are highlighted in blue.

`!familysize [user]` (or `!family size`) lists everyone in the whole family by generation, including relatives by marriage, with who each person is a child or partner of. It also shows the totals: members, generations, marriages and adoptions.

Very large families show the closest 250 people.

## Families inside clans

Every clan is made of families. A family is a group of connected people through marriages and adoptions, and a clan member's whole family counts, including relatives who are not in the clan.

- `!clan families [name]` lists the families in a clan. The family of the clan owner is the **Main family**, and every other connected family with clan members is a **Branch** named after its first clan member. Members without a family are listed separately.
- `!clan tree [name]` draws every family of the clan in one picture, with a title above each family. Clan members are blue and their relatives outside the clan are black.

Branches form by themselves as members marry or adopt, so there is nothing to set up.
