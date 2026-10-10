---
title: Leveling
description: XP, level-up messages, role rewards and multipliers.
order: 6
---

## Turn it on

```
!leveling enable
!leveling channel #level-ups
!leveling announce channel
```

`announce` accepts `channel`, `dm` or `off`.

## Role rewards

```
!leveling levelrole 10 @Active
!leveling levelroles
!leveling rolestack stack
```

## Custom message

Use `!leveling message <text>` and see the variables available with `!leveling variables`.

## Multipliers and exclusions

- `!leveling multiplier add` adds a bonus for a role, channel or globally
- `!leveling noxp channel` and `!leveling noxp role` stop XP in a channel or for a role
- `!leveling weeklyreset` and `!leveling monthlyreset` reset the leaderboard on a schedule

Members can check progress with `!rank` and `!leaderboard`.
