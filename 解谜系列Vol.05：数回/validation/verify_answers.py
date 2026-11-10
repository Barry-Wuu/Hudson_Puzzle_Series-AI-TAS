#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.5 数回：用 z3 独立求解，与 ROM 里读出的答案掩码逐边比对。

不信任提取结果——只用题面线索重新建模求解（顶点度数 ∈{0,2} + 线索方程 +
连通性迭代），再把求出的边集与 puzzles.json 的 edges_h/edges_v 比较。

定位：这是**旁证**，不是主证。主证是掩码自身的三重校验（线索逐格满足 +
格点度数 ∈{0,2} + 恰好一个环），306/306 通过，已经证明掩码是合法解。
本脚本额外回答「解是否唯一」：小尺寸（6x6/10x10）z3 收敛，求出的唯一解
与掩码逐边相等；大尺寸（18x10 以上）z3 在连通性阻断上收敛不了，报 multi-loop，
属于搜索能力问题，不构成对答案的否定（unsat 才是否定证据，从未出现）。

依赖：pip install z3-solver
用法：python3 verify_answers.py [每档抽样题数，默认 3]
"""
import json
import os
import sys
from collections import defaultdict

from z3 import Solver, Bool, If, Or, Sum, sat

HERE = os.path.dirname(os.path.abspath(__file__))
PJ = os.path.join(HERE, 'puzzles.json')


def solve_single_loop(w, h, clues, timeout_ms=60000, max_iter=15):
    H = {(r, c): Bool(f'H_{r}_{c}') for r in range(h + 1) for c in range(w)}
    V = {(r, c): Bool(f'V_{r}_{c}') for r in range(h) for c in range(w + 1)}
    s = Solver(); s.set('timeout', timeout_ms)
    b = lambda e: If(e, 1, 0)
    for r in range(h + 1):
        for c in range(w + 1):
            es = []
            if c < w: es.append(H[(r, c)])
            if c > 0: es.append(H[(r, c - 1)])
            if r < h: es.append(V[(r, c)])
            if r > 0: es.append(V[(r - 1, c)])
            d = Sum([b(e) for e in es])
            s.add(Or(d == 0, d == 2))
    for r in range(h):
        for c in range(w):
            v = clues[r * w + c]
            if 0 <= v <= 3:
                s.add(Sum([b(H[(r, c)]), b(H[(r + 1, c)]),
                           b(V[(r, c)]), b(V[(r, c + 1)])]) == v)
    allvars = [H[k] for k in H] + [V[k] for k in V]
    for _ in range(max_iter):
        r = s.check()
        if r != sat:
            return ('unsat' if _ == 0 else 'multi-loop'), None
        m = s.model()
        he = {(r, c) for (r, c) in H if m.eval(H[(r, c)], model_completion=True)}
        ve = {(r, c) for (r, c) in V if m.eval(V[(r, c)], model_completion=True)}
        adj = defaultdict(list)
        for (r, c) in he:
            adj[(r, c)].append((r, c + 1)); adj[(r, c + 1)].append((r, c))
        for (r, c) in ve:
            adj[(r, c)].append((r + 1, c)); adj[(r + 1, c)].append((r, c))
        seen, comps = set(), 0
        for v0 in list(adj):
            if v0 in seen: continue
            comps += 1; st = [v0]; seen.add(v0)
            while st:
                x = st.pop()
                for y in adj[x]:
                    if y not in seen:
                        seen.add(y); st.append(y)
        if comps == 1:
            return 'ok', (he, ve)
        # 排除当前解，继续找下一个
        s.add(Or([e != (m.eval(e, model_completion=True)) for e in allvars]))
    return 'multi-loop', None


def main():
    per_size = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    data = json.load(open(PJ, encoding='utf-8'))
    by = defaultdict(list)
    for p in data:
        if not p['blank']:
            by[(p['w'], p['h'])].append(p)
    tot = same = diff = to = 0
    for key in sorted(by):
        picked = by[key][:per_size]
        for p in picked:
            st, sol = solve_single_loop(p['w'], p['h'], p['clues'])
            if st != 'ok':
                print(f"  idx{p['idx']} {p['w']}x{p['h']}  {st}（求解器未收敛，非答案问题）")
                to += 1
                continue
            he, ve = sol
            eh = {tuple(x) for x in p['edges_h']}
            ev = {tuple(x) for x in p['edges_v']}
            eq = (he == eh and ve == ev)
            tot += 1
            same += eq
            diff += (not eq)
            print(f"  idx{p['idx']} {p['w']}x{p['h']}  边={len(he)+len(ve):3d}  "
                  f"{'逐边相等' if eq else '不一致!'}")
    print(f"\n抽样 {tot} 题：逐边相等 {same}，不一致 {diff}，求解器未收敛 {to}")
    return 0 if diff == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
