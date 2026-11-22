#!/bin/bash
# Fresh-machine smoke test of INSTALL-FOR-AI.md (non-interactive parts). Runs as root on Ubuntu 24.04.
# Skipped (need a human): AI logins, BotFather, Claude pairing, certbot (needs public port 80).
set -euxo pipefail
SRC=$(cd "$(dirname "$0")/.." && pwd)
X="python3 $SRC/test/extract.py $SRC/INSTALL-FOR-AI.md"

# base software, files (clone replaced by a copy of this checkout), cloud desktop, Claude Code + bun
$X base | bash -ex
$X toolbox | bash -ex
$X files | sed "s#^git clone .*#cp -r $SRC /opt/tgbox-src#" | bash -ex
$X desktop | bash -ex
$X claude-install | bash -ex

# 5 plugin patch: put the latest official plugin where `/plugin install` would
git clone -q --depth 1 https://github.com/anthropics/claude-plugins-official /tmp/cpo
mkdir -p /root/.claude/plugins/cache/claude-plugins-official/telegram/
cp -r /tmp/cpo/external_plugins/telegram /root/.claude/plugins/cache/claude-plugins-official/telegram/0.0.0
$X claude-patch | bash -ex
grep -q 'say:' /root/.claude/plugins/cache/claude-plugins-official/telegram/0.0.0/server.ts

# checks
st=$(/opt/clouddesk/desk.sh status); echo "$st"; grep -q "up   chrome" <<<"$st"
/opt/tapdesk/deskshot.sh /tmp/desk.jpg
tgpy $SRC/test/toolbox_test.py
python3 - <<'PY'
import subprocess
# a blank/black screenshot means the desktop didn't come up
out = subprocess.run(["ffmpeg","-loglevel","error","-i","/tmp/desk.jpg","-vf","signalstats,metadata=print","-f","null","-"],capture_output=True,text=True).stderr
print(out[-300:])
PY
cat > /opt/tgbox/claude/status.json <<'J'
{"session_id":"test","model":{"display_name":"Opus 5.5"},"effort":{"level":"high"},
 "rate_limits":{"five_hour":{"used_percentage":8,"resets_at":9999999999},"seven_day":{"used_percentage":1,"resets_at":9999999999}}}
J
for c in usage status help jobs memory; do TGBOX_DIR=/opt/tgbox/claude python3 /opt/tgbox/claude/tgfmt.py $c; done
for f in /opt/tgbox/claude/*.sh /opt/tapdesk/*.sh /opt/clouddesk/desk.sh; do bash -n "$f" || sh -n "$f"; done
python3 -m py_compile /opt/tapdesk/server.py /opt/tapdesk/card.py
echo "123:fake" > /tmp/tok
(TAPDESK_OWNER=1 TAPDESK_TOKEN_FILE=/tmp/tok TAPDESK_DOMAIN=x TAPDESK_BIND=127.0.0.1 timeout 6 python3 -u /opt/tapdesk/server.py || true) | tee /tmp/tap.out
grep -q "on 127.0.0.1:8796" /tmp/tap.out
/opt/tapdesk/deskctl.sh acquire claude "test" && /opt/tapdesk/deskctl.sh status && /opt/tapdesk/deskctl.sh release claude

# [Claude] service starts the tmux session (Claude itself stops at its login screen here)
$X claude-start | bash -ex
sleep 15
tmux has-session -t claude-tg
tmux capture-pane -pt claude-tg | tail -20

# [relay] Codex + Antigravity CLIs, then the relay against a fake Telegram: fake agents (full flow) and the real CLIs (not logged in)
$X codex-install | bash -ex
$X agy-install | bash -ex
codex --version; agy --version
python3 -m py_compile /opt/tgbox/relay/tgrelay.py /opt/tgbox/relay/tgsend.py
/opt/tgbox/relay/tgrelay.py check
for a in codex antigravity; do python3 "$SRC/test/relay_test.py" $a; python3 "$SRC/test/relay_test.py" $a --real; done
# login screens as the runbook describes them (stop at the URL; nobody logs in here). Screens are printed for review.
shot() { for i in 1 2 3 4 5 6; do sleep 5; tmux capture-pane -pJt login > /tmp/pane.txt 2>/dev/null || break; grep -q "https://" /tmp/pane.txt && break; done; echo "== screen: $1"; { grep -v '^\s*$' /tmp/pane.txt || true; } | cut -c1-160 | tail -15; }
tmux new-session -d -s login -x 250 -y 50 -c /root/tgbot 'agy acp --login; sleep 60'; shot "agy acp --login"; grep -q "accounts.google.com" /tmp/pane.txt; tmux kill-session -t login || true
tmux new-session -d -s login -x 220 -y 50 'codex login --device-auth; sleep 60'; shot "codex login --device-auth"; grep -q "auth.openai.com" /tmp/pane.txt; tmux kill-session -t login || true
tmux new-session -d -s login -x 220 -y 50 -c /root/tgbot '/root/.local/bin/claude; sleep 60'; shot "claude"
for step in Enter 1 Enter; do tmux send-keys -t login $step; shot "claude after $step"; done
tmux kill-session -t login || true
/opt/tgbox/relay/tgrelay.py set-token 123456:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA || true
grep -q '^TELEGRAM_BOT_TOKEN=123456:' /opt/tgbox/bot.env && [ "$(stat -c %a /opt/tgbox/bot.env)" = 600 ]
$X relay-start | bash -ex
systemctl is-enabled tgrelay
echo "SMOKE OK"
