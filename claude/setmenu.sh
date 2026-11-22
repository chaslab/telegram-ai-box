#!/bin/sh
# Set the Telegram menu (docs/SPEC.md §1) for the owner's chat only, no language_code.
set -a; . "${TELEGRAM_STATE_DIR:-$HOME/.claude/channels/telegram}/.env"; set +a
curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setMyCommands" -H 'Content-Type: application/json' -d '{
 "scope":{"type":"chat","chat_id":'"${TG_OWNER_ID:?set TG_OWNER_ID}"'},
 "commands":[
  {"command":"desk","description":"远程接管云电脑"},
  {"command":"remind","description":"快捷设提醒"},
  {"command":"jobs","description":"管理定时任务"},
  {"command":"memory","description":"查看长期记忆"},
  {"command":"usage","description":"查额度"},
  {"command":"model","description":"选模型"},
  {"command":"effort","description":"思考强度"},
  {"command":"status","description":"当前设置"},
  {"command":"screen","description":"云电脑截屏"},
  {"command":"help","description":"帮助"}]}' | grep -o '"ok":[a-z]*'
