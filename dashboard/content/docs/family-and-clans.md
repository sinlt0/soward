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
| `!clan invite <user>` | Invites someone (Young Master and Elders) |
| `!clan join <name>` | Accepts an invite, valid for 24 hours |
| `!clan leave` | Leaves your clan |
| `!clan kick <user>` | Removes a member ranked below you |
| `!clan promote` / `demote <user>` | Sets officers (owner) |
| `!clan transfer <user>` | Gives the clan to another member |
| `!clan deposit <amount>` | Builds the clan up by adding coins to the shared bank (also `build`) |
| `!clan upgrade` | Spends bank coins to raise the clan to the next tier |
| `!clan tiers` | Shows every tier and what it gives |
| `!clan stipend` | Collects your daily stipend from the clan bank. The owner can use `on` or `off` |
| `!clan contributions` | Shows who added the most coins |
| `!clan description <text>` | Sets the description |
| `!clan top` | Shows the top clans |
| `!clan disband` | Deletes the clan (owner) |

## Clan tiers

Clans grow through six tiers. Members build the clan up by adding coins with `!clan deposit`, and an owner or officer raises the tier with `!clan upgrade` once the bank has enough coins **and** the clan has enough members.

| Tier | Members | Families | Coins bonus | Daily stipend | To reach it |
| --- | --- | --- | --- | --- | --- |
| Wandering Clan | 10 | 1 | 0% | 0 | Starting tier |
| Rising Clan | 20 | 2 | 3% | 20 | 100,000 coins, 8 members |
| Established Clan | 35 | 3 | 6% | 40 | 300,000 coins, 15 members |
| Great Clan | 50 | 4 | 10% | 70 | 800,000 coins, 25 members |
| Sovereign Clan | 75 | 6 | 15% | 100 | 2,000,000 coins, 40 members |
| Heavenly Clan | 100 | 8 | 20% | 150 | 5,000,000 coins, 60 members |

- **Coins bonus:** every member gets extra coins on top of `!reward`, `!work`, `!gather`, `!hunt`, `!mine` and `!ruins`.
- **Daily stipend:** each member can collect it once every 20 hours with `!clan stipend`. It is paid from the clan bank, so the clan gives back what members put in. The owner can switch it off to save up for the next tier.
- **Member limit:** nobody new can join once the clan is full.
- **Family limit:** a person whose family is not yet in the clan cannot join if the clan already has as many families as its tier allows. Families that grow later, for example through a marriage, are not removed.

## Family tree and size

`!tree [user]` (or `!family tree`) draws the whole family as a picture. It follows every link: partners, their partners, children, and the partners and children of those children, so families merge as people marry or adopt. Partners sit side by side joined by a line, children hang below the parent who adopted them, and you are highlighted in blue.

`!familysize [user]` (or `!family size`) lists everyone in the whole family by generation, including relatives by marriage, with who each person is a child or partner of. It also shows the totals: members, generations, marriages and adoptions.

Very large families show the closest 250 people.

## Families inside clans

Every clan is made of families. A family is a group of connected people through marriages and adoptions, and a clan member's whole family counts, including relatives who are not in the clan.

- `!clan families [name]` lists the families in a clan. The family of the clan owner is the **Main family**, and every other connected family with clan members is a **Branch** named after its first clan member. Members without a family are listed separately.
- `!clan tree [name]` draws every family of the clan in one picture, with a title above each family. Clan members are blue and their relatives outside the clan are black.

Branches form by themselves as members marry or adopt, so there is nothing to set up.

## Named branches

Inside a clan, an Elder or the Young Master can found a named branch with `clan branch create <name>`. Anyone in the clan can join one with `clan branch join <name>` and leave with `clan branch leave`. `clan branch list` shows them all, and the Young Master or a branch's founder can remove one with `clan branch disband <name>`.

A clan can hold as many branches as its tier number, so a tier 1 clan has one and a higher tier allows more. Your status then reads, for example, **Elder of the Ember Court Branch of the fallen Crimson Clan**. Branches are only names and groups. They do not change clan permissions or the family tree shown by `clan families`.
