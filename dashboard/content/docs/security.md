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
- **Trusted members.** The server owner, Extra Owners, Trusted Admins, the bot's owners and members on the AntiNuke trusted list are skipped by AutoMod, AntiNuke and AntiRaid. Administrators are skipped by AutoMod and AntiRaid, and by AntiNuke only if you turn on `!antinuke adminbypass`. The [whitelist](/docs/security-center) exempts people, roles and channels from chosen systems only.
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
