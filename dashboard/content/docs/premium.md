---
title: Premium
description: What Premium unlocks, the limits, and how to activate it.
order: 64
group: Utility
---

## What you get

| Feature | Free | Premium |
| --- | --- | --- |
| Ticket panels | 3 | 10 |
| Staff roles per ticket panel | 10 | 20 |
| Ticket categories per panel | 5 | 10 |
| Ticket form questions | 5 | 10 |
| Open tickets per server | 25 | 250 |
| Embed templates | 100 | 250 |
| No-prefix mode | No | Yes |
| Bot profile customization (`!nbot`) | No | Yes |

## Activate a key

If you were given a premium key, run this in your server:

```
!premium claim <key>
```

Run `!premium` to see the current status and when it expires.

## No-prefix mode

With premium active, members can run commands without typing the prefix. Administrators control it:

| Command | What it does | Needs |
| --- | --- | --- |
| `!premium` | Shows premium status and expiry | Anyone |
| `!premium claim <key>` | Activates premium with a key | Anyone |
| `!premium np` | Shows whether no-prefix mode is on | Administrator |
| `!premium np enable` | Turns no-prefix mode on | Administrator and premium |
| `!premium np disable` | Turns no-prefix mode off | Administrator |

The dashboard also has a no-prefix switch under **Server settings**.

## Owner commands

Bot owners can run `!premium generate`, `!premium revoke` and `!premium keys` to issue, remove and list keys. Durations are presets such as `3d`, `1w`, `1m`, `3mo`, `6mo` and `1y`.

## Notes

Premium is granted for a set time or permanently. The bot does not take payments. Keys are issued by the bot team. When premium ends, existing panels and templates stay, but you cannot create more than the free limits.
