---
title: AntiRaid
description: Check every new member, catch join floods and lock the server down with raid mode.
order: 22
group: Security
---

## How AntiRaid works

AntiRaid looks at every new member (bots are handled separately) in three ways:

1. **The join gate.** A set of filters checks each member as they join: account age, avatar, advertising names, blocked name patterns, a suspicion score, names that copy your staff and names or avatars that match banned users. Each filter can have its own action.
2. **Join floods.** If many people join in a short window, or their accounts were created close together, or their names look alike, the server enters **raid mode**.
3. **Raid mode.** While it is on, the members the raid action applies to are actioned, flagged or not. Raid mode can also raise the server's verification level, sweep the burst of joins that started it, revoke the invites they used and start a [server lockdown](/docs/security-center).

AntiRaid is **off by default**. While it is off, joins are only recorded and nobody is actioned.

Never actioned: members with Administrator, the bot's owners, the server owner, Extra Owners, Trusted Admins, AntiNuke trusted members and anyone on the [whitelist](/docs/security-center) for AntiRaid.

## Who can change what

| Level | Can do |
| --- | --- |
| Administrator | View settings, the overview, status and logs |
| Trusted Admin, Extra Owner, server owner | Change settings, turn AntiRaid on, start or end raid mode |
| Extra Owner, server owner | Turn AntiRaid off and reset settings |

While the tier lock is on (the default), a plain Administrator can only view. See [Security Center](/docs/security-center).

## Setup

1. Give the bot the permission for the action you choose (Kick Members, Ban Members, Moderate Members, or Manage Roles for quarantine) and place its role above new members' roles.
2. Pick where alerts go and turn AntiRaid on:

```
!antiraid alertchannel #security-alerts
!antiraid enable
```

3. Tune the gate:

```
!antiraid minage 7
!antiraid velocity 10 30
!antiraid action kick
!antiraid noavatar on
```

4. Run `!antiraid` on its own to open the overview panel. Run `!antiraid settings` to see every setting.

Or apply a whole bundle with `!security preset balanced` (see [Security Center](/docs/security-center)).

## The join gate

Each filter adds a finding. If a member has several findings, the strongest action wins. Every filter has an action setting. The value `default` means "use the default gate action" (`join_action`, kick unless you change it).

| Filter | Default | What it flags |
| --- | --- | --- |
| Account age | On, 7 days | Accounts younger than `min_age_seconds` |
| No avatar | On | Accounts with the default avatar |
| Advertising name | Off | Names that contain invite links or promo words |
| Blocked name patterns | Empty list | Names that contain any text on `name_filter` |
| Suspicious account | Off | A score from account age, no avatar, many digits in the name, no profile badges and no display name. Flagged at `gate_suspicious_score` (3) or more |
| Staff impersonation | Off | Names almost the same as a staff member's (similarity `impersonation_threshold`, 0.88) |
| Ban evasion | Off | The same avatar as a banned user, or a very similar name (`evasion_threshold`, 0.92) |
| Unverified bots | Off | Bots added without Discord verification (default action kick) |

The impersonation and ban evasion filters are **heuristics**. They compare avatars and names, not people, so expect some false positives and use `timeout` or `quarantine` rather than `ban` unless you trust them.

Actions are `none`, `timeout`, `kick`, `ban` and `quarantine`. A timeout lasts `timeout_duration` (1 hour). A quarantined member can only be released by the server owner or an Extra Owner.

With `action_dm` on, the member gets a message before they are removed. With `gate_age_dm` on, that message also says how old an account must be.

## Raid mode

Raid mode starts when:

- **Join velocity** is reached: `join_velocity_count` joins within `join_velocity_window` seconds (default 10 in 10).
- **Account clusters** are seen: `id_count` accounts (4) created within `id_window` (1 hour) of each other, when `id_cluster` is on.
- **Similar names** are seen: `similar_count` joins (4) with matching names, when `similar_names` is on.
- A staff member runs `!antiraid raidmode`.
- **AntiNuke** punishes someone, when `follow_antinuke` is on.
- AutoMod starts server-wide panic mode.

When it starts, AntiRaid can:

