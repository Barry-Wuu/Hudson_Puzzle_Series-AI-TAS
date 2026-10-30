#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针：规则说明页（ルール N/6）如何翻页/跳过。"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds


def counter(im):
    """右上角 3/6 的蓝色像素区域。"""
    a = np.asarray(im.convert("RGB")).astype(int)
    reg = a[2:22, 200:250]
    return int(((reg[:, :, 2] > 110) & (reg[:, :, 0] < 95) & (reg[:, :, 1] > 60)).sum())


def snap(name):
    im = ds.grab(name)
    print(f"  {name} counter_blue={counter(im)}")
    return im


def main():
    print("初始:")
    snap("rule_init")
    # 试各种翻页方式
    for key in ("x", "a", "b", "z", "Shift_L", "Up", "Right", "Down", "Left",
                "Return", "space", "Tab"):
        ds.press(key, wait=0.9)
        im = ds.grab(f"rule_key_{key}")
        c = counter(im)
        print(f"  key={key} counter_blue={c}")
        if c != counter(ds.grab("rule_init")):
            print(f"    → 变化了！")
            break


main()
