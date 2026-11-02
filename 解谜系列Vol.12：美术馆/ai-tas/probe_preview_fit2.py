#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""标定：选关页上屏**预览板**几何（用真实关卡反查）。
做法：进关 → 抓进关瞬间的上屏预览图 → 与 puzzles.json 全表比对 → 暴力搜几何。
"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import play_akari_seg2 as P

IM = sys.argv[1] if len(sys.argv) > 1 else "/root/.codebuddy/artifact/vol12/sel_51.png"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 51


def preview_grid(im, x0, y0, p, thr=170):
    a = np.asarray(im.convert("RGB")).astype(int)
    out = []
    for r in range(10):
        row = ""
        for c in range(10):
            xi = int(round(x0 + p * (c + 0.5)))
            yi = int(round(y0 + p * (r + 0.5)))
            s = max(2, int(p * 0.3))
            cell = a[yi - s:yi + s + 1, xi - s:xi + s + 1].reshape(-1, 3)
            row += 'W' if cell.mean(axis=1).mean() < thr else '.'
        out.append(row)
    return out


def main():
    im = Image.open(IM)
    data = json.load(open(P.PUZZLES))
    seq = data["やさしい"]
    # 目标：该预览对应的 puzzles 编号（已知游戏第 51 关 = puzzles 第 70 关）
    target = 70
    exp = P.expected_walls(seq[target - 1])
    best = None
    for x0 in np.arange(70, 92, 1.0):
        for y0 in np.arange(18, 40, 1.0):
            for p in np.arange(13.0, 18.01, 0.5):
                for thr in (150, 170, 190):
                    g = preview_grid(im, x0, y0, float(p), thr)
                    m = sum(x == y for r1, r2 in zip(g, exp) for x, y in zip(r1, r2))
                    if best is None or m > best[0]:
                        best = (m, x0, y0, round(float(p), 2), thr, g)
    m, x0, y0, p, thr, g = best
    print(f"最佳: x0={x0} y0={y0} p={p} thr={thr} 匹配 {m}/100")
    print("解析:")
    for r in g:
        print("   ", r)
    print("期望(第70关):")
    for r in exp:
        print("   ", r)


main()
