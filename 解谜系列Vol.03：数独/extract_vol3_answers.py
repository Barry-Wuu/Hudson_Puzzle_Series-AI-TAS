#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.3（数独 / SUDOKU / ASQJ）题库提取器 —— 从 ROM 的 NitroFS 资源包挖出现成的题面+答案表。

方法论（与其它卷一致，用户定调）：答案是 ROM 里现成的二进制数据表，
**玩之前静态提取**，不是求解器现场推算，也不靠游戏内逐关读屏。

ROM 结构（实测，日版 ASQJ / 8MiB）：
  NitroFS fid=4（FAT 第 5 项，1.97MB 图形/数据资源包）头部是一张 u32 子块偏移表
  （单调递增，共 860 项）。表尾部连续 300 个子块，每块 648 字节 = 81*4*2：
    [0:324]   题面平面：81 个 u32 LE，0=空格，1..9=给定数字
    [324:648] 答案平面：81 个 u32 LE，1..9，即该关完整解
  300 块 = やさしい 70 + ふつう 140 + むずかしい 90
  （游戏选关页实测「クリアしている問題 000/070 / 000/140 / 000/090」，合计 300）。
  認定問題（めざせ！段位認定！プラチナ/ゴールド/シルバー/ブロンズ）复用这 300 关，
  ROM 里没有独立的段位题库块。

自检（全 300 关逐关执行，任一失败即报错）：
  ① 题面合法：行/列/宫内给定数字互不重复；
  ② 答案平面是合法数独解（每行/列/宫恰好 1..9）；
  ③ 答案平面覆盖所有给定格（给定处与题面一致）；
  ④ 题面回溯求解恰好 1 个解，且该解与 ROM 答案平面逐格一致。
  やさしい No.001 另与实机截图读出的题面/通关解交叉验证一致。

用法：
  python3.11 extract_vol3_answers.py [ROM路径]
默认 ROM: /workspace/roms/解谜系列Vol.03：数独.nds
产出（写到脚本同目录 validation/ 下）：
  puzzles.json   300 关结构化数据（题面 + 答案 + 难度/档内编号/空格数）
