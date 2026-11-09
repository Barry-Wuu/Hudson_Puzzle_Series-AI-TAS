#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.9（数独2 / SUDOKU 2）题库提取器 —— 从 ROM 静态挖出 410 关的题面与答案。

方法论（与其它卷一致）：答案是 ROM 里现成的二进制数据表，**开录前静态提取**，
不是求解器现场推算，也不靠逐关读屏。

ROM 结构（实测，Vol.09 / 8MiB）：
  偏移 0x323330（十进制 3290672）起，连续 410 个 **164 字节**定长块：
    [0:81]    题面：81 个单字节，0=空格，1..9=给定数字
    [81:162]  答案：81 个单字节，1..9，即该关完整解
    [162:164] 填充/标志，恒 00 00
  410 块 = 練習問題 20 + やさしい 20 + ふつう 130 + むずかしい 230 + 超難問 10，
  顺序即游戏选关顺序（已用实机录播首帧逐档抽样比对，见 validate_order() 注释）。

  段位認定問題（ブロンズ/シルバー/ゴールド/プラチナ）**不在**这个表里——
  全 ROM 按 4 字节对齐扫过，410 块连续段之后没有任何合法题块，认定题是现场生成的。

自检（全 410 关逐关执行，任一失败即报错）：
  ① 题面合法：行/列/宫内给定数字互不重复；
  ② 答案平面是合法数独解（每行/列/宫恰好 1..9）；
  ③ 答案覆盖所有给定格（给定处与答案一致）；
  ④ 题面回溯求解恰好 1 个解，且该解与 ROM 答案平面逐格一致。

用法：
  python3 extract_vol9_answers.py [ROM路径]
默认 ROM: /workspace/roms/解谜系列Vol.09：数独2.nds
产出：validation/puzzles.json —— 410 关结构化数据（题面 + 答案 + 难度/档内编号/空格数）
"""
import os
import sys
import json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'validation', 'puzzles.json')
DEFAULT_ROM = '/workspace/roms/解谜系列Vol.09：数独2.nds'

BASE = 3290672
BLOCK = 164
GRID = 81
# (难度名, 该档关卡数)，顺序即 410 块的全局顺序
DIFFS = [('練習問題', 20), ('やさしい', 20), ('ふつう', 130), ('むずかしい', 230), ('超難問', 10)]
TOTAL = sum(n for _, n in DIFFS)


def load_grids(rom):
    a = np.fromfile(rom, dtype=np.uint8)
    out = []
    for i in range(TOTAL):
        off = BASE + i * BLOCK
        blk = a[off:off + BLOCK]
        if len(blk) < BLOCK:
            raise RuntimeError('题库块越界：第 %d 块' % (i + 1))
        puzzle = [int(x) for x in blk[:GRID]]
        sol = [int(x) for x in blk[GRID:GRID * 2]]
        tail = [int(x) for x in blk[GRID * 2:BLOCK]]
        if any(x > 9 for x in puzzle) or any(not 1 <= x <= 9 for x in sol):
            raise RuntimeError('第 %d 块取值越界' % (i + 1))
        out.append((puzzle, sol, tail))
    return out


def legal_givens(p):
    """① 题面给定互不重复（行/列/宫）"""
    g = [p[i * 9:(i + 1) * 9] for i in range(9)]
    for i in range(9):
        row = [x for x in g[i] if x]
        col = [g[r][i] for r in range(9) if g[r][i]]
        if len(row) != len(set(row)) or len(col) != len(set(col)):
            return False
    for br in range(0, 9, 3):
        for bc in range(0, 9, 3):
            blk = [g[r][c] for r in range(br, br + 3) for c in range(bc, bc + 3) if g[r][c]]
            if len(blk) != len(set(blk)):
                return False
    return True


def legal_solution(s):
    """② 答案是一个完整合法数独解"""
    if sorted(s) != sorted(list(range(1, 10)) * 9):
        return False
    g = [s[i * 9:(i + 1) * 9] for i in range(9)]
    for i in range(9):
        if len(set(g[i])) != 9 or len({g[r][i] for r in range(9)}) != 9:
            return False
    for br in range(0, 9, 3):
        for bc in range(0, 9, 3):
            if len({g[r][c] for r in range(br, br + 3) for c in range(bc, bc + 3)}) != 9:
                return False
    return True


def count_solutions(p, limit=2):
    """④ 回溯计数（最多数到 limit 个解就停）"""
    g = [p[i * 9:(i + 1) * 9][:] for i in range(9)]
    sols = []

    def ok(r, c, v):
        for i in range(9):
            if g[r][i] == v or g[i][c] == v:
                return False
        br, bc = 3 * (r // 3), 3 * (c // 3)
        for i in range(br, br + 3):
            for j in range(bc, bc + 3):
                if g[i][j] == v:
                    return False
        return True

    def rec():
        if len(sols) >= limit:
            return
        best, cand = None, None
        for r in range(9):
            for c in range(9):
                if g[r][c] == 0:
                    cs = [v for v in range(1, 10) if ok(r, c, v)]
                    if not cs:
                        return
                    if cand is None or len(cs) < len(cand):
                        best, cand = (r, c), cs
            if cand is not None and len(cand) == 1:
                break
        if best is None:
            sols.append([x for row in g for x in row])
            return
        r, c = best
        for v in cand:
            g[r][c] = v
            rec()
            g[r][c] = 0
            if len(sols) >= limit:
                return

    rec()
    return len(sols), (sols[0] if sols else None)


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROM
    if not os.path.exists(rom):
        sys.exit('找不到 ROM：%s' % rom)
    grids = load_grids(rom)
    print('读到 %d 个题库块' % len(grids))

    flat = []
    for d, n in DIFFS:
        flat += [d] * n
    assert len(flat) == TOTAL

    records, fails = [], []
    seen = {}
    for pos, (puzzle, sol, tail) in enumerate(grids):
        idx = pos + 1
        diff = flat[pos]
        seen[diff] = seen.get(diff, 0) + 1
        diff_idx = seen[diff]
        if not legal_givens(puzzle):
            fails.append((idx, '①题面不合法'))
        if not legal_solution(sol):
            fails.append((idx, '②答案不合法'))
        elif any(puzzle[i] and puzzle[i] != sol[i] for i in range(GRID)):
            fails.append((idx, '③答案未覆盖给定'))
        else:
            k, first = count_solutions(puzzle)
            if k != 1:
                fails.append((idx, '④解数=%d' % k))
            elif first != sol:
                fails.append((idx, '④求解结果与 ROM 答案不一致'))

        records.append({
            'idx': idx,
            'diff': diff,
            'diff_idx': diff_idx,
            'w': 9, 'h': 9,
            'puzzle': puzzle,
            'solution': sol,
            'blank': sum(1 for x in puzzle if x == 0),
        })

    if fails:
        print('自检失败 %d 项：' % len(fails))
        for f in fails[:20]:
            print('  ', f)
        sys.exit(1)

    print('自检通过：410 关全部满足「题面合法 / 答案合法 / 覆盖给定 / 唯一解 / 与 ROM 答案一致」')
    from collections import Counter
    c = Counter(r['diff'] for r in records)
    print('难度分布：', dict(c))
    print('空格数范围：%d–%d' % (min(r['blank'] for r in records), max(r['blank'] for r in records)))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(records, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print('已写出', OUT)


if __name__ == '__main__':
    main()
