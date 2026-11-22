#!/usr/bin/env python3
"""End-to-end test of relay/tgrelay.py against a fake Telegram (mock_tg.py) and a fake agent (fakebin/).
    relay_test.py codex|antigravity [--real]
--real uses the real `codex` / `agy` on PATH (not logged in): checks the relay starts them and explains the login."""
import json, os, re, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELAY = HERE.parent / "relay" / "tgrelay.py"
AGENT = sys.argv[1]
REAL = "--real" in sys.argv
PORT = 8799 + {"codex": 0, "antigravity": 4}[AGENT] + (2 if REAL else 0)
BASE = f"http://127.0.0.1:{PORT}"
USER = 4242
tmp = Path(tempfile.mkdtemp())
(tmp / "bot.env").write_text("TELEGRAM_BOT_TOKEN=123:fake\n")
(tmp / "tgbox.env").write_text("TG_OWNER_ID=\n")
env = dict(os.environ, TGBOX_AGENT=AGENT, TGBOX_WORK=str(tmp / "work"), TGBOX_TOKEN_FILE=str(tmp / "bot.env"),
           TGBOX_ENV_FILE=str(tmp / "tgbox.env"), TAPDESK_ENV_FILE=str(tmp / "none"), TG_API=BASE, TGBOX_TZ="Asia/Shanghai")
env.pop("TG_OWNER_ID", None)
if not REAL:
    env["PATH"] = f"{HERE / 'fakebin'}:{env['PATH']}"

mock = subprocess.Popen([sys.executable, str(HERE / "mock_tg.py"), str(PORT)])
time.sleep(0.5)
relay = subprocess.Popen([sys.executable, "-u", str(RELAY), "run"], env=env, stdout=open(tmp / "relay.log", "w"), stderr=subprocess.STDOUT)
FAIL = []


def sent():
    return json.loads(urllib.request.urlopen(BASE + "/ctl/sent").read())


def push(u):
    mark[0] = len(sent())
    urllib.request.urlopen(urllib.request.Request(BASE + "/ctl/push", json.dumps(u).encode(), {"Content-Type": "application/json"}))


MID = [100]


def msg(text=None, **extra):
    MID[0] += 1
    m = {"message_id": MID[0], "chat": {"id": USER, "type": "private"}, "from": {"id": USER}, **extra}
    if text is not None:
        m["text"] = text
    push({"message": m})


def tap(data, mid=1):
    push({"callback_query": {"id": "cb" + str(time.time()), "from": {"id": USER}, "data": data,
                             "message": {"message_id": mid, "chat": {"id": USER, "type": "private"}, "text": "q"}}})


def wait_for(name, pred, timeout=20):
    t = time.time()
    while time.time() - t < timeout:
        for c in sent()[mark[0]:]:
            if pred(c):
                print("  ok:", name)
                return c
        time.sleep(0.3)
    print("  FAIL:", name, [(c["method"], (c.get("text") or "")[:60]) for c in sent()[mark[0]:]][-8:])
    FAIL.append(name)
    return None


mark = [0]


def text_has(s):
    return lambda c: c["method"] in ("sendMessage", "editMessageText") and s in (c.get("text") or "")


