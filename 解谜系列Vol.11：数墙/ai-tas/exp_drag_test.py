#!/usr/bin/env python3
"""实测「拖动连涂」是否掉格：mousedown 起点 -> 连续 mousemove 过中间格 -> mouseup 终点。

对比三种 dwell（每格停留）：0.10(慢) / 0.07(中) / 0.04(快)。
读盘统计这段墙格里变黑(B)/漏白(W)/灰(A)数量，验证拖动是否可靠。
"""
import sys
import time
import subprocess
from collections import defaultdict

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import numpy as np
import mode2_fast as M

lvl = 81
idx = lvl - 1
walls = M.walls_of(idx)

# 找 oc=0 可见(c<10)的最长水平连续墙段
rows = defaultdict(list)
for r, c in walls:
    if c < 10:
        rows[r].append(c)
seg = None
for r in sorted(rows):
    cs = sorted(rows[r])
    run, best = [], None
    for c in cs:
        if not run or c == run[-1] + 1:
            run.append(c)
        else:
            if best is None or len(run) > len(best):
                best = run
            run = [c]
    if best is None or len(run) > len(best):
        best = run
    if best and (seg is None or len(best) > len(seg[1])):
        seg = (r, best)
r, cs = seg
print(f"测试段: 行{r} 列{cs[0]}..{cs[-1]} 长{len(cs)}", flush=True)


def to_win(nx, ny):
    return (ds.WIN_X + nx, ds.WIN_Y + 192 + ny)


def drag(seg_r, seg_cs, dwell):
    pts = [M.cell_nds(seg_r, c) for c in seg_cs]
    sx, sy = to_win(*pts[0])
    args = ["xdotool", "mousemove", str(sx), str(sy), "mousedown", "1"]
    for nx, ny in pts[1:]:
        wx, wy = to_win(nx, ny)
        args += ["mousemove", str(wx), str(wy), "sleep", str(dwell)]
    args += ["mouseup", "1"]
    subprocess.run(args, env=ds.ENV)
    time.sleep(0.6)
    g = M.board_gray()
    black = [c for c in seg_cs if M.cell_state(g, seg_r, c) == "B"]
    white = [c for c in seg_cs if M.cell_state(g, seg_r, c) == "W"]
    ano = [c for c in seg_cs if M.cell_state(g, seg_r, c) == "A"]
    print(f"  drag dwell={dwell}: 黑{len(black)} 白{len(white)}{white} 灰{len(ano)}", flush=True)
    return len(white)


if not M.ensure_select():
    print("FAIL: cannot reach select")
    sys.exit(1)

for dwell in (0.10, 0.07, 0.04):
    t0 = M.enter_level(lvl)
    M.scroll_to_oc_rect(0)
    time.sleep(0.3)
    if hasattr(M, "wait_unlocked"):
        M.wait_unlocked(idx, (r, cs[0]))
    else:
        time.sleep(4.5)
    drag(r, cs, dwell)
    M.ensure_select()
    time.sleep(0.3)
print("done", flush=True)
