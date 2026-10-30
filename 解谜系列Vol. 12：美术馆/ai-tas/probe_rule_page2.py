#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针 2：识别规则说明页（「ルール N/6」）并找出翻页/跳过方式。

判据：上屏 y=0..24 的左上角有「ルール」标题（白字）+ 右上角 N/6（白字）
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds


def white_frac(a, y0, y1, x0, x1):
    reg = a[y0:y1, x0:x1]
    return float(((reg[:, :, 0] > 200) & (reg[:, :, 1] > 200) & (reg[:, :, 2] > 200)).mean())


def state(name):
    im = ds.grab(name)
    a = np.asarray(im.convert("RGB")).astype(int)
    left = white_frac(a, 2, 22, 2, 60)      # 「ルール」
    right = white_frac(a, 2, 22, 215, 250)   # N/6
    print(f"  {name}: left_white={left:.3f} right_white={right:.3f}")
    return left, right


def main():
    print("当前:")
    base = state("r_init")
    for key in ("x", "Up", "Right", "Down", "Left", "Return", "space", "a", "b"):
        ds.press(key, wait=0.9)
        s = state(f"r_{key}")
        if abs(s[1] - base[1]) > 0.01 or abs(s[0] - base[0]) > 0.01:
            print(f"    → key={key} 有效")
    # 试点击上屏左右（翻页箭头）
    for x, y in ((30, 100), (230, 100), (128, 10), (245, 12)):
        ds.tap_local(x, y, after=1.0)
        s = state(f"r_tap{x}_{y}")
        if abs(s[1] - base[1]) > 0.01 or abs(s[0] - base[0]) > 0.01:
            print(f"    → tap({x},{y}) 有效")


main()
