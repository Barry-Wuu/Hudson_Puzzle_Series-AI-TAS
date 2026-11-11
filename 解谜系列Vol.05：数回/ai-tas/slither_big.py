#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.05 数回 24x14 大盘录制核心：多视口滚动 + 逐视口实测格线 + 逐边绘制。

★ 关键实机事实（ふつう 第65問 idx1587，2026-11-12 标定）：
  18x10 只有横向两档；24x14 是「上屏全盘缩略图 + 下屏 16px 放大局部」，
  横向 3 档、纵向 2 档，且**每次滚动格线起点会像素级漂移**：
      col0 = 0  -> X0=11 ; col0 = 5 -> X0=24 ; col0 = 10 -> X0=20
      row0 = 0  -> Y0=9  ; row0 = 5 -> Y0=18
  因此绝不能全局固定 X0/Y0；必须每个视口用「格线检测 + 数字匹配」实测
  (X0, Y0, row0, col0)。用错的 X0/Y0 做数字匹配只有 105 分，用实测值
  可达 125/126 满分。

  * 下屏格点 P=16；每视口显示 14 列 x 9 行格（15 x 10 个顶点）。
  * 数字匹配：下屏 9x14 格心有无数字 vs 题库 clue_grid 全偏移比对。
  * 逻辑档位：col0 ∈ {0,5,10}（覆盖顶点列 0..14 / 5..19 / 10..24），
    row0 ∈ {0,5}（覆盖顶点行 0..9 / 5..14），联合覆盖全盘 0..24 / 0..14。
  * 可画像素边界：x <= 244（x=251 右侧滑块死区）、y <= 162（y=169 底部
    工具栏死区）。c=24 在 col0=10 视口落在 x=244、r=14 在 row0=5 视口
    落在 y=162，实测差分 418 均可画。
  * 滚动控件：右滑块 (250,86) 横向 +1 档 / 左滑块 (4,86) -1 档 /
    底部滑块 (127,167) 纵向 +1 档（无反向）。故遍历走蛇形，纵向单向。
  * 上屏缩略图：格距 10px，深绯红 (197,8,41) 视口框，仅用于导航辅助。
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
_DATA = None

P = 16
XMAX, YMAX = 244, 162          # 可画像素上界（右侧滑块 / 底部工具栏死区之外）
TAPS = {"R": (250, 86), "L": (4, 86), "D": (127, 167)}
# 从干净进关 (0,0) 出发的蛇形滚动序列；纵向只能 +，故先走完 row0=0 全部横档
SCROLL_SEQ = [None, "R", "R", "D", "L", "L"]

# ★ 6 步蛇形滚动里，只有 4 个视口的参数经 dry-run 验证可画（缺边 0）。
#   中间两档 R1(X0=15,c0=6) / L1(X0=24,c0=5) 的格线是像素级过渡态、
#   坐标不可靠（第65問第二次 dry-run 在这两档分别缺 20 / 9 条边），
#   因此只作为滚动过渡、**不在其上画边**。
#   而 4 个可信视口联合已 100% 覆盖 53 题：
#     col 0..14 + 10..24，row 0..9 + 5..14 => 全盘 0..24 / 0..14。
#   绝不能在「已画过线」的画面上重新 detect_origin：画上的线会被误判成格线
#   （首次 dry-run 得到 Y0=57/34/82 之类的过渡原点，漏 43 条边）。
#   step -> 可信视口参数（step1 / step4 为 None 表示仅过渡不绘制）
DRAW_VIEWS = {
    0: dict(X0=11, Y0=9,  r0=0, c0=0),    # 起点
    2: dict(X0=20, Y0=9,  r0=0, c0=10),   # R2
    3: dict(X0=20, Y0=18, r0=5, c0=10),   # D1
    5: dict(X0=11, Y0=18, r0=5, c0=0),    # L2
}
MISS_TH = 80                   # 净盘差分阈值

