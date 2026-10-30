#!/bin/bash
# seg1 正式录制：新存档 + HUDSON logo 起录 + 入門 20 关全过 + 回选关
# 无 X 光标 / 256x384 原分辨率 / 有音乐（PulseAudio desmume_out.monitor）
set -e
BASE=/root/.codebuddy/artifact/vol11
AI="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
OUT="${1:-/workspace/数墙_入門实况_seg1.mp4}"
export PULSE_SERVER=unix:/tmp/pulse_native
export DISPLAY=:99

# 1. 停 desmume
pkill -x desmume-cli || true
sleep 1.5

# 2. 备份并删除存档（新起存档）
[ -f /root/.config/desmume/game.dsv ] && cp /root/.config/desmume/game.dsv /root/.config/desmume/game.dsv.bak_before_seg1
rm -f /root/.config/desmume/game.dsv
echo "saved backup, fresh save"

# 3. 先启动 ffmpeg（保证 HUDSON logo 入镜）
ffmpeg -y -f x11grab -framerate 30 -video_size 256x384 -draw_mouse 0 -i :99+384,192 \
  -f pulse -i desmume_out.monitor \
  -c:v libopenh264 -b:v 3000k -g 60 -pix_fmt yuv420p \
  -c:a aac -b:a 160k -shortest "$OUT" > /tmp/ffmpeg_seg1.log 2>&1 &
FFPID=$!
echo "$FFPID" > /tmp/seg1_ffmpeg.pid
echo "ffmpeg pid=$FFPID -> $OUT"
sleep 1.0

# 4. 启动 desmume（开声音）
cd "$BASE"
SDL_VIDEODRIVER=x11 SDL_VIDEO_WINDOW_POS=384,192 SDL_AUDIODRIVER=alsa \
  PULSE_SERVER=unix:/tmp/pulse_native DISPLAY=:99 \
  desmume-cli --cpu-mode=1 --num-cores=1 --disable-limiter game.nds > /tmp/desmume_seg1.log 2>&1 &
DPID=$!
echo "$DPID" > /tmp/seg1_desmume.pid
echo "desmume pid=$DPID (HUDSON logo 出现中)"

# 5. 等窗口就绪
for i in $(seq 1 40); do
  sleep 0.5
  if xdotool search --name desmume > /dev/null 2>&1; then
    xdotool search --name desmume | head -1 | xargs -I{} xdotool windowmove {} 384 192
    xdotool search --name desmume | head -1 | xargs -I{} xdotool windowfocus {}
    break
  fi
done
echo "window ready"
