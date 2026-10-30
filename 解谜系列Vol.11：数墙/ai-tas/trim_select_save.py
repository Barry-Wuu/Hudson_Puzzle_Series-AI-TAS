#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数墙录像后处理：选关界面只留末尾 0.5s + 「セーブしています…」save 界面整段删除。

用法: python3 trim_select_save.py <in.mp4> <out.mp4>
  - 逐帧分类（state2.select 签名 + save 专属签名），缓存 states 到 <in>.states.npy
  - save 界面 = 下屏大块橙色对话框 + 上半屏蓝花纹底（区别于暂停菜单上的确认框：
    那个有青色横条与灰底，蓝底条件不满足）
  - select 段 -> 保留末尾 0.5s；save 段(>=5帧) -> 整段删除；其余原样
"""
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import state2  # noqa: E402

FPS = 30.0
KEEP_S = 0.5
MIN_SAVE_FRAMES = 5

# save 对话框签名阈值（基于 seg2/seg3 实测：save 橙盒 ~25000px/蓝底~80%，
# 暂停菜单确认框蓝底不达标）
ORANGE_MIN = 15000
BLUE_RATIO = 0.60


def is_save_screen(a):
    """a: RGB uint8/uint16 ndarray (384,256,3)。判定是否「セーブしています…」界面。"""
    R = a[220:360, 10:245, 0].astype(int)
    G = a[220:360, 10:245, 1].astype(int)
    B = a[220:360, 10:245, 2].astype(int)
    orange = (R > 150) & (R < 240) & (G > 60) & (G < 150) & (B < 90) & (R > B + 80)
    if int(orange.sum()) < ORANGE_MIN:
        return False
    Rb = a[0:200, :, 0].astype(int)
    Gb = a[0:200, :, 1].astype(int)
    Bb = a[0:200, :, 2].astype(int)
    blue = (Bb > Rb + 30) & (Bb > 140) & (Bb < 235) & (Gb > Rb)
    return float(blue.mean()) > BLUE_RATIO


def classify(in_mp4, cache):
    if os.path.exists(cache):
        return np.load(cache)
    cap = cv2.VideoCapture(in_mp4)
    fps = cap.get(cv2.CAP_PROP_FPS) or FPS
    recs = []  # (state, is_save)
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        im = Image.fromarray(cv2.cvtColor(fr, cv2.COLOR_BGR2RGB))
        a = np.asarray(im)
        recs.append((state2.detect(im), is_save_screen(a)))
    cap.release()
    states = np.array([r[0] for r in recs])
    saves = np.array([r[1] for r in recs], dtype=bool)
    np.savez(cache, states=states, saves=saves, fps=fps)
    return states, saves, fps


def runs_of(mask):
    out = []
    k, n = 0, len(mask)
    while k < n:
        if mask[k]:
            s = k
            while k < n and mask[k]:
                k += 1
            out.append((s, k - 1))
        else:
            k += 1
    return out


def main():
    in_mp4, out_mp4 = sys.argv[1], sys.argv[2]
    cache = in_mp4 + ".states.npz"
    states, saves, fps = classify(in_mp4, cache)
    n = len(states)
    sel_runs = runs_of(states == "select")
    save_runs = [r for r in runs_of(saves) if r[1] - r[0] + 1 >= MIN_SAVE_FRAMES]
    save_set = set()
    for s, e in save_runs:
        save_set.update(range(s, e + 1))
    save_t = sum(e - s + 1 for s, e in save_runs) / fps
    print(f"frames={n} select_runs={len(sel_runs)} save_runs={len(save_runs)} "
          f"save_total={save_t:.1f}s")

    # keep 段列表（闭区间帧号）：save 删除；select 只留末尾 0.5s；其余保留
    keep = []
    prev = 0  # 上一处理点（不含）

    def flush_nonselect_block(a, b):
        """帧 [a,b] 内无 save：把其中 select 段裁到末尾 0.5s。"""
        if b < a:
            return
        # 找该块内的 select 段（限制在块内）
        cur = a
        for s, e in sel_runs:
            if e < a or s > b:
                continue
            s2, e2 = max(s, a), min(e, b)
            if s2 - 1 >= cur:
                keep.append((cur, s2 - 1))
            w = int(round(KEEP_S * fps))
            if e2 - s2 + 1 > w:
                keep.append((e2 - w + 1, e2))
            else:
                keep.append((s2, e2))
            cur = e2 + 1
        if b >= cur:
            keep.append((cur, b))

    for s, e in save_runs:
        if s - 1 >= prev:
            flush_nonselect_block(prev, s - 1)
        prev = e + 1
    if n - 1 >= prev:
        flush_nonselect_block(prev, n - 1)

    merged = []
    for seg in keep:
        if merged and seg[0] == merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], seg[1])
        else:
            merged.append(seg)
    dur = sum(b - a + 1 for a, b in merged) / fps
    print(f"keep segments={len(merged)} output≈{dur:.1f}s ({dur/60:.2f} min)")

    parts_v, parts_a, cin = [], [], []
    for i, (a, b) in enumerate(merged):
        s, e = a / fps, (b + 1) / fps
        parts_v.append(f"[0:v]trim=start={s:.6f}:end={e:.6f},setpts=PTS-STARTPTS[v{i}]")
        parts_a.append(f"[0:a]atrim=start={s:.6f}:end={e:.6f},asetpts=PTS-STARTPTS[a{i}]")
        cin.append(f"[v{i}][a{i}]")
    flt = ";\n".join(parts_v + parts_a) + ";\n" + "".join(cin) + \
        f"concat=n={len(merged)}:v=1:a=1[vout][aout]\n"
    fpath = out_mp4 + ".filter.txt"
    with open(fpath, "w") as f:
        f.write(flt)

    r = subprocess.run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
        "-i", in_mp4, "-filter_complex_script", fpath,
        "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libopenh264", "-b:v", "3000k", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_mp4,
    ])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
