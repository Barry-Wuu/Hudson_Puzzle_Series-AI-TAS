#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模式2 認定題库 rec252-259 的 L/R 串生成 → plans.json（单页盘，无翻页）。

認定盘 13-15 见方、候选 ≤47 <48 ⇒ 全部单页（page_of 恒 0），页序无优化空间；
页内沿用 replan_mode2_paged 的受限交换搜索（DP 精确成本）。
产出经 runner 同款 rebuild_pages_sim 自校验（kanji 坐标决定性）。

用法：
  python3 make_cert_plans.py --dry     # 只对比不写盘
  python3 make_cert_plans.py           # 生成 8 条写回 plans.json
"""
import argparse
import random
import sys

import plan_fast as P                    # noqa: E402
import plan_store as PS                  # noqa: E402
import lr_plan as LR                     # noqa: E402
import mode2_fill as M                   # noqa: E402
import run_mode2_easy1_fast as R         # noqa: E402

CERT_RECS = list(range(252, 260))        # ブロンズ252/253 シルバー254/255 ゴールド256/257 プラチナ258/259
T_TAP, T_HOP = 0.06, 0.08


def est_time(n_map, n_kanji, n_arrow, n_hop):
    return T_TAP * (n_map + n_kanji + n_arrow) + 0.02 * n_kanji + T_HOP * n_hop


def plan_rec(rec, iters, dry):
    fill, cands, bc, W, H = M._mode2_data(rec)
    cells = {b: sorted(bc[b], key=lambda c: (c[1], c[0])) for b in bc}
    npages = max(1, -(-len(cands) // P.PAL_PAGE))
    assert npages == 1, 'rec%d 候选 %d 非单页？' % (rec, len(cands))
    order0 = sorted(fill.keys())

    plan_local, (Rw, Cw), _sm = R.load_plan(rec)

    def sc_of(ordr):
        dpr = LR.dp(ordr, cells, W, H, 1.22)
        return dpr[0][0] * T_TAP + dpr[0][1] * T_HOP, dpr

    best_ord = list(order0)
    best_sc, best = sc_of(best_ord)
    rnd = random.Random(7)
    g = best_ord
    for _ in range(iters):
        saved = list(g)
        if rnd.random() < 0.5:
            i, j = sorted(rnd.sample(range(len(g)), 2))
            g[i:j + 1] = g[i:j + 1][::-1]
        else:
            i, j = rnd.sample(range(len(g)), 2)
            g[i], g[j] = g[j], g[i]
        s2, d2 = sc_of(g)
        if s2 < best_sc:
            best_sc, best_ord, best = s2, list(g), d2
        else:
            g[:] = saved

    seq, arrows, n_hop, n_page = LR.emit(best_ord, best[0][2], fill, cands, cells)
    n_map = sum(1 for s in seq if s[0] == 'map')
    n_kanji = sum(1 for s in seq if s[0] == 'kanji')
    n_arrow = sum(arrows.values())
    # 自校验：runner 同款窗口态模拟（单页 ⇒ 翻页 0；kanji 坐标决定性）
    fixed, flips, _ep, nohop = R.rebuild_pages_sim(seq, plan_local, Rw, Cw, 0, 1)
    assert flips == 0, 'rec%d 单页盘模拟翻页 %d ≠ 0' % (rec, flips)
    print('rec%d %dx%d 组%-3d | 触摸%-3d 箭头%-3d 跳跃%-3d 估时 %.2fs ✓'
          % (rec, W, H, len(fill), n_map + n_kanji, n_arrow, n_hop,
             est_time(n_map, n_kanji, n_arrow, n_hop)), flush=True)
    if not dry:
        PS.save({rec: {'seq': seq}})
    return seq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry', action='store_true')
    ap.add_argument('--iters', type=int, default=500)
    a = ap.parse_args()
    for rec in CERT_RECS:
        plan_rec(rec, a.iters, a.dry)
    print('done%s' % ('（dry，未写盘）' if a.dry else '，已写回 plans.json'))


if __name__ == '__main__':
    main()
