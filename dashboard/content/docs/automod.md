---
title: AutoMod
description: Filter banned words, invites and links, and slow down spammers with a heat score.
order: 23
group: Security
---

## How AutoMod works

AutoMod reads every message in your server (ignoring bots) and gives each member a **heat score**. Every message adds a little heat, and rule breaks such as banned words, invites, blocked links, duplicate messages and mass mentions add more. Heat drains away at **1 point per second**, so a regular who chats quickly for a moment is fine, while a spammer builds up heat faster than it drains.

- At **10 heat or more**, the message is deleted and the member is **timed out**.
- At **30 heat or more**, the message is deleted and the member is **quarantined** (roles removed, see [AntiNuke](/docs/antinuke#quarantine)).

AutoMod is **off by default**. Turn it on with `!automod enable`. Heat scores are kept in memory, so they reset when the bot restarts.

Members who are exempt are never scored: anyone with Administrator, the bot's owners, Extra Owners, Trusted Admins and members on the AntiNuke trusted list (`!antinuke trust add @member`).

## Setup

```
!automod enable
!automod banword scam
!automod blockinvites on
!automod blockdomain example.com
```

Run `!automod` on its own to open the overview panel. Use its menu to browse banned words, invite blocking, the link blocklist and panic status.

## What adds heat

| Event | Heat added |
| --- | --- |
| Any message | 2 |
| Banned word in the message | 5 |
| Discord invite link (when invite blocking is on) | 4 |
| Link that breaks your link rules | 2 |
| Duplicate message | 3 |
| Mass mention (5 or more user and role mentions) | 1.5 for each mention |
| Text wall (over 600 characters with no line break in the first 300) | 1 |
| Emoji spam (more than 10 emojis) | 1.5 |

Several can apply to one message and they add up. Members who joined while verification was pending and have not verified yet get **1.5 times** the heat.

How each check works:

- **Banned words** match anywhere inside a message and ignore capitals. A banned word `ass` also matches `class`, so use whole, specific words.
- **Invites** match `discord.gg/...` and `discord.com/invite/...` links, only when `!automod blockinvites on` is set.
- **Links** are only checked if you have added a blocked domain or an allowed domain. A link is flagged if its domain ends with a blocked domain, or, when you have an allowlist, if its domain does not end with any allowed domain.
- **Duplicates** compare a message with the member's previous message. Messages shorter than 10 characters are never counted. Identical messages, or messages with almost the same set of characters, count.

## Punishments

| Heat | What happens |
| --- | --- |
| 10 or more | The message is deleted and the member is timed out for **5 minutes times their multiplier**. The longest possible timeout is 28 days. |
| 30 or more | The message is deleted, the member is quarantined and their multiplier goes up by 1 (to a maximum of 10). |

Every message that leaves a member at 10 heat or more is deleted. The multiplier starts at 1 and applies to the length of later timeouts. It only goes up after a quarantine, and it only goes back to 1 when you run `!automod resetheat`.

When **3 different members** reach 30 heat within **60 seconds**, the whole server enters **panic mode** for 10 minutes. Panic mode is shared with [AntiRaid](/docs/antiraid) and AntiNuke. If AntiRaid is enabled, it starts raid mode.

Each action is sent to the security log channel if you have [logging](/docs/logging) set up.

## Command reference

Commands need Administrator, or the `administrator` fake permission (see [Moderation](/docs/moderation)).

| Command | What it does | Needs |
| --- | --- | --- |
| `!automod` | Opens the overview panel. Alias: `!am`. | Administrator |
| `!automod enable` | Turns AutoMod on. | Administrator |
| `!automod disable` | Turns AutoMod off. | Administrator |
| `!automod banword <word or phrase>` | Adds a word or phrase to the banned list. It is saved in lowercase. | Administrator |
| `!automod unbanword <word or phrase>` | Removes a word or phrase from the banned list. | Administrator |
| `!automod blockinvites <on/off>` | Turns Discord invite blocking on or off. | Administrator |
| `!automod blockdomain <domain>` | Adds a domain to the link blocklist, for example `example.com`. | Administrator |
| `!automod allowdomain <domain>` | Adds a domain to the link allowlist. Once the allowlist has any entry, only links from allowed domains are fine. | Administrator |
| `!automod heat [member]` | Shows a member's heat, mute multiplier and the thresholds. Defaults to you. | Administrator |
| `!automod resetheat <member>` | Clears a member's heat and sets their multiplier back to 1. | Administrator |

There are no commands to remove a blocked or allowed domain. Remove them from the dashboard.

## Settings and defaults

| Setting | Default |
| --- | --- |
| AutoMod | Off |
| Heat drain | 1 per second |
| Timeout threshold | 10 heat |
| Quarantine threshold | 30 heat |
| Base timeout | 5 minutes |
| Longest timeout | 28 days |
| Highest multiplier | 10 |
| Panic mode trigger | 3 members at 30 heat within 60 seconds |
| Panic mode length | 10 minutes |
| Block invites | Off |
| Banned words, blocked domains, allowed domains | Empty |

## From the dashboard

Open **AutoMod** under the Security modules. You need to be the server owner or have Manage Server or Administrator (see [Using the dashboard](/docs/dashboard)).

- **Module settings:** on/off switch, block Discord invites, banned words (one per line), blocked links (one domain per line) and allowed links (one domain per line). Editing the lists lets you remove entries, which commands cannot do for domains.
- **AutoMod heat:** a table of members who currently have heat, with their score and multiplier and a Reset button. You can also check or reset any member by ID.

## Troubleshooting

**AutoMod is not doing anything.** Check it is on with `!automod`. Staff with Administrator are exempt, so test with a normal account.

**Normal chat is getting people timed out.** Every message adds 2 heat and drains 1 per second, so more than one message every 2 seconds builds up. Shorten your banned word list for words that match inside other words, and add trusted members with `!antinuke trust add`.

**A member keeps getting longer timeouts.** Their multiplier went up after a quarantine. Run `!automod resetheat @member`.

**Links are blocked that should be fine.** If you added any allowed domain, every other domain is flagged. Add the domain with `!automod allowdomain`, or remove the allowlist from the dashboard.

**The bot cannot time out a member.** Its role must be above theirs and it needs Moderate Members.
