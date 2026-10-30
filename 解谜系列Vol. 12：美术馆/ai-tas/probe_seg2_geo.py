#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""10×10 盘面几何验证：X0=16, Y0=208, PITCH=16 下的墙检测 vs 官方答案。

关键差异（vs 入門 6×6）：
  * 入門 X0=24 Y0=216 P=24，格心取 ±7；
  * 10×10 P=16，格心 ±7 会溢出到格线（蓝）上，故取 ±5 更安全。
"""
import json
import os
import sys

import numpy as np

import ds

PUZZLES = os.path.join(os.path.dirname(__file__), "..", "validation", "puzzles.json")
X0, Y0, P = 16, 208, 16


def walls(a, half):
    out = []
    for r in range(10):
        row = ""
        for c in range(10):
            cx, cy = X0 + P * (c + 0.5), Y0 + P * (r + 0.5)
            cell = a[int(cy) - half:int(cy) + half, int(cx) - half:int(cx) + half].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += "W" if blue > 0.35 else "."
        out.append(row)
    return out


def main():
    a = np.asarray(ds.grab("s2_geo2").convert("RGB")).astype(int)
    d = json.load(open(PUZZLES))
    pz = d["やさしい"][0]
    exp = ["".join("W" if pz["given"][y * pz["w"] + x] == 45 else "."
                   for x in range(pz["w"])) for y in range(pz["h"])]
    for half in (5, 6, 7):
        got = walls(a, half)
        m = sum(x == y for r1, r2 in zip(got, exp) for x, y in zip(r1, r2))
        print(f"half={half}: 匹配 {m}/100")
        for r1, r2 in zip(got, exp):
            mark = "" if r1 == r2 else "   <<<"
            print(f"  got {r1}   exp {r2}{mark}")
        print()
    # 触摸坐标
    print("bulbs 触摸坐标(NDS):")
    for (x, y) in pz["bulbs"]:
        print(f"  ({x},{y}) -> ({int(X0 + P * (x + 0.5))}, {int(Y0 + P * (y + 0.5) - 192)})")


if __name__ == "__main__":
    main()
