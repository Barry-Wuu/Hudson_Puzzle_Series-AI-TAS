#!/usr/bin/env python3
"""全速（--disable-limiter）实验：帧计数计时下，锁/判定延迟的墙钟被压缩，
burst 墙钟成为唯一大头。测 70ms/格在全速下的丢击率与 TIME。

用法: python3 exp_turbo.py <lvl> [gap hold after]
"""
import subprocess
import sys
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import mode2_fast as M

lvl = int(sys.argv[1])
gap = float(sys.argv[2]) if len(sys.argv) > 2 else 0.02
hold = float(sys.argv[3]) if len(sys.argv) > 3 else 0.04
after = float(sys.argv[4]) if len(sys.argv) > 4 else 0.01
print(f"=== turbo lvl{lvl} tap=({gap},{hold},{after}) -> {(gap+hold+after)*1000:.0f}ms/格", flush=True)


def enter_turbo(lvl):
    """全速版进关：poll play -> 轮询 clue_match 匹配 -> 返回 (t0, settle_wall)。"""
    row, col = (lvl - 1) // 10, (lvl - 1) % 10
    wy = 280 + 16 * row
    wx = 19 + 24 * col
    for att in range(5):
        if not M.ensure_select():
            return None, None
        ds.tap(wx, wy - 192, after=0.4)
        ds.press("x", wait=0.2)
        t0 = time.time()
        st = M.poll(("play", "tut"), timeout=6)
        if st in ("play", "tut"):
            t_poll = time.time()
            for settle in range(40):
                time.sleep(0.1)
                ok, tot = M.clue_match(lvl - 1)
                if ok >= tot - 2:
                    return t0, time.time() - t_poll
            print(f"  [enter {lvl}] clue mismatch {ok}/{tot}", flush=True)
        else:
            print(f"  [enter {lvl}] att{att} state={st}", flush=True)
    return None, None


if not M.ensure_select():
    print("FAIL: cannot reach select")
    sys.exit(1)

t0, settle = enter_turbo(lvl)
if t0 is None:
    print(f"FAIL: enter lvl{lvl}")
    sys.exit(1)
print(f"entered lvl{lvl}: settle={settle:.2f}s (clue_match 匹配墙钟)", flush=True)

# 起涂点：clue_match 匹配后 + 0.25s 保险（锁 ≈ 276 帧，与滑入动画同步结束）
time.sleep(0.25)
walls = M.walls_of(lvl - 1)
pts = [M.cell_nds(r, c) for r, c in walls]
tb = time.time()
ds.tap_batch(pts, gap=gap, hold=hold, after=after)
M.safe_mouseup()
burst_wall = time.time() - tb
print(f"burst {burst_wall:.2f}s 墙钟 ({len(pts)}格, {(burst_wall/len(pts))*1000:.0f}ms/格)", flush=True)

cleared = False
for k in range(120):
    if M.state() == "clear":
        cleared = True
        break
    time.sleep(0.1)
print(f"clear: {cleared} (burst后 {time.time()-tb:.1f}s 墙钟)", flush=True)

if cleared:
    time.sleep(1.5)
    im = ds.grab(f"turbo_l{lvl}")
    n = M.stars_gold(im)
    print(f"gold_stars={n}", flush=True)
    im.crop((0, 0, 256, 192)).resize((512, 384)).save(f"/tmp/turbo_top_l{lvl}.png")
    g = M.board_gray()
    miss = [w for w in walls if M.cell_state(g, *w) == "W"]
    print(f"漏涂: {len(miss)} {miss[:15]}", flush=True)
else:
    g = M.board_gray()
    miss = [w for w in walls if M.cell_state(g, *w) == "W"]
    print(f"未通关 漏涂: {len(miss)} {miss[:15]}", flush=True)
    M.ensure_select()
