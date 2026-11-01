---
title: Music App
description: A full music app that runs inside Discord, with search, playlists, a queue and a Listening status.
order: 51
group: Fun
---

## How it works

The Music App is an **Activity**: a music player that opens inside Discord itself, like a built-in app. You can use it in servers, in voice channels and in DMs. Audio plays on **your own device**, so it does not use the bot's voice connection and it does not need you to be in a voice channel.

While a song plays, your Discord profile shows **Listening to** the song name and artist, with the cover art and a progress bar, like Spotify. When you pause or close the app, the status goes away.

Your liked songs, playlists and history belong to your Discord account, so they are the same everywhere you open the app.

## Opening it

Run `!musicapp` and press **Open Music**. Aliases: `!activity`, `!player`, `!webplayer`.

You can also open the App Launcher in a voice channel, a text channel or a DM and pick Soward there.

## What you can do

| Area | What it does |
| --- | --- |
| Home | Recommended songs. The more you listen and like, the more it picks songs by artists you play. |
| Search | Type a song or artist and press Enter. |
| Player | Play, pause, previous, next, shuffle, repeat (off, all, one), seek and volume. |
| Queue | Add songs to the queue or play them next from the **⋯** menu. Click a song to jump to it, or remove it. |
| Liked songs | Press the heart on any song. Up to 1000 songs. |
| Playlists | Create playlists, add songs from the **⋯** menu, rename, delete or play them. Up to 20 playlists with 300 songs each. |
| History | The last 100 songs you played. You can clear it. |
| Settings | Your profile, volume and clearing your history. |

Keyboard: **Space** plays or pauses, **Shift + Right** is next and **Shift + Left** is previous.

## Good to know

- The first song needs a moment to start because it has to be found and prepared.
- Songs longer than 30 minutes and live streams are hidden from search.
- A song that cannot be played is skipped with a notice.
- The app asks Discord for permission to know who you are and to show your Listening status. It does not read your servers or messages.
- If the app says it is not set up, the bot owner has not turned it on yet.

## Troubleshooting

- **"Open this inside Discord."** The page only works as an Activity. Use `!musicapp` or the App Launcher.
- **No sound.** Check the volume slider in the app and the volume of Discord on your device. Press play once, because some devices need a tap before audio can start.
- **No Listening status.** The status only shows while a song is playing. Make sure Activity Status is on in Discord under Settings, then Activity Privacy.
- **"Could not start."** Close the Activity and open it again.

## SoundCloud

Use the YouTube and SoundCloud buttons above search results to choose where to search. If YouTube cannot play a song, the app tries a matching SoundCloud version and tells you when it does.
