#!/bin/bash
# seg2 分段录制（两阶段法，原分辨率 256x384 不放大）：速通「やさしい」第2..100关。
# 每段独立启动 desmume（沿用上一段落盘的 .dsv，进度续接），录完干净退出（SRAM 落盘），
# 备份 .dsv，再进下一段 —— 满足「随时保存存档 / 分段录制」。
#
# 为什么两阶段：单进程 x11grab@高帧+实时编码会把抓帧主循环拖垮 → 一卡一卡。先裸抓
# raw(bgr0) 写 /tmp（零编码），音频另起进程抓 pcm_wav，跑完再统一编码+aac（原分辨率 256x384）。
# 为什么每段干净退出：desmume 在退出时把 SRAM 写回 .dsv（已验证），故每段末的 .dsv 即
# 该段真实进度；下一段启动即续上，崩溃也只丢当前段。
set -u
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native
BASE=/root/.codebuddy/artifact/vol11
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
OUTBASE="${1:-/workspace/数墙_seg2}"
FR=30
RAW=/tmp/v11_seg2.bgr0
WAV=/tmp/v11_seg2.wav
SEGMENTS="${SEGS:-2:21:warmup 22:41 42:61 62:81 82:100}"
log(){ echo "[seg2 $(date +%H:%M:%S)] $*"; }

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

N=0
for SEG in $SEGMENTS; do
  N=$((N+1))
  LO=${SEG%%:*}; REST=${SEG#*:}; HI=${REST%%:*}; WARM=${REST#*:}
  [ "$WARM" = "$REST" ] && WARM=""    # 无 warmup 时 REST==WARM，置空
  OUT="$OUTBASE"_p$N.mp4
  log "=== segment $N: lvl $LO..$HI warmup=${WARM:-none} ==="

  # 3. 启动 desmume（沿用当前 .dsv，进度续接；不删档）
  pkill -x desmume-cli 2>/dev/null
  for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
  cd "$BASE"
  SDL_VIDEODRIVER=x11 SDL_VIDEO_WINDOW_POS=384,192 SDL_AUDIODRIVER=alsa DISPLAY=:99 \
    setsid desmume-cli --num-cores=1 game.nds >/tmp/desmume_seg2.log 2>&1 &
  for i in $(seq 1 20); do
    W=$(xdotool search --name -i desmume 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.5
  done
  [ -n "${W:-}" ] && xdotool windowmove "$W" 384 192 2>/dev/null
  log "desmume up (limiter ON); pid=$(pgrep -x desmume-cli|head -1)"

  # 4. 启动 driver
  rm -f /tmp/v11_rec_start /tmp/v11_rec_stop "$RAW" "$WAV"
  cd "$AITAS"
  if [ -n "$WARM" ]; then
    V11_DIFF=やさしい python3 seg2_run.py $LO $HI warmup > /tmp/seg2_driver_p$N.log 2>&1 &
  else
    V11_DIFF=やさしい python3 seg2_run.py $LO $HI > /tmp/seg2_driver_p$N.log 2>&1 &
  fi
  DRV=$!
  log "driver pid=$DRV seg $N; 等开录哨兵..."

  # 5. 轮询开录哨兵
  VPID=""; APID=""
  while [ ! -f /tmp/v11_rec_start ]; do
    if ! kill -0 "$DRV" 2>/dev/null; then log "driver 退出未触发开录哨兵 (seg $N)"; break; fi
    sleep 0.3
  done
  if [ -f /tmp/v11_rec_start ]; then
    ffmpeg -y -loglevel error -f x11grab -draw_mouse 0 -framerate $FR \
      -video_size 256x384 -i :99+384,192 -pix_fmt bgr0 -f rawvideo "$RAW" \
      >/tmp/ff_vid.log 2>&1 & VPID=$!
    ffmpeg -y -loglevel error -f pulse -i desmume_out.monitor \
      -c:a pcm_s16le "$WAV" >/tmp/ff_aud.log 2>&1 & APID=$!
    log "抓取开始 seg $N vid=$VPID aud=$APID (256x384 原分辨率, 无编码)"
    T0=$(date +%s.%N)
  else
    log "WARN seg $N 未开录"
  fi

  # 6. 等停录哨兵
  while [ ! -f /tmp/v11_rec_stop ]; do
    if ! kill -0 "$DRV" 2>/dev/null; then log "driver 退出(无停录哨兵, seg $N)"; break; fi
    sleep 0.3
  done
  [ -n "$VPID" ] && kill -INT "$VPID" 2>/dev/null
  [ -n "$APID" ] && kill -INT "$APID" 2>/dev/null
  sleep 2
  if [ -n "${T0:-}" ]; then T1=$(date +%s.%N); log "seg $N 抓取墙钟 ≈ $(echo "$T1 - $T0" | bc)s"; fi

  # 7. 编码（原分辨率 256x384，不放大）
  if [ -s "$RAW" ] && [ -s "$WAV" ]; then
    ffmpeg -y -hide_banner -loglevel warning \
      -f rawvideo -pix_fmt bgr0 -video_size 256x384 -framerate $FR -i "$RAW" \
      -i "$WAV" \
      -c:v libopenh264 -pix_fmt yuv420p -r $FR -b:v 3000k \
      -c:a aac -b:a 160k -ar 44100 -ac 2 \
      -movflags +faststart -shortest "$OUT"
    log "seg $N ffprobe:"; ffprobe -v error -show_entries format=duration:stream=codec_type,codec_name,width,height \
      -of default=noprint_wrappers=1 "$OUT" 2>&1
    ls -la "$OUT"
  else
    log "WARN seg $N 抓取为空，跳过编码"
  fi

  # 8. 干净退出 desmume（SRAM 落盘），备份 .dsv
  pkill -x desmume-cli 2>/dev/null
  for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
  cp -f /root/.config/desmume/game.dsv /root/.config/desmume/game.dsv.bak_seg2_p$N 2>/dev/null
  log "seg $N done; .dsv backed up -> game.dsv.bak_seg2_p$N"
done
log "ALL SEGMENTS DONE"
