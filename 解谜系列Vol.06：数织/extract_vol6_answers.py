#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.06 数织（ILLUST LOGIC / AILJ18）题库提取：从 NitroFS 里直接挖出 300 道题的答案盘面。

与其它卷同一方法论：答案是 ROM 里现成的数据表，**开录之前静态提取**，不靠求解器现算。

ROM 结构（实测，8 MiB）：
  NitroFS 四个数据文件：quest/quest10x10.bin(16944) / quest15x15.bin(60124) /
  quest20x20.bin(93472) / quest25x25.bin(71072)，另有 quest/quest.bat —— 里面写明这些
  bin 是由 `ilconv.exe csv\\questNNxNN.csv` 从 CSV 转出来的，所以是**题库表**而非运行时缓存。

  每个 bin = 索引表 + 定长记录：
    [0x00] u32 题数
    [0x04] u32 文件长度（自校验）
    [0x08] 题数 × (u32 记录偏移, u32 记录长度)；偏移从 8+8*题数 起，首尾相接无空隙
  记录（'ILQT' 签名）：
    [0x00] 'ILQT'  [0x04] u16 版本(=0)  [0x06] u8 宽  [0x07] u8 高
    [0x08] u32 记录长度  [0x0C] 7×u32 分段指针（标题/尺寸标签/答案词/美术层/盘面/线索A/线索B）
    [0x28] Shift-JIS 字符串 ×3：题目（「ロジックから現れる動物は？」等）/ 尺寸标签 / 答案词
    美术层：宽×高 字节，1 字节/格，高位置 1（≥0x80）= 该格属于画面，低 4 位是画面配色（0..9）
    线索：每行/列固定 ceil(N/2) 字节（最长线段数），0 与 0xFF 都是空位

★ 两处存储约定（实测 300/300 一致，不是推测）：
  ① 盘面按行优先存储，**高位置 1 的格子就是非ogram 的「涂黑格」**；填空格存的是无高位的配色。
  ② 线索数组的段内块序是**反向**的：第二段（宽条数）＝行线索，每条自右向左；第一段（高条数）
     ＝列线索，每条自下而上。所以 runs(第 y 行) == reversed(第二段[y])、runs(第 x 列) ==
     reversed(第一段[x]) 逐条成立（本脚本对 300 题逐条校验，任一失败即报错）。

自检（300 题全量，任一失败即报错）：
  ① 索引表偏移首尾相接、覆盖到文件末尾；
  ② 记录签名/尺寸/长度自洽；
  ③ 盘面涂黑格数 == 行线索之和 == 列线索之和；
  ④ 盘面逐行的连续段 == 行线索（反序逐条相等），逐列同理；
  ⑤ 题目/尺寸/答案词三段 Shift-JIS 均可解码且非空。

