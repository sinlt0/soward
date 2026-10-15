---
title: Social and Reactions
description: Hug, pat, wave and dozens of other anime GIF reactions.
order: 52
group: Fun
---

## How it works

Social commands post an anime GIF with a short line like "Alex hugs Sam!". Some need a person, some take an optional person, and some are just for you. There are 46 of them.

There is nothing to set up. Anyone can use them. Each person can run one social command every 3 seconds.

The GIFs come from several public GIF services. The bot tries them in random order and uses the first one that answers. If all of them are down you get a "No luck" message, so try again in a moment.

## Quick start

```
!hug @Sam
!wave
!wave @Sam
!sleep
```

`<member>` means you mention someone, or give their name or ID. `[member]` means it is optional: with a member the GIF is aimed at them, without one it is just about you.

## With a person

These need a member.

| Command | What it does | Needs |
| --- | --- | --- |
| `!hug <member>` | Hug someone. | Nothing |
| `!kiss <member>` | Kiss someone. | Nothing |
| `!pat <member>` | Pat someone. | Nothing |
| `!cuddle <member>` | Cuddle with someone. | Nothing |
| `!snuggle <member>` | Snuggle with someone. | Nothing |
| `!handhold <member>` | Hold someone's hand. | Nothing |
| `!highfive <member>` | Give someone a high five. | Nothing |
| `!handshake <member>` | Shake hands with someone. | Nothing |
| `!feed <member>` | Feed someone. | Nothing |
| `!poke <member>` | Poke someone. | Nothing |
| `!tickle <member>` | Tickle someone. | Nothing |
| `!slap <member>` | Slap someone. | Nothing |
| `!punch <member>` | Punch someone. | Nothing |
| `!skick <member>` | Kick someone, socially. This is a joke GIF, not a real kick. | Nothing |
| `!yeet <member>` | Yeet someone. | Nothing |
| `!bite <member>` | Bite someone. | Nothing |
| `!lick <member>` | Lick someone. | Nothing |
| `!bully <member>` | Bully someone, playfully. | Nothing |
| `!stare <member>` | Stare at someone. | Nothing |
| `!glare <member>` | Glare at someone. | Nothing |
| `!shoot <member>` | Shoot someone, virtually. | Nothing |
| `!threaten <member>` | Threaten someone. | Nothing |
| `!scare <member>` | Scare someone. | Nothing |

## With or without a person

The member is optional. Without one, the GIF is just about you.

| Command | What it does | Needs |
| --- | --- | --- |
| `!wave [member]` | Wave hello. | Nothing |
| `!blush [member]` | Blush. | Nothing |
| `!smile [member]` | Smile. | Nothing |
| `!wink [member]` | Wink. | Nothing |
| `!dance [member]` | Dance, alone or with someone. | Nothing |
| `!cry [member]` | Cry, or cry on someone's shoulder. | Nothing |
| `!laugh [member]` | Laugh. | Nothing |
| `!pout [member]` | Pout. | Nothing |
| `!shrug [member]` | Shrug. | Nothing |
| `!dodge [member]` | Dodge an attack. | Nothing |
| `!hide [member]` | Hide, or hide from someone. | Nothing |
| `!scared [member]` | Show that you are scared. | Nothing |
| `!smug [member]` | Look smug. | Nothing |
| `!cringe [member]` | Cringe. | Nothing |
| `!nom [member]` | Nom nom nom. | Nothing |
| `!angry [member]` | Show that you are angry. | Nothing |
| `!disgust [member]` | Show your disgust. | Nothing |

## Just for you

These take no arguments.

| Command | What it does | Needs |
| --- | --- | --- |
| `!sleep` | Go to sleep. | Nothing |
| `!bored` | Show how bored you are. | Nothing |
| `!happy` | Show how happy you are. | Nothing |
| `!sad` | Show how sad you are. | Nothing |
| `!think` | Show that you are thinking. Alias: `!thinking`. | Nothing |
| `!confused` | Show how confused you are. | Nothing |

## Counters

When you aim a command at someone, the bot keeps count and adds a small line under the GIF, for example "They've hugged each other 3x" and "Sam has been hugged 5x". The counts are saved, and they are not reset.

Some commands share a counter with a similar one:

| Shared counter | Commands |
| --- | --- |
| kick | `!skick`, `!angry` |
| shoot | `!shoot`, `!threaten`, `!scare` |
| stare | `!stare`, `!glare`, `!disgust` |
| cuddle | `!cuddle`, `!snuggle` |
| feed | `!feed`, `!nom` |
| cry | `!cry`, `!sad` |
| think | `!think`, `!confused` |

## Limits and defaults

- Cooldown: one social command per person every 3 seconds.
- You cannot aim a command at yourself. Commands that accept a member answer "You can't ... yourself!".

## Troubleshooting

- **"No luck"**: every GIF service was unavailable. Try again in a moment.
- **The bot says it could not find the member**: mention the person, or use their exact name or ID.
- **Nothing happens**: you may be on cooldown. Wait a few seconds.
