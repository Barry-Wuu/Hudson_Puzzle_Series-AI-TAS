#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""L/R 肩键版快通规划器：在 plan_fast 的徽章顺序上做 DP，用「跳跃」替掉大量箭头。

机制（§S12 实机逐帧定论，务必遵守）：
  * 每枚徽章的待填格按 **读序 = (行,列) 排序** 循环；`R`（键 `w`）向前、`L`（键 `q`）向后；
  * **每一次 hop 都把缩略图窗口重锚到 `clamp(光标格)`**（不只是离开窗口时）；
  * ⇒ 一次 hop 能把窗口「传送」到同一徽章另一格近旁，替掉大量箭头。
  * **顺序约束**：hops 必须在「点缩略图选中该徽章之后、点汉字之前」发射
    —— 此时该徽章各格仍为白色待填，跳得动；绑完变蓝就跳不动了（§S12）。

输出结构与 `plan_fast.plan()` 一致，seq 里新增 `('hop', 'w'|'q', 0, note)`。
用法:
  python3 lr_plan.py --level 1 --dry-run            # 打印统计
  python3 lr_plan.py --level 1 --json > plan.json   # 给执行器消费
"""
import argparse
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))
os.environ.setdefault('AI_TAS_DIFFICULTY', 'futsuu')

import plan_fast as P     # noqa: E402
import plan_store as PS   # noqa: E402  （统一动作序列仓库 validation/plans.json）
import seq_codec as SC    # noqa: E402  （seq 统计现算，§S40）
import kanji_common as KC  # noqa: E402  （(模式,难度,关卡) → rec 换算）

WIN = 4
HOP_KEY = {1: 'w', -1: 'q'}          # R=w 向前, L=q 向后
# 模式3「ホワイトパズル」の 黒マス 按钮（下屏底部、D-pad 右下的小黑方块）
# 实机标定 2026-10-15：底屏相对坐标 (111,168)。按它把当前选中组的格子清空成墙体。
BLACK_XY = (int(os.environ.get('AI_TAS_BLACK_X', 111)),
            int(os.environ.get('AI_TAS_BLACK_Y', 168)))
# 实测单价（2026-10-12）：虚拟箭头/触摸点按 0.0645s；可靠跳跃 0.079s（keydown+0.05+keyup）
T_ARROW = float(os.environ.get('LR_T_ARROW', 0.0645))
T_HOP = float(os.environ.get('LR_T_HOP', 0.079))
T_PAGE = float(os.environ.get('LR_T_PAGE', 0.5))


def cached_plan(level, diff=None):
    """从统一仓库 `validation/plans.json` 读模式1「难度+关卡」的规划（无则 None）。

    `diff` 参数仅为兼容旧签名保留，实际一律用 `kanji_common.DIFF`（见下方说明）。
    ★ 2026-10-15：原来的 `validation/plans/<diff>_l<NN>.json`（160 个单文件）已与
      `plans_mode2/`、`plans_by_rec/` 合并成**单个** `validation/plans.json`
      （列表第 n 项 = rec n，见 plan_store.py）。这里经 `kanji_common.rec_for`
      把「难度+关卡」换算成 rec 再查表 —— 与 `plan_by_rec` 走同一份数据。
    难度口径必须与算一侧完全一致：`build()`→`plan_fast.solve()` 用的是
      **导入时快照的 `kanji_common.DIFF`**（不是现读环境变量），故这里也用 `KC.DIFF`。
    ★ §S40：仓库只存 seq——原「命中仍校验 level/diff 回显」随字段一并移除
      （防串关改依 `KC.rec_for` 单一事实来源 + 仓库惯例：改映射/规划器后重跑
      `precompute_plans.py` 刷新，见 PITFALLS §S40）。返回 dict 的统计字段
      由 `seq_codec.seq_stats` 从 seq 现算。
    """
    diff = KC.DIFF
    try:
        rec = KC.rec_for(1, diff, level)
    except SystemExit:
        return None
    seq = PS.get(rec)
    if seq is None:
        return None
    out = {'rec': rec, 'level': level, 'seq': seq}
    out.update(SC.seq_stats(seq))
    return out


def build(level):
    fill, kanji_order, bc, W, H = P.solve(level)
    # ★ 读序 = 按 (行,列) 排；badge_cells 元组是 (列,行)
    cells = {b: sorted(bc[b], key=lambda c: (c[1], c[0])) for b in bc}
    return fill, kanji_order, cells, W, H


def clamp_cell(cell, H, W):
    col, row = cell
    return (min(max(row, 0), H - WIN), min(max(col, 0), W - WIN))


def move_to(o, cell, H, W):
    col, row = cell
    rlo, rhi = max(0, row - WIN + 1), min(row, H - WIN)
    clo, chi = max(0, col - WIN + 1), min(col, W - WIN)
    nr = min(max(o[0], rlo), rhi)
    nc = min(max(o[1], clo), chi)
    return (nr, nc), abs(nr - o[0]) + abs(nc - o[1])


def transitions(o, cs, H, W):
    """[(o_arrow, mc, ei, h, d, o_after)]：先箭头把窗口挪到能含 cs[ei]，再可选 h 次跳"""
    out = []
    n = len(cs)
    for ei, e in enumerate(cs):
        o2, mc = move_to(o, e, H, W)
        out.append((o2, mc, ei, 0, 0, o2))
        for d in (1, -1):
            idx, oo = ei, o2
            for h in range(1, n):
                idx = (idx + d) % n
                oo = clamp_cell(cs[idx], H, W)
                out.append((o2, mc, ei, h, d, oo))
    return out


def dp(order, cells, W, H, hop_weight=1.0, beam=48):
    """对固定徽章顺序求 (箭头, 跳跃) 精确 dp（束搜索限宽）。返回 (best_key, path)"""
    st = {(0, 0): (0, 0, ())}            # origin -> (arrows, hops, path)
    for b in order:
        cs = cells[b]
        new = {}
        for o, (ar, hp, path) in st.items():
            for (o2, mc, ei, h, d, oa) in transitions(o, cs, H, W):
                key = (ar + mc, hp + h)
                cur = new.get(oa)
                if cur is None or (key[0] + hop_weight * key[1]) < (cur[0] + hop_weight * cur[1]):
                    new[oa] = (key[0], key[1], path + ((o2, ei, h, d, mc, oa),))
        st = dict(sorted(new.items(), key=lambda kv: kv[1][0] + hop_weight * kv[1][1])[:beam])
    o, v = min(st.items(), key=lambda kv: kv[1][0] + hop_weight * kv[1][1])
    return v, o


def order_from_planfast(level):
    pf = P.plan(level)
    order = []
    for kind, a, b, note in pf['seq']:
        if kind == 'map':
            bd = int(str(note).split('=')[0])
            if bd not in order:
                order.append(bd)
    return order, pf


def count_pages(order, fill, kanji_order):
    cur, n = 0, 0
    ko = set(kanji_order)
    for b in order:
        ch = fill[b]
        if ch not in ko:
            continue          # 模式3「黑墙」组：不点字、不翻页
        wp = P.kanji_page(ch, kanji_order)
        n += abs(wp - cur)
        cur = wp
    return n


def search_order(order, fill, kanji_order, cells, W, H, hop_weight, iters=400, seed=7):
    """轻量顺序搜索：目标 = 箭头 + 跳跃 + 4×翻页（翻页实价 ~0.5s ≈ 8 次点按，取 4 稳）"""
    def score(ordr, p):
        ar, hp = p[0][0], p[0][1]
        return ar * T_ARROW + hp * T_HOP + count_pages(ordr, fill, kanji_order) * T_PAGE

    best_path = dp(order, cells, W, H, hop_weight)
    best = (score(order, best_path), list(order), best_path)
    rnd = random.Random(seed)
    n = len(order)
    for _ in range(iters):
        cand = list(best[1])
        if rnd.random() < 0.5:
            i, j = sorted(rnd.sample(range(n), 2))
            cand[i:j + 1] = cand[i:j + 1][::-1]
        else:
            i, j = rnd.sample(range(n), 2)
            cand[i], cand[j] = cand[j], cand[i]
        p = dp(cand, cells, W, H, hop_weight)
        sc = score(cand, p)
        if sc < best[0]:
            best = (sc, cand, p)
    return best


def emit(order, path, fill, kanji_order, cells, wall_badges=None):
    """wall_badges: 模式3「黑墙」组（解不在候选表内）——这些组只发『点格选中 + 按黒マス』，
    不翻页、不点字（实机 2026-10-15 定论：黒マス 按钮把该组格子清空成墙体）。"""
    seq = []
    arrows = {'R': 0, 'D': 0, 'L': 0, 'U': 0}
    n_hop = 0
    cur_lpage = 0
    n_page = 0
    o = (0, 0)
    for b, step in zip(order, path):
        o_arrow, ei, h, d, mc, o_after = step
        while o[0] != o_arrow[0]:
            dd = 'D' if o_arrow[0] > o[0] else 'U'
            o = (o[0] + (1 if dd == 'D' else -1), o[1])
            seq.append(('arrow', P.ARROW[dd][0], P.ARROW[dd][1],
                        '缩略图%s' % ('↓' if dd == 'D' else '↑')))
            arrows[dd] += 1
        while o[1] != o_arrow[1]:
            dd = 'R' if o_arrow[1] > o[1] else 'L'
            o = (o[0], o[1] + (1 if dd == 'R' else -1))
            seq.append(('arrow', P.ARROW[dd][0], P.ARROW[dd][1],
                        '缩略图%s' % ('→' if dd == 'R' else '←')))
            arrows[dd] += 1
        e = cells[b][ei]
        seq.append(('map', e[1] - o[0], e[0] - o[1], '%d=%s' % (b, fill[b])))
        for _ in range(h):
            seq.append(('hop', HOP_KEY[d], 0, '跳跃%s' % ('R' if d == 1 else 'L')))
            n_hop += 1
        o = o_after
        if wall_badges and b in wall_badges:
            seq.append(('black', BLACK_XY[0], BLACK_XY[1], '黒マス'))
            continue
        wp = P.kanji_page(fill[b], kanji_order)
        while cur_lpage < wp:
            seq.append(('page', P.LIST_NEXT_D[0], P.LIST_NEXT_D[1], 'リスト次'))
            cur_lpage += 1
            n_page += 1
        while cur_lpage > wp:
            seq.append(('page', P.LIST_PREV_D[0], P.LIST_PREV_D[1], 'リスト前'))
            cur_lpage -= 1
            n_page += 1
        ki, kj = P.kanji_pos(fill[b], kanji_order)
        seq.append(('kanji', ki, kj, fill[b]))
    return seq, arrows, n_hop, n_page


def make_plan(level, hop_weight=1.22, search=True, verbose=True, use_cache=True):
    # ★ 规划一次要 ~15s（束搜索 400 iters，中1 实测 15.5s）。若在**录实况时现算**，
    #   视频里会录进十几秒「进关后画面一动不动」（PITFALLS §S22）——因为这段耗时
    #   发生在 fill() 的计时器 t0 之前，既不算进 fill 也不算进 nav。
    #   ⇒ 设 AI_TAS_PLAN_FILE=<json>：命中则 0s 直接读；未命中则算完写回（供预热用）。
    # ★ 2026-10-15：默认缓存来源 = 统一仓库 `validation/plans.json`（plan_store，
    #   下标即 rec）。仓库命中只读不写；只有显式 AI_TAS_PLAN_FILE 才写回那个文件
    #   （record_trial.sh 的 /tmp 预热仍靠它）。量产规划由 precompute_plans.py
    #   在父进程汇总后一次性 save() 进 plans.json。
    cache = os.environ.get('AI_TAS_PLAN_FILE')
    if use_cache and not cache:
        c = cached_plan(level)
        if c is not None:
            if verbose:
                print('[plan] 复用仓库缓存 %s rec%d（跳过 ~15s 束搜索）'
                      % (os.path.relpath(PS.path()), c['rec']))
            return c
    if cache and os.path.exists(cache):
        try:
            with open(cache, encoding='utf-8') as _f:
                _cached = json.load(_f)
            if _cached.get('level') == level:
                if verbose:
                    print('[plan] 复用缓存 %s（跳过 ~15s 束搜索）' % cache)
                return _cached
        except Exception:
            pass
    fill, kanji_order, cells, W, H = build(level)
    order0, pf = order_from_planfast(level)
    if search:
        _, order, dpr = search_order(order0, fill, kanji_order, cells, W, H, hop_weight)
    else:
        order, dpr = order0, dp(order0, cells, W, H, hop_weight)
    (ar, hp, _p), origin = dpr
    seq, arrows, n_hop, n_page = emit(order, dpr[0][2], fill, kanji_order, cells)
    n_touch = sum(1 for s in seq if s[0] in ('map', 'kanji'))
    est = n_touch * T_ARROW + sum(arrows.values()) * T_ARROW + n_hop * T_HOP + n_page * T_PAGE
    res = {'level': level, 'W': W, 'H': H, 'nbadge': len(fill), 'nkanji': len(kanji_order),
           'seq': seq, 'arrows': arrows, 'n_touch': n_touch,
           'n_arrow': sum(arrows.values()), 'n_hop': n_hop, 'n_page': n_page,
           'pred_fill_s': est, 'plan_fast_arrow': pf['n_arrow'],
           'rec': KC.rec_for(1, KC.DIFF, level), 'mode': 1, 'diff': KC.DIFF}
    if verbose:
        print('No.%02d 盘面%dx%d 徽章%d 汉字%d' % (level, W, H, len(fill), len(kanji_order)))
        print('  现役 plan_fast：箭头 %d + 触摸 %d + 翻页 %d' %
              (pf['n_arrow'], pf['n_touch'], pf.get('n_page', 0)))
        print('  L/R 方案：箭头 %d + 跳跃 %d + 触摸 %d + 翻页 %d  (总动作 %d)' %
              (sum(arrows.values()), n_hop, n_touch, n_page, len(seq)))
        print('  预计填字段 %.2fs（按箭头/触摸 %.4fs、跳跃 %.4fs、翻页 %.1fs 估）'
              % (est, T_ARROW, T_HOP, T_PAGE))
    if cache:
        try:
            _tmp = cache + '.tmp'
            with open(_tmp, 'w', encoding='utf-8') as _f:
                json.dump(res, _f, ensure_ascii=False)
            os.replace(_tmp, cache)
        except Exception:
            pass
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--level', type=int, default=1)
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--hop-weight', type=float, default=1.22)
    ap.add_argument('--no-search', action='store_true')
    a = ap.parse_args()
    r = make_plan(a.level, hop_weight=a.hop_weight, search=not a.no_search)
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
