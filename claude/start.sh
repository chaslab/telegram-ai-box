#!/bin/bash
# Start Claude Code with the Telegram channel (run inside tmux by claude-tg.service).
export HOME=/root PATH=/root/.local/bin:/root/.bun/bin:/usr/local/bin:/usr/bin:/bin
set -a; . /opt/tgbox/tgbox.env; set +a
cd "${TGBOX_WORK:-/root/tgbot}"
exec claude --channels plugin:telegram@claude-plugins-official "$@"
