#!/bin/bash
# 环境自愈：确保 Xvfb :99 + DeSmuME（纯解释器、静音）就绪。
#
# 背景（PITFALLS §T.2）：Xvfb 偶发死亡且残留 /tmp/.X11-unix/X99 socket，
#   若不先删 socket 就重启，新 Xvfb 报 "Server already active" 直接退出、:99 无服务。
#   另：desmume 带 pulse 声音时会刷 "master brightness" 噪音、疑似不稳，故用 --disable-sound。
#
# 幂等：显示通则不动；desmume 不在才拉起。任何时候显示不通 → 清锁 + 杀残留 + 重启。
# 用法： [AI_TAS_DISPLAY=:99] bash ensure_env.sh
set +e
DISP="${AI_TAS_DISPLAY:-:99}"
export DISPLAY="$DISP"
export LD_LIBRARY_PATH=/usr/games:/usr/lib/x86_64-linux-gnu
export AI_TAS_DISPLAY="$DISP"

display_ok() { xdotool getdisplaygeometry >/dev/null 2>&1; }

if ! display_ok; then
  echo "[env] 显示不通：杀残留 + 清 X 锁（§T.2）+ 重启 Xvfb"
  pkill -x desmume-cli 2>/dev/null; sleep 2       # 先让 desmume 有机会 SIGTERM 落盘
  pkill -x Xvfb 2>/dev/null; sleep 1
  rm -f /tmp/.X11-unix/X99 /tmp/.X99-lock
  setsid Xvfb "$DISP" -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 </dev/null &
  sleep 3
fi

if ! pgrep -x desmume-cli >/dev/null; then
  echo "[env] 启动 DeSmuME（纯解释器 --cpu-mode=0，静音）"
  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}"
  setsid /usr/games/desmume-cli --cpu-mode=0 --disable-sound --nojoy=1 /workspace/Kanji/game.nds \
      >>/tmp/desmume.log 2>&1 </dev/null &
  sleep 3
fi

# 校验
if display_ok; then
  echo "[env] ✅ 显示几何 $(DISPLAY=$DISP xdotool getdisplaygeometry 2>&1)"
else
  echo "[env] ❌ 显示仍不通"; tail -3 /tmp/xvfb.log; exit 1
fi
echo "[env] 进程 Xvfb=$(pgrep -x Xvfb | tr '\n' ' ') desmume=$(pgrep -x desmume-cli | tr '\n' ' ')"
