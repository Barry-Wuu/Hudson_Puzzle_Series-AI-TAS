#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""QC：把 validation 里已落盘的 clear 图重新解码，逐格与答案盘比对。

对每张图独立判定，不信任提取脚本的中间量：
  · 逐格取格心 3×3 邻域，判「涂黑」= max<115 且 R>G+8；
  · 与 puzzles.json 的答案盘逐格比，报告「缺格（该涂没涂）/ 多格（不该涂却涂了）」；
  · 顺带判「是否仍是米白底色」（空格中位色 R≥200 且 R−B≥0），即确认未上色。

用法：python3 check_clear_shots.py [尺寸]
退出码非 0 表示存在不一致。
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'validation')
PJ = os.path.join(OUT, 'puzzles.json')
GEO = {10: (16.0, 87.0, 200.0), 15: (10.0, 92.0, 200.0),
       20: (8.0, 88.0, 200.0), 25: (7.0, 75.0, 193.0)}
SIZE_DIR = {10: 'mode1_10x10', 15: 'mode2_15x15', 20: 'mode3_20x20', 25: 'mode4_25x25'}
SIZE_OFF = {10: 0, 15: 50, 20: 150, 25: 250}
W, H = 256, 384


def read_cells(im, n, s, x0, y0):
    a = np.asarray(im.convert('RGB')).astype(np.int16)
    cs = x0 + (np.arange(n) + 0.5) * s
    rs = y0 + (np.arange(n) + 0.5) * s
    X = np.clip(np.rint(np.tile(cs, (n, 1))).astype(int), 0, W - 1)
    Y = np.clip(np.rint(np.tile(rs[:, None], (1, n))).astype(int), 0, H - 1)
    ink = np.zeros((n, n), bool)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            q = a[np.clip(Y + dy, 0, H - 1), np.clip(X + dx, 0, W - 1)]
            ink |= (q.max(axis=-1) < 115) & (q[..., 0] > q[..., 1] + 8)
    paper = a[Y, X][~ink]
    med = np.median(paper, axis=0) if len(paper) else np.array([0, 0, 0])
    return ink, med


def main():
    only = int(sys.argv[1]) if len(sys.argv) > 1 else None
    with open(PJ, encoding='utf-8') as f:
        puzzles = json.load(f)
    bad = 0
    total = 0
    for size, dname in SIZE_DIR.items():
        if only and only != size:
            continue
        d = os.path.join(OUT, dname)
        if not os.path.isdir(d):
            continue
        s, x0, y0 = GEO[size]
        files = sorted(f for f in os.listdir(d) if f.endswith('_clear.png'))
        size_bad = 0
        for f in files:
            num = int(f[1:4])
            grid = np.array(puzzles[SIZE_OFF[size] + num - 1]['grid'], bool)
            im = Image.open(os.path.join(d, f))
            im.load()
            im = im.convert('RGB')
            ink, med = read_cells(im, size, s, x0, y0)
            miss = int((grid & ~ink).sum())
            extra = int((~grid & ink).sum())
            # 未浸染：空格中位色仍属米白系（R−B ≥ 0 且够亮）。上色后 R−B 会掉到负值或
            # R 掉到 200 以下；轻微褪色（如 (238,237,223)）算正常，那是浸染动画的最初半帧。
            colored = not (med[0] >= 200 and med[0] - med[2] >= 0)
            total += 1
            if miss or extra or colored:
                bad += 1
                size_bad += 1
                print('  %s/%s  缺%d格 多%d格  底色=%s%s'
                      % (dname, f, miss, extra, tuple(int(v) for v in med),
                         '  ← 已上色' if colored else ''))
        print('%s：%d 张，异常 %d' % (dname, len(files), size_bad))
    print('\n合计检查 %d 张，异常 %d' % (total, bad))
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
