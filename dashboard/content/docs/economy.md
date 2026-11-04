---
title: Coins and Diamonds
description: Earn coins with rewards, work and votes, gamble them, buy diamonds with crypto, and spend either on premium, family slots and clans.
order: 55
group: Fun
---

## Two currencies

**Coins** are the everyday currency. You earn them for free and spend them on most things. **Diamonds** are the premium currency. You buy them with Bitcoin or Litecoin at **$1 for 1,000 diamonds**. Both belong to you, not to a server, so they work everywhere the bot is.

`!coins` shows both balances, and `!coins <user>` shows someone else's.

## Exchange rate

`!coins convert <diamonds|all>` turns diamonds into coins at exactly **1 diamond = 10 coins**. It only goes one way: coins cannot be turned back into diamonds. Premium costs the same in either currency, so 1 month is 3,000 diamonds or 30,000 coins. With coins you can only buy 1 month, and only once every 90 days per person. Diamonds have no limit and also buy 3 months (8,000) and a special 1 year plan (20,000). Lifetime is not sold for diamonds.

## Earning coins

| Command | What it gives |
| --- | --- |
| `!reward` | Your sect stipend every 20 hours. Collecting within 48 hours keeps your cultivation streak and raises the amount, up to double |
| `!work` | A shift at your sect job every hour, up to 4 times a day. Better jobs pay more |
| `!gather`, `!hunt`, `!mine`, `!ruins` | Small cultivation trips with their own cooldowns and daily limits. `!hunt` and `!ruins` can find nothing |
| `!vote` | 200 coins per bot list every 12 hours, plus 1 to 10 diamonds once a day per bot list |
| `!support` | A tip gives a fixed number of coins whatever the amount |

Every one of these, and `!reward` and `!work`, also has a small chance to drop diamonds along with the coins. A normal day of play drops only a couple of diamonds, so they stay rare.

An active player earns about 800 coins a day, and a player who does every trip earns around 950, so a month of premium takes five to six weeks without paying. `!coins earn` lists the current amounts.

## Sect jobs

`!job` shows your job and how many shifts you need for the next one. Every `!work` shift counts, and new jobs unlock as your total grows. `!job list` shows them all and `!job take <name>` switches to any job you have unlocked.

| Job | Shifts needed | Pay per shift |
| --- | --- | --- |
| Sect Ground Sweeper | 0 | 30-50 |
| Herb Garden Tender | 15 | 40-65 |
| Spirit Beast Keeper | 40 | 50-80 |
| Formation Scribe | 80 | 60-95 |
| Alchemy Furnace Attendant | 140 | 75-115 |
| Auction House Clerk | 220 | 90-140 |
| Auction House Manager | 350 | 110-170 |
| Sect Treasurer Elder | 520 | 140-210 |

## Gambling

`!coinflip <bet|all|half> [yin|yang]` tosses a yin-yang talisman and pays 1.9 times your wager on a win. `!gamble <bet|all|half>` draws your fate for a multiplier:

| Result | Chance |
| --- | --- |
| Lose the bet | 50% |
| 1.5 times | 30% |
| 2 times | 15% |
| 3 times | 4% |
| 6 times | 1% |

Over time the house keeps about 7% of what is bet. Bets are limited and there is a short pause between rolls.

## Spending

| Command | What it does |
| --- | --- |
| `!premium coins 1m` | Buys 1 month of premium for the server with coins, once every 90 days (needs Manage Server) |
| `!premium diamonds <1m\|3m\|1y>` | Buys premium for the server with diamonds, with no limit |
| `!family upgrade` | Buys more marriage or adoption slots with coins |
| `!clan create` | Starts a clan |
| `!clan deposit` | Adds coins to your clan's bank |
| `!profile` themes and badges | Cosmetic items priced in coins |

## Giving and ranking

`!coins give <user> <amount> [coins|diamonds]` passes coins to another cultivator, at least 100. Add `diamonds` at the end to give diamonds instead, at least 10. `!coins top` shows the wealthiest cultivators.

## Older balances

When diamonds were introduced, coins you had bought became the same number of diamonds, and coins you had earned were multiplied by 10.
