#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.12 美術館(Akari) 录像后处理（老规矩）：
  选关界面每段只留末尾 0.5s + 「セーブしています…」save 界面整段删除。

用法: python3 trim_select_save_v12.py <in.mp4> <out.mp4>

画面签名（基于 seg1 实测，60fps 源）：
  save   : 绿点底上的橙色对话框 —— 中下区 orange 像素 > 12000（实测 20666；
           盘面/通关面板最高 4065，隔离度极高）
  select : 绿点底 + 上半屏白色预览板 —— 区域 white 比例 > 0.30（实测 0.576；
           盘面仅 0.015）
  其余（盘面点灯 / クリアタイム 通关面板）原样保留。
"""
import os
import subprocess
import sys

import cv2
import numpy as np

KEEP_S = 0.5             # 选关界面保留时长
MIN_SAVE_FRAMES = 5      # save 段最短帧数（60fps 下 0.083s，save 实际 ~0.2-0.3s）
ORANGE_MIN = 12000       # save 橙框像素阈值
WHITE_MIN = 0.30         # 选关页白预览板比例阈值


def is_save(a):
    """a: RGB ndarray。save = 中下区大块橙色对话框。"""
    R = a[240:384, :, 0].astype(int)
    G = a[240:384, :, 1].astype(int)
    B = a[240:384, :, 2].astype(int)
    orange = (R > 150) & (R < 235) & (G > 55) & (G < 140) & (B < 95) & (R > B + 90)
    return int(orange.sum()) > ORANGE_MIN


def is_select(a):
    """select = 上半屏中间白预览板（白格盘面）比例高。"""
    sub = a[25:185, 90:250, :]
    R, G, B = sub[:, :, 0], sub[:, :, 1], sub[:, :, 2]
    white = (R > 195) & (G > 195) & (B > 195)
    return float(white.mean()) > WHITE_MIN


def classify(in_mp4, cache):
    if os.path.exists(cache):
        d = np.load(cache)
        return d["states"], d["saves"], float(d["fps"])
    cap = cv2.VideoCapture(in_mp4)
    fps = cap.get(cv2.CAP_PROP_FPS) or 60.0
    states, saves = [], []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        a = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
        sv = is_save(a)
        saves.append(sv)
        states.append("save" if sv else ("select" if is_select(a) else "other"))
    cap.release()
    states = np.array(states)
    saves = np.array(saves, dtype=bool)
    np.savez(cache, states=states, saves=saves, fps=fps)
    return states, saves, fps


def runs_of(mask):
    out, k, n = [], 0, len(mask)
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
    cache = in_mp4 + ".states_v12.npz"
    states, saves, fps = classify(in_mp4, cache)
    n = len(states)
    sel_runs = runs_of(states == "select")
    save_runs = [r for r in runs_of(saves) if r[1] - r[0] + 1 >= MIN_SAVE_FRAMES]
    save_t = sum(e - s + 1 for s, e in save_runs) / fps
    sel_t = sum(e - s + 1 for s, e in sel_runs) / fps
    print(f"frames={n} fps={fps:.1f}  时长={n/fps:.2f}s")
    print(f"select 段={len(sel_runs)} 合计{sel_t:.2f}s（每段留末尾{KEEP_S}s）")
    print(f"save   段={len(save_runs)} 合计{save_t:.2f}s（整段删除）")

    keep = []
    prev = 0

    def flush(a, b):
        if b < a:
            return
        cur = a
        for s, e in sel_runs:
            if e < a or s > b:
                continue
            s2, e2 = max(s, a), min(e, b)
            if s2 - 1 >= cur:
                keep.append((cur, s2 - 1))
            w = int(round(KEEP_S * fps))
            keep.append((e2 - w + 1, e2) if e2 - s2 + 1 > w else (s2, e2))
            cur = e2 + 1
        if b >= cur:
            keep.append((cur, b))

    for s, e in save_runs:
        if s - 1 >= prev:
            flush(prev, s - 1)
        prev = e + 1
    if n - 1 >= prev:
        flush(prev, n - 1)

    merged = []
    for seg in keep:
        if merged and seg[0] == merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], seg[1])
        else:
            merged.append(seg)
    dur = sum(b - a + 1 for a, b in merged) / fps
    print(f"keep 段={len(merged)} 输出≈{dur:.2f}s ({dur/60:.2f} min)")

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
        "-c:v", "libopenh264", "-b:v", "3000k", "-pix_fmt", "yuv420p", "-r", "60",
        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out_mp4,
    ])
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
