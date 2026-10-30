#!/bin/bash
# Vol.12 美術館(Akari) seg2（やさしい Q1..Q80）実況录制 —— limiter ON 两阶段法
# （同 rec_seg1_limiter.sh，驱动换成 play_akari_seg2.py）
#
# ★ 为什么必须两阶段：
#   单进程 x11grab@60 + 实时 libopenh264@60 会把抓帧主循环拖到 <60fps，
#   又被 -r 60 强制补重复帧 ⇒ 一卡一卡、速度失真（实测有效更新率仅 6.5Hz）。
#   两阶段：阶段1 裸抓 raw(bgr0)（零编码），音频另起进程抓 pcm_wav；
#            跑完再统一 libopenh264@30 + aac 合成。
#
# ★ 关键：DeSmuME 必须**不加 --disable-limiter**（限速器 ON），
#   游戏以真实 60fps 运行，X 窗口每帧都更新 ⇒ 无重复帧、无跳帧。
#
# 用法: bash rec_seg2_limiter.sh <out.mp4> <起始关> <结束关>
set -u
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol. 12：美术馆/ai-tas"
OUT="${1:-/workspace/美術館_やさしい実況_seg2.mp4}"
LO="${2:-1}"
HI="${3:-80}"
FR=30
RAW=/tmp/v12_seg2_rec.bgr0
WAV=/tmp/v12_seg2_rec.wav
SENTINEL=/tmp/v12_rec_start
STOP_SENTINEL=/tmp/v12_rec_stop
log(){ echo "[vol12-seg2 $(date +%H:%M:%S)] $*"; }

# 1. 环境守卫
pgrep -x Xvfb >/dev/null || { log "!! Xvfb 未运行"; exit 1; }
if ! pgrep -x desmume-cli >/dev/null; then
  log "!! desmume 未运行（请先起 limiter ON 的实例）"; exit 1
fi
# ★ limiter 状态硬校验（2026-10-29 seg3 快进事故沉淀）
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

# 3. 启动 driver（须在选关页；到达后触发开录哨兵）
cd "$AITAS"
python3.11 play_akari_seg2.py "$LO" "$HI" > /tmp/vol12_seg2_driver.log 2>&1 &
DRV=$!
log "driver pid=$DRV ; 等开录哨兵..."

# 4. 轮询开录哨兵
VPID=""; APID=""; T0=""
while [ ! -f "$SENTINEL" ]; do
  if ! kill -0 "$DRV" 2>/dev/null; then
    log "driver 已退出但未触发开录哨兵（看 /tmp/vol12_seg2_driver.log）"; break
  fi
  sleep 0.2
done
if [ -f "$SENTINEL" ]; then
  ffmpeg -y -loglevel error -f x11grab -draw_mouse 0 -framerate $FR \
    -video_size 256x384 -i :99+384,192 -pix_fmt bgr0 -f rawvideo "$RAW" \
    >/tmp/ff_v12s2_vid.log 2>&1 & VPID=$!
  ffmpeg -y -loglevel error -f pulse -i desmume_out.monitor \
    -c:a pcm_s16le "$WAV" >/tmp/ff_v12s2_aud.log 2>&1 & APID=$!
  log "抓取开始 vid=$VPID aud=$APID (raw bgr0 @${FR}fps, 无编码)"
  T0=$(date +%s.%N)
else
  log "WARN: 未检测到开录哨兵，跳过抓取"
fi

# 5. 等停录哨兵 / driver 结束
while [ ! -f "$STOP_SENTINEL" ]; do
  if ! kill -0 "$DRV" 2>/dev/null; then
    log "driver 已退出（按 driver 结束收尾）"; break
  fi
  sleep 0.3
done
sleep 1
[ -n "$VPID" ] && kill -INT "$VPID" 2>/dev/null
[ -n "$APID" ] && kill -INT "$APID" 2>/dev/null
sleep 2
if [ -n "${T0:-}" ]; then
  T1=$(date +%s.%N)
  log "抓取墙钟 ≈ $(echo "$T1 - $T0" | bc)s"
fi
log "driver 末行: $(tail -3 /tmp/vol12_seg2_driver.log | tr '\n' ' ')"

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
  log "WARN: 抓取文件为空（/tmp/ff_v12s2_vid.log / /tmp/ff_v12s2_aud.log）"
fi
log "DONE"
