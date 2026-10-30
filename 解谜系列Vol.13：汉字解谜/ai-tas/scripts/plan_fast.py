#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快通序列规划器（纯计算，不读任何图、不碰模拟器）。

★ 本模块是「先算后打」原则的核心：动作序列 100% 由 datasheet 离线推导，
  不需要读屏幕掩码、不需要找橙色光标、不需要任何视觉闭环。

═══ 机制（PITFALLS §Q3 / §R，语义由用户 2026-10-11 确认）═══
* 下屏缩略图是**谜题盘面上的 4×4 滑动窗口**，初始停在左上角。
* 点缩略图格 (i,j) == 点选谜题中对应格 (or+i, oc+j)，该格带徽章号时即选中该徽章。
* 缩略图四周 4 个箭头各把窗口**移动一格**（⚠️ 不是翻页）。
* 每徽章只需操作 1 格（绑定后该徽章全部格自动填满）。
* リスト面板常驻，点汉字完成绑定 ⇒ 每徽章 2 次触摸。

═══ 坐标（沿用 fill_fast_level1.py 实机跑通值，单位=按键精灵设计坐标）═══
  缩略图格 (i,j): (43 + 35*j, 333 + 35*i)
  汉字格   (i,j): (230 + 25*j, 337 + 25*i)
  箭头 ▶(177,384) ▼(95,465)  ◀(14,384)▲(95,306) ← 后两个为对称推断，见 PITFALLS §Q3

═══ 关键坐标约定（易错！）═══
  solve2.solve()['badge_cells'] 的元组是 **(col, row)**，不是 (row, col)。
  已用 No.01 硬编码序列 11/11 交叉验证（见 --self-test）。

用法:
  python3 plan_fast.py --level 1              # 打印 No.01 动作序列
  python3 plan_fast.py --level 35 --stats     # 打印 No.35 统计
  python3 plan_fast.py --self-test            # 与 No.01 已知硬编码序列比对
  python3 plan_fast.py --level 16 --json      # 输出 JSON（供 fill_fast_any.py 消费）
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), '..', '..')))

# ---- 几何常量 ------------------------------------------------------------
WIN = 4                      # 缩略图窗口边长（4×4）
KANJI_COLS = 6               # リスト 面板汉字列数（No.01 实测 12 字 = 2 行 × 6 列）
KANJI_ROWS = 8               # リスト 面板**单页行数**（ふつう 实测：8 行 × 6 列 = 48 字/页）
PAL_PAGE = KANJI_COLS * KANJI_ROWS   # 48 字/页；汉字表 >48 字时分页（大难度必跨页）
# リスト 翻页按钮「前 / 次」（下屏 NDS (161,166)/(225,166)，像素实测），换算为设计坐标
# (= (x*1.5, (y+192)*1.5))。此前只在 fill_fast_level1（No.01 12 字单页）中未用到；
# ふつう/むずかしい 汉字表 74~99 字、必跨 リスト 第 2+ 页，故快通序列必须翻页。
LIST_PREV_D = (241, 537)     # 「前」
LIST_NEXT_D = (338, 537)     # 「次」

# 设计坐标（按键精灵 1.5× 空间，与 fill_fast_level1.py 完全一致）
MAP_X0, MAP_Y0, MAP_STEP = 43, 333, 35      # 缩略图格心
KAN_X0, KAN_Y0, KAN_STEP = 230, 337, 25     # 汉字格心
# ▶ / ▼ 已实机跑通；◀ / ▲ 已于 2026-10-11 实机标定（calib_arrows4.py，窗口移到
# (3,3) 后四箭头齐现）：NDS 实测 ◀=(9,60) ▲=(66,7)，换算回设计坐标 =
# (1.5x, 1.5(y+192)) ⇒ ◀=(13.5,378) ▲=(99,298.5)，四舍五入为整点。
# 仍可用环境变量覆盖：AI_TAS_ARROW_{LX,LY,UX,UY}
ARROW = {'R': (177, 384), 'D': (95, 465),
         'L': (int(os.environ.get('AI_TAS_ARROW_LX', 14)),
               int(os.environ.get('AI_TAS_ARROW_LY', 378))),
         'U': (int(os.environ.get('AI_TAS_ARROW_UX', 99)),
               int(os.environ.get('AI_TAS_ARROW_UY', 299)))}    # ▶▼◀▲


