#!/usr/bin/env python3
"""TapDesk (Grok-style takeover): full X desktop streamed as JPEG frames
(ffmpeg x11grab, latest-frame polling) + xdotool input. Telegram Mini App.
Every API call must carry valid Telegram WebApp initData from the owner."""
import asyncio, hashlib, hmac, json, os, subprocess, time, urllib.parse
from aiohttp import web

# Same file runs on several boxes; per-box settings come from env (systemd unit).
E = os.environ.get
OWNER = int(E("TAPDESK_OWNER", "0"))                         # your Telegram user id (required)
HOST, PORT = "127.0.0.1", int(E("TAPDESK_PORT", "8796"))
DESK = E("TAPDESK_DESK", "")                                 # optional script: `$DESK browser|stop`; "" = desktop always on
DISPLAY = E("TAPDESK_DISPLAY", ":99")
OMNI_Y = int(E("TAPDESK_OMNIBOX_Y", "42"))                   # top of the address-bar band (42 bare, ~68 under a 26px top panel)
OMNIBOX = E("TAPDESK_OMNIBOX", "1") == "1"                   # Chrome maximized at 0,0 -> address bar band = text field
UFW = E("TAPDESK_UFW", "0") == "1"                           # also open/close 443 in ufw with the window
HERE = os.path.dirname(os.path.abspath(__file__))
EVENTS = os.path.join(HERE, "events.log")
W, H = 1280, 800
OUT_W = 960
BROWSER_IDLE = 15 * 60
GRAB_IDLE = 20
ENV = dict(os.environ, DISPLAY=DISPLAY)


def token_from(path):
    """A plain token file, or a KEY=VALUE env file holding TELEGRAM_BOT_TOKEN."""
    txt = open(path).read()
    for line in txt.splitlines():
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return txt.strip()


def bot_tokens():
    paths = [E("TAPDESK_TOKEN_FILE") or E("TAPDESK_TOKEN_ENVFILE", "/root/.claude/channels/telegram/.env")]
    # other bots sharing this desktop: comma-separated token/env files; their takeover cards open the same app
    paths += [x.strip() for x in E("TAPDESK_EXTRA_TOKEN_FILES", "").split(",") if x.strip()]
    toks = [token_from(p) for p in paths]
    if not toks:
        raise SystemExit("no token")
    return toks


SECRETS = [hmac.new(b"WebAppData", t.encode(), hashlib.sha256).digest() for t in bot_tokens()]


DESKCTL = E("TAPDESK_DESKCTL", "")                            # optional deskctl.sh: user takeover locks out the bots


def deskctl(cmd):
    if DESKCTL:
        subprocess.run([DESKCTL, cmd, "user", "用户在接管"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       stdin=subprocess.DEVNULL, env=dict(ENV, DESKCTL_DISPLAY=DISPLAY))


def check_init(init: str) -> bool:
    try:
        pairs = dict(urllib.parse.parse_qsl(init, keep_blank_values=True))
        h = pairs.pop("hash")
        dcs = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
        if not any(hmac.compare_digest(hmac.new(k, dcs.encode(), hashlib.sha256).hexdigest(), h) for k in SECRETS):
            return False
        if time.time() - int(pairs.get("auth_date", 0)) > 3600:
            return False
        return json.loads(pairs["user"])["id"] == OWNER
    except Exception:
        return False


def quiet(cmd):
    return subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          stdin=subprocess.DEVNULL, env=ENV)


FOCUS_JS = """(() => { if (!document.hasFocus()) return ''; let d = document, e = d.activeElement;
  for (let i = 0; i < 5 && e && e.tagName === 'IFRAME'; i++) {
    try { d = e.contentDocument; e = d.activeElement; } catch (x) { return 'iframe'; } }
  if (!e) return '';
  if (e.isContentEditable) return 'edit';
  const t = (e.tagName || '').toLowerCase(), ty = (e.type || '').toLowerCase();
  if (t === 'textarea') return 'edit';
  if (t === 'input' && !['button','submit','checkbox','radio','range','color','file','image','reset','hidden'].includes(ty)) return 'edit';
  return ''; })()"""


async def focused_editable() -> bool:
    """True if the focused element in the visible tab takes text (via CDP on 127.0.0.1:9222)."""
    import aiohttp
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as s:
            async with s.get("http://127.0.0.1:9222/json") as r:
                targets = [t for t in await r.json() if t.get("type") == "page"]
            for t in targets:
                async with s.ws_connect(t["webSocketDebuggerUrl"], max_msg_size=0) as ws:
                    await ws.send_json({"id": 1, "method": "Runtime.evaluate",
                                        "params": {"expression": FOCUS_JS, "returnByValue": True}})
                    msg = await ws.receive_json()
                    v = msg.get("result", {}).get("result", {}).get("value")
                    if v == "edit":
                        return True
    except Exception:
        pass
    return False


