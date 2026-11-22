#!/usr/bin/env python3
"""Telegram relay for Codex CLI and Antigravity CLI (agy) (docs/SPEC.md). Python 3.10+, standard library only.

    tgrelay.py run                 run the bot (systemd: tgrelay.service)
    tgrelay.py set-token [token]   save the @BotFather token -> /opt/tgbox/bot.env (no argument: hidden prompt)
    tgrelay.py pair <code>         accept the pairing code the bot sent you in Telegram
    tgrelay.py job add|list|del    scheduled tasks and reminders (used by the AI, see AGENTS.md)
    tgrelay.py check               print what is configured (no secrets)

Config comes from the environment (/opt/tgbox/tgbox.env):
    TGBOX_AGENT=codex|antigravity   TGBOX_WORK=/root/tgbot   TGBOX_TZ=Asia/Shanghai
    TGBOX_FULL=0|1 (1 = run every command without asking)   TG_API (tests only)
"""
import base64, datetime, json, mimetypes, os, re, secrets, shutil, subprocess, sys, threading, time, traceback, urllib.error, urllib.parse, urllib.request, uuid
from pathlib import Path
from zoneinfo import ZoneInfo

E = os.environ.get
AGENT = E("TGBOX_AGENT", "codex").lower()
WORK = Path(E("TGBOX_WORK", "/root/tgbot"))
STATE_DIR = WORK / ".tgbox"
TOKEN_FILE = Path(E("TGBOX_TOKEN_FILE", "/opt/tgbox/bot.env"))
ENV_FILE = Path(E("TGBOX_ENV_FILE", "/opt/tgbox/tgbox.env"))
TAPDESK_ENV = Path(E("TAPDESK_ENV_FILE", "/opt/tapdesk/tapdesk.env"))
TZ = E("TGBOX_TZ", "Asia/Shanghai")
FULL = E("TGBOX_FULL", "0") == "1"
API = E("TG_API", "https://api.telegram.org").rstrip("/")
NAME = {"codex": "Codex", "antigravity": "Antigravity"}.get(AGENT, AGENT)
INBOX = WORK / "inbox"


def log(*a):
    print(time.strftime("%m-%d %H:%M:%S"), *a, flush=True)


