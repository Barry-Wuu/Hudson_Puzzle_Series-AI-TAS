#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.05 数回 —— 18x10 档（やさしい 93~100）带上音频逐关录制。

与 record_levels.py 的 10x10 档差异：
  * 18 列盘面比下屏宽，横向分两档滚动查看：点边缘红滑块 toggle，内容位移 55px。
    A 档显示顶点列 0~15，B 档显示列 3~18（x 平移 -55）。
  * 画环按「视图分段」：把单环拆成若干同视图的连续链，每链一次拖动作画。
    这种整链拖动比逐条边单独 drag 快 5~8 倍；若整链丢边则退回 --mode edge 逐边画。
  * 画完必须点右下「チェック」(230,180) 触发判定（18x10 不自动结算）。

用法:
    bash ai-tas/boot_audio.sh
    python3 ai-tas/record18_levels.py --lo 93 --hi 100
    python3 ai-tas/record18_levels.py --lo 94 --test        # 不录制，只验证画法
"""
import argparse
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds                      # noqa: E402
import record_levels as rl     # noqa: E402
import record18 as r18         # noqa: E402

BASE = os.path.dirname(HERE)
PJ = os.path.join(BASE, "validation", "puzzles.json")
OUTDIR = "/workspace/vol5_recordings_18x10"
CHECK_BTN = (230, 180)


def loop_verts(idx):
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
    s = next(iter(adj))
    path, cur, used = [s], s, set()
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
    return path


def view_of(a, b):
    """一条边归属哪档：任一端顶点列 >=15 就只在 B 档可见。"""
    return "B" if max(a[1], b[1]) >= 15 else "A"


def split_runs(path):
    """单环 -> [(view, [顶点...]), ...]，相邻同视图的边合并成一条链。"""
    n = len(path)
    views = [view_of(path[i], path[(i + 1) % n]) for i in range(n)]
    start = next((i for i in range(n) if views[i] != views[i - 1]), 0)
    runs, curv, pts = [], None, None
    for k in range(n):
        i = (start + k) % n
        v = views[i]
        if v != curv:
            if pts:
                runs.append((curv, pts))
            curv, pts = v, [path[i], path[(i + 1) % n]]
        else:
            pts.append(path[(i + 1) % n])
    if pts:
        runs.append((curv, pts))
    return runs


def draw_runs(idx, verbose=True):
    runs = split_runs(loop_verts(idx))
    if verbose:
        print("runs", [(v, len(p) - 1) for v, p in runs], flush=True)
    cur = r18.ensure_view("A")
    t0 = time.time()
    for view, vs in runs:
        cur = r18.toggle_to(view, cur)
        r18.drag([r18.vxy(v, view) for v in vs], step=4, gap=0.018,
                 head=0.12, down=0.10, tail=0.10, settle=0.22)
    return cur, time.time() - t0, len(runs)


def draw_edges(idx, verbose=True):
    t0 = time.time()
    cur = r18.draw_all_edges(idx, verbose=verbose)
    return cur, time.time() - t0, len(r18.expected_edges(idx))


def check_and_back(timeout=12.0):
    """点 チェック -> 等结果屏（下屏回选关网格即说明判定完成）-> 按 x 回选关页。"""
    ds.tap(*CHECK_BTN, hold=0.20, after=1.4)
    t0 = time.time()
    seen = False
    while time.time() - t0 < timeout:
        if rl.state() != "board":
            seen = True
            break
        time.sleep(0.4)
    time.sleep(1.6)                       # 让结算乐句 / 星数演出走完
    for _ in range(3):
        ds.press("x", wait=1.4)
        if rl.state() == "select":
            break
        ds.tap(128, 96, hold=0.15, after=1.4)
    ok, _ = rl.ensure_select()
    return seen, ok, time.time() - t0


def run(lo, hi, mode, test, outdir):
    os.makedirs(outdir, exist_ok=True)
    ds.ensure_window()
    print(f"18x10 档 区间 {lo}..{hi} mode={mode} test={test}", flush=True)
    print("起点状态", rl.state(), flush=True)
    logpath = os.path.join(outdir, "record_log.json")
    merged = {}
    if os.path.exists(logpath):
        try:
            merged = {r["lvl"]: r for r in json.load(open(logpath, encoding="utf-8"))}
        except (ValueError, OSError):
            pass

    for lvl in range(lo, hi + 1):
        idx = 1515 + (lvl - 93)
        out = os.path.join(outdir, f"数回_やさしい18x10_第{lvl:02d}問.mp4")
        if not test and os.path.exists(out) and os.path.getsize(out) > 20000:
            print(f"第{lvl}問 已存在，跳过", flush=True)
            continue
        ok_sel, _ = rl.ensure_select()
        if not ok_sel:
            print(f"第{lvl}問 到选关页失败，中止", flush=True)
            break
        ok_enter, taps = rl.enter(lvl)
        if not ok_enter:
            print(f"第{lvl}問 进关失败，中止", flush=True)
            break
        print(f"第{lvl}問 idx={idx} 进关成功(tap{taps}) state={rl.state()}", flush=True)

        rec = None
        if not test:
            rec = rl.rec_start(out)
        cur, wall, unit = (draw_edges if mode == "edge" else draw_runs)(idx)
        seen, back, waited = check_and_back()
        rc = rl.rec_stop(rec) if rec else None
        size = os.path.getsize(out) if (out and os.path.exists(out)) else 0
        row = dict(lvl=lvl, idx=idx, board="18x10", mode=mode,
                   runs=unit, drag=round(wall, 2),
                   judge=seen, back=back, waited=round(waited, 1),
                   ff_rc=rc, size=size)
        merged[lvl] = row
        print(f"第{lvl}問 画完 {wall:.1f}s({unit}) 判定={seen} 回选关={back} "
              f"mp4={size}B", flush=True)
        json.dump([merged[k] for k in sorted(merged)], open(logpath, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        if not seen:
            print("  !! 未能判定，停止本批（检查画法 / 剂量）", flush=True)
            break
    print("完成。日志", logpath, "状态", rl.state(), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=int, default=93)
    ap.add_argument("--hi", type=int, default=100)
    ap.add_argument("--mode", choices=["runs", "edge"], default="runs")
    ap.add_argument("--test", action="store_true", help="不录视频，只验证画法与判定")
    ap.add_argument("--outdir", default=OUTDIR)
    a = ap.parse_args()
    run(a.lo, a.hi, a.mode, a.test, a.outdir)
