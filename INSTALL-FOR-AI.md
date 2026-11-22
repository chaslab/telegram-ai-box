# 部署手册（写给 AI 执行）

> 读这份文档的是 AI 助手（Claude Code、Codex、Antigravity 等，在用户自己的电脑上运行）。
> 你的任务：把一台全新的 Ubuntu 24.04 服务器部署成用户的 Telegram AI 助手（下面简称"机器人"）。
> 用户只需要做三件事：在手机上打开你发的网址登录自己的 AI 账号、在 @BotFather 建一个机器人、给机器人发一句话拿配对码。其他都由你来做。每完成一节，用一两句话告诉用户进度。
> 人也可以自己照着做：把每个代码块复制到服务器终端里运行就行，只是慢一些。
> 来源：https://github.com/chaslab/telegram-ai-box （作者 Chas，PolyForm Noncommercial 许可：个人免费使用，商用请先联系作者）。机器人 /help 末尾的反馈链接请保留。

## 规矩
- 只在用户给你的这台服务器上操作。不要碰用户电脑上的其他东西。
- **账号密码只在用户自己的浏览器里输入**。登录时你把网址发给用户，用户在手机或电脑上打开、登录；页面给的授权码、@BotFather 给的机器人 token，用户发给你，你填到服务器上。
- 授权码和 token 只写进下文指定的位置，不要写进别的文件，回复里不要重复显示。用户介意 token 经过你的话，让他自己 SSH 进服务器粘贴，下文每一步都写了对应命令。
- 每条命令先说清楚是干什么的再运行。出错时先读报错，再改，不要反复硬试。
- 做完第 7 节的检查清单，再告诉用户"装好了"。

## 0. 先确认
向用户确认这几件事，缺一不可：
1. 服务器：Ubuntu 22.04 或 24.04，x86_64，至少 2 核 4G，地区在用户选的 AI 支持的国家（美国、日本、新加坡等；**中国大陆和香港不行**）。
2. 你能用 SSH 登录，并且有 root 权限。（用户把 IP 和登录方式给你；最好用 SSH 密钥。）有的云厂商默认用户是 ubuntu，登录后先 `sudo -i` 切到 root，下文所有命令都以 root 身份运行。
3. 用户有 Telegram 账号。
4. 云厂商控制台的防火墙（安全组）放行 TCP 22、80、443。
5. **问用户有哪家的订阅**（用的是他自己的订阅额度）。三家的程序第 4 节都会装上，用户只登录他要用的那一家；以后想换，登录另一家、改一个设置就行。

| 选项 | 需要的订阅 | 接 Telegram 的方式 |
|---|---|---|
| Claude | Claude Pro 或 Max | Anthropic 官方 Telegram 插件 + 本仓库补丁，最稳 |
| Codex（OpenAI） | ChatGPT Plus / Pro 等能用 Codex 的套餐 | 本仓库自己写的中继 `relay/`（官方没有 Telegram 接入） |
| Antigravity（Google） | Google AI Pro 或 Ultra | 本仓库自己写的中继 `relay/` |

记住用户的选择，下文写着 **[Claude]** 或 **[Codex / Antigravity]**（简称 **[中继]**）的地方只做对应的那条。

下文的 `<IP>` 是服务器公网 IP，`<IPDASH>` 是把 IP 里的点换成横杠（例如 1-2-3-4）。

## 1. 基础软件
<!-- ci:base -->
```bash
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl unzip git tmux python3 python3-aiohttp \
  ffmpeg xdotool x11-utils xvfb dbus-x11 xfce4 xfce4-terminal fonts-noto-cjk certbot patch
# Chrome
curl -fsSLo /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
apt-get install -y /tmp/chrome.deb
# 内存小于 8G 时加 4G swap
[ -f /swapfile ] || { fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile && echo '/swapfile none swap sw 0 0' >> /etc/fstab; }
timedatectl set-timezone Asia/Shanghai   # 按用户所在时区改
```

