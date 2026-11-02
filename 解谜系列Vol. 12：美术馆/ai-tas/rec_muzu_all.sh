#!/bin/bash
# Vol.12 美術館(Akari) muzusaki（むずかしい Q1..Q70）分段実況录制编排器
#
# 分段（按尺寸切，便于断点续录 + 控裸流磁盘）：
#   24×14 段：Q1-20 / Q21-40 / Q41-50
#   36×20 段：Q51-60 / Q61-70
# 首段 A 带 --tutorial：录制前先打入門 L1 抑制教程弹窗（仅首段，全程只打一次）。
#
# 录制规格：固定 30fps + 有声(pulse) + 原分辨率 256x384（见 rec_muzu_limiter.sh）。
# 中断后续录：已生成的 <tag>.mp4 会被跳过（按存在即跳过）。
#
# 用法: nohup bash rec_muzu_all.sh > /tmp/muzu_all.log 2>&1 &
set -u
cd "/workspace/hudson_tas/解谜系列Vol. 12：美术馆/ai-tas"
log(){ echo "[muzu-orch $(date +%H:%M:%S)] $*"; }

CHUNKS=(
  # ★2026-11-01：首段**去掉** --tutorial。tutorial_prep 实测不可用——入門 20 关全是 6×6，
  #   选关网格导航(goto_level)是按 110 关网格标定的，在入門网格里「点格得 -1 ≠ 1」连
  #   续 7 轮失败后卡死。且实测 muzusaki 进关并**不会弹教程**（test_play1 已验证），
  #   故不前置教程，直接录。
  "A_muzu_q1_20    1   20   "
  "B_muzu_q21_40  21   40   "
  "C_muzu_q41_50  41   50   "
  "D_muzu_q51_60  51   60   "
  "E_muzu_q61_70  61   70   "
)

for c in "${CHUNKS[@]}"; do
  set -- $c; name=$1; lo=$2; hi=$3; tut=${4:-}
  out="/workspace/美術館_むずかしい_${name}.mp4"
  if [ -f "$out" ]; then
    echo "[orch] $name 已存在，跳过"
    continue
  fi
  echo "[orch] === chunk $name (Q${lo}-Q${hi}) start $(date +%H:%M:%S) tut=${tut:-N} ==="
  bash rec_muzu_limiter.sh "$out" "$lo" "$hi" "$tut"
  rc=$?
  okn=$(grep -c "ok=True" /tmp/vol12_muzu_driver.log 2>/dev/null || echo 0)
  failn=$(grep -c "ok=False" /tmp/vol12_muzu_driver.log 2>/dev/null || echo 0)
  want=$((hi - lo + 1))
  echo "[orch] chunk $name rc=$rc ok=$okn/$want fail=$failn"
  if [ "$rc" -eq 0 ] && [ -s "$out" ] && [ "$okn" -eq "$want" ]; then
    echo "[orch] chunk $name 验收通过，删除裸流"
    rm -f "/tmp/v12_muzu_rec_${lo}_${hi}.bgr0" "/tmp/v12_muzu_rec_${lo}_${hi}.wav"
  else
    echo "[orch] !! chunk $name 未达预期（保留裸流排查）: out=$out rc=$rc ok=$okn"
    # 失败即停，避免后续段基于错误起点续录
    exit "$rc"
  fi
done
echo "[orch] ALL_DONE $(date +%H:%M:%S)"
ls -la /workspace/美術館_むずかしい_*.mp4 2>/dev/null
