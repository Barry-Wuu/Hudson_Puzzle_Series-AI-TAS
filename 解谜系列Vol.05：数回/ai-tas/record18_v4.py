#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.05 数回 —— 18x10（やさしい 93~100）连续录制（v4，生产版）。

关键实机行为：通关后按 A 不是回选关页，而是**直接进入下一关**（上屏 HUD 变
第 N+1 問）。因此 93~100 可以一条链录下来：每关只需「画 -> 补 -> チェック -> A」。

正确性自校验：每关都按 puzzles.json 里该关的官方单环画，若关卡号错位则判定
必然失败（不会静默录错），因此「过关」本身就是关卡号正确的证明。

用法:
    bash ai-tas/boot_audio.sh
    python3 ai-tas/record18_v4.py --lo 95 --hi 100
    python3 ai-tas/record18_v4.py --lo 95 --hi 95 --dry
"""
import argparse
import json
import numpy as np
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ds                      # noqa: E402
import nav18 as N              # noqa: E402
import record_levels as rl     # noqa: E402
import slither18 as s18        # noqa: E402

OUTDIR = "/workspace/vol5_recordings_18x10"
CHECK_BTN = (190, 178)
MISS_TH = 80


def draw_pass(idx, cur, base):
    edges = s18.edges_of(idx)
    a = [e for e in edges if s18.view_of_edge(*e) == "A"]
    b = [e for e in edges if s18.view_of_edge(*e) == "B"]
    for e in a:
        s18.draw_line(*e, "A")
    cur, ok = s18.go("B", cur, base)
    if not ok:
        print("  !! 切 B 档失败", flush=True)
    for e in b:
        s18.draw_line(*e, "B")
    print(f"  A {len(a)} + B {len(b)} 边绘完", flush=True)
    return cur


def repair(idx, cur, base, rounds=3):
    fixed = 0
    left = 0
    for it in range(rounds):
        missing = []
        for v in ("A", "B"):
            cur, _ = s18.go(v, cur, base)
            sc = s18.score_edges(base[v], s18.shot(), idx, v)
            missing += [(e, v) for e, s in sc.items() if s < MISS_TH]
        print(f"  核查#{it} 缺 {len(missing)} {[e for e, _ in missing][:8]}", flush=True)
        left = len(missing)
        if not missing:
            return cur, 0, fixed
        for (e, v) in missing:
            cur, _ = s18.go(v, cur, base)
            s18.draw_line(*e, v)
            fixed += 1
        time.sleep(0.4)
    return cur, left, fixed


def is_result():
    """上屏结算页判据：绿色底占比高（盘面屏几乎为 0，实测 0.42 vs 0.00）。"""
    a = np.asarray(ds.grab(None).convert("RGB").crop((0, 0, 256, 192))).astype(int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return float(((G > R + 30) & (G > B + 30)).mean()) > 0.15


def judge(timeout=14.0):
    ds.tap(*CHECK_BTN, hold=0.18, after=1.0)
    t0 = time.time()
    ok = False
    while time.time() - t0 < timeout:
        if is_result() or s18.is_select_ui():
            ok = True
            break
        time.sleep(0.3)
    time.sleep(2.4)          # 星数 / 最佳时间演出
    return ok, time.time() - t0


def advance():
    """按 A 前进：通常是直接进下一关；若回选关页则返回 False。"""
    ds.press("x", wait=2.6)
    if s18.is_select_ui():
        return False
    N.wait_start_anim()
    return True


def run(lo, hi, dry, force, outdir):
    os.makedirs(outdir, exist_ok=True)
    ds.ensure_window()
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
        if not dry and not force and os.path.exists(out) and os.path.getsize(out) > 20000:
            print(f"第{lvl}問 已存在，跳过", flush=True)
            continue
        if not s18.is_select_ui():
            if not N.leave_level():
                print("  无法回选关页，中止", flush=True)
                break
        N.goto_window(51)          # 选关窗口确定性滚到 51~100，避免误入别的关
        ok, taps = N.enter_level(lvl)
        if not ok:
            print(f"第{lvl}問 进关失败，中止", flush=True)
            break
        cur = "A"
        base = {}
        ok1 = ok2 = False
        for _try in range(3):
            base["A"] = s18.shot()
            cur, ok1 = s18.toggle("A")
            base["B"] = s18.shot()
            cur, ok2 = s18.toggle("B")
            if ok1 and ok2:
                cur = "A"
                break
            time.sleep(2.5)          # START 演出未结束，等一下重来
        print(f"第{lvl}問 idx={idx} 进关(tap{taps}) 基线={ok1}/{ok2} 档={cur}", flush=True)

        rec = None if dry else rl.rec_start(out)
        t0 = time.time()
        cur = draw_pass(idx, cur, base)
        cur, left, fixed = repair(idx, cur, base)
        wall = time.time() - t0
        cleared, waited = judge()
        rc = rl.rec_stop(rec) if rec else None      # 先停录，保证片尾停在结算页
        went_next = advance() if cleared else False
        size = os.path.getsize(out) if (not dry and os.path.exists(out)) else 0
        merged[lvl] = dict(lvl=lvl, idx=idx, board="18x10", edges=len(s18.edges_of(idx)),
                           draw=round(wall, 1), missing_left=int(left), fixed=int(fixed),
                           cleared=bool(cleared), next=bool(went_next),
                           judge_s=round(waited, 1), ff_rc=rc, size=size)
        print(f"第{lvl}問 画+修 {wall:.1f}s 缺{left} 补{fixed} 过关={cleared}({waited:.1f}s) "
              f"→下一关={went_next} mp4={size}B", flush=True)
        json.dump([merged[k] for k in sorted(merged)], open(logpath, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        if not cleared:
            print("  !! 未过关，停批", flush=True)
            break
    print("结束。日志", logpath, "共", len(merged), "关", flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=int, default=95)
    ap.add_argument("--hi", type=int, default=100)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--outdir", default=OUTDIR)
    a = ap.parse_args()
    run(a.lo, a.hi, a.dry, a.force, a.outdir)