**工具箱**（读写文档、扫描件识字、画图、浏览器自动化）。装好后用户发来 PDF / Word / Excel / PPT / 图片，AI 直接就能处理，不用临时再装：
<!-- ci:toolbox -->
```bash
DEBIAN_FRONTEND=noninteractive apt-get install -y python3-venv poppler-utils pandoc imagemagick \
  tesseract-ocr tesseract-ocr-chi-sim libreoffice-writer-nogui libreoffice-calc-nogui libreoffice-impress-nogui
python3 -m venv /opt/tgbox/venv
/opt/tgbox/venv/bin/pip install -q playwright python-docx openpyxl python-pptx pypdf pillow matplotlib pandas
printf '#!/bin/sh\nexec /opt/tgbox/venv/bin/python "$@"\n' > /usr/local/bin/tgpy && chmod +x /usr/local/bin/tgpy   # 软链接不行：Python 认不出虚拟环境
# Playwright 只用来连云电脑里已经开着的 Chrome，不用再下载它自带的浏览器
```

## 2. 放文件
把本仓库克隆到服务器，再把文件放到固定位置：
<!-- ci:files -->
```bash
git clone https://github.com/chaslab/telegram-ai-box /opt/tgbox-src
mkdir -p /opt/tgbox /opt/clouddesk /opt/tapdesk /root/tgbot/inbox /root/tgbot/outbox
cp -r /opt/tgbox-src/claude /opt/tgbox/claude
cp -r /opt/tgbox-src/relay /opt/tgbox/relay
cp /opt/tgbox-src/desktop/desk.sh /opt/clouddesk/
cp /opt/tgbox-src/tapdesk/{server.py,index.html,card.py,deskctl.sh,deskshot.sh} /opt/tapdesk/
cp /opt/tgbox-src/tgbox.env.example /opt/tgbox/tgbox.env
chmod +x /opt/tgbox/claude/*.sh /opt/tgbox/relay/*.py /opt/clouddesk/desk.sh /opt/tapdesk/*.sh /opt/tapdesk/card.py
```
然后编辑 `/opt/tgbox/tgbox.env`：`TGBOX_AGENT` 改成用户选的 `claude`、`codex` 或 `antigravity`；`TGBOX_TZ` 改成用户时区。

## 3. 云电脑（虚拟桌面 + Chrome）
<!-- ci:desktop -->
```bash
mkdir -p /etc/opt/chrome/policies/managed
cp /opt/tgbox-src/desktop/chrome-policy.json /etc/opt/chrome/policies/managed/tgbox.json
cp /opt/tgbox-src/desktop/clouddesk.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now clouddesk
sleep 10; /opt/clouddesk/desk.sh status
/opt/tapdesk/deskshot.sh /tmp/check.jpg   # 截一张图，自己看一眼：应该是 XFCE 桌面 + 最大化的 Chrome
```
策略文件的作用：用户以后在这个浏览器里登录谷歌时，只登录网页账号，**不会把用户自己的 Chrome 书签、密码同步进来**。

## 4. 装三家 AI，登录用户选的那家

### 4.1 安装（三家都装，都要做）
<!-- ci:claude-install -->
```bash
# Claude Code。这台机器专门给机器人用，所以装在 root 下。用 sudo -i 切到 root 时安装脚本会拒绝，这个变量就是告诉它"我是故意的"
curl -fsSL https://claude.ai/install.sh | CLAUDE_INSTALL_ALLOW_SUDO=1 bash
curl -fsSL https://bun.sh/install | bash
cp /opt/tgbox-src/claude/CLAUDE.md.template /root/tgbot/CLAUDE.md
```
<!-- ci:codex-install -->
```bash
# Codex（要 Node.js 22）
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
npm install -g @openai/codex
cp /opt/tgbox-src/relay/AGENTS.md.template /root/tgbot/AGENTS.md
```
<!-- ci:agy-install -->
```bash
# Antigravity（Google）
curl -fsSL https://antigravity.google/cli/install.sh | bash
ln -sf /root/.local/bin/agy /usr/local/bin/agy
cp /opt/tgbox-src/relay/AGENTS.md.template /root/tgbot/GEMINI.md
```
Codex 和 Antigravity 官方没有 Telegram 接入，用本仓库的 `relay/tgrelay.py`：它从 Telegram 收消息，交给 Codex（`codex app-server`）或 Antigravity（`agy acp`）这两个官方提供的程序接口，再把回复、审批按钮发回 Telegram。用的是用户自己登录的订阅，不需要 API key。

