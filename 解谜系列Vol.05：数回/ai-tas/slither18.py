#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""18x10 档（やさしい 93~100）录制核心：显式视口管理 + 净盘像素差核查 + 补边。

与 record18.py 的区别（record18 的 redx 会被盘面红线/主题色干扰，导致档位错判）：
  * view 判据：只在左右极窄条里找「实心红竖条」（连续 >=40px），画出的细线过不了阈值；
  * 每次切档后重新判定，不看历史假设；
  * 用「净盘截图 vs 当前截图」的同位置像素差判断某条边是否画上（与 RANDOM 主题色无关）；
  * 缺边自动补画（最多 3 轮），补完才点 チェック。
"""
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds                      # noqa: E402
import record18 as r18         # noqa: E402

PJ = os.path.join(os.path.dirname(HERE), "validation", "puzzles.json")
X0, Y0, P = 11, 6, 16
SHIFT_B = 55
SLIDER_Y = (60, 136)
TAP_RIGHT = (250, 86)
TAP_LEFT = (4, 86)


def bot_rgb():
    return np.asarray(ds.grab(None).convert("RGB").crop((0, 192, 256, 384))).astype(int)


def pink_ratio(a):
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    m = (R > 215) & (B > 120) & (G < R - 55)
    return m.sum() / (256 * 192)


def is_select_ui(a=None):
    a = bot_rgb() if a is None else a
    return pink_ratio(a) > 0.08


def slider_side(a=None):
    """返回 'L' / 'R' / None：实心红竖条在哪一侧。"""
    a = bot_rgb() if a is None else a
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    red = (R > 150) & (G < 110) & (B < 110)
    y0, y1 = SLIDER_Y
    left = int(red[y0:y1, 0:12].sum(axis=0).max()) if red[y0:y1, 0:12].size else 0
    right = int(red[y0:y1, 244:256].sum(axis=0).max()) if red[y0:y1, 244:256].size else 0
    if max(left, right) < 12:
        return None
    return "L" if left > right else "R"


def view_now():
    """R=右缘滑块=A 档（显示顶点列 0~15）；L=左缘滑块=B 档（列 3~18）。"""
    s = slider_side()
    return {"R": "A", "L": "B"}.get(s)


def set_view(want, tries=4, verbose=False):
    for _ in range(tries):
        cur = view_now()
        if cur == want:
            return want
        ds.tap(*(TAP_RIGHT if want == "B" else TAP_LEFT), hold=0.18, after=0.9)
        if verbose:
            print("  set_view", want, "prev", cur, "->", view_now(), flush=True)
    return view_now()


def cap(view):
    set_view(view)
    return bot_rgb()


def edges_of(idx):
    data = json.load(open(PJ, encoding="utf-8"))
    p = next(x for x in data if x["idx"] == idx)
    return ([("h", r, c) for (r, c) in p["edges_h"]] +
            [("v", r, c) for (r, c) in p["edges_v"]])


def edge_px(kind, r, c):
    if kind == "h":
        return (X0 + P * c, Y0 + P * r, X0 + P * (c + 1), Y0 + P * r)
    return (X0 + P * c, Y0 + P * r, X0 + P * c, Y0 + P * (r + 1))


def view_of_edge(kind, r, c):
    return "B" if (max(c, c + 1) if kind == "h" else c) >= 15 else "A"


def score_edges(base, cur, idx, view):
    off = -SHIFT_B if view == "B" else 0
    out = {}
    for (k, r, c) in edges_of(idx):
        if view_of_edge(k, r, c) != view:
            continue
        x1, y1, x2, y2 = edge_px(k, r, c)
        x1 += off; x2 += off
        L = max(abs(x2 - x1), abs(y2 - y1))
        tot = n = 0
        for t in range(4, L - 3):
            x = int(round(x1 + (x2 - x1) * t / L))
            y = int(round(y1 + (y2 - y1) * t / L))
            if 0 <= x < 256 and 0 <= y < 192:
                tot += abs(base[y, x] - cur[y, x]).sum()
                n += 1
        out[(k, r, c)] = tot / max(n, 1)
    return out


def draw_line(kind, r, c, view):
    x1, y1, x2, y2 = edge_px(kind, r, c)
    off = -SHIFT_B if view == "B" else 0
    r18.drag([(x1 + off, y1), (x2 + off, y2)], step=4, gap=0.02,
             head=0.12, down=0.10, tail=0.10, settle=0.12)


# ---------- 视口管理（不依赖颜色，只依赖「画面确实变了」与「单元格对齐」）----------
def shot():
    return bot_rgb()


def toggle(cur, tries=4, after=0.9):
    """按当前档点对应侧的滑条，并用「画面是否变化」确认切换成功。"""
    for _ in range(tries):
        before = shot()
        xy = TAP_RIGHT if cur == "A" else TAP_LEFT
        ds.tap(xy[0], xy[1], hold=0.18, after=after)
        after_img = shot()
        if abs(after_img - before).mean() > 4:
            return ("B" if cur == "A" else "A"), True
    return cur, False


def align_err(base, cur_img, view):
    """单元格中心 5x5 的平均像素差：同档≈0，错档明显大（不受画线影响）。"""
    off = -SHIFT_B if view == "B" else 0
    tot = n = 0
    for r in range(10):
        for c in range(18):
            x = X0 + P * c + 8 + off
            y = Y0 + P * r + 8
            if 4 <= x < 251 and 4 <= y < 187:
                tot += abs(base[y - 2:y + 3, x - 2:x + 3] - cur_img[y - 2:y + 3, x - 2:x + 3]).sum()
                n += 1
    return tot / max(n, 1)


def which_view(cur_img, base):
    ea = align_err(base["A"], cur_img, "A")
    eb = align_err(base["B"], cur_img, "B")
    return ("A" if ea < eb else "B"), ea, eb


def go(view, cur, base=None, tries=4):
    """切到指定档；给 base 时用单元格对齐度做二次确认。"""
    for _ in range(tries):
        if cur == view:
            if base is None:
                return cur, True
            got, ea, eb = which_view(shot(), base)
            if got == view:
                return cur, True
            cur = got                       # 记录与实际不符，纠正后继续
            continue
        cur, ok = toggle(cur)
        if not ok:
            return cur, False
    return cur, (cur == view)
