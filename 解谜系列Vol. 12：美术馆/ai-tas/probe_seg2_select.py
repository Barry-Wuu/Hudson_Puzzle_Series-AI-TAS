#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seg2（やさしい）选关页探针 v2：黄底光标定位 + 网格几何 + 滚动行为。

实测：やさしい 页光标 = 黄底黑字数字格（入门页是绿环，两页签名不同）。
背景整页有动画（每帧全屏变化），不能用帧 diff 定位光标。
"""
import time

import numpy as np

import ds


def grab():
    return np.asarray(ds.grab("").convert("RGB")).astype(int)


GRID_Y0, GRID_Y1 = 68, 150   # 选关数字网格行范围（4 行可见，第5行是 ?）


def cursor(im):
    """返回黄底光标格中心 (cx, cy) 或 None。限定在数字网格区内，
    避免误捕下方难度菜单的黄色高亮行。"""
    R, G, B = im[:, :, 0], im[:, :, 1], im[:, :, 2]
    m = (R > 170) & (G > 150) & (B < 120) & (R - B > 70) & (G - B > 50)
    m[:GRID_Y0, :] = False
    m[GRID_Y1:, :] = False
    ys, xs = np.nonzero(m)
    if len(ys) < 30:
        return None
    return int(np.median(xs)), int(np.median(ys)), len(ys)


def main():
    im = grab()
    c = cursor(im)
    print("光标:", c)
    if c:
        x, y, n = c
        print("  光标格范围 x[%d..%d] y[%d..%d]" %
              (x - 11, x + 11, y - 7, y + 7))

    # 逐格测黄底：沿网格行/列找所有黄底块
    R, G, B = im[:, :, 0], im[:, :, 1], im[:, :, 2]
    m = (R > 170) & (G > 150) & (B < 120) & (R - B > 70) & (G - B > 50)
    m[:GRID_Y0, :] = False
    m[GRID_Y1:, :] = False
    rows = {}
    for yy in range(GRID_Y0, GRID_Y1):
        xs = np.nonzero(m[yy])[0]
        if len(xs) > 5:
            rows.setdefault(yy, []).append((len(xs), int(xs.min()), int(xs.max())))
    if rows:
        ys = sorted(rows)
        print("黄底行段 y:", ys[0], "..", ys[-1], " 段数", len(ys))
        for y in ys:
            r = rows[y]
            print("  y=%3d  x[%3d..%3d]  n=%d" % (y, r[0][1], r[0][2], r[0][0]))

    # 方向键行为：每次按完读光标
    for key in ("Right", "Right", "Down", "Down", "Down", "Up", "Up", "Left"):
        ds.press(key, hold=0.04, wait=0.7)
        c = cursor(grab())
        print(f"{key} -> {c}")

    ds.grab("p_yas_v2")


if __name__ == "__main__":
    main()
