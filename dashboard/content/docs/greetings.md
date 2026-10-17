---
title: Greetings
description: Welcome, leave, boost and ban messages, with optional embeds and image cards.
order: 32
group: Community
---

## How greetings work

Greetings are automatic messages the bot sends when something happens to a member. There are four triggers, and each one is set up separately.

| Trigger | Sent when |
| --- | --- |
| `join` | A member joins the server. |
| `leave` | A member leaves or is kicked. |
| `boost` | A member starts boosting the server. |
| `ban` | A member is banned. |

Notes:

- Bots are ignored.
- A member who is banned triggers `ban` instead of `leave`.
- Each trigger is off until you set a channel (or DM delivery) and turn it on.
- If you enable a trigger but leave the message empty, the bot sends a simple default line such as "Welcome to Server!".
- Mentions in greetings can ping users but never roles or `@everyone`.

Use `!greetings` to see the state and channel of all four triggers. Aliases: `!welcome`, `!greet`.

## Quick start

```
!greetings channel join #welcome
!greetings message join Welcome to {server}, {user}! You are our {membercount_ordinal} member.
!greetings toggle join
!greetings test join
```

Run `!greetings test join` to see exactly what a join would look like using your own account. The bot reacts with a check mark when it has sent it.

## Command reference

All subcommands need **Manage Server** (or the fake permission `manage_guild`), except `variables`. Bot owners are always allowed. In every command, `<trigger>` is `join`, `leave`, `boost` or `ban`.

| Command | What it does | Needs |
| --- | --- | --- |
| `!greetings` | Shows each trigger's state and channel. | Manage Server |
| `!greetings channel <trigger> <#channel>` | Sets the channel the message is posted in. | Manage Server |
| `!greetings toggle <trigger>` | Turns a trigger on or off. To turn it on you need a channel set or DM delivery on. | Manage Server |
| `!greetings message <trigger> <text>` | Sets the message text and shows a preview. The text can include `{embed:name}`. | Manage Server |
| `!greetings embed <trigger> <name\|off>` | Attaches a saved embed template, or removes it with `off`. | Manage Server |
| `!greetings dm <trigger> <on\|off> [fallback_on\|fallback_off]` | Sends the greeting as a direct message. Only for `join`, `leave` and `boost`. | Manage Server |
| `!greetings card <trigger> <on\|off> [layout]` | Turns the image card on or off, and optionally picks a layout. | Manage Server |
| `!greetings cardcolor <trigger> <#hex>` | Sets the card accent color. | Manage Server |
| `!greetings cardbackground <trigger> <url\|off>` | Sets a custom card background image, or removes it with `off`. | Manage Server |
| `!greetings deleteafter <trigger> <seconds>` | Deletes the channel message after a delay. `0` turns it off. | Manage Server |
| `!greetings joinroledelay <seconds>` | Delays the automatic join role. `0` turns the delay off. | Manage Server |
| `!greetings test <trigger>` | Sends the greeting using your own account so you can check it. For `ban`, the reason shows as "Test reason". | Manage Server |
| `!greetings variables` | Lists all placeholders. Alias: `!greetings vars`. | Anyone |

## Messages and embeds

The message can be plain text, an embed, or both.

```
!greetings message leave Goodbye {username}. We are now {membercount} members.
!greetings message join {embed:welcome}
!greetings embed boost thanks
```

- `{embed:name}` inside the message adds that embed template and the rest of the text is sent as normal text.
- `!greetings embed <trigger> <name>` attaches a template separately. It is sent in addition to anything in the message text. The template must already exist (see [embeds](/docs/embeds)).
- Placeholders work in the message text and inside the embed.
- Conditions and random text also work: `{if membercount > 100}...{else}...{end}` and `{random}one{|}two{endrandom}`.

## Placeholders

| Placeholder | Output |
| --- | --- |
| `{user}` | Mentions the member. |
| `{username}` | The member's display name. |
| `{usertag}` | The member's username. |
| `{userid}` | The member's ID. |
| `{useravatar}` | Link to the member's avatar. |
| `{userjoindate}` | When the member joined the server, as a Discord timestamp. |
| `{usercreated}` | When the member's account was created, as a Discord timestamp. |
| `{server}` | Server name. |
| `{serverid}` | Server ID. |
| `{servericon}` | Link to the server icon. Empty if there is none. |
| `{membercount}` | Member count. |
| `{membercount_ordinal}` | Member count with a suffix, for example "214th". |
| `{boostcount}` | Number of boosts the server has. |

