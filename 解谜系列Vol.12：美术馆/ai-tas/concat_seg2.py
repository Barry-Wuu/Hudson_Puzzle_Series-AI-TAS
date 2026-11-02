#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把三段原始片拼成完整 seg2：
  p1 = Q1..Q40（整段）
  p2 = Q41..Q60（**截掉末尾失败的 Q61**）
  p3 = Q54..Q80（整段）

注意 p2/p3 有 3 关重叠（Q54..Q60），拼接时 p3 从对应位置切掉重叠部分。
做法：用「通关面板出现次数」定位。p2 恰好 20 次通关（Q41..Q60），
      p3 的前 7 次通关对应 Q54..Q60 ⇒ 从第 7 次通关结束处开始切。
"""
import subprocess
import sys

import numpy as np

W, H = 256, 384


def clear_frames(path):
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
    groups = []
    cur = [marks[0]]
    for x in marks[1:]:
        if x - cur[-1] <= 120:
            cur.append(x)
        else:
            groups.append(cur)
            cur = [x]
    groups.append(cur)
    return i, groups


def main():
    p1 = sys.argv[1]
    p2 = sys.argv[2]
    p3 = sys.argv[3]
    out = sys.argv[4]
    for f in (p1, p2, p3):
        n, g = clear_frames(f)
        print(f"{f}: {n} 帧, {len(g)} 次通关")
        if f == p2:
            cut_p2 = g[-1][-1] + 1
            print(f"   p2 截断帧 = {cut_p2} (t={cut_p2/30:.1f}s)")
        if f == p3:
            # p3 前 7 次通关 = Q54..Q60（与 p2 重叠）⇒ 从第 7 次结束处切
            cut_p3 = g[6][-1] + 1
            print(f"   p3 去重叠起始帧 = {cut_p3} (t={cut_p3/30:.1f}s)")
    parts = []
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", p1, "-c", "copy",
                    "-f", "mpegts", "/tmp/_c1.ts"], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", p2, "-c", "copy",
                    "-frames:v", str(cut_p2), "-f", "mpegts", "/tmp/_c2.ts"], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(cut_p3 / 30.0), "-i", p3,
                    "-c", "copy", "-f", "mpegts", "/tmp/_c3.ts"], check=True)
    with open("/tmp/_cat.txt", "w") as f:
        for p in ("/tmp/_c1.ts", "/tmp/_c2.ts", "/tmp/_c3.ts"):
            f.write(f"file '{p}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
                    "-i", "/tmp/_cat.txt", "-c", "copy", "-movflags", "+faststart", out],
                   check=True)
    print("输出:", out)


main()
