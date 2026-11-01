---
title: Alerts
description: Post YouTube uploads and livestreams and Twitch go-live notices in a channel.
order: 42
group: Community
---

## How alerts work

An alert is a **subscription**: one YouTube channel or one Twitch streamer, tied to the channel where the bot posts. YouTube channels are announced within seconds of a new upload when instant notifications are active, and every subscription also has a polling fallback. Twitch streamers are checked every 2 minutes.

| Platform | The bot posts when |
| --- | --- |
| YouTube | The channel's newest video changes. If that video is a live broadcast it is a **live** alert, otherwise an **upload** alert. |
| Twitch | The streamer goes from offline to live. |

Notes:

- When you subscribe to a YouTube channel, its current newest video is remembered and does not trigger an alert. Only videos posted after that do.
- When you subscribe to a Twitch streamer who is already live, the bot announces the stream at its next check.
- With instant notifications every new upload is announced on its own. In polling mode a check looks at the newest YouTube video only, so two videos posted between checks announce only the newest.
- Scheduled livestreams and premieres are announced when they actually go live, not when they are scheduled.
- Videos that were published more than 12 hours before the notification arrived (for example an old video whose title was edited) are not announced.
- The same video or stream is never announced twice for one subscription.
- YouTube and Twitch alerts only work if that service is set up on this bot. If it is not, adding a subscription tells you so.

Every alert command needs **Manage Server** (or the matching fake permission, see [moderation](/docs/moderation)), except `alerts variables`, which anyone can use. To add a subscription from a command the bot also needs the **Embed Links** permission in your server.

## Instant YouTube notifications

When the dashboard is available, the bot subscribes to each watched YouTube channel through YouTube's push system (WebSub). YouTube then tells the bot about a new upload within seconds, which also means no YouTube API quota is spent waiting for it.

- `!alerts list` marks each YouTube subscription as **instant** or **polling**.
- A channel is on **polling** until YouTube confirms the push subscription, which normally takes a few seconds after you add it.
- Push subscriptions are renewed automatically before they expire.
- If a push is missed or the bot was offline, the **fallback check** still catches the newest video: every 15 minutes for channels on instant mode, every 2 minutes for channels still on polling.
- The same video is never announced twice, even if both paths see it.


## Quick start

```
!alerts youtube add @MrBeast #videos
!alerts twitch add shroud #live
!alerts list
!alerts role 3F9A1C2B @Subscribers
```

1. Add a subscription. The bot replies with its **subscription ID**, an 8-character code such as `3F9A1C2B`.
2. Optionally set a ping role and a custom message using that ID.
3. `!alerts list` shows every subscription and its ID at any time.

You can also run `!alerts` on its own to open an interactive menu with buttons for the variables, the list and the default messages, and a drop-down to add a YouTube or Twitch subscription step by step. The menu works for 5 minutes after you open it.

## Finding a YouTube channel

`!alerts youtube add <channel> <#channel>` accepts any of these for the channel:

- A handle starting with `@`, for example `@MrBeast`
- A channel ID that starts with `UC` and is 24 characters long
- An older-style YouTube username

## Command reference

| Command | What it does | Needs |
| --- | --- | --- |
| `!alerts` | Opens the interactive alerts menu. | Manage Server |
| `!alerts youtube add <channel> <#channel>` | Subscribes to a YouTube channel. Alias: `!alerts yt add`. | Manage Server |
| `!alerts youtube remove <ID>` | Removes a subscription by ID. | Manage Server |
| `!alerts twitch add <username> <#channel>` | Subscribes to a Twitch streamer. | Manage Server |
| `!alerts twitch remove <ID>` | Removes a subscription by ID. | Manage Server |
| `!alerts list` | Lists all subscriptions with their IDs, platforms and channels. | Manage Server |
| `!alerts role <ID> [role]` | Sets the role to mention for this subscription. Run it without a role to stop pinging. | Manage Server |
| `!alerts message <ID> <text>` | Sets a custom message for this subscription and shows a preview. | Manage Server |
| `!alerts toggle <ID> <live\|upload>` | Turns live alerts or upload alerts on or off for this subscription. Each run flips the current state. | Manage Server |
| `!alerts variables` | Shows the placeholders for each platform. Alias: `!alerts vars`. | Anyone |
| `!alerts clear` | Removes every subscription in the server, after you confirm. | Manage Server |

