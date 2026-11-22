#!/usr/bin/env python3
"""Fixed-format replies for the menu commands (docs/SPEC.md §3).
Usage: tgfmt.py usage|status|help|jobs|memory   -> prints the message text to send."""
import json, os, re, subprocess, sys, time

J = json.load(open(os.path.join(os.environ.get("TGBOX_DIR", "/opt/tgbox/claude"), "status.json")))
TZ = os.environ.get("TGBOX_TZ", "Asia/Singapore")


def bar(left):
    n = int(round(left / 10))
    return f"{'▓' * n}{'░' * (10 - n)} {left:.0f}%"


def refresh(ts):
    m = max(0, int(ts - time.time()) // 60)
    return f"   Refreshes in {m // 60}h {m % 60}m"


def jobs():
    out = []
    for l in subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout.splitlines():
        m = re.search(r"# tgjob (.+)$", l)
        if m and not l.lstrip().startswith("#"):
            out.append(m.group(1).strip())
    return out


cmd = sys.argv[1] if len(sys.argv) > 1 else ""
if cmd == "usage":
    r = J.get("rate_limits") or {}
    lines = ["Claude 额度"]
    for k, label in (("five_hour", "5 小时剩余"), ("seven_day", "本周剩余")):
        if k in r:
            lines += [f"{label}：{bar(100 - r[k]['used_percentage'])}", refresh(r[k]["resets_at"])]
    print("\n".join(lines))
elif cmd == "status":
    print(f"模型：{J['model']['display_name']}\n"
          f"思考强度：{(J.get('effort') or {}).get('level') or '默认'}\n"
          f"工具权限：自动允许（有安全检查）\n"
          f"后台状态：空闲\n"
          f"运行中定时任务：{len(jobs())} 个（时区：{TZ}）\n"
          f"对话：{J['session_id']}")
elif cmd == "help":
    print("Claude 24 小时助手\n"
          "直接发文字、图片、语音、视频或文件：接着当前对话处理\n"
          "/desk 远程接管云电脑（用完自动关端口）\n"
          "/remind 设快捷提醒（如 /remind 20m 喝水）\n"
          "/jobs 查看和管理定时任务与提醒\n"
          "/memory 查看长期记忆\n"
          "/usage 查额度\n"
          "/model 选模型\n"
          "/effort 思考强度\n"
          "/status 当前设置\n"
          "/screen 截云电脑屏幕\n"
          "/help 帮助\n\n"
          "菜单、查额度、远程操控这些功能来自 GitHub 上的 telegram-ai-box。有 bug 或建议，欢迎去仓库留言：\n"
          "https://github.com/chaslab/telegram-ai-box/issues")
elif cmd == "jobs":
    js = jobs()
    if not js:
        print(f"暂无定时任务或提醒（时区：{TZ}）。\n\n用法示例：\n· /remind 20m 喝水\n· /remind 18:30 开会\n"
              "· 直接聊天告诉我，比如「每天早上 8 点给我发科技早报」")
    else:
        print(f"定时任务和提醒（时区：{TZ}）\n" + "\n".join(f"· {j}" for j in js))
elif cmd == "memory":
    lines = ["长期记忆", ""]
    idx = os.environ.get("CLAUDE_MEMORY_INDEX") or os.path.expanduser("~/.claude/projects/" + os.environ.get("TGBOX_WORK", "/root/tgbot").replace("/", "-") + "/memory/MEMORY.md")
    if not os.path.exists(idx):
        sys.exit(print("长期记忆\n\n还没有记忆。跟我说「记住……」，我就会记下来。"))
    for l in open(os.environ.get("CLAUDE_MEMORY_INDEX") or os.path.expanduser("~/.claude/projects/" + os.environ.get("TGBOX_WORK", "/root/tgbot").replace("/", "-") + "/memory/MEMORY.md"), encoding="utf-8"):
        m = re.match(r"- \[(.+?)\]\(.+?\)\s*[—-]\s*(.+)", l.strip())
        if m:
            lines.append(f"· {m.group(1)}：{m.group(2)}")
    print("\n".join(lines))
else:
    sys.exit(__doc__)
