#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.12：美術館 / AKARI（BIJUTUKAN / AVVJ）题库提取器 + 攻略生成。

数据层结论（2026-10-27 逆向，全部经 AKARI 规则自检）：
- 主游戏题库在 arm9 偏移 0xA9D30 处的 4 档索引表（顺序为 id3,id2,id1,id0，非升序）：
    id0=入門(20)  id1=やさしい(100)  id2=ふつう(110)  id3=むずかしい(70)，合计 300 题。
  （同 arm9 还内嵌数墙主表 @0x708B0、体験版 Hitori @0x97250、体験版 AKARI @0xA9D40，
   本脚本只提取美術館主游戏 0xA9D30。）
- 每档索引表 = 4 条 (count<<16|id, 记录区 RAM 指针)；记录 12 字节：
    [w u8][h u8][00 00][给定平面指针 u32][解答平面指针 u32]。
- 两平面各 w*h 字节，共享平面池（RAM 0x02000000 区），编码如下：
    【给定平面】0x2D=白格(可放灯)；0x58=黑墙(无号)；0..4=带号黑墙(相邻灯数)。
    【解答平面】0x2D=白格无灯；0x40=白格有灯(★TAS 答案)；0x23=黑墙(无号)；0..4=带号黑墙。
"""
import struct
import json
import os
import sys

ROM = sys.argv[1] if len(sys.argv) > 1 else '/root/.codebuddy/artifact/vol12/解谜系列Vol. 12：美术馆.nds'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'validation', 'puzzles.json')
BASE = 0x02000000
AKARI_TABLE_OFF = 0xA9D30
DIFF_NAMES = {0: '入門', 1: 'やさしい', 2: 'ふつう', 3: 'むずかしい'}

# 字节编码
G_WHITE = 0x2D
G_WALL = 0x58
S_WHITE = 0x2D
S_BULB = 0x40
S_WALL = 0x23


def load_arm9(path):
    d = open(path, 'rb').read()
    a9off = struct.unpack_from('<I', d, 0x20)[0]
    a9sz = struct.unpack_from('<I', d, 0x2C)[0]
    return d[a9off:a9off + a9sz]


def parse_table(a9, table_off):
    out = {}
    for i in range(4):
        v, ptr = struct.unpack_from('<II', a9, table_off + 8 * i)
        count, did = v >> 16, v & 0xFFFF
        out[did] = (count, ptr)
    return out


def parse_records(a9, ptr, count):
    recs = []
    off = ptr - BASE
    for i in range(count):
        w, h = a9[off + 12 * i], a9[off + 12 * i + 1]
        p_given, p_sol = struct.unpack_from('<II', a9, off + 12 * i + 4)
        recs.append((w, h, p_given, p_sol))
    return recs


def read_plane(a9, addr, w, h):
    off = addr - BASE
    return list(a9[off:off + w * h])


def decode(puz):
    """从 (w,h,given,sol) 解出墙/号/灯结构，返回网格：
    grid[r*w+c] = ('W', has_bulb) | ('wall', number_or_None)"""
    w, h, given, sol = puz
    g = []
    for i in range(w * h):
        gb, sb = given[i], sol[i]
        if gb == G_WHITE:
            g.append(('W', sb == S_BULB))
        elif gb == G_WALL:
            g.append(('wall', None))
        elif 0 <= gb <= 4:
            g.append(('wall', gb))
        else:
            g.append(('?', gb))
    return g


def validate(puz):
    """AKARI 规则自检。返回错误列表。"""
    w, h, given, sol = puz
    grid = decode(puz)
    errs = []
    bulbs = [(i % w, i // w) for i, c in enumerate(grid) if c[0] == 'W' and c[1]]
    # 1) 灯必须在白格（已隐含），且 given 该格确为白
    for (c, r) in bulbs:
        if grid[r * w + c] != ('W', True):
            errs.append('灯位非白格 (%d,%d)' % (c, r))
    # 2) 带号墙相邻灯数 == 号
    for i, cell in enumerate(grid):
        if cell[0] == 'wall' and cell[1] is not None:
            c, r = i % w, i // w
            n = sum(1 for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1))
                    if 0 <= c + dc < w and 0 <= r + dr < h
                    and grid[(r + dr) * w + (c + dc)] == ('W', True))
            if n != cell[1]:
                errs.append('号墙@(%d,%d)=%d 实际相邻灯 %d' % (c, r, cell[1], n))
    # 3) 灯互不直视（同行/列中间无墙）
    for (c, r) in bulbs:
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            cc, rr = c + dc, r + dr
            while 0 <= cc < w and 0 <= rr < h:
                cell = grid[rr * w + cc]
                if cell[0] == 'wall':
                    break
                if cell == ('W', True) and (cc, rr) != (c, r):
                    errs.append('灯(%d,%d)与灯(%d,%d)直视' % (c, r, cc, rr))
                    break
                cc += dc
                rr += dr
    # 4) 每个白格被照亮（同行/列有灯且中间无墙）
    for i, cell in enumerate(grid):
        if cell[0] == 'W' and not cell[1]:
            c, r = i % w, i // w
            lit = False
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                cc, rr = c + dc, r + dr
                while 0 <= cc < w and 0 <= rr < h:
                    cur = grid[rr * w + cc]
                    if cur == ('W', True):
                        lit = True
                        break
                    if cur[0] == 'wall':
                        break
                    cc += dc
                    rr += dr
            if not lit:
                errs.append('白格(%d,%d)未被照亮' % (c, r))
    # 5) 解中灯数应与题目白格数一致（粗检：无非法字节）
    for i, cell in enumerate(grid):
        if cell[0] == '?':
            errs.append('非法字节@(%d,%d)=%s' % (i % w, i // w, cell[1]))
    return errs


def main():
    a9 = load_arm9(ROM)
    table = parse_table(a9, AKARI_TABLE_OFF)
    puzzles = {}
    total = 0
    bad = 0
    for did in sorted(table):
        count, ptr = table[did]
        name = DIFF_NAMES[did]
        recs = parse_records(a9, ptr, count)
        puzzles[name] = []
        for idx, (w, h, p_g, p_s) in enumerate(recs):
            given = read_plane(a9, p_g, w, h)
            sol = read_plane(a9, p_s, w, h)
            puz = (w, h, given, sol)
            errs = validate(puz)
            total += 1
            if errs:
                bad += 1
                print('✗ %s rec#%02d (%dx%d): %s' % (name, idx + 1, w, h, '; '.join(errs[:3])))
            # 记录结构化答案
            grid = decode(puz)
            bulbs = [i for i, c in enumerate(grid) if c == ('W', True)]
            numbered = [(i % w, i // w, c[1]) for i, c in enumerate(grid) if c[0] == 'wall' and c[1] is not None]
            puzzles[name].append({
                'rec': idx + 1, 'w': w, 'h': h,
                'given': given, 'sol': sol,
                'bulbs': [(b % w, b // w) for b in bulbs],
                'numbered': numbered, 'ok': not errs,
            })
        sizes = sorted(set((r['w'], r['h']) for r in puzzles[name]))
        print('%s: %d 题, 规格集 %s' % (name, len(puzzles[name]), sizes))
    print('合计 %d 题, 自检失败 %d' % (total, bad))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(puzzles, open(OUT, 'w'), ensure_ascii=False)
    print('已写出', OUT)
    return bad


if __name__ == '__main__':
    sys.exit(1 if main() else 0)