`!alerts youtube` and `!alerts twitch` on their own only show a short usage hint. The `remove` commands for both platforms work with any subscription ID.

## Messages and placeholders

Each alert posts a card with the title, a link and a thumbnail. When a subscription has a ping role or a custom message, the message text is posted as its own message just before the card, with the role mentioned first. If the alert could not be posted, the bot tries again on the next check. `!alerts variables` needs Manage Server.

Default messages:

- YouTube: `**{channel_name}** just posted a new {kind}!` then the title and link.
- Twitch: `**{streamer_name}** just went live!` then the title, the game and the link.

Placeholders, written in curly braces:

| Placeholder | Platform | Output |
| --- | --- | --- |
| `{channel_name}` | YouTube | The channel's display name. |
| `{channel_url}` | YouTube | Link to the channel. |
| `{video_title}` | YouTube | Title of the new video or livestream. |
| `{video_url}` | YouTube | Link to the video or livestream. |
| `{video_thumbnail}` | YouTube | Thumbnail image link. |
| `{kind}` | YouTube | `video` or `livestream`. |
| `{streamer_name}` | Twitch | The streamer's display name. |
| `{streamer_url}` | Twitch | Link to the channel. |
| `{stream_title}` | Twitch | Title of the current stream. |
| `{game_name}` | Twitch | Game or category being streamed, or `N/A`. |
| `{viewer_count}` | Twitch | Live viewer count when the alert was sent. |
| `{stream_thumbnail}` | Twitch | Thumbnail image link. |

Example:

```
!alerts message 3F9A1C2B New {kind} from {channel_name}: {video_title} {video_url}
```

- A custom message is per subscription. Subscriptions without one use the default message for their platform.
- The default message for a platform is changed from the menu: run `!alerts`, press **Edit Default Message**, pick the platform and edit the text (up to 1500 characters).
- There is no command to clear a custom message. Clear it from the dashboard by leaving the message empty.
- Only the placeholders for the subscription's own platform are filled in.

## Live and upload switches

Every subscription has two switches, both on by default.

- `live` controls livestream alerts for YouTube and go-live alerts for Twitch.
- `upload` controls normal video uploads. It only matters for YouTube. Twitch subscriptions have no uploads.

```
!alerts toggle 3F9A1C2B upload
```

## Limits

| Limit | Free | Premium |
| --- | --- | --- |
| YouTube subscriptions per server | 5 | 15 |
| Twitch subscriptions per server | 5 | 15 |

| Limit | Value |
| --- | --- |
| Same channel twice in one server | Not allowed |
| Check interval | Every 2 minutes |
| Custom message (dashboard) | 1000 characters |
| Default message (menu) | 1500 characters |

Premium raises the subscription limit only.

## From the dashboard

Open your server, then **Alerts**. The **Subscriptions** table lists each subscription with its platform, name, channel and ping role.

- **Add subscription.** Pick the platform, enter the YouTube handle or ID or the Twitch username, and choose the announcement channel. The same limits and checks as the command apply.
- **Edit.** Change the announcement channel, ping role, custom message (leave empty for the default), the live switch and, for YouTube, the upload switch.
- **Remove.** Stops alerts for that subscription.

Still needs the menu or commands: editing the default message for a platform, `!alerts variables` and `!alerts clear`. See [using the dashboard](/docs/dashboard) for how to sign in.

## Troubleshooting

- **"Could not find a YouTube channel."** Check the handle or ID. The `@` is needed for handles, and channel IDs start with `UC`.
- **"Limit Reached."** The server is at its subscription limit for that platform (5, or 15 with Premium). Remove one with `!alerts youtube remove <ID>` or `!alerts twitch remove <ID>`.
- **Nothing is posted.** Make sure the bot can see and send messages in the announcement channel, that the right switch (`live` or `upload`) is on, and remember checks run every 2 minutes. The announcement channel must still exist.
- **Old video was not announced.** Only videos posted after you subscribed are announced.
