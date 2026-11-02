#!/bin/bash
# Vol.12 美術館 むずかしい Q1..Q70 —— 逐关独立录制编排器
#
# 与 rec_muzu_all.sh 的区别：本脚本**每关产出一个独立 mp4**（用户要求"各录为一个视频"），
# 而不是按 20 关合并成段。代价是每关都要重启 driver + 重走选关页导航，但换来：
#   - 失败隔离：一关出问题只废一关，不影响其他文件；
#   - 断点续录：已存在的合格 mp4 直接跳过，随时可重跑本脚本续上。
#
# ★ 关卡是**顺序解锁**的（未通关的关卡在选关页显示 "?"，进不去），
#   所以某一关失败后必须停下等人工介入，不能跳到下一关。
#
# 用法: bash rec_q_all.sh [起始关] [结束关]
set -u
cd "/workspace/hudson_tas/解谜系列Vol. 12：美术馆/ai-tas"
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native

LO="${1:-1}"
HI="${2:-70}"
PROG=/tmp/rec70_progress.txt
FAILFLAG=/tmp/rec70_FAILED
PER_JOB_TIMEOUT=${PER_JOB_TIMEOUT:-420}

log(){ echo "[rec70 $(date +%H:%M:%S)] $*" | tee -a "$PROG"; }

# 单关成片合格判据：存在、有视频流(256x384)、有音轨、时长 > 20s
check_mp4(){
  local f="$1"
  [ -s "$f" ] || return 1
  ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$f" 2>/dev/null | grep -q "^256,384$" || return 1
  ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of csv=p=0 "$f" 2>/dev/null | grep -q "aac" || return 1
  local d
  d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f" 2>/dev/null | cut -d. -f1)
  [ -n "$d" ] && [ "$d" -gt 20 ] || return 1
  return 0
}

rm -f "$FAILFLAG"
log "===== 逐关录制启动 范围 Q${LO}-Q${HI} ====="

for q in $(seq "$LO" "$HI"); do
  qq=$(printf "%02d" "$q")
  OUT="/workspace/美術館_むずかしい_Q${qq}.mp4"

  if check_mp4 "$OUT"; then
    log "Q${qq} 已存在且合格，跳过"
    continue
  fi

  ATTEMPT=1
  OK=0
  while [ "$ATTEMPT" -le 2 ]; do
    log "Q${qq} 录制开始 (第 ${ATTEMPT} 次)"
    T0=$(date +%s)
    # 超时保护：卡死时连 driver / 抓取一起清掉
    timeout --signal=TERM --kill-after=15 "$PER_JOB_TIMEOUT" \
      bash rec_muzu_limiter.sh "$OUT" "$q" "$q" >>/tmp/rec70_raw.log 2>&1
    RC=$?
    T1=$(date +%s)
    EL=$((T1 - T0))

    if check_mp4 "$OUT"; then
      log "Q${qq} ✓ 完成 用时 ${EL}s 大小 $(stat -c%s "$OUT")"
      OK=1
      break
    fi

    log "Q${qq} ✗ 第 ${ATTEMPT} 次失败 rc=${RC} 用时 ${EL}s（详见 /tmp/rec70_raw.log）"
    # 清理残留，避免下一次录制被旧进程干扰
    pkill -f "play_akari_muzu.py" 2>/dev/null
    pkill -f "v12_muzu_rec" 2>/dev/null
    sleep 2

    # 环境自检：pulse / desmume 死掉是常见故障
    if ! pgrep -x pulseaudio >/dev/null || ! pgrep -x desmume-cli >/dev/null; then
      log "Q${qq} !! 检测到 pulse 或 desmume 已退出 → 需人工重启环境后再续"
      echo "Q${q}: env_dead" > "$FAILFLAG"
      rm -f "$OUT"
      exit 2
    fi
    ATTEMPT=$((ATTEMPT + 1))
  done

  if [ "$OK" -ne 1 ]; then
    log "Q${qq} !! 两次均失败，停止编排等待人工介入"
    echo "Q${q}: record_failed" > "$FAILFLAG"
    rm -f "$OUT"
    exit 3
  fi
done

log "===== ALL_DONE Q${LO}-Q${HI} ====="
ls -la /workspace/美術館_むずかしい_Q*.mp4 2>/dev/null | wc -l | xargs -I{} echo "现有单关视频数: {}" | tee -a "$PROG"
