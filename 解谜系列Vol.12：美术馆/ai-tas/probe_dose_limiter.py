#!/usr/bin/env python3
"""limiter ON（正常 60fps）下重标定点灯剂量：逐组测试 Q2，报告点后暗格数。"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import ds
from play_akari import (X0, Y0, P, PUZZLES, boot_to_select, goto, wait_select,
                        board_walls, expected_walls, board_dark_count, bulb_points,
                        escape_to_select)


def dark_cells(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    out = []
    for y in range(6):
        for x in range(6):
            cx, cy = int(X0 + P * (x + 0.5)), int(Y0 + P * (y + 0.5))
            c = a[cy - 5:cy + 5, cx - 5:cx + 5].reshape(-1, 3)
            if ((c[:, 0] < 60) & (c[:, 1] < 60) & (c[:, 2] < 60)).mean() > 0.5:
                out.append((x, y))
    return out


def main():
    data = json.load(open(PUZZLES))
    pz = data["入門"][1]
    pts = bulb_points(pz)
    doses = [
        dict(gap=0.03, hold=0.08, after=0.10),
        dict(gap=0.03, hold=0.09, after=0.16),
        dict(gap=0.04, hold=0.10, after=0.22),
    ]
    for i, dose in enumerate(doses):
        if not wait_select(4):
            if not escape_to_select() and not boot_to_select():
                print("!! 无法回到选关页", flush=True)
                return
        if goto(2) != 2:
            print("!! nav 失败", flush=True)
            return
        ds.press("x", wait=0.6)
        time.sleep(2.6)   # ★ limiter ON：进关动画实测 2.2s 结束，等够再点灯
        m = sum(a == b for a, b in zip("".join(board_walls(ds.grab(""))),
                                       "".join(expected_walls(pz))))
        t0 = time.time()
        ds.tap_batch(pts, **dose)
        dt = time.time() - t0
        time.sleep(1.6)
        im = ds.grab("")
        dark = dark_cells(im)
        print("dose#%d %s 耗时%.2fs 墙%d/36 暗格=%d 剩=%s" %
              (i + 1, dose, dt, m, len(dark), dark), flush=True)
        # 退出：已通关则 x 回选关；否则 Start 菜单退
        if board_dark_count(im) < 120:
            ds.press("x", wait=0.4)
            if not wait_select(3):
                ds.press("x", wait=0.4)
                wait_select(3)
        if not wait_select(1):
            escape_to_select()
        time.sleep(0.6)


if __name__ == "__main__":
    main()
