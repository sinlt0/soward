---
title: Auto Partner
description: Ticket-style partnerships where partners post your ad, send a screenshot and get posted automatically.
order: 66
group: Community
---

## How it works

A partner opens a private ticket from a button panel. In the ticket they:

1. Post your server's ad in their own server.
2. Send **their** ad in the ticket. It must contain a server invite that never expires.
3. Send a screenshot that shows your ad posted in their server.

Zyro reads the screenshot and checks that most of your ad's text and your invite are visible. When it passes, the partner's ad is posted in your partner channel and the ticket closes by itself.

## Setting it up

You need Manage Server.

| Command | What it does |
| --- | --- |
| `!autopartner ad <text>` | Your server's ad. It must contain your invite |
| `!autopartner channel <#channel>` | Where partner ads are posted |
| `!autopartner category <category>` | Where partner tickets are created (optional) |
| `!autopartner staff <@role>` | A role that can see and approve tickets (optional) |
| `!autopartner ping <@role>` | A role pinged on every new partner post (optional) |
| `!autopartner log <#channel>` | Logs opened tickets and posted partners (optional) |
| `!autopartner minmembers <number>` | Smallest server you accept, from the invite's member count |
| `!autopartner panel [#channel]` | Posts the button partners click |
| `!autopartner enable` / `disable` | Opens or closes new tickets |
| `!autopartner status` | Shows the setup and whether screenshot reading is ready |

## Ad format

Ads are posted exactly as the partner wrote them, as a normal message, so image and gif links, invite previews, masked links like `[name](https://discord.gg/code)`, subtext, spoilers and blank-line tricks all keep working. An ad can be up to 2000 characters.

If the ad contains `[Your Partnership ping]` (also `[partnership ping]` or `[ping]`), it is replaced with your ping role. If it does not and you set a ping role, the role is added at the end. Pings written inside the ad, such as `@everyone`, never ping anyone.

Files uploaded with the ad are not copied, so use links. Links to Discord attachments can expire on Discord's side.

For ads that are only links and pictures, the screenshot check relies on your invite code or your server name being visible.

## Managing partners

`!autopartner list` shows recent partner posts with their IDs, and `!autopartner remove <id>` deletes a post.

## Rules the bot enforces

- One open ticket per person.
- The partner's invite must be valid, never expire, and belong to a different server.
- Each person gets 3 tries for the screenshot. After that a staff member can press **Approve** in the ticket.
- The exact same screenshot cannot be used twice.
- A server that was posted in the last 7 days cannot be posted again.
- Tickets that sit open for 24 hours are removed.
- `@everyone`, `@here` and other pings inside an ad never ping anyone. Only your ping role does.

## Good to know

Screenshot reading is automatic text recognition, so it can be fooled by an image that only contains the ad text, and it can miss a very small or blurry screenshot. Staff approval is there for those cases, and you can check the `!autopartner list` posts at any time.
