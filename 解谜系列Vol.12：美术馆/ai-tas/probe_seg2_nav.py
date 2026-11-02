#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seg2 选关导航探针：黄底光标定位（正确区域）+ 方向键 + 翻页。

★ 关键：选关数字网格在 y≈265..340（不是上半部！上半部 y=225..251 是盘面预览）。
★ 光标 = 黄底黑字格；下层还有难度菜单（也带黄色高亮），必须限定 y 范围。
"""
import time

import numpy as np

import ds

GRID_Y0, GRID_Y1 = 265, 345


def grab():
    return np.asarray(ds.grab("").convert("RGB")).astype(int)


def cursor(im):
    R, G, B = im[:, :, 0], im[:, :, 1], im[:, :, 2]
    m = (R > 170) & (G > 150) & (B < 120) & (R - B > 70) & (G - B > 50)
    m[:GRID_Y0, :] = False
    m[GRID_Y1:, :] = False
    ys, xs = np.nonzero(m)
    if len(ys) < 20:
        return None
    return int(np.median(xs)), int(np.median(ys)), len(ys)


def to_cell(cx, cy):
    """像素 → (行, 列)，行 0..3（可见 4 行），列 0..9。"""
    col = int(round((cx - 19) / 24))
    row = int(round((cy - 278) / 16))
    return row, col


def main():
    im = grab()
    c = cursor(im)
    print("光标:", c, "→ 格", to_cell(c[0], c[1]) if c else None)
    ds.grab("nav_0")

    print("--- 方向键测试（读光标格）---")
    for key in ("Right", "Right", "Down", "Down", "Up", "Left", "Left", "Left"):
        ds.press(key, hold=0.04, wait=0.7)
        c = cursor(grab())
        print(f"  {key:6s} -> {c} 格 {to_cell(c[0], c[1]) if c else None}")

    print("--- 翻页测试：连按 Down 12 次 ---")
    for i in range(12):
        ds.press("Down", hold=0.04, wait=0.35)
    c = cursor(grab())
    print("  Down×12 -> 格", to_cell(c[0], c[1]) if c else None)
    ds.grab("nav_down12")

    print("--- 连续 Down 40 次（看能否到 100 关）---")
    for i in range(40):
        ds.press("Down", hold=0.04, wait=0.25)
    c = cursor(grab())
    print("  Down+40 -> 格", to_cell(c[0], c[1]) if c else None)
    ds.grab("nav_down52")

    print("--- 鼠标点第 50 格位（滚动后）---")
    ds.grab("nav_now")


if __name__ == "__main__":
    main()
