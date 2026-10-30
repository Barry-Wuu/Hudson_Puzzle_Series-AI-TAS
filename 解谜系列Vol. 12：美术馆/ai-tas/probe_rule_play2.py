#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针 12：进 Q51（会触发 ルール 说明过场），观察：
  1) 进关后多久真正进入第 51 关
  2) 说明页期间按 ▶ (NDS 250,175) 是否能翻页/跳过
  3) 下屏盘面 owner 随时间的变化
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ds
import play_akari_seg2 as P

data = json.load(open(P.PUZZLES))
seq = data["やさしい"]
exp_all = [(i + 1, P.expected_walls(p)) for i, p in enumerate(seq) if p["w"] == 10]


def owner_now():
    a = np.asarray(ds.grab("").convert("RGB")).astype(int)
    got = []
    for r in range(10):
        row = ""
        for c in range(10):
            cx, cy = int(16 + 16 * (c + 0.5)), int(208 + 16 * (r + 0.5))
            cell = a[cy - 5:cy + 6, cx - 5:cx + 6].reshape(-1, 3)
            blue = ((cell[:, 2] > 100) & (cell[:, 2] > cell[:, 0] + 35)).mean()
            row += "W" if blue > 0.35 else "."
        got.append(row)
    best = []
    for idx, e in exp_all:
        m = sum(x == y for r1, r2 in zip(got, e) for x, y in zip(r1, r2))
        best.append((m, idx))
    best.sort(reverse=True)
    return best[0]


def rule_page():
    a = np.asarray(ds.grab("").convert("RGB")).astype(int)
    reg = a[0:26, 215:256]
    g = ((np.abs(reg[:, :, 0] - 65) < 25) & (np.abs(reg[:, :, 1] - 90) < 25)
         & (np.abs(reg[:, :, 2] - 57) < 25)).sum()
    return int(g) > 250


def main():
    # 回选关页
    for _ in range(6):
        if P.in_select_page():
            break
        P.escape_to_select()
    print("select:", P.in_select_page())
    # 导航到 Q51
    P._scroll_up_to_top()
    P._scroll_down_steps(1)
    ds.tap_local(P.COL_X0, P.ROW_Y[4], after=1.0)
    ds.grab("p12_sel")
    ds.press("x", wait=1.0)
    for i in range(14):
        rp = rule_page()
        ow = owner_now()
        print(f"  t{i}: rule={rp} owner={ow}")
        if ow[0] >= 95 and ow[1] == 51:
            print("  → 已进入第 51 关")
            break
        if rp:
            ds.tap(250, 175, after=1.0)     # ▶ 翻页
        else:
            time.sleep(1.0)
    ds.grab("p12_end")


main()
