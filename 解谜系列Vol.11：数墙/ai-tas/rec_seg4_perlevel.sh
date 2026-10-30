#!/bin/bash
# seg4 分关录制（断点续录）：逐关录一段 + 每关退出 desmume 落盘存档一次。
# 难度：むずかしい（80 关，lvl1..40=24×14，lvl41..80=36×20）。BGM=BGM3。
# 每关产物：/workspace/数墙_seg4_lv<L>.mp4；每关存档：game.dsv.bak_lv<L>。
# 断点续录：某关 mp4 已存在且时长有效则跳过（被 supervisord 回收重启后免重录）。
#
# 用法: bash rec_seg4_perlevel.sh [OUTDIR] [LO] [HI]
set -u
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native
BASE=/root/.codebuddy/artifact/vol11
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
OUTDIR="${1:-/workspace}"
LO=${2:-1}
HI=${3:-80}
FR=30
RAW=/tmp/v11_seg4.bgr0
WAV=/tmp/v11_seg4.wav
DIFF=むずかしい
DOTDSV=/root/.config/desmume/game.dsv
log(){ echo "[seg4pl $(date +%H:%M:%S)] $*"; }

# 0. Xvfb
if ! pgrep -x Xvfb >/dev/null; then
  Xvfb :99 -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 &
  sleep 2
fi
# 1. PulseAudio + desmume_out 空 sink
if ! pactl info >/dev/null 2>&1; then
  mkdir -p /run/user/102 /tmp/pulsehome && chown pulse:pulse /run/user/102 /tmp/pulsehome && chmod 700 /run/user/102
  rm -f /tmp/pulse_native
  runuser -u pulse -- env XDG_RUNTIME_DIR=/run/user/102 HOME=/tmp/pulsehome \
    pulseaudio -n -F /tmp/pulse_cfg.pa --exit-idle-time=-1 --disable-shm=1 --disallow-exit \
    --log-target=file:/tmp/pulse.log & sleep 2
fi
log "Xvfb=$(pgrep -x Xvfb|head -1) sink=$(pactl list short sinks 2>/dev/null|grep -o desmume_out|head -1)"

# 2. 起点存档快照（仅首次）
if [ -f "$DOTDSV" ] && [ ! -f "${DOTDSV}.bak_seg4_base" ]; then
  cp -f "$DOTDSV" "${DOTDSV}.bak_seg4_base"
  log "snapshotted seg4 base save"
fi

launch_desmume(){
  pkill -x desmume-cli 2>/dev/null
  for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
  cd "$BASE"
  SDL_VIDEODRIVER=x11 SDL_VIDEO_WINDOW_POS=384,192 SDL_AUDIODRIVER=pulse \
    DBUS_SESSION_BUS_ADDRESS= PULSE_SERVER=unix:/tmp/pulse_native DISPLAY=:99 \
    desmume-cli --num-cores=1 game.nds >/tmp/desmume_seg4.log 2>&1 &
  for i in $(seq 1 30); do
    W=$(xdotool search --name -i desmume 2>/dev/null | head -1); [ -n "$W" ] && break; sleep 0.5
  done
  [ -n "${W:-}" ] && xdotool windowmove "$W" 384 192 2>/dev/null
  log "desmume up pid=$(pgrep -x desmume-cli|head -1)"
}

ensure_bgm3(){
  rm -f /tmp/v11_bgm_ready
  cd "$AITAS"
  V11_DIFF=$DIFF python3 bgm3_setup.py > /tmp/seg4_bgm_setup.log 2>&1
  if [ ! -f /tmp/v11_bgm_ready ]; then
    log "FATAL BGM3 fail (see /tmp/seg4_bgm_setup.log)"; return 1
  fi
  log "BGM3 ready"; return 0
}

