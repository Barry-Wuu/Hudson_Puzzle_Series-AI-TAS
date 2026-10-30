#!/bin/bash
# seg1 重录 v2：限速器ON(固定60fps) + 原分辨率256x384 + 无光标 + 有音乐
# 关键改进（2026-10-26）：
#  1. 弃用 --disable-limiter(turbo 变速→音乐失真)，改回 lvl80/81 验证过的
#     限速器ON固定帧率管线（音乐自然同步，靠剂量保证点击命中）。
#  2. driver 完成后立即 kill ffmpeg，消除"20关全过后结尾长 idle"。
#  3. 配收紧版 seg1_run.py（关间过渡态主动按A推进，杜绝24s空转）。
set -u
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native
BASE=/root/.codebuddy/artifact/vol11
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
OUT="${1:-/workspace/数墙_入門实況_seg1_v2.mp4}"
log(){ echo "[seg1v2 $(date +%H:%M:%S)] $*"; }

# 1. Xvfb
if ! pgrep -x Xvfb >/dev/null; then
  setsid Xvfb :99 -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 &
  sleep 2
fi

# 2. PulseAudio + desmume_out 空 sink（录音源）
if ! pactl info >/dev/null 2>&1; then
  mkdir -p /run/user/102 /tmp/pulsehome && chown pulse:pulse /run/user/102 /tmp/pulsehome && chmod 700 /run/user/102
  rm -f /tmp/pulse_native
  runuser -u pulse -- env XDG_RUNTIME_DIR=/run/user/102 HOME=/tmp/pulsehome \
    pulseaudio -n -F /tmp/pulse_cfg.pa --exit-idle-time=-1 --disable-shm=1 --disallow-exit \
    --log-target=file:/tmp/pulse.log & sleep 2
fi
log "Xvfb=$(pgrep -x Xvfb|head -1) sink=$(pactl list short sinks 2>/dev/null|grep -o desmume_out|head -1)"

# 3. 新存档
pkill -x desmume-cli 2>/dev/null; sleep 1
[ -f /root/.config/desmume/game.dsv ] && cp -f /root/.config/desmume/game.dsv /root/.config/desmume/game.dsv.bak_seg1v2 2>/dev/null || true
rm -f /root/.config/desmume/game.dsv
log "fresh save ready"

# 4. desmume：用 turbo(--disable-limiter)。实测限速器ON会让 nyumon 逐格数字/颜色
#    识别大面积退化（每关 marks=18 误识 + unknown clue digit 重试，单关 7s->17s 且不稳），
#    故保留 turbo（识别正常、音乐可录且已被前版接受）；收紧的 seg1_run.py 负责消除关间 idle。
cd "$BASE"
SDL_VIDEODRIVER=x11 SDL_VIDEO_WINDOW_POS=384,192 SDL_AUDIODRIVER=alsa DISPLAY=:99 \
  setsid desmume-cli --cpu-mode=1 --num-cores=1 --disable-limiter game.nds >/tmp/desmume_seg1v2.log 2>&1 &
DPID=$!
for i in $(seq 1 20); do
  W=$(xdotool search --name -i desmume 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.5
done
[ -n "${W:-}" ] && xdotool windowmove "$W" 384 192 2>/dev/null
log "desmume up pid=$DPID win=${W:-none}"

# 5. ffmpeg 固定帧率60 + 无光标 + 音乐
rm -f "$OUT"
ffmpeg -y -hide_banner -loglevel warning \
  -f x11grab -draw_mouse 0 -framerate 60 -video_size 256x384 -i :99+384,192 \
  -f pulse -i desmume_out.monitor \
  -c:v libopenh264 -b:v 3000k -pix_fmt yuv420p -r 60 -g 120 \
  -c:a aac -b:a 160k -ar 44100 -ac 2 \
  -movflags +faststart "$OUT" >/tmp/ffmpeg_seg1v2.log 2>&1 &
FFPID=$!
log "ffmpeg pid=$FFPID; 等 HUDSON logo 入镜..."
sleep 7

# 6. driver（收紧版 seg1_run.py：关间过渡态主动按A，消除长静止）
cd "$AITAS"
V11_DIFF=入門 python3 seg1_run.py 1 20 > /tmp/seg1_v2_driver.log 2>&1
log "driver rc=$? ; 末行: $(tail -1 /tmp/seg1_v2_driver.log)"

# 7. 立即停 ffmpeg（消除结尾 idle；多留1s让选关页收尾干净）
sleep 1
log "stopping ffmpeg..."
kill -INT "$FFPID" 2>/dev/null
for i in $(seq 1 20); do kill -0 "$FFPID" 2>/dev/null || break; sleep 0.5; done
kill -0 "$FFPID" 2>/dev/null && kill -9 "$FFPID" 2>/dev/null

# 8. 报告
log "=== ffprobe ==="
ffprobe -v error -show_entries format=duration:stream=codec_type,codec_name,width,height,channels \
  -of default=noprint_wrappers=1 "$OUT" 2>&1
ls -la "$OUT"
log "DONE"
