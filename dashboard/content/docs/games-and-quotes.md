---
title: Ship, Truth or Dare and Quotes
description: Ship two members, play truth or dare, and turn messages into quote images.
order: 54
group: Fun
---

## What is here

Three small fun features, all usable by anyone and all working in servers only:

- **Ship** shows how compatible two members are, with a picture card.
- **Truth or Dare** gives random questions and dares.
- **Quote** turns a message into a styled quote image.

## Ship

```
!ship @Sam
!ship @Alex @Sam
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!ship <member>` | Ships you with that member. | Nothing |
| `!ship <member1> <member2>` | Ships two members with each other. | Nothing |

The reply shows a compatibility percentage, a row of hearts, a short comment and a card with both avatars and a heart that fills to the percentage.

How the rating works:

- Every pair gets its own base rating between 10% and 80%. It is the same for that pair every time, and the order of the two names does not matter.
- Each time the same pair is shipped again, the rating goes up by 6 points, up to a maximum of 99%. This bonus resets every 12 hours and when the bot restarts.
- About 2 in 100 pairs are a perfect 100% match. For those pairs it is always 100%.
- You cannot ship a member with themselves.
- Cooldown: one ship every 3 seconds per person.

## Truth or Dare

```
!truth
!dare pg
!tod pg13
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!truth [rating]` | Gives a random truth question. | Nothing |
| `!dare [rating]` | Gives a random dare. | Nothing |
| `!tod [rating]` | Picks truth or dare at random and gives one. Alias: `!truthordare`. | Nothing |

Ratings:

| Rating | Meaning |
| --- | --- |
| `pg` | Mild |
| `pg13` | Default when you give no rating |
| `r` | Adult. Only works in registered [NSFW channels](/docs/nsfw) |

Under each question there is an **Another one** button that replaces it with a new one of the same kind and rating. Anyone who can see the message can press it, and the "Requested by" line then shows who pressed it. The button stops working after about 2 minutes, and you can run the command again for a new one.

Cooldown: one command every 2 seconds per person. If the question service is down, the bot says it could not reach it. Try again shortly.

## Quote

Reply to any message and run the command, and the bot makes a quote image with the author's avatar, name and text.

```
!makeaquote
```

You can also reply to a message and mention the bot, without typing a command. The bot makes the same quote.

| Command | What it does | Needs |
| --- | --- | --- |
| `!makeaquote` | Turns the message you replied to into a quote image. Aliases: `!mcq`, `!quote`. | Reply to a message |
| `!quotefont [font]` | Sets your default font. Without an argument it lists the fonts. | Nothing |
| `!quotestyle [style]` | Sets your default weight: `regular`, `italic`, `bold` or `bolditalic`, where the font supports it. Without an argument it lists what your font offers. | Nothing |
| `!quotecolor [color]` | Sets your default accent color. Without an argument it lists the colors. | Nothing |
| `!quotecolorize` | Toggles whether the avatar is shown in color or grayscale by default. Alias: `!quoteavatar`. | Nothing |

These settings are yours. They follow you across servers.

### Customize from the card

Every quote card has dropdowns for **font**, **weight/style**, **accent color** and a **Colorize Avatar / Grayscale Avatar** button. Only the person who asked for the quote can use them. The card updates in place.

### Fonts

| Key | Font | Premium |
| --- | --- | --- |
| `classic` | Classic Serif (default) | No |
| `playfair` | Playfair Display | No |
| `garamond` | EB Garamond | No |
| `cormorant` | Cormorant Garamond | Yes |
| `baskerville` | Libre Baskerville | Yes |
| `typewriter` | Special Elite | Yes |
| `handwritten` | Caveat | Yes |
| `bebas` | Bebas Neue | Yes |

### Accent colors

| Key | Color | Premium |
| --- | --- | --- |
| `gray` | Classic Gray (default) | No |
| `gold` | Gold | No |
| `rose` | Rose | No |
| `sapphire` | Sapphire | Yes |
| `emerald` | Emerald | Yes |
| `violet` | Violet | Yes |

Premium fonts and colors work only in servers that have [premium](/docs/premium). In other servers a saved premium choice falls back to the default for that quote.

### Quote rules

- The default weight is italic, and the default avatar style is grayscale.
- Not every font has every weight. Typewriter has only regular, Caveat has regular and bold. The weight dropdown is disabled when a font has only one option.
- Text is cut to 400 characters. If the message has no text, the first embed's description is used, and a message with only an attachment shows "[attachment]".
- Bot messages cannot be quoted.
- Cooldown for `!makeaquote`: 4 seconds per person.

## Troubleshooting

- **"Reply Required"**: reply to the message you want to quote, then run the command.
- **"That message doesn't have any text to quote"**: the message has no text, embed text or attachment.
- **"Couldn't fetch that user's avatar"**: Discord did not return the avatar. Try again.
- **Ship shows "Can't Ship That"**: you picked the same member twice.
- **"Can't Do That" on truth or dare**: you asked for `r` outside an NSFW channel, or used a rating other than `pg`, `pg13` or `r`.

## Counting

Members count upward together in one channel. Numbers must follow in order, and nobody can count twice in a row. A wrong number or a double count resets the count to 0, adds a ❌ and tells everyone who broke it. Correct numbers get a ✅, and every 100th number is celebrated.

| Command | What it does | Needs |
| --- | --- | --- |
| `!counting` | Shows the status, current number and record. | Anyone |
| `!counting top` | Shows the best counters. | Anyone |
| `!counting channel #channel` | Sets the counting channel. | Manage Server |
| `!counting toggle` | Turns counting on or off. | Manage Server |
| `!counting set <number>` | Sets the current number. | Manage Server |
| `!counting reset` | Resets the count to 0. | Manage Server |

## Wordle

Everyone in a server gets the same word each day, and a new word starts at 00:00 UTC. Use `!wordle` to post the game, then press **Play** and type a 5 letter guess. Your board is private. When you finish, a spoiler free result is posted in the channel.

- `!wordle stats [member]` shows played games, wins and streaks.
- `!wordle top` shows the server leaderboard.

Any five letters count as a guess, so the game does not check a dictionary.

## Icebreakers

| Command | What it does |
| --- | --- |
| `!wyr` | A would you rather with 🅰️ and 🅱️ reactions. |
| `!nhie` | A never have I ever prompt. |
| `!rizz [member]` | A cheesy pickup line, optionally aimed at someone. |
| `!icebreaker` | A conversation starter. Aliases: `!question`, `!ice`. |

## Daily question

Soward can post a new question every day without repeating one until all have been used.

- `!daily channel #channel` sets the channel.
- `!daily time <HH:MM>` and `!daily offset <hours>` set when it posts, for example `09:00` and `6`.
- `!daily role @role` pings a role with each question. Run it without a role to remove the ping.
- `!daily toggle` turns it on or off and `!daily now` posts one immediately.
