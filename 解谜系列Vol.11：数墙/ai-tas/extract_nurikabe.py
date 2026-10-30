#!/usr/bin/env python3
"""Vol.11：数墙（NURIKABE / AUUJ18）题库提取器。

数据层结论（2026-10-19 首夜逆向，全部经实机截图交叉验证）：
- 题库内嵌 arm9（文件偏移见下），无 NitroFS 独立文件、无 overlay。
- 难度索引表：4 条 u32 对 = (count<<16 | 难度id, 记录区 RAM 指针)。
  id: 0=入門(20) 1=やさしい(100) 2=ふつう(100) 3=むずかしい(80)，合计 300 题。
- 记录 12 字节：[w u8][h u8][00 00][线索平面指针 u32][墙平面指针 u32]。
  两指针指向共享平面池（RAM 0x0207xxxx 区），每平面 w*h 字节：
  线索平面 u8（0=空格，≥1=线索数字）；墙平面 u8（0=白，1=墙 = 官方答案）。
- 同一 arm9 还有体验版题库：Hitori 表 @0x97290（300 题同构，
  平面=数字阵+涂块解）、Akari 表 @0xa9d80（仅 2 档）。本脚本只提取数墙主游戏。
"""
import struct, json, os, sys

ARM9 = sys.argv[1] if len(sys.argv) > 1 else '/root/.codebuddy/artifact/vol11/game.nds'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(__file__), '..', 'validation', 'puzzles.json')
BASE = 0x02000000

# 难度索引表（arm9 文件偏移）: (难度id, 中文名, count, 记录区 RAM 指针)
NURI_TABLE_OFF = 0x0708f0
DIFFS = {0: 'nyuumon', 1: 'yasashii', 2: 'futsuu', 3: 'muzukashii'}
DIFF_NAMES = {0: '入門', 1: 'やさしい', 2: 'ふつう', 3: 'むずかしい'}


def load_arm9(path):
    d = open(path, 'rb').read()
    a9off = struct.unpack_from('<I', d, 0x20)[0]
    a9sz = struct.unpack_from('<I', d, 0x2C)[0]
    return d[a9off:a9off + a9sz]


def parse_table(a9, table_off):
    """4 条 (count<<16|id, ptr)，返回 {id: (count, ptr)}。"""
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
        p_clue, p_wall = struct.unpack_from('<II', a9, off + 12 * i + 4)
        recs.append((w, h, p_clue, p_wall))
    return recs


def read_plane(a9, addr, w, h):
    off = addr - BASE
    return list(a9[off:off + w * h])


def check_nurikabe(w, h, clue, wall):
    """数墙规则自检。返回错误列表（空=通过）。"""
    errs = []
    n = w * h
    # 1) 线索和 = 白格数
    clue_sum = sum(clue)
    white = wall.count(0)
    if clue_sum != white:
        errs.append('线索和 %d != 白格数 %d' % (clue_sum, white))
    # 2) 每个白色连通块恰含一个线索格，且块大小=线索值
    seen = [False] * n
    for i in range(n):
        if wall[i] == 0 and not seen[i]:
            comp = []
            st = [i]
            seen[i] = True
            clues_in = []
            while st:
                p = st.pop()
                comp.append(p)
                if clue[p]:
                    clues_in.append((p, clue[p]))
                r, c = divmod(p, w)
                for q in ((r + 1) * w + c if r + 1 < h else -1,
                          (r - 1) * w + c if r >= 1 else -1,
                          r * w + c + 1 if c + 1 < w else -1,
                          r * w + c - 1 if c >= 1 else -1):
                    if q >= 0 and wall[q] == 0 and not seen[q]:
                        seen[q] = True
                        st.append(q)
            if len(clues_in) != 1:
                errs.append('白块@(%d,%d) 含 %d 个线索' % (i // w, i % w, len(clues_in)))
            elif clues_in[0][1] != len(comp):
                errs.append('岛@(%d,%d) 大小 %d != 线索 %d' %
                            (i // w, i % w, len(comp), clues_in[0][1]))
    # 3) 墙 4 连通
    walls = [i for i in range(n) if wall[i] == 1]
    if walls:
        seenw = {walls[0]}
        st = [walls[0]]
        while st:
            p = st.pop()
            r, c = divmod(p, w)
            for q in ((r + 1) * w + c if r + 1 < h else -1,
                      (r - 1) * w + c if r >= 1 else -1,
                      r * w + c + 1 if c + 1 < w else -1,
                      r * w + c - 1 if c >= 1 else -1):
                if q >= 0 and wall[q] == 1 and q not in seenw:
                    seenw.add(q)
                    st.append(q)
        if len(seenw) != len(walls):
            errs.append('墙不连通: %d/%d' % (len(seenw), len(walls)))
    return errs


def main():
    a9 = load_arm9(ARM9)
    table = parse_table(a9, NURI_TABLE_OFF)
    puzzles = {}
    total = 0
    bad = 0
    for did in sorted(table):
        count, ptr = table[did]
        name = DIFF_NAMES[did]
        recs = parse_records(a9, ptr, count)
        puzzles[name] = []
        for idx, (w, h, p_clue, p_wall) in enumerate(recs):
            clue = read_plane(a9, p_clue, w, h)
            wall = read_plane(a9, p_wall, w, h)
            errs = check_nurikabe(w, h, clue, wall)
            total += 1
            if errs:
                bad += 1
                print('✗ %s rec#%02d (%dx%d): %s' % (name, idx + 1, w, h, '; '.join(errs)))
            puzzles[name].append({
                'rec': idx + 1, 'w': w, 'h': h,
                'clue': clue, 'wall': wall, 'ok': not errs,
            })
        sizes = sorted(set((r['w'], r['h']) for r in puzzles[name]))
        print('%s: %d 题, 规格集 %s' % (name, len(puzzles[name]), sizes))
    print('合计 %d 题, 自检失败 %d' % (total, bad))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(puzzles, open(OUT, 'w'), ensure_ascii=False)
    print('已写出', OUT)


if __name__ == '__main__':
    main()
