#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针 8：进 Q51 后逐次按 x，记录 (a) 页码区域 (b) 下屏盘面归属的 puzzles 编号。
"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import play_akari_seg2 as P

data = json.load(open(P.PUZZLES))
seq = data["やさしい"]
exp_all = [P.expected_walls(p) for p in seq if p["w"] == 10]


def board_owner(im):
    a = np.asarray(im.convert("RGB")).astype(int)
    got = []
    for r in range(10):
        row = ""
        for c in range(10):
            cx, cy = int(16 + 16 * (c + 0.5)), int(208 + 16 * (r + 0.5))
            cell = a[cy - 5:cy + 6, cx - 5:cx + 6].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += "W" if blue > 0.35 else "."
        got.append(row)
    best = []
    for i, e in enumerate(exp_all):
        m = sum(x == y for r1, r2 in zip(got, e) for x, y in zip(r1, r2))
        best.append((m, i + 1))
    best.sort(reverse=True)
    return got, best[:2]


def counter_sig(im):
    a = np.asarray(im.convert("RGB")).astype(np.int16)
    return a[0:26, 210:256].tobytes()


def main():
    for i in range(10):
        im = ds.grab(f"p8_{i}")
        got, best = board_owner(im)
        cs = counter_sig(im)
        print(f"iter{i}: board_owner={best}  num_sig={cs[:6].hex()}")
        if i == 0:
            ds.grab("p8_0")
        ds.press("x", wait=1.3)
    print("done")


main()
