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
| **Web dashboard** | Python/Flask site with Discord sign-in, a Dyno-style server page (prefix and core settings, searchable module grid with on/off switches, per-module forms), audit log, categorised command list, docs, changelog, terms and privacy. Talks to the bot over a private Unix socket. Switch it on or off per server with `dashboard on/off` |
| **Music** | Queue, filters, autoplay and 24/7 lofi radio stations through Lavalink v4 |
| **Tickets** | Multi-panel support tickets with button panels, intake forms, multiple staff roles and categories per panel, claim/priority/add/remove tools, per-member and per-panel limits, inactivity auto-close, ticket stats, and HTML transcripts. Free servers get 3 panels and 10 staff roles per panel; Premium gets 10 and 20 |
| **NSFW channels** | Role-gated instead of Discord's one-click age prompt: `nsfw role`, `nsfw addchannel`, `nsfw removechannel`, `nsfw viewchannels`, `nsfw sync`. Original channel permissions are saved and restored on removal |
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
| `SOWARD_CLIENT_ID` / `SOWARD_CLIENT_SECRET` | For dashboard sign-in | Discord OAuth2 credentials |
| `SOWARD_DASHBOARD_URL` | For dashboard sign-in | Public site URL, no trailing slash |
| `SOWARD_SESSION_SECRET` | Recommended | Signs dashboard session cookies |
| `SOWARD_SUPPORT_URL` | No | Support server link shown on the site |
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

The emoji in `emoji/*.py` point at custom emoji hosted on the author's servers,
so they will **not render for you** (and some files, such as `social.py` and
`anime.py`, still contain placeholder IDs like `<:play:1000000000000002001>`).
Upload your own emoji to a server the bot can see and replace the IDs. All bot
output goes through `utils/emoji_manager.py`; no default Unicode emoji are used.

## Web dashboard

The dashboard is an addon controlled from [`addons.py`](./addons.py) in the project root:

```python
dash = {
    "dashboard": True,
    "dashboard_port": 8080,
}
```

Set `dashboard` to `False` to skip starting the web server entirely, and
`dashboard_port` to change the port. If the port is missing or invalid, `$PORT`
is used, then `8080`. Hosts that assign a port (Render) need `dashboard_port`
to match it. More addon toggles can be added as new dicts after `dash`.

`python main.py` starts the bot and, beside it, the Flask site on `$PORT`
(default `8080`). The two processes talk over a Unix socket at
`data/soward-ipc.sock` (a loopback port is used on Windows), protected by a
secret generated on every boot.

1. In the Discord Developer Portal open your application, go to **OAuth2** and
   add `<SOWARD_DASHBOARD_URL>/callback` as a redirect.
2. Set `SOWARD_CLIENT_ID`, `SOWARD_CLIENT_SECRET`, `SOWARD_DASHBOARD_URL` and
   `SOWARD_SESSION_SECRET`.
3. Open the site, sign in and pick a server.

Anyone with Manage Server (or Administrator) in a server where the bot is
present can manage it. Permissions are checked on the bot side for every
request. Control access from Discord:

| Command | Who | Effect |
|---|---|---|
| `dashboard` | anyone | Show whether web access is on |
| `dashboard on` / `off` | Manage Server | Allow or block the dashboard for this server |
| `dashboard global on` / `off` | bot owners | Switch the dashboard on or off everywhere |

The legal pages under `dashboard/content/legal/` are starting templates. Have
them reviewed before you rely on them.

## Deploying

A [`render.yaml`](./render.yaml) blueprint is included. The site serves a
`/health` endpoint on `$PORT`. Any host that can run `python main.py` and keep a
process alive works. Persist the `data/` directory or use MongoDB so state
survives restarts. Free Render instances sleep when idle, which also pauses the
bot.

## Project structure

```
main.py        entry point
config.py      tunable constants
cogs/          one file per feature, auto-loaded
events/        cross-system listeners, auto-loaded
utils/         shared helpers (db, security, components, ...)
emoji/         emoji dictionaries merged by EmojiManager
dashboard/     Flask site and web dashboard (separate process)
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
