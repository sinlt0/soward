---
title: Custom commands
description: Build your own commands and auto-responses with triggers, variables, conditions and actions.
order: 30
group: Community
---

## How custom commands work

A custom command is a trigger plus a response. When a message (or a reaction, or a timer) matches the trigger, the bot builds the response, fills in variables, runs any action tags, and posts the result in the channel.

- Everything is managed with the `!cc` command group. Aliases: `!customcommand`, `!customcmd`.
- A custom command never overrides a built-in command. If a message is already a valid bot command, the bot runs that and ignores custom commands.
- When a new command is added, its trigger cannot match the name or alias of an existing bot command.
- Only the first matching command runs for a message.
- There is no free or premium difference. Every server gets the same limits.

## Quick start

```
!cc add hello Hey {user}, welcome to {server}!
!hello
```

By default `!cc add` creates a **command** trigger: members type your prefix plus the trigger. Now make it fancier:

```
!cc addresponse hello Hi {username}!
!cc cooldown hello 30
!cc embed hello "Greeting" #7C6BF6
```

The command now picks one of its two responses at random, can be used once every 30 seconds per member, and is sent as an embed.

## Command reference

Most `!cc` subcommands need **Manage Server** (or the fake permission `manage_guild`, see [moderation](/docs/moderation)). Bot owners are always allowed. Subcommands marked "Anyone" can be used by every member.

### Creating and managing commands

| Command | What it does | Needs |
| --- | --- | --- |
| `!cc` | Shows how many custom commands the server has. | Manage Server |
| `!cc add <trigger> <response>` | Creates a command. The trigger is one word (use quotes for spaces) up to 50 characters, the response up to 4000. | Manage Server |
| `!cc remove <trigger>` | Deletes a command. Alias: `!cc delete`. | Manage Server |
| `!cc edit <trigger> <response>` | Replaces the first response. | Manage Server |
| `!cc rename <old> <new>` | Changes a trigger. | Manage Server |
| `!cc copy <source> <new trigger>` | Copies a command with all its settings. Usage count starts at 0. | Manage Server |
| `!cc toggle <trigger>` | Turns a command on or off. | Manage Server |
| `!cc enableall` | Turns every command on. | Manage Server |
| `!cc disableall` | Turns every command off. | Manage Server |
| `!cc purge` | Deletes every custom command after you confirm. | Manage Server |
| `!cc describe <trigger> <text>` | Saves a note about the command (first 200 characters are kept). | Manage Server |
| `!cc list [group]` | Lists commands with their on/off state, trigger type, cooldown and group. | Anyone |
| `!cc info <trigger>` | Shows every setting of a command and its first response. | Anyone |
| `!cc search <text>` | Searches trigger names, responses and descriptions. Shows up to 15 matches. | Anyone |
| `!cc stats` | Shows total uses and the 10 most used commands. | Anyone |
| `!cc id <trigger>` | Shows a command's numeric ID. | Anyone |
| `!cc variables` | Shows the variable list in Discord. Alias: `!cc vars`. | Anyone |
| `!cc actions` | Shows the action tag list in Discord with page buttons. Alias: `!cc acts`. | Anyone |

### Triggers

| Command | What it does | Needs |
| --- | --- | --- |
| `!cc triggertype <trigger> <type>` | Sets the trigger type. Alias: `!cc tt`. Types are listed below. | Manage Server |
| `!cc casesensitive <trigger>` | Switches case sensitivity on or off. Alias: `!cc cs`. | Manage Server |
| `!cc interval <trigger> <minutes> [#channel]` | Makes the command run on a timer. Sets the type to `interval`. | Manage Server |
| `!cc reaction <trigger> <emoji> [message ID]` | Makes the command run on a reaction. Sets the type to `reaction`. | Manage Server |
| `!cc exec <trigger or ID> [args]` | Runs a command right now. Alias: `!cc run`. | Manage Server |

### Responses

