---
title: Security and moderation
description: AutoMod, AntiNuke, AntiRaid and verification.
order: 4
---

## AutoMod

```
!automod enable
!automod banword <word>
!automod blockinvites
!automod blockdomain example.com
```

AutoMod tracks a heat score per member so repeat offenders escalate. Use `!automod heat @member` to view it and `!automod resetheat @member` to clear it.

## AntiNuke

Stops malicious admin actions such as mass bans and channel deletion.

```
!antinuke enable
!antinuke punishment quarantine
!antinuke threshold 3
!antinuke trust @member
```

Use `!antinuke strict` to punish any dangerous permission grant. `!antinuke incident` shows or changes the incident state.

## AntiRaid

```
!antiraid enable
!antiraid minage 7
!antiraid velocity 10 30
!antiraid action kick
!antiraid alertchannel #alerts
```

`!antiraid raidmode` turns raid mode on or off manually and `!antiraid status` shows what triggered it.

## Verification

```
!verification setup #verify
!verification type captcha
!verification role @Member
!verification gaterole @Unverified
```

Choose `button`, `captcha` or `manual` for the type. Staff can use `!approve @member` for manual reviews.

## Role order matters

The bot can only manage roles below its own highest role. Move the bot's role above the roles it needs to manage.
