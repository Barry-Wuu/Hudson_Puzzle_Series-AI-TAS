#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针：选关页上屏是否显示**当前选中关的盘面预览**。
若是，则可用预览墙布局精确校验选中关卡，避免「进错关」。

用法: python3.11 probe_seg2_preview.py
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import play_akari_seg2 as P

PUZZLES = P.PUZZLES


def top_preview(im=None):
    """上屏预览板区域。"""
    if im is None:
        im = ds.grab("")
    a = np.asarray(im.convert("RGB")).astype(int)
    return a[25:185, 90:250, :]


def main():
    data = json.load(open(PUZZLES))
    seq = data["やさしい"]
    print("in_select_page:", P.in_select_page())
    # 先截一张选关页全图
    ds.grab("probe_select_full")

    # 选中第 61 关（rg=6, col=0）：滚到顶 + 下滚 2 步 → vis_row=4, col=0
    P._scroll_up_to_top()
    P._scroll_down_steps(2)
    ds.tap_local(P.COL_X0, P.ROW_Y[4], after=1.0)
    ds.grab("probe_select_clicked")
    pre = top_preview()
    # 统计颜色种类
    flat = pre.reshape(-1, 3)
    uniq, cnt = np.unique(flat, axis=0, return_counts=True)
    order = np.argsort(-cnt)[:12]
    print("预览区主要颜色:")
    for i in order:
        print("   ", tuple(uniq[i]), cnt[i])
    # 用 10x10 pitch=16 解析
    x0, y0, p = 90, 25, 16
    grid = []
    for r in range(10):
        row = ""
        for c in range(10):
            cx, cy = int(x0 + p * (c + 0.5)), int(y0 + p * (r + 0.5))
            cell = pre[cy - 5:cy + 6, cx - 5:cx + 6].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += 'W' if blue > 0.35 else '.'
        grid.append(row)
    print("预览解析:")
    for r in grid:
        print("   ", r)
    exp = P.expected_walls(seq[60])
    print("Q61 期望:")
    for r in exp:
        print("   ", r)
    m = sum(x == y for r1, r2 in zip(grid, exp) for x, y in zip(r1, r2))
    print("匹配", m, "/100")


if __name__ == "__main__":
    main()
