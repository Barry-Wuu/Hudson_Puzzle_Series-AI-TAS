#!/usr/bin/env python3
"""Akari 点灯剂量实测 v2：每剂量在不同关卡各测一次（避免重复进同关的 exit 抖动）。
命中判定：tap_batch 后盘面 dark<120 => 全部灯点亮(漏点必留暗格)。
用 main 风格 clear->x->select 回选关页（不通 Return 菜单，规避通关画面误触）。
"""
import json, time
import play_akari as P
import ds

seq = json.load(open(P.PUZZLES))["入門"]

# (关卡n, after) —— 覆盖 7/8/9/10 灯
TARGETS = [
    (2, 0.02), (3, 0.02), (4, 0.02),
    (5, 0.05), (6, 0.05),
    (7, 0.10), (8, 0.10),
]
HOLD, GAP = 0.06, 0.02

if not P.wait_select(4):
    print("boot...", flush=True)
    if not P.boot_to_select():
        raise SystemExit("boot fail")

for (n, after) in TARGETS:
    pz = seq[n - 1]
    if P.goto(n) != n:
        print(f"Q{n}: goto 失败"); break
    ds.press("x", wait=2.0)
    time.sleep(1.2)
    pts = P.bulb_points(pz)
    t0 = time.time()
    ds.tap_batch(pts, gap=GAP, hold=HOLD, after=after)
    tap_t = time.time() - t0
    cleared = False
    for _ in range(10):
        time.sleep(0.5)
        if P.board_dark_count(ds.grab("")) < 120:
            cleared = True
            break
    # 回选关页（main 风格：通关后按 x）
    ds.press("x", wait=1.5)
    back = P.wait_select(4)
    per = tap_t / len(pts)
    print(f"Q{n} bulbs={len(pts)} after={after:<4} per={per:.3f}s cleared={cleared} back_select={back}",
          flush=True)
    if not back:
        print(f"Q{n}: 未回选关页，尝试 escape"); P.escape_to_select()
        if not P.wait_select(3):
            print(f"Q{n}: 卡死，中止"); break
print("DONE", flush=True)