# ---------------------------------------------------------------- state files
def _load(name, default):
    try:
        return json.loads((STATE_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(name, data):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_DIR / (name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(STATE_DIR / name)


STATE_LOCK = threading.RLock()


def state():
    return _load("state.json", {})


def update_state(**kw):
    with STATE_LOCK:
        s = state()
        for k, v in kw.items():
            if v is None:
                s.pop(k, None)
            else:
                s[k] = v
        _save("state.json", s)
        return s


def owner():
    return int(E("TG_OWNER_ID") or state().get("owner") or 0)


def read_token():
    try:
        for line in TOKEN_FILE.read_text().splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


# ---------------------------------------------------------------- Telegram
class TG:
    token = ""

    @classmethod
    def call(cls, method, _timeout=40, files=None, **params):
        url = f"{API}/bot{cls.token}/{method}"
        if files:
            boundary = uuid.uuid4().hex
            body = b""
            for k, v in params.items():
                v = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
                body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
            for k, path in files.items():
                fn = Path(path).name.replace('"', "")
                body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                         f"Content-Type: application/octet-stream\r\n\r\n").encode() + Path(path).read_bytes() + b"\r\n"
            body += f"--{boundary}--\r\n".encode()
            req = urllib.request.Request(url, body, {"Content-Type": f"multipart/form-data; boundary={boundary}"})
        else:
            req = urllib.request.Request(url, json.dumps(params, ensure_ascii=False).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=_timeout) as r:
                j = json.loads(r.read())
        except urllib.error.HTTPError as e:
            j = json.loads(e.read() or b"{}")
        if not j.get("ok"):
            raise RuntimeError(f"{method}: {j.get('description')}")
        return j.get("result")

    @classmethod
    def safe(cls, method, **kw):
        try:
            return cls.call(method, **kw)
        except Exception as e:
            log("tg", method, "failed:", e)
            return None


def plain(s):
    """SPEC §4: plain text. Strip the Markdown the models like to add."""
    s = re.sub(r"^```[^\n]*\n?", "", s, flags=re.M)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"(?<!\w)__(.+?)__(?!\w)", r"\1", s)
    s = re.sub(r"`([^`\n]+)`", r"\1", s)
    s = re.sub(r"^#{1,6}\s+", "", s, flags=re.M)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 \2", s)
    return s.strip()


def say(text, **kw):
    text = plain(text or "")
    if not text:
        return None
    r = None
    while text:
        cut = text if len(text) <= 4000 else text[:text.rfind("\n", 0, 4000)]
        if not cut.strip():
            cut = text[:4000]
        r = TG.safe("sendMessage", chat_id=owner(), text=cut, **kw)
        text = text[len(cut):].lstrip("\n")
    return r


def buttons(rows):
    return {"inline_keyboard": [[{"text": t, "callback_data": d[:64]} for t, d in row] for row in rows]}


# ---------------------------------------------------------------- progress (one ⏳ message, edited, deleted at the end)
class Progress:
    def __init__(self):
        self.mid, self.text, self.t = None, "", 0

    def show(self, text):
        text = "⏳ " + text[:300]
        if text == self.text or time.time() - self.t < 2:
            return
        self.text, self.t = text, time.time()
        if self.mid:
            TG.safe("editMessageText", chat_id=owner(), message_id=self.mid, text=text)
        else:
            r = TG.safe("sendMessage", chat_id=owner(), text=text, disable_notification=True)
            self.mid = (r or {}).get("message_id")

    def end(self):
        if self.mid:
            TG.safe("deleteMessage", chat_id=owner(), message_id=self.mid)
        self.mid, self.text = None, ""


# ---------------------------------------------------------------- button questions from the AI (approvals etc.)
PENDING = {}   # key -> [Event, value]


def ask(text, options, timeout=900):
    """options: [(label, value)]. Returns the value tapped, or None on timeout."""
    key = uuid.uuid4().hex[:8]
    rec = PENDING[key] = [threading.Event(), None]
    labels = dict((v, t) for t, v in options)
    rows = [[(t, f"a|{key}|{v}") for t, v in options[i:i + 3]] for i in range(0, len(options), 3)]
    r = TG.safe("sendMessage", chat_id=owner(), text=text[:3900], reply_markup=buttons(rows))
    ok = rec[0].wait(timeout)
    PENDING.pop(key, None)
    if r:
        pick = rec[1] if ok else None
        TG.safe("editMessageText", chat_id=owner(), message_id=r["message_id"],
                text=text[:3900] + "\n\n" + (f"✅ 已选择：{labels.get(pick, pick)}" if pick else "（没有回应，按拒绝处理）"))
    return rec[1] if ok else None


def short(s, n=200):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


# ================================================================ backends
NOTE = ("你在通过 Telegram 跟用户聊天，用户在手机上看。回复用简体中文纯文本，不用 Markdown 和 HTML。"
        "工作目录里的 AGENTS.md / GEMINI.md 写了你的工具和习惯，先读一遍。")


class Codex:
    """One long-lived `codex app-server` with one thread (the same conversation keeps going)."""
    efforts_supported = True

    def __init__(self):
        self.p, self.n, self.thread, self.turn_id = None, 0, "", ""
        self.wait, self.lock, self.elock = {}, threading.Lock(), threading.Lock()
        self.ui = None
        self.done = threading.Event()
        self._models = (0, [])

    # -- json-rpc plumbing
    def _send(self, x):
        with self.lock:
            self.p.stdin.write((json.dumps(x, ensure_ascii=False) + "\n").encode())
            self.p.stdin.flush()

    def request(self, method, params=None, timeout=120):
        with self.lock:
            self.n += 1
            mid = self.n
        ev = threading.Event()
        self.wait[mid] = [ev, None]
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
        if not ev.wait(timeout):
            self.wait.pop(mid, None)
            raise RuntimeError(f"{method} 没有回应")
        r = self.wait.pop(mid)[1]
        if "error" in r:
            raise RuntimeError(str(r["error"].get("message") or r["error"]))
        return r.get("result") or {}

    def _reader(self, p):
        for line in p.stdout:
            try:
                j = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            if "method" not in j:
                w = self.wait.get(j.get("id"))
                if w:
                    w[1] = j
                    w[0].set()
                continue
            prm = j.get("params") or {}
            if prm.get("threadId") and prm["threadId"] != self.thread:
                continue
            if "id" in j:
                threading.Thread(target=self._server_request, args=(j,), daemon=True).start()
            else:
                try:
                    self._notify(j["method"], prm)
                except Exception as e:
                    log("notify error", e)
        log("codex app-server exited")
        self.done.set()

    def alive(self):
        return self.p is not None and self.p.poll() is None

    def _start_process(self):
        self.close()
        self.p = subprocess.Popen(["codex", "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, cwd=str(WORK))
        threading.Thread(target=self._reader, args=(self.p,), daemon=True).start()
        self.request("initialize", {"clientInfo": {"name": "tgbox", "title": "tgbox Telegram", "version": "1"}}, 60)
        self._send({"jsonrpc": "2.0", "method": "initialized"})

    def ensure(self):
        with self.elock:
            want = state().get("thread") or ""
            if self.alive() and self.thread and self.thread == want:
                return
            if not self.alive():
                self._start_process()
            self.thread = ""
            if want:
                try:
                    self.request("thread/resume", {"threadId": want, "cwd": str(WORK), "developerInstructions": NOTE})
                    self.thread = want
                except RuntimeError as e:
                    log("resume failed, starting a new thread:", e)
            if not self.thread:
                t = self.request("thread/start", {"cwd": str(WORK), "developerInstructions": NOTE})
                self.thread = t["thread"]["id"]
                update_state(thread=self.thread)
                try:
                    self.request("thread/name/set", {"threadId": self.thread, "name": "✈️ Telegram"})
                except Exception:
                    pass

    def close(self):
        if self.p and self.p.poll() is None:
            try:
                self.p.stdin.close()
                self.p.wait(10)
            except Exception:
                self.p.kill()
        self.p, self.thread = None, ""

    # -- one turn
    def run(self, inputs, ui):
        self.ui, self.done = ui, threading.Event()
        items = []
        for x in inputs:
            items.append({"type": "text", "text": x["text"]} if x["type"] == "text" else {"type": "localImage", "path": x["path"]})
        s = state()
        for attempt in (1, 2):
            try:
                self.ensure()
                ts = {"threadId": self.thread, "input": items,
                      "approvalPolicy": "never" if FULL else "on-request",
                      "sandboxPolicy": {"type": "dangerFullAccess"} if FULL else {"type": "workspaceWrite", "networkAccess": True}}
                if s.get("model"):
                    ts["model"] = s["model"]
                if s.get("effort"):
                    ts["effort"] = s["effort"]
                r = self.request("turn/start", ts)
                break
            except (RuntimeError, OSError) as e:
                if attempt == 2:
                    raise
                log("session broken, restarting:", e)
                self.close()
        self.turn_id = (r.get("turn") or {}).get("id") or ""
        while not self.done.wait(5):
            if not self.alive():
                raise RuntimeError("Codex 意外退出了，再发一次试试")
        self.turn_id = ""

    def steer(self, inputs):
        if not (self.turn_id and self.thread):
            return False
        try:
            items = [{"type": "text", "text": x["text"]} if x["type"] == "text" else {"type": "localImage", "path": x["path"]} for x in inputs]
            self.request("turn/steer", {"threadId": self.thread, "expectedTurnId": self.turn_id, "input": items}, 30)
            return True
        except Exception as e:
            log("steer failed:", e)
            return False

    def cancel(self):
        if self.turn_id and self.thread:
            try:
                self.request("turn/interrupt", {"threadId": self.thread, "turnId": self.turn_id}, 15)
            except Exception as e:
                log("interrupt failed:", e)

    def new_conversation(self):
        self.cancel()
        update_state(thread=None)
        self.thread = ""

    def conversation(self):
        return state().get("thread") or "（新对话）"

    def _notify(self, m, prm):
        ui = self.ui
        if not ui:
            return
        it = prm.get("item") or {}
        typ = it.get("type")
        if m == "item/started":
            if typ == "commandExecution":
                ui.progress("运行：" + short(it.get("command") or "", 120))
            elif typ == "mcpToolCall":
                ui.progress(f"用工具：{it.get('server')}.{it.get('tool')}")
            elif typ == "webSearch":
                ui.progress("搜索：" + short(it.get("query") or "", 100))
            elif typ == "fileChange":
                ui.progress("改文件：" + "、".join(Path(str(x.get("path"))).name for x in it.get("changes") or [])[:80])
            elif typ == "reasoning":
                ui.progress("思考中…")
        elif m == "item/completed" and typ == "agentMessage":
            ui.reply(it.get("text") or "")
        elif m == "error" and not prm.get("willRetry"):
            ui.reply("⚠️ " + str((prm.get("error") or {}).get("message") or "Codex 出错了"))
        elif m == "turn/completed":
            t = prm.get("turn") or {}
            if t.get("status") == "failed":
                ui.reply("⚠️ " + explain_error(str((t.get("error") or {}).get("message") or "这一轮失败了")))
            self.done.set()

    def _server_request(self, j):
        m, prm, rid = j["method"], j.get("params") or {}, j["id"]
        if m in ("item/commandExecution/requestApproval", "item/fileChange/requestApproval", "execCommandApproval", "applyPatchApproval"):
            what = prm.get("command") or prm.get("reason") or "改文件"
            if isinstance(what, list):
                what = " ".join(what)
            dec = ask(f"🔐 Codex 想要执行：\n{short(what, 600)}" + (f"\n原因：{prm['reason']}" if prm.get("reason") and prm.get("command") else ""),
                      [("允许", "accept"), ("这次对话都允许", "acceptForSession"), ("不行", "decline")]) or "decline"
            if m in ("execCommandApproval", "applyPatchApproval"):
                dec = {"accept": "approved", "acceptForSession": "approved_for_session"}.get(dec, "denied")
            self._send({"jsonrpc": "2.0", "id": rid, "result": {"decision": dec}})
        elif m == "item/permissions/requestApproval":
            dec = ask("🔐 Codex 想要更多权限：" + short(prm.get("reason") or "", 500), [("允许", "accept"), ("不行", "decline")])
            self._send({"jsonrpc": "2.0", "id": rid, "result": {"permissions": (prm.get("permissions") or {}) if dec == "accept" else {}, "scope": "turn"}})
        elif m == "mcpServer/elicitation/request":
            pick = ask(f"🔐 {prm.get('serverName') or 'Codex'}：{prm.get('message') or '要你确认'}", [("允许", "accept"), ("不行", "decline")])
            self._send({"jsonrpc": "2.0", "id": rid, "result": {"action": "accept", "content": {}} if pick == "accept" else {"action": "decline"}})
        else:
            self._send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "not supported over Telegram"}})

    # -- menu data
    def call(self, method, params=None):
        if not self.alive():
            with self.elock:
                if not self.alive():
                    self._start_process()
        return self.request(method, params, 30)

    def models(self):
        """[(id, label)] as listed by Codex itself, cached 10 minutes."""
        if self._models[1] and time.time() - self._models[0] < 600:
            return self._models[1]
        ms = [m for m in self.call("model/list", {}).get("data") or [] if not m.get("hidden")]
        self._raw_models = ms
        self._models = (time.time(), [(m.get("model"), m.get("displayName") or m.get("model")) for m in ms])
        return self._models[1]

    def _model_obj(self):
        self.models()
        want = state().get("model")
        ms = getattr(self, "_raw_models", [])
        return next((m for m in ms if m.get("model") == want), None) or next((m for m in ms if m.get("isDefault")), None) or (ms[0] if ms else {})

    def model_label(self):
        try:
            m = self._model_obj()
            return (m.get("displayName") or m.get("model") or "默认") + ("" if state().get("model") else "（默认）")
        except Exception:
            return state().get("model") or "默认"

    def efforts(self):
        return [e.get("reasoningEffort") for e in self._model_obj().get("supportedReasoningEfforts") or [] if e.get("reasoningEffort")]

    def effort_label(self):
        e = state().get("effort")
        if e:
            return EFFORT.get(e, e)
        try:
            d = self._model_obj().get("defaultReasoningEffort")
            return f"默认（{EFFORT.get(d, d)}）" if d else "默认"
        except Exception:
            return "默认"

    def set_model(self, model_id):
        update_state(model=model_id)

    def usage(self):
        r = self.call("account/rateLimits/read").get("rateLimits") or {}
        lines = ["Codex 额度"]
        for key, name in (("primary", "5 小时剩余"), ("secondary", "本周剩余")):
            w = r.get(key)
            if w:
                lines += [f"{name}：{bar(100 - float(w.get('usedPercent') or 0))}", refreshes(w.get("resetsAt"))]
        if len(lines) == 1:
            lines.append("还没拿到额度数据（先聊一句再查）。")
        return "\n".join(lines)


