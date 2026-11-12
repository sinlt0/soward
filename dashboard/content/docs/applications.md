---
title: Applications
description: Staff, partner and member applications with step-by-step forms, reviews, votes, interviews and exports.
order: 46
group: Community
---

## How it works

You create one or more **application forms**, add questions, point each form at a private review channel and post an apply panel. Members press a button and answer in a private step-by-step form that only they can see. When they submit, the application appears in the review channel with Accept, Deny and Interview buttons and staff vote buttons. The applicant gets a direct message with the result.

## Quick start

```
!application create staff Staff Application
!application question add staff paragraph Why do you want to join the team?
!application question add staff text How old are you?
!application question add staff choice Which role are you applying for?
!application question options staff 3 Moderator | Event host | Ticket team
!application set staff channel #staff-applications
!application roles staff reviewers add @Manager
!application roles staff accept_add add @Staff
!application panel #apply staff
```

## Question types

| Type | What the applicant sees |
| --- | --- |
| `text` | A short answer box, up to 200 characters. |
| `paragraph` | A long answer box, up to 1000 characters. |
| `choice` | A dropdown to pick one option. |
| `multi` | A dropdown to pick several options. |
| `yesno` | A dropdown with Yes and No. |

Up to five text questions in a row are shown in one pop-up form. Choice questions are shown one at a time. Applicants can go back, edit their answers and review everything before they press **Submit**. Questions can be made optional with `application question required <form> <number> off`. A form can have up to 25 questions, or 40 with Premium.

## Settings

Use `!application set <form> <setting> <value>`.

| Setting | What it does |
| --- | --- |
| `title`, `description` | The name and description shown to applicants. |
| `color` | The accent colour, for example `#FF69B4`. |
| `channel` | The review channel where applications are posted. Required. |
| `enabled` | Opens or closes the application. `!application open <form>`, `!application close <form>` and `!application toggle <form>` do the same. |
| `cooldown` | Hours before someone can apply again after a denial or withdrawal. |
| `account_age` | The minimum Discord account age in days. |
| `join_age` | The minimum time in the server in days. |
| `slots` | Closes the application automatically after this many acceptances. 0 means unlimited. |
| `thread` | Opens a staff discussion thread on every application. |
| `votes` | Shows staff upvote and downvote buttons. |
| `require_reason` | Staff must give a reason when denying. |
| `autodeny_leave` | Denies a pending application when the applicant leaves the server. |
| `interview_category` | The category for interview channels. |
| `dm_submit`, `dm_accept`, `dm_deny` | The direct messages sent to the applicant. Variables: `{user}`, `{username}`, `{server}`, `{form}`, `{id}`, `{reason}`. |


## Opening and closing

Turn an application off with `!application close staff` (or `off`) and back on with `!application open staff` (or `on`). `toggle` flips it. The dashboard switch does the same.

While an application is closed:

- Its button on every apply panel turns **red** and reads "Staff: Closed". The panel's color turns red when every form on it is closed. In a panel with a dropdown the option says "(Closed)".
- Anyone who presses it is told privately that applications are currently closed. Nothing is started.
- Applications that were already submitted can still be reviewed, accepted and denied.

Panels update by themselves within a minute of any change, including closing from the dashboard or when all spots are filled. Only panels posted with `!application panel` or by a template after this update are tracked. Post a panel again to bring an older one in line.

## Role lists

Use `!application roles <form> <list> <add|remove|clear> [roles]`.

| List | What it does |
| --- | --- |
| `ping` | Pinged when an application arrives. |
| `required` | Applicants must have all of these roles. |
| `blocked` | Applicants with any of these roles cannot apply. |
| `reviewers` | Can accept, deny, vote and open interviews. Without reviewers only members with Manage Server can review. |
| `accept_add` and `accept_remove` | Given or removed when an application is accepted. |
| `deny_add` and `deny_remove` | Given or removed when an application is denied. |

Zyro's top role must be above the roles it gives or removes.

## Reviewing

- **Accept** gives and removes the roles, sends the accepted message and updates the review post.
- **Deny** asks for a reason, which is sent to the applicant.
- **Interview** creates a private channel with the applicant and the reviewers. The channel is kept until you delete it.
- **Upvote and Downvote** let reviewers show their opinion. Pressing again removes the vote.
- Reviewers cannot decide their own application unless they are administrators.

## Commands

| Command | What it does | Needs |
| --- | --- | --- |
| `!application mine` | Shows your applications and their status. | Anyone |
| `!application withdraw <id>` | Withdraws one of your pending applications. | Anyone |
| `!application list [form] [status]` | Lists applications. The default status is pending. | Reviewer |
| `!application view <id>` | Shows an application with every answer. | Reviewer |
| `!application accept <id> [note]` | Accepts an application. | Reviewer |
| `!application deny <id> [reason]` | Denies an application. | Reviewer |
| `!application stats [form]` | Shows counts and the acceptance rate. | Manage Server |
| `!application export [form]` | Exports applications to a CSV file. | Manage Server |
| `!application forms` and `!application info <form>` | Lists forms and shows one form's settings. | Manage Server |
| `!application question add\|edit\|remove\|move\|required\|options\|list` | Manages questions. | Manage Server |
| `!application panel #channel <forms>` | Posts an apply panel. Up to five forms use buttons, more use a dropdown. | Manage Server |
| `!application apply <form>` | Posts an apply button for one form. | Manage Server |

`application` can also be typed as `app`, `apps` or `applications`.

## Good to know

- Applicants need direct messages open to get their result.
- Each applicant can have one pending application per form. Accepted applicants cannot apply to the same form again.
- Deleting a form keeps its past submissions, and exports still include them.
- Free servers can have 5 forms. Premium servers can have 25.
- Questions, roles and messages are built with commands. Reviewing and cleanup settings are also on the dashboard.

## Delete interview channels automatically

`application autodelete <form> <on|off> [minutes]` deletes the interview channel after an application is accepted or denied. Use `0` minutes to delete it right away, or up to 1440 (one day) to give staff time to say goodbye. Without it, interview channels stay until you delete them. The applicant is told how long the channel has left, and the cleanup survives bot restarts.

## Dashboard

Open **Applications** in the dashboard to:

- See pending applications with **Read**, **Accept**, **Deny** and **Interview** buttons. Deny asks for a reason, and it is required when the form requires one.
- See recent decisions and who made them.
- Change each form's status, review channel, reason requirement and interview cleanup.

Dashboard decisions run as you. You need Manage Server or a reviewer role for the form, and you cannot review your own application. Roles, DMs and the review post update exactly as if you used the buttons in Discord.

The Dating v2 [server template](/docs/server-templates) creates a ready-made `staff` form with five scenario questions and posts its panel. Re-running the template updates the questions and roles but keeps the accepted count and whether the form is open.
