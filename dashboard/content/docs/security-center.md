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

### Granular rules

Scopes exempt a whole system. Granular rules allow one specific thing instead.

```
!whitelist action @Builder channel_create channel_update
!whitelist action @Mod members
!whitelist invite #partners discord.gg/abc123
!whitelist invite @Partners 123456789012345678
!whitelist link server youtube.com
!whitelist word #memes heck
!whitelist rules
!whitelist revoke #partners invite discord.gg/abc123
!whitelist clearrules
```

- **Actions** (member or role): allowed to do only the named AntiNuke actions, such as `channel_create` without `channel_delete`. Groups: `channels`, `roles`, `members`, `webhooks`, `emojis`, `server`. Everything else is still watched.
- **Invites**: allow one invite link or code, or every invite to one server by giving its server ID. Use a channel to allow it in that channel only, or `server` to allow it everywhere.
- **Links**: allow one domain, including its subdomains. Scam and phishing filters still apply.
- **Words**: allow one banned word.
- Invite, link and word rules accept a member, role, channel, category or `server` as the target.
- Rules are mirrored to the backup database like other settings. A server can have up to 500.


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

## Commands

Plain Administrators can only view while the tier lock is on.

| Command | What it does | Needs |
|---|---|---|
| `!security` (alias `!sec`) | Overview of every protection and your access level | Administrator |
| `!security threat` | The threat score and what raised it | Administrator |
| `!security settings`, `get <key>` | View settings | Administrator |
| `!security set <module> <key> <value>`, `add`, `remove` | Change settings in any module | Trusted Admin |
| `!security log <channel>`, `!security alerts <channel> [role]` | Where logs and alerts go | Trusted Admin |
| `!security beast off` | End Beast Mode early | Trusted Admin |
| `!whitelist list`, `scopes` (alias `!wl`) | View the whitelist | Trusted Admin |
| `!serverlock`, `!backup`, `!securitycheck` | Lockdown, backups, scan | Trusted Admin |
| `!security lock <on/off>` | The tier lock | Extra Owner |
| `!security setup [preview\|preset]` | Scan the server and set up protection automatically | Extra Owner |
| `!security preset <name>`, `export`, `import`, `reset` | Presets, export, import, reset | Extra Owner |
| `!whitelist add / remove / clear` | Edit the whitelist | Extra Owner |
| `!whitelist action / invite / link / word / revoke / clearrules` | Edit granular rules | Extra Owner |
| `!whitelist rules` | View granular rules | Trusted Admin |
| `!backup restore <id>` | Restore a backup | Extra Owner |

"Extra Owner" means an Extra Owner or the server owner.

## Customizing everything

Every security module exposes the same commands. Over 240 settings in total.

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

## Automatic setup

`!security setup` looks at your server and configures protection for you. It is the fastest way to get a sensible setup, and you can change anything afterwards.

```
!security setup preview
!security setup
!security setup strict
```

**What it looks at:** member count, how many people joined this week, your busiest hour of joins, how many of this week's joiners have accounts under 7 days old, how many accounts and bots hold Administrator, whether the server is a public community, how many moderation cases you had in the last 30 days, and weekly activity when leveling is on. Join statistics come from the members Soward can see, so a very large server may show approximate numbers.

**What it does:**

1. Scores your risk from those signals and picks a preset: `relaxed` for small, low-risk servers, `balanced` for most, `strict` for busy or public ones, `paranoid` for high-risk ones. Name a preset yourself to override the choice.
2. Tunes a few values to your server. A busy server gets a higher raid trigger so normal join waves do not count as a raid, and backup frequency follows your size.
3. Creates the log channels and points the security log and alerts at them, unless you already have them.
4. Creates a **Quarantined** role that cannot see any channel and makes it Soward's quarantine role, unless you already have one.
5. Takes a first backup of roles, channels, bans and settings if you have none.

Soward shows the plan with **Confirm** and **Cancel** buttons and changes nothing until you confirm. `preview` shows the plan only.

**What it leaves alone:** verification. Switching verification on changes how every new member joins, so setup only recommends a type and tells you the command. It also reports things it cannot fix, such as Administrator bots, Discord's 2FA requirement for moderators, and Soward's role being too low.

When it finishes, Soward sends your settings from before the run as a JSON file. `!security import` with that file attached restores the custom values you had. Run `!securitycheck` afterwards to see your score.

Setup needs the server owner, an Extra Owner, and the Manage Roles, Manage Channels and Manage Webhooks permissions for the bot. Steps that need a missing permission are skipped and listed.

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

Detections add points: an AntiNuke trigger, raid mode, severe AutoMod hits and punishments, quarantine tampering, flagged joins, mass-mention bursts, abusive webhooks, verification lockouts and web verification results that look like a VPN or an alt account. When the score inside the **threat window** reaches the **threat threshold**, **Beast Mode** switches on:

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

`!backup` saves roles and channels for free. Premium servers can also use [deep backups](/docs/deep-backups), which save Soward's settings, embeds, panels and custom commands too.

```
!backup create [label]
!backup list
!backup info <id>
!backup diff <id>
!backup restore <id> [roles|channels|bans|settings|all] [repair] [preview]
!backup delete <id>
!backup auto on
```

