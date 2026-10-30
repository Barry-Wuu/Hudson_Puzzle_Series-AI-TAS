#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针 9：在选关页选中某关 → 上屏预览板 → 同时搜 (几何 × puzzles 编号)，
找出游戏关卡号与 puzzles.json 编号的对应关系。
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
exp_all = [(i + 1, P.expected_walls(p)) for i, p in enumerate(seq) if p["w"] == 10]


def pg(im, x0, y0, p, thr):
    a = np.asarray(im.convert("RGB")).astype(int)
    out = []
    for r in range(10):
        row = ""
        for c in range(10):
            xi = int(round(x0 + p * (c + 0.5)))
            yi = int(round(y0 + p * (r + 0.5)))
            s = max(1, int(p * 0.3))
            cell = a[yi - s:yi + s + 1, xi - s:xi + s + 1].reshape(-1, 3)
            row += "W" if cell.mean(axis=1).mean() < thr else "."
        out.append(row)
    return out


def main():
    n = int(sys.argv[1])
    im = Image.open(f"/root/.codebuddy/artifact/vol12/sel_{n}.png")
    best = None
    for x0 in np.arange(72, 90, 1.0):
        for y0 in np.arange(20, 38, 1.0):
            for p in np.arange(13.0, 18.01, 0.5):
                for thr in (140, 160, 180, 200):
                    g = pg(im, x0, y0, float(p), thr)
                    for idx, e in exp_all:
                        m = sum(x == y for r1, r2 in zip(g, e) for x, y in zip(r1, r2))
                        if best is None or m > best[0]:
                            best = (m, x0, y0, round(float(p), 2), thr, idx, g)
    m, x0, y0, p, thr, idx, g = best
    print(f"游戏关 {n} → 最佳 (geom x0={x0} y0={y0} p={p} thr={thr}) 匹配 puzzles #{idx} : {m}/100")


main()
