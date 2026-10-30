#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针 5：系统扫描按键/触摸，找规则页（ル--ル N/6）的翻页方式。

判据：**上屏**（y 0..192）整块 diff —— 翻页时规则图整体重绘，diff 大。
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds


def up(im):
    return np.asarray(im.convert("RGB")).astype(np.int16)[:192]


def main():
    base = up(ds.grab(""))
    print("起始 up 已抓")
    keys = ["x", "z", "X", "Z", "Return", "Shift_R", "Shift_L", "space",
            "Up", "Down", "Left", "Right", "Escape", "Tab", "F1", "c", "v",
            "b", "n", "m", "comma", "period"]
    for k in keys:
        ds.press(k, wait=0.9)
        cur = up(ds.grab(""))
        d = float(np.abs(cur - base).mean())
        mark = "★翻页" if d > 3.0 else ""
        print(f"  key {k:8s} up_diff={d:7.3f} {mark}")
        if d > 3.0:
            ds.grab(f"rp_after_{k}")
            base = cur
    # 触摸下屏若干点
    for x, y in [(10, 175), (60, 178), (128, 178), (200, 178), (245, 178),
                 (10, 10), (245, 10), (128, 5)]:
        ds.tap(x, y, after=1.0)
        cur = up(ds.grab(""))
        d = float(np.abs(cur - base).mean())
        mark = "★翻页" if d > 3.0 else ""
        print(f"  tap({x},{y}) up_diff={d:7.3f} {mark}")
        if d > 3.0:
            ds.grab(f"rp_tap_{x}_{y}")
            base = cur
    ds.grab("rp_final")


main()
