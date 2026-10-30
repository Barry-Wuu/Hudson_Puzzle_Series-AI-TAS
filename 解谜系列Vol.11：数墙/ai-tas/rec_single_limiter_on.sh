#!/bin/bash
# seg1 完整录制（vol13 两阶段法）：正常倍速（限速器ON/60fps 游戏速度）+ 原分辨率
# 256x384 + 无光标 + 有音乐。
# 流程（seg1 模式，默认）：
#   新存档 -> 第1关暖机（吃掉一次性教程，不录）-> 回到选关界面时开录 ->
#   完整录「入门」第2关..第20关 -> 末关清完回选关时停录。
# Hudson→第1关教程整段不录（用户手动补齐）。
#
# ★ 为什么两阶段（照搬 vol13 record_trial.sh §S22-4）：
#   旧版单进程 x11grab@60 + 实时 libopenh264@60 会把抓帧主循环拖到 <60fps，又被
#   -r 60 强制补重复帧 ⇒ 一卡一卡、速度失真。两阶段先裸抓 raw(bgr0) 写 /tmp（零编码，
#   抓帧不被编码抢），音频另起进程抓 pcm_wav；跑完再统一编码+3x 放大+aac。实测不掉帧。
#   录 30fps（vol13 一致，像素解谜观感已顺滑）。
set -u
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native
BASE=/root/.codebuddy/artifact/vol11
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
OUT="${1:-/workspace/数墙_seg1_limiterON.mp4}"
MODE="${2:-seg1}"
FR=30
RAW=/tmp/v11_rec.bgr0
WAV=/tmp/v11_rec.wav
log(){ echo "[seg1-limiterON $(date +%H:%M:%S)] $*"; }

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

# 3. 新存档（先彻底退出旧 desmume 再删档，避免 SIGTERM 延迟落盘把旧进度写回）
pkill -x desmume-cli 2>/dev/null
for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
[ -f /root/.config/desmume/game.dsv ] && cp -f /root/.config/desmume/game.dsv /root/.config/desmume/game.dsv.bak_single 2>/dev/null || true
rm -f /root/.config/desmume/game.dsv
log "fresh save ready (desmume exited=$(pgrep -x desmume-cli | wc -l))"

# 4. desmume：限速器ON（固定60fps 游戏速度，不加 --disable-limiter）。不逐格OCR故无退化。
cd "$BASE"
SDL_VIDEODRIVER=x11 SDL_VIDEO_WINDOW_POS=384,192 SDL_AUDIODRIVER=alsa DISPLAY=:99 \
  setsid desmume-cli --num-cores=1 game.nds >/tmp/desmume_single.log 2>&1 &
DPID=$!
for i in $(seq 1 20); do
  W=$(xdotool search --name -i desmume 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.5
done
[ -n "${W:-}" ] && xdotool windowmove "$W" 384 192 2>/dev/null
log "desmume up pid=$DPID win=${W:-none} (limiter ON / 60fps 游戏速度)"

# 5. 启动 driver（seg1：暖机第1关后录 2..20；或传关卡列表做单关）
rm -f /tmp/v11_rec_start /tmp/v11_rec_stop "$RAW" "$WAV"
cd "$AITAS"
V11_DIFF=入門 python3 test_single_guide.py $MODE > /tmp/single_guide_driver.log 2>&1 &
DRV=$!
log "driver pid=$DRV mode=$MODE ; 等开录哨兵（第1关暖机回选关）..."

# 6. 轮询开录哨兵：第1关清完回选关（/tmp/v11_rec_start）才开始抓帧
VPID=""; APID=""
while [ ! -f /tmp/v11_rec_start ]; do
  if ! kill -0 "$DRV" 2>/dev/null; then
    log "driver 已退出但未触发开录哨兵（可能卡在教程/进关失败）"; break
  fi
  sleep 0.3
done
if [ -f /tmp/v11_rec_start ]; then
  # 阶段1：只抓，不编码。视频 raw bgr0 写磁盘；音频 pcm_wav 另起进程。
  ffmpeg -y -loglevel error -f x11grab -draw_mouse 0 -framerate $FR \
    -video_size 256x384 -i :99+384,192 -pix_fmt bgr0 -f rawvideo "$RAW" \
    >/tmp/ff_vid.log 2>&1 & VPID=$!
  ffmpeg -y -loglevel error -f pulse -i desmume_out.monitor \
    -c:a pcm_s16le "$WAV" >/tmp/ff_aud.log 2>&1 & APID=$!
  log "抓取开始 vid=$VPID aud=$APID (raw, 无编码)"
  T0=$(date +%s.%N)
else
  log "WARN: 未检测到开录哨兵，跳过抓取"
fi

# 7. 等停录哨兵 / driver 结束
while [ ! -f /tmp/v11_rec_stop ]; do
  if ! kill -0 "$DRV" 2>/dev/null; then
    log "driver 已退出（未等到停录哨兵，按 driver 结束收尾）"; break
  fi
  sleep 0.3
done
[ -n "$VPID" ] && kill -INT "$VPID" 2>/dev/null
[ -n "$APID" ] && kill -INT "$APID" 2>/dev/null
sleep 2
if [ -n "${T0:-}" ]; then
  T1=$(date +%s.%N)
  log "抓取墙钟 ≈ $(echo "$T1 - $T0" | bc)s"
fi

# 8. 阶段2：事后编码 + 3x 放大 + aac 合成（此刻无实时压力，可慢慢编）
if [ -s "$RAW" ] && [ -s "$WAV" ]; then
  ffmpeg -y -hide_banner -loglevel warning \
    -f rawvideo -pix_fmt bgr0 -video_size 256x384 -framerate $FR -i "$RAW" \
    -i "$WAV" \
    -vf "scale=768:1152:flags=neighbor" \
    -c:v libopenh264 -pix_fmt yuv420p -r $FR -b:v 3000k \
    -c:a aac -b:a 160k -ar 44100 -ac 2 \
    -movflags +faststart -shortest "$OUT"
  log "=== ffprobe ==="
  ffprobe -v error -show_entries format=duration:stream=codec_type,codec_name,width,height,channels \
    -of default=noprint_wrappers=1 "$OUT" 2>&1
  ls -la "$OUT"
else
  log "WARN: 抓取文件为空，跳过编码（检查 /tmp/ff_vid.log / /tmp/ff_aud.log）"
fi
# 收尾：杀掉 desmume，避免进程泄漏影响下轮
pkill -x desmume-cli 2>/dev/null
log "desmume stopped"
log "DONE"
