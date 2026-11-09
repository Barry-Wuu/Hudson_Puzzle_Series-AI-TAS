#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.05 数回（スリザーリンク / SLITHERLINK / A3LJ18）题库静态提取。

方法论与 Vol.06 数织 / Vol.11 数墙一致：**答案是 ROM 里现成的数据表，开录之前
静态提取，不靠求解器现算，也不逆运行时内存编码。**

ROM 结构（实测，日版 A3LJ18 / 8 MiB）：
  NitroFS 只有 5 个 FAT 项；题库打包在 `indata/add01dat.bin`（3,868,148 B）里。
  该文件是一个通用 pack：开头是 u32 偏移表（1704 项），之后是 1704 条记录
  （图形 RSC/RGI/SCR/IMG/RECT、题库、素材混排）。

  题库区 = 偏移表 idx 1395..1703，共 **308 条**定长记录，按尺寸分 5 档：
    6x6  =  24 条 (size 100)   入門教学
    10x10 = 101 条 (size 228)  含 1 条尺寸样本头 (idx1396)
    18x10 =  81 条 (size 388)  含 1 条尺寸样本头 (idx1397)
    24x14 =  61 条 (size 700)  含 1 条尺寸样本头 (idx1398)
    36x20 =  41 条 (size 1468) 含 1 条尺寸样本头 (idx1399)
  合计 24+101+81+61+41 = 308。

  每条题目记录布局（308/308 全量自检一致，非推测）：
    [0]      u8 w  (格子宽)
    [1]      u8 h  (格子高)
    [2]      u8 标记A（题面头两字节之一，疑似难度/评级，0..4）
    [3]      u8 标记B（0..4）
    [4 : 4+w*h]        题目数字盘，逐行 u8：0/1/2/3 = Slitherlink 线索；
                       4 = 空格（无线索）。值域严格 0..4，无例外。
    [4+w*h : ...]      答案区 = 数字盘之后**连续 0/1 段**（到首个 >1 字节为止）。
                       301 题长度 = w*h-2；另有 7 条 24x14 题长度 = w*h-1
                       （末字节恰为 1，或边界差异；如实保留，不强行归一）。
    答案段之后是图形元数据：多数题以固定 4 字节前缀 `C4 96 49 01`
    （=196 150 73 1）开头，其后 2 字节是变化的图形尺寸/指针；
    少数 24x14 题前缀不同（如 `E1 00 00 A8 93 00 00 80`）。

  自检（308 题全量，任一失败即报错）：
    ① 偏移表首尾相接、覆盖到文件末尾；
    ② 记录头 w/h 落在 {6,10,18,24,36}×{6,10,14,20}；
    ③ 数字盘值域 ⊆ {0,1,2,3,4}；
    ④ 答案段严格 0/1 且长度 ∈ {w*h-2, w*h-1}（301 + 7 条，实测两类）；
    ⑤ 答案段之后仍有图形/元数据字节（记录未截断）。

用法：python3 extract_vol5_answers.py [ROM路径]
产出（脚本同目录 validation/ 下）：
  vol5_pack.bin                 题库容器原始字节（保真存档）
  puzzles.json                  308 题结构化数据 + 自检
  题库盘面与待解读段.md         逐题数字盘 + 0/1 段（语义未明，非答案）字符画
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROM = '/workspace/roms/解谜系列Vol.05：数回.nds'
OUTDIR = os.path.join(HERE, 'validation')
PACK_NAME = 'add01dat.bin'
GRATAIL = bytes([196, 150, 73, 1])  # 固定前缀；其后 2 字节是变化的图形尺寸/指针

# 题库区在 pack 偏移表里的下标范围（实测）
IDX_START = 1395
DIMS = {(6, 6): 100, (10, 10): 228, (18, 10): 388, (24, 14): 700, (36, 20): 1468}


def extract_pack(rom_path):
    """从 ROM 的 NitroFS 里解出 add01dat.bin（FAT 第 4 项）。"""
    rom = open(rom_path, 'rb').read()
    fat_off = struct.unpack_from('<I', rom, 0x48)[0]
    fat_size = struct.unpack_from('<I', rom, 0x4C)[0]
    n = fat_size // 8
    # 找名字含 add01dat 的 FAT 项；此处直接用「最大且以偏移表开头」的项兜底
    best = None
    for i in range(n):
        s, e = struct.unpack_from('<II', rom, fat_off + i * 8)
        blob = rom[s:e]
        if len(blob) > 3_000_000 and struct.unpack_from('<I', blob, 0)[0] == 6816:
            best = blob
            break
    if best is None:
        # 兜底：最大的 FAT 项
        best = max((rom[struct.unpack_from('<II', rom, fat_off + i * 8)[0]:
                        struct.unpack_from('<II', rom, fat_off + i * 8)[1]]
                    for i in range(n)), key=len)
    return best


