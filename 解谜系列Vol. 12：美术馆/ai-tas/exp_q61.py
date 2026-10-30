#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""实验：进 Q61，抓多帧 + 真实盘面尺寸检测（自动找板面左右边界）。"""
import json
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import play_akari_seg2 as P


def analyze(name):
    im = Image.open(f"/root/.codebuddy/artifact/vol12/{name}.png").convert("RGB")
    a = np.asarray(im).astype(int)
    print(f"-- {name} --")
    # 下屏 y>=192，找非背景行范围
    low = a[192:, :, :]
    # 盘面区域：找白格（>190）横向范围
    for label, y in (("上屏", 0), ("下屏", 192)):
        band = a[y:y + 192, :, :]
        white = (band[:, :, 0] > 190) & (band[:, :, 1] > 190) & (band[:, :, 2] > 190)
        colcnt = white.sum(axis=0)
        nz = np.nonzero(colcnt > 3)[0]
        print(f"  {label} 白色列范围: {nz.min() if len(nz) else '-'}..{nz.max() if len(nz) else '-'}")
        rowcnt = white.sum(axis=1)
        nzr = np.nonzero(rowcnt > 3)[0]
        print(f"  {label} 白色行范围: {nzr.min() if len(nzr) else '-'}..{nzr.max() if len(nzr) else '-'}")
    return a


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 61
    print("in_select_page:", P.in_select_page())
    P._scroll_up_to_top()
    rg = (n - 1) // 10
    P._scroll_down_steps(max(0, rg - 4))
    vis_row = rg if rg <= 4 else 4
    col = (n - 1) % 10
    ds.tap_local(P.COL_X0 + P.COL_DX * col, P.ROW_Y[vis_row], after=1.0)
    ds.grab(f"x{n}_selected")
    ds.press("x", wait=1.5)
    for i in range(6):
        ds.grab(f"x{n}_t{i}")
        time.sleep(0.8)
    for i in range(6):
        analyze(f"x{n}_t{i}")


main()
