#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提速版画法：单击线段中点 + 批量 xdotool（一次窗口布局，消除 ensure_window 逐次开销）。

用法（env 调参）：
  CLICK_GAP=0.02 CLICK_HOLD=0.05 CLICK_AFTER=0.12 python3.11 fast_click.py --lo 1 --hi 1
  CHAIN=1 可把同一档所有边的点击串成一条 xdotool 命令（极致提速）。

设计要点：
  - 一次 ensure_window()，之后所有触摸用裸 xdotool 命令，不重复 search/windowmove/focus。
  - 每条边中点单击一次（已证实 = 画一条线）。
  - A/B 分档：同档边一次性串起；切档单独 tap 滑块。
  - 画完做逐边净盘差分核查（漏边=差≈0），再点チェック，如实判过关。
"""
import os, sys, time, subprocess, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds
import nav18 as N
import record18 as r18
import edgecheck as ec
import slither18 as s18
import record18_v4 as V
import record_big as RB

IDX_BASE = 1522          # idx = base + lvl (ふつう)
GAP = float(os.environ.get("CLICK_GAP", "0.03"))
HOLD = float(os.environ.get("CLICK_HOLD", "0.05"))
AFTER = float(os.environ.get("CLICK_AFTER", "0.15"))
CHAIN = os.environ.get("CHAIN", "1") == "1"
BATCH = int(os.environ.get("CLICK_BATCH", "24"))   # 每条 xdotool 命令最多串多少边
PARK = (ds.WIN_X + 250, ds.WIN_Y + 380)


def park():
    subprocess.run(["xdotool", "mousemove", str(PARK[0]), str(PARK[1])], env=ds.ENV)


def click_cmd(points, lead=0.0):
    """points=[(nds_x,nds_y),...] -> 一条 xdotool 命令串起所有单击。
    lead: 整批第一条 mousemove 后的额外停顿（消除批次开头首点丢失）。"""
    cmd = ["xdotool"]
    for i, (mx, my) in enumerate(points):
        sx, sy = ds.WIN_X + mx, ds.WIN_Y + 192 + my
        g = GAP + (lead if i == 0 else 0.0)
        cmd += ["mousemove", str(sx), str(sy), "sleep", str(g),
                "mousedown", "1", "sleep", str(HOLD), "mouseup", "1",
                "sleep", str(AFTER)]
    return cmd


def enter_verified(lvl, tries=4):
    """稳定进关：先回目标难度选关页，再滚窗、点格子、清结算页。
    复用 record18_v4/record_big 已验证的导航链，不再用不可靠的 OCR 校验。"""
    import record_big as RB
    for k in range(tries):
        if not RB.to_select_of("futsuu"):
            time.sleep(1.0)
            continue
        N.goto_window(1 if lvl <= 50 else 51)
        ok, taps = N.enter_level(lvl)
        if not ok:
            continue
        # 第1关已通关：进关先显示成绩页，触摸一下即进净盘（press x 会翻到别的关！）
        time.sleep(0.8)
        for _ in range(3):
            if V.completion_anim() or V.real_result() or RB.on_board():
                ds.tap(128, 96, hold=0.12, after=0.8)   # 触摸推进，不用 A
            else:
                break
        N.wait_start_anim()
        return True
    return False


def run_level(lvl, do_check=True, verbose=True, assume_board=False, skip_verify=False):
    idx = IDX_BASE + lvl
    if not assume_board:
        if not enter_verified(lvl):
            if verbose:
                print(f"L{lvl}: 进关失败，跳过", flush=True)
            return dict(lvl=lvl, idx=idx, edges=0, t=0, ok=False)
    else:
        ds.ensure_window()
    time.sleep(0.3)

    data = json.load(open(ec.PJ, encoding="utf-8"))
    p = next(x for x in data if x["idx"] == idx)
    edges = [("h", r, c) for (r, c) in p["edges_h"]] + [("v", r, c) for (r, c) in p["edges_v"]]
    A = [e for e in edges if r18.edge_view(*e) == "A"]
    B = [e for e in edges if r18.edge_view(*e) == "B"]

    ds.ensure_window()
    r18.ensure_view("A")
    cur = "A"
    LEAD = float(os.environ.get("CLICK_LEAD", "0.18"))   # 每批首点额外停顿

    def pts_for(group, view):
        off = -r18.SHIFT_B if view == "B" else 0
        out = []
        for (k, r, c) in group:
            x1, y1, x2, y2 = r18.edge_px(k, r, c)
            out.append(((x1 + x2)//2 + off, (y1 + y2)//2))
        return out

    def paint_batch(groups_by_view):
        """按档批量画；返回 (view->净盘base, view->边列表)。"""
        nonlocal cur
        bases = {}
        for view, group in groups_by_view:
            if not group:
                continue
            if view != cur:
                r18.toggle_to(view, cur)
                cur = view                      # ★ 切档后必须更新 cur，否则后续核查拿错档画面比 base
            time.sleep(0.35)
            # 存档该档净盘（首轮该档还没画时）
            if view not in bases:
                park(); time.sleep(0.3); bases[view] = ec.bot_rgb()
            pl = pts_for(group, view)
            for i in range(0, len(pl), BATCH):
                subprocess.run(click_cmd(pl[i:i+BATCH], lead=LEAD), env=ds.ENV, check=True)
            park(); time.sleep(0.2)
        return bases

    t0 = time.time()
    bases = paint_batch((("A", A), ("B", B)))
    if skip_verify:
        # 激进模式：批量画法本身已证实画对（Completion!!），跳过整个核查补边。
        if verbose:
            print("  skip_verify: 跳过核查补边，画完直接チェック", flush=True)
    else:
        # 逐档核查 + 补边（最多 3 轮）
        MAX_FIX = int(os.environ.get("CLICK_FIXROUNDS", "3"))
        TH = 60.0
        for rnd in range(MAX_FIX + 1):
            misses = {}
            for view, group in (("A", A), ("B", B)):
                if not group or view not in bases:
                    continue
                if view != cur:
                    r18.toggle_to(view, cur); cur = view; time.sleep(0.35)
                park(); time.sleep(0.25); now = ec.bot_rgb()
                sc = ec.edge_scores(bases[view], now, idx, view)
                miss = [e for e in group if sc.get(e, 0.0) < TH]
                if miss:
                    misses[view] = miss
            total = sum(len(v) for v in misses.values())
            if verbose:
                print(f"  核查轮{rnd}: 漏边 {total}" + (f" {dict((k,len(v)) for k,v in misses.items())}" if total else ""), flush=True)
            if total == 0 or rnd == MAX_FIX:
                break
            # 补边：逐条独立点击（稳），每条后留足间隔
            for view, group in misses.items():
                if view != cur:
                    r18.toggle_to(view, cur); cur = view; time.sleep(0.35)
                for e in group:
                    mx, my = pts_for([e], view)[0]
                    # 补边用已验证可靠的独立 tap（历史 exp_click_all 从不漏）
                    ds.tap(mx, my, hold=0.10, after=0.45)
                park(); time.sleep(0.2)
    park()
    elapsed = time.time() - t0

    ds.grab(f"fc_{lvl}_drawn")
    if verbose:
        print(f"L{lvl} idx{idx}: 边数={len(edges)}(A{len(A)}+B{len(B)}) 总耗时(含核查补边)={elapsed:.1f}s", flush=True)

    result = None
    if do_check:
        ck = (195, 182)
        ds.tap(*ck, hold=0.18, after=0.0)
        park()
        got = False
        # 只观察、绝不 tap 推进。过关判据三选一命中即可：
        #   Completion 弹窗 / 真结算页 / 盘面已消失(自动回到选关页)
        # 注：DeSmuME 无音频下 Completion 可能一闪而过，靠"离开盘面"兜底。
        t1 = time.time()
        while time.time() - t1 < 8:
            if V.completion_anim() or V.real_result():
                got = True
                break
            # 宽松兜底：下屏中央 "Completion!!" 橙色大字面积（带 Please touch 时
            # completion_anim 的白色/xor 判据会漏，但橙色面积稳定 >3500，误检<1700）
            bot = ec.bot_rgb()
            reg = bot[70:135, 30:230]
            orange = int(((reg[:, :, 0] > 150) & (reg[:, :, 1] > 60) &
                          (reg[:, :, 1] < 175) & (reg[:, :, 2] < 110)).sum())
            if orange > 2500:
                got = True
                break
            if not RB.on_board() and N._screen_kind() in ("select", "menu"):
                got = True
                break
            time.sleep(0.25)
        ds.grab(f"fc_{lvl}_check")
        result = got
        if verbose:
            print(f"  -> チェック结果: {'Completion/过关' if got else '未过关'}", flush=True)
    return dict(lvl=lvl, idx=idx, edges=len(edges), t=elapsed, ok=result)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=int, default=1)
    ap.add_argument("--hi", type=int, default=1)
    ap.add_argument("--nocheck", action="store_true")
    ap.add_argument("--assume-board", action="store_true", help="假设当前已在目标关净盘，跳过导航")
    ap.add_argument("--skip-verify", action="store_true", help="跳过核查补边，画完直接チェック（激进提速）")
    a = ap.parse_args()
    print(f"参数 GAP={GAP} HOLD={HOLD} AFTER={AFTER} CHAIN={CHAIN} BATCH={BATCH}", flush=True)
    for lvl in range(a.lo, a.hi + 1):
        run_level(lvl, do_check=not a.nocheck, assume_board=a.assume_board, skip_verify=a.skip_verify)


if __name__ == "__main__":
    main()
