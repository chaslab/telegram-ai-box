#!/usr/bin/env python3
"""Print ```bash blocks of INSTALL-FOR-AI.md so CI runs exactly what the doc tells the AI to run.
    extract.py INSTALL-FOR-AI.md base files ...   blocks marked <!-- ci:NAME --> (or 1-based numbers)"""
import re, sys
doc = open(sys.argv[1], encoding="utf-8").read()
named = dict(re.findall(r"<!-- ci:([\w-]+) -->\s*```bash\n(.*?)```", doc, re.S))
blocks = re.findall(r"```bash\n(.*?)```", doc, re.S)
for n in sys.argv[2:]:
    print(f"# ---- block {n}\n" + (named[n] if n in named else blocks[int(n) - 1]))
