# Telegram AI Box

[中文](README.md) | **English**

Your own cloud server + Telegram + the AI subscription you already pay for (Claude, ChatGPT's Codex, or Google's Antigravity) gives you a Grokbot-like experience on your phone: send a message and the server gets to work. It's online 24/7, your quota is visible, and you pick the model.

Author: Chas (X: [@HiTszHei](https://x.com/HiTszHei))

Found a bug or have an idea for improvement? Feel free to open an [issue](https://github.com/chaslab/telegram-ai-box/issues).

Hooking an AI up to Telegram is easy; making it pleasant to use is the hard part. This repo is a set of Telegram components we polished for a long time. Once installed, using your AI from your phone feels close to sitting at your computer:

| Component | What it looks like in Telegram |
|---|---|
| Fixed menu | Tap the menu left of the input box: 10 common commands |
| /model, /effort | Buttons pop up under the message; tap to switch model or thinking effort, the current one is marked ✅ |
| /usage | How much quota is left, with progress bars and time to refresh |
| /status | Current model, thinking effort, scheduled tasks, session |
| /remind, /jobs | Quick reminders and the scheduled task list |
| /memory | What it remembers about you |
| Cloud desktop | A virtual desktop with Chrome on the server that the AI uses to get things done on the web |
| Toolbox | Read and write PDF / Word / Excel / PowerPoint, OCR scans, draw charts, all preinstalled |
| /desk takeover | For logins, captchas and payments, the AI opens the page and sends a card; tap it to use the full-screen desktop yourself inside Telegram |
| /screen | Peek at what the cloud desktop is doing |
| Small habits | Every message gets a 👀 first; slow jobs post "⏳ working…" and delete it when done |

The bot's replies and menus are in Chinese by default; it follows your language when you write in another one.

## Why run your own
| | Hosted assistant (e.g. Grokbot) | Your own server + this kit |
|---|---|---|
| When idle | Sleeps, sandbox may be rebuilt | Never sleeps, everything you installed stays |
| Quota | Set by the platform, not visible | Your own subscription, /usage any time |
| Model, thinking effort | The platform picks | You pick, tap a button to switch |
| Cost | Platform subscription | The AI subscription you already have + a server |

## How to install
1. Get a server outside mainland China (Ubuntu 24.04, about 4 GB RAM; choose a region your AI service supports, such as the US, Japan or Singapore).
2. Send this sentence to the AI assistant on your own computer (Claude Code, Codex or Antigravity), and give it SSH access to the server:
   > Please deploy this server by following https://github.com/chaslab/telegram-ai-box/blob/main/INSTALL-FOR-AI.md.
3. It installs all three (Claude, Codex, Antigravity), asks which subscription you have, and needs you in only three places: open the link it sends on your phone and sign in (send back the authorization code if the page shows one), create a bot with @BotFather and send it the token, and message your bot once and tell it the pairing code. To switch to another AI later, sign in to that one and change one setting.

Prefer to do it by hand? Copy the commands from [INSTALL-FOR-AI.md](INSTALL-FOR-AI.md) block by block; it's just slower. (The runbook is in Chinese; your AI reads it fine either way.)

## Which AIs are supported
| AI | How it connects to Telegram | Stability |
|---|---|---|
| Claude Code | Anthropic's official Telegram plugin + this repo's patch (buttons, menu) | Most stable, officially maintained |
| Codex | This repo's own relay in [relay/](relay/), using Codex's official app-server interface | Ours (unofficial) |
| Antigravity (Google AI Pro / Ultra) | The same relay, using Antigravity CLI's (agy) official ACP interface | Ours (unofficial) |

Neither Codex nor Antigravity has an official Telegram integration; [relay/](relay/) fills that gap: menu, model buttons, "allow / deny" buttons before running commands, reminders and scheduled tasks, cloud desktop takeover — it works like the Claude version.
**Set your expectations**: it's not an official product. Codex / Antigravity updates may change their interfaces and occasionally break something. If that happens, hand the error log (`journalctl -u tgrelay -n 100`) to your AI and let it fix `relay/tgrelay.py`.

Using a different AI: follow sections 1, 2, 3 and 5 of the runbook, then have your AI write a new backend modeled on the `Codex` and `Antigravity` classes in `relay/tgrelay.py`, with the look defined in [docs/SPEC.en.md](docs/SPEC.en.md). The last section of the runbook explains how.

## What's in the repo
| Path | Contents |
|---|---|
| `INSTALL-FOR-AI.md` | The deployment runbook, written for an AI to execute and readable by people |
| `docs/SPEC.md` | Component spec: what the menu, buttons and replies look like (Chinese and English) |
| `claude/` | The Claude Code setup: official Telegram plugin patch, menu and button scripts, fixed-format replies, autostart, instructions for the bot |
| `relay/` | The Codex / Antigravity setup: the Telegram relay (Python standard library only), small tools for the AI to send files and buttons, instructions for the bot |
| `desktop/` | Cloud desktop: virtual screen + XFCE + Chrome, starts on boot |
| `tapdesk/` | The mini app for taking over the cloud desktop from Telegram |
| `test/` | Automated test that runs the runbook as written on a fresh Ubuntu machine, with a fake Telegram and fake AIs |

## Notes
- The bot has root on this server and can run commands. Keep it to yourself; don't add it to groups.
- Don't send passwords, card numbers or verification codes in Telegram. When something needs a login, use /desk and do it yourself.
- Follow your AI provider's terms, and put the server in a region the provider supports.
- The Claude patch modifies the official Telegram plugin; reapply it after plugin updates (have your AI follow runbook section 4.4).
- A few sites with strict bot checks (strict Cloudflare settings) may not pass in a cloud server's browser; do those on your phone.

## License
[PolyForm Noncommercial 1.0.0](LICENSE): free for personal and other noncommercial use, modification and sharing; keep the author notice and the link to this repo. For commercial use, please contact the author first. For the Claude plugin patch, see [NOTICE](NOTICE).
