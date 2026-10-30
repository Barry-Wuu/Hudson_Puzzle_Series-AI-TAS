#!/bin/bash
# 以「纯解释器模式」启动 DeSmuME CLI。
#
# 为什么必须加 --cpu-mode=0：
#   DeSmuME 默认启用 JIT 动态重编译，运行期需要 mmap(PROT_EXEC)/mprotect；
#   在启用 seccomp 的沙箱里这会触发 SIGSYS，进程启动即被杀（日志只到 "DeSmuME 0.9.11"）。
#   改用纯解释器（--cpu-mode=0）即可绕过该限制，模拟器稳定运行。
#
# 用法： [AI_TAS_DISPLAY=:99] ./launch_desmume_interp.sh [ROM路径] [日志路径]
set -e
DISP="${AI_TAS_DISPLAY:-:99}"
ROM="${1:-game.nds}"
LOG="${2:-/tmp/desmume.log}"
export DISPLAY="$DISP"
export LD_LIBRARY_PATH="${AI_TAS_LD_LIB:-/usr/games}:/usr/lib/x86_64-linux-gnu"
exec /usr/games/desmume-cli --cpu-mode=0 --disable-sound --nojoy=1 "$ROM" >>"$LOG" 2>&1
