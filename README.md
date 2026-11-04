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
| **Security stack** | Security Center (Owner, Extra Owner and Trusted Admin tiers, scoped whitelist, presets, server lockdown, backups and restore, threat score), AntiNuke (per-action limits, restore and quarantine), AntiRaid (join gate, impersonation and ban-evasion checks, invite tracking, raid mode), heat-based AutoMod with a warning ladder and Discord AutoMod sync, Verification (button, captcha, manual and web with VPN and alt detection) and AutoRole, all coordinated through a shared incident state |
| **Moderation** | ban, kick, mute, warn, purge, tempban, softban, lockdown and slowmode, with a full case history |
| **Logging** | Moderation, security, member, message and server logs routed to dedicated channels |
| **Web dashboard** | Python/Flask site with Discord sign-in, a Dyno-style server page (prefix and core settings, searchable module grid with on/off switches, per-module forms, and create/edit/delete tools for panels, embeds, 24/7 lofi, giveaways, reaction roles, custom commands, alerts, rewards and moderation), audit log, categorised command list, docs, changelog, terms and privacy. Talks to the bot over a private Unix socket. Switch it on or off per server with `dashboard on/off` |
| **Music** | Queue, filters, autoplay and 24/7 lofi radio stations through Lavalink v4 |
| **Tickets** | Multi-panel support tickets with button panels, intake forms, multiple staff roles and categories per panel, claim/priority/add/remove tools, per-member and per-panel limits, inactivity auto-close, ticket stats, and HTML transcripts. Free servers get 3 panels and 10 staff roles per panel; Premium gets 10 and 20 |
| **NSFW channels** | Role-gated instead of Discord's one-click age prompt: `nsfw role`, `nsfw addchannel`, `nsfw removechannel`, `nsfw viewchannels`, `nsfw sync`. Original channel permissions are saved and restored on removal |
| **Personal tools** | Global reminders with repeats and per-user timezones (`remind`), and a private to-do list (`todo`) |
| **Games** | Tic-Tac-Toe, Connect 4, Rock Paper Scissors (against a friend or the bot), Hangman, Trivia and Typing Race, with per-game records and leaderboards |
| **Lookups** | Weather, translate, dictionary, Urban Dictionary, calculator, crypto prices and local time, using free public APIs with no keys |
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
MongoDB and Lavalink are optional. Auto partner reads screenshots with Tesseract, so install the `tesseract-ocr` program on the host (for example `apt install tesseract-ocr`); without it staff approve partner tickets by hand.

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
| `SOWARD_WEBSUB`, `SOWARD_WEBSUB_CALLBACK`, `SOWARD_WEBSUB_SECRET` | No | Instant YouTube push. Callback defaults to `SOWARD_DASHBOARD_URL` + `/websub/youtube` (must be public https); secret defaults to the IPC secret |
| `SOWARD_CLIENT_ID` / `SOWARD_CLIENT_SECRET` | For dashboard sign-in | Discord OAuth2 credentials |
| `SOWARD_DASHBOARD_URL` | For dashboard sign-in | Public site URL, no trailing slash |
| `SOWARD_SESSION_SECRET` | Recommended | Signs dashboard session cookies |
| `SOWARD_IPINTEL_PROVIDER` / `SOWARD_IPINTEL_KEY` | For VPN detection | `proxycheck` or `ipqs` with that service's API key. Used by the `web` verification type |
| `SOWARD_IP_SALT` | Recommended with `web` verification | Secret mixed into the stored address hashes |
| `SOWARD_BEHIND_PROXY` | If hosted behind a proxy | Set to `1` so the real visitor address is read from `X-Forwarded-For` |
| `SOWARD_TURNSTILE_SITE_KEY` / `SOWARD_TURNSTILE_SECRET` | No | Adds a Cloudflare Turnstile widget to the verification page |
| `SOWARD_SUPPORT_URL` | No | Support server link shown on the site |
| `SOWARD_DEV_LOG_*_WEBHOOK`, `SOWARD_DEV_STATS_WEBHOOK` | No | Developer-only logging webhooks |
| `SOWARD_BLOCKCYPHER_TOKEN` | No | Optional free BlockCypher token that raises the Litecoin explorer rate limit |

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

## Music Activity

Soward Music is a Discord Activity: a music app that runs inside Discord for
servers, voice channels and DMs. It is served by the dashboard (a section of
the Flask site under `/activity/`) and needs the dashboard to be running and
reachable over HTTPS. It does not need Lavalink. Audio is searched and streamed
by the dashboard process through `yt-dlp`, so the host needs outbound access to
YouTube and enough bandwidth for the listeners.

Developer Portal setup, on the same application as the bot:

