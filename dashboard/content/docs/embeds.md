---
title: Embeds
description: Build reusable embed templates and use them in greetings, panels and the dashboard.
order: 31
group: Community
---

## How embeds work

An embed template is a saved, styled message card with a title, description, color, images, footer and fields. You build it once with `!embed`, give it a name, and then reuse it anywhere by writing `{embed:name}`.

- Templates are saved per server. Names are lowercase and can contain letters, numbers, `_` and `-`, up to 50 characters.
- Placeholders such as `{user}` and `{server}` inside a template are filled in each time it is sent.
- Templates are used by [greetings](/docs/greetings) (as `{embed:name}` in the message or attached with `!greetings embed`), by verification messages, and by reaction role panels.
- You can build and send templates from the web dashboard too.

## Quick start

```
!embed create welcome
```

This opens the interactive builder. Use the buttons to set a title, description, color and so on. Every change is saved immediately. Press **Preview** to see how it looks, then **Done**.

Use it anywhere with:

```
{embed:welcome}
```

For example, make it the join message:

```
!greetings message join {embed:welcome}
```

## The builder

`!embed create <name>` and `!embed edit <name>` open the builder. Only the person who opened it can use the buttons, and it stops responding after 10 minutes (run `!embed edit <name>` to open it again).

| Button | What it sets |
| --- | --- |
| Title | Title (up to 256 characters) and an optional link that makes the title clickable. |
| Description | Main text (up to 4000 characters). |
| Color | A hex color such as `#7C6BF6`. |
| Author | Author text (up to 256 characters), an icon URL and an optional link. |
| Footer | Footer text (up to 2048 characters) and an icon URL. |
| Image | Large image URL. |
| Thumbnail | Small image URL, shown in the corner. |
| Toggle Timestamp | Shows the time the embed was sent. |
| Preview | Shows you the embed with your own details filled in. Only you see it. |
| Add Field | Adds a field with a name (up to 256), a value (up to 1024) and an inline yes or no. |
| Remove Last Field | Removes the newest field. |
| Done | Closes the builder and shows how to reference the template. |

Leaving a box empty clears that part. Image and link URLs must be valid addresses starting with `http://` or `https://` or Discord will reject the embed when it is sent.

## Command reference

`!embed` needs **Manage Server** (or the fake permission `manage_guild`). Bot owners are always allowed. Subcommands marked "Anyone" can be used by all members.

| Command | What it does | Needs |
| --- | --- | --- |
| `!embed` | Shows how many templates you have and the limit. | Manage Server |
| `!embed create <name>` | Creates a template and opens the builder. | Manage Server |
| `!embed edit <name>` | Opens the builder for an existing template. | Manage Server |
| `!embed delete <name>` | Deletes a template after you confirm. | Manage Server |
| `!embed rename <old> <new>` | Renames a template. | Manage Server |
| `!embed duplicate <name> <new name>` | Copies a template and its fields under a new name. Alias: `!embed copy`. | Manage Server |
| `!embed list` | Lists templates with a short preview and their `{embed:name}` tag. | Anyone |
| `!embed preview <name>` | Posts the template in the channel, with your own details filled in. | Anyone |
| `!embed variables` | Shows the placeholder list. Alias: `!embed vars`. | Anyone |

Renaming or deleting from commands does not update places that already use the old name. After a rename, update your `{embed:old}` references. If a message refers to a template that does not exist, the embed is simply left out.

## Placeholders

These placeholders work in any text part of a template (title, description, author, footer, field names and values, and the link and image URLs). They are replaced when the embed is sent. Unknown placeholders are left as typed.

| Placeholder | Output |
| --- | --- |
| `{user}` | Mentions the member. |
| `{username}` | The member's display name. |
| `{usertag}` | The member's username. |
| `{userid}` | The member's ID. |
| `{useravatar}` | Link to the member's avatar. Handy for thumbnail URLs. |
| `{userjoindate}` | When the member joined the server, as a Discord timestamp. |
| `{usercreated}` | When the member's account was created, as a Discord timestamp. |
| `{server}` | Server name. |
| `{serverid}` | Server ID. |
| `{servericon}` | Link to the server icon. Empty if there is none. |
| `{membercount}` | Member count. |
| `{boostcount}` | Number of boosts the server has. |
| `{channel}` | Mentions the channel the embed is sent in, when it is known. |
| `{channelname}` | Channel name, when it is known. |
| `{channelid}` | Channel ID, when it is known. |

Which member and channel the placeholders describe depends on where the embed is used. With `!embed preview` and the builder preview it is you and the current channel. In a greeting it is the member who joined, left, boosted or was banned (channel placeholders are not filled in greetings). From the dashboard **Send** button it is you and the channel you picked.

Templates also support conditions and random text, the same as other messages:

```
{if membercount > 100}We are growing fast!{else}Small and cozy.{end}
{random}Welcome!{|}Hello there!{|}Glad you are here!{endrandom}
```

Conditions compare a placeholder name (written without braces) to a single word using `==`, `!=`, `>`, `>=`, `<` or `<=`. Any other condition text is treated as true.

## Using an embed in a message

Anywhere that supports `{embed:name}` you can mix text and embeds. Text outside the tag is sent as normal message text, and each `{embed:name}` adds that embed.

```
!greetings message join Welcome {user}! {embed:welcome}
```

## Limits

| Setting | Free | Premium |
| --- | --- | --- |
| Embed templates per server | 100 | 250 |

| Setting | Value |
| --- | --- |
| Fields per embed | 25 |
| Template name length | 50 characters |
| Title | 256 characters |
| Description | 4000 characters |
| Footer | 2048 characters |
| Field name / value | 256 / 1024 characters |

See [Premium](/docs/premium) for how to unlock the higher limit.

## From the dashboard

The Embeds page on the web dashboard lists every template with its preview text, number of fields and its `{embed:name}` tag. You can:

- Create a template. The form has name, title and title link, description, color, author name, icon and link, footer text and icon, image, thumbnail, a timestamp switch and a fields box. Write fields one per line as `name | value | inline` (leave out `inline` to stack it). A template needs at least a title, description, author, footer, image, thumbnail or field.
- Edit every one of those settings in the same form. Saving replaces the template's fields with the lines in the box.
- Send a template to any channel. The bot needs Send Messages and Embed Links there. Placeholders are filled in with you as the member, and mentions in the embed do not ping anyone.
- Copy, rename and delete a template.

On the dashboard, renaming a template also updates the greeting settings that use it, and deleting one removes it from greetings that used it. The commands do not do this.

Everything about templates can be done on the dashboard. The interactive builder with live preview buttons and `!embed preview` are Discord only.

## Troubleshooting

- **"Invalid Name"**: use only letters, numbers, `_` and `-`.
- **"Limit Reached"**: delete templates you no longer use, or get Premium for a higher limit.
- **The embed does not show up**: check the name in `{embed:name}` matches exactly and that the template exists with `!embed list`.
- **Discord rejects the embed**: check that image and link URLs are valid and start with `http://` or `https://`.
- **The builder buttons stopped working**: it times out after 10 minutes. Run `!embed edit <name>` again.
