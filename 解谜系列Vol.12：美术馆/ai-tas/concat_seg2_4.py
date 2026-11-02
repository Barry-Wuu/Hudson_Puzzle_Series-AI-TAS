#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拼接 seg2 四段原始片（各段切到最后一次通关面板结束处）：
  p1  = Q1..Q40   p2 = Q41..Q60   p4b = Q61..Q63   p4 = Q64..Q80
用法: python3.11 concat_seg2_4.py out.mp4 p1.mp4 p2.mp4 p4b.mp4 p4.mp4
"""
import subprocess
import sys

import numpy as np

W, H = 256, 384


def clear_groups(path):
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
    groups, cur = [], [marks[0]]
    for x in marks[1:]:
        if x - cur[-1] <= 120:
            cur.append(x)
        else:
            groups.append(cur)
            cur = [x]
    groups.append(cur)
    return i, groups


def main():
    out, files = sys.argv[1], sys.argv[2:]
    parts = []
    for k, f in enumerate(files):
        n, g = clear_groups(f)
        cut = g[-1][-1] + 1
        print(f"{f}: {n}帧 {len(g)}次通关 -> 截到 {cut} (t={cut/30:.1f}s)")
        ts = f"/tmp/_seg2_{k}.ts"
        if k == 0:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f, "-c", "copy",
                            "-frames:v", str(cut), "-f", "mpegts", ts], check=True)
        else:
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", f, "-c", "copy",
                            "-frames:v", str(cut), "-f", "mpegts", ts], check=True)
        parts.append(ts)
    with open("/tmp/_cat4.txt", "w") as fh:
        for p in parts:
            fh.write(f"file '{p}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", "/tmp/_cat4.txt", "-c", "copy", "-movflags", "+faststart", out],
                   check=True)
    print("输出:", out)


main()
