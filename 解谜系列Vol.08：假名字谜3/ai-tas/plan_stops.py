#!/usr/bin/env python3.11
"""视口停靠规划: 集合覆盖 + Dijkstra 最短路径。
状态(视口, 已覆盖数字mask), 从(0,0)出发, 求覆盖全部数字的最小滚动步数路径。
允许经过"不带来新数字"的视口(为到达远处), 因为转移只更新位置不要求mask变化。
"""
import heapq


def visible(pos_n, dr, dc):
    return any(dr <= r <= dr + 3 and dc <= c <= dc + 5 for r, c in pos_n)


def plan_stops(pos, MAX_DR=6, MAX_DC=4):
    nums = sorted(n for n in pos if pos[n])
    nb = {n: i for i, n in enumerate(nums)}
    FULL = (1 << len(nums)) - 1
    views = [(dr, dc) for dr in range(MAX_DR + 1) for dc in range(MAX_DC + 1)]
    cover = {}
    for dr, dc in views:
        m = 0
        for n in nums:
            if visible(pos[n], dr, dc):
                m |= 1 << nb[n]
        cover[(dr, dc)] = m

    START = (0, 0)
    INF = 10 ** 9
    # dist[(view, mask)] = 最小步数
    dist = {(START, cover[START]): 0}
    par = {}
    heap = [(0, START, cover[START])]
    while heap:
        d, v, mask = heapq.heappop(heap)
        if d > dist.get((v, mask), INF):
            continue
        if mask == FULL:
            break
        for v2 in views:
            if v2 == v:
                continue
            step = abs(v[0] - v2[0]) + abs(v[1] - v2[1])
            nm = mask | cover[v2]
            nd = d + step
            key = (v2, nm)
            if nd < dist.get(key, INF):
                dist[key] = nd
                par[key] = (v, mask)
                heapq.heappush(heap, (nd, v2, nm))

    # 找终点(覆盖FULL的最小步数状态)
    end = min(((d, k) for k, d in dist.items() if k[1] == FULL), key=lambda x: x[0])
    steps, state = end
    # 回溯只保留"带来新数字"的停靠点 + 起点
    path = []
    cur = state
    while cur in par:
        path.append(cur[0])
        cur = par[cur]
    path.append(START)
    path = path[::-1]
    # 精简: 只保留起点 + 覆盖有增长的视口
    stops = [START]
    seen = cover[START]
    for v in path[1:]:
        if cover[v] & ~seen:
            stops.append(v)
            seen |= cover[v]
    return stops, steps


if __name__ == "__main__":
    import json
    import solve_vol8 as s
    data = json.load(open(s.ANS, encoding="utf-8"))
    for lv in [1, 2, 3, 5, 10]:
        p = data[lv - 1]
        g, wd, ht = p["grid"], p["w"], p["h"]
        pos = {n: [(r, c) for r in range(ht) for c in range(wd)
                   if g[r * wd + c] != 0x7f and (g[r * wd + c] & 0x7f) == n]
               for n in range(1, 17)}
        stops, steps = plan_stops(pos)
        print(f"第{lv}关 {wd}x{ht}: {steps}步 停靠{stops}")
