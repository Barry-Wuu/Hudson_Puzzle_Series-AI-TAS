#!/usr/bin/env python3
"""Vol.10 validation 星数复核。

用法：cd validation && python3 check_stars.py
逐张读 l<NNN>_clear.png 的星星数，与各难度满星标准比对。
判星用位置模式（不是数金色段），详见 README.md。
"""
import os, sys, glob
import numpy as np
from PIL import Image

FULL = {            # 难度目录 -> (满星数, 首关, 末关)
    'mode1_tutorial': (3, 2, 20),
    'mode2_easy':     (4, 1, 100),
    'mode3_medium':   (5, 1, 100),
    'mode4_hard':     (6, 1, 80),
}
Y0, Y1 = 292, 328          # 星星行带
GOLD = lambda a: (a[:, :, 0] > 170) & (a[:, :, 1] > 150) & (a[:, :, 1] < 235) & (a[:, :, 2] < 110)


def stars(path):
    a = np.asarray(Image.open(path).convert('RGB'), dtype=int)[Y0:Y1]
    m = GOLD(a)
    col = m.sum(axis=0)
    on = col >= 1
    raw, prev, st = [], False, 0
    for k, v in enumerate(on):
        if v and not prev:
            st = k
        if prev and not v:
            raw.append([st, k - 1])
        prev = v
    if prev:
        raw.append([st, len(on) - 1])
    # 合并间隙 <=4px 的相邻段：抗锯齿会把一颗星拆成两段
    segs = []
    for s, e in raw:
        if segs and s - segs[-1][1] - 1 <= 4:
            segs[-1][1] = e
        else:
            segs.append([s, e])
    good = []
    for s, e in segs:
        w = e - s + 1
        ys, _ = np.where(m[:, s:e + 1])
        h = (ys.max() - ys.min() + 1) if len(ys) else 0
        if 10 <= w <= 17 and 11 <= h <= 17:
            good.append(s)
    good.sort()
    if not good:
        return 0
    chain = [good[0]]
    for x in good[1:]:
        if 17 <= x - chain[-1] <= 24:
            chain.append(x)
        else:
            break
    return len(chain)


def orange(path):
    a = np.asarray(Image.open(path).convert('RGB'), dtype=int)
    R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    return int(((R > 200) & (G > 90) & (G < 190) & (B < 110)).sum())


def main():
    base = os.path.dirname(os.path.abspath(__file__))
    total_bad = 0
    for d, (need, lo, hi) in FULL.items():
        pdir = os.path.join(base, d)
        files = sorted(glob.glob(os.path.join(pdir, 'l*_clear.png')))
        hist, bad, done_only = {}, [], []
        for f in files:
            n = int(os.path.basename(f)[1:4])
            s = stars(f)
            hist[s] = hist.get(s, 0) + 1
            if s < need:
                # 完成图判定：橙色「完成!」大字像素量（实测 2650~2890）
                # 与结算页（实测 80~103）区分极明显；阈值 1500
                if need == 5 and orange(f) >= 1500:
                    done_only.append(n)      # 完成图，按规则允许
                else:
                    bad.append((n, s))
        print(f'{d}: {len(files)} 张 满星{need}★ 星数分布={dict(sorted(hist.items()))}')
        if done_only:
            print(f'  完成图（无星结算，按规则允许）{len(done_only)} 张')
        if bad:
            total_bad += len(bad)
            print(f'  !! 异常 {len(bad)} 张: {bad[:12]}')
        # 连续性
        got = {int(os.path.basename(f)[1:4]) for f in files}
        miss = [n for n in range(lo, hi + 1) if n not in got]
        if miss:
            print(f'  缺号（{len(miss)}）: {miss[:15]}')
    print('\n结论:', '全部通过' if total_bad == 0 else f'{total_bad} 张异常')
    return 0 if total_bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
