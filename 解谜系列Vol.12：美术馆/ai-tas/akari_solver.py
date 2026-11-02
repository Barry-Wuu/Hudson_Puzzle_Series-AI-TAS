#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Akari（美術館）求解器：从 puzzles.json 的 given（墙+数字）求合法解。

规则：灯照亮同行同列至墙；灯互不相照；数字墙邻居灯数恰为数字；全部白格被照亮。
用法：python3.11 akari_solver.py <关卡号>...   （无参数 = 求解全部 110 关并报告）
"""
import json
import os
import sys


def solve(w, h, given):
    """given: 长度 w*h 字符串，'-'=空格，其他=墙（数字或字符）。返回灯集合或 None。"""
    walls = set()
    nums = {}
    for y in range(h):
        for x in range(w):
            ch = given[y * w + x]
            if ch == "-":
                continue
            walls.add((x, y))
            if ch.isdigit():
                nums[(x, y)] = int(ch)
    whites = [(x, y) for y in range(h) for x in range(w) if (x, y) not in walls]

    # see[x,y] = 从 (x,y) 沿四方向直到墙能看到的白格（含自身）
    see = {}
    for (x, y) in whites:
        s = {(x, y)}
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            while 0 <= nx < w and 0 <= ny < h and (nx, ny) not in walls:
                s.add((nx, ny))
                nx += dx
                ny += dy
        see[(x, y)] = s

    lit_possible = {}   # 白格 -> 可能照亮它的位置集（含自身）
    for c0 in whites:
        lit_possible[c0] = see[c0]

    state = {}          # (x,y) -> True(灯)/False(无灯)；未定不在 state
    fixed_on, fixed_off = set(), set()

    def neighbors(x, y):
        return [(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))]

    def propagate():
        """约束传播。返回 False=矛盾。"""
        changed = True
        while changed:
            changed = False
            # 1. 灯不相照：fixed_on 的 see 集 → 全部 fixed_off
            for L in list(fixed_on):
                for c0 in see[L]:
                    if c0 not in fixed_on and c0 not in fixed_off:
                        fixed_off.add(c0)
                        changed = True
            # 2. 数字墙精确约束
            for (wx, wy), k in nums.items():
                nb = neighbors(wx, wy)
                on = [p for p in nb if p in fixed_on]
                unk = [p for p in nb if p not in fixed_on and p not in fixed_off
                       and p not in walls]
                if len(on) > k or len(on) + len(unk) < k:
                    return False
                if len(on) == k and unk:
                    for p in unk:
                        fixed_off.add(p)
                    changed = True
                if len(on) + len(unk) == k and unk:
                    for p in unk:
                        fixed_on.add(p)
                    changed = True
            # 3. 照亮覆盖：每白格的可照亮源 = see 反向 ∩ 非 fixed_off
            for c0 in whites:
                if c0 in fixed_on:
                    continue
                src = [p for p in lit_possible[c0] if p not in fixed_off]
                if not src:
                    return False
                if len(src) == 1 and src[0] not in fixed_on:
                    fixed_on.add(src[0])
                    changed = True
        return True

    def search():
        if not propagate():
            return None
        # 找未定白格（MRV：可照亮源最少）
        best, best_srcs = None, None
        for c0 in whites:
            if c0 in fixed_on or c0 in fixed_off:
                continue
            srcs = [p for p in lit_possible[c0] if p not in fixed_off]
            if best is None or len(srcs) < len(best_srcs):
                best, best_srcs = c0, srcs
                if len(srcs) <= 2:
                    break
        if best is None:
            return set(fixed_on)
        for choice in (True, False):
            f_on, f_off = set(fixed_on), set(fixed_off)
            if choice:
                fixed_on.add(best)
            else:
                fixed_off.add(best)
            r = search()
            if r is not None:
                return r
            fixed_on.clear(); fixed_on.update(f_on)
            fixed_off.clear(); fixed_off.update(f_off)
        return None

    # 递归深度：用显式栈防 336 格递归爆栈 —— 规模小直接递归，sys.setrecursionlimit 拉高
    sys.setrecursionlimit(100000)
    return search()


def load_puzzles():
    pj = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "..", "validation", "puzzles.json")
    data = json.load(open(pj, encoding="utf-8"))
    # 兼容 seg3 驱动的 _SEQ 结构（list）或 dict
    if isinstance(data, dict):
        for k in ("puzzles", "levels", "data"):
            if k in data:
                data = data[k]
                break
    return data


if __name__ == "__main__":
    data = load_puzzles()
    idx = sys.argv[1:]
    ns = [int(i) for i in idx] if idx else list(range(1, len(data) + 1))
    nbad = 0
    for n in ns:
        pz = data[n - 1]
        w, h = pz["w"], pz["h"]
        sol = solve(w, h, pz["given"])
        if sol is None:
            print(f"Q{n}: 无解！！")
            nbad += 1
            continue
        # 自检：全照亮 + 数字满足 + 不互照
        walls = {(x, y) for y in range(h) for x in range(w)
                 if pz["given"][y * w + x] != "-"}
        ok = True
        for y in range(h):
            for x in range(w):
                if (x, y) in walls:
                    continue
                seen = any((x, y) in {p for p in [(x, y)]} for p in [])  # placeholder
        # 用 see 逻辑快速自检
        litset = set()
        for (lx, ly) in sol:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = lx, ly
                while 0 <= nx < w and 0 <= ny < h and (nx, ny) not in walls:
                    litset.add((nx, ny))
                    nx += dx; ny += dy
        for y in range(h):
            for x in range(w):
                if (x, y) not in walls and (x, y) not in litset:
                    ok = False
        for (wx, wy), k in {(x, y): int(pz["given"][y * w + x])
                            for y in range(h) for x in range(w)
                            if pz["given"][y * w + x].isdigit()}.items():
            cnt = sum((wx + dx, wy + dy) in sol
                      for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            if cnt != k:
                ok = False
        # 不互照
        for (lx, ly) in sol:
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = lx + dx, ly + dy
                while 0 <= nx < w and 0 <= ny < h and (nx, ny) not in walls:
                    if (nx, ny) in sol:
                        ok = False
                    nx += dx; ny += dy
        old = {(b[0], b[1]) for b in pz["bulbs"]}
        print(f"Q{n} {w}x{h}: 求解 {len(sol)} 灯 自检={'OK' if ok else 'FAIL'}"
              f"  与旧bulbs相同={sol == old}  旧bulbs数={len(old)}")
        if not ok:
            nbad += 1
    print(f"\n异常 {nbad}/{len(ns)}")