### 4.2 登录选的那一家（用户在手机上点网址）
登录程序都是交互式的，放在服务器的 tmux 里跑，你用 `tmux capture-pane -pJt login` 看屏幕（`-J` 把折行的长网址拼回一行），用 `tmux send-keys -t login ...` 代替用户按键。网址发给用户；用户只在自己的浏览器里登录账号。

- [Claude]
  ```
  tmux new-session -d -s login -x 220 -y 50 -c /root/tgbot /root/.local/bin/claude
  ```
  看屏幕逐步走：配色 → `Enter`；登录方式 → 按 `1`（Claude account with subscription）；屏幕出现登录网址 → 发给用户，用户登录、授权后页面会给一个授权码 → 用户发回给你 → `tmux send-keys -t login '<授权码>' Enter`；"信任这个文件夹" → `Enter`。
  看到输入框后装 Telegram 插件：`tmux send-keys -t login '/plugin install telegram@claude-plugins-official' Enter`，按屏幕提示选（提示找不到插件市场时，先发 `/plugin marketplace add anthropics/claude-plugins-official`）。装好后 `tmux send-keys -t login '/exit' Enter`。
- [Codex]
  ```
  tmux new-session -d -s login -x 220 -y 50 'codex login --device-auth; sleep 30'
  ```
  屏幕上有一个网址和一串代码：都发给用户，用户打开网址、登录 ChatGPT 账号、输入那串代码（这次是用户往网页里填，不用发回给你）。如果网页提示要先开启"设备代码登录"，让用户按提示到 ChatGPT 的设置 → 安全里打开，再重来。完成后 `codex login status` 应显示已登录。
- [Antigravity]
  ```
  tmux new-session -d -s login -x 250 -y 50 -c /root/tgbot 'agy acp --login; sleep 30'
  ```
  屏幕出现 Google 登录网址 → 发给用户，用户登录 Google 账号（有 AI Pro / Ultra 的那个），页面会给一个授权码（或者跳到一个打不开的页面，那就把那个页面的完整网址发回来也行）→ 用户发回给你 → `tmux send-keys -t login '<授权码或网址>' Enter`。检查：`agy -p "/usage" --output-format json` 的 `status` 应是 `SUCCESS`（这条不开对话、不花额度）。

最后 `tmux kill-session -t login`。用户想自己来的话，让他 SSH 进服务器直接运行 `claude` / `codex login --device-auth` / `agy acp --login`，照屏幕提示做。

### 4.3 建 Telegram 机器人，把 token 填到服务器
让用户在 Telegram 找 @BotFather（蓝色认证标）→ `/newbot` → 起名字 → 起一个以 bot 结尾的用户名 → 收到 token，发给你。
- [Claude]
  ```
  mkdir -p /root/.claude/channels/telegram && umask 077 && printf 'TELEGRAM_BOT_TOKEN=%s\n' '<token>' > /root/.claude/channels/telegram/.env
  ```
- [中继]
  ```
  /opt/tgbox/relay/tgrelay.py set-token '<token>'
  ```
  看到"好了，机器人是 @xxx"就对了。（用户自己来：不带参数运行，按提示粘贴。）