class Desk:
    def __init__(self):
        self.frame = b""
        self.hash = ""
        self.proc = None
        self.last_poll = 0.0
        self.last_use = time.time()
        self.cond = asyncio.Condition()

    async def ensure(self):
        self.last_use = time.time()
        if DESK and subprocess.run(["curl", "-s", "-m", "1", "127.0.0.1:9222/json/version"],
                                   capture_output=True).returncode != 0:
            await asyncio.to_thread(quiet, [DESK, "browser"])
        if self.proc is None or self.proc.returncode is not None:
            self.proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-loglevel", "error", "-f", "x11grab", "-draw_mouse", "0", "-framerate", "5",
                "-video_size", f"{W}x{H}", "-i", DISPLAY, "-vf", f"scale={OUT_W}:-2",
                "-q:v", "10", "-f", "image2pipe", "-c:v", "mjpeg", "-",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=ENV)
            asyncio.create_task(self._read(self.proc))

    async def _read(self, proc):
        buf = b""
        while True:
            chunk = await proc.stdout.read(65536)
            if not chunk:
                break
            buf += chunk
            while True:
                s = buf.find(b"\xff\xd8")
                e = buf.find(b"\xff\xd9", s + 2)
                if s < 0 or e < 0:
                    break
                jpg = buf[s:e + 2]
                buf = buf[e + 2:]
                h = hashlib.md5(jpg).hexdigest()[:12]
                if h != self.hash:
                    async with self.cond:
                        self.frame, self.hash = jpg, h
                        self.cond.notify_all()

    async def next_frame(self, have: str, wait: float = 2.0):
        self.last_poll = time.time()
        await self.ensure()
        async with self.cond:
            if self.hash == have or not self.frame:
                try:
                    await asyncio.wait_for(self.cond.wait_for(lambda: self.hash != have and self.frame), wait)
                except asyncio.TimeoutError:
                    return None
            return self.frame, self.hash

    async def xdo(self, *args):
        p = await asyncio.create_subprocess_exec("xdotool", *args, env=ENV,
                                                 stdout=asyncio.subprocess.DEVNULL,
                                                 stderr=asyncio.subprocess.DEVNULL)
        await p.wait()

    async def handle(self, a: dict):
        await self.ensure()
        t = a.get("t")
        X = lambda: str(int(max(0, min(1, a["x"])) * (W - 1)))
        Y = lambda: str(int(max(0, min(1, a["y"])) * (H - 1)))
        if t == "click":
            await self.xdo("mousemove", X(), Y(), "click", "1")
            px, py = int(X()), int(Y())
            if OMNIBOX and OMNI_Y <= py <= OMNI_Y + 40 and 120 <= px <= 1190:   # Chrome omnibox band (maximized 1280x800 window)
                return {"ok": True, "edit": True}
            await asyncio.sleep(0.15)
            return {"ok": True, "edit": await focused_editable()}
        elif t == "down":
            await self.xdo("mousemove", X(), Y(), "mousedown", "1")
        elif t == "move":
            await self.xdo("mousemove", X(), Y())
        elif t == "up":
            if "x" in a:
                await self.xdo("mousemove", X(), Y())
            await self.xdo("mouseup", "1")
        elif t == "scroll":
            n = int(a.get("n", 0))
            if n:
                if "x" in a:
                    await self.xdo("mousemove", X(), Y())
                await self.xdo("click", "--repeat", str(min(abs(n), 15)), "--delay", "15", "5" if n > 0 else "4")
        elif t == "type":
            txt = a.get("text", "")[:2000]
            if txt:
                await self.xdo("type", "--delay", "12", "--", txt)
        elif t == "key":
            k = a.get("k", "")
            if k in ("Return", "BackSpace", "Tab", "Escape", "Delete", "Left", "Right", "Up", "Down",
                     "ctrl+a", "ctrl+c", "ctrl+v", "ctrl+l", "ctrl+t", "ctrl+w", "alt+Left"):
                await self.xdo("key", k)
        elif t == "leave":
            if pub_until() > time.time():
                set_pub_until(min(pub_until(), time.time() + 45))
            deskctl("release")
        elif t in ("done", "skip", "open"):
            with open(EVENTS, "a") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {t}\n")
            deskctl("preempt" if t == "open" else "release")   # the user always wins; bots see PREEMPTED and pause
            if t in ("done", "skip") and pub_until() > time.time():
                set_pub_until(time.time() + 30)
        return {"ok": True}

    async def idle_loop(self):
        while True:
            await asyncio.sleep(10)
            now = time.time()
            if self.proc and self.proc.returncode is None and now - self.last_poll > GRAB_IDLE:
                self.proc.terminate()
                self.proc = None
            if DESK and now - self.last_use > BROWSER_IDLE and now - self.last_poll > BROWSER_IDLE:
                if subprocess.run(["pgrep", "-f", "Xvfb :99"], capture_output=True).returncode == 0:
                    await asyncio.to_thread(quiet, [DESK, "stop"])
                    self.frame, self.hash = b"", ""


