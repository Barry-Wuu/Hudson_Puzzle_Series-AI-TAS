#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.05 数回（スリザーリンク / SLITHERLINK / A3LJ18）题库与答案静态提取。

方法论与 Vol.06 数织 / Vol.11 数墙一致：**答案是 ROM 里现成的数据表，开录之前
静态提取，不靠求解器现算，也不逆运行时内存编码。**

ROM 结构（实测，日版 A3LJ18 / 8 MiB）：
  NitroFS 只有 5 个 FAT 项；题库打包在 `indata/add01dat.bin`（3,868,148 B）里。
  该文件是一个通用 pack：开头是 u32 偏移表（1704 项），之后是 1704 条记录
  （图形 RSC/RGI/SCR/IMG/RECT、题库、素材混排）。

  题库区 = 偏移表 idx 1395..1702，共 **308 条**定长记录，按尺寸分 5 档：
    6x6  =  24 条 (100 B)   入門教学
    10x10 = 101 条 (228 B)
    18x10 =  81 条 (388 B)
    24x14 =  61 条 (700 B)
    36x20 =  41 条 (1468 B)

  每条题目记录布局（**算术上唯一自洽**，5 档尺寸全部成立）：
    [0]              u8 w
    [1]              u8 h
    [2 : 2+w*h]      线索盘，逐行 u8：0/1/2/3 = Slitherlink 线索，4 = 空格
    [2+w*h : 2+2w*h] 答案掩码，逐行 u8：每格「环内=1 / 环外=0」，其边界即环路
    [2+2w*h : ]      固定 26 字节图形元数据，前 4 字节固定为 `C4 96 49 01`，其后随题变化

    长度校验：2 + 2·w·h + 26 == 记录长度
      6x6   2+72+26   = 100   ✓
      10x10 2+200+26  = 228   ✓
      18x10 2+360+26  = 388   ✓
      24x14 2+672+26  = 700   ✓
      36x20 2+1440+26 = 1468  ✓

  ★ 历史坑：早期版本把记录头当成 4 字节（w,h,flag_a,flag_b），线索盘从 [4] 起、
    答案段从 [4+w*h] 起，于是把答案掩码的头 2 字节吃进了线索盘尾部，得到
    「0/1 段长度 = w*h-2」的假象，并据此误判「0/1 段不是答案」。实际盘面起点是 [2]，
    修正后 308 题里 306 题可用掩码边界直接还原官方唯一环路。

  自检（308 题全量，任一失败即报错）：
    ① 偏移表首尾相接、覆盖到文件末尾；
    ② 记录头 w/h 落在 {6,10,18,24,36}×{6,10,14,20}，长度 == 2+2·w·h+26；
    ③ 线索盘值域 ⊆ {0,1,2,3,4}，答案掩码值域 ⊆ {0,1}；
    ④ 由掩码推出的环路满足**每一个**数字线索；
    ⑤ 每个格点度数为 0 或 2，且环路恰好一个连通分量。
    仅 2 条 6x6 空白占位记录（idx1400 全空、idx1401 有线索无答案）按设计跳过 ④⑤。

用法：python3 extract_vol5_answers.py [ROM路径]
产出（脚本同目录 validation/ 下）：
  vol5_pack.bin          题库容器原始字节（保真存档，不入库）
  puzzles.json           308 题结构化数据：线索盘 + 答案掩码 + 环路边 + 自检结果
  题库与答案.md          逐题题面 + 官方环路字符画
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROM = '/workspace/roms/解谜系列Vol.05：数回.nds'
OUTDIR = os.path.join(HERE, 'validation')

# 题库区在 pack 偏移表里的下标范围（实测）
IDX_START = 1395
IDX_END = 1703          # 不含
DIMS = {(6, 6): 100, (10, 10): 228, (18, 10): 388, (24, 14): 700, (36, 20): 1468}
TAIL_LEN = 26
BLANK_IDX = {1400, 1401}   # 入門档的两条空白占位记录（无线索/无答案）


def extract_pack(rom_path):
    """从 ROM 的 NitroFS 里解出 add01dat.bin。"""
    rom = open(rom_path, 'rb').read()
    fat_off = struct.unpack_from('<I', rom, 0x48)[0]
    fat_size = struct.unpack_from('<I', rom, 0x4C)[0]
    n = fat_size // 8
    best = None
    for i in range(n):
        s, e = struct.unpack_from('<II', rom, fat_off + i * 8)
        blob = rom[s:e]
        if len(blob) > 3_000_000 and struct.unpack_from('<I', blob, 0)[0] == 6816:
            best = blob
            break
    if best is None:
        best = max((rom[struct.unpack_from('<II', rom, fat_off + i * 8)[0]:
                        struct.unpack_from('<II', rom, fat_off + i * 8)[1]]
                    for i in range(n)), key=len)
    return best


