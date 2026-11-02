#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从选关页**上屏预览板**提取所选关卡的墙布局（深灰方块），
再与 puzzles.json 全部 100 关比对，找出编号偏移。

方法：
  1. 上屏找出白底板区域 bbox
  2. 找深灰方块簇（墙）中心
  3. 用网格投票推断 pitch & origin（10×10）
  4. 提取墙布局，与 puzzles 逐关比对
"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import play_akari_seg2 as P

IM = sys.argv[1] if len(sys.argv) > 1 else "/root/.codebuddy/artifact/vol12/probe_select_clicked.png"
N = int(sys.argv[2]) if len(sys.argv) > 2 else 61


def clusters(mask, min_size=4):
    """简单连通域，返回质心与面积。"""
    h, w = mask.shape
    lab = np.zeros((h, w), int)
    cur = 0
    out = []
    ys, xs = np.nonzero(mask)
    seen = set()
    for y0, x0 in zip(ys, xs):
        if (y0, x0) in seen:
            continue
        cur += 1
        stack = [(y0, x0)]
        seen.add((y0, x0))
        pts = []
        while stack:
            y, x = stack.pop()
            pts.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and (ny, nx) not in seen:
                        seen.add((ny, nx))
                        stack.append((ny, nx))
        if len(pts) >= min_size:
            arr = np.array(pts)
            out.append((arr[:, 1].mean(), arr[:, 0].mean(), len(pts)))
    return out


def main():
    a = np.asarray(Image.open(IM).convert("RGB")).astype(int)
    up = a[:192, :, :]
    gray = (up[:, :, 0] < 120) & (up[:, :, 1] < 120) & (up[:, :, 2] < 120)
    cs = clusters(gray, 6)
    print("上屏深灰簇数:", len(cs))
    cs.sort(key=lambda c: (c[1], c[0]))
    for c in cs:
        print("   x=%.1f y=%.1f area=%d" % c)

    if not cs:
        return
    xs = np.array([c[0] for c in cs])
    ys = np.array([c[1] for c in cs])
    # 板区域：x>60 且 y>25（排除标题栏）
    sel = [(x, y, s) for x, y, s in cs if x > 60 and 25 < y < 190]
    print("\n板内簇数:", len(sel))
    if len(sel) < 3:
        return
    bx = np.array([c[0] for c in sel])
    by = np.array([c[1] for c in sel])
    # 用差分推断 pitch
    ux = np.unique(np.round(np.diff(np.sort(bx)), 1))
    uy = np.unique(np.round(np.diff(np.sort(by)), 1))
    print("x 差分:", ux[:12])
    print("y 差分:", uy[:12])


main()