class AcpAgent:
    """One long-lived Agent Client Protocol (ACP) agent process with one session. Subclasses give the command line."""
    efforts_supported = False

    def __init__(self):
        self.p, self.n, self.sid = None, 0, ""
        self.wait, self.lock, self.elock = {}, threading.Lock(), threading.Lock()
        self.ui, self.loading, self.buf = None, False, ""
        self.model_state = {}
        self.busy = False

    def _send(self, x):
        with self.lock:
            self.p.stdin.write((json.dumps(x, ensure_ascii=False) + "\n").encode())
            self.p.stdin.flush()

    def request(self, method, params=None, timeout=120):
        with self.lock:
            self.n += 1
            mid = self.n
        ev = threading.Event()
        self.wait[mid] = [ev, None]
        self._send({"jsonrpc": "2.0", "id": mid, "method": method, "params": params or {}})
        if not ev.wait(timeout):
            self.wait.pop(mid, None)
            raise RuntimeError(f"{method} 没有回应")
        r = self.wait.pop(mid)[1]
        if "error" in r:
            err = r["error"]
            raise RuntimeError(str(err.get("message") or err) + (f" {err.get('data')}" if err.get("data") else ""))
        return r.get("result") or {}

    def _reader(self, p):
        for line in p.stdout:
            try:
                j = json.loads(line.decode("utf-8", "replace"))
            except ValueError:
                continue
            if "method" not in j:
                w = self.wait.get(j.get("id"))
                if w:
                    w[1] = j
                    w[0].set()
                continue
            if "id" in j:
                threading.Thread(target=self._server_request, args=(j,), daemon=True).start()
            elif j["method"] == "session/update" and not self.loading:
                try:
                    self._update((j.get("params") or {}).get("update") or {})
                except Exception as e:
                    log("update error", e)
        log("agent process exited")

    def alive(self):
        return self.p is not None and self.p.poll() is None

    def close(self):
        if self.p and self.p.poll() is None:
            try:
                self.p.stdin.close()
                self.p.wait(10)
            except Exception:
                self.p.kill()
        self.p, self.sid = None, ""

    def _start_process(self):
        self.close()
        self.p = subprocess.Popen(self._cmd(), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=str(WORK))
        threading.Thread(target=self._reader, args=(self.p,), daemon=True).start()
        self.init = self.request("initialize", {"protocolVersion": 1, "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}, "terminal": False}}, 90)

    def _cmd(self):
        raise NotImplementedError

    def ensure(self):
        with self.elock:
            want = state().get("session") or ""
            if self.alive() and self.sid and self.sid == want:
                return
            if not self.alive():
                self._start_process()
            self.sid = ""
            if want and (self.init.get("agentCapabilities") or {}).get("loadSession"):
                try:
                    self.loading = True
                    r = self.request("session/load", {"sessionId": want, "cwd": str(WORK), "mcpServers": []}, 120)
                    self.sid = want
                except RuntimeError as e:
                    log("load failed, new session:", e)
                finally:
                    self.loading = False
            if not self.sid:
                try:
                    r = self.request("session/new", {"cwd": str(WORK), "mcpServers": []}, 120)
                except RuntimeError as e:
                    raise RuntimeError(explain_error(str(e)))
                self.sid = r["sessionId"]
                update_state(session=self.sid)
            self.model_state = r.get("models") or self.model_state
            self.config_options = r.get("configOptions") or getattr(self, "config_options", [])
            mode = "yolo" if FULL else "default"
            try:
                self.request("session/set_mode", {"sessionId": self.sid, "modeId": mode}, 30)
            except RuntimeError as e:
                log("set_mode failed:", e)

    def _flush(self):
        if self.buf.strip() and self.ui:
            self.ui.reply(self.buf)
        self.buf = ""

    def _update(self, u):
        kind = u.get("sessionUpdate")
        ui = self.ui
        if not ui:
            return
        if kind == "agent_message_chunk":
            c = u.get("content") or {}
            if c.get("type") == "text":
                self.buf += c.get("text") or ""
        elif kind == "agent_thought_chunk":
            ui.progress("思考中…")
        elif kind == "tool_call":
            self._flush()
            ui.progress(short(u.get("title") or u.get("kind") or "用工具", 150))
        elif kind == "current_mode_update":
            pass

    def _server_request(self, j):
        m, prm, rid = j["method"], j.get("params") or {}, j["id"]
        if m == "session/request_permission":
            tc = prm.get("toolCall") or {}
            opts = prm.get("options") or []
            cn = {"allow_once": "允许", "allow_always": "一直允许", "reject_once": "不行", "reject_always": "一直不行"}
            choices = [(cn.get(o.get("kind"), o.get("name") or o.get("optionId")), o["optionId"]) for o in opts if o.get("kind") != "reject_always"]
            self._flush()
            pick = ask(f"🔐 {NAME} 想要：" + short(tc.get("title") or tc.get("kind") or "执行操作", 600), choices)
            res = {"outcome": {"outcome": "selected", "optionId": pick}} if pick else {"outcome": {"outcome": "cancelled"}}
            self._send({"jsonrpc": "2.0", "id": rid, "result": res})
        else:
            self._send({"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "not supported over Telegram"}})

    def run(self, inputs, ui):
        self.ui, self.buf, self.busy = ui, "", True
        prompt = []
        for x in inputs:
            if x["type"] == "text":
                prompt.append({"type": "text", "text": x["text"]})
            else:
                mt = mimetypes.guess_type(x["path"])[0] or "image/jpeg"
                prompt.append({"type": "image", "mimeType": mt, "data": base64.b64encode(Path(x["path"]).read_bytes()).decode()})
        try:
            for attempt in (1, 2):
                try:
                    self.ensure()
                    r = self.request("session/prompt", {"sessionId": self.sid, "prompt": prompt}, 3600)
                    break
                except (RuntimeError, OSError) as e:
                    if attempt == 2 or not (isinstance(e, OSError) or not self.alive()):
                        raise
                    self.close()
            self._flush()
            count_usage(r.get("usage") or {})
            if r.get("stopReason") not in (None, "end_turn", "cancelled"):
                ui.reply(f"（这一轮提前停了：{r.get('stopReason')}）")
        finally:
            self.busy = False

    def steer(self, inputs):
        return False   # ACP agents may cancel the running prompt when a new one arrives, so the relay queues instead

    def cancel(self):
        if self.sid and self.alive():
            self._send({"jsonrpc": "2.0", "method": "session/cancel", "params": {"sessionId": self.sid}})

    def new_conversation(self):
        self.cancel()
        update_state(session=None)
        self.sid = ""

    def conversation(self):
        return state().get("session") or "（新对话）"

    def models(self):
        if not self.model_state:
            try:
                self.ensure()
            except Exception as e:
                log("models:", e)
        return [(m["modelId"], m.get("name") or m["modelId"]) for m in self.model_state.get("availableModels") or []]

    def model_label(self):
        cur = state().get("model") or self.model_state.get("currentModelId")
        name = dict(self.models()).get(cur, cur or "默认")
        return name + ("" if state().get("model") else "（默认）")

    def efforts(self):
        return []

    def effort_label(self):
        return "由模型自动决定"

    def set_model(self, model_id):
        update_state(model=model_id)

    def usage(self):
        raise NotImplementedError


def count_usage(u):
    today = datetime.datetime.now(ZoneInfo(TZ)).strftime("%Y-%m-%d")
    data = _load("usage.json", {})
    d = data.setdefault(today, {"requests": 0, "tokens": 0})
    d["requests"] += 1
    d["tokens"] += int(u.get("totalTokens") or 0)
    _save("usage.json", {k: v for k, v in data.items() if k >= (datetime.date.today() - datetime.timedelta(days=30)).isoformat()})


def explain_error(msg):
    if "（原始信息：" in msg:   # already explained
        return msg
    low = msg.lower()
    if any(k in low for k in ("auth", "login", "credential", "unauthorized", "401", "not logged", "api key")):
        how = {"codex": "codex login --device-auth",
               "antigravity": "agy acp --login（打开它给的网址登录 Google，把授权码粘回终端）"}.get(AGENT, AGENT)
        return f"{NAME} 还没登录或登录过期了。在服务器终端运行 {how} 重新登录一次。\n（原始信息：{short(msg, 200)}）"
    if "quota" in low or "rate limit" in low or "429" in low or "usage limit" in low:
        return f"额度用完了，等刷新后再试。发 /usage 看什么时候刷新。\n（原始信息：{short(msg, 200)}）"
    return msg


EFFORT = {"none": "不思考 none", "minimal": "最低 minimal", "low": "低 low", "medium": "中 medium", "high": "高 high", "xhigh": "很高 xhigh", "max": "最高 max"}


def bar(left):
    left = max(0.0, min(100.0, float(left)))
    n = int(round(left / 10))
    return f"{'▓' * n}{'░' * (10 - n)} {left:.0f}%"


def refreshes(ts):
    m = max(0, int(float(ts or 0) - time.time()) // 60)
    return f"   Refreshes in {m // 60}h {m % 60}m"


# ================================================================ jobs (reminders + scheduled tasks)
def _cron_field(f, v, lo, hi):
    for part in f.split(","):
        step = 1
        if "/" in part:
            part, step = part.split("/")
            step = int(step)
        if part == "*":
            a, b = lo, hi
        elif "-" in part:
            a, b = map(int, part.split("-"))
        else:
            a = b = int(part)
        if a <= v <= b and (v - a) % step == 0:
            return True
    return False


def cron_match(expr, t):
    mi, h, dom, mon, dow = expr.split()
    return (_cron_field(mi, t.minute, 0, 59) and _cron_field(h, t.hour, 0, 23) and _cron_field(dom, t.day, 1, 31)
            and _cron_field(mon, t.month, 1, 12) and _cron_field(dow.replace("7", "0"), (t.weekday() + 1) % 7, 0, 6))


JOB_LOCK = threading.Lock()


def jobs():
    return _load("jobs.json", [])


def job_add(kind, text, cron=None, at=None):
    if cron:
        cron_match(cron, datetime.datetime.now())   # raises on a bad expression
    j = {"id": uuid.uuid4().hex[:6], "kind": kind, "text": text, "cron": cron, "at": at, "enabled": True}
    with JOB_LOCK:
        js = jobs()
        js.append(j)
        _save("jobs.json", js)
    return j


def job_desc(j):
    tz = ZoneInfo(TZ)
    when = f"定时 {j['cron']}" if j.get("cron") else datetime.datetime.fromtimestamp(j["at"], tz).strftime("%m-%d %H:%M")
    what = "提醒" if j["kind"] == "remind" else "任务"
    return f"{'' if j.get('enabled', True) else '（已暂停）'}{when} {what}：{short(j['text'], 60)}"


def scheduler(enqueue):
    last_minute = None
    while True:
        try:
            now = datetime.datetime.now(ZoneInfo(TZ))
            minute = now.replace(second=0, microsecond=0)
            fire = []
            with JOB_LOCK:
                js, keep = jobs(), []
                for j in js:
                    due = False
                    if j.get("enabled", True):
                        if j.get("cron"):
                            due = minute != last_minute and cron_match(j["cron"], now)
                        elif j.get("at") and j["at"] <= time.time():
                            due = True
                    if due:
                        fire.append(j)
                    if not (due and not j.get("cron")):
                        keep.append(j)
                if len(keep) != len(js):
                    _save("jobs.json", keep)
            last_minute = minute
            for j in fire:
                if j["kind"] == "remind":
                    say("⏰ 提醒：" + j["text"])
                else:
                    enqueue([{"type": "text", "text": f"[定时任务 {j['id']}，不是用户刚发的] {j['text']}"}])
        except Exception as e:
            log("scheduler:", e)
        time.sleep(20)


def parse_remind(arg):
    """'20m 喝水' / '2h 休息' / '18:30 开会' -> (timestamp, text)"""
    m = re.match(r"^\s*(\d+)\s*(m|min|分钟?|h|小时|d|天)\s*(.+)$", arg or "", re.I)
    if m:
        n, u = int(m.group(1)), m.group(2).lower()
        sec = n * (3600 if u in ("h", "小时") else 86400 if u in ("d", "天") else 60)
        return time.time() + sec, m.group(3).strip()
    m = re.match(r"^\s*(\d{1,2})[:：](\d{2})\s*(.+)$", arg or "")
    if m:
        tz = ZoneInfo(TZ)
        now = datetime.datetime.now(tz)
        t = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if t <= now:
            t += datetime.timedelta(days=1)
        return t.timestamp(), m.group(3).strip()
    return None, None


# ================================================================ the bot
class Antigravity(AcpAgent):
    """Google Antigravity CLI (`agy acp`, Agent Client Protocol). Google AI Pro / Ultra accounts use this, not Gemini CLI."""

    @property
    def efforts_supported(self):
        return self._effort_option() is not None

    def _cmd(self):
        return ["agy", "acp"] + (["--dangerously-skip-permissions"] if FULL else [])

    def ensure(self):
        super().ensure()
        if state().get("model") and self.model_state.get("currentModelId") != state()["model"]:
            try:
                self.request("session/set_model", {"sessionId": self.sid, "modelId": state()["model"]}, 30)
                self.model_state["currentModelId"] = state()["model"]
            except RuntimeError as e:
                log("set_model:", e)
        self._apply_effort()
        if getattr(self, "_menu_effort", None) != self.efforts_supported and owner():
            self._menu_effort = self.efforts_supported
            set_menu()   # /effort appears only if this agy build can change it

    def _effort_option(self):
        for o in getattr(self, "config_options", []) or []:
            if re.search(r"effort|thinking|reasoning", f"{o.get('id')} {o.get('name')}", re.I):
                return o
        return None

    def _apply_effort(self):
        o, e = self._effort_option(), state().get("effort")
        if o and e and o.get("currentValue") != e:
            try:
                self.request("session/set_config_option", {"sessionId": self.sid, "configId": o["id"], "value": e}, 30)
                o["currentValue"] = e
            except RuntimeError as err:
                log("set effort:", err)

    def efforts(self):
        o = self._effort_option()
        return [x.get("value") for x in (o or {}).get("options") or [] if isinstance(x, dict) and x.get("value")]

    def effort_label(self):
        e = state().get("effort")
        if e:
            return EFFORT.get(e, e)
        o = self._effort_option()
        cur = (o or {}).get("currentValue")
        return f"默认（{EFFORT.get(cur, cur)}）" if cur else "默认"

    def set_model(self, model_id):
        update_state(model=model_id)
        if self.sid and self.alive() and model_id:
            try:
                self.request("session/set_model", {"sessionId": self.sid, "modelId": model_id}, 30)
                self.model_state["currentModelId"] = model_id
            except RuntimeError as e:
                log("set_model failed:", e)
        elif not model_id:
            self.close()   # back to the default model: fresh process, same conversation

    def models(self):
        ms = super().models()
        if ms:
            return ms
        r = subprocess.run(["agy", "models"], capture_output=True, text=True, timeout=60, cwd=str(WORK))
        return [tuple((l.split("\t") + [l])[:2]) for l in r.stdout.splitlines() if "\t" in l]

    def usage(self):
        """`agy -p "/usage" --output-format json` answers without starting a turn or spending quota."""
        r = subprocess.run(["agy", "-p", "/usage", "--output-format", "json"], capture_output=True, text=True, timeout=90,
                           cwd=str(WORK), stdin=subprocess.DEVNULL)
        j = next((json.loads(l) for l in r.stdout.splitlines()[::-1] if l.startswith("{")), {})
        if j.get("status") != "SUCCESS":
            raise RuntimeError(j.get("error") or short(r.stderr or r.stdout or "agy 没有输出", 200))
        return format_agy_usage(((j.get("command") or {}).get("data") or {}).get("groups") or [])


GROUP_CN = {"gemini models": "Gemini 模型", "claude and gpt models": "Claude / GPT 模型"}


def format_agy_usage(groups):
    """SPEC /usage format from agy's quota groups: each group shares a 5-hour and a weekly limit."""
    lines = ["Antigravity 额度"]
    for g in groups:
        bs = {b.get("window"): b for b in g.get("buckets") or []}
        if len(groups) > 1:
            lines.append(GROUP_CN.get(str(g.get("name")).lower(), g.get("name")))
        for win, label in (("5h", "5 小时剩余"), ("weekly", "本周剩余")):
            b = bs.get(win)
            if b and b.get("remaining_fraction") is not None:
                lines.append(f"{label}：{bar(float(b['remaining_fraction']) * 100)}")
                try:
                    lines.append(refreshes(datetime.datetime.fromisoformat(str(b["reset_time"]).replace("Z", "+00:00")).timestamp()))
                except (KeyError, ValueError):
                    pass
    if len(lines) == 1:
        lines.append("没有拿到额度数据。")
    return "\n".join(lines)


BACKEND = {"codex": Codex, "antigravity": Antigravity}.get(AGENT, Codex)()
QUEUE, QLOCK, QEV = [], threading.Lock(), threading.Event()
CURRENT = {"busy": False}


class UI:
    def __init__(self):
        self.prog = Progress()

    def progress(self, text):
        self.prog.show(text)

    def reply(self, text):
        self.prog.end()
        say(text)


def enqueue(inputs):
    with QLOCK:
        QUEUE.append(inputs)
    QEV.set()


def worker():
    while True:
        QEV.wait()
        with QLOCK:
            if not QUEUE:
                QEV.clear()
                continue
            inputs = QUEUE.pop(0)
        CURRENT["busy"] = True
        ui = UI()
        stop = threading.Event()
        threading.Thread(target=typing, args=(stop,), daemon=True).start()
        try:
            BACKEND.run(inputs, ui)
        except Exception as e:
            log("turn error:", traceback.format_exc())
            ui.reply("⚠️ " + explain_error(str(e)))
        finally:
            stop.set()
            ui.prog.end()
            CURRENT["busy"] = False


def typing(stop):
    while not stop.is_set():
        TG.safe("sendChatAction", chat_id=owner(), action="typing")
        stop.wait(4.5)


def download(file_id, name):
    f = TG.call("getFile", file_id=file_id)
    INBOX.mkdir(parents=True, exist_ok=True)
    dest = INBOX / f"{time.strftime('%Y%m%d-%H%M%S')}-{re.sub(r'[^\w.-]', '_', name)}"
    with urllib.request.urlopen(f"{API}/file/bot{TG.token}/{f['file_path']}", timeout=120) as r:
        dest.write_bytes(r.read())
    return dest


def has_desk():
    return Path("/opt/tapdesk/card.py").exists()


def menu():
    cmds = []
    if has_desk():
        cmds.append(("desk", "远程接管云电脑"))
    cmds += [("new", "开新对话"), ("remind", "快捷设提醒"), ("jobs", "管理定时任务"), ("memory", "查看长期记忆"),
             ("usage", "查额度"), ("model", "选模型")]
    if BACKEND.efforts_supported:
        cmds.append(("effort", "思考强度"))
    cmds.append(("status", "当前设置"))
    if has_desk():
        cmds.append(("screen", "云电脑截屏"))
    cmds.append(("help", "帮助"))
    return cmds


def warm_up():
    """Antigravity: open the session early so /effort shows in the menu only when this agy build supports it."""
    if isinstance(BACKEND, Antigravity) and owner():
        try:
            BACKEND.ensure()
        except Exception as e:
            log("warm up:", e)


def set_menu():
    TG.safe("setMyCommands", scope={"type": "chat", "chat_id": owner()},
            commands=[{"command": c, "description": d} for c, d in menu()])


# Credit + feedback link (PolyForm Noncommercial: keep the notice).
HELP_FOOTER = "菜单、查额度、远程操控这些功能来自 GitHub 上的 telegram-ai-box。有 bug 或建议，欢迎去仓库留言：\nhttps://github.com/chaslab/telegram-ai-box/issues"


def help_text():
    extra = {"desk": "远程接管云电脑（用完自动关端口）", "new": "开一个新对话", "remind": "设快捷提醒（如 /remind 20m 喝水）",
             "jobs": "查看和管理定时任务与提醒", "memory": "查看长期记忆", "usage": "查额度", "model": "选模型",
             "effort": "思考强度", "status": "当前设置", "screen": "截云电脑屏幕", "help": "帮助"}
    return (f"{NAME} 24 小时助手\n直接发文字、图片、语音、视频或文件：接着当前对话处理\n" + "\n".join(f"/{c} {extra[c]}" for c, _ in menu())
            + "\n\n" + HELP_FOOTER)


def memory_text():
    f = WORK / "MEMORY.md"
    items = [l.strip()[2:] for l in (f.read_text(encoding="utf-8").splitlines() if f.exists() else []) if l.strip().startswith("- ")]
    if not items:
        return "长期记忆\n\n还没有记忆。跟我说「记住……」，我就会记下来。"
    return "长期记忆\n\n" + "\n".join("· " + i for i in items)


def status_text():
    n = len([j for j in jobs() if j.get("enabled", True)])
    q = len(QUEUE)
    busy = "空闲" if not CURRENT["busy"] else f"后台处理中（排队 {q} 条）"
    perm = "全部自动允许" if FULL else "自动允许（有安全检查）"
    return (f"模型：{BACKEND.model_label()}\n思考强度：{BACKEND.effort_label()}\n工具权限：{perm}\n"
            f"后台状态：{busy}\n运行中定时任务：{n} 个（时区：{TZ}）\n对话：{BACKEND.conversation()}")


def show_model():
    try:
        ms = BACKEND.models()
    except Exception as e:
        return say("⚠️ 拿不到模型列表：" + explain_error(str(e)))
    cur = state().get("model")
    rows = [[(("✅ " if mid == cur else "") + label, "m|" + mid) for mid, label in ms[i:i + 2]] for i in range(0, len(ms), 2)]
    rows.append([(("✅ " if not cur else "") + f"默认（跟随 {NAME}）", "m|")])
    TG.safe("sendMessage", chat_id=owner(), text=f"选模型（现在：{BACKEND.model_label()}）", reply_markup=buttons(rows))


def show_effort():
    try:
        es = BACKEND.efforts()
    except Exception as e:
        return say("⚠️ " + explain_error(str(e)))
    if not es:
        return say("这个模型不能调思考强度。")
    cur = state().get("effort")
    rows = [[(("✅ " if e == cur else "") + EFFORT.get(e, e), "e|" + e)] for e in es]
    rows.append([(("✅ " if not cur else "") + "默认（跟随模型）", "e|")])
    TG.safe("sendMessage", chat_id=owner(), text=f"选思考强度（现在：{BACKEND.effort_label()}）", reply_markup=buttons(rows))


def show_jobs():
    js = jobs()
    if not js:
        return say(f"暂无定时任务或提醒（时区：{TZ}）。\n\n用法示例：\n· /remind 20m 喝水\n· /remind 18:30 开会\n"
                   "· 直接聊天告诉我，比如「每天早上 8 点给我发科技早报」")
    say(f"定时任务和提醒（时区：{TZ}）")
    for j in js:
        TG.safe("sendMessage", chat_id=owner(), text=job_desc(j),
                reply_markup=buttons([[("启用" if not j.get("enabled", True) else "暂停", "j|t|" + j["id"]), ("🗑 删除", "j|d|" + j["id"])]]))


def send_screen():
    out = "/tmp/tgbox-screen.jpg"
    r = subprocess.run(["/opt/tapdesk/deskshot.sh", out], capture_output=True, text=True, timeout=60)
    if r.returncode or not Path(out).exists():
        return say("⚠️ 截屏失败：" + short(r.stderr or r.stdout, 300))
    TG.safe("sendPhoto", chat_id=owner(), files={"photo": out}, caption="云电脑现在的画面")


def command(cmd, arg):
    if cmd == "help" or cmd == "start":
        say(help_text())
    elif cmd == "status":
        say(status_text())
    elif cmd == "usage":
        try:
            say(BACKEND.usage())
        except Exception as e:
            say("⚠️ 查不到额度：" + explain_error(str(e)))
    elif cmd == "model":
        show_model()
    elif cmd == "effort" and BACKEND.efforts_supported:
        show_effort()
    elif cmd == "new":
        BACKEND.new_conversation()
        say("已开新对话。之前的对话还在服务器上，长期记忆不受影响。")
    elif cmd == "memory":
        say(memory_text())
    elif cmd == "jobs":
        show_jobs()
    elif cmd == "remind":
        at, text = parse_remind(arg)
        if not at:
            return say("用法：/remind 20m 喝水、/remind 2h 休息、/remind 18:30 开会\n复杂的（每天、每周）直接跟我说。")
        job_add("remind", text, at=at)
        say(f"好，{datetime.datetime.fromtimestamp(at, ZoneInfo(TZ)).strftime('%m-%d %H:%M')} 提醒你：{text}")
    elif cmd == "desk" and has_desk():
        r = subprocess.run(["python3", "/opt/tapdesk/card.py", arg or "用户主动打开云电脑"], capture_output=True, text=True, timeout=90)
        if r.returncode:
            say("⚠️ 接管卡片没发出去：" + short(r.stderr or r.stdout, 300))
    elif cmd == "screen" and has_desk():
        send_screen()
    elif cmd == "stop":
        BACKEND.cancel()
        say("已让它停下。")
    else:
        return False
    return True


def on_message(m):
    uid = (m.get("from") or {}).get("id")
    if (m.get("chat") or {}).get("type") != "private":
        return
    if not owner():
        return pairing(m)
    if uid != owner():
        return
    TG.safe("setMessageReaction", chat_id=uid, message_id=m["message_id"], reaction=[{"type": "emoji", "emoji": "👀"}])
    text = m.get("text") or m.get("caption") or ""
    if m.get("text", "").startswith("/"):
        cmd, _, arg = m["text"][1:].partition(" ")
        cmd = cmd.split("@")[0].lower()
        if command(cmd, arg.strip()):
            return
    inputs = []
    try:
        if m.get("photo"):
            p = download(m["photo"][-1]["file_id"], "photo.jpg")
            inputs.append({"type": "image", "path": str(p)})
            inputs.append({"type": "text", "text": f"[用户发来一张图片，已存到 {p}]"})
        for key in ("document", "voice", "audio", "video", "video_note"):
            if m.get(key):
                f = m[key]
                p = download(f["file_id"], f.get("file_name") or f"{key}{mimetypes.guess_extension(f.get('mime_type') or '') or ''}")
                inputs.append({"type": "text", "text": f"[用户发来{ {'voice': '语音', 'audio': '音频', 'video': '视频', 'video_note': '视频'}.get(key, '文件') }，已存到 {p}]"})
    except Exception as e:
        say("⚠️ 文件没收下来（Telegram 机器人最多收 20MB）：" + short(e, 200))
    if text:
        inputs.append({"type": "text", "text": text})
    if not inputs:
        return
    if CURRENT["busy"] and BACKEND.steer(inputs):
        return
    enqueue(inputs)


def on_callback(cb):
    uid = (cb.get("from") or {}).get("id")
    if uid != owner():
        return TG.safe("answerCallbackQuery", callback_query_id=cb["id"])
    data = cb.get("data") or ""
    msg = cb.get("message") or {}
    mid = msg.get("message_id")
    kind, _, rest = data.partition("|")
    toast = ""
    if kind == "a":
        key, _, val = rest.partition("|")
        rec = PENDING.get(key)
        if rec:
            rec[1] = val
            rec[0].set()
        toast = "已选择"
    elif kind == "m":
        BACKEND.set_model(rest or None)
        label = dict(BACKEND.models()).get(rest, rest) if rest else f"默认（跟随 {NAME}）"
        toast = f"已切换：{label}"
        TG.safe("editMessageText", chat_id=uid, message_id=mid, text=f"模型已切换为：{label}\n（对话不变，下一条消息起生效）")
    elif kind == "e":
        update_state(effort=rest or None)
        label = EFFORT.get(rest, rest) if rest else "默认（跟随模型）"
        toast = f"已切换：{label}"
        TG.safe("editMessageText", chat_id=uid, message_id=mid, text=f"思考强度已切换为：{label}\n（下一条消息起生效）")
    elif kind == "j":
        op, _, jid = rest.partition("|")
        with JOB_LOCK:
            js = jobs()
            j = next((x for x in js if x["id"] == jid), None)
            if j and op == "t":
                j["enabled"] = not j.get("enabled", True)
            elif j and op == "d":
                js.remove(j)
            _save("jobs.json", js)
        if j and op == "d":
            toast = "已删除"
            TG.safe("editMessageText", chat_id=uid, message_id=mid, text="🗑 已删除：" + job_desc(j))
        elif j:
            toast = "已暂停" if not j["enabled"] else "已启用"
            TG.safe("editMessageText", chat_id=uid, message_id=mid, text=job_desc(j),
                    reply_markup=buttons([[("启用" if not j["enabled"] else "暂停", "j|t|" + jid), ("🗑 删除", "j|d|" + jid)]]))
    elif data.startswith("say:"):
        text = data[4:]
        toast = f"已选择：{text}"
        TG.safe("editMessageText", chat_id=uid, message_id=mid, text=(msg.get("text") or "") + f"\n\n✅ 已选择：{text}")
        on_message({"chat": msg.get("chat") or {"type": "private"}, "from": cb["from"], "message_id": mid, "text": text})
    TG.safe("answerCallbackQuery", callback_query_id=cb["id"], text=toast[:190])


def pairing(m):
    """No owner yet: give the sender a code. Whoever can run `tgrelay.py pair <code>` on the server becomes the owner."""
    uid = m["from"]["id"]
    with STATE_LOCK:
        s = state()
        pend = s.get("pending") or {}
        code = next((c for c, v in pend.items() if v["user"] == uid), None)
        if not code:
            code = f"{secrets.randbelow(10 ** 6):06d}"
            pend = {c: v for c, v in pend.items() if time.time() - v["t"] < 3600}
            pend[code] = {"user": uid, "t": time.time()}
            update_state(pending=pend)
    TG.safe("sendMessage", chat_id=uid, text=f"这个机器人还没配对。\n配对码：{code}\n\n在服务器终端运行：\n/opt/tgbox/relay/tgrelay.py pair {code}\n（或者把配对码告诉帮你部署的 AI）")


def set_env_line(path, key, value):
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return False
    out, done = [], False
    for l in lines:
        if l.startswith(key + "="):
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(l)
    if not done:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n")
    return True


def run():
    TG.token = read_token()
    if not TG.token:
        sys.exit(f"没有机器人 token：先运行 {sys.argv[0]} set-token")
    WORK.mkdir(parents=True, exist_ok=True)
    me = TG.call("getMe")
    log(f"@{me['username']} relay for {NAME}, owner={owner() or '(not paired)'}")
    threading.Thread(target=worker, daemon=True).start()
    threading.Thread(target=scheduler, args=(enqueue,), daemon=True).start()
    if owner():
        set_menu()
        threading.Thread(target=warm_up, daemon=True).start()
    offset, had_owner = None, bool(owner())
    while True:
        try:
            ups = _poll(offset)
        except Exception as e:
            log("poll:", e)
            time.sleep(5)
            continue
        if not had_owner and owner():   # just paired from the terminal
            had_owner = True
            set_menu()
            threading.Thread(target=warm_up, daemon=True).start()
            say("配对成功 ✅ 以后这个机器人只听你的。点输入框左边的菜单看看能做什么。")
        for u in ups:
            offset = u["update_id"] + 1
            try:
                if "message" in u:
                    on_message(u["message"])
                elif "callback_query" in u:
                    on_callback(u["callback_query"])
            except Exception:
                log("handler:", traceback.format_exc())


def _poll(offset):
    params = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
    if offset:
        params["offset"] = offset
    return TG.call("getUpdates", _timeout=40, **params)


# ================================================================ CLI
def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "run":
        run()
    elif a[0] == "set-token":
        import getpass
        tok = (a[1] if len(a) > 1 else getpass.getpass("粘贴 @BotFather 给的 token（输入时不显示），回车：")).strip()
        if not re.match(r"^\d+:[\w-]{30,}$", tok):
            sys.exit("这不像机器人 token（应该是 数字:一串字母），再试一次。")
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOKEN_FILE.write_text(f"TELEGRAM_BOT_TOKEN={tok}\n")
        os.chmod(TOKEN_FILE, 0o600)
        TG.token = tok
        try:
            print("好了，机器人是 @" + TG.call("getMe")["username"])
        except Exception as e:
            print("token 存好了，但验证失败：", e)
    elif a[0] == "pair" and len(a) == 2:
        with STATE_LOCK:
            s = state()
            p = (s.get("pending") or {}).get(a[1].strip())
            if not p or time.time() - p["t"] > 3600:
                sys.exit("配对码不对或过期了：在 Telegram 里给机器人再发一句话，拿新的配对码。")
            update_state(owner=p["user"], pending=None)
        set_env_line(ENV_FILE, "TG_OWNER_ID", p["user"])
        if TAPDESK_ENV.exists():
            set_env_line(TAPDESK_ENV, "TAPDESK_OWNER", p["user"])
        print(f"配对成功，主人 id {p['user']}（已写进 {ENV_FILE}" + (f" 和 {TAPDESK_ENV}" if TAPDESK_ENV.exists() else "") + "）")
    elif a[0] == "job":
        if a[1:2] == ["list"]:
            for j in jobs():
                print(j["id"], job_desc(j))
        elif a[1:2] == ["del"] and len(a) == 3:
            with JOB_LOCK:
                _save("jobs.json", [j for j in jobs() if j["id"] != a[2]])
            print("deleted", a[2])
        elif a[1:2] == ["add"]:
            import argparse
            ap = argparse.ArgumentParser(prog="tgrelay.py job add")
            ap.add_argument("--cron", help='分 时 日 月 周，例如 "0 8 * * *"（服务器时区 TGBOX_TZ）')
            ap.add_argument("--at", help='一次性，例如 "2026-11-23 08:00"')
            ap.add_argument("--remind", help="到时间直接发这句话给用户")
            ap.add_argument("--task", help="到时间让 AI 执行这段指令")
            o = ap.parse_args(a[2:])
            if not (o.cron or o.at) or not (o.remind or o.task):
                ap.error("需要 --cron 或 --at，以及 --remind 或 --task")
            at = datetime.datetime.strptime(o.at, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(TZ)).timestamp() if o.at else None
            j = job_add("remind" if o.remind else "task", o.remind or o.task, cron=o.cron, at=at)
            print("added", j["id"], job_desc(j))
        else:
            sys.exit("job add|list|del")
    elif a[0] == "check":
        print("agent:", AGENT, "| work:", WORK, "| tz:", TZ, "| full:", FULL)
        print("token:", "ok" if read_token() else "missing", "| owner:", owner() or "not paired")
        print("cli:", shutil.which({"codex": "codex", "antigravity": "agy"}.get(AGENT, AGENT)) or "NOT FOUND")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
