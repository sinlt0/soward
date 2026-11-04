---
title: Lookups
description: Weather, translate, dictionary, calculator, crypto prices and local time.
order: 59
group: Utility
---

- `!weather <city>` shows the current weather and a 3 day forecast in °C and °F.
- `!translate [language] [text or message link]` translates text, with no length limit apart from Discord's own message size. Reply to a message with `!translate spanish` to translate it, or paste a message link (from a channel you can read). The language can be a name (`spanish`) or a code (`es`), defaults to English, and the source language is detected for you. In slash commands use `/utility translate` and put the link in the text box, or right click a message and pick **Apps > Translate message** to get a private translation in your Discord language.
- `!define <word>` gives definitions, examples and pronunciation for an English word.
- `!urban <term>` looks up slang. Entries are written by users and can be explicit, so it only works in age-restricted channels.
- `!calc <expression>` calculates things like `(3+4)*5`, `2^10`, `sqrt(144)` or `15% of 200`.
- `!price <coin> [currency]` shows a crypto price, for example `!price btc` or `!price eth eur`.
- `!time [user|timezone]` shows someone's local time. It uses the timezone they set with `!remind tz`, or any zone like `Asia/Dhaka`.

Lookups use free public services, so they can be slow or unavailable at times. Results are cached for a short while.
