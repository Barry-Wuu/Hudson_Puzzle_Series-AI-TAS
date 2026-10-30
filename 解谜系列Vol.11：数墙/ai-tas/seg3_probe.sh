#!/bin/bash
# seg3 探针启动：limiter ON，不录制。确认 ふつう 第1关是否有教程。
set -u
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native
BASE=/root/.codebuddy/artifact/vol11
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
log(){ echo "[seg3probe $(date +%H:%M:%S)] $*"; }

if ! pgrep -x Xvfb >/dev/null; then
  setsid Xvfb :99 -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 &
  sleep 2
fi
if ! pactl info >/dev/null 2>&1; then
  mkdir -p /run/user/102 /tmp/pulsehome && chown pulse:pulse /run/user/102 /tmp/pulsehome && chmod 700 /run/user/102
  rm -f /tmp/pulse_native
  runuser -u pulse -- env XDG_RUNTIME_DIR=/run/user/102 HOME=/tmp/pulsehome \
    pulseaudio -n -F /tmp/pulse_cfg.pa --exit-idle-time=-1 --disable-shm=1 --disallow-exit \
    --log-target=file:/tmp/pulse.log & sleep 2
fi
log "Xvfb=$(pgrep -x Xvfb|head -1) sink=$(pactl list short sinks 2>/dev/null|grep -o desmume_out|head -1)"

if [ -f /root/.config/desmume/game.dsv.bak_seg2_p5 ]; then
  cp -f /root/.config/desmume/game.dsv.bak_seg2_p5 /root/.config/desmume/game.dsv
  log "restored seg2 save (やさしい 100 done, tutorial done)"
else
  log "WARN: 无 seg2 备份"
fi

pkill -x desmume-cli 2>/dev/null
for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
cd "$BASE"
SDL_VIDEODRIVER=x11 SDL_VIDEO_WINDOW_POS=384,192 SDL_AUDIODRIVER=alsa DISPLAY=:99 \
  setsid desmume-cli --num-cores=1 game.nds >/tmp/desmume_seg3probe.log 2>&1 &
for i in $(seq 1 20); do
  W=$(xdotool search --name -i desmume 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.5
done
[ -n "${W:-}" ] && xdotool windowmove "$W" 384 192 2>/dev/null
log "desmume up; pid=$(pgrep -x desmume-cli|head -1)"

cd "$AITAS"
V11_DIFF=ふつう python3 seg3_probe.py 2>&1 | tee /tmp/seg3_probe.log
log "probe rc=${PIPESTATUS[0]}"

pkill -x desmume-cli 2>/dev/null
for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
log "desmume stopped; PROBE ALL DONE"
