"""输入锁时长探针：A 放灯后不同等待下走 1 步再 A，用灯泡像素判定丢步。"""
import sys, time
sys.path.insert(0, ".")
from cal_hold import PZ, step, zero_cursor
from play_akari_seg3 import (escape_to_select, goto_level, reset_level,
                             wait_select_page, grab_np, _bulb_present, find_cursor)

pz = PZ[31]; w, h = pz["w"], pz["h"]
if not wait_select_page(8.0):
    escape_to_select()
assert goto_level(31) and reset_level()
time.sleep(1.0)
zero_cursor(pz, w, h)

# 取解的前两个灯
b1, b2 = pz["bulbs"][0], pz["bulbs"][1]
print("灯1", b1, "灯2", b2, flush=True)

def walk(bx, by):
    while cur[0] != bx:
        step("Right" if cur[0] < bx else "Left"); cur[0] += 1 if cur[0] < bx else -1
    while cur[1] != by:
        step("Down" if cur[1] < by else "Up"); cur[1] += 1 if cur[1] < by else -1

cur = [0, 0]
# 灯1：A 后等 2.5s（基线，确保灯1在）
walk(*b1)
ds_x = __import__("ds")
ds_x.press("x", wait=1.0); time.sleep(1.5)
dc, dr = min(max(cur[0]-5,0),w-10), 0
print("灯1 present:", _bulb_present(grab_np(), b1[0], b1[1], dc, dr), flush=True)

# 灯2：A 后只等 1.5s（0.5 wait + 1.0 sleep），立刻走位 → 看灯2是否出现
walk(*b2)
ds_x.press("x", wait=0.5); time.sleep(1.0)
dc2, _ = min(max(cur[0]-5,0),w-10), 0
a2 = grab_np()
p2 = _bulb_present(a2, b2[0], b2[1], dc2, 0)
p1b = _bulb_present(a2, b1[0], b1[1], dc2, 0)
print(f"短锁后 灯2 present: {p2}  灯1 仍 present: {p1b}", flush=True)
print("(若灯2=True 且 灯1=True → 1.5s 短锁可行)", flush=True)
