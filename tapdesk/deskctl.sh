#!/bin/bash
# deskctl.sh: occupancy lock for one cloud desktop shared by several bots on the same machine.
# Every bot calls `acquire` before driving the desktop/browser, `beat` between steps, `release` when done.
#
#   deskctl.sh acquire <bot> "<task>"   0 = got it (or already mine / stale lock taken over)
#                                        1 = busy -> prints: BUSY <bot>|<task>|<minutes>
#   deskctl.sh preempt <bot> "<task>"   take it over even if busy (only after the user chose 挤下它)
#   deskctl.sh beat <bot>               0 = still mine; 2 = PREEMPTED <by>|<task>: stop driving now
#   deskctl.sh release <bot>            free it (only if mine)
#   deskctl.sh status                   FREE, or BUSY <bot>|<task>|<minutes>
#
# A lock without a heartbeat for STALE seconds (default 600) counts as free.
# Env: DESKCTL_DIR (default /var/lib/clouddesk), DESKCTL_DISPLAY (default :99), DESKCTL_STALE.
DIR=${DESKCTL_DIR:-/var/lib/clouddesk}; mkdir -p "$DIR" 2>/dev/null
F="$DIR/lock${DESKCTL_DISPLAY:-:99}"; F=${F/:/-}
STALE=${DESKCTL_STALE:-600}
now=$(date +%s)
exec 9>"$F.flock"; flock -w 5 9 || { echo "ERR lock timeout"; exit 3; }

read_lock() { owner=""; task=""; since=0; beat=0
  [ -f "$F" ] && IFS='|' read -r owner task since beat < "$F"
  if [ -n "$owner" ] && [ $((now - ${beat:-0})) -gt "$STALE" ]; then owner=""; fi; }
write_lock() { printf '%s|%s|%s|%s\n' "$1" "$2" "$3" "$now" > "$F"; }
busy_line() { echo "BUSY $owner|$task|$(( (now - since) / 60 ))"; }

cmd=$1; bot=$2; what=${3:-}
read_lock
case "$cmd" in
  acquire)
    if [ -z "$owner" ] || [ "$owner" = "$bot" ]; then
      [ "$owner" = "$bot" ] && s=$since || s=$now
      write_lock "$bot" "$what" "$s"; echo OK; exit 0
    fi
    busy_line; exit 1 ;;
  preempt)
    [ -n "$owner" ] && [ "$owner" != "$bot" ] && printf '%s|%s\n' "$bot" "$what" > "$F.preempted-$owner"
    write_lock "$bot" "$what" "$now"; echo OK; exit 0 ;;
  beat)
    if [ -f "$F.preempted-$bot" ]; then echo "PREEMPTED $(cat "$F.preempted-$bot")"; rm -f "$F.preempted-$bot"; exit 2; fi
    if [ "$owner" = "$bot" ]; then write_lock "$bot" "$task" "$since"; echo OK; exit 0; fi
    if [ -z "$owner" ]; then echo "FREE"; exit 0; fi
    echo "PREEMPTED $owner|$task"; exit 2 ;;
  release)
    [ "$owner" = "$bot" ] && rm -f "$F"; rm -f "$F.preempted-$bot"; echo OK ;;
  status)
    [ -z "$owner" ] && echo FREE || busy_line ;;
  *) sed -n 2,14p "$0"; exit 1 ;;
esac
