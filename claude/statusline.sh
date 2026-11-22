#!/bin/sh
# Claude Code statusLine hook: keeps the latest status (model, effort, rate_limits) so /usage and /status can read it.
f=${TGBOX_DIR:-/opt/tgbox/claude}/status.json
cat > "$f.tmp" && mv "$f.tmp" "$f"
python3 -c 'import json,sys
j=json.load(open(sys.argv[1])); r=j.get("rate_limits") or {}
print((j.get("model") or {}).get("display_name",""), *[f"{k}: {round((v or {}).get(\"used_percentage\",0))}%" for k,v in r.items() if isinstance(v,dict)])' "$f" 2>/dev/null || echo
