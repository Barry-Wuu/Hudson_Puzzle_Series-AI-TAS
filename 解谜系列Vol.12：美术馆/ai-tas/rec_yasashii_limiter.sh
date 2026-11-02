#!/bin/bash
# Vol.12 美術館(Akari) yasashii（やさしい Q81..Q100）実況录制 —— limiter ON 两阶段法
#
# 复用 muzusaki 已验证管线：固定帧率 30fps（阶段1 裸抓 bgr0@30 + 阶段2 -r 30 编码）、
# 有声（pulse desmume_out.monitor → aac）、原分辨率 256x384（不放大）。
# 两阶段：裸抓零编码（抓帧不被编码抢）、跑完再统一 libopenh264 + aac 合成。
# DeSmuME 必须 limiter ON（不加 --disable-limiter），否则 ~3-6 倍快进。
#
# 用法: bash rec_yasashii_limiter.sh <out.mp4> <起始关> <结束关>
set -u
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native
AITAS="/workspace/hudson_tas/解谜系列Vol.12：美术馆/ai-tas"
OUT="${1:-/workspace/美術館_やさしい実況.mp4}"
LO="${2:-81}"
HI="${3:-100}"
FR=30
RAW=/tmp/v12_yasa_rec_${LO}_${HI}.bgr0
WAV=/tmp/v12_yasa_rec_${LO}_${HI}.wav
SENTINEL=/tmp/v12_yasa_rec_start
STOP_SENTINEL=/tmp/v12_yasa_rec_stop
log(){ echo "[vol12-yasa $(date +%H:%M:%S)] $*"; }

# 任何退出都确保杀掉抓取进程，杜绝孤儿进程把 raw 越写越大
trap 'pkill -INT -f "v12_yasa_rec" 2>/dev/null; true' EXIT

# 1. 环境守卫
pgrep -x Xvfb >/dev/null || { log "!! Xvfb 未运行"; exit 1; }
if ! pgrep -x desmume-cli >/dev/null; then
  log "!! desmume 未运行（请先起 limiter ON 的实例: bash vol12_env.sh on）"; exit 1; fi
DPID=$(pgrep -x desmume-cli | head -1)
if tr '\0' ' ' < "/proc/$DPID/cmdline" 2>/dev/null | grep -q -- "--disable-limiter"; then
  log "!! desmume(pid=$DPID) 带 --disable-limiter，会录出快进画面。请先: bash vol12_env.sh on 重启实例"; exit 1
fi
log "limiter 校验通过 pid=$DPID"
W=$(xdotool search --name "[Dd]esmume" 2>/dev/null | head -1)
[ -n "$W" ] && xdotool windowmove "$W" 384 192 2>/dev/null && xdotool windowfocus "$W" 2>/dev/null
log "desmume win=$W  sink=$(pactl list short sinks 2>/dev/null | grep -c desmume_out)"

# 2. 清哨兵
rm -f "$SENTINEL" "$STOP_SENTINEL" "$RAW" "$WAV"

# 3. 启动 driver（自行切到やさしい选关页，导航到 Q$LO 后触发开录哨兵）
cd "$AITAS"
python3.11 play_yasashii.py "$LO" "$HI" > /tmp/vol12_yasa_driver.log 2>&1 &
DRV=$!
log "driver pid=$DRV ; 等开录哨兵..."

# 4. 轮询开录哨兵
VPID=""; APID=""; T0=""
while [ ! -f "$SENTINEL" ]; do
  if ! kill -0 "$DRV" 2>/dev/null; then
    log "driver 已退出但未触发开录哨兵（看 /tmp/vol12_yasa_driver.log）"; break; fi
  sleep 0.2
done
if [ -f "$SENTINEL" ]; then
  ffmpeg -y -loglevel error -f x11grab -draw_mouse 0 -framerate $FR \
    -video_size 256x384 -i :99+384,192 -pix_fmt bgr0 -f rawvideo "$RAW" \
    >/tmp/ff_v12yasa_vid.log 2>&1 & VPID=$!
  ffmpeg -y -loglevel error -f pulse -i desmume_out.monitor \
    -c:a pcm_s16le "$WAV" >/tmp/ff_v12yasa_aud.log 2>&1 & APID=$!
  log "抓取开始 vid=$VPID aud=$APID (raw bgr0 @${FR}fps, 无编码)"
  T0=$(date +%s.%N)
else
  log "WARN: 未检测到开录哨兵，跳过抓取 —— 判失败"
  exit 1
fi

# 5. 等停录哨兵 / driver 结束
while [ ! -f "$STOP_SENTINEL" ]; do
  if ! kill -0 "$DRV" 2>/dev/null; then
    log "driver 已退出（按 driver 结束收尾）"; break; fi
  sleep 0.3
done
sleep 1
[ -n "$VPID" ] && kill -INT "$VPID" 2>/dev/null
[ -n "$APID" ] && kill -INT "$APID" 2>/dev/null
sleep 2
if grep -q "FAIL Q" /tmp/vol12_yasa_driver.log 2>/dev/null; then
  log "!! driver 判定失败（FAIL Q）—— 本 chunk 作废"
  exit 1
fi
if [ -n "${T0:-}" ]; then
  T1=$(date +%s.%N)
  log "抓取墙钟 ≈ $(echo "$T1 - $T0" | bc)s"
fi
log "driver 末行: $(tail -3 /tmp/vol12_yasa_driver.log | tr '\n' ' ')"

# 6. 阶段2：事后编码 + aac 合成
if [ -s "$RAW" ] && [ -s "$WAV" ]; then
  ffmpeg -y -hide_banner -loglevel warning \
    -f rawvideo -pix_fmt bgr0 -video_size 256x384 -framerate $FR -i "$RAW" \
    -i "$WAV" \
    -c:v libopenh264 -pix_fmt yuv420p -r $FR -b:v 3000k \
    -c:a aac -b:a 160k -ar 44100 -ac 2 \
    -movflags +faststart -shortest "$OUT"
  log "=== ffprobe ==="
  ffprobe -v error -show_entries format=duration:stream=codec_type,codec_name,width,height,channels \
    -of default=noprint_wrappers=1 "$OUT" 2>&1
  ls -la "$OUT"
else
  log "WARN: 抓取文件为空（/tmp/ff_v12yasa_vid.log / /tmp/ff_v12yasa_aud.log）"
fi
log "DONE"
