#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全网格通关校验：扫描选关页全部 35 格，逐格报告蓝/灰状态。

背景（PITFALLS §T）：
  kanji_common.level_cleared() 只检查**目标关卡单格**，蓝>灰即判通关。
  这在「整关确实填完并结算」时正确，但有两个假阳性窗口：
    1) 导航错位进了别的关并通关 → 目标格仍是灰，但脚本没看其它格 → 误报该关已通
    2) 目标格中心像素碰巧蓝（光标/边框/抖动）→ 误判
  本脚本补强：读选关页整页 35 格，输出每格蓝/灰占比，
  并给出「哪几格已蓝（=已通关）、哪几格仍灰（=未通）」的完整清单。
  判定标准：目标格蓝 且 其它非目标格保持灰（蓝格集合 == 预期已通关集合）→ 强通关。
"""
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, 'ai-tas/scripts'))

import numpy as np
from PIL import Image

import kanji_common as F


def scan_grid(path):
    """返回 {level: (blue_ratio, gray_ratio)}，level=1..35。"""
    img = np.array(Image.open(path).convert('RGB')).astype(int)[192:384]
    out = {}
    for lv in range(1, 36):
        x, y = F.level_xy(lv)
        c = img[y - 5:y + 6, x - 9:x + 10]
        blue = float((np.abs(c - np.array(F.CLEARED_BLUE)).max(2) <= 12).mean())
        gray = float((np.abs(c - np.array(F.UNCLEARED_GRAY)).max(2) <= 12).mean())
        out[lv] = (blue, gray)
    return out


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--level', type=int, default=None, help='目标关（不填则只报告全网格）')
    ap.add_argument('--path', default=None, help='截图路径（默认现场抓帧）')
    args = ap.parse_args()

    if args.path is None:
        args.path = F.shot(os.path.join(F.DIAG_DIR, '_gridchk.png'))
    res = scan_grid(args.path)

    blue_set = [lv for lv, (b, g) in res.items() if b > g]
    print('=== 选关页全网格扫描 ===')
    print('已通关(蓝):', blue_set if blue_set else '无')
    for lv in range(1, 36, 5):
        row = []
        for c in range(5):
            n = lv + c
            b, g = res[n]
            mark = 'B' if b > g else ('G' if g > b else '.')
            row.append('No.%02d:%s(%.0f%%)' % (n, mark, max(b, g) * 100))
        print('  ' + '  '.join(row))

    if args.level:
        lv = args.level
        b, g = res.get(lv, (0, 0))
        ok = b > g
        # 强判定：目标格蓝，且蓝格集合不含「预期外」的关卡
        # （如果只跑了这一关，预期蓝格集合 == {lv}）
        print()
        print('目标 No.%02d: 蓝 %.0f%% / 灰 %.0f%% -> %s'
              % (lv, b * 100, g * 100, '✅ 已通关' if ok else '❌ 未通关'))
        if ok:
            unexpected = [x for x in blue_set if x != lv]
            if unexpected:
                print('⚠️ 但还有这些格也蓝了（可能误入其它关并通关）:',
                      unexpected)
                print('   判定为【可疑】，建议人工核对')
            else:
                print('✅ 蓝格集合 == {No.%02d}，无意外蓝格，强通关成立' % lv)


if __name__ == '__main__':
    main()