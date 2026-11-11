#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""18x10 档（やさしい93~100）两段式画环：View A(列0~14) + View B(列15~18, x-55)。

几何（实机标定）：x0=11 y0=6 pitch=16；横向滚动为两档 toggle，位移 55px。
View A 显示顶点列 0~15（x 11..251）；View B 显示列 3~18（x 11+16c-55）。
环单环顶点列 0..18，故按边拆分：边两端 max(col)>=15 归 View B，否则 View A。
"""
import json, os, sys, time
import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds, record_levels as rl

X0, Y0, P = 11, 6, 16
SHIFT_B = 55           # A->B 内容左移 55px
PJ = os.path.join(os.path.dirname(HERE), "validation", "puzzles.json")


def loop_path(idx):
    data = json.load(open(PJ, encoding="utf-8"))
    p = next(x for x in data if x["idx"] == idx)
    adj = {}
    for (r, c) in p["edges_h"]:
        a, b = (r, c), (r, c + 1)
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    for (r, c) in p["edges_v"]:
        a, b = (r, c), (r + 1, c)
        adj.setdefault(a, []).append(b); adj.setdefault(b, []).append(a)
    assert all(len(v) == 2 for v in adj.values()), "非单环"
    s = next(iter(adj)); path = [s]; cur = s; used = set()
    while True:
        nxt = None
        for nb in adj[cur]:
            k = tuple(sorted([cur, nb]))
            if k not in used:
                nxt = nb; used.add(k); break
        if nxt is None or nxt == s:
            break
        path.append(nxt); cur = nxt
        if len(path) > len(adj) + 2:
            break
    assert len(path) == len(used), "未闭合"
    return path   # list of (r,c)


def board():
    return ds.grab(None).convert("RGB").crop((0, 192, 256, 384))


def redx(im):
    """只在左右极窄边条找红色滑块（避免把盘面红色线误判）。仅开局净盘时用。"""
    a = np.asarray(im).astype(int); R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    red = (R > 150) & (G < 90) & (B < 90)
    mask = np.zeros_like(red)
    mask[60:135, 0:11] = True       # 左滑块
    mask[60:135, 245:256] = True    # 右滑块
    red = red & mask
    ys, xs = np.where(red)
    return int(xs.mean()) if len(xs) else None


# 滚档坐标（实机标定）：A=红在右缘，B=红在左缘
TAP_TO_B = (250, 86)   # 当前 A，点右侧滑块 -> B
TAP_TO_A = (4, 86)     # 当前 B，点左侧滑块 -> A


def toggle_to(view, cur):
    """按当前档确定地点滑块切到目标档（不依赖检测，避免被盘面红线干扰）。"""
    if view == cur:
        return cur
    xy = TAP_TO_B if view == "B" else TAP_TO_A
    rl.ds.tap(xy[0], xy[1], hold=0.18, after=0.9)
    return view


def ensure_view(want):
    """仅开局净盘时调用：检测红滑块在左还是右，决定当前档并切到 want。"""
    rx = redx(board())
    cur = "A" if (rx is None or rx >= 128) else "B"
    return toggle_to(want, cur)


def drag(points, step=8, gap=0.016, turn=0.015, head=0.14, down=0.10, tail=0.10, settle=0.25):
    x0, y0 = points[0]
    cmd = ["xdotool", "mousemove", str(ds.WIN_X + x0), str(ds.WIN_Y + 192 + y0),
           "sleep", str(head), "mousedown", "1", "sleep", str(down)]
    seq = list(points)
    for (xa, ya), (xb, yb) in zip(seq, seq[1:]):
        L = max(abs(xb - xa), abs(yb - ya))
        if L:
            for i in range(step, L + 1, step):
                xx = int(round(xa + (xb - xa) * i / L)); yy = int(round(ya + (yb - ya) * i / L))
                cmd += ["mousemove", str(ds.WIN_X + xx), str(ds.WIN_Y + 192 + yy), "sleep", str(gap)]
        cmd += ["mousemove", str(ds.WIN_X + xb), str(ds.WIN_Y + 192 + yb), "sleep", str(turn)]
    cmd += ["sleep", str(tail), "mouseup", "1"]
    import subprocess
    subprocess.run(cmd, env=ds.ENV)
    time.sleep(settle)


def vxy(v, view):
    """顶点(r,c) -> 窗口内下屏像素(x,y)。view='A' 原坐标；'B' x-55。"""
    r, c = v
    x = X0 + P * c - (SHIFT_B if view == "B" else 0)
    y = Y0 + P * r
    return (x, y)


def _reddish(img, x, y):
    if x < 0 or x > 255 or y < 0 or y > 191:
        return False
    r, g, b = img[y, x, 0], img[y, x, 1], img[y, x, 2]
    return (r > 140) and (r > g + 45) and (r > b + 45)


def _edge_frac(img, x1, y1, x2, y2):
    steps = max(abs(x2 - x1), abs(y2 - y1))
    n = t = 0
    for k in range(2, steps - 1):
        x = int(round(x1 + (x2 - x1) * k / steps))
        y = int(round(y1 + (y2 - y1) * k / steps))
        t += 1
        if any(_reddish(img, x + dx, y + dy) for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1))):
            n += 1
    return n / max(t, 1)


def edge_view(kind, r, c):
    if kind == "h":
        return "B" if max(c, c + 1) >= 15 else "A"
    return "B" if c >= 15 else "A"


def edge_px(kind, r, c):
    if kind == "h":
        return (X0 + P * c, Y0 + P * r, X0 + P * (c + 1), Y0 + P * r)
    return (X0 + P * c, Y0 + P * r, X0 + P * c, Y0 + P * (r + 1))


def expected_edges(idx):
    data = json.load(open(PJ, encoding="utf-8"))
    p = next(x for x in data if x["idx"] == idx)
    e = [("h", r, c) for (r, c) in p["edges_h"]] + [("v", r, c) for (r, c) in p["edges_v"]]
    return e


def scan_missing(idx, cur):
    """返回缺失边列表（按各自 view 扫描）。cur 为当前 A/B 档，函数内会切档，返回后档位为 B。"""
    miss = []
    for view in ("A", "B"):
        cur = toggle_to(view, cur)
        img = np.asarray(board()).astype(int)
        off = -SHIFT_B if view == "B" else 0
        for (k, r, c) in expected_edges(idx):
            if edge_view(k, r, c) != view:
                continue
            x1, y1, x2, y2 = edge_px(k, r, c)
            if _edge_frac(img, x1 + off, y1, x2 + off, y2) < 0.6:
                miss.append((k, r, c))
    return miss, cur


def draw_edge(kind, r, c, view):
    x1, y1, x2, y2 = edge_px(kind, r, c)
    off = -SHIFT_B if view == "B" else 0
    drag([(x1 + off, y1), (x2 + off, y2)], step=4, gap=0.02, settle=0.10)


def draw_all_edges(idx, verbose=True):
    """逐条边单独绘制（最稳健，避免长笔画插值丢边）。先画全部 A 边再切 B 边。"""
    cur = ensure_view("A")
    edges = expected_edges(idx)
    if verbose:
        na = sum(1 for e in edges if edge_view(*e) == "A")
        nb = len(edges) - na
        print("edges", len(edges), "A", na, "B", nb, flush=True)
    for (k, r, c) in edges:
        if edge_view(k, r, c) == "A":
            draw_edge(k, r, c, "A")
    cur = toggle_to("B", cur)
    for (k, r, c) in edges:
        if edge_view(k, r, c) == "B":
            draw_edge(k, r, c, "B")
    return cur



def draw_loop(idx, verbose=True):
    path = loop_path(idx)
    n = len(path)

    def eview(i):
        return edge_view("h", path[i][0], path[i][1]) if False else (
            "B" if max(path[i][1], path[(i + 1) % n][1]) >= 15 else "A")
    views = [eview(i) for i in range(n)]
    start = 0
    for i in range(n):
        if views[i] != views[(i + 1) % n]:
            start = (i + 1) % n
            break
    order = [(start + k) % n for k in range(n)]
    strokes = []
    cur_view = None; cur_vs = None
    for i in order:
        v = views[i]
        if v != cur_view:
            if cur_vs:
                strokes.append((cur_view, cur_vs))
            cur_view = v; cur_vs = [path[i]]
        cur_vs.append(path[(i + 1) % n])
    if cur_vs:
        strokes.append((cur_view, cur_vs))
    if verbose:
        print("loop verts", n, "strokes", [(s[0], len(s[1])) for s in strokes], flush=True)
    cur = ensure_view("A")
    for view, vs in strokes:
        cur = toggle_to(view, cur)
        drag([vxy(v, view) for v in vs])
    return cur, len(strokes)


def draw_verified(idx, max_iter=6, verbose=True):
    """画环 + 自动补缺边，直到 Completion 或无进展。"""
    cur, k = draw_loop(idx, verbose)
    for it in range(max_iter):
        time.sleep(0.6)
        if rl.state() == "completion":
            if verbose: print("完成于初次绘制", flush=True)
            return True
        miss, cur = scan_missing(idx, cur)
        if verbose:
            print("iter", it, "missing", len(miss), miss[:8], flush=True)
        if not miss:
            break
        for (kd, r, c) in miss:
            view = edge_view(kd, r, c)
            cur = toggle_to(view, cur)
            draw_edge(kd, r, c, view)
    time.sleep(0.5)
    return rl.state() == "completion"



if __name__ == "__main__":
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 1515
    ok = draw_verified(idx)
    print("verified complete:", ok, "state", rl.state(), flush=True)
