# Unified bot UX spec v2

[中文](SPEC.md)

Goal: whatever model a bot runs on (Claude, Gemini or anything else), the user sees the same menus, buttons and messages in Telegram, and they behave the same way.
**Each bot implements features in its own way, but the look and feel stay identical.** 

## 0. Languages

- Two languages ship built in: **Chinese** and **English**.
- Any other language is not bundled. The user's own AI reads this English version, translates it, and sets up its own copy.
- **Menus:** Telegram chooses the menu language by the **Telegram app's interface language**, not the language the user chats in. Many people chat in Chinese with an English interface.
  - **Personal bot (one user):** set the menu with chat scope (`scope: {"type":"chat","chat_id":<user id>}`) and **no `language_code`**, in the language the user chats in. They see that set whatever their app language is.
  - **Public bot:** set two default-scope sets: `language_code: "zh"` for Chinese, and one without `language_code` for English.
  - A chat-scoped menu takes priority over default-scope menus.
- **Replies:** answer in the user's language. Every fixed format below has a Chinese and an English version.

## 1. Menu (setMyCommands)

The order and wording are fixed. Don't use emoji or bracketed notes.

| # | Command | English | Chinese | Required? |
|---|---|---|---|---|
| 1 | /desk | Take over cloud desktop | 远程接管云电脑 | if TapDesk is installed |
| 2 | /new | New conversation | 开新对话 | if possible |
| 3 | /remind | Quick reminder | 快捷设提醒 | if possible |
| 4 | /jobs | Scheduled tasks | 管理定时任务 | if possible |
| 5 | /memory | Long-term memory | 查看长期记忆 | if possible |
| 6 | /usage | Usage limits | 查额度 | yes |
| 7 | /model | Choose model | 选模型 | yes |
| 8 | /effort | Thinking effort | 思考强度 | yes (skip if the backend has no such setting) |
| 9 | /status | Current settings | 当前设置 | yes |
| 10 | /screen | Cloud desktop screenshot | 云电脑截屏 | if the bot has a cloud desktop |
| last | /help | Help | 帮助 | yes |

- **Omit what the bot can't do.** Never add an entry that only replies "not supported".
- **New features:** add the row to this table first (position plus both labels), then implement it in each bot.
- **Watch for interception.** Some relays or plugins handle /status and /help themselves; the official Claude Code Telegram plugin does. Make them forward these to the AI, or have the relay reply in the formats below.

## 2. Choice buttons (/model, /effort and any other choice)

- **Inline buttons only**, attached under the message.
  - Never use a reply keyboard, the kind that sits under the input box: it blocks typing and keeps popping back up.
- **Title:** `Choose model (current: X)` or `Choose thinking effort (current: X)`.
- **Current choice:** prefix the current option with `✅ `.
- **Model buttons:** 2 per row, labelled with the model name, plus a last row on its own: `Default (follow <app>)`.
- **Effort buttons:** 1 per row: `low`, `medium`, `high`, `xhigh`, `max`, plus a last row on its own: `Default (follow model)`.
- **List only options this bot can actually use.** Claude has Opus and Gemini doesn't, so each bot lists its own.
- **After a tap:**
  - Show a toast: `Switched: X` (or `Selected: X` for a generic choice).
  - Edit the original message:
    - Model: `Model switched to: X`, then on a new line `(Same conversation; takes effect from your next message)`
    - Effort: `Thinking effort switched to: X`, then on a new line `(Takes effect from your next message)`
    - Anything else: the original text, a blank line, then `✅ Selected: X`
- **Ignoring the buttons is fine.** The user can keep typing as normal.

## 3. Fixed reply formats

**/status**
```
Model: X
Thinking effort: X
Tool permissions: all auto-approved | auto-approved (with safety checks) | chat only, no commands
Background: idle | working (N queued)
Scheduled tasks: N (time zone: Asia/Singapore)
Conversation: <session id or "(new)">
```

**/usage** (shows the remaining percentage as a 10-cell bar)
```
<App> usage
5-hour left: ▓▓▓▓▓▓▓▓▓░ 92%
   Refreshes in 3h 52m
This week left: ▓▓▓▓▓▓▓▓▓▓ 99%
   Refreshes in 153h 16m
```

**/jobs** (when there are none)
```
No scheduled tasks or reminders (time zone: Asia/Singapore).

Examples:
· /remind 20m drink water
· /remind 18:30 meeting
· Or just tell me, e.g. "send me a tech news brief every morning at 8"
```
When there are tasks, show one line per task, each with "Pause/Resume" and "🗑 Delete" buttons.

**/memory**
```
Long-term memory

· <one memory>
· ...
```

**/help**
```
<App> 24-hour assistant
Send text, photos, voice, video or files: I continue the current conversation
/desk Take over the cloud desktop (port closes automatically afterwards)
/new Start a new conversation
/remind Quick reminder (e.g. /remind 20m drink water)
/jobs View and manage scheduled tasks and reminders
/memory View long-term memory
/usage Usage limits
/model Choose model
/effort Thinking effort
/status Current settings
/help Help
```
List only the commands that are actually in the menu.

**/screen:** by default, screenshot **the bot's own cloud desktop** (the one /desk takes over) and send the image. Screenshot another machine (e.g. the user's home PC) only when the user asks for it.

**/desk:** run `tapdesk/card.py "User opened the cloud desktop"`. This sends a "🖥 Computer · action needed" card with a screenshot and a "🖥 Take over" button. See tapdesk/README.md.

## 3.5 Whose computer, and sharing one

- **Each bot operates its own computer by default** (its own cloud desktop). /desk and /screen always refer to that one.
- Operating anyone else's computer (the user's home PC, another bot's server) is **not a menu item**. Do it only when the user explicitly asks in chat.
- **Every bot has /desk and /screen.** "Someone else is using the desktop" is not a reason to leave them out.
- When several bots on one server share a cloud desktop, they take turns with the `tapdesk/deskctl.sh` occupancy lock:
  - **Before touching the desktop or browser:** `deskctl.sh acquire <your name> "<what you're doing>"`.
  - **If it returns BUSY** (another bot holds it), send the user a message with buttons:
    ```
    The cloud desktop is being used by <other bot> for: <task> (N min)
    [Let it continue (default)] [Take over]
    ```
    - **No tap** means the default: let it continue. Wait (try acquire again in a few minutes) or do the parts that don't need the desktop.
    - **"Take over":** `deskctl.sh preempt <you> "<task>"`.
  - **Between steps:** `deskctl.sh beat <you>`. On PREEMPTED, stop immediately, tell the user "X took the desktop, pausing", and resume once it's free.
  - **When done:** `deskctl.sh release <you>`.
  - **User takeover:** when the user taps "🖥 Take over", TapDesk preempts every bot as `user`. The lock is released when they tap "Done" or close the page.
  - **/screen:** looking (a screenshot) needs no lock.

## 4. General habits

- **Format:** plain text in the user's language; no raw Markdown symbols, no HTML.
- **Acknowledge:** react 👀 to every incoming message first.
- **Slow work:**
  1. Send "⏳ Working on…".
  2. When done, send the result as a new message.
  3. Delete the ⏳ message.
- **Hands-on steps belong to the user.** For captchas, logins, passwords, verification codes and payments, send the /desk takeover card and let the user do it. The bot never does these steps itself.
- **Never echo secrets.** That covers keys, tokens, subscription links and verification codes.


