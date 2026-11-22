#!/bin/bash
# Keep the bot running in a tmux session named claude-tg (started at boot by claude-tg.service).
export HOME=/root PATH=/root/.local/bin:/root/.bun/bin:/usr/local/bin:/usr/bin:/bin
if tmux has-session -t claude-tg 2>/dev/null && tmux list-panes -t claude-tg -F '#{pane_current_command}' | grep -qi claude; then
  echo already running; exit 0
fi
tmux kill-session -t claude-tg 2>/dev/null
tmux new-session -d -s claude-tg /opt/tgbox/claude/start.sh
sleep 10
tmux send-keys -t claude-tg 'Telegram 已连接。按 CLAUDE.md 的习惯工作，等用户消息。' Enter
echo started
