#!/usr/bin/env python3
"""Vol.05 数回 (SLITHERLINK / A3LJ) DeSmuME 操作公用层。

移植自 Vol.11/Vol.12 已验证的 ds.py：
  - 用 desmume-cli（SDL 窗口）即可被 xdotool 触摸 + import 截图，无需 GTK GUI。
  - 窗口必须 windowmove 到 (384,192)，截图 crop 才能对齐（下屏在窗口 y=192 起）。
  - 触摸用 mousemove→sleep→down→hold→up；gap 默认 0.04（坐标生效后再 down）。

★ 棋盘几何（GRID_X0/GRID_Y0/PITCH）与 tap 剂量（GAP/HOLD/AFTER）属于**待实机标定**项，
  先给占位值，boot 后用 probe 脚本量出来再回填。
"""
import os, signal, subprocess, time
from PIL import Image

DISP = ":99"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROM = "/workspace/roms/解谜系列Vol.05：数回.nds"
WIN_X, WIN_Y = 384, 192          # 窗口左上角；下屏内容从窗口 y=192 起
WIN_W, WIN_H = 256, 384
ENV = dict(os.environ, DISPLAY=DISP, XDG_RUNTIME_DIR="/tmp")


def win():
    out = subprocess.run(["xdotool", "search", "--name", "desmume"],
                         env=ENV, capture_output=True, text=True).stdout.split()
    return out[0] if out else None


def ensure_window():
    w = win()
    if not w:
        return None
    subprocess.run(["xdotool", "windowmove", w, str(WIN_X), str(WIN_Y)], env=ENV)
    subprocess.run(["xdotool", "windowfocus", w], env=ENV)
    return w


def start():
    if win():
        ensure_window()
        return win()
    log = open("/tmp/desmume_vol5.log", "w")
    subprocess.Popen(["desmume-cli", "--cpu-mode=1", "--disable-sound",
                      "--num-cores=1", ROM],
                     env=ENV, stdout=log, stderr=log, start_new_session=True)
    for _ in range(60):
        time.sleep(0.5)
        if ensure_window():
            time.sleep(3)
            return win()
    raise RuntimeError("DeSmuME 启动失败")


def kill():
    subprocess.run(["pkill", "-x", "desmume-cli"])
    time.sleep(1.2)


def grab(name="tmp"):
    ensure_window()
    raw = os.path.join(BASE, "_raw.png")
    subprocess.run(["import", "-window", "root", raw], env=ENV, check=True)
    im = Image.open(raw).crop((WIN_X, WIN_Y, WIN_X + WIN_W, WIN_Y + WIN_H))
    if name:
        im.save(os.path.join(BASE, f"{name}.png"))
    return im


def press(key, wait=0.55, hold=0.14):
    w = ensure_window()
    subprocess.run(["xdotool", "keydown", key], env=ENV)
    time.sleep(hold)
    subprocess.run(["xdotool", "keyup", key], env=ENV)
    time.sleep(wait)


def diff(a, b):
    import numpy as np
    x = np.asarray(a.convert("L")).astype(int)
    y = np.asarray(b.convert("L")).astype(int)
    return int(abs(x - y).sum())


# ---- 棋盘几何（下屏局部坐标，★ 待标定）----
GRID_X0, GRID_Y0 = 24, 24       # 占位；Slitherlink 点阵原点
PITCH = 16                       # 占位；格间距
VIS_COLS, VIS_ROWS = 10, 9       # 占位；可视列/行（小盘 6×6 全显）


def tap(nds_x, nds_y, hold=0.06, after=0.6, gap=0.04):
    """按压式触摸。nds_x/nds_y = 下屏 NDS 相对坐标 (0-255, 0-191)。"""
    w = ensure_window()
    sx, sy = WIN_X + nds_x, WIN_Y + 192 + nds_y
    subprocess.run(["xdotool", "mousemove", str(sx), str(sy), "sleep", str(gap),
                    "mousedown", "1", "sleep", str(hold), "mouseup", "1"], env=ENV)
    time.sleep(after)


if __name__ == "__main__":
    import sys
    w = start()
    print("winid", w)
    if len(sys.argv) > 1:
        im = grab(sys.argv[1])
        print("size", im.size)
