#!/bin/bash
# seg4 分段录制（两阶段法，原分辨率 256x384 不放大）：速通「むずかしい」第1..80关。
# 每段独立启动 desmume（沿用上一段落盘的 .dsv，进度续接），录完干净退出（SRAM 落盘），
# 备份 .dsv，再进下一段 —— 满足「随时保存存档 / 分段录制」。
#
# 难度：V11_DIFF=むずかしい（80 关：lvl1..40=24×14，lvl41..80=36×20；教程全局已 done）。
# BGM：むずかしい 用 BGM3（每段开录前 bgm3_setup.py 强制重切+校验，防 BGM2 误录）。
# 两阶段法 / 每段干净退出 同 rec_seg3.sh（见其注释）。
set -u
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native
BASE=/root/.codebuddy/artifact/vol11
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
OUTBASE="${1:-/workspace/数墙_seg4}"
FR=30
RAW=/tmp/v11_seg4.bgr0
WAV=/tmp/v11_seg4.wav
SEGMENTS="${SEGS:-1:20 21:40 41:60 61:80}"
log(){ echo "[seg4 $(date +%H:%M:%S)] $*"; }

# 0. 以当前 live 存档为 seg4 起点（seg3 末态：ふつう 100 done，むずかしい 可达且第1关无教程）
if [ -f /root/.config/desmume/game.dsv ]; then
  cp -f /root/.config/desmume/game.dsv /root/.config/desmume/game.dsv.bak_seg4_base
  log "snapshotted current live save as seg4 base"
else
  log "WARN: 无 live 存档，将用全新存档"
fi

# 1. Xvfb
if ! pgrep -x Xvfb >/dev/null; then
  Xvfb :99 -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 &
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
  LO=${SEG%%:*}; REST=${SEG#*:}; HI=${REST%%:*}
  OUT="$OUTBASE"_p$N.mp4
  # 断点续录：本段 mp4 已存在且时长有效则跳过（supervisord 重启后免重录已完成段）
  if [ -s "$OUT" ] && ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT" 2>/dev/null | grep -qE '^[0-9]+\.[0-9]'; then
    log "seg $N 已存在且有效，跳过（断点续录）: $OUT"
    continue
  fi
  log "=== segment $N: lvl $LO..$HI ==="

  # 3. 启动 desmume（沿用当前 .dsv，进度续接；不删档）
  pkill -x desmume-cli 2>/dev/null
  for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
  cd "$BASE"
  SDL_VIDEODRIVER=x11 SDL_VIDEO_WINDOW_POS=384,192 SDL_AUDIODRIVER=pulse \
    DBUS_SESSION_BUS_ADDRESS= PULSE_SERVER=unix:/tmp/pulse_native DISPLAY=:99 \
    desmume-cli --num-cores=1 game.nds >/tmp/desmume_seg4.log 2>&1 &
  for i in $(seq 1 20); do
    W=$(xdotool search --name -i desmume 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.5
  done
  [ -n "${W:-}" ] && xdotool windowmove "$W" 384 192 2>/dev/null
  log "desmume up (limiter ON); pid=$(pgrep -x desmume-cli|head -1)"

  # 3.5 BGM3 设置（每段开录前必做——防 BGM2/1 误录）
  rm -f /tmp/v11_bgm_ready
  cd "$AITAS"
  V11_DIFF=むずかしい python3 bgm3_setup.py > /tmp/seg4_bgm_setup_p$N.log 2>&1
  if [ ! -f /tmp/v11_bgm_ready ]; then
    log "FATAL seg $N: BGM3 setup 失败（见 /tmp/seg4_bgm_setup_p$N.log），中止——防误录"
    pkill -x desmume-cli 2>/dev/null
    exit 1
  fi
  log "seg $N BGM3 ready"

  # 4. 启动 driver
  rm -f /tmp/v11_rec_start /tmp/v11_rec_stop "$RAW" "$WAV"
  cd "$AITAS"
  V11_DIFF=むずかしい python3 seg4_run.py $LO $HI > /tmp/seg4_driver_p$N.log 2>&1 &
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
  cp -f /root/.config/desmume/game.dsv /root/.config/desmume/game.dsv.bak_seg4_p$N 2>/dev/null
  log "seg $N done; .dsv backed up -> game.dsv.bak_seg4_p$N"
done
log "ALL SEGMENTS DONE"
