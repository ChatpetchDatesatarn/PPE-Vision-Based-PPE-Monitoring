#!/bin/bash
# Find the Tapo camera's IP at start-up, so CAM_IP never has to be edited by hand (e.g. on a phone hotspot).
#   1) try the cached CAM_IP from ~/safety/.cam.env (TCP 554, 1 s)
#   2) else scan CAM_SCAN_SUBNETS in parallel for an open TCP 554
#   3) confirm each candidate with an RTSP DESCRIBE (Digest or Basic auth) on the stream the app uses: only 200 counts
#   repeat until CAM_DISCOVER_TIMEOUT (default 90 s) — the camera may boot slower than the Jetson
# Found: prints the IP on stdout (nothing else) and exits 0. Not found: exits 1 (caller keeps CAM_IP).
# Log lines go to stderr and ~/safety/logs/cam_discover.log.
#
# Secrets: .cam.env is only sourced, never printed. The DESCRIBE runs in a child bash that reads
# user/pass from stdin; the hashing uses bash builtins + md5sum/base64 on stdin, so the password is
# never in any argv (ps) and never in the environment of a child process.
#
# Env overrides (for tests / other sites; none of them is a secret):
#   CAM_IP=<ip>               replace the cached IP (only for this run)
#   CAM_SCAN_SUBNETS="a/b c/d" subnets to scan (default "172.20.10.0/28 192.168.1.0/24")
#   CAM_STREAM=1|2            stream path to confirm (default 1, same as the app)
#   CAM_DISCOVER_TIMEOUT=90   seconds to keep retrying
#
# Usage: ip=$(bash ~/safety/perception/cam_discover.sh) && CAM_IP=$ip

# ---- child mode: one RTSP DESCRIBE, credentials on stdin (line 1 user, line 2 pass) -----------------
# prints the RTSP status code of the final answer (200 / 401 / ...) or "000" on no answer
if [ "$1" = "--describe" ]; then
  ip=$2; stream=$3
  IFS= read -r u; IFS= read -r p
  uri="rtsp://$ip:554/stream$stream"
  md5() { md5sum | cut -d' ' -f1; }
  exec 3<>"/dev/tcp/$ip/554" || { echo 000; exit 0; }
  # read one RTSP reply from fd 3: sets CODE and HDRS (headers only; DESCRIBE body is not needed)
  reply() {
    CODE=000; HDRS=""; local l
    IFS= read -r -t 3 -u 3 l || return 1
    l=${l%$'\r'}; CODE=$(echo "$l" | awk '{print $2}')
    while IFS= read -r -t 3 -u 3 l; do l=${l%$'\r'}; [ -z "$l" ] && break; HDRS="$HDRS$l"$'\n'; done
  }
  printf 'DESCRIBE %s RTSP/1.0\r\nCSeq: 1\r\nAccept: application/sdp\r\nUser-Agent: cam_discover\r\n\r\n' "$uri" >&3
  reply || { echo 000; exit 0; }
  if [ "$CODE" = 401 ]; then
    # reconnect: some cameras close the socket after 401
    exec 3<&- 3>&-; exec 3<>"/dev/tcp/$ip/554" || { echo 000; exit 0; }
    wa=$(printf '%s' "$HDRS" | grep -i '^WWW-Authenticate:' | grep -i digest | head -1)
    if [ -n "$wa" ]; then
      realm=$(printf '%s' "$wa" | sed -n 's/.*realm="\([^"]*\)".*/\1/p')
      nonce=$(printf '%s' "$wa" | sed -n 's/.*nonce="\([^"]*\)".*/\1/p')
      ha1=$(printf '%s:%s:%s' "$u" "$realm" "$p" | md5)
      ha2=$(printf 'DESCRIBE:%s' "$uri" | md5)
      resp=$(printf '%s:%s:%s' "$ha1" "$nonce" "$ha2" | md5)
      auth="Digest username=\"$u\", realm=\"$realm\", nonce=\"$nonce\", uri=\"$uri\", response=\"$resp\""
    else
      auth="Basic $(printf '%s:%s' "$u" "$p" | base64 -w0)"
    fi
    printf 'DESCRIBE %s RTSP/1.0\r\nCSeq: 2\r\nAccept: application/sdp\r\nUser-Agent: cam_discover\r\nAuthorization: %s\r\n\r\n' "$uri" "$auth" >&3
    reply || { echo 000; exit 0; }
  fi
  echo "$CODE"
  exit 0
