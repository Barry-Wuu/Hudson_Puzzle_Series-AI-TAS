#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seg2 成片验收：卡顿检测 / save 残留 / select 段帧数 / 音量。

用法: python3.11 verify_seg2.py <in.mp4>
"""
import subprocess
import sys

import numpy as np

IN = sys.argv[1]
W, H, FR = 256, 384, 30


def read_frames(path):
    """流式读帧，避免 OOM。"""
    p = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        stdout=subprocess.PIPE)
    n = W * H * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        yield np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    p.stdout.close()
    p.wait()


def main():
    frames = read_frames(IN)
    n = 0
    diffs = []
    orange_cnt = []
    white_cnt = []
    prev = None
    for a in frames:
        n += 1
        if prev is not None:
            diffs.append(float(np.abs(a.astype(np.int16) - prev.astype(np.int16)).mean()))
        prev = a
        # save 橙框检测（中下区）
        seg = a[240:384, :, :].astype(int)
        orange = ((seg[:, :, 0] > 150) & (seg[:, :, 0] < 235) & (seg[:, :, 1] > 55)
                  & (seg[:, :, 1] < 140) & (seg[:, :, 2] < 95)
                  & (seg[:, :, 0] > seg[:, :, 2] + 90))
        orange_cnt.append(int(orange.sum()))
        # select 页白预览板
        sub = a[25:185, 90:250, :].astype(int)
        white = (sub[:, :, 0] > 195) & (sub[:, :, 1] > 195) & (sub[:, :, 2] > 195)
        white_cnt.append(float(white.mean()))
    print(f"总帧数 {n}  时长 {n/FR:.2f}s")

    d = np.array(diffs)
    # 动画段：相邻帧差 > 2（明显变化）
    anim = d > 2
    print(f"动画帧数 {int(anim.sum())}")
    if anim.sum():
        # 动画段内部卡顿：某帧差 <0.5 且前后都动
        idx = np.nonzero(anim)[0]
        still_in_anim = 0
        for i in idx:
            if i < len(d) and d[i] < 0.5:
                still_in_anim += 1
        print(f"动画段内静止帧 {still_in_anim} ({100*still_in_anim/anim.sum():.2f}%)")
    # select 段（白预览板 > 0.30）连续段帧数
    w = np.array(white_cnt) > 0.30
    runs = []
    k = 0
    while k < len(w):
        if w[k]:
            j = k
            while j + 1 < len(w) and w[j + 1]:
                j += 1
            runs.append((k, j - k + 1))
            k = j + 1
        else:
            k += 1
    if runs:
        lens = [r[1] for r in runs]
        print(f"select 段数 {len(runs)}  帧长 min={min(lens)} max={max(lens)} 分布={sorted(set(lens))[:10]}")
    else:
        print("select 段数 0")
    # save 段
    o = np.array(orange_cnt) > 12000
    oruns = 0
    k = 0
    while k < len(o):
        if o[k]:
            j = k
            while j + 1 < len(o) and o[j + 1]:
                j += 1
            oruns += 1
            k = j + 1
        else:
            k += 1
    print(f"save 橙框段数 {oruns}  残留帧 {int(o.sum())}")


main()