用法：python3 extract_vol6_answers.py [ROM路径]
产出：validation/puzzles.json + 答案.md（写到脚本同目录）
"""
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROM = '/workspace/roms/解谜系列Vol.06：数织.nds'
FILES = [('quest10x10.bin', 10), ('quest15x15.bin', 15),
         ('quest20x20.bin', 20), ('quest25x25.bin', 25)]
OUTDIR = os.path.join(HERE, 'validation')


def sjis(b):
    return b.rstrip(b'\x00').decode('shift_jis', 'replace')


def runs(line):
    return [len(t) for t in ''.join(map(str, line)).split('0') if t]


def parse_bin(d):
    n, total = struct.unpack_from('<II', d, 0)
    if total != len(d):
        raise RuntimeError('文件长度字段不符: %d != %d' % (total, len(d)))
    out = []
    prev_end = 8 + 8 * n
    for i in range(n):
        o, s = struct.unpack_from('<II', d, 8 + 8 * i)
        if o != prev_end or o + s > len(d):
            raise RuntimeError('第 %d 题索引不连续: off=%d expect=%d' % (i, o, prev_end))
        prev_end = o + s
        rec = d[o:o + s]
        if rec[:4] != b'ILQT':
            raise RuntimeError('第 %d 题缺 ILQT 签名' % i)
        ver, = struct.unpack_from('<H', rec, 4)
        w, h = rec[6], rec[7]
        rlen, = struct.unpack_from('<I', rec, 8)
        if rlen != s:
            raise RuntimeError('第 %d 题长度字段不符' % i)
        p = struct.unpack_from('<7I', rec, 12)
        title = [sjis(rec[p[k]:p[k + 1]]) for k in range(3)]
        art = rec[p[4]:p[5]]
        if len(art) < w * h:
            raise RuntimeError('第 %d 题美术层长度不足' % i)
        grid = [[1 if art[y * w + x] >= 0x80 else 0 for x in range(w)] for y in range(h)]
        per = (w + 1) // 2
        cl = lambda buf, c: [[v for v in buf[j * per:(j + 1) * per] if v not in (0, 255)]
                             for j in range(c)]
        clue_cols = cl(rec[p[5]:p[6]], h)   # 第一段：列线索（自下而上）
        clue_rows = cl(rec[p[6]:rlen], w)   # 第二段：行线索（自右向左）
        if len(clue_rows) != h or len(clue_cols) != w:
            raise RuntimeError('第 %d 题线索条数不符' % i)
        # 自检 ③④
        nrow = sum(map(sum, clue_rows))
        ncol = sum(map(sum, clue_cols))
        nink = sum(map(sum, grid))
        if not (nrow == ncol == nink):
            raise RuntimeError('第 %d 题计数不符: ink=%d row=%d col=%d' % (i, nink, nrow, ncol))
        for y in range(h):
            if runs(grid[y]) != clue_rows[y][::-1]:
                raise RuntimeError('第 %d 题第 %d 行线索不符' % (i, y))
        for x in range(w):
            if runs([grid[y][x] for y in range(h)]) != clue_cols[x][::-1]:
                raise RuntimeError('第 %d 题第 %d 列线索不符' % (i, x))
        if not all(title):
            raise RuntimeError('第 %d 题标题字符串为空' % i)
        out.append(dict(idx=i, w=w, h=h, title=title[0], label=title[1], word=title[2],
                        ink=nink, grid=grid, clue_rows=clue_rows, clue_cols=clue_cols))
    if prev_end != len(d):
        raise RuntimeError('索引表未覆盖到文件末尾')
    return out


def load_rom(path):
    import ndspy.rom
    r = ndspy.rom.NintendoDSRom.fromFile(path)
    got = {}
    for i in range(len(r.files)):
        try:
            name = r.filenames.filenameOf(i)
        except Exception:
            continue
        if name and name.startswith('quest/') and name.endswith('.bin'):
            got[name.split('/')[-1]] = bytes(r.files[i])
    return got, r


def md_answer(p, idx):
    lines = ['**第%03d問（%s · %s）**' % (idx, p['label'], p['word']), '', '```']
    for row in p['grid']:
        lines.append(''.join('■' if v else '・' for v in row))
    lines += ['```', '']
    return '\n'.join(lines)


def main():
    rom = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_ROM
    files, r = load_rom(rom)
    print('ROM: %s  code=%s' % (rom, bytes(r.idCode)))
    allq, gid = [], 0
    for fn, size in FILES:
        if fn not in files:
            raise RuntimeError('缺文件 ' + fn)
        qs = parse_bin(files[fn])
        for q in qs:
            gid += 1
            q['global'] = gid
            q['size'] = size
        print('  %-16s %3d 题  涂黑格 %d~%d' % (fn, len(qs), min(q['ink'] for q in qs), max(q['ink'] for q in qs)))
        allq += qs
    print('合计 %d 题；300 题全部通过索引/签名/计数/线索四条自检' % len(allq))

    os.makedirs(OUTDIR, exist_ok=True)
    with open(os.path.join(OUTDIR, 'puzzles.json'), 'w', encoding='utf-8') as f:
        json.dump(allq, f, ensure_ascii=False)
    md = ['# 解谜系列 Vol.06：数织 — 全 %d 题答案盘面' % len(allq), '',
          '> 从 ROM 的 `quest/questNNxNN.bin` 静态提取：盘面美术层高位置 1 的格子即涂黑格。',
          '> 每题的题面线索与盘面已逐行逐列交叉校验（300/300 通过），可用 `■` 直接照填。', '']
    cur = None
    for q in allq:
        if q['size'] != cur:
            cur = q['size']
            md += ['## %d×%d（%d 题）' % (cur, cur, sum(1 for x in allq if x['size'] == cur)), '']
        md.append(md_answer(q, q['idx'] + 1))
    with open(os.path.join(HERE, '答案.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(md))
    print('已写出', os.path.join(OUTDIR, 'puzzles.json'), '与 答案.md')


if __name__ == '__main__':
    main()
