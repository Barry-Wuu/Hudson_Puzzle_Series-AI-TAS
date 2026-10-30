#!/usr/bin/env python3
"""慢速 burst 实验：burst 期间用 SIGSTOP/SIGCONT 把 DeSMuME 降到 ratio 速度。

原理：显示时间 = 通关页帧 - 计时器启动帧；burst 占的游戏帧 = 墙钟xratio。
常速 70ms/格 burst 3.7s = 218帧 -> 显示 4.0s。
50% 速：burst = 109帧 -> 显示 ~2.2s；且帧长 33.4ms > hold 40ms 保证 0 丢击。

用法: python3 exp_slowmo.py <lvl> <ratio>
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
print(f"=== slowmo lvl{lvl} ratio={ratio} ===", flush=True)

pid = int(subprocess.run(["pgrep", "-x", "desmume-cli"],
                         capture_output=True, text=True).stdout.split()[0])
print("desmume pid", pid, flush=True)


class SlowMo:
    """跑 frame 墙钟 + 停 frame/ratio-frame 墙钟，循环。"""

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
ds.tap_batch(pts, gap=0.02, hold=0.04, after=0.01)
M.safe_mouseup()
burst_wall = time.time() - tb
sm.stop()
burst_frames = burst_wall * ratio * 60
print(f"burst {burst_wall:.2f}s 墙钟 = {burst_frames:.0f} 游戏帧 ({len(pts)}格)", flush=True)

# 等通关（常速）
cleared = False
for k in range(60):
    st = M.state()
    if st == "clear":
        cleared = True
        break
    time.sleep(0.2)
print(f"clear: {cleared} (burst后 {time.time()-tb:.1f}s)", flush=True)

if cleared:
    time.sleep(2.0)
    im = ds.grab(f"slow_l{lvl}")
    n = M.stars_gold(im)
    print(f"gold_stars={n}", flush=True)
    im.crop((0, 0, 256, 192)).resize((512, 384)).save(f"/tmp/slow_top_l{lvl}.png")
    im.crop((0, 192, 256, 384)).resize((512, 384)).save(f"/tmp/slow_bot_l{lvl}.png")
    # 读盘面漏涂（verify 前统计）
    g = M.board_gray()
    miss = [w for w in walls if M.cell_state(g, *w) == "W"]
    print(f"漏涂: {len(miss)} {miss[:20]}", flush=True)
else:
    # 读盘面看丢击
    g = M.board_gray()
    miss = [w for w in walls if M.cell_state(g, *w) == "W"]
    print(f"未通关 漏涂: {len(miss)} {miss[:20]}", flush=True)
    M.ensure_select()
