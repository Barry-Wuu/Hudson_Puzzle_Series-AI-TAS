#!/usr/bin/env python3
"""慢速 burst + verify 补点全流程：务必通关并读星级（5★ 阈值探针）。

用法: python3 exp_slowmo2.py <lvl> <ratio>
"""
import os
import signal
import subprocess
import sys
import threading
import time

sys.path.insert(0, "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas")
import ds
import mode2_fast as M

lvl = int(sys.argv[1])
ratio = float(sys.argv[2]) if len(sys.argv) > 2 else 0.5
GAP = float(sys.argv[3]) if len(sys.argv) > 3 else 0.02
HOLD = float(sys.argv[4]) if len(sys.argv) > 4 else 0.08
AFTER = float(sys.argv[5]) if len(sys.argv) > 5 else 0.01
print(f"=== slowmo2 lvl{lvl} ratio={ratio} tap=({GAP},{HOLD},{AFTER}) -> {(GAP+HOLD+AFTER)*1000:.0f}ms/格 ===", flush=True)

pid = int(subprocess.run(["pgrep", "-x", "desmume-cli"],
                         capture_output=True, text=True).stdout.split()[0])


class SlowMo:
    def __init__(self, pid, ratio):
        self.pid, self.ratio = pid, ratio
        self.on = False
        self.th = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        frame = 1.0 / 60.0
        run = frame
        stop = frame / self.ratio - frame
        while True:
            if self.on:
                os.kill(self.pid, signal.SIGCONT)
                t = time.perf_counter()
                while time.perf_counter() - t < run - 0.001:
                    pass
                os.kill(self.pid, signal.SIGSTOP)
                t = time.perf_counter()
                while time.perf_counter() - t < stop - 0.001:
                    pass
            else:
                os.kill(self.pid, signal.SIGCONT)
                time.sleep(0.02)

    def start(self):
        self.on = True
        self.th.start()
        time.sleep(0.1)

    def stop(self):
        self.on = False
        os.kill(self.pid, signal.SIGCONT)
        time.sleep(0.15)


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

sm = SlowMo(pid, ratio)
sm.start()
walls = M.walls_of(lvl - 1)
pts = [M.cell_nds(r, c) for r, c in walls]
tb = time.time()
ds.tap_batch(pts, gap=GAP, hold=HOLD, after=AFTER)
M.safe_mouseup()
burst_wall = time.time() - tb
burst_frames = burst_wall * ratio * 60
print(f"burst {burst_wall:.2f}s = {burst_frames:.0f} 游戏帧 ({len(pts)}格)", flush=True)

# 慢速下补点（只补纯白格）
for k in range(6):
    if M.state() == "clear":
        break
    time.sleep(0.6)
    g = M.board_gray()
    miss = M.white_misses(g, walls)
    if not miss:
        break
    print(f"  [verify k{k}] miss={len(miss)} {miss[:10]}", flush=True)
    for (r, c) in miss:
        ds.tap(*M.cell_nds(r, c), **M.VERIFY_TAP)
    M.safe_mouseup()
sm.stop()

# 常速等通关
cleared = False
for k in range(80):
    if M.state() == "clear":
        cleared = True
        break
    time.sleep(0.2)
print(f"clear: {cleared} (burst后 {time.time()-tb:.1f}s)", flush=True)

if cleared:
    time.sleep(2.0)
    im = ds.grab(f"sm2_l{lvl}")
    n = M.stars_gold(im)
    print(f"gold_stars={n}", flush=True)
    im.crop((0, 0, 256, 192)).resize((512, 384)).save(f"/tmp/sm2_top_l{lvl}.png")
    im.crop((0, 192, 256, 384)).resize((512, 384)).save(f"/tmp/sm2_bot_l{lvl}.png")
else:
    g = M.board_gray()
    miss = M.white_misses(g, walls)
    print(f"未通关 漏涂: {len(miss)} {miss[:15]}", flush=True)
    M.ensure_select()
