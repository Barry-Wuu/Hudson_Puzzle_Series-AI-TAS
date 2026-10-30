#!/bin/bash
# seg3 剂量测试启动脚本：limiter ON（=录屏时游戏速度），不录制。
# 复用 seg2 存档（やさしい 100 关 done，无教程），测同尺寸关卡即可等价ふつう。
set -u
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native
BASE=/root/.codebuddy/artifact/vol11
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
log(){ echo "[seg3dose $(date +%H:%M:%S)] $*"; }

# 1. Xvfb
if ! pgrep -x Xvfb >/dev/null; then
  setsid Xvfb :99 -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 &
  sleep 2
fi
# 2. PulseAudio + desmume_out 空 sink
if ! pactl info >/dev/null 2>&1; then
  mkdir -p /run/user/102 /tmp/pulsehome && chown pulse:pulse /run/user/102 /tmp/pulsehome && chmod 700 /run/user/102
  rm -f /tmp/pulse_native
  runuser -u pulse -- env XDG_RUNTIME_DIR=/run/user/102 HOME=/tmp/pulsehome \
    pulseaudio -n -F /tmp/pulse_cfg.pa --exit-idle-time=-1 --disable-shm=1 --disallow-exit \
    --log-target=file:/tmp/pulse.log & sleep 2
fi
log "Xvfb=$(pgrep -x Xvfb|head -1) sink=$(pactl list short sinks 2>/dev/null|grep -o desmume_out|head -1)"

# 3. 恢复 seg2 存档（やさしい 100 done，无教程）—— 用同尺寸等价测
if [ -f /root/.config/desmume/game.dsv.bak_seg2_p5 ]; then
  cp -f /root/.config/desmume/game.dsv.bak_seg2_p5 /root/.config/desmume/game.dsv
  log "restored seg2 save (やさしい 100 done, tutorial done)"
elif [ -f /root/.config/desmume/game.dsv.bak_seg2_p3 ]; then
  cp -f /root/.config/desmume/game.dsv.bak_seg2_p3 /root/.config/desmume/game.dsv
  log "restored seg2 p3 save (やさしい ~61)"
else
  log "WARN: 无 seg2 备份存档，将用现有/新存档（可能有教程，首次关会慢）"
fi

# 4. 启动 desmume（limiter ON，不加 --disable-limiter）
pkill -x desmume-cli 2>/dev/null
for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
cd "$BASE"
SDL_VIDEODRIVER=x11 SDL_VIDEO_WINDOW_POS=384,192 SDL_AUDIODRIVER=alsa DISPLAY=:99 \
  setsid desmume-cli --num-cores=1 game.nds >/tmp/desmume_seg3dose.log 2>&1 &
for i in $(seq 1 20); do
  W=$(xdotool search --name -i desmume 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.5
done
[ -n "${W:-}" ] && xdotool windowmove "$W" 384 192 2>/dev/null
log "desmume up (limiter ON); pid=$(pgrep -x desmume-cli|head -1)"

# 5. 跑剂量测试 driver（不录制）
cd "$AITAS"
V11_DIFF=やさしい python3 seg3_dose_test.py > /tmp/seg3_dose_driver.log 2>&1
rc=$?
log "driver rc=$rc"

# 6. 收尾
pkill -x desmume-cli 2>/dev/null
for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
log "desmume stopped"
log "ALL DONE"
