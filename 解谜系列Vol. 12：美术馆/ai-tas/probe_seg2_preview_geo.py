#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针：标定选关页上屏**预览板**几何（10×10 网格），用于精确校验选中关卡。"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import play_akari_seg2 as P

def main():
    im = Image.open("/root/.codebuddy/artifact/vol12/probe_select_clicked.png").convert("RGB")
    a = np.asarray(im).astype(int)
    white = (a[:, :, 0] > 190) & (a[:, :, 1] > 190) & (a[:, :, 2] > 190)
    # 上屏区域 y<192
    up = white[:192, :]
    ys, xs = np.nonzero(up)
    print("上屏白色 bbox x", xs.min(), xs.max(), "y", ys.min(), ys.max())
    # 每行白像素量，找板上下边界
    rows = up.sum(axis=1)
    for y in range(0, 192, 4):
        print(y, rows[y])

main()
