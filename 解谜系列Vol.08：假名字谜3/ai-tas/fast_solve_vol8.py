#!/usr/bin/env python3.11
"""Vol.08 第1关极速填字 —— 对齐 Vol.13 生产剂量实测。

对比:
  - 旧 solve_vol8_full.py: 每 tap after=0.35~0.45 + 每数字 sleep(0.2)
    + reset() 20 次箭头空点 + 每次 ds.tap 都 spawn 4 个 xdotool 进程 -> 游戏计时 69s
  - 本脚本: 轻量 lite_tap(单进程内联 sleep, 不每次 ensure_window),
    after=0.12 (Vol.13 生产默认), 无多余 sleep/reset -> 目标 20~30s

假设: 游戏已停在第1关干净盘面(视口 dr=0,dc=0)。
机制(实机确认): 点数字格选中 -> 点对应假名键 2 次填入; 视口靠四边箭头滚动。
"""
import time, subprocess, json, sys
import ds
import solve_vol8 as s

LEVEL = int(sys.argv[1]) if len(sys.argv) > 1 else 1   # 1-based
AFTER = float(sys.argv[2]) if len(sys.argv) > 2 else 0.12   # 点击间隔剂量(可调)

ARROW_UP = (90, 4)
ARROW_DOWN = (90, 107)
ARROW_LEFT = (11, 55)
ARROW_RIGHT = (165, 55)
GX0, GY0, PITCH = 24, 19, 26
MAX_DR, MAX_DC = 6, 4
HOLD, GAP = 0.06, 0.04
# AFTER 从命令行参数读取(见上方), 默认 0.12; 原硬编码 0.12 已移除


def lite_tap(x, y, after=AFTER):
    """单进程内联 xdotool, 不在每次点击时重复 ensure_window(windowmove+focus)。"""
    subprocess.run(
        ["xdotool", "mousemove", str(ds.WIN_X + x), str(ds.WIN_Y + 192 + y),
         "sleep", str(GAP), "mousedown", "1", "sleep", str(HOLD), "mouseup", "1"],
        env=ds.ENV)
    time.sleep(after)


def kana_tap(kana):
    kk = s.HIRA2KATA.get(kana, kana)
    pos = s.KANA_POS.get(kk)
    if not pos:
        print(f"  !! {kana}({kk}) 无键位", flush=True)
        return False
    lite_tap(*pos)   # 第1次选中
    lite_tap(*pos)   # 第2次确认填入
    return True


class View:
    def __init__(self):
        self.dr = 0
        self.dc = 0

    def go(self, tr, tc):
        tr = min(max(tr, 0), MAX_DR)
        tc = min(max(tc, 0), MAX_DC)
        while self.dr < tr:
            lite_tap(*ARROW_DOWN); self.dr += 1
        while self.dr > tr:
            lite_tap(*ARROW_UP); self.dr -= 1
        while self.dc < tc:
            lite_tap(*ARROW_RIGHT); self.dc += 1
        while self.dc > tc:
            lite_tap(*ARROW_LEFT); self.dc -= 1

    def cell(self, r, c):
        return (GX0 + PITCH * (c - self.dc), GY0 + PITCH * (r - self.dr))


def pick_cell(cells):
    best = None
    for r, c in cells:
        dc = min(max(c - 2, 0), MAX_DC)
        dr = min(max(r - 1, 0), MAX_DR)
        if not (0 <= c - dc < 6 and 0 <= r - dr < 4):
            dc = min(c, MAX_DC); dr = min(r, MAX_DR)
        cost = dr + dc
        if best is None or cost < best[0]:
            best = (cost, r, c, dr, dc)
    return best


def plan_tsp_order(targets):
    """给定 {数字: (dr,dc)} 视口目标, 从(0,0)出发求访问全部数字的最短滚动路径(Held-Karp)。
    targets 只含实际出现的数字; 返回的顺序使视口滚动步数最少。"""
    nums = sorted(targets)
    if not nums:
        return []
    idx = {n: i + 1 for i, n in enumerate(nums)}       # idx0=起点(0,0)
    pts = [(0, 0)] + [targets[n] for n in nums]
    def dist(i, j):
        return abs(pts[i][0] - pts[j][0]) + abs(pts[i][1] - pts[j][1])
    N = len(nums)
    INF = 10 ** 9
    FULL = 1 << N
    dp = [[INF] * (N + 1) for _ in range(FULL)]
    par = [[-1] * (N + 1) for _ in range(FULL)]
    for j in range(1, N + 1):
        dp[1 << (j - 1)][j] = dist(0, j)
    for mask in range(FULL):
        for j in range(1, N + 1):
            if not (mask >> (j - 1)) & 1:
                continue
            cur = dp[mask][j]
            if cur >= INF:
                continue
            for k in range(1, N + 1):
                if (mask >> (k - 1)) & 1:
                    continue
                nm = mask | (1 << (k - 1))
                nv = cur + dist(j, k)
                if nv < dp[nm][k]:
                    dp[nm][k] = nv
                    par[nm][k] = j
    full = FULL - 1
    end = min(range(1, N + 1), key=lambda j: dp[full][j])
    seq, m, j = [], full, end
    while j != -1:
        seq.append(nums[j - 1])
        pj = par[m][j]
        m ^= (1 << (j - 1))
        j = pj
    return seq[::-1]


def main():
    w = ds.ensure_window()
    subprocess.run(["xdotool", "windowfocus", w], env=ds.ENV)
    time.sleep(0.15)
    p = json.load(open(s.ANS, encoding="utf-8"))[LEVEL - 1]
    g, wd, ht, mp = p["grid"], p["w"], p["h"], p["mapping"]
    pos = {n: [(r, c) for r in range(ht) for c in range(wd)
               if g[r * wd + c] != 0x7f and (g[r * wd + c] & 0x7f) == n]
           for n in range(1, 17)}
    # 为每个数字定代表格 -> 视口目标; 再用 TSP 求最速填写顺序
    cell_of, target = {}, {}
    for n in range(1, 17):
        if pos[n]:
            _, r, c, dr, dc = pick_cell(pos[n])
            cell_of[n] = (r, c)
            target[n] = (dr, dc)
    order = plan_tsp_order(target)
    print(f"第{LEVEL}关 {p['w']}x{p['h']}  TSP顺序={order}", flush=True)

    v = View()
    t0 = time.time()
    scroll_steps = 0
    done = []
    for n in order:
        dr, dc = target[n]
        scroll_steps += abs(dr - v.dr) + abs(dc - v.dc)
        v.go(dr, dc)
        r, c = cell_of[n]
        x, y = v.cell(r, c)
        if not (0 <= x < 256 and 0 <= y < 192):
            continue
        lite_tap(x, y)                                  # 选中数字格
        kana_tap(mp.get(n, mp.get(str(n))))             # 假名键点2次
        done.append(n)
    dt = time.time() - t0
    ds.grab("fast_filled")
    print(f"填字墙钟 {dt:.2f}s, 视口滚动 {scroll_steps} 步, done={done}", flush=True)


if __name__ == "__main__":
    main()