D = Desk()


PUBFLAG = os.path.join(HERE, "public.until")   # epoch seconds; card.py writes it
DENIED = os.path.join(HERE, "denied.log")


def pub_until():
    try:
        return float(open(PUBFLAG).read().strip() or 0)
    except Exception:
        return 0.0


def set_pub_until(t):
    with open(PUBFLAG, "w") as f:
        f.write(str(t))


def authed(req):
    ok = check_init(req.headers.get("X-Init-Data", ""))
    if not ok:
        ip = req.headers.get("X-Forwarded-For") or req.remote
        with open(DENIED, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {ip} {req.method} {req.path}\n")
    elif pub_until() > time.time():
        set_pub_until(max(pub_until(), time.time() + 120))
    return ok


async def index(req):
    return web.FileResponse(os.path.join(HERE, "index.html"), headers={"Cache-Control": "no-store"})


async def tgjs(req):
    return web.FileResponse(os.path.join(HERE, "tg.js"), headers={"Cache-Control": "max-age=86400"})


async def frame(req):
    if not authed(req):
        return web.Response(status=403)
    r = await D.next_frame(req.query.get("h", ""))
    if r is None:
        return web.Response(status=204)
    jpg, h = r
    return web.Response(body=jpg, content_type="image/jpeg", headers={"X-H": h, "Cache-Control": "no-store"})


async def inp(req):
    if not authed(req):
        return web.json_response({"ok": False, "err": "auth"}, status=403)
    try:
        return web.json_response(await D.handle(await req.json()))
    except Exception as e:
        return web.json_response({"ok": False, "err": str(e)[:200]})


async def on_start(app):
    asyncio.create_task(D.idle_loop())


app = web.Application(client_max_size=1 << 20)
app.router.add_get("/", index)
app.router.add_get("/tg.js", tgjs)
app.router.add_get("/api/frame", frame)
app.router.add_post("/api/in", inp)
app.on_startup.append(on_start)

PUB_DOMAIN = E("TAPDESK_DOMAIN", "")                         # e.g. 1-2-3-4.sslip.io (Let's Encrypt cert must exist)
# default: eth0 addr (some clouds NAT the public IP to it)
PUB_BIND = E("TAPDESK_BIND") or subprocess.run(["sh", "-c", "ip -4 -o addr show eth0 | awk '{print $4}' | cut -d/ -f1"],
                                               capture_output=True, text=True).stdout.strip() or "0.0.0.0"


def ufw(on: bool):
    if UFW:
        quiet(["ufw", "allow" if on else "delete", *([] if on else ["allow"]), "443/tcp"])
CERT = f"/etc/letsencrypt/live/{PUB_DOMAIN}"


async def main():
    import ssl, gzip
    if not os.path.exists(os.path.join(HERE, "tg.js")):   # Telegram's WebApp script, not redistributed
        import urllib.request
        urllib.request.urlretrieve("https://telegram.org/js/telegram-web-app.js", os.path.join(HERE, "tg.js"))
    if not OWNER:
        raise SystemExit("set TAPDESK_OWNER")
    for f in ("index.html", "tg.js"):   # aiohttp FileResponse serves the .gz twin; keep it in sync
        src = os.path.join(HERE, f)
        with open(src, "rb") as a, open(src + ".gz", "wb") as b:
            b.write(gzip.compress(a.read(), 9))
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner, HOST, PORT).start()
    print(f"tailnet/local on {HOST}:{PORT}", flush=True)
    ufw(False)
    pub = None
    while True:   # public 443 listener only while a takeover window is open
        want = pub_until() > time.time() and os.path.exists(CERT + "/fullchain.pem")
        if want and pub is None:
            ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ctx.load_cert_chain(CERT + "/fullchain.pem", CERT + "/privkey.pem")
            pub = web.TCPSite(runner, PUB_BIND, 443, ssl_context=ctx)
            try:
                await pub.start()
                ufw(True)
                print("public 443 OPEN", flush=True)
                opened_at = time.time()
                asyncio.create_task(D.ensure())   # warm browser + frame grabber before the phone arrives
            except OSError as e:
                print("public bind failed:", e, flush=True)
                pub = None
        elif pub is not None and want and D.last_poll > opened_at + 1 and time.time() - D.last_poll > 60:
            set_pub_until(0)   # app was opened, now nobody is watching (closed with X) -> shut the door
            continue
        elif not want and pub is not None:
            await pub.stop()
            ufw(False)
            pub = None
            print("public 443 closed", flush=True)
        await asyncio.sleep(3)


asyncio.run(main())
