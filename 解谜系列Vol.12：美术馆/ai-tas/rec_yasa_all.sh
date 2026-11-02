#!/bin/bash
# Vol.12 美術館 やさしい Q1..Q100 —— 逐关独立录制编排器
#
# 结构照抄已验证的 rec_q_all.sh（むずかしい Q1..Q70），差异：
#   * driver  play_yasashii.py（DIFF=やさしい，100 关）
#   * 抓取    rec_yasashii_limiter.sh
#   * 输出    美術館_やさしい_Q##.mp4
#
# ★关卡**顺序解锁**（未通关显示 "?"），所以必须按序推进：
#   第 n 关录完＝通关第 n 关＝解锁第 n+1 关。即「录制过程本身就是解锁过程」，
#   不需要额外的静默通关阶段。
# ★断点续录：已存在且合格的 mp4 直接跳过；某关两次失败即停，等人工介入。
#
# 用法: bash rec_yasa_all.sh [起始关] [结束关]
set -u
cd "/workspace/hudson_tas/解谜系列Vol.12：美术馆/ai-tas"
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native

LO="${1:-1}"
HI="${2:-100}"
PROG=/tmp/recyasa_progress.txt
FAILFLAG=/tmp/recyasa_FAILED
PER_JOB_TIMEOUT=${PER_JOB_TIMEOUT:-600}

log(){ echo "[recyasa $(date +%H:%M:%S)] $*" | tee -a "$PROG"; }

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
log "===== やさしい逐关录制启动 范围 Q${LO}-Q${HI} ====="

for q in $(seq "$LO" "$HI"); do
  qq=$(printf "%02d" "$q")
  OUT="/workspace/美術館_やさしい_Q${qq}.mp4"

  if check_mp4 "$OUT"; then
    log "Q${qq} 已存在且合格，跳过"
    continue
  fi

  ATTEMPT=1
  OK=0
  while [ "$ATTEMPT" -le 2 ]; do
    log "Q${qq} 录制开始 (第 ${ATTEMPT} 次)"
    T0=$(date +%s)
    timeout --signal=TERM --kill-after=15 "$PER_JOB_TIMEOUT" \
      bash rec_yasashii_limiter.sh "$OUT" "$q" "$q" >>/tmp/recyasa_raw.log 2>&1
    RC=$?
    T1=$(date +%s)
    EL=$((T1 - T0))

    if check_mp4 "$OUT"; then
      log "Q${qq} ✓ 完成 用时 ${EL}s 大小 $(stat -c%s "$OUT")"
      OK=1
      break
    fi

    log "Q${qq} ✗ 第 ${ATTEMPT} 次失败 rc=${RC} 用时 ${EL}s（详见 /tmp/recyasa_raw.log）"
    pkill -f "play_yasashii.py" 2>/dev/null
    pkill -f "v12_yasa_rec" 2>/dev/null
    sleep 2

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
ls -1 /workspace/美術館_やさしい_Q*.mp4 2>/dev/null | wc -l | xargs -I{} echo "现有やさしい单关视频数: {}" | tee -a "$PROG"
