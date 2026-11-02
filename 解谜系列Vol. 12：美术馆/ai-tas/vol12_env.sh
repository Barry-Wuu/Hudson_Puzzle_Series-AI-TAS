#!/bin/bash
# vol12 录制/校准环境启动：Xvfb + pulse(desmume_out null sink) + desmume-cli(vol12 ROM)
# 校准阶段用 --disable-sound 减轻负载；正式录制时去掉该参数并开 ffmpeg 收音。
set -u
export DISPLAY=:99
# ★ 2026-10-28 修：desmume 的 SDL alsa 走 ALSA->pulse 插件，必须让它连上自建 pulse
#   socket，否则 "PulseAudio: Unable to connect: Connection refused"、desmume_out.monitor
#   录到的全是静音（Vol.11 rec_seg1_v2.sh 有此行，vol12_env.sh 漏了）。
export PULSE_SERVER=unix:/tmp/pulse_native
ART=/root/.codebuddy/artifact/vol12
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol. 12：美术馆/ai-tas"
SOUND=${1:-off}   # off=静音校准, on=收音录制
log(){ echo "[vol12env $(date +%H:%M:%S)] $*"; }

# 1. Xvfb
if ! pgrep -x Xvfb >/dev/null; then
  setsid Xvfb :99 -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 &
  sleep 2
fi
log "Xvfb=$(pgrep -x Xvfb|head -1)"

# 2. pulse
if ! pgrep -x pulseaudio >/dev/null; then
  mkdir -p /run/user/102 /tmp/pulsehome && chown -R pulse:pulse /run/user/102 /tmp/pulsehome 2>/dev/null
  rm -f /tmp/pulse_native
  runuser -u pulse -- env XDG_RUNTIME_DIR=/run/user/102 HOME=/tmp/pulsehome \
    pulseaudio -n -F /tmp/pulse_cfg.pa --exit-idle-time=-1 --disable-shm=1 --disallow-exit \
    --log-target=file:/tmp/pulse.log & sleep 2
fi
log "pulse sink=$(pactl list short sinks 2>/dev/null|grep -o desmume_out|head -1)"

# 3. 清旧 desmume
pkill -x desmume-cli 2>/dev/null; sleep 1

# 4. desmume：固定窗口到 (384,192)，256x384
cd "$ART"
SND_FLAG=""
[ "$SOUND" = "on" ] && SND_FLAG="SDL_AUDIODRIVER=alsa"
# ★ 2026-10-28 存档隔离：ROM 文件名必须是 vol12.nds（desmume 按文件名存 ~/.config/desmume/<名>.dsv）。
#   曾用 game.nds 导致与 Vol.11 共用 game.dsv、槽位页误读 Vol.11 进度（80.6% 五段）。
# ★ 2026-10-29 修（seg3 快进事故）：--disable-limiter 只允许用于静音校准（SOUND=off）。
#   录制模式（SOUND=on）必须 limiter ON（不加该参数），否则模拟器全速运行，
#   x11grab 按墙钟 30fps 抓屏 ⇒ 成片游戏时间以 ~3-6 倍速流逝 = 快进。
#   （seg1/seg2 当年靠手动起 limiter-ON 实例侥幸避开；seg3 崩溃重启走了本脚本中招。）
if [ "$SOUND" = "on" ]; then
  # ★2026-11-03 修：--spu-mode=1 (Synchronous) 是 desmume 流式 BGM 卡顿的标准开关；
  #   默认 0(Dual Synch/Asynch) 在 CPU 争抢下会让音乐出现断点。limiter 仍 ON（不加
  #   --disable-limiter），保录制不快进。
  SDL_VIDEODRIVER=x11 SDL_VIDEO_WINDOW_POS=384,192 SDL_AUDIODRIVER=alsa \
    setsid desmume-cli --cpu-mode=1 --num-cores=1 --spu-mode=1 vol12.nds >/tmp/desmume_vol12.log 2>&1 &
else
  SDL_VIDEODRIVER=x11 SDL_VIDEO_WINDOW_POS=384,192 \
    setsid desmume-cli --cpu-mode=1 --num-cores=1 --spu-mode=1 --disable-limiter --disable-sound vol12.nds >/tmp/desmume_vol12.log 2>&1 &
fi
DPID=$!
for i in $(seq 1 20); do
  W=$(xdotool search --name '[Dd]esmume' 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.5
done
[ -n "${W:-}" ] && xdotool windowmove "$W" 384 192 2>/dev/null
log "desmume pid=$DPID win=${W:-none}"
echo "$DPID" > /tmp/vol12_desmume.pid
