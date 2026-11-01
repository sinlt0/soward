---
title: Security and moderation
description: Overview of the Security Center, AutoMod, AntiNuke, AntiRaid, NSFW channels and verification, and how they work together.
order: 20
group: Security
---

## The security tools

Soward has several security tools. Each protects against a different problem, and they work best together. All of them are off until you turn them on.

| Tool | Protects against | Guide |
| --- | --- | --- |
| Security Center | Who can change security settings, the whitelist, presets, lockdown, backups | [Security Center](/docs/security-center) |
| AutoMod | Spam, banned words, invite links and bad links from members | [AutoMod](/docs/automod) |
| AntiNuke | Destructive actions such as mass bans and deleted channels | [AntiNuke](/docs/antinuke) |
| AntiRaid | Join floods and suspicious new accounts | [AntiRaid](/docs/antiraid) |
| NSFW channels | NSFW channels visible to everyone | [NSFW channels](/docs/nsfw) |
| Verification | Unchecked new members | [Verification](/docs/verification) |

Quick start:

```
!security preset balanced
```

or turn tools on one by one:

```
!automod enable
!antinuke enable
!antiraid enable
```

Changing security settings needs a Trusted Admin, an Extra Owner or the server owner, and Administrators can view. Applying presets and turning AntiNuke on or off needs an Extra Owner or the server owner. Run a tool's command on its own, such as `!antinuke`, `!antiraid` or `!automod`, to open an overview panel. Only the person who ran it can use its buttons.

You can also turn tools on and change their settings from the web dashboard. See [Using the dashboard](/docs/dashboard).

## How the tools work together

- **Access tiers.** The server owner and Extra Owners control security. Trusted Admins can change settings. While the tier lock is on (the default), plain Administrators can only view. See [Security Center](/docs/security-center).
- **Trusted members.** The server owner, Extra Owners, Trusted Admins and members on the AntiNuke trusted list are skipped by AutoMod, AntiNuke and AntiRaid. Administrators are skipped by AutoMod and AntiRaid, and by AntiNuke only if you turn on `!antinuke adminbypass`. The [whitelist](/docs/security-center) exempts people, roles and channels from chosen systems only.
- **Quarantine.** AntiNuke, AutoMod, AntiRaid and Verification can quarantine a member, which removes their roles. A quarantined member loses access to moderation and security commands. Only the server owner and Extra Owners can release them with `!release @member`.
- **Moderation.** Moderation commands refuse to act on the owner, Extra Owners and the bot, and warnings can escalate to a timeout, kick or ban with the AutoMod [warning ladder](/docs/automod). See [Moderation](/docs/moderation).
- **Incident state.** The server has an incident state of `normal`, `elevated` or `lockdown`. AntiNuke raises it after each punishment, and at `lockdown` verification switches to manual approval.
- **Panic mode and raid mode.** AutoMod starts panic mode when 3 members hit severe heat within 60 seconds. AntiRaid shares this state and starts raid mode when it sees panic mode or an AntiNuke punishment.
- **Threat score.** Detections from every tool add to one score. When it passes the threshold, Beast Mode halves AntiNuke limits and makes AutoMod stricter.
- **Server lockdown and backups.** Any tool can trigger a [server lockdown](/docs/security-center), and AntiNuke can restore roles, channels and bans from a backup after an attack.
- **Logs.** Quarantines, raid mode changes, flagged joins, AutoMod actions and warnings are sent to your Security log channel if you set up [logging](/docs/logging).

## AutoMod

```
!automod enable
!automod banword <word>
!automod blockinvites on
!automod native sync
```

AutoMod gives each member a heat score. Messages and rule breaks add heat, and it drains over time. At 10 heat the member is punished (a timeout by default), and at 30 they are quarantined. It also has a warning ladder, webhook protection and a sync to Discord's own AutoMod. [Read the full AutoMod guide](/docs/automod).

## AntiNuke

```
!antinuke enable
!antinuke punishment quarantine
!antinuke threshold channel_delete 2
!antinuke trust add @member
```

