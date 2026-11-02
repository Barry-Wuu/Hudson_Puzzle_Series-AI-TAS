#!/usr/bin/env python3
"""limiter ON 下的时序探针：正常速度下测
  1) 点灯 dose 是否仍能全亮（0.12s/灯）
  2) 通关后「结算面板」最早可被 x 关闭的时刻（决定 settle 值）
从标题页自动 boot 到入門选关页，进 Q2 实测。"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import ds
from play_akari import (X0, Y0, P, PUZZLES, BULB_DOSE, boot_to_select, cursor_green,
                        goto, wait_select, board_walls, expected_walls,
                        board_dark_count, bulb_points, escape_to_select)


def is_select_fast(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    rows_ok = 0
    for y in (290, 310):
        m = (a[y][:, 2] > 90) & (a[y][:, 0] < 90) & (a[y][:, 1] > 70)
        runs, s = 0, None
        for i, v in enumerate(m):
            if v and s is None:
                s = i
            if not v and s is not None:
                if i - s > 12:
                    runs += 1
                s = None
        if s is not None and 255 - s > 12:
            runs += 1
        if runs >= 9:
            rows_ok += 1
    return rows_ok >= 1


def main():
    data = json.load(open(PUZZLES))
    pz = data["入門"][1]  # Q2
    if not wait_select(4):
        print("escape/boot…", flush=True)
        if not escape_to_select() and not boot_to_select():
            print("!! 无法回到选关页", flush=True)
            return
    if goto(2) != 2:
        print("!! nav 失败", flush=True)
        return
    print("进 Q2…", flush=True)
    ds.press("x", wait=0.4)
    time.sleep(2.8)
    exp = expected_walls(pz)
    m = sum(a == b for a, b in zip("".join(board_walls(ds.grab(""))), "".join(exp)))
    print("墙匹配 %d/36" % m, flush=True)
    t0 = time.time()
    ds.tap_batch(bulb_points(pz), **BULB_DOSE)
    t_light = time.time() - t0
    cleared = None
    tc = time.time()
    while time.time() - tc < 8:
        time.sleep(0.2)
        if board_dark_count(ds.grab("")) < 120:
            cleared = time.time() - tc
            break
    print("点灯耗时 %.2fs  全亮判定=%s (%.2fs)" % (t_light, cleared is not None, cleared or -1), flush=True)
    if cleared is None:
        ds.grab("FAIL_probe_clear")
        print("!! 未全亮，dose 在正常速度下不成立", flush=True)
        return
    # 结算面板：每 0.5s 试按一次 x，看何时真能回选关页
    base = time.time()
    for k in range(14):
        el = time.time() - base
        ds.press("x", wait=0.25)
        ok = is_select_fast(ds.grab(""))
        print("  t=%.1fs 按x -> select=%s" % (el, ok), flush=True)
        if ok:
            print("=> 最早可关闭时刻 ≈ %.1fs（距全亮 %.1fs）" % (el + 0.25, cleared + el + 0.25), flush=True)
            return
        time.sleep(0.25)
    print("!! 14 次仍未回选关页", flush=True)


if __name__ == "__main__":
    main()
