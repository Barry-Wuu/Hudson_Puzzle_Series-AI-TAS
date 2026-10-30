#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""「游戏关卡 ↔ datasheet 记录号」全表打印 —— 防止重复发掘 rec。

模式1/2/3「通常問題」的全部难度 rec 映射已经逐关实机锚定，并**固化**在
`kanji_common.rec_for(mode, diff, level)`（模式1 走 level_to_rec 分段公式，
模式2/3 查 MODE2_REC / MODE3_REC）。本脚本只是把它打印出来，方便一眼查阅。

★ 想加新的模式/难度：只改 `kanji_common.py` 里的 MODE2_REC / MODE3_REC，
  不要在本脚本里写死 rec。方法学（怎么锚定）见 REPORT.md §8b / PITFALLS.md §S29。

用法：
    python3 show_rec_map.py            # 三个模式通常問題全表
    python3 show_rec_map.py --mode 2   # 只看模式2
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from kanji_common import rec_for  # noqa: E402

# (难度 key, 显示名, 关数)
MODES = {
    1: ('漢字ナンクロ', [('yasashii', 'やさしい', 35),
                        ('futsuu', 'ふつう', 60),
                        ('muzukashii', 'むずかしい', 65)]),
    2: ('ひりどりナンクロ', [('yasashii', 'やさしい', 7),
                           ('futsuu', 'ふつう', 15),
                           ('muzukashii', 'むずかしい', 15)]),
    3: ('ホワイトパズル', [('yasashii', 'やさしい', 15),
                         ('futsuu', 'ふつう', 15),
                         ('muzukashii', 'むずかしい', 25)]),
}


def fmt(recs):
    """把 rec 序列压成 `a-b, c, d-e` 形式。"""
    segs, s, p = [], recs[0], recs[0]
    for r in recs[1:]:
        if r == p + 1:
            p = r
            continue
        segs.append((s, p))
        s = p = r
    segs.append((s, p))
    return ', '.join('%d' % a if a == b else '%d-%d' % (a, b) for a, b in segs)


def main():
    want = None
    if '--mode' in sys.argv:
        want = int(sys.argv[sys.argv.index('--mode') + 1])
    for m, (name, diffs) in MODES.items():
        if want and m != want:
            continue
        print('===== 模式%d %s（通常問題）=====' % (m, name))
        for diff, dn, n in diffs:
            recs = [rec_for(m, diff, lv) for lv in range(1, n + 1)]
            print('  %-5s No.01-%02d（%2d 关）：rec %s' % (dn, n, n, fmt(recs)))
        print()
    # 模式1 認定問題（2026-10-15 实测，见 PITFALLS §S50）：4 级 = 4 段连续 5 题
    if want in (None, 1):
        from kanji_common import KENTEI_REC, kentei_recs  # noqa: E402
        print('===== 模式1 漢字ナンクロ（認定問題，题库 rec35-54）=====')
        for lv in ('bronze', 'silver', 'gold', 'platinum'):
            print('  %-8s：rec %s（每级进盘随机抽 1 题，有放回）' % (lv, fmt(kentei_recs(lv))))
        print()
    # 模式3 認定問題（2026-10-15 实测，见 PITFALLS §S52）：题库 = 原「模式3 额外段」rec175-194
    if want in (None, 3):
        from kanji_common import kentei_recs  # noqa: E402
        print('===== 模式3 ホワイトパズル（認定問題，题库 rec175-194）=====')
        for lv in ('bronze', 'silver', 'gold', 'platinum'):
            print('  %-8s：rec %s（每级进盘随机抽 1 题，有放回）' % (lv, fmt(kentei_recs(lv, 3))))
        print()
    print('取自 kanji_common.rec_for(mode, diff, level)；'
          '别处请调用它，不要重新发掘。')


if __name__ == '__main__':
    main()
