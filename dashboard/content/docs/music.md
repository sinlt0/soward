---
title: Music
description: Play songs and playlists in voice channels with a queue, filters and saved playlists.
order: 50
group: Fun
---

## How music works

Soward plays music in voice channels. You ask for a song with `!play`, the bot joins your voice channel, and it posts a **Now Playing** card with buttons for pause, skip, shuffle, stop, loop and autoplay. More songs go into a queue.

Playing songs and managing the queue are done with commands only. The web dashboard cannot start songs or edit the queue. It does manage [lofi radio and 24/7 mode](/docs/lofi).

There is nothing to switch on. You only need to be in a voice channel, and the bot needs **Connect** and **Speak** there. All music commands work in servers only.

## Quick start

```
!play never gonna give you up
!queue
!skip
!stop
```

1. Join a voice channel.
2. Run `!play <song name or link>`. If something is already playing, the song is added to the queue.
3. Use `!np` to bring back the Now Playing card, or `!queue` to see what is coming up.
4. Run `!stop` when you are done. It clears the queue and the bot leaves.

## Playing songs

| Command | What it does | Needs |
| --- | --- | --- |
| `!play <song or link>` | Plays a song or adds it to the queue. Playlist links add every track. Alias: `!p`. | You in a voice channel |
| `!soundcloud <song or link>` | Same as `!play`, but searches SoundCloud. Aliases: `!sc`, `!playsc`. | You in a voice channel |
| `!spotify <song or link>` | Same as `!play`, but searches Spotify. Aliases: `!sp`, `!playsp`. | You in a voice channel |
| `!playnext <song or link>` | Puts a song at the front of the queue so it plays right after the current one. If nothing is playing it starts right away. Alias: `!pn`. | You in a voice channel |
| `!search <query>` | Shows the top 5 results in a dropdown. Pick one to play or queue it. The dropdown expires after 60 seconds. | You in a voice channel |

If you ask for a song while the bot is in a different voice channel, it asks you to join its channel instead.

### Sources

The bot searches **YouTube** (via YouTube Music) by default. A link always works as given. You can also force a source for one search by starting it with `ytsearch:`, `scsearch:` or `spsearch:`.

| Command | What it does | Needs |
| --- | --- | --- |
| `!musicsource` | Shows this server's default search source. Aliases: `!musrc`, `!defaultsource`. | Nothing |
| `!musicsource set <youtube\|soundcloud\|spotify>` | Changes the default source for `!play`, `!playnext` and `!search`. | Manage Server |

Spotify searches only work if the bot's host has Spotify support set up. If it does not, Spotify searches return no results. Use YouTube or SoundCloud instead.

## Controlling playback

| Command | What it does | Needs |
| --- | --- | --- |
| `!pause` | Pauses, or resumes if already paused. | Bot in voice |
| `!resume` | Resumes paused playback. | Bot in voice |
| `!skip [amount]` | Skips the current track. Give a number to skip that many tracks. Alias: `!s`. | Something playing |
| `!stop` | Stops playback, clears the queue, turns off 24/7 and lofi, and disconnects. | Bot in voice |
| `!disconnect` | Leaves the voice channel and turns off 24/7 and lofi. Aliases: `!dc`, `!vcleave`. | Bot in voice |
| `!volume <0-1000>` | Sets the volume. Values outside the range are clamped. Alias: `!vol`. | Bot in voice |
| `!seek <time>` | Jumps to a time in the current track. Use seconds (`90`) or `minutes:seconds` (`1:30`). | Something playing |
| `!nowplaying` | Shows the Now Playing card with progress and buttons. Alias: `!np`. | Something playing |

The Now Playing card buttons are **Pause/Resume**, **Skip**, **Shuffle**, **Stop**, a **Loop** button that cycles off, track, queue, and an **Autoplay** toggle. While a song plays, the card is refreshed about every 20 seconds.

## Queue

