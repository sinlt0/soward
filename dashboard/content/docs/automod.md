---
title: AutoMod
description: Filter banned words, invites, scam links and spam with a heat score, a warning ladder and Discord's own AutoMod.
order: 23
group: Security
---

## How AutoMod works

AutoMod reads every message in your server (ignoring bots) and gives each member a **heat score**. Every message adds a little heat, and rule breaks such as banned words, invites, scam links, duplicate messages and mass mentions add more. Heat drains away at **1 point per second**, so a regular who chats quickly for a moment is fine, while a spammer builds up heat faster than it drains.

- A message that breaks a rule is **deleted** and the member is told why (a short notice that removes itself after 6 seconds).
- At **10 heat or more**, the message is deleted and the member gets the **first strike action**, a **5 minute timeout** by default.
- At **30 heat or more**, the member gets the **severe action**, **quarantine** by default (roles removed, see [AntiNuke](/docs/antinuke#quarantine)).

AutoMod is **off by default**. Turn it on with `!automod enable`, or apply a preset such as `!security preset balanced`. Heat scores are kept in memory, so they reset when the bot restarts.

Never scored: members with Administrator, the server owner, Extra Owners, Trusted Admins, AntiNuke trusted members, members and channels on the [whitelist](/docs/security-center) for AutoMod (a whitelist can also skip only some checks), and the channels and roles you exempt with `!automod exempt`.

## What adds heat

Every weight can be changed (`!automod set weight_<name> <number>`). Defaults:

| Event | Heat |
| --- | --- |
| Any message | 2 |
| Mass mention (at `mention_limit`, 5 or more) | 1.5 for each mention |
| `@everyone` or `@here` ping | 4 |
| Banned word | 5 |
| Discord invite (when invite blocking is on) | 4 |
| Blocked or non-allowed link | 2 |
| Phishing link | 12 |
| IP logger link | 12 |
| Duplicate message | 3 |
| Zalgo (glitch) text | 3 |
| Attachment spam (6 or more files) | 2 |
| Emoji spam (more than 10) | 1.5 |
| Excessive capitals (70% of 15+ letters) | 1.5 |
| Text wall (over 600 characters) | 1 |

Several can apply to one message and they add up. The total is then multiplied by:

- **1.5** for members who joined while [verification](/docs/verification) is pending and have not verified yet (`unverified_heat_factor`).
- **1.5** while raid mode, panic mode or Beast Mode is active (`raid_heat_factor`).

How each check works:

- **Banned words** ignore capitals, look-alike characters and spacing tricks. A banned word `ass` also matches inside `class` unless you turn on the `wholeword` filter. Prefer whole, specific words.
- **Invites** match `discord.gg/...`, `discord.com/invite/...` and common invite look-alikes, only when `!automod blockinvites on` is set.
- **Blocked and allowed links.** A link is flagged if its domain ends with a blocked domain, or, when you have an allowlist, if its domain does not end with any allowed domain. Subdomains count.
- **Scam links** are checked against a built-in list of phishing and IP logger domains (filter `scamlinks`, on by default).
- **Duplicates** compare a message with the member's recent messages inside `duplicate_window` (30 seconds). Messages shorter than 10 characters never count.

Messages that only trip the **caps**, **wall** or **emoji** checks add heat but are not deleted on their own.

## Punishments

| Heat | What happens |
| --- | --- |
| `mute_threshold` (10) | The message is deleted and the member gets `mute_action`: `timeout` (default), `kick`, `ban`, `quarantine` or `none`. A timeout lasts `base_mute` (5 minutes) times their multiplier, up to 28 days. |
| `panic_threshold` (30) | The member gets `panic_action`: `quarantine` by default. |

After either punishment the member's **multiplier** goes up by 1 (to `max_multiplier`, 10) and their heat is reset to 0 (`reset_heat_on_punish`). The multiplier goes back to 1 after `multiplier_reset` (1 hour) without a new punishment, or when you run `!automod resetheat`. `purge_on_punish` also removes the member's last minute of messages.

When **3 different members** reach the severe threshold within **60 seconds**, the whole server enters **panic mode** for 10 minutes. Panic mode is shared with [AntiRaid](/docs/antiraid) and AntiNuke, and if AntiRaid is enabled it starts raid mode. Punishments also add to the [threat score](/docs/security-center).

Each action is sent to the security log channel if you have [logging](/docs/logging) set up.

## Warning ladder

Turn on `warn_ladder_enabled` to escalate members who collect [warnings](/docs/moderation). Only warnings newer than `warn_window` (30 days) count.

| Setting | Default | Meaning |
| --- | --- | --- |
| `warn_timeout_at` | 3 | Timeout (`warn_timeout_duration`, 1 hour) when the member reaches this many warnings |
| `warn_kick_at` | 5 | Kick at this many |
| `warn_ban_at` | 7 | Ban at this many |
| `warn_on_punish` | Off | Each AutoMod punishment also adds a warning, so the ladder applies to AutoMod too |

Set a step to `0` to skip it. The ladder never acts on the server owner or on members whose top role is at or above the bot's. A step happens when the member's active warning count **equals** the number, so a member who is already past a step is not punished again for it.

You can manage the ladder with commands instead of settings:

| Command | What it does | Needs |
| --- | --- | --- |
| `!ladder` | Shows the steps and whether the ladder is on | Manage Messages |
| `!ladder on` / `off` | Turns the ladder on or off | Trusted Admin |
| `!ladder timeout <warns> [duration]` | Timeout step and its length, such as `!ladder timeout 3 1h` | Trusted Admin |
| `!ladder kick <warns>` / `ban <warns>` | Kick and ban steps (`0` turns a step off) | Trusted Admin |
| `!ladder window <duration>` | How long a warning counts, such as `30d` | Trusted Admin |
| `!ladder check @member` | Active warnings, the next step, how many warnings away it is and when the oldest warning stops counting | Manage Messages |

Aliases: `!warnladder`, `!warnsteps`.

## Webhook and mass-mention protection

- `webhook_protection` deletes messages posted by webhooks that ping everyone or here, carry an invite or mass-mention. `webhook_delete` also deletes the webhook (needs Manage Webhooks).
- `burst_lockdown` starts a [server lockdown](/docs/security-center) when `burst_count` (5) mass-mention messages arrive within `burst_window` (30 seconds). It uses your `mention_limit` and counts `@everyone` pings.

## Discord's built-in AutoMod

`!automod native sync` creates AutoMod rules inside Discord from your banned words, mention limit and spam setting. They keep working when the bot is offline and show in Server Settings. `!automod native status` lists them and `!automod native off` removes them. Re-run `sync` after you change the banned words. The bot only touches rules whose name starts with "Soward ·". Discord limits how many rules and keywords a server can have, and `sync` reports anything it could not create. Your exempt roles (up to 20) and channels (up to 50) are copied across.

## Setup

```
!automod enable
!automod banword scam
!automod blockinvites on
!automod blockdomain example.com
!automod native sync
```

Run `!automod` on its own to open the overview panel. Run `!automod settings` to see every setting.

## Commands

| Command | What it does | Needs |
| --- | --- | --- |
| `!automod` (alias `!am`) | Opens the overview panel | Administrator |
| `!automod settings [group]`, `get <key>`, `list <key>` | View settings | Administrator |
| `!automod heat [member]` | A member's heat, multiplier and the thresholds | Administrator |
| `!automod set <key> <value>` | Changes any setting | Trusted Admin |
| `!automod add / remove <key> <value>` | Edits a list setting | Trusted Admin |
| `!automod enable` | Turns AutoMod on | Trusted Admin |
| `!automod banword / unbanword <word>` | Edits the banned words (saved in lowercase, 2 to 100 characters) | Trusted Admin |
| `!automod blockinvites <on/off>` | Invite blocking | Trusted Admin |
| `!automod blockdomain / unblockdomain <domain>` | Link blocklist | Trusted Admin |
| `!automod allowdomain / unallowdomain <domain>` | Link allowlist | Trusted Admin |
| `!automod filter <name> <on/off>` | Toggles `scamlinks`, `caps`, `zalgo`, `duplicates`, `emoji`, `attachments` or `wholeword` | Trusted Admin |
| `!automod mentions <2-50>` | Mention limit | Trusted Admin |
| `!automod exempt <add/remove/list> [channel or role]` | Exempt channels, categories and roles | Trusted Admin |
| `!automod resetheat <member>` | Clears heat and sets the multiplier back to 1 | Trusted Admin |
| `!automod native [sync/status/off]` | Discord's built-in AutoMod rules | Trusted Admin |
| `!automod reset <key or all>` | Restores defaults | Extra Owner |
| `!automod disable` | Turns AutoMod off | Extra Owner |

While the tier lock is on (the default), plain Administrators can only view. See [Security Center](/docs/security-center).

## From the dashboard

Open **AutoMod** under Security. You can switch it on or off, set invite blocking and edit the banned words, blocked links and allowed links (one per line). A table shows members who currently have heat with a Reset button. Everything else in this page is a command.

## Troubleshooting

**AutoMod is not doing anything.** Check it is on with `!automod`. Administrators and trusted members are exempt, so test with a normal account.

**Normal chat is getting people punished.** Every message adds 2 heat and drains 1 per second, so more than one message every 2 seconds builds up. Raise `mute_threshold`, lower `weight_message`, or exempt busy channels. Shorten banned words that match inside other words or turn on `wholeword`.

**A member keeps getting longer timeouts.** Their multiplier went up after earlier punishments. Run `!automod resetheat @member`.

**Links are blocked that should be fine.** If you added any allowed domain, every other domain is flagged. Add the domain with `!automod allowdomain`, or remove the allowlist.

**The bot cannot punish a member.** Its role must be above theirs and it needs the permission for the action (Moderate Members, Kick Members, Ban Members or Manage Roles).

**`native sync` fails.** The bot needs Manage Server, and Discord caps how many AutoMod rules a server can have.

## Settings reference

Every automod setting, taken from the bot's settings list. Change one with `!automod set <key> <value>`, look at one with `!automod get <key>` and put one back with `!automod reset <key>`.

### General

| Setting | Default | Allowed | What it does |
| --- | --- | --- | --- |
| `enabled` | Off | On or Off | Master switch for AutoMod. |

### Filters

| Setting | Default | Allowed | What it does |
| --- | --- | --- | --- |
| `block_invites` | Off | On or Off | Block invite links |
| `mention_limit` | 5 | 2 to 50 | Mention limit |
| `attachment_limit` | 6 | 2 to 20 | Attachment limit |
| `emoji_limit` | 10 | 3 to 100 | Emoji limit |
| `caps_min_length` | 15 | 5 to 200 | Caps minimum length |
| `caps_ratio` | 0.7 | 0.3 to 1 | Caps ratio |
| `wall_length` | 600 | 200 to 4000 | Text wall length |
| `duplicate_window` | 30s | 5s to 10m 0s | Duplicate window |
| `duplicate_similarity` | 0.9 | 0.5 to 1 | Duplicate similarity |
| `filter_scamlinks` | On | On or Off | Filter: scamlinks |
| `filter_caps` | On | On or Off | Filter: caps |
| `filter_zalgo` | On | On or Off | Filter: zalgo |
| `filter_duplicates` | On | On or Off | Filter: duplicates |
| `filter_emoji` | On | On or Off | Filter: emoji |
| `filter_attachments` | On | On or Off | Filter: attachments |
| `filter_wholeword` | Off | On or Off | Filter: wholeword |

### Lists

| Setting | Default | Allowed | What it does |
| --- | --- | --- | --- |
| `banned_words` | Empty | list, up to 200 (500 with Premium) | Banned words |
| `link_blocklist` | Empty | list, up to 200 (500 with Premium) | Blocked domains |
| `link_allowlist` | Empty | list, up to 200 (500 with Premium) | Once set, only these domains are permitted. |
| `exempt_channels` | Empty | list, up to 50 (150 with Premium) | Exempt channels |
| `exempt_roles` | Empty | list, up to 50 (150 with Premium) | Exempt roles |

### Heat

| Setting | Default | Allowed | What it does |
| --- | --- | --- | --- |
| `mute_threshold` | 10.0 | 3 to 200 | Heat that triggers a punishment |
| `panic_threshold` | 30.0 | 5 to 500 | Heat that triggers the severe action |
| `decay` | 1.0 | 0.1 to 20 | Heat lost per second |
| `mute_action` | `timeout` | `timeout`, `kick`, `ban`, `quarantine`, `none` | First strike action |
| `panic_action` | `quarantine` | `timeout`, `kick`, `ban`, `quarantine`, `none` | Severe action |
| `base_mute` | 5m 0s | 10s to 28d 0h | Base timeout length |
| `max_multiplier` | 10 | 1 to 50 | Maximum timeout multiplier |
| `multiplier_reset` | 1h 0m | 1m 0s to 7d 0h | Multiplier reset time |
| `reset_heat_on_punish` | On | On or Off | Reset heat after a punishment |
| `raid_heat_factor` | 1.5 | 1 to 5 | Heat factor during raid mode |
| `unverified_heat_factor` | 1.5 | 1 to 5 | Heat factor for unverified members |

### Warnings

| Setting | Default | Allowed | What it does |
| --- | --- | --- | --- |
| `warn_ladder_enabled` | Off | On or Off | Escalate members who collect warnings: timeout, then kick, then ban. |
| `warn_window` | 30d 0h | 1h 0m to 365d 0h | Older warnings stop counting toward the ladder. |
| `warn_timeout_at` | 3 | 0 to 50 | 0 turns this step off. |
| `warn_timeout_duration` | 1h 0m | 1m 0s to 28d 0h | Ladder timeout length |
| `warn_kick_at` | 5 | 0 to 50 | 0 turns this step off. |
| `warn_ban_at` | 7 | 0 to 50 | 0 turns this step off. |
| `warn_on_punish` | Off | On or Off | AutoMod punishments add a warning |

### Webhooks

| Setting | Default | Allowed | What it does |
| --- | --- | --- | --- |
| `webhook_protection` | Off | On or Off | Delete webhook posts that ping everyone, carry invites or mass-mention. |
| `webhook_delete` | Off | On or Off | Also delete the webhook itself. Needs Manage Webhooks. |
| `burst_lockdown` | Off | On or Off | Lock the server when many mass-mention messages land at once. |
| `burst_count` | 5 | 2 to 50 | Mass-mention messages |
| `burst_window` | 30s | 5s to 10m 0s | Burst window |

### Responses

| Setting | Default | Allowed | What it does |
| --- | --- | --- | --- |
| `delete_flagged` | On | On or Off | Delete flagged messages |
| `notify` | On | On or Off | Tell the member why |
| `notify_delete_after` | 6s | 2s to 2m 0s | Notice lifetime |
| `purge_on_punish` | On | On or Off | Remove the member's recent messages |

### Heat weights

| Setting | Default | Allowed | What it does |
| --- | --- | --- | --- |
| `weight_message` | 2.0 | 0 to 100 | Heat: message |
| `weight_mention` | 1.5 | 0 to 100 | Heat: mention |
| `weight_link` | 2.0 | 0 to 100 | Heat: link |
| `weight_invite` | 4.0 | 0 to 100 | Heat: invite |
| `weight_banned_word` | 5.0 | 0 to 100 | Heat: banned word |
| `weight_duplicate_message` | 3.0 | 0 to 100 | Heat: duplicate message |
| `weight_everyone` | 4.0 | 0 to 100 | Heat: everyone |
| `weight_phishing` | 12.0 | 0 to 100 | Heat: phishing |
| `weight_iplogger` | 12.0 | 0 to 100 | Heat: iplogger |
| `weight_caps` | 1.5 | 0 to 100 | Heat: caps |
| `weight_zalgo` | 3.0 | 0 to 100 | Heat: zalgo |
| `weight_attachments` | 2.0 | 0 to 100 | Heat: attachments |
| `weight_emoji` | 1.5 | 0 to 100 | Heat: emoji |
| `weight_wall` | 1.0 | 0 to 100 | Heat: wall |
