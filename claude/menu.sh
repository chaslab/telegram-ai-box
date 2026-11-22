#!/bin/sh
# /model and /effort pickers: inline buttons under the message (see docs/SPEC.md §2).
# Usage: menu.sh model|effort      Needs: TG_OWNER_ID, the plugin "say:" patch, statusline.sh installed.
# A tap arrives in the conversation as a normal message ("Fable 5.2", "高 high"); the AI then switches.
U=${TGBOX_DIR:-/opt/tgbox/claude}
J=$U/status.json
CURM=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["model"]["display_name"])' "$J" 2>/dev/null)
CURE=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["effort"]["level"])' "$J" 2>/dev/null)
mark() { [ "$1" = "$2" ] && echo "✅ $1" || echo "$1"; }
case "$1" in
  model)  exec "$U/ask.sh" pick "选模型（现在：${CURM:-未知}）" \
            "$(mark "Fable 5.2" "$CURM")" "$(mark "Opus 5.5" "$CURM")" "$(mark "Sonnet 5.5" "$CURM")" "默认（跟随 Claude Code）" ;;
  effort) emark() { [ "$1" = "$CURE" ] && echo "✅ $2 $1" || echo "$2 $1"; }
          PER_ROW=1 exec "$U/ask.sh" pick "选思考强度（现在：${CURE:-未知}）" \
            "$(emark low 低)" "$(emark medium 中)" "$(emark high 高)" "$(emark xhigh 很高)" "$(emark max 最高)" "默认（跟随模型）" ;;
  *) echo "usage: $0 model|effort" ;;
esac
