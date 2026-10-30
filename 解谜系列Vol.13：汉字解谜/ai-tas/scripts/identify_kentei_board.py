#!/usr/bin/env python3
"""从填字界面截图自动识别「認定問題」加载的是哪个 rec（PITFALLS §S51）。

用途：rec50/rec53（ロの数同为115、枠同为15×15）等菜单不可分的场合，靠盘面结构定案；
亦可用于核验「菜单上屏参数 = 实际加载题」。


原理：上屏盘面 16px/格，网格线为纯黑行/列；格心颜色分类
  黑=盘外、蓝=提示汉字(固定)、其余=待填格(徽章)。
上屏高度只装得下前 ~10 行，故用可见行做结构比对，与 solve2 的
badge_cells/grid 逐格对齐，取不匹配数最少者。

用法: python3 identify_board.py <png> [png ...]
"""
import sys, os
from collections import Counter
sys.path.insert(0, '/workspace/Kanji')
sys.path.insert(0, '/workspace/Kanji/ai-tas/scripts')
import numpy as np
from PIL import Image
import solve2

RECS = list(range(35, 55))
_cache = {}


def offline_masks(rec):
    if rec not in _cache:
        r = solve2.solve(rec)
        bset = set()
        for v in r['badge_cells'].values():
            bset.update(v)
        _cache[rec] = (set(r['grid']), bset,
                       max(c for c, _ in r['grid']) + 1,
                       max(w for _, w in r['grid']) + 1)
    return _cache[rec]


def grid_lines(a, axis):
    blk = (a.max(2) < 60)
    frac = blk.mean(axis=0) if axis == 0 else blk.mean(axis=1)
    return [i for i in range(len(frac)) if frac[i] > 0.45]


def cells_from_lines(lines):
    """由相邻黑网格线间距推格：返回 [(start,end), ...]（start=线号，格在线之间）。"""
    lines = sorted(set(lines))
    if len(lines) < 2:
        return []
    diffs = [b - a for a, b in zip(lines, lines[1:])]
    cnt = Counter(diffs)
    cand = [d for d in cnt if cnt[d] >= 2 and d >= 8]
    if not cand:
        return []
    pitch = max(cand, key=lambda d: cnt[d])
    return [(a, b) for a, b in zip(lines, lines[1:]) if b - a == pitch]


def classify_cell(a, y0, x0):
    cell = a[y0 + 4:y0 + 12, x0 + 4:x0 + 12]
    m = cell.reshape(-1, 3).mean(0)
    if m.max() < 70:
        return '.'
    if m[2] - m[0] > 60:
        return 'b'
    return 'W'


def shot_map(path):
    a = np.array(Image.open(path).convert('RGB')).astype(int)[0:192]
    cols = cells_from_lines(grid_lines(a, 0))
    rows = cells_from_lines(grid_lines(a, 1))
    m = {}
    for ri, (ya, yb) in enumerate(rows):
        for ci, (xa, xb) in enumerate(cols):
            m[(ci, ri)] = classify_cell(a, (ya + yb) // 2 - 4, (xa + xb) // 2 - 4)
    geo = (cols[0][0], rows[0][0], cols[0][1] - cols[0][0],
           rows[0][1] - rows[0][0], len(cols), len(rows))
    return m, geo


def identify(path, top=3):
    m, geo = shot_map(path)
    vis = set(m)
    scores = []
    for rec in RECS:
        grid, bset, W, H = offline_masks(rec)
        mm = 0
        for (c, r) in vis:
            if c >= W or r >= H:
                mm += 1
                continue
            if (m[(c, r)] != '.') != ((c, r) in grid):
                mm += 1
        scores.append((mm, rec))
    scores.sort()
    return m, geo, scores[:top]


if __name__ == '__main__':
    for p in sys.argv[1:]:
        m, geo, sc = identify(p)
        print('%-30s 几何%s  %s' % (os.path.basename(p), geo,
              '  '.join('rec%d(差%d)' % (r, d) for d, r in sc)))
