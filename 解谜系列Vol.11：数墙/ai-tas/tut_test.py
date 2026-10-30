#!/usr/bin/env python3
"""测试 tut.py 驱动：从当前步骤继续打到本关结束。"""
import sys, time
sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import tut
import ds
from state2 import detect

print("== 初始状态 ==")
f = tut.grab_np()
print("state:", detect(ds.grab(None)))
grid = tut.detect_grid(f, verbose=True)
if not grid:
    print("FATAL no grid"); sys.exit(1)

for step_i in range(60):
    f = tut.grab_np()
    st = detect(ds.grab(None))
    print(f"\n== step {step_i} state={st} ==")
    if st == "clear":
        print("LEVEL CLEAR!"); break
    if st not in ("tut", "play"):
        print(f"unexpected state {st}, stop"); break
    grid = tut.detect_grid(f, verbose=True) or grid
    fp0 = tut.upper_fp(f)
    ok = tut.do_step(grid, fp0, verbose=True)
    print(f"  -> advanced={ok}")
    if not ok:
        print("  no advance, stop"); break
    time.sleep(0.5)

print("\n== 终态 ==")
print("state:", detect(ds.grab(None)))
