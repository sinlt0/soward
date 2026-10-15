---
title: Verification
description: Gate new members behind a button, captcha or manual approval.
order: 13
group: Moderation
---

## How verification works

When verification is on, new members must pass a check before they get access. You post a **panel** with a Verify button in a channel that only unverified members can see. What happens when they press it depends on the verification **type**:

| Type | What the member does |
| --- | --- |
| `button` | Presses Verify and is accepted immediately. |
| `captcha` | Presses Verify, gets a private image with a 6-character code, then presses Enter code and types it. The code is not case sensitive. A wrong code means they press Verify again for a new one. |
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

## Command reference

`!verify` works as a short name for `!verification`. All commands need Administrator.

| Command | What it does | Needs |
| --- | --- | --- |
| `!verification` | Opens the verification overview panel. | Administrator |
| `!verification type <button\|captcha\|manual>` | Sets how members verify. | Administrator |
| `!verification role <role>` | Sets the role given after verification. | Administrator |
| `!verification gaterole <role>` | Sets the role held until a member verifies. | Administrator |
| `!verification setup <channel>` | Posts the verification panel in a channel. | Administrator |
| `!verification message <text>` | Sets a custom panel message. Use `none`, `reset`, `default`, `clear` or `off` to go back to the default look. | Administrator |
| `!verification pendingtimeout <on\|off> [minutes] [kick\|ban]` | Removes members who never verify. | Administrator |
| `!approve <member>` | Manually verifies a member and grants access. Works for any type. | Administrator |

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

- If your server is in lockdown, the Verify button tells members to wait for staff approval instead of verifying them. Use `!approve` for people you trust.
- When AntiNuke puts the server into lockdown, the verification type is switched to `manual`. When the server returns to normal, your chosen type is restored.

## From the dashboard

The Verification page on the web dashboard lets you:

- Set the verification type, verified role and gate role.
- Turn the "remove members who never verify" option on or off, and set the minutes and action (kick or ban).
- Post or repost the panel in a channel (the old panel message is deleted).
- See members waiting for verification and approve them with one click, or approve by user ID.

The custom panel message is a command only.

## Troubleshooting

- **"No verification type set"**: run `!verification type button`, `captcha` or `manual` first.
- **Members see the whole server**: the gate role must deny access to your channels, or your channels must require the verified role. Soward only hands out the roles, you control what they can see.
- **Roles are not given**: the bot's top role must be above the verified role and gate role.
- **The captcha image does not show**: make sure the bot can attach files in that channel.
- **A member says the button does nothing in manual mode**: that is expected. Their request is logged and staff must run `!approve`.
