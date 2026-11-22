#!/bin/sh
# Delete a bot message (used to remove the "⏳ working…" note): tgdel.sh <message_id>
set -a; . "${TELEGRAM_STATE_DIR:-$HOME/.claude/channels/telegram}/.env"; set +a
curl -s -m 15 "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/deleteMessage" -d chat_id="${TG_OWNER_ID:?}" -d message_id="$1" | grep -o '"ok":[a-z]*'