# 由录制器注入：每次点滑块前询问「是否已经判定完成」，防止 Completion!!
# 弹窗被连续点击误操作回标题。
STOP_HOOK = None


def _data():
    global _DATA
    if _DATA is None:
        _DATA = json.load(open(PJ, encoding="utf-8"))
    return _DATA


def bot_rgb():
    return np.asarray(ds.grab(None).convert("RGB")).astype(int)[192:384]


def top_rgb():
    return np.asarray(ds.grab(None).convert("RGB")).astype(int)[0:192]


def puzzle(idx):
    return next(x for x in _data() if x["idx"] == idx)


def edges_of(idx):
    p = puzzle(idx)
    return ([("h", r, c) for (r, c) in p["edges_h"]] +
            [("v", r, c) for (r, c) in p["edges_v"]])


# ---------- 逐视口实测 ----------
def _peaks(v, th, lo, hi):
    xs = [i for i, c in enumerate(v) if c > th and lo < i < hi]
    o = []
    for x in xs:
        if o and x - o[-1][-1] <= 1:
            o[-1].append(x)
        else:
            o.append([x])
    return [g[0] for g in o]


def detect_origin(a):
    """从下屏图找格线主序列起点 (X0, Y0)：连续 16px 间距最长的那条。"""
    d = (a.sum(axis=2) < 480)
    gx = _peaks(d[10:170, :].sum(axis=0), 110, 3, 250)
    gy = _peaks(d[:, 8:248].sum(axis=1), 100, 3, 180)

    def main(v):
        best = []
        for s in v:
            seq = [s]
            while seq[-1] + P in v:
                seq.append(seq[-1] + P)
            if len(seq) > len(best):
                best = seq
        return best[0] if best else 11

    return main(gx), main(gy)


def measure(idx, a=None, tries=4):
    """实测当前视口 -> dict(X0,Y0,r0,c0,score)。

    格线检测定像素原点，数字匹配定逻辑档位；score >= 110 视为动画已稳定。
    """
    grid = puzzle(idx)["clue_grid"]
    H, W = len(grid), len(grid[0])
    last = None
    for _ in range(tries):
        im = bot_rgb() if a is None else a
        X0, Y0 = detect_origin(im)
        m = np.zeros((9, 14), bool)
        for r in range(9):
            for c in range(14):
                x, y = X0 + P * c + 8, Y0 + P * r + 8
                if 0 <= x - 6 and x + 7 <= 256 and 0 <= y - 6 and y + 7 <= 192:
                    m[r, c] = (im[y - 6:y + 7, x - 6:x + 7].sum(axis=2) < 400).sum() > 8
        best = (-1, 0, 0)
        for r0 in range(0, min(H, 7)):
            for c0 in range(0, min(W, 13)):
                s = 0
                for r in range(9):
                    for c in range(14):
                        if r0 + r < H and c0 + c < W:
                            s += int(m[r, c] == (grid[r0 + r][c0 + c] != "."))
                if s > best[0]:
                    best = (s, r0, c0)
        last = dict(X0=X0, Y0=Y0, r0=best[1], c0=best[2], score=best[0])
        if best[0] >= 110:
            return last
        a = None
        time.sleep(0.6)
    return last


# ---------- 上屏视口框（导航辅助 / 复位校验）----------
def frame_view(a=None):
    """上屏深绯红视口框左上角 -> 框档位 (row, col)，仅供复位检查。"""
    a = top_rgb() if a is None else a
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    m = (R > 170) & (R < 235) & (G < 60) & (B < 90)
    m[:20, :] = False
    colcnt, rowcnt = m.sum(axis=0), m.sum(axis=1)
    xs = np.where(colcnt >= 80)[0]
    ys = np.where(rowcnt >= 100)[0]
    if len(xs) < 2 or len(ys) < 2:
        return None
    return round((int(ys.min()) - 23) / 10), round((int(xs.min()) - 5) / 10)