### 4.4 [Claude] 给官方插件打补丁、写设置
官方插件默认不支持"点按钮选择"，`/status`、`/help` 也被插件自己拦掉了：
<!-- ci:claude-patch -->
```bash
P=$(ls -d /root/.claude/plugins/cache/*/telegram/*/ | tail -1)
cd "$P" && cp server.ts server.ts.orig && patch -p1 < /opt/tgbox/claude/telegram-plugin.patch
```
补丁打不上（插件更新过）时：读补丁里的三处改动（/help、/status 转给 Claude；`say:` 开头的按钮当成用户发的文字），在新版 server.ts 里手工改成同样效果。**插件每次更新后都要重新打。**

写入 `/root/.claude/settings.json`（已有内容就合并，不要覆盖）：
```json
{
  "statusLine": { "type": "command", "command": "/opt/tgbox/claude/statusline.sh" },
  "permissions": {
    "allow": [
      "Bash(/opt/tgbox/claude/*)",
      "Bash(python3 /opt/tgbox/claude/tgfmt.py *)",
      "Bash(/opt/tapdesk/*)",
      "Bash(python3 /opt/tapdesk/card.py *)",
      "Bash(tmux send-keys -t claude-tg *)"
    ]
  }
}
```
其他操作没有放行，机器人做的时候会在 Telegram 里弹出"允许 / 拒绝"按钮，用户点了才执行。用户想放得更开，让他自己决定。

## 5. TapDesk（在 Telegram 里接管云电脑）
<!-- ci:tapdesk -->
```bash
certbot certonly --standalone -d <IPDASH>.sslip.io --agree-tos --register-unsafely-without-email -n
cp /opt/tgbox-src/tapdesk/tapdesk.env.example /opt/tapdesk/tapdesk.env
cp /opt/tgbox-src/tapdesk/tapdesk.service.example /etc/systemd/system/tapdesk.service
```
把 `/opt/tapdesk/tapdesk.env` 改成下面这样（整份替换；不要在值后面加注释）：
```
TAPDESK_OWNER=
TAPDESK_TOKEN_ENVFILE=/root/.claude/channels/telegram/.env
TAPDESK_DISPLAY=:99
TAPDESK_DESK=
TAPDESK_OMNIBOX=1
TAPDESK_OMNIBOX_Y=70
TAPDESK_UFW=0
TAPDESK_DOMAIN=<IPDASH>.sslip.io
TAPDESK_DESKCTL=/opt/tapdesk/deskctl.sh
```
- `TAPDESK_TOKEN_ENVFILE`：[Claude] 用上面这个；[中继] 改成 `/opt/tgbox/bot.env`。
- `TAPDESK_OWNER` 先空着，第 6 节配对后填。服务器开了 ufw 就把 `TAPDESK_UFW` 设成 1。

## 6. 启动和配对

### 6A. [Claude]
<!-- ci:claude-start -->
```bash
cp /opt/tgbox/claude/claude-tg.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now claude-tg
```
**配对**：让用户在 Telegram 打开自己的机器人，随便发一句话，机器人会回一个 6 位配对码，用户把配对码告诉你。你运行：
```
tmux send-keys -t claude-tg '/telegram:access pair <配对码>' Enter
sleep 5; tmux send-keys -t claude-tg '/telegram:access policy allowlist' Enter
```
（只认这个用户。用 `tmux capture-pane -pt claude-tg` 确认执行成功；如果弹出确认框，按屏幕提示回答。）

配对后用户 id 在 `/root/.claude/channels/telegram/access.json` 的 `allowFrom` 里。把它填进 `/opt/tgbox/tgbox.env` 的 `TG_OWNER_ID` 和 `/opt/tapdesk/tapdesk.env` 的 `TAPDESK_OWNER`，然后：
```bash
set -a; . /opt/tgbox/tgbox.env; set +a; /opt/tgbox/claude/setmenu.sh   # 设菜单，应输出 "ok":true
systemctl enable --now tapdesk
systemctl restart claude-tg   # 让机器人读到新的 TG_OWNER_ID
```

