#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模式2（ひりどりナンクロ）填字：**复用模式1 已验证的解答操作**
（plan_fast 的规划几何 + fill_fast_any 的执行节奏：点缩略图编号格选组 + 点リスト汉字绑定）。

用户 2026-10-14 明确：模式2 的解答操作与模式1 **完全一样**（同编号整组联动 = 模式1 的徽章绑定）。
差别只在**数据层**：模式2 的记录格式与模式1 不同，`solve2.py` 解析不了，故这里用
`plan_mode2_beam.load_plan` 取 (fill, kanji_order, badge_cells)，再交给 `plan_fast._plan`。

用法（需已停在填字界面；模式2 默认手写，脚本先点 LISTMODE 切リスト）：
  python3 mode2_fill.py --rec 270 --dry      # 只打印规划
  python3 mode2_fill.py --rec 270            # 执行
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import plan_fast as P              # noqa: E402
import fill_fast_any as FA         # noqa: E402
import kanji_common as F           # noqa: E402
import lr_plan as LR               # noqa: E402
from plan_mode2_beam import load_plan   # noqa: E402


def _mode2_data(rec):
    """模式2 记录 → plan_fast/lr_plan 同构数据。"""
    plan, (R, C), slots, cands = load_plan(rec)
    fill = {p['slot']: p['kanji'] for p in plan}
    # plan_fast/kentei_fill 的 badge_cells 元组是 (列, 行)；load_plan 是 (行, 列)
    bc = {p['slot']: [(c, r) for (r, c) in p['cells']] for p in plan}
    return fill, cands, bc, C, R


def build(rec, strategy='A'):
    """plan_fast 路径（箭头导航；作为对照/兜底）。"""
    fill, cands, bc, W, H = _mode2_data(rec)
    # group_by_page=True：按リスト页分组，避免组序在页间反复跳（否则翻页次数暴涨）
    return P._plan(rec, fill, cands, bc, W, H, strategy, group_by_page=True)


def build_lr(rec, hop_weight=1.22, search=True):
    """L/R 跳跃路径（★ 与模式1 新管线同口径）：用跳跃替掉大量箭头，
    动作数大幅下降 ⇒ 输入队列不积压 ⇒ 长序列不丢（模式1 中1：箭头 102→33）。
    返回结构与 P.plan() 一致，额外含 hop 动作，供 fill_fast_any.do_fill 执行。
    """
    fill, cands, bc, W, H = _mode2_data(rec)
    # 读序 = 按 (行,列) 排；badge_cells 元组是 (列,行)
    cells = {b: sorted(bc[b], key=lambda c: (c[1], c[0])) for b in bc}
    order0 = list(fill.keys())
    if search:
        _, order, dpr = LR.search_order(order0, fill, cands, cells, W, H, hop_weight)
    else:
        order, dpr = order0, LR.dp(order0, cells, W, H, hop_weight)
    seq, arrows, n_hop, n_page = LR.emit(order, dpr[0][2], fill, cands, cells)
    n_touch = sum(1 for s in seq if s[0] in ('map', 'kanji'))
    return {'level': rec, 'W': W, 'H': H, 'nbadge': len(fill), 'nkanji': len(cands),
            'seq': seq, 'arrows': arrows, 'n_touch': n_touch,
            'n_arrow': sum(arrows.values()), 'n_hop': n_hop, 'n_page': n_page,
            'strategy': 'lr'}


def reanchor(R, C):
    """把缩略图窗口重锚到左上角 (0,0)，供「序列假设窗口从 (0,0) 起」的调用前使用。

    ★ 2026-10-14 实测（用户确认机制 + 实机验证）：
      * 缩略图四周箭头**每点一次移窗一格**；窗口到地图边缘后，该方向的箭头
        **消失**（点击落空但无副作用）⇒ 狂按 (R+2)/(C+2) 次必收敛到 (0,0)。
      * **必须慢速**：0.02 pacing 连点会被吞，窗口停在盘面中部 ⇒ 之后所有
        `map`（点缩略图格）全部错位。hold 0.06 + after 0.10 才稳定复现。
    """
    lx, ly = P.ARROW['L'][0] / 1.5, P.ARROW['L'][1] / 1.5 - 192
    ux, uy = P.ARROW['U'][0] / 1.5, P.ARROW['U'][1] / 1.5 - 192
    for _ in range(R + 2):
        F.tap(ux, uy, hold=0.06, after=0.10)
    for _ in range(C + 2):
        F.tap(lx, ly, hold=0.06, after=0.10)