| Command | What it does | Needs |
| --- | --- | --- |
| `!queue` | Shows the queue, 10 tracks per page, with total length. Alias: `!q`. | Nothing |
| `!remove <position>` | Removes one track by its queue number. Alias: `!rm`. | Bot in voice |
| `!move <from> <to>` | Moves a track from one queue position to another. Alias: `!mv`. | Bot in voice |
| `!shuffle` | Shuffles the queue. | Tracks in queue |
| `!loop [off\|track\|queue]` | Sets the loop mode. Without an argument it loops the current track. | Bot in voice |
| `!autoplay` | Toggles autoplay, which adds related tracks when the queue ends. Alias: `!ap`. | Bot in voice |

The queue panel has **Prev**, **Next**, **Shuffle** and **Clear** buttons. Only the person who ran `!queue` can use them.

## Filters

Filters change how the current music sounds. Play something first, then use them.

```
!filter
!filter nightcore
!clearfilter
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!filter` | Opens a dropdown of filters. Only you can use it, and it closes after 2 minutes. Alias: `!fx`. | Something playing |
| `!filter <name>` | Applies a filter directly. | Something playing |
| `!clearfilter` | Removes all filters. Alias: `!nofx`. | Bot in voice |

Available filters:

| Name | Effect |
| --- | --- |
| `bassboost` | Heavy low-end boost |
| `nightcore` | Sped up with a higher pitch |
| `slowed` | Slowed down with a reverb feel |
| `vaporwave` | Slowed down and nostalgic |
| `8d` | Rotating stereo panning |
| `karaoke` | Removes vocals |
| `clear` | Removes all filters (dropdown and `!filter clear`) |

Applying a filter replaces the previous one. Filters do not stack.

## Saved playlists

Playlists belong to you, not to the server, and you can load them in any server.

```
!playlist save road trip
!playlist load road trip
!playlist view road trip
!playlist delete road trip
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!playlist` | Lists your saved playlists with their track counts. Alias: `!pl`. | Nothing |
| `!playlist save <name>` | Saves the current track and the queue as a playlist. | Something playing or queued |
| `!playlist load <name>` | Adds a saved playlist to the queue and starts it if nothing is playing. | You in a voice channel |
| `!playlist view <name>` | Shows the first 20 tracks. | Nothing |
| `!playlist delete <name>` | Deletes a playlist. Alias: `!playlist del`. | Nothing |

Names are not case sensitive.

## 24/7 mode

| Command | What it does | Needs |
| --- | --- | --- |
| `!247` | Toggles 24/7 mode. The bot stays in voice when the queue ends instead of leaving. Run again to turn off. | Manage Server |

The bot must already be in a voice channel, so start a song first. It remembers the channel and rejoins after a restart. `!stop` and `!disconnect` also turn it off. See [lofi and 24/7](/docs/lofi) for the dashboard controls.

## Limits and defaults

- Volume: 0 to 1000.
- Queue pages show 10 tracks.
- `!search` shows 5 results.
- Saved playlists: up to 25 per user, names up to 50 characters.
- Loading a saved playlist adds at most 200 tracks.
- `!playlist view` shows the first 20 tracks.
- Default loop mode for `!loop` is `track`.
- Default search source is YouTube.
- Without 24/7 mode, the bot disconnects when it has been idle.

## Who can use what

Most music commands have no permission requirement. Anyone can run them, and the playback buttons are open to everyone who can see the card. Only these need **Manage Server** (or a fake permission granted with `!fakeperm`, see [moderation](/docs/moderation)): `!musicsource set`, `!247` and every `!lofi` command. Administrators and the bot's owners are always allowed.

## Troubleshooting

- **"Not in voice"**: join a voice channel first.
- **"Wrong channel"**: the bot is already in another voice channel. Join it or disconnect the bot with `!disconnect`.
- **"Connection failed"**: check that the bot has **Connect** and **Speak** in your voice channel.
- **"No results"**: try different words or paste a link. For Spotify, see the note under Sources.
- **Starting a song while lofi is on**: the lofi stream stops and the bot switches to normal music.
- **Nothing plays at all**: music runs through a separate audio server called Lavalink. If you host Soward yourself, make sure Lavalink 4 or newer is running and its password matches your bot settings.