# ---------- 边坐标（全部基于实测 M）----------
def endpts(kind, r, c):
    return [(r, c), (r, c + 1)] if kind == "h" else [(r, c), (r + 1, c)]


def _xy(rr, cc, M):
    return M["X0"] + P * (cc - M["c0"]), M["Y0"] + P * (rr - M["r0"])


def edge_px(kind, r, c, M):
    (x1, y1), (x2, y2) = (_xy(*v, M) for v in endpts(kind, r, c))
    return (x1, y1, x2, y2)


def visible(kind, r, c, M):
    """边的两个端点顶点都落在可画像素区内（避开滑块 / 工具栏死区）。"""
    for v in endpts(kind, r, c):
        x, y = _xy(*v, M)
        if not (M["X0"] <= x <= XMAX and M["Y0"] <= y <= YMAX):
            return False
    return True


def draw_line(kind, r, c, M):
    x1, y1, x2, y2 = edge_px(kind, r, c, M)
    r18.drag([(x1, y1), (x2, y2)], step=4, gap=0.02,
             head=0.12, down=0.10, tail=0.10, settle=0.12)


def score_edges(base, cur, edges, M):
    """净盘差分：每条边中间像素与净盘基线的平均 RGB 差。"""
    out = {}
    for (k, r, c) in edges:
        x1, y1, x2, y2 = edge_px(k, r, c, M)
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


# ---------- 绘制主流程 ----------
def draw_all(idx, settled=None, verbose=True):
    """按蛇形滚动序列逐视口绘制；每视口实测参数、净盘差分核查。

    缺边**不就地补画**（18x10 教训：补边会把已完成回路 toggle 坏），
    而是放回 pending，让后续视口（不同坐标系）重画；仍缺则交 run() 整关重试。
    返回 (未画完边集合, 累计仍缺数, 是否中途结算, 视口实测记录)。
    """
    edges = edges_of(idx)
    pending = set(edges)
    miss_total = 0
    stopped = False
    visited = []
    for step, action in enumerate(SCROLL_SEQ):
        if settled is not None and settled():
            stopped = True
            break
        if action is not None:
            if STOP_HOOK is not None and STOP_HOOK():
                stopped = True
                break
            ds.tap(*TAPS[action], hold=0.18, after=1.2)
            time.sleep(0.7)
        if settled is not None and settled():
            stopped = True
            break
        # 中间两档坐标不可靠，仅作滚动过渡，不画边
        if step not in DRAW_VIEWS:
            if verbose:
                print(f"  视口#{step} 过渡档，跳过绘制", flush=True)
            continue
        # 用硬编码标定参数，不从已画线的画面重新检测（检测会被线条污染）
        M = DRAW_VIEWS[step]
        visited.append((M["r0"], M["c0"], M["X0"], M["Y0"], -1))
        group = [e for e in edges if e in pending and visible(*e, M)]
        if not group:
            if verbose:
                print(f"  视口#{step} 逻辑({M['r0']},{M['c0']}) 原点({M['X0']},{M['Y0']}) 无新边", flush=True)
            continue
        base = bot_rgb()
        for e in group:
            draw_line(*e, M)
            pending.discard(e)
            if settled is not None and settled():
                stopped = True
                break
        if stopped:
            break
        sc = score_edges(base, bot_rgb(), group, M)
        miss = [e for e, s in sc.items() if s < MISS_TH]
        miss_total += len(miss)
        if verbose:
            print(f"  视口#{step} 逻辑({M['r0']},{M['c0']}) 原点({M['X0']},{M['Y0']}) "
                  f"画 {len(group)} 边 缺 {len(miss)} {miss[:4]}", flush=True)
        if miss:
            # 交后续视口重画，不就地补
            pending.update(miss)
    return pending, miss_total, stopped, visited


if __name__ == "__main__":
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 1587
    M = measure(idx)
    print("idx", idx, "measure", M, "边数", len(edges_of(idx)))
    print("可见边", sum(1 for e in edges_of(idx) if visible(*e, M)))
