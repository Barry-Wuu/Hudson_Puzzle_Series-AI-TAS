#!/bin/bash
# seg4 准备：启动 desmume（limiter ON）+ 跑 seg4_explore.py 定位 BGM3 按钮。
set -u
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native
BASE=/root/.codebuddy/artifact/vol11
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
log(){ echo "[seg4prep $(date +%H:%M:%S)] $*"; }

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

pkill -x desmume-cli 2>/dev/null
for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
cd "$BASE"
SDL_VIDEODRIVER=x11 SDL_VIDEO_WINDOW_POS=384,192 SDL_AUDIODRIVER=alsa DISPLAY=:99 \
  setsid desmume-cli --num-cores=1 game.nds >/tmp/desmume_seg4prep.log 2>&1 &
for i in $(seq 1 20); do
  W=$(xdotool search --name -i desmume 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.5
done
[ -n "${W:-}" ] && xdotool windowmove "$W" 384 192 2>/dev/null
log "desmume up; pid=$(pgrep -x desmume-cli|head -1)"

cd "$AITAS"
V11_DIFF=むずかしい python3 seg4_explore.py 2>&1 | tee /tmp/seg4_explore.log
log "explore rc=${PIPESTATUS[0]}"
