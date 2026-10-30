#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快通填字执行器：通用关卡的「缩略图滑动窗口」快通（替代已废弃的対応表慢路径）。

★ 与 kanji_common.py 的分工
  * 导航 / 结算 / 通关判定 —— **全部复用 kanji_common**（含像素自校验，可靠且已验证）。
  * 填字 —— 换成 plan_fast.py 离线算好的动作序列。

★ 核心原则（用户 2026-10-11 明确）
  **先算后打**：序列 100% 由 datasheet 推导，**不读屏幕掩码、不找橙色光标、
  不做任何视觉闭环**。之前在「读图 + 找橙色光标」上耗掉的大量时间，本路径全部省掉。

★ 与旧対応表慢路径的对比（同为绑定 N 个徽章）
  旧路径      ：每徽章 4 次触摸（対応表 → 选徽章 → リスト → 点字）+ 面板切换动画
  本路径      ：每徽章 2 次触摸（点缩略图格 + 点汉字），リスト 常驻，零面板切换
  ⇒ No.35（37 徽章）触摸数 148 → 74，另有约 31 次箭头移动。

用法:
  # 单独填字（假定已停在填字界面；导航用 kanji_common.nav_to_fill）
  python3 fill_fast_any.py --level 35

  # 一键：先导航再填字再结算
  python3 fill_fast_any.py --level 35 --with-nav
  python3 fill_fast_any.py --level 16 --with-nav --warm      # 已在选关页时加 --warm

  # 热启动续关（上一关结算后已停在选关页）时用它：
  # 只做「检查选关页 + 点关」，不做 30s 冷启动全链路。填字仍走本脚本的快通序列。
  python3 fill_fast_any.py --level 3 --warm-nav

  # 只看序列 / 只跑填字不结算
  python3 fill_fast_any.py --level 35 --dry-run
  python3 fill_fast_any.py --level 35 --no-settle

环境变量（2026-10-13 起改自适应等待，见 PITFALLS §S24）:
  AI_TAS_SKIP_LISTMODE  已在填字界面且リスト已开时置 1
  AI_TAS_PANEL_WAIT(0.85)  仅作「等列表面板打开」轮询的超时上限（原固定睡眠，已废）
  AI_TAS_SEIKAI_WAIT(1.2)  仅作「等正解横幅出现」轮询的超时基数（原固定睡眠，已废）
  AI_TAS_PAGE_WAIT(0.6)    リスト翻页动画等待（**保留固定值**：翻页无可靠像素签名）
  AI_TAS_ARROW_{LX,LY,UX,UY}  覆盖 ◀▲ 坐标（已实机标定，一般无需覆盖，见 plan_fast.ARROW）
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, '..', '..')))

import kanji_common as F      # noqa: E402  导航/结算/判定全部复用
import plan_fast as P         # noqa: E402

# ★ 2026-10-13（§S24）：下面两个原为**固定睡眠**，现仅作自适应轮询的上限/基数（见 do_fill）。
PANEL_WAIT = float(os.environ.get('AI_TAS_PANEL_WAIT', 0.85))
SEIKAI_WAIT = float(os.environ.get('AI_TAS_SEIKAI_WAIT', 1.2))
# リスト 翻页（前/次）带约 0.4s 翻页动画；紧随其后的「点汉字」若不等动画播完会**静默丢失**
# （ふつう No.01 实测：不等待时 73 徽章有 6 个绑不上、题盘留空、不出正解）。
PAGE_WAIT = float(os.environ.get('AI_TAS_PAGE_WAIT', 0.6))
# ★ 2026-10-13（§S25）：长序列喘息。290 步大盘关（medium 56 等）在 0.087s/步
#   无停顿压缩节奏下会累积丢输入（实测填不满、不出正解）；每 10 步休 0.3s 即稳定
#   正解（trace 实证：截图引入的 ~0.3s/10步 节奏恰能兜住）。小关代价仅 +0.75s。
BREATHE_EVERY = int(os.environ.get('AI_TAS_BREATHE_EVERY', 10))
BREATHE_SEC = float(os.environ.get('AI_TAS_BREATHE_SEC', 0.3))
LISTMODE_XY = (80, 500)       # 设计坐标：打开リスト面板

# 由 plan_fast 的几何常量推出设计坐标（与 fill_fast_level1.py 同一套）
def _map_xy(i, j):
    return P.MAP_X0 + P.MAP_STEP * j, P.MAP_Y0 + P.MAP_STEP * i


def _kanji_xy(i, j):
    return P.KAN_X0 + P.KAN_STEP * j, P.KAN_Y0 + P.KAN_STEP * i


def click_design(xd, yd):
    """设计坐标（按键精灵 1.5× 空间）→ 下屏相对 → kanji_common.tap"""
    F.tap(xd / 1.5, yd / 1.5 - 192)