| Command | What it does | Needs |
| --- | --- | --- |
| `!cc addresponse <trigger> <response>` | Adds another response. One is picked at random each time. Alias: `!cc ar`. Up to 10 per command. | Manage Server |
| `!cc removeresponse <trigger> <number>` | Removes a response by its position (starting at 1). You cannot remove the last one. Alias: `!cc rr`. | Manage Server |
| `!cc embed <trigger> [title] [color]` | Switches embed mode on or off, and optionally sets the embed title and hex color. | Manage Server |
| `!cc deleteafter <trigger> [trigger seconds] [response seconds]` | Deletes the trigger message and/or the response after a delay. `0` turns each off. Alias: `!cc da`. | Manage Server |

### Cooldowns and restrictions

| Command | What it does | Needs |
| --- | --- | --- |
| `!cc cooldown <trigger> <seconds> [user\|global]` | Sets a cooldown. Default type is `user`. `0` removes it. Alias: `!cc cd`. | Manage Server |
| `!cc resetcd <trigger> [member]` | Clears the cooldown for one member, or for everyone if you leave the member out. | Manage Server |
| `!cc restrict <trigger> <allow\|deny\|clear> <role\|channel> [targets...]` | Controls who can use the command and where. | Manage Server |

### Groups

| Command | What it does | Needs |
| --- | --- | --- |
| `!cc group` | Shows how many groups exist. | Manage Server |
| `!cc group create <name>` | Creates a group (name up to 50 characters). | Manage Server |
| `!cc group delete <name>` | Deletes a group. Its commands stay but lose the group. | Manage Server |
| `!cc group list` | Lists groups and how many commands each has. | Anyone |
| `!cc group restrict <group> <allow\|deny\|clear> <role\|channel> [targets...]` | Applies restrictions to every command in the group. | Manage Server |
| `!cc setgroup <trigger> [group]` | Puts a command in a group. Leave the group out to remove it from its group. | Manage Server |

### Backup

| Command | What it does | Needs |
| --- | --- | --- |
| `!cc export` | Sends all commands as a JSON file. | Manage Server |
| `!cc import` | Imports commands from an attached `.json` file made by `!cc export`. | Manage Server |

Import skips triggers that already exist and stops at the server limit. Imported commands get new IDs. Groups are not exported or imported.

## Triggers

Set the trigger type with `!cc triggertype <trigger> <type>`.

| Type | Fires when | Notes |
| --- | --- | --- |
| `command` | The first word of the message, after the prefix, equals the trigger. | Default. The prefix is optional, so `!hello` and `hello` both work. |
| `starts_with` | The message starts with the trigger. | Matches the whole message text including any prefix. |
| `contains` | The trigger appears anywhere in the message. | |
| `exact_match` | The whole message equals the trigger. | |
| `regex` | The trigger, read as a regular expression, matches somewhere in the message. | The trigger must be a valid regex or the change is refused. |
| `message_edit` | A member edits a message and the new text contains the trigger. | Set with `!cc triggertype`. Edits that only change embeds or links do not fire it. `{before}` holds the old text. |
| `reaction` | A member adds the set reaction. | Set with `!cc reaction`. |
| `interval` | A timer runs out. | Set with `!cc interval`. |

Things to know:

- The trigger is stored exactly as you typed it for matching, and looked up case-insensitively by name. Matching ignores case unless you turn on case sensitivity, and then it matches the case you typed.
- Regex triggers keep their exact text, so `\S` and `\D` work as written. Only the first 500 characters of a message are tested.
- To create a trigger with a space, put it in quotes, then change its type: `!cc add "good morning" Morning!` followed by `!cc triggertype "good morning" contains`.
- Bots and direct messages never trigger custom commands.

### Reaction triggers

`!cc reaction <trigger> <emoji> [message ID]` runs the command when a member adds that emoji. With a message ID it only reacts to that message, otherwise to any message in the server. For a custom emoji use the emoji itself, for example `<:name:123456789>`. The response posts in the channel where the reaction happened. Restrictions, cooldowns and the usage counter apply.

### Interval triggers

`!cc interval <trigger> <minutes> [#channel]` posts the response on a timer. Minutes must be from 1 to 10080 (7 days). The channel defaults to the current one. The first post comes after one full interval. The bot checks timers once a minute, so posts can be up to a minute late. A disabled command does not post.

### Reaction and interval limits