"""
import os
import sys
import json
import struct
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'validation', 'puzzles.json')
DEFAULT_ROM = '/workspace/roms/解谜系列Vol.03：数独.nds'

# (难度名, 该档关卡数)，顺序即题库块的全局顺序
DIFFS = [('やさしい', 70), ('ふつう', 140), ('むずかしい', 90)]
TOTAL = sum(n for _, n in DIFFS)
BLOCK_LEN = 648          # 81*4*2
GRID = 81


def load_file4(rom_path):
    """读 NitroFS fid=4 的原始字节（不写死绝对偏移，从 FAT 取）。"""
    d = open(rom_path, 'rb').read()
    fat = struct.unpack_from('<I', d, 0x48)[0]
    start, end = struct.unpack_from('<II', d, fat + 8 * 4)
    return d[start:end]


def parse_subblocks(f4):
    """解析头部 u32 子块偏移表，返回所有 648 字节块 (表内序号, 相对偏移, 字节)。"""
    offs = []
    i = 0
    while True:
        v = struct.unpack_from('<I', f4, i)[0]
        if v == 0 or v > len(f4):
            break
        offs.append(v)
        i += 4
    if len(offs) < 2 or any(offs[k] >= offs[k + 1] for k in range(len(offs) - 1)):
        raise RuntimeError('子块偏移表非法')
    blocks = []
    for k in range(len(offs) - 1):
        e = offs[k + 1]
        b = f4[offs[k]:e]
        if len(b) == BLOCK_LEN:
            blocks.append((k, offs[k], b))
    return offs, blocks


def u32_plane(b, base):
    return [struct.unpack_from('<I', b, base + 4 * i)[0] for i in range(GRID)]


def sudoku_ok(f):
    """f 是 81 个 1..9：每行/列/宫恰好 1..9 各一次。"""
    g = [f[i * 9:(i + 1) * 9] for i in range(9)]
    full = list(range(1, 10))
    for r in g:
        if sorted(r) != full:
            return False
    for c in range(9):
        if sorted(g[r][c] for r in range(9)) != full:
            return False
    for br in range(0, 9, 3):
        for bc in range(0, 9, 3):
            if sorted(g[r][c] for r in range(br, br + 3) for c in range(bc, bc + 3)) != full:
                return False
    return True


def legal_puzzle(f):
    """f 是 81 个 0..9（0=空格）：行/列/宫内给定数字互不重复，给定数在 17..60。"""
    if len(f) != GRID or any(v > 9 for v in f):
        return False
    nz = sum(1 for v in f if v)
    if not (17 <= nz <= 60):
        return False
    g = [f[i * 9:(i + 1) * 9] for i in range(9)]
    for r in g:
        s = [v for v in r if v]
        if len(s) != len(set(s)):
            return False
    for c in range(9):
        s = [g[r][c] for r in range(9) if g[r][c]]
        if len(s) != len(set(s)):
            return False
    for br in range(0, 9, 3):
        for bc in range(0, 9, 3):
            s = [g[r][c] for r in range(br, br + 3) for c in range(bc, bc + 3) if g[r][c]]
            if len(s) != len(set(s)):
                return False
    return True


def solve_unique(flat, limit=2):
    """回溯求前 limit 个解；返回解的列表（每项为 81 长一维列表）。"""
    G = [flat[i * 9:(i + 1) * 9] for i in range(9)]

    def ok(r, c, v):
        for i in range(9):
            if G[r][i] == v or G[i][c] == v:
                return False
        br, bc = 3 * (r // 3), 3 * (c // 3)
        for i in range(br, br + 3):
            for j in range(bc, bc + 3):
                if G[i][j] == v:
                    return False
        return True

    sols = []

    def rec():
        if len(sols) >= limit:
            return
        best, cand = None, None
        for r in range(9):
            for c in range(9):
                if G[r][c] == 0:
                    cs = [v for v in range(1, 10) if ok(r, c, v)]
                    if not cs:
                        return
                    if cand is None or len(cs) < len(cand):
                        best, cand = (r, c), cs
        if best is None:
            sols.append([v for row in G for v in row])
            return
        r, c = best
        for v in cand:
            G[r][c] = v
            rec()
            G[r][c] = 0
    rec()
    return sols


def global_to_diff(idx):
    """全局关卡号 -> (难度名, 档内编号)。"""
    base = 1
    for name, n in DIFFS:
        if idx < base + n:
            return name, idx - base + 1
        base += n
    raise ValueError('关卡号越界: %d' % idx)


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROM
    f4 = load_file4(rom)
    offs, blocks = parse_subblocks(f4)
    # 题库 = 尾部连续 300 个 648 字节块
    tail = blocks[-TOTAL:]
    if len(tail) != TOTAL or [b[0] for b in tail] != list(range(tail[0][0], tail[0][0] + TOTAL)):
        raise RuntimeError('未找到尾部连续 %d 个题库块（实得 %d）' % (TOTAL, len(blocks)))

    out = []
    for gi, (k, rel, b) in enumerate(tail, 1):
        puzzle = u32_plane(b, 0)
        answer = u32_plane(b, 324)
        if not legal_puzzle(puzzle):
            raise RuntimeError('第 %d 关题面不合法' % gi)
        if not sudoku_ok(answer):
            raise RuntimeError('第 %d 关答案平面不是合法数独解' % gi)
        if any(puzzle[i] and puzzle[i] != answer[i] for i in range(GRID)):
            raise RuntimeError('第 %d 关答案与给定数字冲突' % gi)
        sols = solve_unique(puzzle)
        if len(sols) != 1 or sols[0] != answer:
            raise RuntimeError('第 %d 关非唯一解或与 ROM 答案不符' % gi)
        diff, didx = global_to_diff(gi)
        out.append(dict(idx=gi, diff=diff, diff_idx=didx,
                        w=9, h=9, puzzle=puzzle, solution=answer,
                        blank=sum(1 for v in puzzle if v == 0)))

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False)
    print('题库块: %d 个（子块表 %d 项，题库 blk%d..blk%d）' %
          (len(out), len(offs), tail[0][0], tail[-1][0]))
    print('难度分布:', dict(Counter(r['diff'] for r in out)))
    print('空格数分布:', dict(sorted(Counter(r['blank'] for r in out).items())))
    print('全 300 关自检通过（题面合法 / 答案合法 / 覆盖给定 / 唯一解 / 与 ROM 答案一致）')
    print('已写出', OUT)


if __name__ == '__main__':
    main()
