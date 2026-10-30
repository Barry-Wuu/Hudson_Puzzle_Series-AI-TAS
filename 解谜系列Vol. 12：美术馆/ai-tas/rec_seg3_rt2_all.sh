#!/bin/bash
# seg3 重录编排器 v2（光标走位版驱动）：B→C→D→E1→E2，成功即删 raw。
# 用法: nohup bash rec_seg3_rt2_all.sh > /tmp/rt2_all.log 2>&1 &
set -u
cd "$(dirname "$0")"

CHUNKS=(
  "31 50 B_q31_50"
  "51 70 C_q51_70"
  "71 90 D_q71_90"
  "91 100 E1_q91_100"
  "101 110 E2_q101_110"
)

for c in "${CHUNKS[@]}"; do
  set -- $c
  LO=$1; HI=$2; TAG=$3
  OUT="/workspace/seg3rt2_$TAG.mp4"
  if [ -f "$OUT" ]; then
    echo "[orch] $TAG 已存在，跳过"
    continue
  fi
  echo "[orch] === chunk $TAG (Q$LO-Q$HI) start $(date +%H:%M:%S) ==="
  bash rec_seg3_limiter.sh "$OUT" "$LO" "$HI"
  rc=$?
  echo "[orch] chunk $TAG rc=$rc $(date +%H:%M:%S)"
  if [ $rc -ne 0 ]; then
    echo "[orch] !! FAIL $TAG —— 停止编排"
    exit "$rc"
  fi
  # 成功即删裸流控磁盘
  rm -f "/tmp/v12_seg3_rec_${LO}_${HI}.bgr0" "/tmp/v12_seg3_rec_${LO}_${HI}.wav"
  echo "[orch] $TAG raw 已清理"
done
echo "[orch] ALL_DONE $(date +%H:%M:%S)"
