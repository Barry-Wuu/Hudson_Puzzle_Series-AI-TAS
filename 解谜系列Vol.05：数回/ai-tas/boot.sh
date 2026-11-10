#!/usr/bin/env bash
# Vol.05 数回 —— 实机环境一键启动（DeSmuME + Xvfb）
#
# 关键坑（本轮实测）：
#   1. Xvfb :99 经常不在运行（只剩 /tmp/.X11-unix/X99 残套接字），必须先起 Xvfb。
#   2. desmume-cli 需要 XDG_RUNTIME_DIR，否则 SDL 不建窗口、进程空转（无窗口名）。
#   3. 只用 desmume-cli（SDL 窗口）即可被 xdotool 触摸 + import 截图，无需 GTK GUI。
#
# 用法： bash boot.sh   （之后另开脚本 import ds / from ds import *）
set -e
export XDG_RUNTIME_DIR=/tmp
export DISPLAY=:99

# 1) 起 Xvfb（若未运行）
if ! pgrep -x Xvfb >/dev/null; then
  rm -f /tmp/.X11-unix/X99
  Xvfb :99 -screen 0 1280x1024x24 +extension GLX +extension RANDR +extension RENDER >/tmp/xvfb.log 2>&1 &
  sleep 2
fi

# 2) 起 desmume-cli（若未运行）
if ! pgrep -x desmume-cli >/dev/null; then
  /usr/games/desmume-cli --cpu-mode=1 --disable-sound --num-cores=1 \
    "/workspace/roms/解谜系列Vol.05：数回.nds" >/tmp/desmume_vol5.log 2>&1 &
  # 等窗口出现并 settle
  for _ in $(seq 1 60); do
    sleep 0.5
    id=$(DISPLAY=:99 XDG_RUNTIME_DIR=/tmp xdotool search --name desmume 2>/dev/null | head -1)
    [ -n "$id" ] && break
  done
  sleep 3
fi

echo "Xvfb + desmume-cli 就绪。窗口:"
DISPLAY=:99 XDG_RUNTIME_DIR=/tmp xdotool search --name desmume 2>/dev/null