1. **Installation**: turn on both User Install and Guild Install.
2. **OAuth2 > Redirects**: add the placeholder `https://127.0.0.1`.
3. **Activities > Settings**: turn on **Enable Activities** and tick the supported platforms (desktop, mobile and web). This creates the default Launch entry point command.
4. **Activities > URL Mappings**: add one mapping, prefix `/` and target `your-dashboard-host/activity` (no protocol, no trailing slash). Requests from the Activity then reach the dashboard's `/activity/` routes.
5. Make sure `SOWARD_CLIENT_ID`, `SOWARD_CLIENT_SECRET` and `SOWARD_DASHBOARD_URL` are set. The Activity reuses them. Set `SOWARD_ACTIVITY=0` to turn the feature off.

If songs will not play, open the Activity as the owner, go to Settings and press
**Run music diagnostics**. It reports the `yt-dlp` version, whether search works and
the exact error when preparing a song fails. YouTube often blocks cloud server
addresses and asks to "sign in to confirm you're not a bot". The Activity first
retries with other YouTube player clients. If that is not enough, give it cookies
from a throwaway YouTube account: export them as a Netscape `cookies.txt`, then set
`SOWARD_YTDLP_COOKIES_B64` to the base64 of that file (or `SOWARD_YTDLP_COOKIES` to
a file path, such as a Render secret file). Also set `SOWARD_YTDLP_JS_RUNTIME` to
`node` or `deno`. The export must include `__Secure-1PSIDTS` and `__Secure-3PSIDTS`. Export from a
private window right after signing in, then close it without logging out, because
YouTube rotates cookies that stay open in a tab. Use a spare account, because YouTube
can flag accounts used this way. Keep `yt-dlp` up to date.

