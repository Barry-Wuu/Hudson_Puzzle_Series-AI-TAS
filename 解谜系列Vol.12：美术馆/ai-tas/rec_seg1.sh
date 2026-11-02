#!/bin/bash
# Vol.12 美術館(AKARI) seg1（入門 2-20）実況录制 —— 跳过第1关(教程)
# 前置（由调用方保证）：
#   1. vol12_env.sh on 已启动 Xvfb+pulse+desmume（带声、turbo、窗口(384,192)）
#   2. 音频链路已验证：desmume→alsa-pulse插件→desmume_out→.monitor
# 要点（2026-10-28 重录修复）：
#   - 跳过 Q1（教程关）：录制范围 2-20（用户明确要求）
#   - 驱动自带 boot_to_select()：从标题页自动导航到入門选关页，无需手工预导航
#   - 剂量对标 Vol.11 数墙：tap_batch hold=0.06/after=0.04≈0.12s/灯（旧 after=0.75≈0.81s/灯，慢7倍）
#   - 通关后先等结算动画稳定(1.2s)再按 x，失败重试 x（不通 escape，避免误触）
set -u
export DISPLAY=:99
export PULSE_SERVER=unix:/tmp/pulse_native
AITAS="/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.12：美术馆/ai-tas"
OUT="${1:-/workspace/美术馆_入門实況_seg1.mp4}"
LO="${2:-2}"          # 起始关（默认跳过 Q1）
HI="${3:-20}"         # 结束关
log(){ echo "[vol12seg1 $(date +%H:%M:%S)] $*"; }

# 0. 环境守卫
if ! pgrep -x desmume-cli >/dev/null; then
  log "!! desmume 未运行，请先 bash vol12_env.sh on"; exit 1
fi
pgrep -x Xvfb >/dev/null || { log "!! Xvfb 未运行"; exit 1; }

# 1. ffmpeg：固定60fps + 无光标 + desmume_out.monitor 收音
rm -f "$OUT"
ffmpeg -y -hide_banner -loglevel warning \
  -f x11grab -draw_mouse 0 -framerate 60 -video_size 256x384 -i :99+384,192 \
  -f pulse -i desmume_out.monitor \
  -c:v libopenh264 -b:v 3000k -pix_fmt yuv420p -r 60 -g 120 \
  -c:a aac -b:a 160k -ar 44100 -ac 2 \
  -movflags +faststart "$OUT" >/tmp/ffmpeg_vol12_seg1.log 2>&1 &
FFPID=$!
log "ffmpeg pid=$FFPID；3s 后驱动开跑（录制 Q${LO}-Q${HI}，跳过教程Q1）"
sleep 3

# 2. 驱动：入門 Q2-Q20 点灯清关（main 内自动 boot_to_select 到选关页）
cd "$AITAS"
python3.11 play_akari.py "$LO" "$HI" > /tmp/vol12_seg1_driver.log 2>&1
RC=$?
log "driver rc=$RC；末行: $(tail -1 /tmp/vol12_seg1_driver.log)"

# 3. 立即停 ffmpeg（消除结尾 idle；留1s收尾）
sleep 1
kill -INT "$FFPID" 2>/dev/null
for i in $(seq 1 20); do kill -0 "$FFPID" 2>/dev/null || break; sleep 0.5; done
kill -0 "$FFPID" 2>/dev/null && kill -9 "$FFPID" 2>/dev/null

# 4. 报告
log "=== ffprobe ==="
ffprobe -v error -show_entries format=duration:stream=codec_type,codec_name,width,height,channels \
  -of default=noprint_wrappers=1 "$OUT" 2>&1
ls -la "$OUT"
log "DONE"