AntiNuke counts destructive actions per person in a 10 second window and punishes anyone who reaches the limit. It can also revert dangerous permission grants, protect quarantined members and roll back what an attacker changed. [Read the full AntiNuke guide](/docs/antinuke).

## AntiRaid

```
!antiraid enable
!antiraid minage 7
!antiraid velocity 10 30
!antiraid action kick
!antiraid alertchannel #alerts
```

AntiRaid runs a join gate (account age, avatar, names, suspicion score, impersonation, ban evasion), detects join floods and runs raid mode. [Read the full AntiRaid guide](/docs/antiraid).

## NSFW channels

```
!nsfw role @NSFW
!nsfw addchannel #nsfw
```

Registered channels are hidden from everyone except the NSFW role. [Read the full NSFW guide](/docs/nsfw).

## Verification

```
!verification type captcha
!verification role @Member
!verification gaterole @Unverified
!verification setup #verify
```

Choose `button`, `captcha`, `manual` or `web` for the type. The `web` type is the only one that can look for VPNs and alt accounts. Staff can use `!approve @member` for manual reviews. [Read the full Verification guide](/docs/verification).

## Role order matters

The bot can only manage roles below its own highest role. Move the bot's role above the roles it needs to manage, and give it the permissions its actions need: Kick Members, Ban Members, Moderate Members, Manage Roles, Manage Channels and View Audit Log.

## Ban evasion detection

When someone is banned, Soward remembers their avatar, name, invite and account age. When a new member joins and looks like a banned account (same custom avatar, same or very similar name, same invite, account made after the ban), Soward posts an alert with a score out of 100 and **Ban** and **Not the same person** buttons. It is a signal, not proof, so nothing happens automatically unless you choose to.

```
!evasion channel #security-logs
!evasion scan
```

| Command | What it does |
| --- | --- |
| `!evasion scan` | Learn accounts that were banned before this feature. |
| `!evasion check @member` | Show the closest banned accounts. |
| `!evasion list` | Recent alerts. |
| `!evasion threshold <30-100>` | Score that triggers an alert. Default 60. |
| `!evasion action none\|timeout\|kick` | Extra action on a match. Default none. |
| `!evasion on` / `off` | Turn it on or off. On by default. |

When you ban someone who was flagged, the normal ban message with the appeal button is still sent.

## Incident post-mortems

When AntiRaid raid mode or AntiNuke's Beast Mode starts, Soward begins tracking an incident. When it ends, it posts a one-page summary to your security alert channel (or log channel): how long it lasted, what started it, which protections were raised, the peak threat score, every account it actioned, which AntiNuke limits fired, what was undone and a short timeline.

| Command | What it does | Needs |
| --- | --- | --- |
| `!postmortem` (aliases `!incidents`, `!incident`) | Lists saved incidents with their ids | Trusted Admin |
| `!postmortem <id>` | Shows one saved incident again | Trusted Admin |
| `!postmortem end` | Closes the open incident now and posts the summary | Trusted Admin |

The last 50 incidents are kept. Incidents close on their own when the threat has passed.

## Pause all security

`!security disable [duration] [reason]` pauses every security system at once and keeps all your settings, whitelist and permit tiers. `!security enable` switches everything back on exactly as it was. Only the server owner and Extra Owners can use them.

It is meant for planned situations, for example when a boost service joins with many alt accounts: pause security, whitelist the accounts you expect, then enable it again.

```
!security disable 2h boost service
!whitelist add ...
!security enable
```

While paused, AntiNuke, AntiRaid (including bot-join checks), AutoMod, join verification, the verification timeout kick and ban evasion alerts do not act. Logging, the whitelist, permit tiers and members who are already quarantined are unchanged. Raid mode is ended when you pause.

For safety there is always an end time: the default is 2 hours and the longest is 7 days. Security switches back on by itself when it passes and `!security` shows when. Pausing and resuming are written to the security log.
