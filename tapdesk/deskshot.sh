#!/bin/bash
# Screenshot this machine's cloud desktop (:99). Usage: deskshot.sh [out.jpg]; prints the jpg path.
# Any bot on this machine may use it for /screen (looking is fine even while another bot holds the deskctl lock).
OUT=${1:-/tmp/deskshot.jpg}
pgrep -x Xvfb >/dev/null || { systemctl restart clouddesk.service; sleep 8; }
ffmpeg -loglevel error -y -f x11grab -video_size 1280x800 -i :99 -frames:v 1 -q:v 3 "$OUT" </dev/null && echo "$OUT"
