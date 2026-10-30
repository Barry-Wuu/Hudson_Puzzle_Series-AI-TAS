#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针 3：规则说明页（ルール N/6）如何翻页 —— 用图像差分判据（不依赖颜色）。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds


def grab_arr():
    return np.asarray(ds.grab("").convert("RGB")).astype(np.int16)


def diff(a, b):
    return float(np.abs(a - b).mean())


def main():
    base = grab_arr()
    print("初始 md5-ish ok")
    tries = [
        ("key x", lambda: ds.press("x", wait=1.0)),
        ("key Return", lambda: ds.press("Return", wait=1.0)),
        ("key Up", lambda: ds.press("Up", wait=1.0)),
        ("key Down", lambda: ds.press("Down", wait=1.0)),
        ("key Left", lambda: ds.press("Left", wait=1.0)),
        ("key Right", lambda: ds.press("Right", wait=1.0)),
        ("tap NDS(128,80)", lambda: ds.tap(128, 80, after=1.0)),
        ("tap NDS(30,150)", lambda: ds.tap(30, 150, after=1.0)),
        ("tap NDS(230,20)", lambda: ds.tap(230, 20, after=1.0)),
        ("tap NDS(128,10)", lambda: ds.tap(128, 10, after=1.0)),
        ("tap NDS(250,175)", lambda: ds.tap(250, 175, after=1.0)),
    ]
    for name, fn in tries:
        fn()
        cur = grab_arr()
        d = diff(base, cur)
        print(f"  {name}: diff={d:.3f} {'★ 变化' if d > 1.0 else ''}")
        if d > 1.0:
            ds.grab("rule_changed")
            base = cur
    ds.grab("rule_final")


main()
