---
title: Games App
description: Play chess and Doom with friends inside Discord with a lobby, rooms and spectators.
order: 52
group: Fun
---

## How it works

The Games App lives in the same **Activity** as the Music App. Open it with `!gamesapp` (also `!chess`), or from the App Launcher, then choose **Games** in the side bar. It works in servers, in voice channels and in DMs.

## Chess

1. Press **Play as White**, **Play as Black** or **Random** to create a room.
2. Anyone in the same session sees the room under **Open rooms**. Pressing **Join** takes the free seat, and the game starts as soon as both seats are filled.
3. Everyone else can press **Watch** to follow the game live.
4. Tap one of your pieces to see its legal moves, then tap a square to move.

The game follows the full rules: check, checkmate, stalemate, castling, en passant and promotion. It also ends in a draw by insufficient material, threefold repetition or the fifty-move rule.

## During a game

- **Offer draw** asks your opponent, who can accept or decline.
- **Resign** needs a second tap to confirm.
- **Rematch** swaps colours once both players press it.
- **Flip board** turns the board around for you.
- Your Discord status shows **Playing Chess** while you are in a room.

## Doom

Doom runs inside the Activity, with the shareware **Doom 1** built in. Choose **Play solo** or **Host a shared room** on the Doom card.

### Solo

Everyone plays their own copy. Nobody else sees your screen or controls it.

### Shared room

One game for the whole session. Everyone sees the same screen, and the host picks how it is controlled:

- **Take turns:** one player controls the game at a time. The turn passes on its own after 30 seconds, 1, 2 or 5 minutes, or sooner with **Pass the turn**. Other players watch, and their keys are ignored until their turn.
- **Vote:** everyone who is playing can press keys at once, and a key only counts while most of the active players hold it. With one player it works like solo, and with four players a key needs three of them.

Anyone in the session can open **Open rooms** and press **Join**. People who join late catch up to the current moment in a few seconds. The host can **Restart game** or **Close room**. Each person can host one Doom room at a time and a session holds up to 10.

### Your own WAD files

Pick **My own WAD files** to load a full game IWAD such as DOOM.WAD, DOOM2.WAD or Freedoom, add-on level WADs, or both. Add-ons run on top of the built-in Doom 1 when no IWAD is picked. Add-on levels made for Doom II need a Doom II IWAD, and Zyro tells you when one is missing. In solo mode the files stay in your browser. In a shared room the host's files are sent to the room (up to 4 files, 16 MB each and 24 MB in total) so everyone plays the same WADs, and they are deleted when the room closes. Only genuine Doom WAD files are accepted. Only the bundled Doom 1 shareware is provided. Bring your own copies of the other games.

### Controls

| Action | Keys |
|---|---|
| Move | W and S, or the up and down arrows |
| Turn | Left and right arrows |
| Strafe | A and D |
| Fire | Ctrl, F, or click the screen |
| Use or open | Space or E |
| Run | Shift |
| Weapons | 1 to 7 |
| Map and menu | Tab and Esc |

On phones and tablets, on-screen buttons appear under the game. **Sound off** mutes the effects. Music is not played.

## Good to know

- Rooms belong to the Activity session they were made in, so people in other sessions do not see them.
- A player can host two open rooms at a time, and a session holds up to 20 rooms.
- There is no clock in chess yet.
- Rooms are kept in memory, so they are cleared when the bot's dashboard restarts, and idle rooms close on their own after a while. A shared Doom room pauses while nobody is in it.
- Choosing what to play is done in `addons.py` under `game_lobby`: set `chess` or `doom` to `False` to hide one.
