---
title: Server Templates
description: Build a full server from a preset, or save your own server as a template, with roles, channels, self roles, levels and Soward settings.
order: 22
group: Security
---

## What templates do

A template is a saved layout of a whole server: roles, categories, channels, permissions, rules, self role panels and Soward's own settings. You can build a new server from one in a single command.

```
!template presets
!template preview community
!template apply community
```

`!tpl` and `!servertemplate` work too. Anyone can browse and preview. Applying and publishing need the **server owner or an Extra Owner**, and Soward needs Manage Roles, Manage Channels and Manage Webhooks.

## Built-in presets

| Preset | For |
|---|---|
| `community` | A friendly general server with levels, events, voice and staff tools |
| `gaming` | Game chats, LFG, tournaments, streaming, and game and platform roles |
| `support` | Help desk with a ticket panel, FAQ, help forum, status and feedback |
| `dating` | Adults-only social server with strict security, captcha verification and safety reports |
| `datingv2` | **Premium.** A bigger adults-only server with Verified Girl, Guy and Non-Binary roles, a verification ticket, seven ticket panels, gender lounges, matchmaking and 14 self role panels |
| `study` | Subject channels, focus rooms, daily goals and study level roles |
| `creator` | Fan hub with live and video alert channels and a supporter lounge |

Every preset includes:

- **Staff roles** (Admin, Moderator, Helper), a member role, bot role and booster role.
- **Level roles** at levels 5, 10, 20, 35 and 50 with leveling switched on.
- **Ping roles** for announcements, events, giveaways and more, as buttons.
- **Colour and pronoun roles** as a select menu and reactions.
- A **verify** channel with Soward's verification panel, a **rules** channel with the rules posted, and a self roles channel.
- **Greetings**: a welcome embed on join, a leave message (off by default) and a thank-you message for boosts.
- A **ticket panel** with a private help desk, a transcripts channel and intake questions: Support, Safety Report (dating), Tutor Help (study) or Business Inquiry (creator).
- Log channels and a security preset.
- Staff-only channels and voice channels with sensible permissions.

Role panels, rules and welcome text are Soward embeds that you can edit afterwards. Their names start with `tpl-`, for example `tpl-rules`. See [Embeds](/docs/embeds).

## Dating v2 (Premium)

`datingv2` needs Soward Premium on the server because it goes beyond the free limits. You can preview it for free with `!template preview datingv2`.

- **Verification:** a private ticket where a Verifier asks for a code photo and grants **Verified Girl**, **Verified Guy** or **Verified Non-Binary**. Verified members unlock the matching lounge and voice room.
- **Seven ticket panels:** Verification, Support, Safety Report, Ban Appeal, Partnership, VIP Request and Profile Review, each with intake questions. Verification tickets and their log are visible to staff only.
- **Staff roles:** Admin, Head Moderator, Moderator, Verifier and Helper.
- **About 80 channels:** gender and verified lounges, VIP lounge, matchmaking (profile format, friend finder, profile cards), hobbies, games, six regions, date rooms for two, game and movie night, a speed dating stage, and safety, appeals and staff areas.
- **14 self role panels:** age confirmation, pings, status, looking for, DM preferences, age range, identity, orientation, pronouns, region, languages, interests, zodiac and name colours.
- **Join to Create**: a hub voice channel that gives every member their own temporary room, see [Join to Create](/docs/join-to-create).
- **Booster Perks**: Rich (1 boost) and Wealthy (2 boosts) tier roles with an XP bonus, a Booster role, and custom booster roles placed below the Booster role, see [Booster Perks](/docs/booster). Members cannot change display or permissions on their custom roles.
- **Eight level roles** from Friendly to Legend, strict security and captcha verification.

Soward never asks for ID. The verification flow uses a code photo that stays inside the private ticket.

## Applying a template

```
!template apply <preset or code> [roles] [channels] [settings] [content]
```

Leave the parts out to apply everything. Soward shows what will be added and waits for **Confirm**.

- **roles**: creates the roles.
- **channels**: creates categories and channels with their permissions.
- **settings**: leveling, greetings, security, log channels, NSFW, verification and other Soward settings.
- **content**: embeds, rules messages, self role panels and ticket panels. Greetings use the `tpl-welcome` embed, so apply `content` together with `settings`.

By default nothing is deleted. Roles, categories and channels with the same name are reused. Settings in the template replace your current values for those settings. Discord limits (250 roles, 500 channels) are respected, and anything skipped is listed when it finishes.

## Clean mode

```
!template apply community clean
!template apply community channels clean
```

`clean` removes the old channels, categories and roles that are not in the template, so the server ends up matching it. It deletes channels only when `channels` is applied and roles only when `roles` is applied.

- Soward shows how many channels and roles will go and asks you to confirm.
- A backup is taken first. Undo with `!backup restore <id>`. Restoring brings back the structure, not the messages.
- Kept: log channels, open tickets, the rules and updates channels, Soward's quarantine role, bot roles, and roles above Soward's top role.
- The channel you ran the command in is deleted last, and the result is posted in a new channel.
- Messages in deleted channels are gone for good.

## Full clean

```
!template apply community fullclean
```

For a complete reset, `fullclean` kicks every bot except Soward, deletes **every** channel and category and every role Soward can delete (including the old quarantine role), clears the saved log channels and panels that pointed at them, then rebuilds the whole server from the template. It always includes a fresh **Quarantined** role that is hidden from every channel and linked to AntiNuke.

- Only the **server owner** can run it, and it asks for confirmation with the exact numbers.
- A backup is taken first. Undo with `!backup restore <id>`.
- Every member loses their roles, so everyone has to verify again and pick roles again. Messages and open tickets in deleted channels are gone.
- Discord does not allow deleting the rules and updates channels of a Community server, so those stay. Roles above Soward and integration roles stay too.

The Quarantined role is also created by a normal apply when the `roles` part is included and your server has none.

## Saving your own server

```
!template publish My Server
!template update <code>
!template describe <code> <text>
!template visibility <code> <private|unlisted|public>
!template export <code>
!template delete <code>
!template list
```

`publish` saves roles, categories, channels and permission overwrites, plus Soward settings: leveling (rewards, multipliers, no-XP lists), greetings, log channels, security settings, whitelist (roles and channels), AntiNuke punishments, NSFW role and channels, ticket settings, anime daily config, embeds, posted self role panels and posted ticket panels (staff roles, category, transcript channel, button label, intake questions).

Join to Create hubs and Booster Perks settings are saved too. Not saved: custom commands, giveaways, alerts, open tickets and transcripts, warnings, XP and any member data. Members, bans and messages never leave your server.

A new template is **private**. `unlisted` lets anyone with the code use it, and `public` also lists it in `!template browse`. You can keep 5 templates.

## Safety

When you apply someone else's template, Soward removes dangerous permissions from its roles and skips the tier lock and AntiNuke administrator bypass, so a template cannot weaken your security. IDs from another server are never copied.

## Limits to know about

- Templates cap at 150 roles and 200 channels.
- Role order is best effort. Check that Soward's role is above the roles it created.
- Verification panels and role panels are posted new. Run the command once, not repeatedly.