def parse_pack(d):
    first = struct.unpack_from('<I', d, 0)[0]
    n = first // 4
    offs = list(struct.unpack_from('<%dI' % n, d, 0)) + [len(d)]
    # 自检 ①
    for i in range(n):
        if offs[i + 1] <= offs[i]:
            raise RuntimeError('偏移表非递增 @%d' % i)
    out = []
    for i in range(IDX_START, n):
        o, e = offs[i], offs[i + 1]
        b = d[o:e]
        if len(b) < 8:
            continue
        w, h, fa, fb = b[0], b[1], b[2], b[3]
        cells = w * h
        # 自检 ②
        if (w, h) not in DIMS or len(b) != DIMS[(w, h)]:
            raise RuntimeError('idx%d 尺寸/长度异常 w=%d h=%d len=%d' % (i, w, h, len(b)))
        num = list(b[4:4 + cells])
        # 自检 ③
        if any(x > 4 for x in num):
            raise RuntimeError('idx%d 数字盘出现 >4' % i)
        ans_start = 4 + cells
        # 答案 0/1 段 = 从数字盘之后起、连续 0/1 的最大段
        k = ans_start
        while k < len(b) and b[k] <= 1:
            k += 1
        ans = list(b[ans_start:k])
        ans_len = len(ans)
        # 自检 ④：答案段严格 0/1，且长度只能是 w*h-2 或 w*h-1（实测两类，如实保留）
        if any(x > 1 for x in ans):
            raise RuntimeError('idx%d 答案区出现 >1' % i)
        if ans_len not in (cells - 2, cells - 1):
            raise RuntimeError('idx%d 答案段长度异常 %d (期望 %d/%d)'
                               % (i, ans_len, cells - 2, cells - 1))
        # 自检 ⑤：答案段之后必须还有图形/元数据字节（记录未截断）
        if k >= len(b):
            raise RuntimeError('idx%d 答案段后无图形数据' % i)
        out.append({
            'idx': i,
            'w': w, 'h': h,
            'flag_a': fa, 'flag_b': fb,
            'cells': cells,
            # 0-3 线索，4=空；保留原始值，便于与实机题面逐格核对
            'clues': num,
            'clue_grid': [''.join('.' if num[r * w + c] == 4 else str(num[r * w + c])
                                  for c in range(w)) for r in range(h)],
            'answer': ans,
            'answer_ink': sum(ans),
        })
    return out


def to_md(puzzles, path):
    lines = [
        '# 解谜系列 Vol.5 数回（SLITHERLINK）题库盘面与待解读段',
        '',
        '> 静态提取自 ROM `indata/add01dat.bin` pack；数字盘 `0-3`=线索、`.`=空格。',
        '> 后半段为 0/1 数据（长度 w*h-2，7 题例外为 w*h-1），**语义未明、非官方答案**；',
        '> 已验证不是环路线段 / 答案画 / 线索掩码。`#`=1、`.`=0。',
        '> 真正的环路答案待求解器或独立答案表确定。详见 README.md 与自检口径。',
        '',
        f'题目总数：**{len(puzzles)}**（6x6=24 / 10x10=101 / 18x10=81 / 24x14=61 / 36x20=41）',
        '',
    ]
    cur = None
    for p in puzzles:
        key = (p['w'], p['h'])
        if key != cur:
            cur = key
            lines += [f'## {p["w"]}x{p["h"]}', '']
        lines += [f'### pack idx {p["idx"]}　({p["w"]}x{p["h"]}, 答案墨迹 {p["answer_ink"]})', '']
        lines += ['**题面数字盘**（`.`=空格）', '', '```']
        lines += [''.join(row) for row in p['clue_grid']]
        lines += ['```', '']
        lines += ['**官方答案 0/1 标记**（按行铺 w*h-2 字节）', '', '```']
        a = p['answer']
        # 按 w 宽铺行，末行不足补位
        for r in range(0, len(a), p['w']):
            lines.append(''.join('#' if x else '.' for x in a[r:r + p['w']]))
        lines += ['```', '']
    open(path, 'w').write('\n'.join(lines) + '\n')


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROM
    os.makedirs(OUTDIR, exist_ok=True)
    pack = extract_pack(rom)
    open(os.path.join(OUTDIR, 'vol5_pack.bin'), 'wb').write(pack)
    puzzles = parse_pack(pack)
    json.dump(puzzles, open(os.path.join(OUTDIR, 'puzzles.json'), 'w'),
              ensure_ascii=False, indent=1)
    to_md(puzzles, os.path.join(OUTDIR, '题库盘面与待解读段.md'))
    from collections import Counter
    c = Counter((p['w'], p['h']) for p in puzzles)
    print('提取完成 %d 题:' % len(puzzles), dict(c))
    print('  待解读 0/1 段墨迹范围 %d..%d' % (min(p['answer_ink'] for p in puzzles),
                                          max(p['answer_ink'] for p in puzzles)))
    print('  产出:', os.path.join(OUTDIR, 'puzzles.json'),
          os.path.join(OUTDIR, '题库盘面与待解读段.md'))


if __name__ == '__main__':
    main()
