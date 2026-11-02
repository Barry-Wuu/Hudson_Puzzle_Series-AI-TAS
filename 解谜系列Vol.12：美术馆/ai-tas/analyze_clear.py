#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析原始片的通关面板位置（用于拼接切点）。"""
import subprocess
import sys

import numpy as np

W, H = 256, 384
path = sys.argv[1]
p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path,
                      "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                     stdout=subprocess.PIPE)
n = W * H * 3
i = 0
marks = []
while True:
    b = p.stdout.read(n)
    if len(b) < n:
        break
    a = np.frombuffer(b, np.uint8).reshape(H, W, 3).astype(int)
    seg = a[190:384].reshape(-1, 3)
    panel = ((np.abs(seg[:, 0] - 49) < 14) & (np.abs(seg[:, 1] - 82) < 14)
             & (np.abs(seg[:, 2] - 123) < 14)).sum()
    if panel > 3000:
        marks.append(i)
    i += 1
p.stdout.close()
p.wait()
print("总帧", i, "通关面板帧数", len(marks))
groups = []
cur = [marks[0]]
for x in marks[1:]:
    if x - cur[-1] <= 120:
        cur.append(x)
    else:
        groups.append(cur)
        cur = [x]
groups.append(cur)
print("通关次数:", len(groups))
for g in groups[-5:]:
    print(f"  帧 {g[0]}-{g[-1]}  t={g[0]/30:.1f}s")