fi

# ---- main ----------------------------------------------------------------------------------------
SELF=$(readlink -f "$0")
ENVF="$HOME/safety/.cam.env"
LOGF="$HOME/safety/logs/cam_discover.log"
mkdir -p "$(dirname "$LOGF")"
log() { echo "$(date '+%F %T') cam_discover: $*" | tee -a "$LOGF" >&2; }

OVR_IP=${CAM_IP-}            # an env CAM_IP given by the caller wins over the file (tests)
[ -f "$ENVF" ] || { log "missing $ENVF"; exit 1; }
set +x
# shellcheck disable=SC1090
. "$ENVF"
[ -n "$OVR_IP" ] && CAM_IP=$OVR_IP
[ -n "$CAM_USER" ] && [ -n "$CAM_PASS" ] || { log "CAM_USER/CAM_PASS not set in .cam.env"; exit 1; }
export -n CAM_USER CAM_PASS  # never hand them to child processes through the environment
SUBNETS=${CAM_SCAN_SUBNETS:-"172.20.10.0/28 192.168.1.0/24"}
STREAM=${CAM_STREAM:-1}
LIMIT=${CAM_DISCOVER_TIMEOUT:-45}

port_open() { timeout -s 9 1 bash -c "exec 3<>/dev/tcp/$1/554" 2>/dev/null; }

# RTSP DESCRIBE with auth; credentials on stdin of the child (bash builtin printf: no argv, no env)
confirm() {
  local code
  code=$(printf '%s\n%s\n' "$CAM_USER" "$CAM_PASS" | timeout -s 9 5 bash "$SELF" --describe "$1" "$STREAM" 2>/dev/null)
  [ -n "$code" ] || code=000
  [ "$code" = 200 ] && return 0
  log "  $1:554 answered RTSP $code (not ours / wrong password)"
  return 1
}

# all host IPs of a.b.c.d/n (n >= 16), excluding network and broadcast
hosts() {
  local ip=${1%/*} n=${1#*/} a b c d base size i
  IFS=. read -r a b c d <<<"$ip"
  size=$(( 1 << (32 - n) ))
  base=$(( ((a << 24) | (b << 16) | (c << 8) | d) & ~(size - 1) & 0xFFFFFFFF ))
  for (( i = 1; i < size - 1; i++ )); do
    local x=$(( base + i ))
    echo "$(( (x >> 24) & 255 )).$(( (x >> 16) & 255 )).$(( (x >> 8) & 255 )).$(( x & 255 ))"
  done
}

# parallel TCP 554 scan of one subnet (16 at a time, 1 s timeout each); prints open IPs
scan() {
  hosts "$1" | xargs -P 16 -I{} bash -c 'timeout -s 9 1 bash -c "exec 3<>/dev/tcp/{}/554" 2>/dev/null && echo {}' | sort -t. -k4,4n
}

T0=$(date +%s.%N)
elapsed() { awk -v a="$T0" -v b="$(date +%s.%N)" 'BEGIN { printf "%.1f", b - a }'; }
round=0
while :; do
  round=$((round + 1))
  if [ -n "$CAM_IP" ] && port_open "$CAM_IP" && confirm "$CAM_IP"; then
    log "camera found at $CAM_IP (via cached) stream$STREAM in $(elapsed) s, round $round"
    echo "$CAM_IP"; exit 0
  fi
  [ "$round" = 1 ] && log "cached CAM_IP ${CAM_IP:-<empty>} not confirmed (no TCP 554 or no RTSP 200) — scanning: $SUBNETS"
  for net in $SUBNETS; do
    for ip in $(scan "$net"); do
      [ "$ip" = "$CAM_IP" ] && continue
      if confirm "$ip"; then
        log "camera found at $ip (via scan $net) stream$STREAM in $(elapsed) s, round $round"
        sed -i "s/CAM_IP=.*/CAM_IP=$ip/" "$ENVF" 2>/dev/null
        echo "$ip"; exit 0
      fi
    done
  done
  if awk -v e="$(elapsed)" -v l="$LIMIT" 'BEGIN { exit !(e + 3 >= l) }'; then break; fi
  sleep 2
done
log "camera NOT found after $(elapsed) s ($round rounds) — keeping CAM_IP ${CAM_IP:-<empty>}"
exit 1