# 3. 一次性 BGM3（全局设置，存于 SRAM；pkill 落盘后逐关从存档继承，无需每关重设）
#    依据：pkill 会刷 SRAM（进度才能逐关续上），BGM 偏好属同一块 SRAM，进关不重置。
log "一次性设置 BGM3 并落盘（后续关卡从存档继承，避免每关重设 ~2-3min 开销与失败面）"
launch_desmume
if ! ensure_bgm3; then
  log "一次性 BGM3 设置失败，exit 1"
  exit 1
fi
pkill -x desmume-cli 2>/dev/null
for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
cp -f "$DOTDSV" "${DOTDSV}.bak_seg4_base" 2>/dev/null
log "BGM3 已落盘；存档快照 bak_seg4_base 已更新"

# 4. 逐关循环（BGM3 已从存档继承，循环内不再重设）
for L in $(seq "$LO" "$HI"); do
  OUT="$OUTDIR/数墙_seg4_lv$L.mp4"
  if [ -s "$OUT" ] && ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUT" 2>/dev/null | grep -qE '^[0-9]+\.[0-9]'; then
    log "lv$L 已存在且有效，跳过（断点续录）"
    continue
  fi

  # 4.1 启动 desmume（恢复上一关 .dsv，进度续接；BGM3 已存于存档）
  launch_desmume

  # 3.3 录本关
  rm -f /tmp/v11_rec_start /tmp/v11_rec_stop "$RAW" "$WAV"
  cd "$AITAS"
  V11_DIFF=$DIFF python3 seg4_run.py $L $L > /tmp/seg4_driver_lv$L.log 2>&1 &
  DRV=$!
  VPID=""; APID=""; T0=""
  while [ ! -f /tmp/v11_rec_start ]; do
    if ! kill -0 "$DRV" 2>/dev/null; then log "driver 退出未开录 lv$L"; break; fi
    sleep 0.3
  done
  if [ -f /tmp/v11_rec_start ]; then
    ffmpeg -y -loglevel error -f x11grab -draw_mouse 0 -framerate $FR \
      -video_size 256x384 -i :99+384,192 -pix_fmt bgr0 -f rawvideo "$RAW" \
      >/tmp/ff_vid.log 2>&1 & VPID=$!
    ffmpeg -y -loglevel error -f pulse -i desmume_out.monitor \
      -c:a pcm_s16le "$WAV" >/tmp/ff_aud.log 2>&1 & APID=$!
    log "抓取开始 lv$L"; T0=$(date +%s)
  fi
  while [ ! -f /tmp/v11_rec_stop ]; do
    if ! kill -0 "$DRV" 2>/dev/null; then log "driver 退出(无停录哨兵) lv$L"; break; fi
    sleep 0.3
  done
  [ -n "$VPID" ] && kill -INT "$VPID" 2>/dev/null
  [ -n "$APID" ] && kill -INT "$APID" 2>/dev/null
  sleep 2
  if [ -n "$T0" ]; then log "lv$L 抓取墙钟 ≈ $(($(date +%s)-T0))s"; fi

  if [ -s "$RAW" ] && [ -s "$WAV" ]; then
    ffmpeg -y -hide_banner -loglevel warning \
      -f rawvideo -pix_fmt bgr0 -video_size 256x384 -framerate $FR -i "$RAW" \
      -i "$WAV" \
      -c:v libopenh264 -pix_fmt yuv420p -r $FR -b:v 3000k \
      -c:a aac -b:a 160k -ar 44100 -ac 2 \
      -movflags +faststart -shortest "$OUT"
    log "lv$L 编码完成"; ls -la "$OUT"
  else
    log "WARN lv$L 抓取为空，未出片（下次重试）"
  fi

  # 3.4 每关存档：退出 desmume 触发 SRAM 落盘，备份 .dsv
  pkill -x desmume-cli 2>/dev/null
  for _ in $(seq 1 20); do pgrep -x desmume-cli >/dev/null || break; sleep 0.5; done
  cp -f "$DOTDSV" "${DOTDSV}.bak_lv$L" 2>/dev/null
  log "lv$L 存档已保存 -> game.dsv.bak_lv$L"
done
log "ALL LEVELS DONE (LO=$LO HI=$HI)"