| Step | Setting | Default |
| --- | --- | --- |
| Raise verification to High (put back when it ends) | `raise_verification` | On |
| Action the burst of joins that caused it | `sweep` | On |
| Lock the whole server | `security.lockdown_on_raid` | Off |
| Add to the [threat score](/docs/security-center) | always | |
| Post an alert in the alert channel | `alert_channel_id` | |

While raid mode is on, new members get the **raid action** (`raid_mode_action`, kick by default). `raid_target` decides who: `all` (every non-exempt member) or `flagged` (only those a gate filter caught). Raid mode lasts 10 minutes (`raid_mode_duration`) and ends by itself, or earlier with `!antiraid raidmode`.

## Invite tracking

With `invite_tracking` on, AntiRaid remembers which invite each member used. With `revoke_invites` on as well, an invite is deleted once `revoke_invite_min` (3) flagged joins came through it within `invite_window` (10 minutes). This needs the Manage Server permission. If the bot was offline when an invite was used, that join cannot be traced.

## Commands

Everything below is also available through `!antiraid set <setting> <value>`.

| Command | What it does | Needs |
| --- | --- | --- |
| `!antiraid` (alias `!raid`) | Opens the overview panel | Administrator |
| `!antiraid settings [group]` | Lists settings and their values | Administrator |
| `!antiraid get <setting>` | Shows one setting and its default | Administrator |
| `!antiraid list <setting>` | Shows a list setting | Administrator |
| `!antiraid set <setting> <value>` | Changes a setting | Trusted Admin |
| `!antiraid add / remove <setting> <value>` | Edits a list setting | Trusted Admin |
| `!antiraid reset <setting or all>` | Restores defaults | Extra Owner |
| `!antiraid enable` | Turns AntiRaid on | Trusted Admin |
| `!antiraid disable` | Turns AntiRaid off | Extra Owner |
| `!antiraid minage <days>` | Minimum account age. `0` stops the age check | Trusted Admin |
| `!antiraid velocity <count> [seconds]` | Joins that start raid mode | Trusted Admin |
| `!antiraid action <kick/ban/timeout/quarantine>` | Default gate action | Trusted Admin |
| `!antiraid raidaction <kick/ban/timeout/quarantine>` | Action during raid mode | Trusted Admin |
| `!antiraid noavatar <on/off>` | Flag accounts with no avatar | Trusted Admin |
| `!antiraid namefilter <add/remove/list> [text]` | Blocked name patterns | Trusted Admin |
| `!antiraid sweep <on/off>` | Action the burst that started a raid | Trusted Admin |
| `!antiraid raiseverification <on/off>` | Raise verification during raid mode | Trusted Admin |
| `!antiraid follownuke <on/off>` | Start raid mode when AntiNuke triggers | Trusted Admin |
| `!antiraid alertchannel <channel>` | Where raid alerts go | Trusted Admin |
| `!antiraid raidmode` | Start or end raid mode (works even if AntiRaid is off, but joins are only actioned while it is on) | Trusted Admin |
| `!antiraid status` | Raid and panic mode state, trigger, start and expiry | Anyone |
| `!antiraid logs` | The 15 latest flagged joins | Administrator |

## From the dashboard

Open **AntiRaid** under Security. The page has the on/off switch and the main settings: minimum account age, join velocity and window, flag no avatar, default action, raid mode length and alert channel. It also shows whether raid mode is active, with a button to start or end it, and the latest 25 flagged joins. The gate filters, invite tracking and the other settings are commands for now.

## Troubleshooting

**Nobody is being actioned.** Check that AntiRaid is on, that the member really fails a filter, and that the bot has the permission for the action with a role above the member's.

**Real new members are being removed.** Raise `join_velocity_count`, lower `minage`, turn off `noavatar` or the suspicious filter, or use `timeout` instead of `kick`. During raid mode with `raid_target all`, every new member is actioned. End it with `!antiraid raidmode` or set `raid_target flagged`.

**Raid mode keeps coming back.** Run `!antiraid status` to see the trigger: `join_velocity`, `pattern:...` (account cluster or similar names), `antinuke_incident`, `automod_heat_panic` or `manual:<id>`.

**An invite was not revoked.** Invite tracking needs Manage Server, only counts joins it saw, and needs `revoke_invite_min` flagged joins through the same invite.

**No alert appeared.** Set `!antiraid alertchannel` and let the bot send messages there. If none is set, the main log channel is used.
