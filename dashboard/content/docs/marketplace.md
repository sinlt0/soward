---
title: Marketplace and Auctions
description: Sell items and crafted weapons to other players for a fee, with fixed-price listings and bidding auctions.
order: 56
group: Fun
---

Players can trade cultivation items for spirit stones in two ways. Everything is global, so you trade with players from every server.

## What you can sell

Pills, brews, materials, armor, charms and **crafted weapons**. A weapon keeps its quality and remaining durability when it is sold. Soul-bound weapons and story relics can never be sold, traded or stolen. A weapon you are wearing cannot be listed, and a listed weapon cannot be worn.

## Fees

| | Fee | Paid by |
| --- | --- | --- |
| Marketplace sale | 5% of the sale price | Seller |
| Auction sale | 8% of the final price | Seller |

Listing, bidding, buying and cancelling cost nothing. The fee is only taken when something actually sells, and it comes out of what the seller receives. An unsold item or an expired listing comes back to your bag in full.

## Marketplace

Fixed prices. Items are removed from your bag while listed and returned if the listing is cancelled or expires after 7 days. You can have 10 listings at once.

| Command | What it does |
| --- | --- |
| `!market [search] [page]` | Browse listings, cheapest first |
| `!market sell <item> <amount> <price each>` | List a stack, for example `!market sell "demon core" 10 150` |
| `!market sell #12 5000` | List the crafted weapon numbered 12 in your bag |
| `!market buy <id> [amount]` | Buy all or part of a stack |
| `!market mine` | See your listings |
| `!market cancel <id>` | Take a listing back |
| `!market fees` | Show how fees work |

Prices can be written as `1500`, `1.5k` or `2m`.

## Auctions

You set a starting price, a length from 1 to 72 hours and, if you like, a buyout price. You can run 5 auctions at once.

| Command | What it does |
| --- | --- |
| `!auction [search] [page]` | Browse running auctions, soonest first |
| `!auction create <item> <amount> <start> [hours] [buyout]` | Start an auction |
| `!auction create #12 2000 24 10k` | Auction a crafted weapon |
| `!auction bid <id> <amount>` | Place a bid |
| `!auction buyout <id>` | Pay the buyout price and win at once |
| `!auction view <id>` | See one auction |
| `!auction mine` | Auctions you run or are bidding on |
| `!auction cancel <id>` | Cancel your auction, only while it has no bids |

Your bid is taken from your spirit stones right away. If someone outbids you, your spirit stones come back immediately and you get a message. Each bid must beat the last by at least 5%. A bid in the last 5 minutes extends the auction by 5 minutes so nobody can win by sniping. When an auction ends, the winner gets the item, the seller gets the price minus the fee, and both are told by message. If there were no bids, the item goes back to the seller.
