---
title: Security Center
description: Access tiers, the global whitelist, presets, every security setting, server lockdown, backups and the security check.
order: 19
group: Security
---

## What the Security Center is

The Security Center is the layer that sits over [AntiNuke](/docs/antinuke), [AntiRaid](/docs/antiraid), [AutoMod](/docs/automod) and [Verification](/docs/verification). It decides **who may change security settings**, **who is exempt from which system**, and gives every module the same set of customization commands, plus server lockdown, backups, a threat score and a security check.

Run `!security` for an overview of your protections and your own access level. `!sec` works too.

## Access tiers

| Tier | Who | Can do |
|---|---|---|
| Owner | Server owner, Extra Owners | Everything, including turning modules off, the whitelist, tiers, resets, presets, import, export and restoring backups |
| Trusted Admin | People the owner or an Extra Owner promotes | Change every normal security setting and run lockdown and backups |
| Administrator | Members with the Administrator permission | View settings and logs only, while the tier lock is on |

Only the server owner can add an Extra Owner. The owner or an Extra Owner adds Trusted Admins.

```
!extraowner add @member
!trustedadmin add @member
```

The **tier lock** is on by default. Turn it off with `!security lock off` if you want every Administrator to count as a Trusted Admin. Owner-only actions stay owner-only.

## Whitelist

The whitelist exempts a member, a role or a channel. Each entry has one or more **scopes**, so someone can skip link filtering without skipping AntiNuke.

```
!whitelist add @Helper automod
!whitelist add @Partners links invites
!whitelist add #bot-commands spam mentions
!whitelist remove @Helper automod
!whitelist list
!whitelist scopes
```

| Scope | Exempts from |
|---|---|
| `all` | Every security system |
| `antinuke` | AntiNuke limits and the quarantine hold |
| `antiraid` | The join gate and raid actions |
| `automod` | Every AutoMod filter |
| `spam` | Spam, duplicate and wall-of-text filters |
| `mentions` | Mention limits |
| `invites` | Invite blocking |
| `links` | Link and scam filters |
| `words` | Banned words |
| `quarantine` | Quarantine hold checks |

Leaving the scope out means `all`. Removing without a scope removes every scope for that target. Adding, removing and clearing are owner-level. A server holds up to 500 entries.

Administrators are exempt from AutoMod filters. For AntiNuke they are **not** exempt unless you turn on `!antinuke adminbypass on`, because a stolen administrator account is the most common way servers are nuked.

## Customizing everything

Every security module exposes the same commands. Over 220 settings in total.

| Command | What it does |
|---|---|
| `!antinuke settings [group]` | List settings and current values. Also `antiraid`, `automod`, `verification`, `security` |
| `!antinuke get <key>` | Show one setting with its default and allowed values |
| `!antinuke set <key> <value>` | Change a setting |
| `!antinuke reset <key>` | Return a setting to its default. `reset all` resets the module (owner) |
| `!antinuke add <key> <value>` | Add to a list setting such as banned words or exempt roles |
| `!antinuke remove <key> <value>` | Remove from a list |
| `!security set <module> <key> <value>` | The same, from one place |

Values accept `on`/`off`, numbers, durations such as `30s`, `15m`, `2h`, `7d`, roles, channels and named choices. Wrong values are refused with the allowed range.

Settings marked **critical** (turning a module on or off, administrator bypass, the tier lock) need an owner.

### Per-action limits

AntiNuke has a short-window limit and an hourly limit for every monitored action.

```
!antinuke threshold ban 3
!antinuke hourly ban 10
!antinuke window 20
!antinuke limits
```

An hourly limit of `0` turns the hourly check off.

### Join gate

AntiRaid filters (account age, no avatar, advertising names, blocked name patterns, suspicious score) each have their own on/off switch and their own action: `timeout`, `kick`, `ban` or `quarantine`. Use `default` to follow the general join action. See `!antiraid settings`.

## Presets

```
!security preset
!security preset strict
```

