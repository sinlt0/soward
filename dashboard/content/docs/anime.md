---
title: Anime and Manga
description: Look up anime and manga, get recommendations and post a daily pick.
order: 53
group: Fun
---

## How it works

The anime commands search AniList and show a card with the cover, a short description, score, status, episodes or chapters, year and genres, plus a **View on AniList** button. You can also set up a **daily recommendation** that the bot posts in a channel of your choice.

Search and discovery commands work for everyone. Only the daily recommendation setup needs permissions.

## Quick start

```
!animesearch Cowboy Bebop
!mangasearch Berserk
!animerandom Comedy
!trending
```

To get a daily pick:

```
!animedaily channel #anime
!animedaily enable
```

## Search and discover

| Command | What it does | Needs |
| --- | --- | --- |
| `!animesearch <title> [nsfw]` | Shows the best match for an anime title. Alias: `!as`. | Nothing |
| `!mangasearch <title> [nsfw]` | Shows the best match for a manga or manhwa title. Alias: `!ms`. | Nothing |
| `!animerecommend <title> [nsfw]` | Finds the anime you named, then shows one anime that AniList recommends for fans of it. Alias: `!arec`. | Nothing |
| `!animerandom [genre] [nsfw]` | Shows a random anime, optionally from one genre. Aliases: `!arandom`, `!randomanime`. | Nothing |
| `!mangarandom [genre] [nsfw]` | Shows a random manga or manhwa, optionally from one genre. Aliases: `!mrandom`, `!randommanga`. | Nothing |
| `!trending` | Lists the 5 most trending anime right now with their scores. | Nothing |

Random picks come from the 300 most popular titles that match (all of them, if fewer match).

### Genres

For `!animerandom`, `!mangarandom` and the daily recommendation, the genre must be one of:

Action, Adventure, Comedy, Drama, Ecchi, Fantasy, Horror, Mahou Shoujo, Mecha, Music, Mystery, Psychological, Romance, Sci-Fi, Slice of Life, Sports, Supernatural, Thriller.

Genre names are not case sensitive. An unknown genre shows the full list.

### Adult content

Results hide adult (18+) titles by default. To include them, add the word `nsfw` at the end of the command, for example `!animesearch some title nsfw`. This only works in an [NSFW channel](/docs/nsfw) set up with `!nsfw addchannel`, with the NSFW role set. In other channels the bot refuses.

## Daily recommendation

The bot can post one anime or manga pick per day in a channel. It avoids repeating any of the last 20 picks it posted in your server.

```
!animedaily channel #anime
!animedaily type manga
!animedaily genre Fantasy
!animedaily time 14:30
!animedaily role @Anime
!animedaily enable
```

All `!animedaily` commands need **Manage Server** (or a fake permission granted with `!fakeperm`, see [moderation](/docs/moderation)) and work in servers only. Administrators and the bot's owners are always allowed.

| Command | What it does | Needs |
| --- | --- | --- |
| `!animedaily` | Shows the current settings, or setup hints if it is off. | Manage Server |
| `!animedaily channel <channel>` | Sets the text channel for the daily post. | Manage Server |
| `!animedaily enable` | Turns the daily post on. A channel must be set first. | Manage Server |
| `!animedaily disable` | Turns the daily post off. | Manage Server |
| `!animedaily type <anime\|manga>` | Chooses anime or manga. | Manage Server |
| `!animedaily genre <genre>` | Limits picks to one genre. Use `any` to clear it. | Manage Server |
| `!animedaily time <HH:MM or HH>` | Sets the post time in UTC, for example `9:40` or `14`. | Manage Server |
| `!animedaily role [role]` | Sets a role to ping with each post. Run without a role to clear it. | Manage Server |
| `!animedaily nsfw` | Toggles adult content in the daily post. The channel must be a registered NSFW channel. | Manage Server |

### Daily defaults and timing

- Type: anime.
- Genre: any.
- Post time: 12:00 UTC.
- Ping role: none.
- Adult content: off. It is also skipped whenever the channel is not a registered NSFW channel.
- The bot checks every 15 minutes, so a post can arrive up to about 15 minutes after the set time.
- It posts at most once per UTC day. If you enable it after the set time has already passed, the first post comes soon, within about 15 minutes.
- Times are always UTC. Convert from your own time zone.

## Limits and cooldowns

- `!animesearch` and `!mangasearch`: 3 seconds per person.
- `!animerecommend`, `!animerandom`, `!mangarandom` and `!trending`: 4 seconds per person.
- Descriptions are cut to 400 characters.
- Search shows only the top match, and recommendations show only one title.

## Troubleshooting

- **"Not Found"**: AniList had no match. Try the English or romaji title.
- **"Can't Do That"**: you asked for `nsfw` outside an NSFW channel.
- **"No Results"**: AniList did not answer or had nothing for that genre. Try again shortly.
- **"No Recommendations"**: AniList has no recommendations for that title yet.
- **"No Channel Set"**: run `!animedaily channel #channel` before `enable` or `nsfw`.
- **Daily post does not appear**: check that it is enabled, and that the bot can send messages in the channel.