def do_fill(level, dry=False, plan_mode=None, rec=None):
    """执行快通填字。返回 (序列统计, 耗时)。

    plan_mode: 'lr' = 用 lr_plan.py 的 L/R 跳跃版序列（箭头大幅减少、新增 hop 动作）；
               其它/None = 现役 plan_fast.py。
    rec: 直接按《记录号》规划（plan_by_rec），用于没有「难度/关卡」映射的记录
         （認定問題题库 rec35–54、模式3 rec160–249、模式2 等）。level 可为 None。
    """
    plan_mode = plan_mode or os.environ.get('AI_TAS_PLAN', '')
    if rec is None and os.environ.get('AI_TAS_REC'):
        rec = int(os.environ['AI_TAS_REC'])
    tagfd = ('l%02d' % level) if level is not None else ('rec%s' % rec)
    if rec is not None:
        import plan_by_rec
        res = plan_by_rec.plan_rec(int(rec))
        print('  [plan=rec] rec%d 箭头 %d + 跳跃 %d + 翻页 %d'
              % (rec, res['n_arrow'], res['n_hop'], res['n_page']))
    elif plan_mode == 'lr':
        import lr_plan
        res = lr_plan.make_plan(level)
        print('  [plan=lr] 箭头 %d + 跳跃 %d + 翻页 %d'
              % (res['n_arrow'], res['n_hop'], res['n_page']))
    else:
        res = P.plan(level)
    # §S40：仓库只存 seq，W/H/nbadge/nkanji 等规划期元数据不再落盘，
    # 打印改用 seq 现算的统计（seq_codec.seq_stats）
    print('%s  共 %d 步：触摸 %d + 箭头 %d + リスト翻页 %d  %s'
          % (tagfd, len(res['seq']), res['n_touch'], res['n_arrow'],
             res.get('n_page', 0),
             dict((k, v) for k, v in res['arrows'].items() if v)))
    if res['arrows'].get('L') or res['arrows'].get('U'):
        print('  用到 ◀/▲（已实机标定：◀=(14,378) ▲=(99,299)，见 plan_fast.ARROW）')
    if dry:
        return res, 0.0

    if not os.environ.get('AI_TAS_SKIP_LISTMODE'):
        # ★ 2026-10-13（§S24）：等「開始!」横幅消失后再点 LISTMODE——游戏内计时器
        #   从横幅消失起算，此刻即计时起点。实测：横幅前的过渡态与横幅期间输入均被
        #   吞（预点 LISTMODE 不注册），故不预点；横幅消失后点稳注册。
        F.wait_banner_gone()
        # 点 LISTMODE 并轮询等列表面板真正打开（替代固定 PANEL_WAIT；
        # 打开即可点字，比固定 0.85s 更稳也更快）。带一次补点兜底。
        opened = False
        for attempt in (1, 2):
            click_design(*LISTMODE_XY)      # 开リスト面板
            t_panel = time.time()
            chk = None
            while time.time() - t_panel < max(PANEL_WAIT * 2.5, 2.0):
                chk = F.shot(os.path.join(F.DIAG_DIR, '%s_listchk.png' % tagfd))
                if F.list_panel_open(chk):
                    break
                time.sleep(0.1)
            if chk is not None and F.list_panel_open(chk):
                time.sleep(0.1)             # 面板可见后留极小缓冲再点字
                opened = True
                break
            print('  [warn] LISTMODE 第 %d 次点击后列表面板仍未打开，补点' % attempt)
        if not opened:
            raise SystemExit('❌ LISTMODE 两次点击后列表面板均未打开，中止'
                             '（防止静默涂胶到手写面板；截图 %s）' % chk)

    t0 = time.time()
    for n, (kind, a, b, note) in enumerate(res['seq'], 1):
        if kind == 'map':
            click_design(*_map_xy(a, b))
        elif kind == 'kanji':
            click_design(*_kanji_xy(a, b))
        elif kind == 'page':                 # リスト 翻页：等动画播完再继续
            click_design(a, b)
            time.sleep(PAGE_WAIT)
        elif kind == 'hop':                  # L/R 肩键跳跃：a = 'w'(R向前) / 'q'(L向后)
            F.hop(a)
        elif kind == 'black':                # 模式3「黒マス」：把当前选中组清成墙体（a,b 为底屏相对坐标）
            F.tap(a, b)
        else:                                # arrow：a,b 已是设计坐标
            click_design(a, b)
        if BREATHE_EVERY > 0 and n % BREATHE_EVERY == 0:
            time.sleep(BREATHE_SEC)          # §S25 长序列喘息，防累积丢输入
        if n % 10 == 0 or kind in ('arrow', 'page'):
            print('  %3d/%d %s' % (n, len(res['seq']), note), flush=True)
    dt = time.time() - t0
    print('  填字完成 %.2fs' % dt, flush=True)

    # ★ 2026-10-13（§S24）：正解横幅出现即截图——证据图计时器 ≈ fill 耗时，
    #   不再固定睡 SEIKAI_WAIT（那 1.2s 全计进计时器）。超时（失败关）直接截，交由 settle 诊断。
    # ★ 2026-10-13（§S26）：长序列（≥150 步）输入队列积压，游戏消化滞后，正解横幅
    #   可晚于最后一拍数秒——3s 窗口会错过横幅截到黑场（medium56/hard11/30/50 实证）。
    #   按步数自适应放宽窗口；轮询到横幅即返回，对成功关零代价。
    seikai_timeout = max(SEIKAI_WAIT * 2.5, 3.0, 8.0 if len(res['seq']) >= 150 else 0.0)
    shot_name = ('l%02d_fill_complete.png' % level) if level is not None \
        else ('rec%s_fill_complete.png' % rec)
    F.wait_seikai_shot(os.path.join(F.SHOT_DIR, shot_name), timeout=seikai_timeout)
    return res, dt