def solve(level):
    """取数据层解。返回 (fill, kanji_order, badge_cells, W, H)。

    关卡号→记录号走**难度映射**（kanji_common.rec_for_level，受 AI_TAS_DIFFICULTY 控制）：
      やさしい No.N=rec(N-1)、ふつう No.N=rec(54+N)、むずかしい 分段见 kanji_common。
    """
    import solve2
    import kanji_common as K
    idx = K.rec_for_level(level)
    r = solve2.solve(idx, verbose=False)
    if not r:
        raise SystemExit('⚠️ No.%s（难度 %s，记录 %d）解析失败' % (level, K.DIFF, idx))
    bc = r['badge_cells']
    if not bc:
        raise SystemExit('⚠️ No.%s 无 badge_cells（solve2 版本过旧？）' % level)
    W = max(c for cs in bc.values() for c, _ in cs) + 1
    H = max(w for cs in bc.values() for _, w in cs) + 1
    return r['fill'], r['kanji_order'], bc, W, H


def kanji_pos(ch, kanji_order):
    """汉字在 リスト 面板**页内**的 (行, 列)。列数 KANJI_COLS，每页 PAL_PAGE 字。"""
    i = kanji_order.index(ch)
    i2 = i % PAL_PAGE
    return i2 // KANJI_COLS, i2 % KANJI_COLS


def kanji_page(ch, kanji_order):
    """汉字所在 リスト 页（0-based）：>42 字在第 2 页起。"""
    return kanji_order.index(ch) // PAL_PAGE


def in_window(cell, orow, ocol):
    """格 (col,row) 是否落在窗口 (orow,ocol) 内；返回窗口内相对 (i,j) 或 None。"""
    col, row = cell
    if ocol <= col <= ocol + WIN - 1 and orow <= row <= orow + WIN - 1:
        return row - orow, col - ocol
    return None


def window_range(v, n):
    """要覆盖坐标 v（行或列），窗口原点可取区间 [lo,hi]（裁剪到盘面）。"""
    lo = max(0, v - WIN + 1)
    hi = min(v, n - WIN)
    return lo, hi


def move_to(orow, ocol, trow, tcol, H, W):
    """把窗口从 (orow,ocol) 挪到能覆盖目标格 (tcol,trow) 的最近原点。
    返回 (新orow, 新ocol, 代价)。"""
    rlo, rhi = window_range(trow, H)
    clo, chi = window_range(tcol, W)
    nrow = min(max(orow, rlo), rhi)
    ncol = min(max(ocol, clo), chi)
    return nrow, ncol, abs(nrow - orow) + abs(ncol - ocol)


def count_coverable(badge_cells, orow, ocol, U):
    """窗口在 (orow,ocol) 时能处理 U 中多少徽章。"""
    return sum(1 for b in U
               if any(in_window(c, orow, ocol) for c in badge_cells[b]))


def heuristic(bc, U, nr, nc, H, W):
    """前瞻一层：搬到 (nr,nc) 后，剩余徽章各自的**最小移动代价均值**。
    值越小 ⇒ 该方向奔向徽章密集区，后续总移动更少。"""
    rem = [b for b in U if not any(in_window(c, nr, nc) for c in bc[b])]
    if not rem:
        return 0.0
    tot = 0
    for b in rem:
        tot += min(move_to(nr, nc, c[1], c[0], H, W)[2] for c in bc[b])
    return tot / len(rem)


STRATEGIES = ('A', 'B', 'C', 'D', 'E', 'F')


def plan(level, prefer_forward=True, strategy='auto'):
    """strategy='auto'（默认）：跑遍 STRATEGIES × {不分组, 按リスト页分组}，取**总点击最少**者。

    为什么需要多策略：单一排序键无法兼顾小盘与大盘——
      * 前瞻优先(A/C/E) 让 No.01 达到最优 3 次移动，但大盘 606 次箭头；
      * 覆盖数优先(B/D) 大盘降到 546 次，No.01 却退化成 4 次。
    为什么还要「按页分组」（用户 2026-10-11 要求把翻页计入优化）：大难度 汉字表 >48 字
      要翻 リスト 页，而**翻页一次 ≈ 4 次普通点击的代价**（动作 + 0.6s 翻页动画）。
      不分组时按窗口顺序走，会在两页之间反复横跳、翻页几十次；分组变体把同页徽章集中处理，
      把翻页降到 (页数-1) 次（大难度≈1 次），代价是箭头略增。
    排序键 = n_touch + n_arrow + **4×n_page**（近似总耗时），取最小。
    """
    fill, kanji_order, bc, W, H = solve(level)
    if strategy != 'auto':
        return _plan(level, fill, kanji_order, bc, W, H, strategy)

    best = None
    for s in STRATEGIES:
        for gb in (False, True):
            r = _plan(level, fill, kanji_order, bc, W, H, s, group_by_page=gb)
            if r is None:
                continue
            # 总代价 ≈ 触摸 + 箭头 + 4×翻页（一次翻页 = 一次点击 + PAGE_WAIT ≈ 4 倍）
            total = r['n_touch'] + r['n_arrow'] + 4 * r['n_page']
            key = (total, r['n_page'], r['n_arrow'],
                   r['arrows'].get('L', 0) + r['arrows'].get('U', 0))
            if best is None or key < best[0]:
                best = (key, r, s, gb)
    if best is None:
        raise SystemExit('⚠️ No.%s 所有策略均失败' % level)
    res = best[1]
    res['strategy'] = best[2] + ('+G' if best[3] else '')
    return res


