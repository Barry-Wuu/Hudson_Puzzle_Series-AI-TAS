#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mode2 多页关（候选 >48）重规划：**页分组升序** + 页内受限搜索（§S57）。

背景（用户 2026-10-16）：「每关至多只需要一次翻页」——plans.json 里模式1/3 共
164 条计划翻页 1-2 次（它们的种子顺序来自 plan_fast 的 group_by_page=True），
但 mode2 旧串由**无页约束**的 lr_plan.search_order（400 次全序列随机交换）产出，
2 页盘仍翻 8~20 次、rec281 三页盘 29 次（实测分布：翻页>2 的 rec 全部是 mode2）。

本工具（一次性离线，运行时零计算）：
  1. 徽章按候选页**升序**重排——2026-10-16 实测（rec270/250/285 双页盘 +
     rec281 三页盘，格芯墨点判据）：列表面板进关**恒开在第0页**，旧 §U
     「停末页」假设作废（它让降序组从第0页出发先绕去末页，双页盘反而 2 次
     翻页）。升序组从第0页顺序走到末页 = npages-1 次翻页（2 页盘 1 次、
     3 页盘 2 次），即「前/次」循环模型下的下限；
  2. 页内保持槽序做种子，用**页内受限交换**轻量搜索（DP 精确计移动成本，
     得分按攒批执行器实测单价：箭头 0.06s / 跳跃 0.08s / 翻页 0.21s）；
  3. lr_plan.emit 产出新 L/R 串，经 runner 同款窗口态模拟自校验后写回
     plans.json（PS.save，flock 单写者）。

运行时翻页由 runner 的循环模型按**实测开页页号**重建（§U），本工具产出的
page 步仅占位；自校验统一按开第0页（start_page=0）计数。

用法：
  python3 replan_mode2_paged.py --dry            # 只对比不写盘
  python3 replan_mode2_paged.py                  # 全部 31 个多页 rec 重规划写回
  python3 replan_mode2_paged.py --rec 250 270    # 指定 rec
"""
import argparse
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('DISPLAY', ':99')

import plan_fast as P                    # noqa: E402
import plan_store as PS                  # noqa: E402
import lr_plan as LR                     # noqa: E402
import mode2_fill as M                   # noqa: E402
import run_mode2_easy1_fast as R         # noqa: E402

# 攒批执行器实测单价（§S55/§S46：tap=0.02+0.02+0.02；hop=0.05+0.03；翻页另等 0.15）
T_TAP = 0.06
T_HOP = 0.08
T_FLIP = 0.21


def est_time(n_map, n_kanji, n_arrow, n_hop, n_flip):
    return (T_TAP * (n_map + n_kanji + n_arrow + n_flip)
            + 0.02 * n_kanji + T_HOP * n_hop + 0.15 * n_flip)


def replan_rec(rec, iters, dry, W, H):
    fill, cands, bc, W2, H2 = M._mode2_data(rec)
    assert (W2, H2) == (W, H)
    cells = {b: sorted(bc[b], key=lambda c: (c[1], c[0])) for b in bc}
    page_of = {b: cands.index(fill[b]) // P.PAL_PAGE for b in fill}
    pages = sorted(set(page_of.values()))      # 升序：面板恒开第0页（2026-10-16 实测）
    npages = len(pages)
    groups = {pg: [b for b in sorted(fill.keys()) if page_of[b] == pg] for pg in pages}

    def flat(gs):
        return [b for pg in pages for b in gs[pg]]

    # 旧串统计（用于对比；翻页按实测开页页号=0 重建）
    old_seq = PS.get(rec)
    old_st = R.SC.seq_stats(old_seq)
    old_flips = None
    plan_local, (Rw, Cw), _ = R.load_plan(rec)
    _fixed, old_flips, _ep, _nh = R.rebuild_pages_sim(
        old_seq, plan_local, Rw, Cw, 0, npages)

    # 种子：页升序 + 页内槽序
    cur = {pg: list(v) for pg, v in groups.items()}
    best_ord = flat(cur)
    best = LR.dp(best_ord, cells, W, H, 1.22)
    best_sc = best[0][0] * T_TAP + best[0][1] * T_HOP
    rnd = random.Random(7)
    for _ in range(iters):
        pg = rnd.choice(pages)
        g = cur[pg]
        if len(g) < 2:
            continue
        saved = list(g)
        if rnd.random() < 0.5:
            i, j = sorted(rnd.sample(range(len(g)), 2))
            g[i:j + 1] = g[i:j + 1][::-1]
        else:
            i, j = rnd.sample(range(len(g)), 2)
            g[i], g[j] = g[j], g[i]
        cand_ord = flat(cur)
        dpr = LR.dp(cand_ord, cells, W, H, 1.22)
        sc = dpr[0][0] * T_TAP + dpr[0][1] * T_HOP
        if sc < best_sc:
            best_sc, best_ord, best = sc, cand_ord, dpr
        else:
            cur[pg] = saved

    seq, arrows, n_hop, n_page = LR.emit(best_ord, best[0][2], fill, cands, cells)
    n_map = sum(1 for s in seq if s[0] == 'map')
    n_kanji = sum(1 for s in seq if s[0] == 'kanji')
    n_arrow = sum(arrows.values())
    # 自校验：新串过 runner 同款模拟（含 kanji 坐标校验），按开第0页数运行时翻页
    fixed, new_flips, endpage, nohop = R.rebuild_pages_sim(
        seq, plan_local, Rw, Cw, 0, npages)
    new_t = est_time(n_map, n_kanji, n_arrow, n_hop, new_flips)
    old_t = est_time(old_st['n_touch'] // 2, old_st['n_touch'] // 2,
                     old_st['n_arrow'], old_st['n_hop'], old_flips)
    print('rec%-3d 页%d 组%-3d | 旧：箭头%-3d 跳跃%-3d 翻页%-2d 估%.2fs → '
          '新：箭头%-3d 跳跃%-3d 翻页%-2d 估%.2fs（%+.2fs）%s'
          % (rec, npages, len(fill), old_st['n_arrow'], old_st['n_hop'], old_flips,
             old_t, n_arrow, n_hop, new_flips, new_t, new_t - old_t,
             '✓' if new_flips == npages - 1 else '❌翻页≠页数-1'))
    if not dry:
        PS.save({rec: {'seq': seq}})
    return new_t - old_t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rec', type=int, nargs='*', default=None)
    ap.add_argument('--iters', type=int, default=100)
    ap.add_argument('--dry', action='store_true')
    a = ap.parse_args()

    # 多页 rec：候选 >48（yasashii 的 rec250 15x15 也在内——正是「易慢于尺寸」那关）
    recs = a.rec if a.rec else []
    if not recs:
        import kanji_common as KC
        for _diff, _recs in KC.MODE2_REC.items():
            for rec in _recs:
                _p, _rc, _s, cands = R.beam_load(rec)
                if len(cands) > P.PAL_PAGE:
                    recs.append(rec)
        recs.sort()
    print('待重规划 %d 个多页 rec：%s（iters=%d%s）'
          % (len(recs), recs, a.iters, '，dry 不写盘' if a.dry else ''), flush=True)
    t0 = time.time()
    tot = 0.0
    for rec in recs:
        plan, (Rw, Cw), _slots, _c = R.beam_load(rec)
        tot += replan_rec(rec, a.iters, a.dry, Cw, Rw)
    print('=== 完成 %d 关，耗时 %.1fs，估时净变化 %+.2fs%s ==='
          % (len(recs), time.time() - t0, tot, '' if a.dry else '（已写回 plans.json）'))


if __name__ == '__main__':
    main()