A backup keeps roles, role permissions, categories, channels and their permission overwrites, the ban list (up to 1000) and a few server settings. **Restore only creates what is missing.** Nothing existing is deleted. Restore `roles`, `channels`, `bans` (bans that went missing), `settings` (name, verification level, content filter, notifications and AFK timeout) or `all`. Add `repair` to also reset the permissions of roles that still exist. Members' role assignments and messages are not part of a backup. Restoring is owner-only.

`backup diff <id>` lists what changed since a backup: deleted roles and channels, and edited role permissions, channel names, topics, categories and permissions, plus channels created afterwards. `backup restore <id> preview` shows what a restore would do without changing anything. `repair` now also puts edited **channels** back (name, category, topic, slowmode and permission overwrites), not only role permissions.

Turn on `antinuke.restore_from_backup` to restore automatically after an AntiNuke incident, and `antinuke.restore_repair` to also repair edited roles and channels at the same time. Dating v2 turns both on.

Automatic backups run every few hours (`security.backup_interval_hours`) and keep the newest few (`security.backup_keep`). Manual backups keep the newest 25.

## Incident post-mortems

When a raid, a Beast Mode period or an AntiNuke incident calms down (no raid mode, no Beast Mode, no lockdown and three quiet minutes), Soward posts a summary in the alert channel:

- what started it and how long it lasted
- which protections were raised (raid mode, Beast Mode, suspended whitelists, lockdown, verification level)
- accounts that were kicked, banned, timed out or quarantined, and why
- which AntiNuke limits fired and the punishment
- what was undone (restored channels and roles, objects the attacker created that were removed, verification level and lockdown put back, backup restores)

`!postmortem` lists the last incidents, `!postmortem <id>` reads one and `!postmortem end` closes the current one early. Turn it off with `security.postmortem`.

## Whitelist audit and expiry

Every whitelist entry and granular rule now records when it was **last used**, and can **expire**.

```
!whitelist add @Contractor all 7d
!whitelist action @Mod channel_create 12h
!whitelist invite #partners discord.gg/example 30d
!whitelist expire @Contractor 3d
!whitelist expire @Contractor never
!whitelist audit
```

A trailing length such as `12h`, `7d` or `4w` sets an expiry. Expired entries are removed automatically and logged. `whitelist audit` lists entries that were never used, are stale (unused for `security.whitelist_stale_days`, 30 by default), expire within a week, or point at a member, role or channel that no longer exists. A weekly report with the same findings goes to the security log when `security.whitelist_report` is on. The first report arrives a week after the update.

"Last used" means the last time a security check matched that entry.

## Previewing changes

Add `preview` to see what would change without changing anything:

```
!security preset strict preview
!security import preview
!whitelist add @Mod all 7d preview
!whitelist action @Mod channel_create preview
!whitelist remove @Mod preview
!backup restore <id> all repair preview
!template apply datingv2 preview
```

## Extra protections

All of these are off by default. The strict preset switches on impersonation filtering, invite tracking and webhook protection, and the paranoid preset switches on all of them.

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
- Ban evasion and impersonation checks are heuristics: they compare avatars and names, not people.
- VPN and alt detection only exist in the `web` verification type, which needs an IP intelligence provider for VPNs. See [Verification](/docs/verification#web-verification).

## Settings reference

Every security setting, taken from the bot's settings list. Change one with `!security set security <key> <value>`, look at one with `!security get <key>` and put one back with `!security reset security <key>`.

### General

| Setting | Default | Allowed | What it does |
| --- | --- | --- | --- |
| `lock` | On | On or Off | When on, only the owner, Extra Owners and Trusted Admins can change security settings. |
| `log_channel_id` | Not set | a channel | Where every security action is logged. |
| `alert_channel_id` | Not set | a channel | Where urgent alerts are posted. Falls back to the log channel. |
| `alert_role_id` | Not set | a role | Pinged when AntiNuke triggers or a raid starts. |
| `alert_owner` | On | On or Off | Direct message the server owner on serious detections. |
| `auto_backup` | Off | On or Off | Snapshot roles and channels on a schedule so they can be restored. |
| `backup_interval_hours` | 6 | 1 to 168 | Backup interval (hours) |
| `backup_keep` | 5 | 1 to 25 | Automatic backups to keep |
| `postmortem` | On | On or Off | Post a summary of what happened, who was actioned and what was undone when a raid or attack ends. |
| `whitelist_report` | On | On or Off | Post a weekly list of unused, stale and expiring whitelist entries to the security log. |
| `whitelist_stale_days` | 30 | 7 to 365 | Days before a whitelist entry counts as stale |
| `lockdown_duration` | 30m 0s | 1m 0s to 1d 0h | How long a lockdown lasts before it lifts on its own. |
| `lockdown_on_nuke` | Off | On or Off | Lock the server after an AntiNuke trigger |
| `lockdown_on_raid` | Off | On or Off | Lock the server when raid mode starts |
| `lockdown_skip_channels` | Empty | list, up to 50 | Channels left open during a lockdown. |
| `protected_roles` | Empty | list, up to 25 | Only trusted members can give or remove these roles. |
| `threat_score` | On | On or Off | Raise protection automatically when many detections happen close together. |
| `threat_threshold` | 8 | 2 to 100 | Threat points that trigger Beast Mode |
| `threat_window` | 10m 0s | 1m 0s to 1d 0h | Threat window |
