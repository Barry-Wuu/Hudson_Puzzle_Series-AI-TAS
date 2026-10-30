#!/usr/bin/env python3
"""修正视口模型验证：VCW_VIS=10, dc=clamp(cur-5,0,w-10)，重扫 0..17 列映射。
沿用 cal_hold2 结束时的盘面（光标在 col17 附近）→ 先 escape 重进。"""
import sys, time, json
sys.path.insert(0, ".")
import numpy as np
from cal_hold import PZ, clamp, step, zero_cursor, ICON_MASK
from play_akari_seg3 import (escape_to_select, goto_level, reset_level,
                             wait_select_page)

pz = PZ[31]; w, h = pz["w"], pz["h"]

def find_cursor2(exp, search=4):
    """dc 候选 0..w-10，可见 vc 0..9。"""
    exp_dc = clamp(exp[0] - 5, 0, w - 10)
    cands = sorted({clamp(exp_dc + d, 0, w - 10) for d in range(-search, search + 1)},
                   key=lambda c: abs(c - exp_dc))
    a = __import__("play_akari_seg3").grab_np()
    for dc in cands:
        best, bestn = None, 0
        for vr in range(0, min(10, h)):
            for vc in range(0, min(10, w - dc)):
                if (vc, vr) in ICON_MASK: continue
                y0, x0 = 208 + 16 * vr, 16 + 16 * vc
                reg = a[max(y0-3,0):y0+19, max(x0-3,0):x0+19]
                R, G, B = reg[:,:,0], reg[:,:,1], reg[:,:,2]
                n = int(((R>200)&(G>110)&(G<215)&(B<95)).sum())
                if n > bestn: bestn, best = n, (dc + vc, vr)
        if best is not None and bestn >= 30:
            return best
    return None

if not wait_select_page(8.0):
    escape_to_select()
assert goto_level(31) and reset_level()
time.sleep(1.0)
pos = zero_cursor(pz, w, h)
print("归零:", pos, flush=True)
mapping = []
for col in range(0, w):
    got = find_cursor2((col, 0))
    mapping.append((col, got))
    if col < w - 1:
        step("Right")
ok = all(g == (c, 0) for c, g in mapping)
print("全部精确:", ok, flush=True)
print(json.dumps(mapping), flush=True)