def do_settle(level):
    """结算 + 通关判定（复用 kanji_common.settle / level_cleared）。"""
    F.settle(level)
    ok, blue, gray = F.level_cleared(level)
    print('  通关判定：蓝 %.1f%% / 灰 %.1f%%  ->  %s'
          % (blue * 100, gray * 100, '✅ 已通关' if ok else '❌ 未通关'))
    return ok


def main():
    args = sys.argv[1:]
    rec = int(args[args.index('--rec') + 1]) if '--rec' in args else None
    if '--level' in args:
        level = int(args[args.index('--level') + 1])
    elif rec is not None:
        level = None            # 按 rec 规划：假定游戏已停在填字界面
    else:
        raise SystemExit(__doc__)
    dry = '--dry-run' in args
    with_nav = '--with-nav' in args
    warm = '--warm' in args
    warm_nav = '--warm-nav' in args

    if level is not None and warm_nav and not dry:
        # 热启动导航：检查已在选关页 → 点关两次 → 等填字界面出现即返回
        # ★ 2026-10-13（§S24）：原为点关后固定 sleep(NAV_ENTER_WAIT)。
        #   NAV_TAP_AFTER 必须保持 1.5——压到 0.3 会让第二点注册不上，
        #   fill 首拍沦为进关点击、整关涂胶（两次失败实证）。
        #   现改为轮询 in_fill：进关瞬态（横幅出现前）即就绪，
        #   尽早返回让 do_fill 抢在横幅消失前点 LISTMODE，重叠面板就绪延迟。
        chk = F.shot(os.path.join(F.DIAG_DIR, 'l%02d_warm_check.png' % level))
        if not F.on_level_select(chk):
            raise SystemExit('⚠️ --warm-nav 假定游戏已停在选关页，但实测不在'
                             '（截图 %s）。请先手工回到选关页。' % chk)
        print('[导航] 热启动：已确认在选关页，点关 No.%02d 两次' % level)
        x, y = F.level_xy(level)
        F.tap(x, y, after=F.NAV_TAP_AFTER)
        F.tap(x, y, after=F.NAV_TAP_AFTER)
        t_enter = time.time()
        entered = False
        while time.time() - t_enter < max(F.NAV_ENTER_WAIT, 3.0):
            p = F.shot(os.path.join(F.DIAG_DIR, 'l%02d_enterchk.png' % level))
            if F.in_fill_interface(p):
                entered = True
                break
            time.sleep(0.1)
        if not entered:
            raise SystemExit('⚠️ 点关后未进入填字界面（截图 %s），中止。' % p)
        print('[导航] 已进入填字界面（+%.1fs，横幅等待交由 do_fill 自适应处理）'
              % (time.time() - t_enter))
    elif level is not None and with_nav and not dry:
        # 全链路导航，复用 kanji_common：warm=True 走热启动（已在选关页），否则冷启动。
        print('[导航] %s -> No.%02d' % ('热启动' if warm else '冷启动', level), flush=True)
        F.nav_to_fill(level, warm=warm)

    tag = ('No.%02d' % level) if level is not None else ('rec%d' % rec)
    print('[填字] %s 快通序列' % tag, flush=True)
    do_fill(level, dry=dry, plan_mode='lr' if '--plan-lr' in args else None, rec=rec)
    if dry:
        return
    if '--no-settle' not in args and level is not None:
        print('[结算]', flush=True)
        do_settle(level)
    print('done.')


if __name__ == '__main__':
    main()
