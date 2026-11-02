#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针 6：查清「ルール」页与 puzzles.json 编号的对应关系。

做法：进选关页 → 滚到 Q51 → 截图看选关网格/预览，
再用**预览板**判断当前选中关的实际盘面尺寸与形状。
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import play_akari_seg2 as P


def main():
    print("select:", P.in_select_page())
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 51
    rg = (n - 1) // 10
    col = (n - 1) % 10
    P._scroll_up_to_top()
    if rg > 4:
        P._scroll_down_steps(rg - 4)
        vis = 4
    else:
        vis = rg
    ds.tap_local(P.COL_X0 + P.COL_DX * col, P.ROW_Y[vis], after=1.2)
    ds.grab(f"sel_{n}")
    # 上屏预览板尺寸：找白底区域
    im = ds.grab("")
    a = np.asarray(im.convert("RGB")).astype(int)
    up = a[:192]
    white = (up[:, :, 0] > 190) & (up[:, :, 1] > 190) & (up[:, :, 2] > 190)
    rows = white.sum(axis=1)
    cols = white.sum(axis=0)
    nz = np.nonzero(rows > 20)[0]
    nzc = np.nonzero(cols > 20)[0]
    print(f"预览白区 行 {nz.min()}..{nz.max()} 列 {nzc.min()}..{nzc.max()}")
    # 标题栏
    print("标题栏左上像素:", a[10, 10], "右上:", a[10, 240])


main()