When YouTube blocks the server, the Activity first asks your Lavalink node for the
audio (this needs the node to run the YouTube source plugin with its stream endpoint
enabled; the diagnostics list the node's plugins and whether the endpoint answers).
If that fails too, it plays a matching SoundCloud
version of the song instead (matched by title, artist and length). Search results also
have a SoundCloud tab. SoundCloud needs no cookies.

The same Activity has a **Games** tab with chess: players create or join a room,
others can watch, and the server checks every move against the full rules. Rooms live in
the dashboard process's memory and there is no clock yet. `!gamesapp` posts a launch
button.

Choose which apps are available in `addons.py`. Opening the Activity shows an apps
page with a card for each app that is on. If only one is on, it opens straight away.

```python
activities = {
    "enabled": True,
    "music": True,
    "game_lobby": {
        "enabled": True,
        "chess": True,
    },
}
```

Turning an app off also blocks its server routes and its `!musicapp` or `!gamesapp`
command. `SOWARD_ACTIVITY=0` still turns every app off.

### Coins, family and clans

Wallets hold two currencies. Coins are earned (`!reward`, `!work` at a sect job from `config.CULTIVATION_JOBS`, the `!gather`, `!hunt`, `!mine` and `!ruins` trips from `config.CULTIVATION_ACTIVITIES`, votes, tips) and gambled (`!coinflip`, `!gamble`); diamonds are bought through the crypto invoices at `config.DIAMOND_PER_USD` per dollar and, like coins, can be given to other users or converted one way into coins at `config.DIAMOND_TO_COINS`. Reward, work and trip commands can also drop diamonds (`config.DIAMOND_DROPS`), and votes give `config.VOTE_DIAMONDS_*` diamonds once a day per site. Votes (`config.VOTE_COINS`) and tips (`config.SUPPORT_COINS`) pay coins. Reward, work and gamble numbers are in `config.REWARD_*`, `config.WORK_*` and `config.GAMBLE_*`. On first start the wallet migration turns old bought coins into diamonds 1:1 and multiplies earned coins by 10, so back up the database before deploying. Premium can be bought with either currency (`!premium coins`, `!premium diamonds`); diamonds buy the plans in `config.PREMIUM_DIAMOND_PLANS` (no lifetime) and coins only buy `config.PREMIUM_COIN_PLAN` and only once every `config.PREMIUM_COIN_COOLDOWN_DAYS` days per user. Marriage and adoption slots, clan prices and
the other limits are constants near the top of the economy section of `config.py`.

### Vote rewards

`!vote` links to the bot's discordbotlist.com page. When someone votes, the site posts to
`<dashboard url>/vote/discordbotlist` and the voter gets global no-prefix for
`SOWARD_VOTE_NP_HOURS` hours (default 12), a thank-you DM and a vote streak. On the bot's
discordbotlist.com edit page, set **Upvote Webhook** to that URL and **Webhook Secret** to a
long random string, then put the same string in `SOWARD_VOTE_DBL_SECRET`. The **Test webhook**
button on the site sends from your browser and cannot reach a private dashboard, so check
with a real vote.

Set `SOWARD_DBL_TOKEN` to the token from the page's **Generate token** link and the bot posts its
server and user counts to discordbotlist.com every 30 minutes.

### Auto partner

`!autopartner` runs ticket-style partnerships. A partner opens a ticket, posts your server's ad in their own server, sends their ad with an invite and a screenshot of your ad, and the bot reads the screenshot with `pytesseract` (needs the `tesseract` program). If your ad text and invite are visible, the partner's ad is posted in your partner channel. Staff can approve tickets by hand, the same screenshot cannot be reused, and a server cannot be posted again for `config.AUTOPARTNER_REPEAT_DAYS` days. The tables are `autopartner_config`, `autopartner_tickets`, `autopartner_posts` and `autopartner_hashes`.

### Translation

`!translate` works with no setup through the free MyMemory service (about 5,000 characters per day
per IP). Two optional settings raise that: `SOWARD_TRANSLATE_EMAIL` (any email, free, lifts MyMemory
to about 50,000 characters per day) and `SOWARD_DEEPL_KEY` (a DeepL API Free key, 500,000 characters
per month). Languages DeepL does not support still fall back to MyMemory.

### Covering hosting

`!support` creates a pay-what-you-want Bitcoin or Litecoin invoice with the same wallet
as premium purchases. Set `SOWARD_SUPPORT_GUILD` and `SOWARD_SUPPORTER_ROLE` to also give
tippers a role in your support server. The dashboard has a `/supporters` page that lists
people who opted in with `!support public on`.

The website can show an A-ADS banner to visitors who are not signed in. Create an ad
unit at a-ads.com with your own Bitcoin address, then set it in `addons.py`:

```python
ads = {
    "enabled": True,
    "aads_unit": "1234567",
}
```

Banners only appear on public pages (home, docs, commands, changelog, team and
supporters). They never appear for signed-in users, on the dashboard, on legal pages, in
verification or appeal pages, or in Activities. The privacy policy already mentions them.

Until the app is distributed, only the application owner and team members can
launch the Activity. Playing music from YouTube may break YouTube's terms of
service, the same as the bot's other music commands, so decide whether to run
it on a public bot. `!musicapp` posts a button that launches it.

## Premium and no-prefix

- `premium generate <duration>` (owner/dev): presets like `3d`, `1w`, `1m`,
  `3mo`, `1y` or custom values such as `45d`.
- `premium claim <key>`: any member redeems a key for their server.
- `premium np enable|disable`: per-server toggle of the no-prefix perk.
- `globalnp add|remove|list` (owner/dev): no-prefix access in every server.

### Crypto premium payments

Members buy premium with `!premium buy`. The bot never holds a private key: it stores only a **public** key from your wallet, derives a new payment address for every invoice, and the money goes straight to your wallet. No KYC and no payment processor are involved.

1. In **Electrum** (Bitcoin) or **Electrum-LTC** (Litecoin) create a **Standard wallet** with a **Segwit** seed. Open **Wallet, Information** and copy the **Master Public Key** (`zpub`, `xpub`, `ypub`, `Ltub` or `Mtub`). Never share your seed words or anything starting with `xprv` or `zprv`.
2. Run `!crypto setup btc <key>` (or `ltc`). The bot deletes your message and shows address number 1. Check that it equals the first receiving address in your wallet.
3. Run `!crypto status` to test the blockchain explorers and price feeds. At least two explorers per coin must answer, because two have to agree before premium is granted.
4. Optional: `!crypto log #channel` posts every payment and every invoice that needs review.

| Command (bot owner and developers) | What it does |
| --- | --- |
| `!crypto setup <btc\|ltc> <key>` | Adds a wallet and starts selling in that coin |
| `!crypto off <coin>` | Stops selling in that coin. Open invoices keep being checked |
| `!crypto status` | Wallets, explorers, prices and open invoices |
| `!crypto invoices [status]` | Recent invoices: `pending`, `seen`, `paid`, `expired`, `cancelled`, `review` |
| `!crypto verify <id>` | Checks the chain for an invoice now, even if it expired |
| `!crypto approve <id>` | Grants premium for an invoice that received a payment but not enough |
| `!crypto cancel <id>` | Cancels an unpaid invoice |
| `!crypto log [#channel]` | Where payment logs go |

Plans, prices, coins, the invoice time, the grace period, confirmations, the number of explorers that must agree and the explorers themselves are in `config.py` (`CRYPTO_*`). Electrum only looks ahead 20 unused addresses by default, so after many unpaid invoices raise the gap limit in Electrum to see a payment on a later address. Keys, premium revoke and global no-prefix remain owner commands: `!premium generate`, `!premium revoke`, `!premium keys`, `!globalnp`.

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
