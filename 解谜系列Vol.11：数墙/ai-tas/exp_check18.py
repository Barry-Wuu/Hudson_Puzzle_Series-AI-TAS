#!/usr/bin/env python3
"""验证 lvl18 多涂 2 格之谜：burst 后长等动画沉降，再读盘面 + 查是否已通关。

用法: python3 exp_check18.py [lvl]
"""
import sys
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import mode2_fast as M

lvl = int(sys.argv[1]) if len(sys.argv) > 1 else 18

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
ds.tap_batch(pts, gap=0.02, hold=0.04, after=0.01)
M.safe_mouseup()
print(f"burst done {time.time()-tb:.2f}s ({len(pts)}格)", flush=True)

# 关键改动：等 3.5s 让所有涂黑动画彻底沉降
for k in range(7):
    time.sleep(0.5)
    st = M.state()
    print(f"  t+{0.5*(k+1):.1f}s state={st}", flush=True)
    if st == "clear":
        break

g = M.board_gray()
miss = [w for w in walls if M.cell_state(g, *w) == "W"]
extra = []
for r in range(10):
    for c in range(10):
        if M.cell_state(g, r, c) == "B" and (r, c) not in walls:
            extra.append((r, c))
print(f"漏涂: {len(miss)} {miss}")
print(f"多涂: {len(extra)} {extra}")
print(f"walls 含 (6,5)? {(6,5) in walls}  (6,9)? {(6,9) in walls}")

if M.state() == "clear":
    time.sleep(2.5)
    im = ds.grab(f"chk_l{lvl}")
    n = M.stars_gold(im)
    print(f"gold_stars={n}", flush=True)
    im.crop((0, 0, 256, 192)).resize((512, 384)).save(f"/tmp/chk_top_l{lvl}.png")
else:
    M.ensure_select()
