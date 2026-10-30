#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针 11：在规则页（ルール N/6）下屏直接点灯，验证是否可玩/可通关。"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import play_akari_seg2 as P

data = json.load(open(P.PUZZLES))
seq = data["やさしい"]


def board_grid(im):
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
    return got


def owner(got):
    best = []
    for i, pz in enumerate(seq):
        if pz["w"] != 10:
            continue
        e = P.expected_walls(pz)
        m = sum(x == y for r1, r2 in zip(got, e) for x, y in zip(r1, r2))
        best.append((m, i + 1))
    best.sort(reverse=True)
    return best[:3]


def main():
    im = ds.grab("p11_init")
    got = board_grid(im)
    print("当前盘面归属:", owner(got))
    idx = owner(got)[0][1]
    pz = seq[idx - 1]
    print(f"采用 puzzles #{idx}  bulbs={len(pz['bulbs'])}")
    coords = [(int(16 + 16 * (bx + 0.5)), int(16 + 16 * (by + 0.5)))
              for (bx, by) in pz["bulbs"]]
    time.sleep(6.5)
    for rnd in range(3):
        for i, (bx, by) in enumerate(pz["bulbs"]):
            if not P._lit_at(bx, by):
                ds.tap(coords[i][0], coords[i][1], hold=0.10, after=0.06)
        time.sleep(0.6)
        left = [(bx, by) for (bx, by) in pz["bulbs"] if not P._lit_at(bx, by)]
        print(f"  轮{rnd}: 未亮 {len(left)}")
        if not left:
            break
    time.sleep(1.0)
    ds.grab("p11_after")
    print("clear_panel:", P.is_clear_panel())
    print("in_select_page:", P.in_select_page())


main()
