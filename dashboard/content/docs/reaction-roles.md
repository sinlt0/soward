---
title: Reaction roles
description: Let members pick their own roles with reactions or a select menu.
order: 41
group: Community
---

## How reaction roles work

A **panel** is a message that gives out roles. Each role on a panel is a **binding**: an emoji tied to a role. A panel is one of two types:

| Type | How members use it |
| --- | --- |
| `reaction` | The bot adds one reaction per role. Members react to get the role and remove the reaction to lose it. This is the default. |
| `select` | The message has a drop-down menu with one option per role. Members tick the roles they want. |

Panels are identified by an 8-character **panel ID** such as `3F9A1C2B`. The command is `!reactionrole` with the alias `!rr`. Every subcommand needs **Manage Roles** (or the matching fake permission, see [moderation](/docs/moderation)). Bot owners are always allowed.

There is nothing to switch on. The bot needs the **Manage Roles** permission, its top role must be above every role you hand out, and it must be allowed to add reactions and embed links in the channel.

## Quick start

```
!rr create
!rr addrole 3F9A1C2B 🎮 @Gamer
!rr addrole 3F9A1C2B 🎨 @Artist
!rr post 3F9A1C2B #roles
```

1. `!rr create` makes an empty panel and tells you its ID.
2. `!rr addrole <panel> <emoji> <role>` adds each role. Use a normal emoji, or a custom emoji from a server the bot is in.
3. `!rr post <panel> [#channel]` posts the panel. Without a channel it posts in the current one. The panel needs at least one role first.

`!rr` with nothing after it lists your panels with their role count, type, mode and whether they are posted or locked.

## Panel look

The posted message is an embed with a list of the roles added at the bottom.

- **Default look.** The title "Reaction Roles" and the text "React below to receive a role."
- **Saved embed.** `!rr create <embed name>` uses one of your saved [embeds](/docs/embeds) for the title, text, color and so on. The embed must already exist. Placeholders in it are filled in.

The default title and text can be changed from the dashboard (see below). There is no command for it.

## Command reference

| Command | What it does | Needs |
| --- | --- | --- |
| `!rr` | Lists the server's panels. Alias: `!reactionrole`. | Manage Roles |
| `!rr create [embed name] [reaction\|select]` | Creates a panel. The type is the second argument, so to make a `select` panel you must also give an embed name first. | Manage Roles |
| `!rr addrole <panel> <emoji> <role> [label]` | Binds an emoji to a role. Running it again for the same emoji replaces the role and label. The optional label is shown in the role list and in select menus. | Manage Roles |
| `!rr removerole <panel> <emoji>` | Removes a binding and, for reaction panels, clears that reaction from the message. | Manage Roles |
| `!rr post <panel> [#channel]` | Posts the panel as a new message. | Manage Roles |
| `!rr attach <panel> <message ID> [#channel]` | Uses an existing message for a reaction panel and adds the reactions to it. | Manage Roles |
| `!rr mode <panel> <toggle\|add_only\|unique>` | Sets the panel's default mode. | Manage Roles |
| `!rr bindingmode <panel> <emoji> <mode>` | Sets the behavior of one binding. Alias: `!rr rolemode`. | Manage Roles |
| `!rr bind <panel> <emoji> <swap role>` | Sets up a swap: reacting removes the swap role and grants this binding's role. | Manage Roles |
| `!rr group <panel> <emoji> <group name\|off>` | Puts a binding in a group where a member can hold only one role. `off` removes it from the group. | Manage Roles |
| `!rr maxroles <panel> <count\|off>` | Limits how many roles from this panel one member can hold. | Manage Roles |
| `!rr gate <panel> <required\|blacklist> [role] [emoji]` | Requires a role, or blocks a role, for the whole panel or for one binding. | Manage Roles |
| `!rr lock <panel>` | Stops the panel granting or removing roles until unlocked. | Manage Roles |
| `!rr unlock <panel>` | Turns a locked panel back on. | Manage Roles |
| `!rr delete <panel>` | Deletes the panel, its roles and its posted message, after you confirm. | Manage Roles |

## Binding modes

Binding modes change what reacting and un-reacting does for one role on a **reaction** panel. Set them with `!rr bindingmode <panel> <emoji> <mode>`. The default is `normal`.

| Mode | Reacting | Removing the reaction |
| --- | --- | --- |
| `normal` | Adds the role. | Removes the role. |
| `add_only` | Adds the role. | Does nothing. The member keeps the role. |
| `remove_only` | Removes the role. | Does nothing. |
| `reversed` | Removes the role. | Adds the role. Useful for opt-out roles. |
| `verify` | Adds the role, then the bot removes the reaction. | Does nothing. |
| `binding` | Removes the swap role (if the member has it) and adds this role. Set with `!rr bind`, not `bindingmode`. | Does nothing. |
| `unique` | Adds the role and removes the member's other roles from the same panel. | Removes the role. |

