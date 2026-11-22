#!/bin/bash
# 在 Telegram 里给用户弹选项按钮或输入框（Bot API 直发，chat $TG_OWNER_ID）
#   ask.sh choose "问题" "选项1" "选项2" ...   底部弹按钮（末尾自动加「✏️ 其他，我自己写」），点了就是发一条该文字的普通消息
#   ask.sh input  "问题" "输入框提示"          弹出回复输入框（不是密码框，别用来收密码）
#   ask.sh close  ["文字"]                     收起按钮
#   ask.sh link   "文字" "按钮名" "URL"         消息下带一个点开网址的按钮（如云浏览器画面）
#   ask.sh pick   "问题" "选项1" "选项2" ...   按钮挂在消息下面（inline），点了=用户发了该文字；不点也不挡输入框
#                                              （需要打过 telegram-plugin.patch）
#   ask.sh app    "文字" ["按钮名"]              消息下带「云浏览器」Mini App 按钮（Telegram 内打开，点截图操控）
# pick 默认每行 2 个，PER_ROW=1 ask.sh pick ... 每行 1 个。输出 message_id。
set -u
set -a; . "${TELEGRAM_STATE_DIR:-$HOME/.claude/channels/telegram}/.env"; set +a
API="https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}"
CHAT=${TG_OWNER_ID:?set TG_OWNER_ID}
mode=${1:-}; shift || true
case "$mode" in
  choose)
    text=$1; shift
    kb=$(python3 -c '
import json,sys
opts=sys.argv[1:]+["✏️ 其他，我自己写"]; rows=[opts[i:i+3] for i in range(0,len(opts),3)]
print(json.dumps({"keyboard":[[{"text":o} for o in r] for r in rows],"resize_keyboard":True,"one_time_keyboard":True,"is_persistent":False,"input_field_placeholder":"点按钮，或直接打字"},ensure_ascii=False))' "$@") ;;
  input)
    text=$1; ph=${2:-}
    kb=$(python3 -c 'import json,sys;print(json.dumps({"force_reply":True,"input_field_placeholder":sys.argv[1][:64]},ensure_ascii=False))' "$ph") ;;
  close)
    text=${1:-好的}; kb='{"remove_keyboard":true}' ;;
  pick)
    text=$1; shift
    kb=$(python3 -c '
import json,sys
import os; n=int(os.environ.get("PER_ROW","2")); allo=sys.argv[1:]
opts=[o for o in allo if not o.lstrip("✅ ").startswith("默认")]; tail=[o for o in allo if o not in opts]
rows=[opts[i:i+n] for i in range(0,len(opts),n)]+[[o] for o in tail]
print(json.dumps({"inline_keyboard":[[{"text":o,"callback_data":("say:"+o)[:64]} for o in r] for r in rows]},ensure_ascii=False))' "$@") ;;
  app)
    text=$1; name=${2:-🖥 打开云浏览器}
    kb=$(python3 -c 'import json,sys;print(json.dumps({"inline_keyboard":[[{"text":sys.argv[1],"web_app":{"url":sys.argv[2]}}]]},ensure_ascii=False))' "$name" "${TAPDESK_URL:?set TAPDESK_URL}") ;;
  link)
    text=$1
    kb=$(python3 -c 'import json,sys;print(json.dumps({"inline_keyboard":[[{"text":sys.argv[1],"url":sys.argv[2]}]]},ensure_ascii=False))' "$2" "$3") ;;
  *) echo "用法: ask.sh choose|input|close|link|app|pick ..."; exit 1 ;;
esac
curl -s -m 15 "$API/sendMessage" --data-urlencode chat_id="$CHAT" --data-urlencode text="$text" \
  --data-urlencode reply_markup="$kb" | grep -o '"message_id":[0-9]*' | head -1
