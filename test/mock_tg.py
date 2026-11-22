#!/usr/bin/env python3
"""A tiny fake Telegram Bot API for testing relay/tgrelay.py without a real bot.
    POST /ctl/push  {update without update_id}   queue an update for getUpdates
    GET  /ctl/sent                                  every bot API call made so far (JSON list)
Everything under /bot<token>/<method> answers like Telegram would (good enough for the relay)."""
import json, sys, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

UPDATES, SENT, LOCK, NEW = [], [], threading.Lock(), threading.Condition()
SEQ = {"u": 0, "m": 1000}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/ctl/sent":
            with LOCK:
                return self._json(SENT)
        if self.path.startswith("/file/"):
            b = b"\xff\xd8fakejpeg"
            self.send_response(200)
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            return self.wfile.write(b)
        self._json({"ok": False})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n)
        if self.path == "/ctl/push":
            u = json.loads(raw)
            with NEW:
                SEQ["u"] += 1
                u["update_id"] = SEQ["u"]
                UPDATES.append(u)
                NEW.notify_all()
            return self._json({"ok": True})
        method = self.path.rsplit("/", 1)[-1]
        ctype = self.headers.get("Content-Type", "")
        params = json.loads(raw or b"{}") if "json" in ctype else {"_multipart": True, "_bytes": len(raw)}
        if method != "getUpdates":
            with LOCK:
                SENT.append({"method": method, **params})
        if method == "getUpdates":
            off = params.get("offset") or 0
            deadline = time.time() + min(int(params.get("timeout") or 0), 3)
            with NEW:
                while True:
                    out = [u for u in UPDATES if u["update_id"] >= off]
                    if out or time.time() > deadline:
                        break
                    NEW.wait(0.2)
            return self._json({"ok": True, "result": out})
        if method == "getMe":
            return self._json({"ok": True, "result": {"id": 1, "is_bot": True, "username": "test_bot"}})
        if method == "getFile":
            return self._json({"ok": True, "result": {"file_path": "photos/x.jpg"}})
        if method in ("sendMessage", "sendPhoto", "sendDocument", "editMessageText"):
            SEQ["m"] += 1
            return self._json({"ok": True, "result": {"message_id": params.get("message_id") or SEQ["m"]}})
        return self._json({"ok": True, "result": True})


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8799
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
