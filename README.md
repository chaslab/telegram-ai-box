# Telegram AI 助手组件包

**中文** | [English](README.en.md)

一台自己的云服务器 + Telegram + 你自己的 AI 订阅（Claude、ChatGPT 的 Codex，或 Google 的 Antigravity），在手机上得到类似 Grokbot 的体验：发条消息，服务器就去干活；24 小时在线，额度透明，模型自己选。

作者：Chas（X：[@HiTszHei](https://x.com/HiTszHei)）

用着有 bug 或有改进想法，欢迎在 [Issues](https://github.com/chaslab/telegram-ai-box/issues) 留言。

把 AI 接到 Telegram 上不难，难的是用起来顺手。这个仓库照着 Grokbot 的高频用法，打磨了一套 Telegram 组件。装上以后，在手机上用你自己的 AI，体验跟 Grokbot 差不多，而且额度透明、模型自己选，服务器 24 小时在线，在 Telegram 里点点按钮就能操作：

<!-- 截图：菜单 / 选模型按钮 / 查额度 / 接管云电脑 -->

| 组件 | 在 Telegram 里是什么样 |
|---|---|
| 固定菜单 | 点输入框左边的菜单，10 个常用命令，中文 |
| /model、/effort | 消息下面弹出按钮，点一下就换模型、换思考强度，当前的打 ✅ |
| /usage | 额度还剩多少，进度条 + 多久后刷新 |
| /status | 当前模型、思考强度、定时任务、会话 |
| /remind、/jobs | 快捷提醒、定时任务列表 |
| /memory | 它记住了你哪些事 |
| 云电脑 | 服务器上一个带 Chrome 的虚拟桌面，AI 用它上网办事 |
| 工具箱 | 读写 PDF / Word / Excel / PPT、扫描件识字、画图表，装好就能用 |
| /desk 接管 | 碰到登录、验证码、付款，AI 把页面打开好，发一张卡片，你在 Telegram 里点开全屏桌面亲手操作 |
| /screen | 随时看一眼云电脑在干嘛 |
| 小习惯 | 收到消息先回 👀；慢活先发"⏳ 正在…"，做完删掉 |

## 为什么要自己搭
| | 托管助手（如 Grokbot） | 自己搭 + 这套组件 |
|---|---|---|
| 闲置时 | 会休眠，可能被重建 | 不休眠，装好的东西一直在 |
| 额度 | 平台说了算，看不到 | 用你自己的订阅，/usage 随时看 |
| 模型、思考强度 | 平台选 | 你选，点按钮就换 |
| 费用 | 平台订阅 | 你本来就有的 AI 订阅 + 一台服务器 |

## 怎么装
1. 买一台海外服务器（Ubuntu 24.04，4G 内存左右；地区选你的 AI 服务支持的地方，比如美国、日本、新加坡）。
2. 把这句话发给你自己电脑上的 AI 助手（Claude Code、Codex、Antigravity 都行），再把服务器的 SSH 登录方式给它：
   > 请按 https://github.com/chaslab/telegram-ai-box/blob/main/INSTALL-FOR-AI.md 帮我把这台服务器部署好。
3. 它会把三家（Claude、Codex、Antigravity）的程序都装好，问你有哪家的订阅，然后只在三个地方需要你：在手机上打开它发的网址登录你的账号（有授权码就发回给它）、在 @BotFather 建机器人把 token 发给它、给机器人发一句话把配对码告诉它。以后想换一家，登录另一家、改一个设置就行。

不想交给 AI，也可以自己照着 [INSTALL-FOR-AI.md](INSTALL-FOR-AI.md) 一段段复制命令做，只是慢一些。

## 支持哪些 AI
| AI | 怎么接 Telegram | 稳定性 |
|---|---|---|
| Claude Code | Anthropic 官方 Telegram 插件 + 本仓库的补丁（按钮、菜单） | 最稳，官方维护 |
| Codex | 本仓库自己写的中继 [relay/](relay/)，接 Codex 官方的 app-server 接口 | 我们自己写的（非官方） |
| Antigravity（Google AI Pro / Ultra） | 同一个中继，接 Antigravity CLI（agy）官方的 ACP 接口 | 我们自己写的（非官方） |

Codex 和 Antigravity 官方都没有 Telegram 接入，[relay/](relay/) 是这个仓库补上的：菜单、换模型按钮、执行命令前的"允许 / 不行"按钮、提醒和定时任务、接管云电脑，跟 Claude 版用起来一样。
**说明一下预期**：它不是官方产品，Codex / Antigravity 升级后接口可能变化，偶尔会出小毛病。遇到问题，把报错（`journalctl -u tgrelay -n 100`）交给你的 AI，让它对照 `relay/tgrelay.py` 修。

用这几家以外的 AI：第 1、2、3、5 节照做，然后让你的 AI 参照 `relay/tgrelay.py` 里的 `Codex`、`Antigravity` 几个类写一个新的接法，外观按 [docs/SPEC.md](docs/SPEC.md) 来。部署手册最后一节有说明。

## 仓库里有什么
| 目录 | 内容 |
|---|---|
| `INSTALL-FOR-AI.md` | 部署手册，写给 AI 执行，人也看得懂 |
| `docs/SPEC.md` | 组件规范：菜单、按钮、回复格式长什么样（中英文） |
| `claude/` | Claude Code 的接法：官方 Telegram 插件补丁、菜单和按钮脚本、固定格式回复、开机自启、给机器人的说明 |
| `relay/` | Codex / Antigravity 的接法：Telegram 中继（只用 Python 标准库）、给 AI 发文件和按钮的小工具、给机器人的说明 |
| `desktop/` | 云电脑：虚拟屏幕 + XFCE + Chrome，开机自启 |
| `tapdesk/` | 在 Telegram 里接管云电脑的小程序 |
| `test/` | 在全新 Ubuntu 上按部署手册原样跑一遍的自动测试，含假 Telegram 和假 AI |

## 注意
- 机器人有这台服务器的最高权限，能执行命令。只给你自己用，不要拉进群。
- 不要在 Telegram 里发密码、银行卡、验证码。需要登录时用 /desk 自己点。
- 用 AI 订阅要遵守服务商的条款，服务器放在服务商支持的地区。
- Claude 版的补丁改的是官方 Telegram 插件，插件更新后要重新打（让你的 AI 照部署手册 4.4 节做）。
- 少数网站的人机验证（Cloudflare 设得严的）在云服务器的浏览器里可能过不去，这类网站在手机上操作。

## 许可 / License
[PolyForm Noncommercial 1.0.0](LICENSE)：个人和非商业用途免费使用、修改、分享，请保留作者和本仓库链接；商业用途请先联系作者。Claude 插件补丁部分见 [NOTICE](NOTICE)。
Free for personal and other noncommercial use; keep the author notice and repo link. For commercial use, please contact the author first.
