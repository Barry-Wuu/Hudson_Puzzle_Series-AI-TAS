#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""18x10 画线核查器：以「净盘 vs 当前盘」像素差判定某条边是否画出。

不依赖主题色（RANDOM 每关换色，红线判据会失效），只比较同一条边中段
在净盘截图与当前截图上的差异——画上线的位置必然变亮/变色。
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds          # noqa: E402
import record18 as r18   # noqa: E402

PJ = os.path.join(os.path.dirname(HERE), "validation", "puzzles.json")


def bot_rgb():
    return np.asarray(ds.grab(None).convert("RGB").crop((0, 192, 256, 384))).astype(int)


def cap_view(view, cur):
    cur = r18.toggle_to(view, cur)
    return bot_rgb(), cur


def edges_of(idx):
    data = json.load(open(PJ, encoding="utf-8"))
    p = next(x for x in data if x["idx"] == idx)
    return [("h", r, c) for (r, c) in p["edges_h"]] + [("v", r, c) for (r, c) in p["edges_v"]]


def _sample(img, x1, y1, x2, y2):
    """沿边中段取样（去掉两端 4px，避开顶点圆点）。"""
    L = max(abs(x2 - x1), abs(y2 - y1))
    pts = []
    for t in range(4, L - 3):
        x = int(round(x1 + (x2 - x1) * t / L))
        y = int(round(y1 + (y2 - y1) * t / L))
        if 0 <= x < 256 and 0 <= y < 192:
            pts.append((x, y))
    return pts


def edge_scores(base, cur, idx, view):
    """返回 {(kind,r,c): 平均像素差}，只看该 view 可见的边。"""
    off = -r18.SHIFT_B if view == "B" else 0
    out = {}
    for (k, r, c) in edges_of(idx):
        if r18.edge_view(k, r, c) != view:
            continue
        x1, y1, x2, y2 = r18.edge_px(k, r, c)
        pts = _sample(base, x1 + off, y1, x2 + off, y2)
        if not pts:
            out[(k, r, c)] = 0.0
            continue
        d = 0.0
        for (x, y) in pts:
            d += abs(base[y, x] - cur[y, x]).sum()
        out[(k, r, c)] = d / len(pts)
    return out


def report(idx, baseA, baseB, cur):
    """打印各 view 的差值分布，用于标定阈值。"""
    rows = []
    for view, base in (("A", baseA), ("B", baseB)):
        cur_v, cur = cap_view(view, cur)
        s = edge_scores(base, cur_v, idx, view)
        vals = sorted(s.values())
        rows.append((view, vals, s))
        print(f"[{view}] n={len(vals)} min={vals[0]:.1f} p50={vals[len(vals)//2]:.1f} "
              f"max={vals[-1]:.1f}", flush=True)
        print("   最低 8 条:", [(k, round(v, 1)) for k, v in
                            sorted(s.items(), key=lambda kv: kv[1])[:8]], flush=True)
    return rows, cur


if __name__ == "__main__":
    print("仅作为库使用；见 diag94.py")
