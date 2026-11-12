---
title: Premium
description: What Premium unlocks, the limits, and how to buy it with crypto or activate a key.
order: 64
group: Utility
---

## What you get

| Feature | Free | Premium |
| --- | --- | --- |
| Ticket panels | 3 | 10 |
| Staff roles per ticket panel | 10 | 20 |
| Ticket categories per panel | 5 | 10 |
| Ticket form questions | 5 | 10 |
| Open tickets per server | 25 | 250 |
| Embed templates | 100 | 250 |
| Custom commands | 100 | 250 |
| Custom command groups | 20 | 50 |
| Responses per custom command | 10 | 25 |
| Application forms | 5 | 25 |
| Questions per application form | 25 | 40 |
| Join-to-create hubs | 2 | 10 |
| Alert subscriptions per platform | 5 | 15 |
| Server templates | 5 | 15 |
| Lofi custom stations | 20 | 60 |
| Tracks per loaded playlist | 200 | 500 |
| Booster reward tiers | 15 | 30 |
| NSFW channels | 25 | 50 |
| AutoMod banned words, blocked and allowed domains | 200 | 500 |
| AutoMod exempt channels and roles | 50 | 150 |
| Anti-raid name filter patterns | 50 | 150 |
| No-prefix mode | No | Yes |
| [Audit Vault](/docs/audit-vault) history | 7 days | 365 days, with CSV export |
| [Scheduled actions](/docs/scheduled-actions) | No | Yes, up to 25 |
| Ticket ratings, canned replies and transcript archive | No | Yes |
| [Deep backups](/docs/deep-backups) with settings and restore | No | Yes |
| Bot profile customization (`!nbot`) | No | Yes |

## Buy premium with crypto

Run `!premium buy` in the server you want to upgrade. You do not need an account, an email or any ID.

1. Pick a plan: **1 month ($3)**, **3 months ($8)** or **1 year ($20)**.
2. Pick **Bitcoin** or **Litecoin**.
3. Zyro shows an invoice with the exact amount, a payment address and a QR code. The address is created **only for your invoice**, so nobody else's payment can ever be mixed up with yours, even when many people buy at the same time.
4. Send the exact amount from any wallet within 30 minutes. Zyro watches the blockchain and turns premium on by itself once the payment has 1 confirmation, usually within a few minutes for Litecoin and within about ten for Bitcoin. You do not have to press anything, but **Check payment** looks right away.

Good to know:

- Send only the coin you picked, on its own network, to the address shown. Coins sent to the wrong network or to another address cannot be recovered.
- Prices are fixed in US dollars and converted to the coin when the invoice is created, and stay locked for the 30 minutes.
- If you send slightly less than the amount (up to 1% is fine), it still counts. If you send a lot less, the invoice stays open for the rest. If you send more, premium is extended in proportion, for example paying double the 1 month price gives 2 months.
- A payment that arrives after the invoice expired still counts if it arrives within 24 hours.
- Buying again before your premium ends adds the time on top of what you have. A server that already has premium with no end date cannot buy more.
- `!premium buy gift` makes a premium key instead of activating this server. The key is sent to your direct messages when paid (and the **Show my key** button on the invoice shows it only to you). Anyone can redeem it with `!premium claim`.
- You can have 2 open invoices at a time. Press **Cancel** on an unpaid invoice to free the slot.
- Payments are confirmed by two independent blockchain explorers before premium is given. If they are down, the invoice simply waits.
- Premium is not refundable once granted. If something goes wrong with a payment, ask for help in the support server and give the invoice id shown on your invoice.

## Free trial

Every server gets one free 3-day premium trial. Someone with Manage Server runs `!premium trial claim` to start it, and `!premium trial` shows when it ends. You get a reminder 24 hours before it ends, by direct message to the person who claimed it (or in the server's system channel if their messages are closed). A server that already has premium cannot claim one, and a trial can only be used once per server.

## Activate a key

If you were given a premium key, run this in your server:

```
!premium claim <key>
```

Run `!premium` to see the current status and when it expires.

## No-prefix mode

With premium active, members can run commands without typing the prefix. You choose who: **everyone**, or **only the roles and members you pick**, such as admins, moderators or your staff role. Administrators control it.

| Command | What it does |
| --- | --- |
| `!premium` | Shows premium status and expiry. Anyone can use it. |
| `!premium claim <key>` | Activates premium with a key. Anyone can use it. |
| `!premium limits` | Shows every free and premium limit side by side. Aliases: `perks`, `compare`. Anyone can use it. |
| `!premium np` | Shows whether no-prefix mode is on and who can use it. |
| `!premium np enable` | Turns no-prefix mode back on. |
| `!premium np disable` | Turns no-prefix mode off completely, for everyone. Your list of roles and members is kept. |
| `!premium np server enable` | Everyone in the server can skip the prefix. This is the default. |
| `!premium np server disable` | Only the roles and members you added can skip the prefix. |
| `!premium np add <role or member>` | Lets a role or member skip the prefix. Alias: `give`. |
| `!premium np remove <role or member>` | Takes it away again. Alias: `revoke`. |
| `!premium np list` | Shows everyone you added. |

All of these need Administrator, and turning things on needs an active premium.

### Only for staff

```
!premium np server disable
!premium np add @Moderator
!premium np add @Admin
!premium np add @someone
```

Members with any added role, and any member you added by name, can run commands without a prefix. Everyone else still uses the prefix. You can add up to 50 roles and members.

Good to know:

- `!premium np disable` overrides everything. While it is off, nobody skips the prefix, even people on your list.
- While **server-wide** is on, everyone can already skip the prefix, so your list has no effect until you run `!premium np server disable`.
- The prefix and the bot mention always keep working.
- The dashboard has a switch for server-wide under **Server settings**.

## Notes

Premium is granted for a set time, or permanently with a key. You can pay with Bitcoin or Litecoin using `!premium buy`, with coins or diamonds using `!premium coins` and `!premium diamonds` (coins buy 1 month only, once every 90 days per person; diamonds buy 1 month, 3 months or 1 year with no limit, but never lifetime) (see [Coins and Diamonds](/docs/economy)), or redeem a premium key. Zyro never sees your wallet, and crypto payments cannot be reversed. When premium ends, existing panels and templates stay, but you cannot create more than the free limits.
