#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按《记录号》(rec) 直接算 L/R 动作序列 —— 不依赖「难度/关卡号」映射。

为什么需要它：
  * 現役流水线（lr_plan / precompute_plans）只能按「难度 + 关卡号」规划，
    而 datasheet 里还有大量**没有登场关卡**的记录：認定問題随机题库（rec35–54 等）、
    未发掘记录（rec175–194、rec252–259）、模式3（ホワイトパズル）全难度 ——
    这些 rec 没有 (diff, level)，跑批处理时无从下手。
  * 本模块直接用 `solve2.solve(idx)` 取数据层解，复用 `lr_plan` 的 DP/顺序搜索/发射。

用法：
  python3 plan_by_rec.py 161                     # 单条，打印统计
  python3 plan_by_rec.py --all --jobs 16         # 全库可解析 rec 批量生成
  python3 plan_by_rec.py --range 0 299           # 指定区间
输出：validation/plans.json（列表第 n 项 = rec n，见 plan_store.py）
"""
import argparse
import multiprocessing as mp
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
sys.path.insert(0, REPO)

import plan_fast as P      # noqa: E402
import lr_plan as LR       # noqa: E402
import plan_store as PS    # noqa: E402
import seq_codec as SC     # noqa: E402
import solve2              # noqa: E402


def build_rec(idx):
    """按记录号取数据层解 → (fill, kanji_order, badge_cells, W, H)。"""
    r = solve2.solve(idx, verbose=False)
    if not r or not r.get('badge_cells'):
        raise SystemExit('rec%d 解析失败（无 badge_cells）' % idx)
    bc = r['badge_cells']
    W = max(c for cs in bc.values() for c, _ in cs) + 1
    H = max(w for cs in bc.values() for _, w in cs) + 1
    return r['fill'], r['kanji_order'], bc, W, H


def order_from_rec(idx, fill, kanji_order, bc, W, H):
    """用 plan_fast 的多策略择优取徽章处理顺序（与 lr_plan.order_from_planfast 同思路，
    但改为按 rec 直接跑 _plan，不经过 level→rec 映射）。

    注意：模式3 的「黑墙」组其解是 ０-９Ａ-Ｊ（不在候选表），`plan_fast._plan` 会因
    `kanji_order.index()` 失败——故这里把墙组的解临时替换成候选表里已有的字（只为取顺序，
    实际发射时墙组会走『黒マス』，见 plan_rec）。"""
    ko_set = set(kanji_order)
    fill_safe = {b: (ch if ch in ko_set else kanji_order[0]) for b, ch in fill.items()}
    best = None
    for s in P.STRATEGIES:
        for gb in (False, True):
            try:
                r = P._plan(idx, fill_safe, kanji_order, bc, W, H, s, group_by_page=gb)
            except SystemExit:
                r = None
            if r is None:
                continue
            total = r['n_touch'] + r['n_arrow'] + 4 * r['n_page']
            key = (total, r['n_page'], r['n_arrow'])
            if best is None or key < best[0]:
                best = (key, r)
    if best is None:
        raise SystemExit('rec%d 所有策略均失败' % idx)
    order = []
    for kind, a, b, note in best[1]['seq']:
        if kind == 'map':
            bd = int(str(note).split('=')[0])
            if bd not in order:
                order.append(bd)
    return order


def cached_rec(idx):
    """读统一仓库 validation/plans.json 的第 idx 项——§S40 起返回 seq 本身（无则 None）。

    ★ 2026-10-15：原来读 `validation/plans_by_rec/rec%03d.json`（255 个单文件），
      已与 plans/、plans_mode2/ 合并成单个 plans.json（下标即 rec）。
    ★ §S40：仓库只存动作序列，这里返回的就是 seq（4 元素 tuple list）。
    """
    return PS.get(idx)


def plan_rec(idx, hop_weight=1.22, search=True, verbose=False, use_cache=True):
    # ★ 2026-10-15：**优先读统一仓库**。`order_from_rec` 的多策略择优 + `LR.search_order`
    #   对 25×20 大盘要 ~60~100s；若在**进关之后**现算，这段全计进游戏内计时器
    #   （实测 rec204 计时器 00:01:45 = 现算 ~100s + 填字 38s）。仓库缓存已随 git 提交
    #   （validation/plans.json），批处理直接读、0s。命令行 --force 或 use_cache=False 才现算。
    if use_cache:
        c = cached_rec(idx)
        if c is not None:
            # §S40：仓库只存 seq，统计（n_touch/n_arrow/…）由 seq 现算；
            # W/H/nbadge 等规划期元数据不再落盘，打印侧已同步改造。
            out = {'rec': idx, 'seq': c}
            out.update(SC.seq_stats(c))
            return out
    fill, kanji_order, bc, W, H = build_rec(idx)
    # ★ 2026-10-15：模式3「ホワイトパズル」的**黑墙组**——其解是全角数字/字母（０-９Ａ-Ｊ），
    #   不在候选表内。这些组不是点字，而是『选中该组 → 按 黒マス 按钮』把它清成墙体。
    #   （实机定论见 PITFALLS §S32；56 个 rec 有此结构。）
    ko_set = set(kanji_order)
    wall_badges = sorted(b for b, ch in fill.items() if ch not in ko_set)
    # 读序 = (行,列)，与 lr_plan.build 一致
    cells = {b: sorted(bc[b], key=lambda c: (c[1], c[0])) for b in bc}
    order0 = order_from_rec(idx, fill, kanji_order, bc, W, H)
    if search:
        _, order, dpr = LR.search_order(order0, fill, kanji_order, cells, W, H, hop_weight)
    else:
        order, dpr = order0, LR.dp(order0, cells, W, H, hop_weight)
    seq, arrows, n_hop, n_page = LR.emit(order, dpr[0][2], fill, kanji_order, cells,
                                         wall_badges=set(wall_badges))
    n_touch = sum(1 for s in seq if s[0] in ('map', 'kanji'))
    n_black = sum(1 for s in seq if s[0] == 'black')
    est = (n_touch * LR.T_ARROW + sum(arrows.values()) * LR.T_ARROW
           + n_hop * LR.T_HOP + n_page * LR.T_PAGE)
    res = {'rec': idx, 'W': W, 'H': H, 'nbadge': len(fill), 'nkanji': len(kanji_order),
           'seq': seq, 'arrows': arrows, 'n_touch': n_touch, 'n_black': n_black,
           'walls': [fill[b] for b in wall_badges],
           'n_arrow': sum(arrows.values()), 'n_hop': n_hop, 'n_page': n_page,
           'pred_fill_s': est}
    if verbose:
        print('rec%-4d 盘面%dx%d 徽章%d 汉字%d | 箭头%d 跳%d 触%d 页%d 墙%d | 预估 %.2fs'
              % (idx, W, H, len(fill), len(kanji_order),
                 res['n_arrow'], n_hop, n_touch, n_page, n_black, est))
    return res


def _work(args):
    """算一条 rec 的规划并**原样返回**（不落盘）。

    ★ 2026-10-15：落盘改由父进程汇总后一次性 `plan_store.save()` ——
      多个 worker 各自对同一个 plans.json 做读—改—写会互相覆盖。
    """
    idx, force = args
    if not force and PS.has(idx):
        return (idx, 'skip', 0.0, '', None)
    t0 = time.time()
    try:
        # ★ 这里必须 use_cache=False：_work 已自带「已缓存就 skip」的逻辑，
        #   若走缓存，--force 重算会被缓存短路、永远刷不出新结果。
        res = plan_rec(idx, verbose=False, use_cache=False)
    except SystemExit as e:
        return (idx, 'FAIL', time.time() - t0, str(e), None)
    return (idx, 'ok', time.time() - t0,
            '箭头%d 跳%d 触%d 页%d 预估%.2fs'
            % (res['n_arrow'], res['n_hop'], res['n_touch'], res['n_page'],
               res['pred_fill_s']), res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('idxs', nargs='*', type=int)
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--range', nargs=2, type=int, metavar=('A', 'B'))
    ap.add_argument('--jobs', type=int, default=0)
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()

    if a.all:
        idxs = list(range(300))
    elif a.range:
        idxs = list(range(a.range[0], a.range[1] + 1))
    else:
        idxs = a.idxs
    if not idxs:
        ap.error('需要 rec 号、--range 或 --all')

    # 父进程只读一次仓库、算出「已缓存」集合传给 worker（免得 N 个 worker 各读一遍 1MB）
    have = frozenset() if a.force else frozenset(i for i in idxs if PS.has(i))
    jobs = a.jobs or min(len(idxs), os.cpu_count() or 4)
    print('按 rec 生成动作序列：%d 条（已缓存 %d），并发 %d → %s'
          % (len(idxs), len(have), jobs, PS.path()), flush=True)
    t0 = time.time()
    ok = fail = skip = 0
    failures = []
    pending = {}                      # rec -> plan，攒一批落盘一次
    FLUSH = 20                        # 每 20 条 save：中途被杀也只丢最后一批
    with mp.Pool(jobs, maxtasksperchild=1) as pool:
        for i, (idx, st, dt, info, res) in enumerate(
                pool.imap_unordered(_work, [(x, a.force) for x in idxs]), 1):
            if st == 'ok':
                ok += 1
                if res is not None:
                    pending[idx] = res
            elif st == 'skip':
                skip += 1
            else:
                fail += 1
                failures.append(idx)
            if st != 'skip':
                print('  [%d/%d] rec%-3d %s %.1fs  %s' % (i, len(idxs), idx, st, dt, info),
                      flush=True)
            if len(pending) >= FLUSH:
                PS.save(pending)
                pending.clear()
    if pending:
        PS.save(pending)
    print('完成：ok=%d skip=%d fail=%d，仓库现有 %d 条，总耗时 %.1fs'
          % (ok, skip, fail, PS.stats()['cached'], time.time() - t0))
    if failures:
        print('失败 rec（多半是 solve2 解析不到）：%s' % failures)


if __name__ == '__main__':
    main()