These two types have no triggering message, so they can only use a small set of variables (see below). Action tags that do not need a message still run: roles, moderation and nicknames work on the member who reacted (reaction triggers only), and channel, message and role-management tags work in both. Tags that need the triggering message, such as `{silentdelete}` and `{react}`, do nothing. Embed builder tags work.

## Responses

- A response can be up to 4000 characters.
- A command can hold up to 10 responses. One is chosen at random each time it runs.
- Turn on embed mode with `!cc embed <trigger> [title] [color]`. The response becomes the embed description. Running the command again turns embed mode off, so check the reply to see which state you are in. Put titles with spaces in quotes.
- You can also build the embed from inside the response with the embed builder action tags.
- You can use random blocks inside a single response: `{random}one{|}two{|}three{endrandom}` picks one option each time.

## Variables

Variables are written in braces and replaced when the command runs. Names are lowercase. Anything that is not a known variable is left as typed.

### Message-based triggers (command, starts_with, contains, exact_match, regex, `!cc exec`)

| Variable | Output |
| --- | --- |
| `{user}` | Mentions the member. |
| `{username}` | The member's display name. |
| `{userid}` | The member's ID. |
| `{usertag}` | The member's username. |
| `{useravatar}` | Link to the member's avatar. |
| `{server}` | Server name. |
| `{serverid}` | Server ID. |
| `{servericon}` | Link to the server icon, empty if there is none. |
| `{membercount}` | Member count. |
| `{channel}` | Mentions the channel. |
| `{channelname}` | Channel name. |
| `{channelid}` | Channel ID. |
| `{args}` | Everything typed after the first word, as one string. |
| `{arg1}`, `{arg2}`, ... | Each word after the first word. |
| `{argscount}` | How many words come after the first word. |
| `{msgid}` | ID of the message. |
| `{msglink}` | Link to the message. |
| `{timestamp}` | The time of the message as a Discord timestamp that shows in each viewer's own time zone. |
| `{match0}` | The whole text matched by a `regex` trigger. |
| `{match1}`, `{match2}`, ... | Capture groups from a `regex` trigger. Empty if the group did not match. |

### Reaction triggers

`{user}`, `{username}`, `{userid}`, `{server}`, `{serverid}`, `{membercount}`, `{channel}`, `{channelname}`, `{channelid}`, `{emoji}` (the reaction used) and `{msgid}` (the message reacted to).

### Interval triggers

`{server}`, `{serverid}`, `{membercount}`, `{channel}`, `{channelname}` and `{channelid}`.

## Conditions

Use `{if ...}...{else}...{end}` to change the response. The `{else}` part is optional.

```
{if arg1 == yes}You said yes!{else}You said something else.{end}
{if argscount > 2}That is a lot of words.{end}
{if hasarg 1}Hello {arg1}!{else}Tell me your name: !hello <name>{end}
```

| Condition | True when |
| --- | --- |
| `hasrole Role` | The member who triggered the command has that role. Use `{if not hasrole Role}` for the opposite. |
| `name == value` | The variable equals the value. |
| `name != value` | The variable does not equal the value. |
| `name > value`, `>=`, `<`, `<=` | Both sides are numbers and the comparison holds. |
| `hasarg N` | Argument number N was given and is not empty. |

Rules:

- Write the variable name without braces, for example `arg1`, not `{arg1}`.
- The value is a single word. Comparison is exact, including case.
- If the left side is not a known variable, it is compared as plain text.
- Any other condition text, such as a role check, is always treated as true. Only the conditions in the table are supported.
- Conditions can be nested up to 5 levels.

## Action tags

Action tags do things instead of (or as well as) sending text. They are written as `{action:value}`, run when the command fires, and are removed from the message before it is sent. Use `|` to separate parts of a value. If an action fails, for example because the bot lacks permission, it is skipped without an error.

Tags that take no value work with or without the colon, for example `{noresponse}`.

Action tags run for message triggers, `!cc exec`, and in a reduced form for reaction and interval triggers. Run `!cc actions` in Discord to see the same list with page buttons.

Text that members type into variables such as `{args}` is never treated as a tag, and mentions inside it are neutralised, so members cannot inject actions. Role tags refuse managed roles, roles above the bot, and roles with dangerous permissions. Moderation tags refuse the server owner, the bot, and members whose highest role is at or above the bot's.

