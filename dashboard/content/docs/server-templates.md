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
| `datingv2` | **Premium.** The full 18+ dating blueprint: gate and fam roles, staff ladder, 90 styled channels, six ticket panels with a private safety desk, verified badges, DM center, partners and level perks |
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

`datingv2` follows the Dating Server Blueprint. It needs Soward Premium on the server because it goes beyond the free limits. You can preview it for free with `!template preview datingv2`.

- **Style:** categories look like `˚₊ lounge ₊˚`, and channels and roles look like `♡﹒general﹒˚₊☁️𓂃﹗`, each with its own emoji. Embed titles use a bold font.
- **Gate:** members get **unverified** on join and can only see verify, rules and announcements. After verification they lose it and get **fam**, the main member role. The quarantine role from the template is used as Soward's quarantine role, with no permissions, and every channel and category denies it all permissions. The unverified and muted roles are linked to Soward's verification and quarantine settings.
- **@everyone has no permissions.** Fam carries the real permissions. Embed links unlock at level 5 and attach files at level 10. Fam gets attach files inside the support, verification, report and safety ticket categories.
- **Staff ladder:** founders, owner, co-owner, quarantine, admin, manager, assistant manager, moderator, trial mod, partnership managers, ticket team, event hosts and staff, each with the permissions from the blueprint.
- **Roles in blueprint order:** staff, ten colour roles (two booster-only), wealthy, rich, partner rep, couples, birthday, six level roles, verified girl, boy and nonbinary, fam, unverified, muted, then the self roles.
- **Rules and self roles use custom commands.** The rules channel has a rules panel with a dropdown (chat, DM, voice, safety and other rules). The roles channel has one CUSTOMIZE panel with a Personization Options dropdown. Each choice opens a private panel with its own banner image and dropdown for DM status, looking for, relationship status, pronouns, orientation, age range, region, pings and name colours. All of it is made with `!cc` commands you can edit afterwards, such as `!cc menu edit sr-dm 1 ...`.
- **Self role details:** pick-one groups swap the old role, and the rest toggle. The two booster colours have their own panel in the custom role requests channel.
- **90 channels in 21 categories:** start here, meet, dm center, lounge, interests, couples, events, activities, voice, partners, boosters and levels, help desk, six opened-ticket categories, ticket transcripts, logs and staff.
- **Six ticket panels:** support, verified badge, report, safety desk, partnership and staff applications. Each opens tickets in its own category with its own staff. Safety tickets are visible to assistant managers and up only and write to a private safety-transcripts channel.
- **Logs:** Soward's five log categories (moderation, messages, member activity, security and server changes) in styled channels. Soward has no separate voice log category.
- **Join to Create**, see [Join to Create](/docs/join-to-create), and **Booster Perks**, see [Booster Perks](/docs/booster). Rich is 1 boost and wealthy is 2 boosts. Booster-only channels use those two tier roles, and custom booster roles are placed below Discord's Server Booster role.
- **Level roles** at 5, 10, 20, 30, 50 and 75 with display on.

Applying this preset turns off every @everyone permission, so existing members need the fam role. Soward warns you before you confirm. Age verification is left to your own setup. Soward never asks for ID, and badge proof stays inside the private ticket.

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

### Stopping and resuming

- `!template cancel` stops a running apply right away. Everything already built stays.
- `!template status` shows what has been created so far.
- If Discord rate limits the server and stops answering, Soward gives up after three calls in a row time out and tells you, instead of hanging. Wait a few minutes and run `!template apply` again. Roles and channels that already exist are reused, so it continues where it stopped.

### Role order

Template roles are placed in one block under Soward's role, top to bottom: staff, bots, main member roles (such as Fam and the verified roles), booster and VIP roles, level roles, then colour and self roles. Keep Soward's role at the top of your role list so it can order them.

## Staff review commands in Dating v2

Dating v2 adds two custom commands so staff do not have to write review posts by hand.

- `!rq <summary>` works only in review-queue and only for the ticket team, moderators and managers. It posts a "Review Request" embed with a dropdown: Claim, Approve, Warn, Mute, Ban, Need more info, Done and Escalate. Each pick is logged in the channel with the staff member and a link to the request, so the next person on shift can see what is pending and what was decided. The member never sees it. Escalate also posts a link in safety-review.
- `!safecase <summary>` works only in safety-review and only for assistant managers and managers. Its dropdown has Claim, Need more evidence, Warn, Ban, Quarantine, Report to Discord, Follow up with reporter and Close with result. Decisions stay in safety-review and are never copied to review-queue.

The dropdown records decisions only. It does not run the ban or warning for you, so use the normal moderation commands for the action itself. Inside template custom command text, `{{channel:key}}` is replaced with the matching channel of the template.

## Custom commands in templates

Templates can carry [custom commands](/docs/custom-commands), including their dropdown menus, cooldowns and role or channel restrictions. They are created in the **content** part. Commands that already exist are never overwritten, and a template can post a command's message (for example a rules panel) into a channel. Usage counts are not saved. When you apply another server's template, only safe commands are added: plain triggers that use role toggles and embed tags, never bans, kicks or channel actions.

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

Join to Create hubs and Booster Perks settings are saved too. Not saved: giveaways, alerts, open tickets and transcripts, warnings, XP and any member data. Members, bans and messages never leave your server.

A new template is **private**. `unlisted` lets anyone with the code use it, and `public` also lists it in `!template browse`. You can keep 5 templates.

## Safety

When you apply someone else's template, Soward removes dangerous permissions from its roles and skips the tier lock and AntiNuke administrator bypass, so a template cannot weaken your security. IDs from another server are never copied.

## Limits to know about

- Templates cap at 150 roles and 200 channels.
- Role order is best effort. Check that Soward's role is above the roles it created.
- Verification panels and role panels are posted new. Run the command once, not repeatedly.
