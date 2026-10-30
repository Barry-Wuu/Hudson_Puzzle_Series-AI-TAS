#!/bin/bash
# seg4 自愈 pipeline：分关录制(断点续录) -> 装配(去 save 屏+拼接) -> 写 DONE
# 由 supervisord [program:seg4pipe] 托管；被回收/SIGTERM/异常退出时自动重启，
# 录制脚本断点续录保证从已完成关之后继续，不重复劳动。
set -u
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
CLIPDIR="/workspace"
FINAL="/workspace/数墙_seg4_final.mp4"
DONE="/tmp/seg4_DONE"
LOG="/tmp/seg4pipe.log"
echo "$(date) seg4pipe start (pid=$$)" >> "$LOG"

# 已完成则直接退出（supervisord 对 exit 0 不重启）
if [ -f "$DONE" ]; then
  echo "$(date) DONE exists, skip" >> "$LOG"
  exit 0
fi

# 1) 分关录制（rec_seg4_perlevel.sh 内部断点续录：已完成关 mp4 有效则跳过）
bash "$AITAS/rec_seg4_perlevel.sh" "$CLIPDIR" 1 80 >> "$LOG" 2>&1
REC_RC=$?
echo "$(date) rec_seg4_perlevel rc=$REC_RC" >> "$LOG"
if [ "$REC_RC" != "0" ]; then
  echo "$(date) 录制失败(rc=$REC_RC)，exit 触发 supervisord 重启续录" >> "$LOG"
  exit "$REC_RC"
fi

# 校验 80 关片段齐全（缺失则 exit 1 触发重启补录）
missing=0
for L in $(seq 1 80); do
  f="$CLIPDIR/数墙_seg4_lv$L.mp4"
  [ -s "$f" ] || missing=$((missing+1))
done
if [ "$missing" -ne 0 ]; then
  echo "$(date) 缺失 $missing 关片段，exit 1 触发重启补录" >> "$LOG"
  exit 1
fi

# 2) 装配：逐关去 save 屏 + select 压 0.5s，拼接成成品
bash "$AITAS/seg4_assemble.sh" "$CLIPDIR" 80 >> "$LOG" 2>&1
ASM_RC=$?
echo "$(date) seg4_assemble rc=$ASM_RC" >> "$LOG"
if [ "$ASM_RC" != "0" ]; then
  echo "$(date) 装配失败(rc=$ASM_RC)，exit 触发重启重试" >> "$LOG"
  exit "$ASM_RC"
fi

if [ -s "$FINAL" ]; then
  echo "$(date) PIPELINE OK -> $FINAL" >> "$LOG"
  : > "$DONE"
  exit 0
else
  echo "$(date) 成品缺失，exit 1" >> "$LOG"
  exit 1
fi
