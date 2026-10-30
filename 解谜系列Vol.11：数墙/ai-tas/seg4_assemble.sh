#!/bin/bash
# seg4 装配：逐关片段去 save 屏 + select 压 0.5s，再拼接成 数墙_seg4_final.mp4。
# 复用 trim_select_save.py（选关末 0.5s + 「セーブしています…」整段删除）。
set -u
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
OUTDIR="${1:-/workspace}"
HI=${2:-80}
TRIMDIR="$OUTDIR/_seg4_trim"
FINAL="$OUTDIR/数墙_seg4_final.mp4"
log(){ echo "[seg4asm $(date +%H:%M:%S)] $*"; }
mkdir -p "$TRIMDIR"
cd "$AITAS"

# 1. 逐关裁剪
for L in $(seq 1 "$HI"); do
  SRC="$OUTDIR/数墙_seg4_lv$L.mp4"
  DST="$TRIMDIR/lv$(printf '%03d' "$L").mp4"
  if [ ! -s "$SRC" ]; then log "MISSING src lv$L"; continue; fi
  if [ -s "$DST" ] && ffprobe -v error -show_entries format=duration -of csv=p=0 "$DST" 2>/dev/null | grep -qE '^[0-9]+\.[0-9]'; then
    continue
  fi
  python3 trim_select_save.py "$SRC" "$DST" >> /tmp/seg4asm_trim.log 2>&1 \
    && log "trim ok lv$L" || log "trim FAIL lv$L"
done

# 2. 拼接（concat demuxer，同码流 copy）
: > "$TRIMDIR/list.txt"
n=0
for L in $(seq 1 "$HI"); do
  DST="$TRIMDIR/lv$(printf '%03d' "$L").mp4"
  if [ -s "$DST" ]; then echo "file '$DST'" >> "$TRIMDIR/list.txt"; n=$((n+1)); fi
done
log "trimmed clips to concat: $n / $HI"
if [ "$n" -lt "$HI" ]; then log "WARN 仍有缺失片段，exit 1 触发重试"; exit 1; fi

ffmpeg -y -hide_banner -loglevel warning -f concat -safe 0 -i "$TRIMDIR/list.txt" -c copy "$FINAL" \
  && log "FINAL written: $FINAL" || { log "concat FAIL"; exit 1; }
ls -la "$FINAL"
log "final duration(s)=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$FINAL" 2>/dev/null)"