def loop_edges(w, h, mask):
    """把内/外掩码转成环路边集（水平边 H[r][c]=(r,c)-(r,c+1)，垂直边 V[r][c]=(r,c)-(r+1,c)）。"""
    def ins(r, c):
        return mask[r * w + c] if 0 <= r < h and 0 <= c < w else 0
    he = [(r, c) for r in range(h + 1) for c in range(w) if ins(r - 1, c) != ins(r, c)]
    ve = [(r, c) for r in range(h) for c in range(w + 1) if ins(r, c - 1) != ins(r, c)]
    return he, ve


def verify(w, h, clues, he, ve):
    """返回 (线索违例数, 度数违例数, 连通分量数)。"""
    hes, ves = set(he), set(ve)
    bad = 0
    for r in range(h):
        for c in range(w):
            v = clues[r * w + c]
            if v <= 3:
                cnt = ((r, c) in hes) + ((r + 1, c) in hes) + \
                      ((r, c) in ves) + ((r, c + 1) in ves)
                if cnt != v:
                    bad += 1
    degbad = 0
    for r in range(h + 1):
        for c in range(w + 1):
            dg = ((r, c) in hes) + ((r, c - 1) in hes) + \
                 ((r, c) in ves) + ((r - 1, c) in ves)
            if dg not in (0, 2):
                degbad += 1
    adj = {}
    for (r, c) in he:
        adj.setdefault((r, c), []).append((r, c + 1)); adj.setdefault((r, c + 1), []).append((r, c))
    for (r, c) in ve:
        adj.setdefault((r, c), []).append((r + 1, c)); adj.setdefault((r + 1, c), []).append((r, c))
    seen = set(); comps = 0
    for v0 in adj:
        if v0 in seen: continue
        comps += 1; st = [v0]; seen.add(v0)
        while st:
            x = st.pop()
            for y in adj[x]:
                if y not in seen: seen.add(y); st.append(y)
    return bad, degbad, comps


def parse_pack(d):
    first = struct.unpack_from('<I', d, 0)[0]
    n = first // 4
    offs = list(struct.unpack_from('<%dI' % n, d, 0)) + [len(d)]
    for i in range(n):                                   # 自检 ①
        if offs[i + 1] <= offs[i]:
            raise RuntimeError('偏移表非递增 @%d' % i)
    out = []
    for i in range(IDX_START, min(IDX_END, n)):
        b = d[offs[i]:offs[i + 1]]
        if len(b) < 8:
            continue
        w, h = b[0], b[1]
        cells = w * h
        if (w, h) not in DIMS:                            # 自检 ②
            raise RuntimeError('idx%d 尺寸异常 w=%d h=%d' % (i, w, h))
        if len(b) != 2 + 2 * cells + TAIL_LEN:
            raise RuntimeError('idx%d 记录长度 %d != %d' % (i, len(b), 2 + 2 * cells + TAIL_LEN))
        clues = list(b[2:2 + cells])
        mask = list(b[2 + cells:2 + 2 * cells])
        tail = b[2 + 2 * cells:]
        if any(x > 4 for x in clues):                     # 自检 ③
            raise RuntimeError('idx%d 线索盘出现 >4' % i)
        if any(x > 1 for x in mask):
            raise RuntimeError('idx%d 答案掩码非 0/1' % i)
        he, ve = loop_edges(w, h, mask)
        bad, degbad, comps = verify(w, h, clues, he, ve)
        blank = i in BLANK_IDX
        if not blank:                                     # 自检 ④⑤
            if bad or degbad or comps != 1:
                raise RuntimeError('idx%d 答案不自洽 线索违例%d 度数违例%d 分量%d'
                                   % (i, bad, degbad, comps))
        out.append({
            'idx': i, 'w': w, 'h': h, 'cells': cells,
            'clues': clues,
            'clue_grid': [''.join('.' if clues[r * w + c] == 4 else str(clues[r * w + c])
                                  for c in range(w)) for r in range(h)],
            'answer_mask': mask,                 # 每格环内=1 / 环外=0
            'answer_grid': [''.join(str(mask[r * w + c]) for c in range(w)) for r in range(h)],
            'edges_h': he,                       # [(r,c)] 水平边 (r,c)-(r,c+1)
            'edges_v': ve,                       # [(r,c)] 垂直边 (r,c)-(r+1,c)
            'edges': len(he) + len(ve),
            'answer_ink': sum(mask),
            'blank': blank,
            'tail_hex': tail[:8].hex(),
        })
    return out


