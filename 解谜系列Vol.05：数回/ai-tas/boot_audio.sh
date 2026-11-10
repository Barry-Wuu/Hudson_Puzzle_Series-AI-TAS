#!/usr/bin/env bash
# Vol.05 数回 —— 带音频实机环境一键启动（录制专用）
#
# 与 boot.sh 的区别：boot.sh 用 --disable-sound（只截图，速度快）；
# 本脚本让 DeSmuME 走 SDL_AUDIODRIVER=pulse -> desmume_out 空 sink，
# ffmpeg 从 desmume_out.monitor 收音，BGM=RANDOM 才能录进视频。
#
# 前置：pulse_cfg.pa（vol12/vol11 录制沿用的空 sink 配置）可缺，本脚本会自建。
set -e
export XDG_RUNTIME_DIR=/tmp
export DISPLAY=:99

# 1) Xvfb
if ! pgrep -x Xvfb >/dev/null; then
  rm -f /tmp/.X11-unix/X99
  Xvfb :99 -screen 0 1280x1024x24 +extension GLX +extension RANDR +extension RENDER >/tmp/xvfb.log 2>&1 &
  sleep 2
fi

# 2) pulseaudio 空 sink（native socket /tmp/pulse_native + desmume_out）
if [ ! -f /tmp/pulse_cfg.pa ]; then
  cat > /tmp/pulse_cfg.pa <<'EOF'
load-module module-native-protocol-unix socket=/tmp/pulse_native auth-anonymous=1
load-module module-null-sink sink_name=desmume_out sink_properties=device.description=desmume_out
set-default-sink desmume_out
EOF
fi
if ! PULSE_SERVER=unix:/tmp/pulse_native pactl info >/dev/null 2>&1; then
  mkdir -p /run/user/102 /tmp/pulsehome
  chown pulse:pulse /run/user/102 /tmp/pulsehome 2>/dev/null || true
  chmod 700 /run/user/102
  rm -f /tmp/pulse_native
  runuser -u pulse -- env XDG_RUNTIME_DIR=/run/user/102 HOME=/tmp/pulsehome \
    pulseaudio -n -F /tmp/pulse_cfg.pa --exit-idle-time=-1 --disable-shm=1 \
    --disallow-exit --log-target=file:/tmp/pulse.log >/dev/null 2>&1 &
  sleep 3
fi

# 3) DeSmuME（带音频；不带 --disable-sound）
if ! pgrep -x desmume-cli >/dev/null; then
  PULSE_SERVER=unix:/tmp/pulse_native SDL_AUDIODRIVER=pulse SDL_VIDEODRIVER=x11 \
  SDL_VIDEO_WINDOW_POS=384,192 \
    /usr/games/desmume-cli --cpu-mode=1 --num-cores=1 \
    "/workspace/roms/解谜系列Vol.05：数回.nds" >/tmp/desmume_vol5_audio.log 2>&1 &
  for _ in $(seq 1 60); do
    sleep 0.5
    id=$(xdotool search --name desmume 2>/dev/null | head -1)
    [ -n "$id" ] && break
  done
  sleep 4
fi

echo "Xvfb + pulse(desmume_out) + desmume-cli(带音频) 就绪。"
echo "sink: $(PULSE_SERVER=unix:/tmp/pulse_native pactl list short sinks 2>/dev/null | tr '\n' ' ')"
echo "窗口: $(xdotool search --name desmume 2>/dev/null | tr '\n' ' ')"
