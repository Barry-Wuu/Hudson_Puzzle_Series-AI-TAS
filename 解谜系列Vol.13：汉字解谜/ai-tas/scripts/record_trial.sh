#!/usr/bin/env bash
# 录一段「单关实况」（有声 / 无鼠标指针 / 与 trial 严格对齐 / 不录进规划空转 / 不卡）
#
# ★ 五个必须（2026-10-13 踩坑修正，详见 PITFALLS §S22）：
#   1) `-draw_mouse 0`：否则 Xvfb 的 X 形鼠标指针被画进画面（xdotool mousemove 会把
#      指针挪到点击处，留下一个 ✕ 标记，且会停在那十几秒）。
#   2) 录制前先离线算好 lr_plan（束搜索 ~15s）。这段发生在 fill() 计时器 t0 **之前**，
#      既不算 nav 也不算 fill，现算会录进一段「进关后画面一动不动」。
#   3) 用 `-t` 掐断而不是 kill -INT：本沙箱 ffmpeg 收到 SIGINT 后还会继续录 ~18s。
#   4) **两阶段录制**：边采边编码会把采集帧率从 30fps 压到 ~3.5fps（libopenh264 编
#      512x768 太慢，X 的画面更新被整批漏掉 ⇒ 视频一卡一卡）。先无编码抓原始帧，
#      事后再编码。实测：一步到位 3.5fps vs 两阶段 28.8fps。
#   5) 进关后必须等 `AI_TAS_POST_ENTER_WAIT`（~2s）才动，否则稳定差最后 1 个徽章。
#
# 用法: record_trial.sh [输出路径] [难度 futsuu] [关卡 1] [计划 lr] [录制秒数 26]
set -u
OUT=${1:-/workspace/kanji_l01_lr.mp4}
DIFF=${2:-futsuu}
LV=${3:-1}
PLAN=${4:-lr}
DUR=${5:-26}

# 已验证的「可靠最大压缩」时序（中1 实测 22.5s / 蓝 75.6% PASS）。
# 不定成默认的话，录出来是生产默认时序（fill 45s），慢得像没在玩。
export AI_TAS_TAP_AFTER=${AI_TAS_TAP_AFTER:-0.02}
export AI_TAS_TAP_HOLD=${AI_TAS_TAP_HOLD:-0.02}
export AI_TAS_MOVE_GAP=${AI_TAS_MOVE_GAP:-0.02}
# ★ 2026-10-13（§S24）：点关步进必须 ≥1.5——0.3 会让第二点注册不上（当年是靠下面
#   POST_ENTER_WAIT=2 叠出 3.5s 总等待才越过横幅，属侥幸而非 0.3 可用）。
export AI_TAS_NAV_TAP_AFTER=${AI_TAS_NAV_TAP_AFTER:-1.5}
export AI_TAS_NAV_ENTER_WAIT=${AI_TAS_NAV_ENTER_WAIT:-5.0}
export AI_TAS_PANEL_WAIT=${AI_TAS_PANEL_WAIT:-0.6}
# 进关后必须再等几秒才动：立刻点字会稳定差最后 1 个徽章绑不上（不出正解，§S22）
export AI_TAS_POST_ENTER_WAIT=${AI_TAS_POST_ENTER_WAIT:-2}
export AI_TAS_PAGE_WAIT=${AI_TAS_PAGE_WAIT:-0.4}
export AI_TAS_SEIKAI_WAIT=${AI_TAS_SEIKAI_WAIT:-0.3}

export DISPLAY=:99
export XDG_RUNTIME_DIR=/tmp/runtime          # 少了它 ffmpeg 连不上 pulse
export LD_LIBRARY_PATH=/usr/games:/usr/lib/x86_64-linux-gnu
cd "$(dirname "$0")"

# 开录之前把规划算完并落盘（录制时经 AI_TAS_PLAN_FILE 直接读，0s）
if [ "$PLAN" = "lr" ]; then
  export AI_TAS_PLAN_FILE=/tmp/lrplan_${DIFF}_${LV}.json
  echo "[REC] 预热规划 -> $AI_TAS_PLAN_FILE"
  python3 -c "import lr_plan, json; print(json.dumps(lr_plan.make_plan($LV, verbose=False)))" \
      > /dev/null
fi

RAW=/dev/shm/kanji_rec.bgr0
WAV=/dev/shm/kanji_rec.wav
rm -f "$OUT" "$RAW" "$WAV"

# ---- 阶段 1：只采集，不编码、不转换（保住 30fps 采集）------------------------
# 视频：x11grab 直出 bgr0，零像素格式转换，写内存盘（零磁盘延迟）。
# 音频：另起一个进程，别让 pulse 采集挤占视频采集的主循环。
ffmpeg -y -loglevel error -f x11grab -draw_mouse 0 -framerate 30 \
       -video_size 256x384 -i ":99+384,192" \
       -pix_fmt bgr0 -f rawvideo -t "$DUR" "$RAW" > /tmp/rec_v.log 2>&1 &
VFPID=$!
ffmpeg -y -loglevel error -f pulse -i kanji.monitor \
       -c:a pcm_s16le -t "$DUR" "$WAV" > /tmp/rec_a.log 2>&1 &
AFPID=$!
sleep 0.6                                    # 让 ffmpeg 真正进入录制，再开始点关
AI_TAS_PLAN="$PLAN" AI_TAS_DIFFICULTY="$DIFF" python3 timing_sweep.py --trial --level "$LV"
wait $VFPID 2>/dev/null
wait $AFPID 2>/dev/null

# ---- 阶段 2：事后编码（CPU 压力已解除，可以慢慢编）---------------------------
ffmpeg -y -loglevel error \
       -f rawvideo -pix_fmt bgr0 -video_size 256x384 -framerate 30 -i "$RAW" \
       -i "$WAV" \
       -vf scale=512:768:flags=neighbor \
       -c:v libopenh264 -pix_fmt yuv420p -r 30 -c:a aac -b:a 128k -shortest \
       "$OUT" 2>&1 | tail -3
rm -f "$RAW" "$WAV"

echo "[REC] $OUT"
ffmpeg -hide_banner -i "$OUT" 2>&1 | grep -E "Duration|Stream"
