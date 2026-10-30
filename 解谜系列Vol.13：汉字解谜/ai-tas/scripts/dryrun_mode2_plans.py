#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线 dry-run：验证 plans.json 的 37 条 mode2 L/R 动作串可被「窗口态模拟」正确解读。

与 runner（run_mode2_easy1_fast.py v7，§S57）同口径，但**完全不碰模拟器**：
规划/改串后跑一遍，确认每条串在执行器眼里自洽（kanji 面板坐标 == 徽章 li
推导坐标），防止把错串写进 plans.json。

模拟规则（与 lr_plan.emit / beam walk_execute 同口径）：
  初始 窗口(0,0)/光标(0,0)（§S56 实证）；
  arrow：org/cur 同向 ±1（org 夹 [0,R-4]×[0,C-4]，cur 夹 [0,R-1]×[0,C-1]）；
  map(i,j)：光标 = org+(i,j)（点格即选中该格所属徽章，org 不变）；
  hop(w/q)：光标 = 当前徽章读序下一/上一格，org = clamp(光标)（§S12）；
  kanji/page：不影响窗口态。
每个 kanji 步恢复其徽章 → 该徽章汉字在候选表的 li → 面板坐标 (li%48//6, li%48%6)
必须与串里 K<row><col> 一致；翻页按**循环模型**（§U）双向取近重插：
正向「次」/反向「前」，次数 = min((tgt-cur)%n, (cur-tgt)%n)。
  2026-10-16 实测：面板进关**恒开第0页**（§S57.2），故运行时起点=0；
  本工具对 0 页起/末页起**两种起点都跑**，确认重建在两种假设下都自洽
  （翻页数只差在起点假设，坐标校验与起点无关）。
同时产出无跳变体 nohop（hop→等效箭头）：runner 补填轮用——徽章已绑定（蓝）
时 hop 跳不动（§S12），原样重打会窗口漂移。

cands 顺序一致性：**逐字反查** `cands.index(p['kanji']) == p['li']`——面板候选表
含未使用的干扰字（如 rec260：18 组 vs 19 候选），不能整体比对。

用法：python3 dryrun_mode2_plans.py
"""
import os
import sys

sys.path.insert(0, '/workspace/Kanji/ai-tas/scripts')
os.environ.setdefault('DISPLAY', ':99')

import plan_fast as P
import plan_store as PS
from plan_mode2_beam import load_plan as beam_load
import run_mode2_easy1_fast as R

RECS = ([260, 261, 262, 263, 264, 250, 251] + list(range(270, 285))
        + list(range(285, 300)))

ARROW_BY_DESIGN = {(P.ARROW[k][0], P.ARROW[k][1]): k for k in P.ARROW}
WIN = 4


def clamp(v, lo, hi):
    return min(max(v, lo), hi)


def simulate(seq, plan_local, Rows, Cols, start_page, npages, verbose=False):
    """返回 (fixed, npress, endpage, nohop, problems)"""
    by_slot = {p['slot']: sorted(p['cells']) for p in plan_local}
    cell2slot = {}
    for s, cs in by_slot.items():
        for cell in cs:
            cell2slot[cell] = s
    slot_page = {p['slot']: p['li'] // P.PAL_PAGE for p in plan_local}
    slot_kpos = {p['slot']: ((p['li'] % P.PAL_PAGE) // P.KANJI_COLS,
                             (p['li'] % P.PAL_PAGE) % P.KANJI_COLS)
                 for p in plan_local}
    org = [0, 0]
    cur = [0, 0]
    slot = None
    fixed, nohop = [], []
    curpage = start_page
    npress = 0
    problems = []
    for s in seq:
        k = s[0]
        if k == 'arrow':
            d = ARROW_BY_DESIGN.get((s[1], s[2]))
            if d is None:
                problems.append('未知箭头坐标 %r' % ((s[1], s[2]),))
                continue
            if d in ('U', 'D'):
                st = 1 if d == 'D' else -1
                org[0] = clamp(org[0] + st, 0, Rows - WIN)
                cur[0] = clamp(cur[0] + st, 0, Rows - 1)
            else:
                st = 1 if d == 'R' else -1
                org[1] = clamp(org[1] + st, 0, Cols - WIN)
                cur[1] = clamp(cur[1] + st, 0, Cols - 1)
            fixed.append(s); nohop.append(s)
        elif k == 'map':
            i, j = s[1], s[2]
            cur = [org[0] + i, org[1] + j]
            slot = cell2slot.get(tuple(cur))
            if slot is None:
                problems.append('map 步指向非徽章格 org=%s +( %d,%d)' % (org, i, j))
            note = '%d=%s' % (slot, dict((p['slot'], p['kanji'])
                                         for p in plan_local).get(slot, '?'))
            fixed.append(('map', i, j, note)); nohop.append(('map', i, j, note))
        elif k == 'hop':
            key = s[1]
            cs = by_slot[slot]
            idx = cs.index(tuple(cur))
            st = 1 if key == 'w' else -1
            cur = list(cs[(idx + st) % len(cs)])
            o_after = [clamp(cur[0], 0, Rows - WIN), clamp(cur[1], 0, Cols - WIN)]
            fixed.append(s)
            # nohop：用等效箭头把 org 从当前位置推到 o_after
            o = list(org)
            while o[0] != o_after[0]:
                dd = 'D' if o_after[0] > o[0] else 'U'
                o[0] += 1 if dd == 'D' else -1
                nohop.append(('arrow', P.ARROW[dd][0], P.ARROW[dd][1],
                              '缩略图%s(hop等效)' % dd))
            while o[1] != o_after[1]:
                dd = 'R' if o_after[1] > o[1] else 'L'
                o[1] += 1 if dd == 'R' else -1
                nohop.append(('arrow', P.ARROW[dd][0], P.ARROW[dd][1],
                              '缩略图%s(hop等效)' % dd))
            org = o_after
        elif k == 'kanji':
            if slot is None:
                problems.append('kanji 步前无 map（slot 未恢复）')
                fixed.append(s); nohop.append(s); continue
            row, col = s[1], s[2]
            exp = slot_kpos[slot]
            if (row, col) != exp:
                problems.append('kanji 坐标 (%d,%d) != 徽章%d 期望 %s'
                                % (row, col, slot, exp))
            tgt = slot_page[slot]
            # 循环翻页（§U）：双向取近，正向按「次」/反向按「前」
            fwd = (tgt - curpage) % npages
            bwd = (curpage - tgt) % npages
            if fwd <= bwd:
                btn, n = P.LIST_NEXT_D, fwd
            else:
                btn, n = P.LIST_PREV_D, bwd
            for _ in range(n):
                fixed.append(('page', btn[0], btn[1],
                              'リスト次' if fwd <= bwd else 'リスト前'))
                nohop.append(('page', btn[0], btn[1],
                              'リスト次' if fwd <= bwd else 'リスト前'))
                npress += 1
            curpage = tgt
            note = dict((p['slot'], p['kanji']) for p in plan_local).get(slot, '')
            fixed.append(('kanji', row, col, note))
            nohop.append(('kanji', row, col, note))
        elif k == 'page':
            continue                      # 丢弃旧线性模型翻页，重建时重插
        else:
            problems.append('未知动作 kind=%r' % (k,))
    return fixed, npress, curpage, nohop, problems


def main():
    all_ok = True
    for rec in RECS:
        seq = PS.get(rec)
        if seq is None:
            print('rec%-3d ❌ plans.json 无计划' % rec)
            all_ok = False
            continue
        plan_local, (Rws, Cws), _slots = R.load_plan(rec)
        _p, _rc, _s, cands = beam_load(rec)
        # cands 顺序一致性：逐字反查（面板含未使用的干扰字，不能整体比对）
        order_ok = all(cands.index(p['kanji']) == p['li'] for p in plan_local)
        npages = max(1, -(-len(cands) // P.PAL_PAGE))
        st = {'map': 0, 'kanji': 0, 'arrow': 0, 'hop': 0, 'page': 0}
        for s in seq:
            st[s[0]] = st.get(s[0], 0) + 1
        fixed, npress, endpage, nohop, problems = simulate(
            seq, plan_local, Rws, Cws, npages - 1, npages)
        # 也按「面板开在第0页」跑一遍（2026-10-16 实测即此，§S57.2），
        # 确认翻页重建在两种起点下都自洽
        fixed0, npress0, end0, _, problems0 = simulate(
            seq, plan_local, Rws, Cws, 0, npages)
        ok = (not problems) and (not problems0) and order_ok
        all_ok = all_ok and ok
        print('rec%-3d %dx%d 组%-3d 候选%-3d 页%d | 串: map%-3d kan%-3d arrow%-3d hop%-3d page%-3d '
              '→ 重建翻页%-2d(末页起)/%-2d(0页起) nohop%-4d | cands顺序%s %s'
              % (rec, Rws, Cws, len(plan_local), len(cands), npages,
                 st.get('map', 0), st.get('kanji', 0), st.get('arrow', 0),
                 st.get('hop', 0), st.get('page', 0),
                 npress, npress0, len(nohop), '✓' if order_ok else '❌',
                 '✓' if ok else '❌ ' + '; '.join(problems[:3])))
    print('=== %s ===' % ('全部 37 关模拟+校验通过' if all_ok else '存在问题，见上'))


if __name__ == '__main__':
    main()