def _plan(level, fill, kanji_order, bc, W, H, strategy, group_by_page=False):
    orow = ocol = 0
    cur_lpage = 0            # リスト 当前页（打开时停在第 1 页 = 0）
    seq = []
    arrows = {'R': 0, 'D': 0, 'L': 0, 'U': 0}
    n_page = 0
    guard = 0

# 分组：按 リスト 页（升序）或整体；分组时同页徽章集中处理 → 翻页降到 (页数-1)
    if group_by_page:
        pages = sorted(set(kanji_page(fill[b], kanji_order) for b in fill))
        groups = [[b for b in fill if kanji_page(fill[b], kanji_order) == p]
                  for p in pages]
    else:
        groups = [list(fill.keys())]

    for badges in groups:
        U = set(badges)
        while U:
            guard += 1
            if guard > 10000:
                raise SystemExit('⚠️ 规划死循环')

            # ---- 1) 吃掉当前窗口内能处理的所有徽章 ----
            progressed = True
            while progressed:
                progressed = False
                for b in sorted(U):
                    for cell in bc[b]:
                        rel = in_window(cell, orow, ocol)
                        if rel is None:
                            continue
                        i, j = rel
                        seq.append(('map', i, j, '%d=%s' % (b, fill[b])))
                        # 汉字若在 リスト 其它页，先翻到该页（大难度必用；小难度 0 次）
                        wp = kanji_page(fill[b], kanji_order)
                        while cur_lpage < wp:
                            seq.append(('page', LIST_NEXT_D[0], LIST_NEXT_D[1], 'リスト次'))
                            cur_lpage += 1
                            n_page += 1
                        while cur_lpage > wp:
                            seq.append(('page', LIST_PREV_D[0], LIST_PREV_D[1], 'リスト前'))
                            cur_lpage -= 1
                            n_page += 1
                        ki, kj = kanji_pos(fill[b], kanji_order)
                        seq.append(('kanji', ki, kj, fill[b]))
                        U.discard(b)
                        progressed = True
                        break
            if not U:
                break

            # ---- 2) 选下一步窗口移动 ----
            best = None
            for b in U:
                for cell in bc[b]:
                    nr, nc, cost = move_to(orow, ocol, cell[1], cell[0], H, W)
                    cov = count_coverable(bc, nr, nc, U)
                    back = 1 if (nr < orow or nc < ocol) else 0
                    if strategy == 'A':     # 当前默认
                        key = (cost, round(heuristic(bc, U, nr, nc, H, W), 3),
                               nr, -cov, nc)
                    elif strategy == 'B':   # 覆盖数优先
                        key = (cost, -cov, round(heuristic(bc, U, nr, nc, H, W), 3),
                               nr, nc)
                    elif strategy == 'C':   # 前瞻用总和（密集区权重更大）
                        key = (cost,
                               round(heuristic(bc, U, nr, nc, H, W) * len(U), 3),
                               nr, -cov, nc)
                    elif strategy == 'D':   # 覆盖数 + 前瞻总和
                        key = (cost, -cov,
                               round(heuristic(bc, U, nr, nc, H, W) * len(U), 3),
                               nr, nc)
                    elif strategy == 'E':   # 前瞻均值 + 覆盖数（覆盖排在行号前）
                        key = (cost, round(heuristic(bc, U, nr, nc, H, W), 3),
                               -cov, nr, nc)
                    elif strategy == 'F':   # 回溯惩罚优先
                        key = (cost, back, round(heuristic(bc, U, nr, nc, H, W), 3),
                               nr, -cov, nc)
                    else:
                        key = (cost, -cov)
                    if best is None or key < best[0]:
                        best = (key, nr, nc)

            _, nr, nc = best
            # 逐格发射箭头（先走行再走列；方向由差值符号决定）
            while orow != nr:
                d = 'D' if nr > orow else 'U'
                orow += 1 if d == 'D' else -1
                seq.append(('arrow', ARROW[d][0], ARROW[d][1], '缩略图%s' % ('↓' if d == 'D' else '↑')))
                arrows[d] += 1
            while ocol != nc:
                d = 'R' if nc > ocol else 'L'
                ocol += 1 if d == 'R' else -1
                seq.append(('arrow', ARROW[d][0], ARROW[d][1], '缩略图%s' % ('→' if d == 'R' else '←')))
                arrows[d] += 1

    return {
        'level': int(level), 'W': W, 'H': H,
        'nbadge': len(fill), 'nkanji': len(kanji_order),
        'seq': seq, 'arrows': arrows,
        'n_touch': sum(1 for s in seq if s[0] in ('map', 'kanji')),
        'n_arrow': sum(arrows.values()),
        'n_page': n_page,
    }