### 6B. [中继]
<!-- ci:relay-start -->
```bash
cp /opt/tgbox/relay/tgrelay.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now tgrelay
```
**配对**：让用户在 Telegram 打开自己的机器人，随便发一句话，机器人会回一个 6 位配对码，用户把配对码告诉你。你运行：
```
/opt/tgbox/relay/tgrelay.py pair <配对码>
```
它会自动把用户 id 写进 `tgbox.env` 和 `tapdesk.env`，机器人会在 Telegram 里说"配对成功"并设好菜单。然后：
```bash
systemctl enable --now tapdesk
```
权限：默认 `TGBOX_FULL=0`，Codex 在沙盒里跑（能改 /root/tgbot、能上网），要做沙盒外的事、Antigravity 要执行命令时，会在 Telegram 里弹"允许 / 不行"按钮。用户嫌按钮多，可以把 `/opt/tgbox/tgbox.env` 里的 `TGBOX_FULL` 改成 1 再 `systemctl restart tgrelay`，让他自己决定。

## 7. 检查清单（全部通过才算装好）
让用户在 Telegram 里依次试，你在服务器上看日志配合排查（[Claude] `tmux attach -t claude-tg`；[中继] `journalctl -u tgrelay -f`）：
- [ ] 发"你好" → 先出现 👀，再收到中文回复
- [ ] 点菜单 → 能看到 /desk、/usage、/model 等命令
- [ ] /usage → 收到额度（[Claude] 新会话刚启动时可能要先聊一句才有数据）
- [ ] /model → 消息下面出现按钮；点一个 → 提示已切换
- [ ] /screen → 收到云电脑截图
- [ ] 工具箱：你自己先跑 `tgpy /opt/tgbox-src/test/toolbox_test.py`，应输出 TOOLBOX OK；再让用户发一个 PDF 或 Word 文件说"总结一下"，发一张图片问"图里有什么"，说"把这个做成表格发我" → 都能做到
- [ ] /desk → 收到"接管"卡片；点开能看到桌面、能点击
- [ ] `reboot` 服务器，2 分钟后发消息还能回（开机自启）

## 8. 交给用户时说清楚
- 机器人有这台服务器的 root 权限，能执行命令。不要把它拉进群里给别人用。
- 不要在 Telegram 里发密码、银行卡、验证码。需要登录时，用 /desk 自己在云电脑里操作。
- 额度用的是用户自己的订阅，/usage 随时看。
- [中继] 中继是本仓库自己写的，不是官方的。Codex / Antigravity 升级后如果出问题，把 `journalctl -u tgrelay -n 100` 的报错交给 AI，让它对照 `relay/tgrelay.py` 修。
- 用着有 bug 或改进想法，可以到 https://github.com/chaslab/telegram-ai-box/issues 留言（/help 最后也有这个链接）。
- 出问题时：[Claude] `tmux attach -t claude-tg` 看终端，`systemctl restart claude-tg` 重启；[中继] `systemctl restart tgrelay` 重启。

## 附：以后换一家 / 用的不是这三家
**换一家**（比如从 Codex 换到 Antigravity，都是中继）：按 4.2 登录新的那家，把 `/opt/tgbox/tgbox.env` 的 `TGBOX_AGENT` 改掉，`systemctl restart tgrelay`。在中继和 Claude 之间换：停掉一个服务（`systemctl disable --now tgrelay` 或 `claude-tg`），按第 4、6 节做另一边。同一个机器人 token 同时只能给一个程序用。

**用的不是这三家**：
第 1、2、3、5 节（基础软件、云电脑、TapDesk）跟用什么 AI 无关，照做。然后：
1. 看那个 AI 有没有"给别的程序接"的接口（常驻进程、JSON-RPC、ACP 之类）或无界面模式。
2. 参照 `relay/tgrelay.py`：里面的 `Codex`（JSON-RPC app-server）和 `Antigravity`（ACP，很多 AI 命令行都支持这个标准协议）两个类就是现成的接法，照样写一个新类（启动、发消息、收回复、审批、列模型、查额度），其余的菜单、按钮、提醒、接管电脑都能直接复用。
3. 外观和手感按 `docs/SPEC.md` 来。查不到的项（比如额度）就不放进菜单。
