#!/bin/bash
# seg3 limiter-ON 重录编排器：6 分块串行，成功即删裸流（控磁盘），核对每块 ok 数
cd "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol. 12：美术馆/ai-tas"
log(){ echo "[rt-all $(date +%H:%M:%S)] $*"; }

CHUNKS=(
  "A_q1_30    1   30"
  "B_q31_50  31   50"
  "C_q51_70  51   70"
  "D_q71_90  71   90"
  "E1_q91_100 91 100"
  "E2_q101_110 101 110"
)

for c in "${CHUNKS[@]}"; do
  set -- $c; name=$1; lo=$2; hi=$3
  out="/workspace/seg3rt_${name}.mp4"
  raw="/tmp/v12_seg3_rec_${lo}_${hi}.bgr0"
  raww="/tmp/v12_seg3_rec_${lo}_${hi}.wav"
  want=$((hi - lo + 1))
  log "=== chunk $name Q${lo}-${hi}（应 ok ${want} 关） ==="
  bash rec_seg3_limiter.sh "$out" "$lo" "$hi"
  rc=$?
  okn=$(grep -c "ok=True" /tmp/vol12_seg3_driver.log 2>/dev/null || echo 0)
  failn=$(grep -c "ok=False" /tmp/vol12_seg3_driver.log 2>/dev/null || echo 0)
  log "chunk $name rc=$rc ok=$okn/$want fail=$failn"
  if [ "$rc" -eq 0 ] && [ -s "$out" ] && [ "$okn" -eq "$want" ]; then
    log "chunk $name 验收通过，删除裸流"
    rm -f "$raw" "$raww"
  else
    log "!! chunk $name 未达预期（保留裸流排查）: out=$out rc=$rc ok=$okn"
  fi
done
log "=== 全部 chunk 完成 ==="
ls -la /workspace/seg3rt_*.mp4 2>/dev/null