# ---- 自检：与 No.01 已知硬编码序列比对 ------------------------------------
# 由 fill_fast_level1.py SEQ 反推：窗口 (orow,ocol) 下的 map(i,j) -> 谜题格(行,列)
# 硬编码窗口轨迹：(0,0) ×7 → ▶(0,1) → ▶(0,2) → ▼(1,2)
HARDCODED = [
    ((0, 0), (0, 1), 1), ((0, 0), (1, 0), 5), ((0, 0), (1, 2), 6),
    ((0, 0), (2, 1), 8), ((0, 0), (2, 3), 9), ((0, 0), (3, 1), 7),
    ((0, 0), (3, 2), 11), ((0, 1), (0, 3), 2), ((0, 2), (0, 3), 3),
    ((1, 2), (3, 0), 4), ((1, 2), (3, 1), 10),
]


def self_test():
    """验证 badge_cells 轴序 + 窗口模型：硬编码 map 推出的谜题格必须属于该徽章。"""
    _, _, bc, W, H = solve(1)
    print('=== 自检：No.01 硬编码序列 vs badge_cells ===')
    print('盘面 %dx%d' % (W, H))
    ok = 0
    for (orow, ocol), (i, j), badge in HARDCODED:
        row, col = orow + i, ocol + j
        hit = (col, row) in bc.get(badge, [])
        ok += hit
        print('  窗口(%d,%d) map(%d,%d) → 谜题(行%d,列%d) 徽章%-3d %s'
              % (orow, ocol, i, j, row, col, badge, '✓' if hit else '✗'))
    print('命中 %d/%d' % (ok, len(HARDCODED)))
    if ok != len(HARDCODED):
        print('⚠️ 轴序/窗口模型有误，规划器结论不可信')
        return False

    # 再验证：规划器生成的序列应能覆盖全部徽章，且每步 map 的格确实属于该徽章
    res = plan(1)
    print('\n=== 规划器 No.01 ===')
    print('  徽章 %d，触摸 %d，箭头 %d %s'
          % (res['nbadge'], res['n_touch'], res['n_arrow'], res['arrows']))
    _, _, bc2, _, _ = solve(1)
    # 重放规划器序列，校验每一步 map 落点
    orow = ocol = 0
    seen = set()
    bad = 0
    for kind, a, b, note in res['seq']:
        if kind == 'arrow':
            if (a, b) == ARROW['R']:
                ocol += 1
            elif (a, b) == ARROW['L']:
                ocol -= 1
            elif (a, b) == ARROW['D']:
                orow += 1
            elif (a, b) == ARROW['U']:
                orow -= 1
        elif kind == 'map':
            badge = int(note.split('=')[0])
            row, col = orow + a, ocol + b
            if (col, row) not in bc2.get(badge, []):
                print('  ✗ map(%d,%d)→(%d,%d) 不属于徽章%d' % (a, b, row, col, badge))
                bad += 1
            seen.add(badge)
    print('  重放校验：覆盖徽章 %d/%d，异常 %d' % (len(seen), res['nbadge'], bad))
    print('  结论：%s' % ('✓ 规划器自洽' if bad == 0 and len(seen) == res['nbadge'] else '✗ 有问题'))
    return bad == 0 and len(seen) == res['nbadge']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--level', type=int)
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--stats', action='store_true')
    ap.add_argument('--self-test', action='store_true')
    a = ap.parse_args()

    if a.self_test:
        sys.exit(0 if self_test() else 1)

    if not a.level:
        ap.error('需要 --level 或 --self-test')

    res = plan(a.level)
    if a.json:
        print(json.dumps(res, ensure_ascii=False))
        return

    if a.stats or True:
        print('No.%02d 盘面%dx%d 徽章%d 汉字%d'
              % (res['level'], res['W'], res['H'], res['nbadge'], res['nkanji']))
        print('触摸 %d（%d 徽章 × 2）+ 箭头 %d  %s'
              % (res['n_touch'], res['nbadge'], res['n_arrow'],
                 dict((k, v) for k, v in res['arrows'].items() if v)))
        if res['arrows'].get('L') or res['arrows'].get('U'):
            print('⚠️ 用到 ◀/▲（坐标系对称推断，尚未实机标定）')
        print('预计耗时 ≈%.1fs（每拍 0.125s）'
              % ((res['n_touch'] + res['n_arrow']) * 0.125))
    if not a.stats:
        print('\n序列：')
        for n, (kind, x, y, note) in enumerate(res['seq'], 1):
            print('  %2d %-6s (%3d,%3d) %s' % (n, kind, x, y, note))


if __name__ == '__main__':
    main()
