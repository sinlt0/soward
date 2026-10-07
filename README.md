<div align="center">

# Soward

A modular, prefix-based Discord bot with a built-in security stack, moderation,
music, leveling, giveaways, custom commands and more.

Built by **Sinlt (辛特)** and the **Soward Team**.

[![CI](https://github.com/sinlt0/soward/actions/workflows/ci.yml/badge.svg)](https://github.com/sinlt0/soward/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](./LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)
![discord.py 2.7+](https://img.shields.io/badge/discord.py-2.7%2B-5865F2)

</div>

---

## Features

| Area | What you get |
|---|---|
| **Security stack** | AntiNuke (per-action thresholds and quarantine), AntiRaid (join-velocity detection, raid mode), heat-based AutoMod, Verification gate (button, captcha, manual) and AutoRole, all coordinated through a shared incident state (normal, elevated, lockdown) |
| **Moderation** | ban, kick, mute, warn, purge, tempban, softban, lockdown and slowmode, with a full case history |
| **Logging** | Moderation, security, member, message and server logs routed to dedicated channels |
| **Music** | Queue, filters, autoplay and 24/7 lofi radio stations through Lavalink v4 |
| **Community** | Leveling and XP, giveaways, reaction roles, greetings with generated image cards, AFK, quotes, ship, truth or dare, anime lookup |
| **Custom commands** | Per-server commands with triggers, conditionals, role and channel restrictions, and action tags |
| **Alerts** | YouTube upload/live and Twitch stream notifications |
| **Premium** | Server-wide flag that unlocks no-prefix mode, redeemed with generated keys |
| **UI** | Discord Components V2 (`LayoutView`, `Container`) for help, settings and panels |
| **Reliability** | SQLite always on, MongoDB as an optional mirror that reconnects automatically; a broken cog never stops the rest from loading |

The bot is **prefix-only** (default prefix `!`, configurable per server) and
commands are case-insensitive. Run `!help` for the full command list.

## Quick start

**Requirements:** Python 3.11+, a bot token from the
[Discord Developer Portal](https://discord.com/developers/applications).
MongoDB and Lavalink are optional.

```bash
git clone https://github.com/sinlt0/soward.git
cd soward

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # set SOWARD_TOKEN
# edit devs.json and replace the IDs with your own Discord user ID(s)

python main.py
```

In the Developer Portal, enable all three **privileged gateway intents**
(Presence, Server Members, Message Content). The bot requests `Intents.all()`.

Invite link: replace `YOUR_CLIENT_ID`, then open it in a browser.

```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&scope=bot%20applications.commands&permissions=8
```

`permissions=8` is Administrator, which the security features are simplest with.
Scope it down if you prefer, but AntiNuke, quarantine and moderation need
Manage Roles, Manage Channels, Ban/Kick Members and Moderate Members.

## Configuration

### Environment variables (`.env`)

| Variable | Required | Description |
|---|---|---|
| `SOWARD_TOKEN` | Yes | Discord bot token |
| `SOWARD_MONGO_URI` / `SOWARD_MONGO_DB` | No | MongoDB mirror (default `mongodb://localhost:27017` / `soward`) |
| `SOWARD_LAVALINK_HOST` / `_PORT` / `_PASSWORD` / `_SECURE` | No | Lavalink v4 node for music |
| `SOWARD_LAVALINK_NODES` | No | JSON list of nodes, overrides the four above |
| `SOWARD_SPOTIFY_CLIENT_ID` / `_SECRET` | No | Enables Spotify search |
| `SOWARD_YOUTUBE_API_KEY`, `SOWARD_TWITCH_CLIENT_ID` / `_SECRET` | No | Alerts cog |
| `SOWARD_DEV_LOG_*_WEBHOOK`, `SOWARD_DEV_STATS_WEBHOOK` | No | Developer-only logging webhooks |

See [`.env.example`](./.env.example) for the full template.

### `devs.json`

Owner and developer access (premium key generation, global no-prefix, `dev`
commands). **Replace the IDs with your own** before running your own instance,
otherwise the original author's account has owner access on your bot.

```json
{ "owner_ids": [123456789012345678], "dev_ids": [123456789012345678], "dev_role_ids": [] }
```

### `config.py`

Tunables live here: default prefix, XP rates, economy payouts, AntiNuke
thresholds, AutoMod heat values, premium durations and hidden help categories.

## Music

Music uses [Wavelink](https://github.com/PythonistaGuild/Wavelink) and needs a
running [Lavalink v4](https://lavalink.dev/getting-started/) server. If no node
is reachable, music commands just don't work and the rest of the bot is
unaffected.

## Premium and no-prefix

- `premium generate <duration>` (owner/dev): presets like `3d`, `1w`, `1m`,
  `3mo`, `1y` or custom values such as `45d`.
- `premium claim <key>`: any member redeems a key for their server.
- `premium np enable|disable`: per-server toggle of the no-prefix perk.
- `globalnp add|remove|list` (owner/dev): no-prefix access in every server.

## Custom emoji

`emoji/*.py` ships with placeholder IDs such as `<:play:1000000000000002001>`.
Upload your own emoji and replace the placeholders, or they won't render. All
bot output goes through `utils/emoji_manager.py`; no default Unicode emoji are
used.

## Deploying

A [`render.yaml`](./render.yaml) blueprint is included. The bot serves a status
page and a `/health` endpoint on `$PORT` (default `8080`). Any host that can run
`python main.py` and keep a process alive works. Persist the `data/` directory
or use MongoDB so state survives restarts.

## Project structure

```
main.py        entry point
config.py      tunable constants
cogs/          one file per feature, auto-loaded
events/        cross-system listeners, auto-loaded
utils/         shared helpers (db, security, components, ...)
emoji/         emoji dictionaries merged by EmojiManager
web/           aiohttp status page and /health
assets/        fonts for generated cards
```

Drop a new file into `cogs/` or `events/` and it loads on the next restart. If
a module fails to import, the loader logs the full traceback and keeps going.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](./CONTRIBUTING.md) and the
[Code of Conduct](./CODE_OF_CONDUCT.md). Report vulnerabilities privately as
described in [SECURITY.md](./SECURITY.md).

## License and attribution

Soward is licensed under the **Apache License 2.0** ([LICENSE](./LICENSE),
[NOTICE](./NOTICE)). You may fork, self-host and build on it, but you must keep
`LICENSE` and `NOTICE` intact and credit the original project, for example:

> Built upon [Soward](https://github.com/sinlt0/soward) by Sinlt

See [CREDITS.md](./CREDITS.md) for the full list of credits.
