---
title: Verification
description: Gate new members behind a button, captcha, web check or manual approval.
order: 13
group: Moderation
---

## How verification works

When verification is on, new members must pass a check before they get access. You post a **panel** with a Verify button in a channel that only unverified members can see. What happens when they press it depends on the verification **type**:

| Type | What the member does |
| --- | --- |
| `button` | Presses Verify and is accepted immediately. |
| `captcha` | Presses Verify, gets a private image with a 6-character code, then presses Enter code and types it. The code is not case sensitive. A wrong code means they press Verify again for a new one. |
| `web` | Presses Verify, opens a private web page and passes a check there. The page lets the bot spot VPNs and duplicate (alt) accounts. See [Web verification](#web-verification). |
| `manual` | Presses Verify to ask for access. A staff member must approve them with `!approve`. |

When a member passes, they receive the **verified role**, lose the **gate role** if you use one, get any [AutoRole](/docs/autorole) verify roles and join roles, and an entry is added to your security logs.

Bots are not asked to verify.

## Set it up

```
!verification type captcha
!verification role @Verified
!verification gaterole @Unverified
!verification setup #verify-here
```

1. Choose a type with `!verification type`.
2. Set the verified role with `!verification role`.
3. Optionally set a gate role with `!verification gaterole`. It is given when someone joins and removed once they verify. Use it to hide your channels from unverified members.
4. Post the panel with `!verification setup #channel`. Make sure that channel is hidden from the verified role so only unverified members see it.

`!verification setup` refuses to run until a type is set.

## Challenge and requirements

These settings apply to the `captcha` and `web` types. Change them with `!verification set <setting> <value>`.

| Setting | Default | What it does |
| --- | --- | --- |
| `max_attempts` | 3 | Wrong codes before a lockout (also `!verification attempts`) |
| `lockout_seconds` | 5 minutes | How long a locked-out member must wait |
| `click_cooldown` | 5 seconds | Delay between presses of the Verify button |
| `captcha_length` | 6 | Characters in the captcha code |
| `captcha_lifetime` | 3 minutes | How long a code stays valid |
| `min_account_age_hours` | 0 | Accounts younger than this cannot verify yet (also `!verification minage`) |
| `target` | all | `all`, or `suspicious` to only gate accounts that score at least AntiRaid's suspicion score (see [AntiRaid](/docs/antiraid)) |
| `fail_lockouts` | 0 | After this many lockouts the **fail action** is applied. `0` turns it off |
| `fail_action` | kick | `timeout`, `kick`, `ban` or `quarantine` |
| `log_attempts` | on | Log every attempt to the security log |

Lockouts and attempts are kept in memory and reset when the bot restarts. Every lockout adds to the [threat score](/docs/security-center).

## Command reference

`!verify` works as a short name for `!verification`. While the tier lock is on (the default), changing settings needs a Trusted Admin, Extra Owner or the server owner. Plain Administrators can only view. See [Security Center](/docs/security-center).

| Command | What it does | Needs |
| --- | --- | --- |
| `!verification` | Opens the verification overview panel | Administrator |
| `!verification settings [group]`, `get <key>`, `list <key>` | View settings | Administrator |
| `!verification set <key> <value>`, `add`, `remove` | Change settings and lists | Trusted Admin |
| `!verification type <button\|captcha\|manual\|web>` | Sets how members verify | Trusted Admin |
| `!verification role <role>` | Role given after verification | Trusted Admin |
| `!verification gaterole <role>` | Role held until a member verifies | Trusted Admin |
| `!verification setup <channel>` | Posts the verification panel | Trusted Admin |
| `!verification message <text>` | Custom panel message. Use `none`, `reset`, `default`, `clear` or `off` to go back to the default look | Trusted Admin |
| `!verification attempts <1-10>` | Wrong codes allowed | Trusted Admin |
| `!verification minage <hours>` | Minimum account age, 0 to 720 hours | Trusted Admin |
| `!verification pendingtimeout <on\|off> [minutes] [kick\|ban]` | Removes members who never verify | Trusted Admin |
| `!verification webinfo <member>` (alias `altcheck`) | The stored web check for a member: outcome, VPN flag, country, risk score and possible alts. Never shows an address | Trusted Admin |
| `!approve <member>` | Manually verifies a member and grants access. Works for any type | Trusted Admin |
| `!verification deny <member> [reason]` | Kicks a member who is waiting for review | Trusted Admin |
| `!verification reset <key or all>` | Restores defaults | Extra Owner |

## Custom panel message

```
!verification message Welcome to {server}! Press the button to join our {membercount} members.
```

The message supports the usual message variables such as `{server}`, `{membercount}` and `{servericon}`. You can also use `{embed:name}` to show a saved embed template as a real embed. The embed must already exist. After changing the message, run `!verification setup #channel` again to post a new panel.

## Removing members who never verify

```
!verification pendingtimeout on 30 kick
!verification pendingtimeout off
```

| Setting | Default |
| --- | --- |
| Enabled | Off |
| Time allowed | 30 minutes |
| Action | `kick` (or `ban`) |

The minimum time is 5 minutes. Minutes and action are optional and keep their previous value if left out. The bot checks every 2 minutes, so removal can be a little later than the exact time.

## Interaction with security

- **Incident lockdown.** When AntiNuke pushes the server's [incident state](/docs/antinuke#incident-state) to `lockdown`, the verification type is switched to `manual` and the Verify button asks members to wait for staff. When the state goes back to `normal`, your chosen type is restored. Use `!approve` for people you trust.
- **Quarantined members** cannot verify, and `!approve` refuses them until the server owner or an Extra Owner releases them.
- **AutoMod** treats members who have not verified yet as riskier: their heat is multiplied by 1.5 (see [AutoMod](/docs/automod)).
- **AntiRaid** can raise Discord's own server verification level during raid mode. That is separate from this system. See [AntiRaid](/docs/antiraid).
- Failed attempts and lockouts feed the threat score, and a member who keeps failing gets the fail action.

## From the dashboard

The Verification page on the web dashboard lets you:

- Set the verification type, verified role and gate role.
- Turn the "remove members who never verify" option on or off, and set the minutes and action (kick or ban).
- Post or repost the panel in a channel (the old panel message is deleted).
- See members waiting for verification and approve them with one click, or approve by user ID.

The custom panel message is a command only.

## Web verification

The `web` type is the only one that can look for VPNs and alt accounts, because it needs the member's IP address, which Discord never gives a bot.

1. The member presses Verify and gets a private link button. The link is single use and expires after 15 minutes.
2. The page runs a short proof-of-work check, a hidden trap field and a timing check. Add Cloudflare Turnstile keys to the bot for a stronger captcha.
3. The bot looks at the address and decides: allow, send to staff for `!approve` or `!deny`, or refuse.

**What is stored.** Only one-way hashes of the address and a browser fingerprint, the country, a risk score and the outcome. Raw addresses are never saved. Records are deleted after `verification.web_retention_days` (90 by default). The page tells members what it reads.

**VPN detection needs a provider.** Set `SOWARD_IPINTEL_PROVIDER` to `proxycheck` or `ipqs` on the bot (and `SOWARD_IPINTEL_KEY`). Without one, only alt matching works. The bot owner chooses the provider because the keys cost money and are shared across servers.

**Alt detection** compares the new member with earlier web verifications in the same server. `verification.web_alt_match` picks the rule: `ip` (same address), `ip_and_fingerprint` (same address and browser) or `fingerprint`. The default action is `flag`, which lets the member in and logs the match for staff. Households, schools and mobile networks share addresses, so use `manual` or `deny` with care.

| Setting | Default | What it does |
| --- | --- | --- |
| `web_block_vpn` | on | Act on VPNs, proxies and Tor |
| `web_vpn_action` | deny | `deny`, `manual` or `flag` |
| `web_block_hosting` | off | Also act on data-centre addresses |
| `web_unknown_action` | allow | What to do when no provider answers |
| `web_alt_check` | on | Look for alt accounts |
| `web_alt_match` | ip | `ip`, `ip_and_fingerprint` or `fingerprint` |
| `web_alt_action` | flag | `flag`, `manual` or `deny` |
| `web_retention_days` | 90 | How long hashed records are kept |

The bot needs `SOWARD_DASHBOARD_URL` set to the public site address, and the site must be reachable by members. Behind a proxy such as Render, set `SOWARD_BEHIND_PROXY=1`. These checks are signals, not proof. Determined users can still use residential proxies or separate networks.

## Troubleshooting

- **"No verification type set"**: run `!verification type button`, `captcha`, `manual` or `web` first.
- **Members get "Web verification is not set up"**: the bot has no `SOWARD_DASHBOARD_URL`.
- **Members see the whole server**: the gate role must deny access to your channels, or your channels must require the verified role. Soward only hands out the roles, you control what they can see.
- **Roles are not given**: the bot's top role must be above the verified role and gate role.
- **The captcha image does not show**: make sure the bot can attach files in that channel.
- **A member says the button does nothing in manual mode**: that is expected. Their request is logged and staff must run `!approve`.
