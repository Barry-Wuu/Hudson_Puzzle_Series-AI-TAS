#!/usr/bin/env python3
"""录制一段 dsm 影片：标题 -> やさしい -> lvl20 -> 70ms burst -> 通关。
用于分析 DeSmuME movie 格式，后续编辑成高速连涂版本。

前置：DeSmuME 以 --record-movie=/tmp/nav.dsm 启动（本脚本负责导航+操作）。
"""
import sys
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import mode2_fast as M

print("=== recording nav to lvl20 ===", flush=True)

# 从标题开始
for k in range(20):
    st = M.state()
    print(f"nav{k} state={st}", flush=True)
    if st == "select":
        break
    if st == "title":
        ds.tap(128, 23, after=1.0)
    elif st == "menu":
        ds.tap(170, 83, after=1.5)
    elif st == "diff":
        M.select_diff()
    elif st == "clear":
        ds.tap(128, 108, after=1.5)
    elif st == "play":
        ds.press("Return", wait=1.2)
    elif st == "option":
        ds.tap(205, 24, after=0.8); ds.press("x", wait=1.5)
    else:
        ds.press("z", wait=1.0)
    time.sleep(0.3)

if not M.ensure_select():
    print("FAIL: cannot reach select")
    sys.exit(1)

t0 = M.enter_level(20)
if t0 is None:
    print("FAIL enter lvl20")
    sys.exit(1)
print(f"entered lvl20 t0+{time.time()-t0:.2f}s", flush=True)

remain = M.UNLOCK - (time.time() - t0)
if remain > 0:
    time.sleep(remain)

walls = M.walls_of(19)
pts = [M.cell_nds(r, c) for r, c in walls]
tb = time.time()
ds.tap_batch(pts, gap=0.02, hold=0.04, after=0.01)
M.safe_mouseup()
print(f"burst done {time.time()-tb:.2f}s ({len(pts)}格)", flush=True)

# 等通关页并多停一会（让影片录到 clear 页停留）
for k in range(30):
    st = M.state()
    print(f"  wait{k} state={st} t+{time.time()-tb:.1f}s", flush=True)
    if st == "clear":
        time.sleep(2.0)
        ds.grab("rec_clear")
        break
    time.sleep(0.2)

# 停在 clear 页或 select 页，等录制停止
time.sleep(2.0)
print("=== recording done, quit emulator ===", flush=True)
