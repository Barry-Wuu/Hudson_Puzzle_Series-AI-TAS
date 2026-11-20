#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""24x14 批量点中点快速画法标定（只画+判定+测速，不录像）。

复用 record_big 的导航/判定/视口框架，把 slither_big 的逐边 drag 换成
「每视口把所有 visible 边的中点串成一条 xdotool 命令批量点击」（skip 核查，
18x10 已证明核查补边是 cur bug 造成的假象，画法本身一次性全对）。

用法:
  bash boot_audio.sh  或 boot.sh
  DISPLAY=:99 XDG_RUNTIME_DIR=/tmp \
    CLICK_GAP=0.02 CLICK_HOLD=0.06 CLICK_AFTER=0.10 CLICK_BATCH=24 CLICK_LEAD=0.20 \
    python3.11 fast_click_big.py --lo 65 --hi 67
"""
import os, sys, time, subprocess, json, argparse
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds
import nav18 as N
import slither18 as s18
import record18_v4 as V
import slither_big as SB
import record_big as RB
import edgecheck as ec

GAP = float(os.environ.get("CLICK_GAP", "0.02"))
HOLD = float(os.environ.get("CLICK_HOLD", "0.06"))
AFTER = float(os.environ.get("CLICK_AFTER", "0.10"))
BATCH = int(os.environ.get("CLICK_BATCH", "24"))
LEAD = float(os.environ.get("CLICK_LEAD", "0.20"))
PARK = (ds.WIN_X + 250, ds.WIN_Y + 380)
IDX_BASE = 1522   # futsuu: idx = 1522 + lvl


def park():
    subprocess.run(["xdotool", "mousemove", str(PARK[0]), str(PARK[1])], env=ds.ENV)


def click_cmd(points, lead=0.0):
    """points=[(nds_x,nds_y),...] -> 串成一条 xdotool 命令。"""
    cmd = ["xdotool"]
    for i, (mx, my) in enumerate(points):
        sx, sy = ds.WIN_X + mx, ds.WIN_Y + 192 + my
        g = GAP + (lead if i == 0 else 0.0)
        cmd += ["mousemove", str(sx), str(sy), "sleep", str(g),
                "mousedown", "1", "sleep", str(HOLD), "mouseup", "1",
                "sleep", str(AFTER)]
    return cmd


def view_midpoints(group, M):
    """该视口所有 visible 边的中点（下屏相对坐标），去重。"""
    pts = []
    for (k, r, c) in group:
        if not SB.visible(k, r, c, M):
            continue
        x1, y1, x2, y2 = SB.edge_px(k, r, c, M)
        pts.append(((x1 + x2) // 2, (y1 + y2) // 2))
    return pts


def draw_all_fast(idx, verbose=True):
    """蛇形滚动逐视口批量点中点。返回 (画点数, 视口数)。"""
    edges = SB.edges_of(idx)
    remaining = set(edges)
    ds.ensure_window()
    total_pts = 0
    nview = 0
    for step, action in enumerate(SB.SCROLL_SEQ):
        # 是否已结算（前视口点完可能已过关）
        if V.settled():
            break
        if action is not None:
            ds.tap(*SB.TAPS[action], hold=0.18, after=1.2)
            time.sleep(0.7)
        if step not in SB.DRAW_VIEWS:
            continue
        M = SB.DRAW_VIEWS[step]
        group = [e for e in edges if e in remaining and SB.visible(*e, M)]
        if not group:
            continue
        pts = view_midpoints(group, M)
        for i in range(0, len(pts), BATCH):
            subprocess.run(click_cmd(pts[i:i+BATCH], lead=LEAD), env=ds.ENV, check=True)
        park(); time.sleep(0.25)
        total_pts += len(pts)
        nview += 1
        for e in group:
            remaining.discard(e)
        if verbose:
            print(f"  视口#{step} ({M['r0']},{M['c0']}) 点 {len(pts)} 条边", flush=True)
    return total_pts, nview, len(remaining)


def run_level(lvl, diff="futsuu", verbose=True):
    idx = IDX_BASE + lvl
    for attempt in range(1, 4):
        if not RB.to_select_of(diff):
            print(f"L{lvl}: 无法到选关页，第{attempt}次", flush=True)
            continue
        N.goto_window(51 if lvl > 50 else 1)
        ok, _ = N.enter_level(lvl)
        if not ok or not RB.ensure_board(lvl, diff):
            print(f"L{lvl}: 进关/净盘失败，第{attempt}次", flush=True)
            continue
        M0 = SB.measure(idx)
        if (M0["r0"], M0["c0"]) != (0, 0) or M0["score"] < 110:
            print(f"L{lvl}: 视口未复位 {M0['r0']},{M0['c0']} score={M0['score']}，重来", flush=True)
            continue
        t0 = time.time()
        pts, nv, rem = draw_all_fast(idx, verbose=verbose)
        cleared, waited, kind = RB.judge()
        draw_s = time.time() - t0
        print(f"L{lvl} idx{idx}: 视口{nv} 点{pts}边 剩{rem} 画{draw_s:.1f}s "
              f"判定={kind} 过关={cleared}({waited:.1f}s) att={attempt}", flush=True)
        if cleared:
            return dict(lvl=lvl, idx=idx, pts=pts, views=nv, remaining=rem,
                        draw=round(draw_s, 1), cleared=True, attempt=attempt)
    return dict(lvl=lvl, idx=idx, cleared=False, attempt=3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=int, default=65)
    ap.add_argument("--hi", type=int, default=65)
    ap.add_argument("--diff", default="futsuu")
    a = ap.parse_args()
    print(f"参数 GAP={GAP} HOLD={HOLD} AFTER={AFTER} BATCH={BATCH} LEAD={LEAD}", flush=True)
    if not s18.is_select_ui():
        N.goto_muzukashii_select()
    RB.to_select_of(a.diff)
    N.goto_window(1)
    res = []
    for lvl in range(a.lo, a.hi + 1):
        res.append(run_level(lvl, a.diff))
    ok = sum(1 for r in res if r["cleared"])
    print(f"=== 汇总 {ok}/{len(res)} 过关 ===", flush=True)


if __name__ == "__main__":
    main()