`!rr bindingmode` refuses `binding` and tells you to use `!rr bind`.

On `select` panels `unique`, `add_only`, `remove_only`, `reversed`, `verify` and `binding` also apply. Picking a `remove_only` or `reversed` option removes the role, and roles in `add_only`, `verify`, `remove_only`, `reversed` or `binding` mode are not removed when the member un-picks them.

## Panel modes

`!rr mode <panel> <mode>` sets the default for the whole panel. The default is `toggle`.

| Mode | What it does |
| --- | --- |
| `toggle` | Normal behavior: react to add, un-react to remove. |
| `unique` | On reaction panels, picking a role removes the member's other roles from the same panel. Roles in a group (see below) follow the group rule instead. |
| `add_only` | Un-reacting never removes a role. A binding's own mode overrides this. |

## Groups, limits and gates

- **Groups.** `!rr group <panel> <emoji> colors` puts the binding in a group named `colors`. When a member picks a role in a group, the bot removes their other roles in the same group on that panel. Group names are not case sensitive.
- **Maximum roles.** `!rr maxroles <panel> 2` lets a member hold at most 2 roles from the panel. On a reaction panel the bot removes the reaction that went over the limit. On a select panel the menu only allows that many choices (this is set when the panel is posted, so repost it after changing the number).
- **Required role.** `!rr gate <panel> required @Member` means only members with that role can use the panel.
- **Blocked role.** `!rr gate <panel> blacklist @Muted` stops members with that role from using the panel.
- **One binding only.** Add the emoji at the end: `!rr gate <panel> required @Member 🎮`.
- **Clearing a gate.** Use `off` as the role: `!rr gate <panel> required off` for the panel, or `!rr gate <panel> required off 🎮` for one binding.
- A member who fails a gate gets their reaction removed on reaction panels, or a "Skipped" note on select panels.
- **Locking.** A locked panel ignores reactions and menu choices. Existing roles stay as they are.

## Select menu panels

- Each menu option shows the role name, with the label under it if you set one. The emoji is only an internal key for select panels, so any short text works.
- Members choose any number of roles, up to the maximum roles setting. The menu is a full set: roles from the panel that the member has but did not pick are removed. Picking nothing removes all of the panel's roles.
- Role groups, required roles, blocked roles, locking, the panel mode and binding modes all work. With panel mode `unique` the menu allows one choice.
- After you add or remove a role or change the panel mode on a posted select panel, both the role list and the menu on the message update on their own.
- `!rr attach <panel> <message ID>` puts a select menu on one of the bot's own messages. Menus cannot be added to other people's messages.

## Limits

| Limit | Value |
| --- | --- |
| Roles per panel | 20 on reaction panels, 25 on select panels |
| Panels per server (dashboard) | 25 |
| Panels per server (commands) | No limit |
| Roles you can bind | Normal roles below both your top role and the bot's top role, without dangerous permissions such as Administrator. Roles managed by an integration cannot be used. |

Reaction role limits are the same for free and Premium servers.

## Good to know

- `!rr post` deletes the panel's earlier posted message and posts a new one.
- After `!rr addrole` or `!rr removerole` on a panel that is already posted, the message updates and the bot adds or clears the reaction for you.
- `!rr create select` creates a select panel without an embed template. Use `!rr create <embed name> select` to use a template.
- Deleting a panel deletes its posted message too.
- Role changes made by a panel are recorded in the member's role history by Discord's audit log with the reason "Reaction role".

## From the dashboard

Open your server, then **Reaction roles**. There are two tables.

**Panels** (create, edit, post, delete):

- **Create panel.** Type (reactions or select menu), title and description. This is the only way to set the default title and text, and the only way to make a select panel without picking an embed first.
- **Settings.** Title, description, default mode, max roles per member (0 is no limit, up to 25), required role, blocked role and a Locked switch.
- **Post or Repost.** Pick a channel. Reposting deletes the old message first.
- **Delete.** Removes the panel and its message.

**Roles on panels** (add, change mode, remove):

- **Add role.** Choose the panel, emoji or label, role and an optional label. It refuses roles above the bot, integration roles and panels that already have 20 roles.
- **Mode.** Pick a binding mode for a role: normal, unique, verify, reversed, add only or remove only.
- **Remove.** Unbinds the role and clears its reaction.

Still needs commands: `!rr attach`, `!rr bind` (the swap role mode), `!rr group`, `!rr gate` on a single binding, and attaching a saved embed with `!rr create <embed name>`. See [using the dashboard](/docs/dashboard) for how to sign in.

## Troubleshooting

- **"Role Too High".** Move the bot's role above the role you want to hand out in Server Settings, then try again.
- **Reactions do not give roles.** Check the panel is not locked, the panel and binding gates, and that the panel shows as posted in `!rr`.
- **Reaction keeps disappearing.** The member failed a required or blocked role gate, went over the maximum roles, or the binding is in `verify` mode.
- **Custom emoji will not add.** The bot must be in the server the emoji belongs to.