def draw_loop(w, h, he, ve):
    """把环路画成 (2h+1)×(2w+1) 字符画：─│┌┐└┘├┤┬┴┼ 连接边，'·' 为空格点。"""
    hes, ves = set(he), set(ve)
    rows = []
    for r in range(h + 1):
        line = []
        for c in range(w + 1):
            up = (r - 1, c) in ves
            dn = (r, c) in ves
            lf = (r, c - 1) in hes
            rt = (r, c) in hes
            if not (up or dn or lf or rt):
                line.append('·')
            elif dn and rt and not up and not lf:
                line.append('┌')
            elif dn and lf and not up and not rt:
                line.append('┐')
            elif up and rt and not dn and not lf:
                line.append('└')
            elif up and lf and not dn and not rt:
                line.append('┘')
            elif up and dn and not lf and not rt:
                line.append('│')
            elif lf and rt and not up and not dn:
                line.append('─')
            elif dn and lf and rt:
                line.append('┬')
            elif up and lf and rt:
                line.append('┴')
            elif up and dn and rt:
                line.append('├')
            elif up and dn and lf:
                line.append('┤')
            else:
                line.append('┼')
            if c < w:
                line.append('─' if (r, c) in hes else ' ')
        rows.append(''.join(line))
        if r < h:
            line = []
            for c in range(w + 1):
                line.append('│' if (r, c) in ves else ' ')
                if c < w:
                    line.append(' ')
            rows.append(''.join(line))
    return rows


def to_md(puzzles, path):
    ok = sum(1 for p in puzzles if not p['blank'])
    lines = [
        '# 解谜系列 Vol.5 数回（SLITHERLINK）题库与答案',
        '',
        '> 静态提取自 ROM `indata/add01dat.bin` pack，布局 `w,h,线索盘(w·h),答案掩码(w·h),26B 图形元数据`。',
        '> 线索盘 `0-3`=线索、`.`=空格；答案掩码是「每格环内/环外」，其边界即官方唯一环路。',
        f'> 全库 {len(puzzles)} 条记录，其中 **{ok} 题**通过「线索逐格满足 + 格点度数 0/2 + 单环」三重校验。',
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
        flag = '（空白占位，无答案）' if p['blank'] else f'（边 {p["edges"]}）'
        lines += [f'### pack idx {p["idx"]}　({p["w"]}x{p["h"]}, 环内 {p["answer_ink"]} 格){flag}', '']
        lines += ['**题面线索**（`.`=空格）', '', '```']
        lines += p['clue_grid']
        lines += ['```', '']
        lines += ['**官方环路**', '', '```']
        lines += draw_loop(p['w'], p['h'], p['edges_h'], p['edges_v'])
        lines += ['```', '']
    open(path, 'w', encoding='utf-8').write('\n'.join(lines) + '\n')


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROM
    os.makedirs(OUTDIR, exist_ok=True)
    pack = extract_pack(rom)
    open(os.path.join(OUTDIR, 'vol5_pack.bin'), 'wb').write(pack)
    puzzles = parse_pack(pack)
    json.dump(puzzles, open(os.path.join(OUTDIR, 'puzzles.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    to_md(puzzles, os.path.join(OUTDIR, '题库与答案.md'))
    from collections import Counter
    c = Counter((p['w'], p['h']) for p in puzzles)
    good = sum(1 for p in puzzles if not p['blank'])
    print('提取完成 %d 题:' % len(puzzles), dict(c))
    print('  答案自洽 %d/%d（其余为空白占位）' % (good, len(puzzles)))
    print('  边数范围 %d..%d，环内格数范围 %d..%d'
          % (min(p['edges'] for p in puzzles if not p['blank']),
             max(p['edges'] for p in puzzles),
             min(p['answer_ink'] for p in puzzles),
             max(p['answer_ink'] for p in puzzles)))
    print('  产出:', os.path.join(OUTDIR, 'puzzles.json'),
          os.path.join(OUTDIR, '题库与答案.md'))


if __name__ == '__main__':
    main()
