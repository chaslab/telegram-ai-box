#!/bin/bash
# Cloud desktop for your bot: Xvfb virtual screen + XFCE + Chrome (DevTools on 127.0.0.1:9222).
# Usage: desk.sh browser|stop|status      (normally started by clouddesk.service)
D=${CLOUDDESK_DIR:-/opt/clouddesk}
DISP=${CLOUDDESK_DISPLAY:-:99}
CHROME=${CLOUDDESK_CHROME:-$(command -v google-chrome || command -v chromium || echo google-chrome)}
LOG=$D/log; mkdir -p "$LOG" "$D/profile"

running() { pgrep -f "$1" >/dev/null; }

browser() {
  running "Xvfb $DISP" || { nohup Xvfb $DISP -screen 0 1280x800x24 -nolisten tcp >"$LOG/xvfb.log" 2>&1 & sleep 1; }
  export DISPLAY=$DISP
  # pgrep -x: exact process name, so a shell command line that merely mentions it doesn't count
  pgrep -x xfce4-session >/dev/null || { nohup dbus-launch --exit-with-session xfce4-session >"$LOG/xfce.log" 2>&1 & sleep 4; }
  startchrome
}

startchrome() {
  running "user-data-dir=$D/profile" || nohup "$CHROME" --no-sandbox --user-data-dir="$D/profile" \
      --remote-debugging-address=127.0.0.1 --remote-debugging-port=9222 \
      --no-first-run --no-default-browser-check --disable-sync --start-maximized \
      --window-size=1280,800 --window-position=0,0 about:blank >"$LOG/chrome.log" 2>&1 &
  for i in $(seq 1 20); do curl -s -m 1 127.0.0.1:9222/json/version >/dev/null && break; sleep 0.5; done
  # make sure the Chrome window is maximized (alt+F10 toggles, so only when it isn't)
  W=$(DISPLAY=$DISP xdotool search --onlyvisible --class chrom 2>/dev/null | head -1)
  if [ -n "$W" ] && ! DISPLAY=$DISP xprop -id "$W" _NET_WM_STATE | grep -q MAXIMIZED_HORZ; then
    DISPLAY=$DISP xdotool windowactivate --sync "$W" key alt+F10
  fi
}

stop() {
  pkill -f "user-data-dir=$D/profile"
  pkill -x xfce4-session; pkill -x xfce4-panel; pkill -x xfdesktop; pkill -x xfwm4
  pkill -f "Xvfb $DISP"
  echo stopped
}

status() {
  running "Xvfb $DISP" && echo "up   screen $DISP" || echo "DOWN screen $DISP"
  pgrep -x xfce4-session >/dev/null && echo "up   xfce" || echo "DOWN xfce"
  running "user-data-dir=$D/profile" && echo "up   chrome" || echo "DOWN chrome"
  curl -s -m 3 127.0.0.1:9222/json/version | grep -o '"Browser"[^,]*'
}

case "$1" in
  browser) browser;; stop) stop;; status) status;;
  *) echo "usage: $0 browser|stop|status";;
esac
