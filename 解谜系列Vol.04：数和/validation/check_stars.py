#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Vol.4 validation 逐关通关证据 · 星数复核。

用法：cd validation && python3 check_stars.py

判星（按 Vol.4 实测标定，与 Vol.10 的 y=292..328 不同）：
  · 星星行带 y=322..348（下屏蓝色结算页内，クリアタイム 框下方）
  · 暖色掩码 (R>150)&(R>B+60)&(G>B+25)&(G>90)：金星是橙金色，
    蓝底/白框都不满足；得点旁的大金星在 y≈365，不在行带内，不会误计
  · 列投影切段 → 合并间隙 ≤4px（复原被抗锯齿拆开的单颗星）
    → 只保留宽 8~20px 的段 → 段数即星数
  · 实测：ふつう 5 段（x≈98 起，间距 ≈16）、むずかしい 6 段（x≈92 起，间距 ≈16）

满星按 Vol.4 实测：入門 4 / やさしい 4 / ふつう 5 / むずかしい 6。
注意与 Vol.10 的「难度序号 + 2 = 3/4/5/6」不同——本卷入門实测就是 4★
（310 张逐张复核：入門 19 张视频帧全 4 段、やさしい 90 张 4 段、
ふつう 120 张 5 段、むずかしい 80 张 6 段）。
"""
import glob
import os
import sys

import numpy as np
from PIL import Image

FULL = {                       # 难度目录 -> (满星数, 首关, 末关)
    'mode1_tutorial': (4, 1, 20),
    'mode2_easy':     (4, 1, 90),
    'mode3_medium':   (5, 1, 120),
    'mode4_hard':     (6, 1, 80),
}
Y0, Y1 = 322, 348


def star_count(path):
    """返回一张 256×384 结算截图的星数。"""
    a = np.asarray(Image.open(path).convert('RGB'), dtype=int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    warm = (R > 150) & (R > B + 60) & (G > B + 25) & (G > 90)
    col = warm[Y0:Y1].sum(axis=0)
    on = col >= 2
    raw, prev, st = [], False, 0
    for k, v in enumerate(on):
        if v and not prev:
            st = k
        if prev and not v:
            raw.append([st, k - 1])
        prev = v
    if prev:
        raw.append([st, len(on) - 1])
    segs = []
    for s, e in raw:
        if segs and s - segs[-1][1] - 1 <= 4:
            segs[-1][1] = e
        else:
            segs.append([s, e])
    return sum(1 for s, e in segs if 8 <= e - s + 1 <= 20)


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    total_bad = 0
    for d, (need, lo, hi) in FULL.items():
        pdir = os.path.join(base, d)
        files = sorted(glob.glob(os.path.join(pdir, 'l*_clear.png')))
        hist, bad = {}, []
        for f in files:
            n = int(os.path.basename(f)[1:4])
            s = star_count(f)
            hist[s] = hist.get(s, 0) + 1
            if s != need:
                bad.append((n, s))
        got = {int(os.path.basename(f)[1:4]) for f in files}
        miss = [n for n in range(lo, hi + 1) if n not in got]
        print('%s: %d 张 满星%d★ 星数分布=%s' %
              (d, len(files), need, dict(sorted(hist.items()))))
        if bad:
            total_bad += len(bad)
            print('  !! 非满星 %d 张: %s' % (len(bad), bad[:12]))
        if miss:
            total_bad += len(miss)
            print('  !! 缺号 %d 张: %s' % (len(miss), miss[:15]))
    print('\n结论:', '全部满星且齐号' if total_bad == 0 else '%d 项异常' % total_bad)
    return 0 if total_bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
