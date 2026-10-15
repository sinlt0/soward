---
title: Security and moderation
description: Overview of AutoMod, AntiNuke, AntiRaid, NSFW channels and verification.
order: 20
group: Security
---

## The security tools

Soward has several security tools. Each protects against a different problem, and they work best together. All of them are off until you turn them on.

| Tool | Protects against | Guide |
| --- | --- | --- |
| AutoMod | Spam, banned words, invite links and bad links from members | [AutoMod](/docs/automod) |
| AntiNuke | Destructive actions such as mass bans and deleted channels | [AntiNuke](/docs/antinuke) |
| AntiRaid | Join floods and suspicious new accounts | [AntiRaid](/docs/antiraid) |
| NSFW channels | NSFW channels visible to everyone | [NSFW channels](/docs/nsfw) |
| Verification | Unchecked new members | [Verification](/docs/verification) |

Quick start:

```
!automod enable
!antinuke enable
!antiraid enable
```

Most commands need the **Administrator** permission. Run a tool's command on its own, such as `!antinuke`, `!antiraid` or `!automod`, to open an overview panel. Only the person who ran it can use its buttons.

You can also turn tools on and change their settings from the web dashboard. See [Using the dashboard](/docs/dashboard).

## How the tools work together

- **Trusted members.** Anyone with Administrator, the bot's owners, Extra Owners, Trusted Admins and members on the AntiNuke trusted list are skipped by AutoMod, AntiNuke and AntiRaid. Add people with `!antinuke trust add @member`.
- **Quarantine.** AntiNuke and AutoMod can quarantine a member, which removes their roles. Only the server owner can release them with `!release @member`.
- **Incident state.** The server has an incident state of `normal`, `elevated` or `lockdown`. AntiNuke raises it by one step after each punishment. See it with `!antinuke incident status`.
- **Panic mode.** AutoMod starts a server-wide panic mode when 3 members hit panic-level heat within 60 seconds. AntiRaid shares this state, and starts raid mode when it sees panic mode or an AntiNuke punishment.
- **Logs.** Quarantines, raid mode changes, flagged joins and AutoMod actions are sent to your Security log channel if you set up [logging](/docs/logging).

## AutoMod

```
!automod enable
!automod banword <word>
!automod blockinvites on
!automod blockdomain example.com
```

AutoMod gives each member a heat score. Messages and rule breaks add heat, and it drains over time. At 10 heat the member is timed out, and at 30 they are quarantined. Use `!automod heat @member` to view a score and `!automod resetheat @member` to clear it. [Read the full AutoMod guide](/docs/automod).

## AntiNuke

```
!antinuke enable
!antinuke punishment quarantine
!antinuke threshold channel_delete 2
!antinuke trust add @member
```

AntiNuke counts destructive actions per person in a 10 second window and punishes anyone who reaches the limit. `!antinuke strict on` also punishes any dangerous permission grant. `!antinuke incident status` shows the incident state. [Read the full AntiNuke guide](/docs/antinuke).

## AntiRaid

```
!antiraid enable
!antiraid minage 7
!antiraid velocity 10 30
!antiraid action kick
!antiraid alertchannel #alerts
```

`!antiraid raidmode` turns raid mode on or off by hand and `!antiraid status` shows what triggered it. [Read the full AntiRaid guide](/docs/antiraid).

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

Choose `button`, `captcha` or `manual` for the type. Staff can use `!approve @member` for manual reviews. [Read the full Verification guide](/docs/verification).

## Role order matters

The bot can only manage roles below its own highest role. Move the bot's role above the roles it needs to manage, and give it the permissions its actions need: Kick Members, Ban Members, Moderate Members, Manage Roles, Manage Channels and View Audit Log.
