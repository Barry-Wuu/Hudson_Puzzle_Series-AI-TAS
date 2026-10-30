#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针 7：定向测试规则页翻页。

假设：规则页在上屏（绿标题栏 + 右上 N/6），翻页由**下屏右下角 ◀ ▶ 箭头**控制
（下屏仍显示上一关盘面 + 右侧菜单，最底部有 ◀▶ 与「閉じる」）。

动作：逐个候选动作 → 保存页码区域裁剪 → 打印是否变化。
"""
import hashlib
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds

NUM_REGION = (0, 0, 256, 26)      # 绿标题栏整条（含 ルール 与 N/6）
NUM_REGION2 = (210, 0, 256, 26)    # 只看 N/6


def h(arr):
    return hashlib.md5(arr.tobytes()).hexdigest()[:10]


def snap(tag):
    im = ds.grab("")
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    full = a[NUM_REGION[0]:NUM_REGION[1], NUM_REGION[2]:NUM_REGION[3]]
    num = a[NUM_REGION2[0]:NUM_REGION2[1], NUM_REGION2[2]:NUM_REGION2[3]]
    ds.grab(f"rp7_{tag}")
    return h(full), h(num)


def main():
    print("起始:", snap("init"))
    acts = [
        ("tap(232,347)", lambda: ds.tap_local(232, 347, after=1.2)),
        ("tap(210,347)", lambda: ds.tap_local(210, 347, after=1.2)),
        ("tap(232,340)", lambda: ds.tap_local(232, 340, after=1.2)),
        ("tap(232,355)", lambda: ds.tap_local(232, 355, after=1.2)),
        ("tap(245,370)", lambda: ds.tap_local(245, 370, after=1.2)),
        ("tap(200,370)", lambda: ds.tap_local(200, 370, after=1.2)),
        ("key x", lambda: ds.press("x", wait=1.2)),
    ]
    for name, fn in acts:
        fn()
        f, n = snap(name.replace(" ", "_").replace("(", "").replace(")", "").replace(",", "_"))
        print(f"  {name:16s} full={f} num={n}")


main()