Anyone who is allowed to use the command triggers its actions. Actions such as `{ban}` and `{deleterole}` run with the bot's permissions, not the member's, so restrict powerful commands to trusted roles.

How targets are found:

- A **role** can be given by ID, mention or exact name.
- A **member** can be given by ID, mention, display name or username.
- A **channel** can be given by ID, mention or text channel name.

### Roles

| Tag | What it does |
| --- | --- |
| `{addrole:Role}` | Gives the member who triggered the command a role. |
| `{removerole:Role}` | Takes a role from that member. |
| `{togglerole:Role}` | Adds the role, or removes it if they already have it. |
| `{addroleto:Member\|Role}` | Gives a role to another member. |
| `{removerolefrom:Member\|Role}` | Takes a role from another member. |
| `{createrole:Name\|#hex}` | Creates a role. The color is optional. |
| `{deleterole:Role}` | Deletes a role. |
| `{editrole:Role\|property=value}` | Edits a role. Properties: `name`, `color` (hex), `hoist` and `mentionable` (`true` or `false`). |

### Moderation

For `{kick}`, `{ban}` and `{softban}`, if you leave out the `|` the member who triggered the command is the target.

| Tag | What it does |
| --- | --- |
| `{kick:Member\|reason}` | Kicks a member. |
| `{ban:Member\|reason}` | Bans a member without deleting messages. |
| `{softban:Member\|reason}` | Bans and immediately unbans, deleting the last 7 days of messages. |
| `{unban:user ID}` | Unbans a user by ID. |
| `{timeout:Member\|10m}` or `{mute:Member\|10m}` | Times a member out. Duration is a number followed by `s`, `m`, `h` or `d`. Default is 10 minutes. |
| `{untimeout:Member}` or `{unmute:Member}` | Removes a timeout. |
| `{warn:Member\|reason}` | Saves a warning for the member, as if the command's user had warned them. |
| `{setnick:Member\|Nickname}` | Changes a nickname (32 characters). With no `\|`, the value is a nickname for the member who triggered the command. |
| `{resetnick:Member}` | Resets a nickname. With no value, resets the nickname of the member who triggered the command. |

### Messages

| Tag | What it does |
| --- | --- |
| `{dm:message}` | Sends a direct message to the member who triggered the command. |
| `{dmmember:Member\|message}` | Sends a direct message to another member. `{dm:Member\|message}` works the same way. |
| `{sendreply:message}` | Replies to the triggering message without pinging. |
| `{sendchannel:#channel\|message}` | Sends a message to another channel after the main response. |
| `{react:emoji1,emoji2}` | Reacts to the triggering message. Up to 5 emojis. |
| `{reactremove:emoji1,emoji2}` | Removes those reactions from the triggering message. Up to 5. |
| `{silentdelete:}` or `{deletetrigger:}` | Deletes the triggering message right away. |
| `{deleteafter:seconds}` | Deletes the bot's response after that many seconds. |
| `{noresponse}` | Sends no response text. Actions still run. |
| `{log:#channel\|message}` | Posts a log line with the member's name to a channel. |
| `{sleep:seconds}` | Waits before running the next action. Maximum 60. |

### Channels

Without a value, the lock, unlock, hide and show tags use the current channel.

| Tag | What it does |
| --- | --- |
| `{createchannel:name\|Category}` | Creates a text channel. The category (name or ID) is optional. |
| `{deletechannel:#channel}` | Deletes a channel. |
| `{lockchannel:#channel}` | Stops `@everyone` from sending messages. |
| `{unlockchannel:#channel}` | Restores sending for `@everyone`. |
| `{hidechannel:#channel}` | Hides the channel from `@everyone`. |
| `{showchannel:#channel}` | Removes the hide. |

### Embed builder

These tags shape the embed that is sent. They turn on embed output by themselves; `!cc embed` is not required.

| Tag | What it does |
| --- | --- |
| `{settitle:text}` | Sets the embed title. |
| `{setcolor:#hex}` | Sets the embed color. |
| `{setfooter:text}` | Sets the footer. |
| `{setthumbnail:url}` | Sets the thumbnail image. |
| `{setimage:url}` | Sets the large image. |
| `{addfield:Name\|Value}` | Adds a field. Add more tags for more fields. |

