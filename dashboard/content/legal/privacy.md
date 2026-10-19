---
updated: 2026-10-18
---

This Privacy Policy explains what {BOT_NAME} collects, why, and how it is handled. It covers the Discord bot, the web dashboard and this website.

## 1. Information we collect

**When you use the bot in a server**, it stores the data needed for the features that server turns on:

- server settings such as prefix, enabled modules, log channels, greeting messages, verification, AutoMod word lists, AntiNuke and AntiRaid options
- moderation cases and warnings, including the member, moderator, reason and time
- leveling data such as XP, level and role rewards per member
- ticket panels, ticket records (opener, claimer, status, priority, subject, intake answers) and transcripts generated when a ticket closes
- AFK status and message, custom commands, reaction role setups, giveaway entries, alert subscriptions and NSFW channel role setups
- security settings, whitelists, quarantine records and server backups (roles, channels, bans and settings) when a server uses the Security Center
- premium status and expiry for a server or user
- Discord IDs (users, servers, channels, roles, messages) that connect the data above to Discord objects

The bot reads messages in channels it can see in order to run commands, AutoMod, leveling and custom commands. Message content is not stored as a general archive. The exception is a ticket transcript, which is built from the messages in a ticket channel when it closes and sent to the ticket log or transcript channel and, where possible, to the person who opened the ticket.

**When you sign in to the dashboard**, Discord shares your user ID, username, avatar and the list of servers you are in with your permission level in each (scopes `identify` and `guilds`). We use the server list only to decide which servers you can manage. It is held in server memory for the length of your session and is not written to the database.

**Dashboard changes** are written to an audit log with your Discord ID, display name, the module changed, a short summary and the time. Server managers can view it in the dashboard.

**When a server uses web verification**, the member opens a one-time link and completes a short check on our website. We receive the member's IP address and a browser fingerprint, and we store only salted, one-way hashes of them together with the server, the member, the result and the time. The raw IP address is not stored. The address is sent to an IP intelligence provider so VPN and proxy connections can be detected, and the check may use Cloudflare Turnstile. Hashes let the server's staff see whether several accounts verified from the same connection. They cannot be turned back into an IP address.

We do not collect email addresses, phone numbers, passwords or payment details.

## 2. How we use information

Only to run the features above: carrying out commands, enforcing server rules, showing server settings back to authorised managers, preventing abuse and fixing errors. We do not sell personal information and do not use it for advertising.

## 3. Cookies and sessions

The dashboard sets one cookie, `soward_session`, after you sign in. It keeps you signed in and protects forms from cross-site requests. It is not used for tracking. The public pages set no cookies.

## 4. Where data is stored

Data is stored in a SQLite database on the host that runs the bot. If the operator has configured MongoDB, a copy of the same data is mirrored there for backup and recovery. Access is limited to the bot and the people who operate it. We use reasonable safeguards, but no system is perfectly secure.

## 5. Third parties

- **Discord** processes your account and server activity under its own [Privacy Policy](https://discord.com/privacy).
- **Hosting and database providers** store and serve the data on our behalf.
- An **IP intelligence provider** (proxycheck.io or IPQualityScore, depending on how the bot is configured) receives the IP address during web verification to report whether it is a VPN, proxy or hosting address.
- **Cloudflare Turnstile** may be used on the verification page to confirm a visitor is human.
- Optional features can contact **YouTube**, **Twitch** or music sources when a server uses them. Only the queries needed for that feature are sent.
- Fonts on this site are loaded from Google Fonts.

## 6. Retention

Server data is kept while the bot is in the server. Moderation cases, tickets and levels stay until deleted by server staff or removed with the server's data. Dashboard audit log entries are kept until the server's data is removed. Web verification records are deleted after 90 days by default, and servers can choose a different period. Sessions expire automatically.

## 7. Removing data

Removing the bot from a server stops new data collection. To ask for stored data about you or your server to be deleted, contact us through the support server linked on this site and include the relevant Discord IDs. We may need to verify that you own the account or server.

## 8. Children

{BOT_NAME} is for people who are old enough to use Discord. We do not knowingly collect data from anyone under that age.

## 9. Changes

We may update this policy. The date at the top shows the latest revision.

## 10. Contact

Questions can be sent through the support server linked on this site.
