#!/usr/bin/env python3
"""limiter ON 下点灯剂量参数隔离：逐组测「点亮格数」，找真正敏感的参数。"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import ds
from play_akari import (PUZZLES, boot_to_select, goto, wait_select, board_walls,
                        expected_walls, escape_to_select, bulb_points)


def lit_count(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    reg = a[216:216 + 144, 24:24 + 144]
    lit = ((reg[:, :, 0] > 150) & (reg[:, :, 1] > 120) & (reg[:, :, 2] < 120)).sum()
    return int(lit)


def main():
    data = json.load(open(PUZZLES))
    pz = data["入門"][1]
    pts = bulb_points(pz)
    print("Q2 灯数=%d" % len(pts), flush=True)
    configs = [
        ("A 只加gap", dict(gap=0.04, hold=0.08, after=0.10)),
        ("B 只加hold", dict(gap=0.03, hold=0.10, after=0.10)),
        ("C 只加after", dict(gap=0.03, hold=0.08, after=0.22)),
        ("D 全新加大", dict(gap=0.05, hold=0.15, after=0.30)),
        ("E 中档", dict(gap=0.04, hold=0.12, after=0.20)),
    ]
    for name, dose in configs:
        if not wait_select(3):
            if not escape_to_select():
                print("!! 无法回选关页", flush=True)
                return
        if goto(2) != 2:
            print("!! nav 失败", flush=True)
            return
        ds.press("x", wait=0.4)
        time.sleep(2.8)
        m = sum(a == b for a, b in zip("".join(board_walls(ds.grab(""))),
                                       "".join(expected_walls(pz))))
        before = lit_count(ds.grab(""))
        t0 = time.time()
        ds.tap_batch(pts, **dose)
        dt = time.time() - t0
        time.sleep(1.8)
        after = lit_count(ds.grab(""))
        print("%-12s %s 墙%d/36 用时%.2fs 点亮Δ=%d (before=%d after=%d)" %
              (name, dose, m, dt, after - before, before, after), flush=True)
        # 退出本关
        ds.press("x", wait=0.4)
        if not wait_select(2):
            ds.press("x", wait=0.4)
            wait_select(2)
        if not wait_select(1):
            escape_to_select()
        time.sleep(0.5)


if __name__ == "__main__":
    main()
