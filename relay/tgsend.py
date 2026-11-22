#!/usr/bin/env python3
"""For the AI: send something to the owner's Telegram.

    tgsend.py "文字"                         send a message
    tgsend.py --file /path/a.png "说明"       send a file (photos show as photos)
    tgsend.py --pick "问题" "选项A" "选项B"    buttons under the message; a tap arrives as if the user typed that option
"""
import json, mimetypes, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tgrelay as R  # noqa: E402

R.TG.token = R.read_token()
a = sys.argv[1:]
if not a or not R.owner():
    sys.exit(__doc__ if not a else "还没配对")
if a[0] == "--file":
    path, caption = a[1], " ".join(a[2:])
    kind = "photo" if (mimetypes.guess_type(path)[0] or "").startswith("image/") and os.path.getsize(path) < 10_000_000 else "document"
    r = R.TG.call("sendPhoto" if kind == "photo" else "sendDocument", _timeout=300, files={kind: path}, chat_id=R.owner(), caption=caption[:1000])
elif a[0] == "--pick":
    q, opts = a[1], a[2:]
    per_row = 1 if any(len(o) > 12 for o in opts) else 2
    rows = [[(o, "say:" + o) for o in opts[i:i + per_row]] for i in range(0, len(opts), per_row)]
    r = R.TG.call("sendMessage", chat_id=R.owner(), text=q, reply_markup=R.buttons(rows))
else:
    r = R.say(" ".join(a))
print(json.dumps({"ok": True, "message_id": (r or {}).get("message_id")}))
