#!/bin/bash
# 拉起 Xvfb + DeSmuME（纯解释器模式，绕沙箱 seccomp）。后台常驻。
set -e
rm -f /tmp/.X11-unix/X99
Xvfb :99 -screen 0 1024x768x24 >/tmp/xvfb.log 2>&1 &
echo "Xvfb pid $!"
sleep 2
export DISPLAY=:99
export LD_LIBRARY_PATH=/usr/games:/usr/lib/x86_64-linux-gnu
exec /usr/games/desmume-cli --cpu-mode=0 --disable-sound --nojoy=1 /root/.codebuddy/artifact/kanji/game.nds
