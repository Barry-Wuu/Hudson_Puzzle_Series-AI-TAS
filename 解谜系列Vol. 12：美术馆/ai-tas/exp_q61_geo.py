#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提取实际 Q61 盘面墙布局，与 puzzles.json 对比（找编号/几何错位）。"""
import json
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import play_akari_seg2 as P

a = np.asarray(Image.open("/root/.codebuddy/artifact/vol12/x61_t0.png").convert("RGB")).astype(int)

# 自动找盘面边界：下屏 y>=192，找蓝色(墙/数字)像素的包围盒
low = a[192:, :, :]
blue = (low[:, :, 2] > 100) & (low[:, :, 2] > low[:, :, 0] + 35)
ys, xs = np.nonzero(blue)
print("蓝色像素 bbox x", xs.min(), xs.max(), "y", ys.min() + 192, ys.max() + 192)

# 打印列方向蓝色密度，找网格线
colc = blue.sum(axis=0)
print("列密度:", "".join(str(min(c, 9)) for c in colc))
rowc = blue.sum(axis=1)
print("行密度:", "".join(str(min(c, 9)) for c in rowc))
