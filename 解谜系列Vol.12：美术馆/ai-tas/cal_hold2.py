#!/usr/bin/env python3
"""逐格推进映射：光标 0..17 列逐格 Right，每步检测，确定可见列范围与 dc 映射。"""
import sys, time, json
sys.path.insert(0, ".")
from cal_hold import (PZ, clamp, find_cursor, hold_key, step, zero_cursor,
                      ICON_MASK)
from play_akari_seg3 import (escape_to_select, goto_level, reset_level,
                             wait_select_page, has_start_overlay)

pz = PZ[31]; w, h = pz["w"], pz["h"]
if not wait_select_page(8.0):
    escape_to_select()
assert goto_level(31), "进关失败"
time.sleep(2.0)
assert reset_level(), "reset 失败"
time.sleep(1.0)
pos = zero_cursor(pz, w, h)
print("归零:", pos, flush=True)
cur = list(pos or [0, 0])
mapping = []
for col in range(0, w):
    got = find_cursor(pz, (col, 0))
    mapping.append((col, got))
    print(f"记账 col={col} 检测={got}", flush=True)
    if col < w - 1:
        step("Right")
print(json.dumps(mapping), flush=True)