try:
    print(f"== {AGENT}{' (real CLI)' if REAL else ''}")
    msg("你好")
    c = wait_for("pairing code", text_has("配对码"))
    code = re.search(r"配对码：(\d{6})", c["text"]).group(1) if c else "000000"
    mark[0] = len(sent())
    r = subprocess.run([sys.executable, str(RELAY), "pair", code], env=env, capture_output=True, text=True)
    print("  pair:", r.stdout.strip() or r.stderr.strip())
    assert f"TG_OWNER_ID={USER}" in (tmp / "tgbox.env").read_text(), "owner not written to tgbox.env"
    wait_for("paired message", text_has("配对成功"))
    menu = wait_for("menu set", lambda c: c["method"] == "setMyCommands" and (AGENT != "antigravity" or REAL or
                    "effort" in [x["command"] for x in c.get("commands", [])]))
    cmds = [x["command"] for x in (menu or {}).get("commands", [])]
    print("  menu:", cmds)
    if not REAL and "effort" not in cmds:
        FAIL.append("effort missing from menu")

    msg("/help")
    wait_for("/help", text_has("24 小时助手")); wait_for("/help footer", text_has("telegram-ai-box/issues"))
    msg("/status")
    wait_for("/status", text_has("工具权限："))

    if REAL:
        msg("你好")
        wait_for("👀 reaction", lambda c: c["method"] == "setMessageReaction")
        c = wait_for("login hint", text_has("登录"), 90)
        print("  hint:", (c or {}).get("text", "")[:200])
    else:
        msg("/model")
        c = wait_for("/model buttons", lambda c: c["method"] == "sendMessage" and "选模型（现在：" in c.get("text", "") and c.get("reply_markup"))
        target = "gpt-y" if AGENT == "codex" else "gemini-b"
        EFF = True
        tap("m|" + target)
        wait_for("model switched", text_has("模型已切换为："))
        if EFF:
            msg("/effort")
            wait_for("/effort buttons", lambda c: c["method"] == "sendMessage" and "选思考强度" in c.get("text", ""))
            tap("e|medium")
            wait_for("effort switched", text_has("思考强度已切换为：中 medium"))
        msg("/usage")
        wait_for("/usage", {"codex": text_has("5 小时剩余：▓▓▓▓▓▓▓▓░░ 80%"),
                            "antigravity": text_has("Gemini 模型\n5 小时剩余：▓▓▓▓▓▓▓▓░░ 83%")}[AGENT])
        msg("/remind 30m 喝水")
        wait_for("/remind", text_has("提醒你：喝水"))
        msg("/jobs")
        wait_for("/jobs", text_has("提醒：喝水"))
        msg("/memory")
        wait_for("/memory empty", text_has("还没有记忆"))

        msg("你好")
        wait_for("👀 reaction", lambda c: c["method"] == "setMessageReaction")
        wait_for("progress ⏳", text_has("⏳"))
        c = wait_for("agent reply", text_has("echo: 你好"))
        if c and ("**" in c["text"] or "##" in c["text"]):
            FAIL.append("markdown not stripped")
        if AGENT == "codex" and c and "model=gpt-y effort=medium sandbox=workspaceWrite" not in c["text"]:
            FAIL.append("codex turn params: " + c["text"])
        if AGENT == "antigravity" and c and "model=gemini-b/medium" not in c["text"]:
            FAIL.append("antigravity model/effort: " + c["text"])
        wait_for("progress deleted", lambda c: c["method"] == "deleteMessage")

        msg("please approve")
        c = wait_for("approval buttons", lambda c: c["method"] == "sendMessage" and "🔐" in c.get("text", ""))
        if c:
            cb = c["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
            tap(cb)
            wait_for("approved reply", text_has("decision=accept") if AGENT == "codex" else text_has('"optionId": "proceed_once"'))

        msg(photo=[{"file_id": "f1", "width": 10, "height": 10}], caption="看图")
        wait_for("photo reaches agent", text_has("imgs=1"))

        now = time.strftime("%Y-%m-%d %H:%M")
        mark[0] = len(sent())
        r = subprocess.run([sys.executable, str(RELAY), "job", "add", "--at", now, "--task", "定时测试"], env=env, capture_output=True, text=True)
        print("  job:", r.stdout.strip() or r.stderr.strip())
        wait_for("scheduled task runs", text_has("定时测试"), 40)

        msg("/new")
        wait_for("/new", text_has("已开新对话"))
        mark[0] = len(sent())
        r = subprocess.run([sys.executable, str(HERE.parent / "relay" / "tgsend.py"), "--pick", "选一个", "A", "B"], env=env, capture_output=True, text=True)
        print("  tgsend:", r.stdout.strip() or r.stderr.strip())
        tap("say:A")
        wait_for("say: button edits message", text_has("✅ 已选择：A"))
        wait_for("say: button reaches agent", text_has("echo: A"))
finally:
    relay.terminate()
    mock.terminate()
    print("---- relay.log (tail)")
    print("\n".join((tmp / "relay.log").read_text().splitlines()[-15:]))

if FAIL:
    sys.exit(f"RELAY TEST FAILED ({AGENT}): {FAIL}")
print(f"RELAY TEST OK ({AGENT}{' real' if REAL else ''})")
