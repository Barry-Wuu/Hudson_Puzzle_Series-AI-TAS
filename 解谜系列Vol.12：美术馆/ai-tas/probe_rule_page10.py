#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针 10：规则页用下屏底部 ◀▶ / 閉じる 按钮翻页与关闭。"""
import hashlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds

NUM = (0, 215, 26, 256)     # 右上角 N/6 (y0,x0,y1,x1)


def numimg():
    a = np.asarray(ds.grab("").convert("RGB")).astype(np.int16)
    return a[NUM[0]:NUM[2], NUM[1]:NUM[3]]


def h(x):
    return hashlib.md5(x.tobytes()).hexdigest()[:8]


def main():
    base = numimg()
    print("start num:", h(base))
    ds.grab("r10_start")
    acts = [
        ("▶ (238,368)", lambda: ds.tap_local(238, 368, after=1.3)),
        ("◀ (207,368)", lambda: ds.tap_local(207, 368, after=1.3)),
        ("▶ (238,362)", lambda: ds.tap_local(238, 362, after=1.3)),
        ("▶ (243,372)", lambda: ds.tap_local(243, 372, after=1.3)),
        ("閉じる (222,381)", lambda: ds.tap_local(222, 381, after=1.5)),
        ("閉じる (200,381)", lambda: ds.tap_local(200, 381, after=1.5)),
    ]
    for name, fn in acts:
        fn()
        cur = numimg()
        d = float(np.abs(cur - base).mean())
        print(f"  {name:20s} numhash={h(cur)} diff={d:.2f} {'★' if d > 1 else ''}")
        base = cur
    ds.grab("r10_end")


main()
