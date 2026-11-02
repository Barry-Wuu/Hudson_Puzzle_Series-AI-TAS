#!/usr/bin/env python3
"""Akari 点灯剂量实测：在 Q2 上扫不同 (after, gap, hold)，统计命中（=全亮通关）。

判定：tap_batch 全部灯后，若盘面 dark<120 → 100% 命中（任一漏点都会留暗格→dark高）。
约束参考 Vol.11 数墙：hold>=0.055 & hold+after>=0.08。
"""
import json, time
import numpy as np
import play_akari as P
import ds

seq = json.load(open(P.PUZZLES))["入門"]
pz = seq[1]          # Q2, 9 灯
print(f"Q2 bulbs = {len(pz['bulbs'])}", flush=True)

# 先确保选关页
if not P.wait_select(4):
    print("boot_to_select...", flush=True)
    if not P.boot_to_select():
        raise SystemExit("无法到选关页")

# 几种候选剂量（gap 固定 0.02，hold 固定 0.06；扫 after）
DOSES = [
    dict(gap=0.02, hold=0.06, after=0.02),
    dict(gap=0.02, hold=0.06, after=0.05),
    dict(gap=0.02, hold=0.06, after=0.10),
    dict(gap=0.02, hold=0.06, after=0.16),
]

for d in DOSES:
    # 导航到 Q2 并进入
    if P.goto(2) != 2:
        print("goto(2) 失败，中止"); break
    ds.press("x", wait=2.0)
    # 短暂等进关
    time.sleep(1.2)
    pts = P.bulb_points(pz)
    t0 = time.time()
    ds.tap_batch(pts, **d)
    tap_t = time.time() - t0
    # 判通关
    cleared = False
    for _ in range(10):
        time.sleep(0.5)
        if P.board_dark_count(ds.grab("")) < 120:
            cleared = True
            break
    per = tap_t / len(pts)
    print(f"after={d['after']:<4} hold={d['hold']} gap={d['gap']} -> "
          f"tap_total={tap_t:.2f}s per={per:.3f}s/bulb cleared={cleared}", flush=True)
    # 退出回选关页（无论是否通关）
    P.escape_to_select()
    time.sleep(0.5)
print("DONE", flush=True)
