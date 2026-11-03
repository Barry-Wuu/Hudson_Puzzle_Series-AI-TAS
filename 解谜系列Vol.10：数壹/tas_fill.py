#!/usr/bin/env python3
"""数壹（Hitori）实机自动涂黑：按官方答案掩码逐格点击。

剂量 = 每格点击之间的延时，等于 settle（移到目标格后等一拍）+ hold（按住时长）+ gap（松开后等一拍）。
入門 6×6 实机标定结果见 README「点击剂量」。

用法：python3 tas_fill.py <难度 0-3> <关号> [hold] [gap] [settle]
依赖：Xvfb :99 上的 DeSmuME 窗口（512×768），xdotool、ImageMagick import。
"""
import json
import subprocess
import sys
import time

# 棋盘 bbox 以 512×768（2×）窗口为基准，写在下屏内的相对偏移：
# 棋盘左上角相对下屏顶 (BX0=46, BY0=45)，格宽 BSX=48.67、格高 BSY=48.83。
# tap() 会按当前窗口宽度自动缩放（1×=256×384 时整体 ×0.5）。
BX0, BY0, BSX, BSY = 46.0, 45.0, 48.67, 48.83

ENV = {"DISPLAY": ":99",
       "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"}

# 剂量常量（秒）：0.14s/格 实测 9/9 命中、TIME 3s、三星
HOLD, GAP, SETTLE = 0.06, 0.04, 0.04


def geom():
    """返回 DeSmuME 窗口的绝对左上角与尺寸。"""
    r = subprocess.run(["xdotool", "search", "--name", "[Dd]esmume"], env=ENV,
                       capture_output=True, text=True)
    wid = [x for x in r.stdout.split() if x.strip()][-1]
    info = subprocess.run(["xwininfo", "-id", wid], env=ENV,
                          capture_output=True, text=True).stdout
    d = {}
    for ln in info.splitlines():
        ln = ln.strip()
        for k, key in (("Absolute upper-left X", "x"), ("Absolute upper-left Y", "y"),
                       ("Width:", "w"), ("Height:", "h")):
            if ln.startswith(k):
                d[key] = int(ln.split(":")[1])
    return d


def load_cells(diff, idx, json_path='vol10_all.json'):
    data = json.load(open(json_path))
    rec = [r for r in data if r['diff'] == diff and r['idx'] == idx][0]
    return rec, [(r, c) for r in range(rec['h']) for c in range(rec['w']) if rec['M'][r][c]]


def tap(cells, hold=HOLD, gap=GAP, settle=SETTLE, g=None):
    """一次 xdotool 调用打完所有格子。注意 mousemove 必须同时给 x、y——
    漏掉 y 会让 xdotool 把 'sleep' 当坐标解析，鼠标停在上一个位置，
    于是同一格被点两次，变成「白マス印」."""
    g = g or geom()
    s = g['w'] / 512.0  # 1×=0.5，2×=1.0
    parts = []
    for r, c in cells:
        sx = g['x'] + int((BX0 + BSX * (c + 0.5)) * s)
        sy = g['y'] + g['h'] // 2 + int((BY0 + BSY * (r + 0.5)) * s)
        parts += ['mousemove', str(sx), str(sy), 'sleep', f'{settle:.3f}',
                  'mousedown', '1', 'sleep', f'{hold:.3f}',
                  'mouseup', '1', 'sleep', f'{gap:.3f}']
    t = time.time()
    subprocess.run(['xdotool'] + parts, env=ENV)
    return time.time() - t


def click_img(ix, iy, g=None):
    """在窗口内以图像像素坐标点击（适用于上/下屏任何 UI 元素）。"""
    g = g or geom()
    sx = g['x'] + int(ix)
    sy = g['y'] + int(iy)
    subprocess.run(['xdotool', 'mousemove', str(sx), str(sy)], env=ENV)
    time.sleep(0.2)
    subprocess.run(['xdotool', 'mousedown', '1'], env=ENV); time.sleep(0.12)
    subprocess.run(['xdotool', 'mouseup', '1'], env=ENV)


if __name__ == '__main__':
    diff = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    idx = int(sys.argv[2]) if len(sys.argv) > 2 else 9
    hold = float(sys.argv[3]) if len(sys.argv) > 3 else HOLD
    gap = float(sys.argv[4]) if len(sys.argv) > 4 else GAP
    settle = float(sys.argv[5]) if len(sys.argv) > 5 else SETTLE
    rec, cells = load_cells(diff, idx)
    print(f"关 {idx:03d} {rec['w']}×{rec['h']}，需涂 {len(cells)} 格，"
          f"剂量 {settle}+{hold}+{gap}={settle + hold + gap:.3f}s/格")
    el = tap(cells, hold, gap, settle)
    print(f"实测 {el:.2f}s（{el / len(cells):.3f}s/格）")