| Preset | For |
|---|---|
| `relaxed` | Small, trusted communities |
| `balanced` | Most servers |
| `strict` | Public servers |
| `paranoid` | Servers under attack. Lowest limits, ban on violation, captcha verification, automatic backups and lockdown after an attack |

A preset changes many settings at once and is owner-only. Export first if you want to go back: `!security export` sends your changed settings as a JSON file, and `!security import` with the file attached restores them.

## Threat score and Beast Mode

Detections add points: an AntiNuke trigger, raid mode, severe AutoMod hits, quarantine tampering, flagged joins and verification lockouts. When the score inside the **threat window** reaches the **threat threshold**, **Beast Mode** switches on:

- AntiNuke limits are halved and strict mode is on.
- AutoMod heat builds faster.

It ends on its own when the score drops. `!security threat` shows the score and what raised it. `!security beast off` ends it early. The score can be turned off with `!security set security threat_score off`.

## Server lockdown

```
!serverlock on [reason]
!serverlock off
!serverlock duration 30m
!serverlock skip add #announcements
!serverlock auto nuke on
!serverlock auto raid on
```

Aliases: `!panic`, `!slock`. Lockdown denies sending messages, reactions, threads and voice for **@everyone** in every channel and remembers what each channel looked like before. It lifts by itself after the lockdown length (30 minutes by default) and puts every channel back exactly as it was. Channels you add to the skip list stay open. This is separate from `!lockdown`, which locks one channel.

`serverlock auto nuke on` locks the server after an AntiNuke trigger. `serverlock auto raid on` does it when raid mode starts.

## Backups

```
!backup create [label]
!backup list
!backup info <id>
!backup restore <id> [roles|channels|all] [repair]
!backup delete <id>
!backup auto on
```

A backup keeps roles, role permissions, categories, channels and their permission overwrites, the ban list (up to 1000) and a few server settings. **Restore only creates what is missing.** Nothing existing is deleted. Restore `roles`, `channels`, `bans`, `settings` or `all`. Add `repair` to also reset the permissions of roles that still exist. Members' role assignments and messages are not part of a backup. Restoring is owner-only.

Automatic backups run every few hours (`security.backup_interval_hours`) and keep the newest few (`security.backup_keep`). Manual backups keep the newest 25.

## Extra protections

All of these are off by default and switched on in the paranoid preset.

| Feature | Setting prefix | What it does |
|---|---|---|
| Impersonation filter | `antiraid.gate_impersonation_*` | Flags joins whose name is nearly the same as a staff member's |
| Ban evasion filter | `antiraid.gate_evasion_*` | Flags joins with the same avatar or a very similar name as a banned user |
| Invite tracking | `antiraid.invite_tracking`, `revoke_invites` | Remembers which invite each member used and deletes an invite once several flagged joins came through it. Needs Manage Server |
| Native AutoMod | `!automod native sync` | Mirrors banned words, the mention limit and spam into Discord's own AutoMod so they work even if the bot is offline |
| Warning ladder | `automod.warn_*` | Timeout, kick or ban at set warning counts within a time window |
| Webhook protection | `automod.webhook_protection` | Deletes webhook posts that ping everyone, carry invites or mass-mention |
| Burst lockdown | `automod.burst_lockdown` | Locks the server when many mass-mention messages arrive within the window |
| Restore after attack | `antinuke.restore_from_backup` | Recreates missing roles, channels and bans from the latest backup after an AntiNuke incident |

## Security check

`!securitycheck` scans the server and gives a score out of 100, with the most serious findings first: dangerous permissions on @everyone, too many administrator roles or bots, roles above the bot, missing bot permissions, modules that are off, the quarantine role, administrator bypass, the tier lock and missing backups.

## Limits to know about

- Everything depends on Discord's audit log. If the bot lacks **View Audit Log**, AntiNuke cannot see who acted.
- The bot can only act on members and roles **below** its own top role.
- Restores recreate objects, so channel and role IDs change.
- Counts and threat scores are kept in memory and reset when the bot restarts.
- Ban evasion and impersonation checks are heuristics: they compare avatars and names, not people. Soward cannot detect VPNs or alt accounts reliably.