Trigger-specific placeholders:

| Placeholder | Works in | Output |
| --- | --- | --- |
| `{server_boostcount}` | boost | Total active boosts on the server. |
| `{server_boostlevel}` | boost | The server's boost level, 0 to 3. |
| `{server_boosts_until_next_level}` | boost | Boosts needed for the next level, or "Max level reached". |
| `{user_boosting_since}` | boost | The date the member started boosting. |
| `{ban_reason}` | ban | The ban reason, or "No reason provided". |

Channel placeholders (`{channel}`, `{channelname}`, `{channelid}`) are not filled in greetings. Placeholders that do not apply to a trigger are left as typed.

## Direct messages

`!greetings dm <trigger> on` sends the greeting to the member as a direct message instead of in the channel. DMs are available for `join`, `leave` and `boost`. A banned member cannot be messaged, so `ban` has no DM option.

- `fallback_on` is the default. If the DM could not be delivered (for example the member has DMs closed), the greeting is posted in the channel instead.
- With `fallback_off`, the greeting is only ever sent as a DM. Nothing is posted in the channel, even when the DM fails.
- With DM delivery off, only the channel message is sent.
- A channel message is only posted if a channel is set for the trigger.

```
!greetings dm join on
!greetings dm join on fallback_off
!greetings dm join off
```

## Image cards

A card is a generated welcome image with the member's avatar, the title and their position in the member list.

```
!greetings card join on banner
!greetings cardcolor join #7FB3D5
!greetings cardbackground join https://example.com/background.png
```

| Setting | Values |
| --- | --- |
| Layouts | `classic` (default), `left`, `right`, `banner` |
| Accent color | A 6-digit hex color. The default is `#7FB3D5`. |
| Background | A direct link to an image starting with `http://` or `https://`. |

- The card title is "Welcome to Server!", "Name has left the server.", "Thank you for boosting, Name!" or "Name was banned." depending on the trigger. The text under it is the member's position, for example "214th".
- If a card is on and the greeting includes an embed, the card is shown inside the last embed. Otherwise it is attached as an image.
- If the avatar cannot be downloaded in time, the card is skipped and the rest of the greeting is still sent. A background that cannot be downloaded is replaced by the default background.

## Delete after and join role delay

- `!greetings deleteafter <trigger> <seconds>` removes the channel message after that many seconds. It does not affect direct messages.
- `!greetings joinroledelay <seconds>` delays the [auto role](/docs/autorole) for new members by 0 to 3600 seconds. It is stored with the join greeting but works even if the join greeting is off.

## Limits

| Setting | Value |
| --- | --- |
| Triggers | 4: join, leave, boost, ban |
| Card layouts | classic, left, right, banner |
| Join role delay | 0 to 3600 seconds |
| Embeds per greeting | One attached template plus any `{embed:name}` tags in the message |

Greetings are free for all servers. Embed template limits are in [embeds](/docs/embeds).

## From the dashboard

The Greetings page on the web dashboard has a section for each trigger (member joins, leaves, server boosted, member banned). For each you can set:

- Enabled
- Channel
- Message (up to 1500 characters, with the same placeholders)
- Embed, picked from your saved templates
- Send an image card
- Send as a direct message

Still commands only: the card layout, card color and background, DM fallback behavior, delete after, join role delay and `!greetings test`. Create and edit the embeds themselves on the Embeds page.

## Troubleshooting

- **"No Destination" when toggling**: set a channel with `!greetings channel <trigger> #channel` first, or turn on DM delivery.
- **Nothing is sent**: run `!greetings` to check that the trigger is enabled and has a channel. Make sure the bot can Send Messages (and Embed Links and Attach Files for embeds and cards) in that channel.
- **A banned member did not get a leave message**: bans use the `ban` trigger, not `leave`.
- **A placeholder shows up as `{something}`**: it is not available for that trigger, or it is misspelled. Run `!greetings variables`.
- **The embed is missing**: check the template still exists with `!embed list`.
- **A boost message did not appear**: it only fires when someone starts boosting, not when they add more boosts.