### Example

A self-role toggle that stays quiet:

```
!cc add gamer {togglerole:Gamer}Done, I toggled your Gamer role.
!cc cooldown gamer 10
```

Order of work: conditions and random blocks are resolved first, then variables are filled in, then action tags run. So variables can be used inside tags, for example `{addroleto:{userid}|Gamer}` or `{log:#audit-log|{username} used the command}`.

## Cooldowns

`!cc cooldown <trigger> <seconds> [user|global]` limits how often a command can run.

- `user` (default): each member has their own timer.
- `global`: one timer shared by everyone.
- Members who hit a cooldown see a short message with the time left that disappears after 5 seconds.
- Cooldowns are kept in memory and reset when the bot restarts. Use `!cc resetcd` to clear one early.
- `!cc exec` ignores cooldowns and restrictions.

## Restrictions

`!cc restrict <trigger> <allow|deny|clear> <role|channel> [targets...]` accepts mentions or IDs, several at a time.

```
!cc restrict gamer allow role @Members
!cc restrict gamer deny channel #general #rules
!cc restrict gamer clear role
```

A member can use the command only if every rule passes. They are checked in this order:

1. A role in the **denied roles** list blocks the member.
2. A **denied channel** blocks the command there.
3. If there are **allowed roles**, the member needs at least one.
4. If there are **allowed channels**, the command only works in those.

Blocked members see a short "Restricted" message for 5 seconds. Restrictions on a command and on its group are added together. `clear` removes both the allow and deny lists for roles or for channels.

## Groups

Groups let you apply the same restrictions to many commands.

```
!cc group create staff
!cc group restrict staff allow role @Moderators
!cc setgroup ban-hammer staff
!cc setgroup kick-buddy staff
!cc list staff
```

Put group names with spaces in quotes when a command takes the group as a single word, such as `!cc group restrict "staff tools" ...` and `!cc list "staff tools"`.

## Limits

| Setting | Value |
| --- | --- |
| Custom commands per server | 100 |
| Groups per server | 20 |
| Responses per command | 10 |
| Trigger length | 50 characters |
| Response length | 4000 characters |
| Group name length | 50 characters |
| Description length | 200 characters |
| Interval | 1 to 10080 minutes |
| `{sleep}` | Up to 60 seconds |
| `{react}` and `{reactremove}` | 5 emojis each |

## From the dashboard

The Custom Commands page on the web dashboard lists every command with its trigger, type, response count, state and cooldown. You can:

- Create a command: trigger, response, trigger type, cooldown (0 to 86400 seconds) and cooldown type, case sensitivity, embed on or off, delete trigger and delete response delays (0 to 3600 seconds) and enabled.
- Edit those same settings and the first response of an existing command.
- Enable, disable or delete a command.

The dashboard supports the trigger types `command`, `starts_with`, `contains`, `regex` and `exact_match`. Commands that use `message_edit`, `reaction` or `interval` show up in the list and can be toggled or deleted, but must be changed with `!cc`.

Still commands only: extra responses, restrictions, groups, intervals, reaction triggers, descriptions, rename, copy, export and import, search, stats and `!cc exec`.

## Troubleshooting

- **My command does nothing**: check `!cc info <trigger>`. The command must be enabled, and the trigger type must match how you are typing it. A built-in command with the same name always wins.
- **"Reserved Name"**: the trigger matches a built-in command or alias. Pick another name.
- **A regex trigger behaves oddly**: only the first 500 characters of a message are tested, and the pattern must be valid.
- **A case-sensitive command never matches**: the message must match the case you typed when you created the trigger.
- **`{noresponse}` or `{silentdelete}` shows up in the message**: tags with no value need a colon, like `{noresponse}`.
- **An action does nothing**: the bot probably lacks the permission, or cannot find the role, member or channel. Names must match exactly, so try an ID or a mention.
- **Reaction or interval command ignores an action tag**: tags that need the triggering message do nothing, and interval commands have no member, so tags aimed at the member do nothing.
- **"Restricted" or "On Cooldown"**: see the cooldown and restriction sections. Use `!cc info` to see the current settings.