def detect_unfilled(shot, R, C):
    """读上屏图 → 未填格列表 [(行,列)]（0-based）。

    模式2 盘面：**待填格 = 浅/亮底 + 组号数字**，已填/固定格 = 彩色底 + 汉字
    ⇒ 用格中心亮度区分（阈值 200，实测待填格亮底、已填格有彩色底明显更暗）。
    """
    import numpy as np
    from PIL import Image
    im = np.array(Image.open(shot).convert('RGB')).astype(int)
    gray = im.mean(2)
    dark = gray < 100
    cols = [x for x in range(256) if dark[:, x].sum() > 40]
    rows = [y for y in range(192) if dark[y, :].sum() > 40]
    if not cols or not rows:
        return []
    x0, x1, y0, y1 = min(cols), max(cols), min(rows), max(rows)
    cw, ch = (x1 - x0) / C, (y1 - y0) / R
    out = []
    for r in range(R):
        for c in range(C):
            cx, cy = int(x0 + cw * (c + 0.5)), int(y0 + ch * (r + 0.5))
            if im[cy - 1:cy + 2, cx - 1:cx + 2].mean() > 200:
                out.append((r, c))
    return out


def patch_round(rec):
    """重锚窗口 → (0,0)，然后**全量重跑**序列（替代读图补填）。

    ★ 2026-10-14 决策：放弃「读图找未填组」的像素判据。原因：
      * 模式2 大盘格子仅 ~12.5×7.6 px，「未填（白底数字）/ 已填（汉字）/
        固定格（汉字）」的底色相同，亮度、饱和度、暗占比判据全部重叠
        （实测把已填汉字格大量误判，导致每轮「待补组」都是噪声）。
      * 实测数据：每轮漏掉的组**组号各不相同** ⇒ 是**随机丢键**而非系统性漏组。
      故「重锚 → 全量重跑」在几轮内即可把上轮漏掉的组补齐，零误判风险，
      且完全符合「先算后打」原则。
    """
    plan, (R, C), slots, cands = load_plan(rec)
    reanchor(R, C)                       # 序列假设窗口从 (0,0) 起（慢速，见 reanchor 注）
    sub = P._plan(rec, {p['slot']: p['kanji'] for p in plan}, cands,
                  {p['slot']: [(c, r) for (r, c) in p['cells']] for p in plan}, C, R, 'A')
    sub.setdefault('n_hop', 0)           # do_fill 的 lr 分支会打印它
    P.plan = lambda level, **kw: sub
    LR.make_plan = lambda level, **kw: sub
    # 重跑也用慢速点击（0.02 pacing 丢键率更高，慢速提升单轮命中率）
    _orig = FA.click_design
    FA.click_design = lambda xd, yd: F.tap(xd / 1.5, yd / 1.5 - 192,
                                           hold=0.05, after=0.06)
    try:
        FA.do_fill(rec)
    finally:
        FA.click_design = _orig
    return True


def main():
    args = sys.argv[1:]
    if '--rec' not in args:
        raise SystemExit(__doc__)
    rec = int(args[args.index('--rec') + 1])
    strategy = args[args.index('--strategy') + 1] if '--strategy' in args else 'A'
    use_lr = os.environ.get('AI_TAS_PLAN', 'lr') == 'lr'
    rounds = int(os.environ.get('AI_TAS_ROUNDS', '3'))

    res = build_lr(rec) if use_lr else build(rec, strategy)
    print('rec%d  盘面%dx%d  组%d  汉字%d  路径=%s  触摸%d(map+kanji) 箭头%d 跳跃%d 翻页%d' %
          (rec, res['W'], res['H'], res['nbadge'], res['nkanji'],
           'L/R' if use_lr else 'plan', res['n_touch'], res['n_arrow'],
           res.get('n_hop', 0), res.get('n_page', 0)), flush=True)
    if '--dry' in args:
        for s in res['seq']:
            print('   ', s)
        return

    # 让 do_fill 用我们的序列：★必须同时 patch 两条路径——
    #   AI_TAS_PLAN=lr 时 do_fill 走 lr_plan.make_plan（内部 P.solve=模式1解析），
    #   否则 mode2 记录会解析失败（KeyError）。故 P.plan 与 LR.make_plan 都要覆盖。
    P.plan = lambda level, **kw: res
    LR.make_plan = lambda level, **kw: res
    if os.environ.get('AI_TAS_PREANCHOR'):
        print('  预重锚窗口 → (0,0)（慢速点缩略图箭头）…', flush=True)
        reanchor(res['H'], res['W'])
    evid = os.path.join(F.SHOT_DIR, 'l%02d_fill_complete.png' % rec)
    t0 = time.time()
    FA.do_fill(rec)                            # 第 1 轮：完整序列
    for rnd in range(1, rounds + 1):
        time.sleep(1.0)
        chk = os.path.join(F.SHOT_DIR, 'm2_rec%d_check%d.png' % (rec, rnd))
        F.shot(chk)                            # 干净截图（shot 自带 -draw_mouse 0）
        if F.banner_visible(evid) or F.banner_visible(chk):
            print('  ✅ 第%d轮出正解（累计 %.1fs）' % (rnd, time.time() - t0), flush=True)
            return
        print('  ⚠️ 第%d轮未见正解 → 重锚后全量重跑' % rnd, flush=True)
        patch_round(rec)
    print('  ❌ %d 轮后仍未出正解' % rounds, flush=True)


if __name__ == '__main__':
    main()
