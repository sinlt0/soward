---
title: Lofi and 24/7
description: Stream radio around the clock, keep the bot in voice, and add your own stations.
order: 51
group: Fun
---

## What this is

Soward can stream a radio station in a voice channel all day, every day. This is called **lofi radio**. It is separate from normal music: nobody has to queue songs, and it restarts itself if the stream drops or the bot restarts.

**24/7 mode** is different. It keeps the bot sitting in a voice channel after the music queue ends, so it does not leave. It does not play anything by itself.

You can set up both from commands or from the web dashboard.

## Quick start

```
!lofi setup
```

The bot asks which voice channel to use (mention it or type its name, you have 60 seconds), then shows a dropdown of stations. Pick one and it starts.

Or in one command:

```
!lofi 247 #lofi-room
```

This starts the currently selected station (Groove Salad by default) in that channel.

## Lofi commands

All of these need **Manage Server**. You can also use a fake permission granted with `!fakeperm`. Administrators and the bot's owners are always allowed.

| Command | What it does | Needs |
| --- | --- | --- |
| `!lofi` | Shows whether lofi is active, the channel and the station. | Manage Server |
| `!lofi 247 <voice channel>` | Starts lofi in a voice channel with the current station. | Manage Server |
| `!lofi setup` | Guided setup: asks for the channel, then a station. | Manage Server |
| `!lofi channel <voice channel>` | Moves a running lofi stream to another voice channel. | Manage Server |
| `!lofi radio` | Opens a dropdown to change the station, including custom stations. If lofi is running it switches right away. | Manage Server |
| `!lofi volume <0-100>` | Sets the stream volume. Lofi must be playing. | Manage Server |
| `!lofi nowplaying` | Shows the station and stream address currently playing. | Manage Server |
| `!lofi disable` | Stops lofi and leaves the voice channel. | Manage Server |

The setup and station dropdowns can only be used by the person who opened them, and they expire after 2 minutes.

## Built-in stations

These come from SomaFM and work in every server. The key is what you use in the dashboard and in station commands.

| Key | Name |
| --- | --- |
| `groove_salad` | Groove Salad (default) |
| `drone_zone` | Drone Zone |
| `lush` | Lush |
| `digitalis` | Digitalis |
| `fluid` | Fluid |
| `gsclassic` | Groove Salad Classic |
| `deepspace` | Deep Space One |
| `defcon` | DEF CON Radio |

`!lofi setup` offers only the built-in stations. To pick a custom station, use `!lofi radio` or the dashboard.

## Custom stations

You can add your own stream URLs, for example an internet radio stream. Each server can have up to **20** custom stations.

```
!lofi station add chill Chill Vibes | https://stream.example.com/chill
!lofi station test chill
!lofi radio
!lofi station remove chill
```

| Command | What it does | Needs |
| --- | --- | --- |
| `!lofi station` | Lists this server's custom stations. | Manage Server |
| `!lofi station add <key> <name> \| <stream url>` | Adds a station. The `\|` separates the name from the URL. | Manage Server |
| `!lofi station remove <key>` | Removes a custom station. Alias: `!lofi station del`. | Manage Server |
| `!lofi station test <key>` | Plays the station in your current voice channel so you can check it works. Stop it with `!lofi disable` or `!stop`. | Manage Server, you in a voice channel |

Rules:

- The key is made lowercase, spaces become underscores, and it is cut to 20 characters. It must be unique in your server.
- The name is cut to 50 characters.
- Remove a station before reusing its key.
- To use a station, pick it in `!lofi radio` or the dashboard.

## 24/7 mode

| Command | What it does | Needs |
| --- | --- | --- |
| `!247` | Toggles 24/7 mode for the voice channel the bot is currently in. | Manage Server |

Start a song first so the bot is in a voice channel, then run `!247`. The bot remembers the channel and rejoins after a restart. `!stop` and `!disconnect` turn it off.

Lofi and 24/7 mode cannot share a voice connection. Using `!play` while lofi runs stops lofi, and enabling 24/7 from the dashboard asks you to stop lofi first.

## From the dashboard

Open your server in the dashboard and go to the **Music** module. You need to be able to manage the server there (see [Using the dashboard](/docs/dashboard)). There are three tables.

**Lofi radio** shows Status, Voice channel and Station.
- **Start lofi** asks for a voice channel, a station and an optional text channel. It becomes **Restart lofi** while running.
- **Change station** switches station without moving.
- **Move** picks a new voice channel and station.
- **Stop** ends the stream after you confirm.

**24/7 mode** shows Status, Voice channel and Text channel.
- **Enable 24/7** (or **Change channel**) joins a voice channel and keeps it. The text channel is optional.
- **Disable** lets the bot leave when the queue ends, after you confirm.

**Stations** lists built-in and custom stations with their key and stream address.
- **Add station** takes a key, a name and a stream URL.
- **Remove** appears on custom stations only.

Dashboard rules:

- The bot needs **Connect** and **Speak** in the voice channel you pick. Stage channels work too.
- A key can only use lowercase letters, numbers and underscores, up to 20 characters, and cannot match a built-in key.
- A stream URL must start with `http://` or `https://`, up to 500 characters.
- Station names are up to 50 characters. The limit is 20 custom stations per server.
- The dashboard cannot play songs or edit the queue. Use commands for that.

## Troubleshooting

- **"Failed to start" or "Could not connect or stream that station"**: check the bot has **Connect** and **Speak** in the channel, and that the stream URL works. If you host Soward yourself, `ffmpeg` must be installed.
- **"Unplayable" when testing a station**: the bot could not load that URL. Try a direct audio stream link.
- **Lofi stopped by itself**: the bot checks every 30 seconds and restarts the stream if it dropped, as long as lofi is still enabled.
- **Lofi vanished after playing a song**: normal music takes over the voice connection. Run `!lofi 247 #channel` again.
