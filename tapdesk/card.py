#!/usr/bin/env python3
"""Send a "需要操作" takeover card to the owner: screenshot of the desktop + inline [🖥 接管] Mini App button.
Opens the public window for 15 min. Settings come from tapdesk.env next to this file.
Usage: card.py "说明文字"
Then watch events.log here for a new line ending in "done" (user finished) or "skip"."""
import json, os, subprocess, sys, time, urllib.request, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
cfg = {}
for line in open(os.path.join(HERE, "tapdesk.env")):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        cfg[k] = v
if os.environ.get("TAPDESK_CARD_TOKEN_FILE"):   # another bot sharing this desktop sends the card with its own bot
    cfg["TAPDESK_TOKEN_FILE"] = os.environ["TAPDESK_CARD_TOKEN_FILE"]
if cfg.get("TAPDESK_TOKEN_FILE"):
    _t = open(cfg["TAPDESK_TOKEN_FILE"]).read()
    tok = next((l.split("=", 1)[1].strip().strip('"').strip("'") for l in _t.splitlines()
                if l.startswith("TELEGRAM_BOT_TOKEN=")), _t.strip())
else:   # KEY=VALUE env file holding TELEGRAM_BOT_TOKEN
    tok = [l.split("=", 1)[1].strip().strip('"').strip("'") for l in open(cfg["TAPDESK_TOKEN_ENVFILE"])
           if l.startswith("TELEGRAM_BOT_TOKEN=")][0]
chat = cfg["TAPDESK_OWNER"]
url = f"https://{cfg['TAPDESK_DOMAIN']}/"
env = dict(os.environ, DISPLAY=cfg.get("TAPDESK_DISPLAY", ":1"))
if cfg.get("XAUTHORITY"):
    env["XAUTHORITY"] = cfg["XAUTHORITY"]

if cfg.get("TAPDESK_DESK"):   # make sure the desktop/browser is up before the screenshot
    subprocess.run([cfg["TAPDESK_DESK"], "browser"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   stdin=subprocess.DEVNULL, env=env)
shot = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "x11grab", "-video_size", "1280x800",
                       "-i", env["DISPLAY"], "-frames:v", "1", "-q:v", "4", "-f", "image2pipe", "-c:v", "mjpeg", "-"],
                      capture_output=True, env=env).stdout
with open(os.path.join(HERE, "public.until"), "w") as f:
    f.write(str(time.time() + 15 * 60))

desc = sys.argv[1] if len(sys.argv) > 1 else "需要你在电脑上操作一下"
caption = f"🖥 电脑 · 需要操作\n{desc}\n\n点「🖥 接管」自己操作，弄完点里面的「我完成了」；不想弄就回我「跳过」。"
kb = {"inline_keyboard": [[{"text": "🖥 接管", "web_app": {"url": url}}]]}
bnd = uuid.uuid4().hex
parts = [f'--{bnd}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
         for k, v in (("chat_id", chat), ("caption", caption), ("reply_markup", json.dumps(kb, ensure_ascii=False)))]
if shot:
    parts.append(f'--{bnd}\r\nContent-Disposition: form-data; name="photo"; filename="s.jpg"\r\n'
                 f'Content-Type: image/jpeg\r\n\r\n'.encode() + shot + b"\r\n")
parts.append(f"--{bnd}--\r\n".encode())
method = "sendPhoto" if shot else "sendMessage"
if not shot:   # no screenshot -> plain text card
    parts[1] = f'--{bnd}\r\nContent-Disposition: form-data; name="text"\r\n\r\n{caption}\r\n'.encode()
req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/{method}", data=b"".join(parts),
                             headers={"Content-Type": f"multipart/form-data; boundary={bnd}"})
r = json.load(urllib.request.urlopen(req, timeout=30))
print("sent message_id=%s" % r["result"]["message_id"] if r.get("ok") else r)
