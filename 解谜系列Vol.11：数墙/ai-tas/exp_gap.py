#!/usr/bin/env python3
"""常速连涂参数实验 v2：burst + 补点 + 通关 + 星级全流程。

用法: python3 exp_gap.py <lvl> <gap> <hold> <after>
"""
import sys
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import mode2_fast as M

lvl = int(sys.argv[1])
gap, hold, after = float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
print(f"=== gap lvl{lvl} tap=({gap},{hold},{after}) -> {(gap+hold+after)*1000:.0f}ms/格", flush=True)

if not M.ensure_select():
    print("FAIL: cannot reach select")
    sys.exit(1)
t0 = M.enter_level(lvl)
if t0 is None:
    print(f"FAIL: enter lvl{lvl}")
    sys.exit(1)
print(f"entered lvl{lvl} t0+{time.time()-t0:.2f}s", flush=True)

remain = M.UNLOCK - (time.time() - t0)
if remain > 0:
    time.sleep(remain)

walls = M.walls_of(lvl - 1)
pts = [M.cell_nds(r, c) for r, c in walls]
tb = time.time()
ds.tap_batch(pts, gap=gap, hold=hold, after=after)
M.safe_mouseup()
burst_wall = time.time() - tb
print(f"burst {burst_wall:.2f}s ({len(pts)}格)", flush=True)

# 补点（只补纯白格，防 toggle 打转）
for k in range(5):
    if M.state() == "clear":
        break
    time.sleep(0.8)
    g = M.board_gray()
    miss = M.white_misses(g, walls)
    if not miss:
        break
    print(f"  [verify k{k}] miss={len(miss)} {miss[:12]}", flush=True)
    for (r, c) in miss:
        ds.tap(*M.cell_nds(r, c), **M.VERIFY_TAP)
    M.safe_mouseup()

cleared = M.wait_clear(8.0)
print(f"clear: {cleared} (burst后 {time.time()-tb:.1f}s)", flush=True)

if cleared:
    time.sleep(2.0)
    im = ds.grab(f"gap_l{lvl}")
    n = M.stars_gold(im)
    print(f"gold_stars={n}", flush=True)
    im.crop((0, 0, 256, 192)).resize((512, 384)).save(f"/tmp/gap_top_l{lvl}.png")
else:
    g = M.board_gray()
    miss = M.white_misses(g, walls)
    print(f"未通关 漏涂: {len(miss)} {miss[:15]}", flush=True)
    M.ensure_select()
