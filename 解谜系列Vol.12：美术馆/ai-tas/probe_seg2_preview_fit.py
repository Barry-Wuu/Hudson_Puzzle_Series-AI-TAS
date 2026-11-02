#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针：暴力搜索选关页上屏**预览板**几何 (x0,y0,pitch)，
并用灰格检测墙，使预览墙布局与 puzzles.json 的 expected_walls 匹配最大。"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import play_akari_seg2 as P

IM = "/root/.codebuddy/artifact/vol12/probe_select_clicked.png"


def gray_grid(im, x0, y0, p, w=10, h=10):
    a = np.asarray(im.convert("RGB")).astype(int)
    out = []
    for r in range(h):
        row = ""
        for c in range(w):
            cx, cy = x0 + p * (c + 0.5), y0 + p * (r + 0.5)
            xi, yi = int(round(cx)), int(round(cy))
            s = max(2, int(p * 0.28))
            cell = a[yi - s:yi + s + 1, xi - s:xi + s + 1].reshape(-1, 3)
            m = cell.mean(axis=1)
            row += 'W' if m.mean() < 150 else '.'
        out.append(row)
    return out


def main():
    data = json.load(open(P.PUZZLES))
    seq = data["やさしい"]
    exp = P.expected_walls(seq[60])   # Q61
    im = Image.open(IM)
    best = None
    for x0 in range(74, 90):
        for y0 in range(20, 36):
            for p in np.arange(14.0, 17.51, 0.25):
                g = gray_grid(im, x0, y0, float(p))
                m = sum(x == y for r1, r2 in zip(g, exp) for x, y in zip(r1, r2))
                if best is None or m > best[0]:
                    best = (m, x0, y0, round(float(p), 2), g)
    m, x0, y0, p, g = best
    print("最佳几何: x0=%s y0=%s p=%s 匹配 %d/100" % (x0, y0, p, m))
    print("解析:")
    for r in g:
        print("   ", r)
    print("期望:")
    for r in exp:
        print("   ", r)


main()
