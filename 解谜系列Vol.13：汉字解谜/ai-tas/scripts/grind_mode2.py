#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模式2 ふつう/むずかしい 连清脚本（同会话解锁認定 silver+ 用，2026-10-16）。

前提：游戏已停在对应难度选关页（由调用方交互导航，不重启 desmume）。
流程：逐关 双击进关 → wait_banner → v7 填字（含补填）→ 正解 → 盲点结算过场
      → 回选关页。已通关（蓝钮）自动跳过。
失败（两轮填字均无正解）→ 截图 + exit(3)，绝不盲进下一关（防在盘内乱点）。
选关页判定：戻る粉钮 (194-237,174-185) 存在 且 非填字界面（in_board，见其 docstring）。

用法：
  AI_TAS_DISPLAY=:0 AI_TAS_GRIND_DIFF=futsuu python3 grind_mode2.py
"""
import os
import sys
import time

os.environ.setdefault('DISPLAY', ':99')
sys.path.insert(0, '/workspace/Kanji/ai-tas/scripts')
import kanji_common as F                                  # noqa: E402
import numpy as np                                        # noqa: E402
from PIL import Image                                     # noqa: E402
import run_mode2_easy1_fast as V7                         # noqa: E402
import plan_store as PS                                   # noqa: E402
from plan_mode2_beam import load_plan as beam_load        # noqa: E402

SHOT = os.environ.get('AI_TAS_SHOT_DIR', '/tmp/m2grind')
DIFF = os.environ.get('AI_TAS_GRIND_DIFF', 'futsuu').lower()
RECS = {'futsuu': list(range(270, 285)),
        'muzukashii': list(range(285, 300))}[DIFF]
os.makedirs(SHOT, exist_ok=True)


def dshot(name):
    p = os.path.join(SHOT, name)
    F.shot(p)
    return p


def btn_xy(level):
    col, row = (level - 1) % 10, (level - 1) // 10
    return 19 + 24 * col, 83 + 20 * row       # 实测按钮带 nds-y 70-91/行距20


def is_blue(path, x, y):
    a = np.array(Image.open(path).convert('RGB')).astype(int)[192:]
    c = a[max(0, y - 4):y + 5, max(0, x - 8):x + 9]
    blue = ((c[:, :, 2] > c[:, :, 0] + 30) & (c[:, :, 2] > 150)).sum()
    return blue >= 6


def in_board(path):
    """模式2 填字界面判定（下屏整体暗像素）。

    ★ 勿用 `kanji_common.in_fill_interface`——其 `_top_is_board` 对模式2 **8×8 小白盘**
      失效（白格 <6000 不达标），会把「已进盘」误判成未进（2026-10-16 实战踩坑）。
    实测下屏暗像素：盘内 ≈9582(8×8)/10129(20×25) vs 选关页 ≈2103(8×8)/3142–3282，阈值 6000。
    """
    a = np.array(Image.open(path).convert('RGB')).astype(int)[192:]
    return int((a.max(2) < 110).sum()) > 6000


def on_select_page(path):
    """选关页强判据：非填字界面 + 右下 戻る粉钮。"""
    if in_board(path):
        return False
    a = np.array(Image.open(path).convert('RGB')).astype(int)[192:]
    box = a[170:190, 190:242]
    pink = ((box[:, :, 0] > 225) & (box[:, :, 1] > 95)
            & (box[:, :, 1] < 190) & (box[:, :, 2] > 95)
            & (box[:, :, 2] < 190)).sum()
    return pink > 40


def settle(tag, max_tap=16):
    """盲点 (128,163) 推进 ★獲得数→セーブ中→选关页；卡在盘内则失败。"""
    for i in range(max_tap):
        p = dshot('%s_settle_%02d.png' % (tag, i))
        if on_select_page(p):
            print('  选关页确认（第 %d 次检测）' % (i + 1), flush=True)
            return True
        F.tap(128, 163, after=0.5)
        time.sleep(0.35)
    p = dshot('%s_settle_fail.png' % tag)
    print('  ❌ 未回选关页（截图 %s）' % p, flush=True)
    return False


def fill_rec(rec):
    """v7 填字：重锚 → plans.json 串重建 → exec_seq → 补填。"""
    plan_local, (R, C), slots_mat = V7.load_plan(rec)
    V7.BOARD[0], V7.BOARD[1] = R, C
    if not F.list_panel_open():
        V7.B.tap(*V7.ICON_LIST, after=F.TAP_AFTER)
        V7.B.sleep(1.2)
        V7.B.flush()
        time.sleep(0.5)
    cnt = [1]
    for _ in range(C - 1):
        V7.press(V7.LEFT)
        cnt[0] += 1
    for _ in range(R - 1):
        V7.press(V7.UP)
        cnt[0] += 1
    V7.B.flush()
    seq = PS.get(rec)
    assert seq, 'plans.json 无 rec%d 计划' % rec
    # ★ 多页リスト：页数由候选数决定（cert 小盘单页，通常问题 25×20 多页）。
    #   进关恒开第 0 页（§S57.2），detect_page 内部自截图判定。
    ncand = len(beam_load(rec)[3])
    now_page, npages = V7.detect_page(ncand)
    fixed, npress, endpage, nohop = V7.rebuild_pages_sim(
        seq, plan_local, R, C, now_page, npages)
    print('  rec%d 候选 %d → %d 页（开页 %d）' % (rec, ncand, npages, now_page), flush=True)
    t0 = time.time()
    V7.exec_seq(fixed, cnt)
    print('  rec%d 填字 %.2fs / %d 动作（重建 %d→%d 步）'
          % (rec, time.time() - t0, cnt[0], len(seq), len(fixed)), flush=True)
    poll = os.path.join(SHOT, '_nk.png')
    F.wait_seikai_shot(poll, timeout=10.0)
    if F.banner_visible(poll):
        return True
    print('  ⚠️ 首轮未正解 → 重锚补填', flush=True)
    cnt2 = [1]
    for _ in range(C - 1):
        V7.press(V7.LEFT)
        cnt2[0] += 1
    for _ in range(R - 1):
        V7.press(V7.UP)
        cnt2[0] += 1
    V7.B.flush()
    V7.exec_seq(nohop, cnt2, tag='（补填）')
    F.wait_seikai_shot(poll, timeout=10.0)
    return F.banner_visible(poll)


def exit_board():
    """盘内弃答：オプション(40,166) → 問題選択(53,176)×2 → はい(86,114)×2。"""
    F.tap(40, 166, after=1.5)
    F.tap(53, 176, after=1.5)
    F.tap(53, 176, after=1.5)
    F.tap(86, 114, after=1.5)
    F.tap(86, 114, after=2.0)
    return on_select_page(dshot('_exit_chk.png'))


def grind(diff, recs):
    """连清 diff 难度 recs（假定已停在该难度选关页）。返回 True/False（不 sys.exit）。

    已通关（蓝钮）自动跳过；单关失败自动弃答重试至多 3 次。
    """
    print('=== %s 连清（rec %d-%d）===' % (diff, recs[0], recs[-1]), flush=True)
    p0 = dshot('start.png')
    if not on_select_page(p0):
        print('❌ 起点不在选关页（截图 %s）' % p0, flush=True)
        return False
    for level in range(1, len(recs) + 1):
        rec = recs[level - 1]
        tag = '%s_l%02d' % (diff, level)
        p = dshot('%s_pre.png' % tag)
        if is_blue(p, *btn_xy(level)):
            print('L%02d 已通关，跳过' % level, flush=True)
            continue
        ok = False
        for attempt in range(1, 4):
            print('--- %s L%02d (rec%d) 第%d次 ---' % (diff, level, rec, attempt), flush=True)
            x, y = btn_xy(level)
            F.tap(x, y, after=F.NAV_TAP_AFTER)
            F.tap(x, y, after=F.NAV_TAP_AFTER)
            time.sleep(3.5)
            F.wait_banner_gone(timeout=8.0)
            time.sleep(0.5)
            p2 = dshot('%s_board_%d.png' % (tag, attempt))
            if not in_board(p2):
                print('  ⚠️ 未进填字界面（截图 %s）→ 退出重试' % p2, flush=True)
                exit_board()
                time.sleep(1.0)
                continue
            if fill_rec(rec):
                ok = True
                break
            dshot('%s_fillfail_%d.png' % (tag, attempt))
            print('  ⚠️ rec%d 两轮未正解 → 弃答重试' % rec, flush=True)
            if not exit_board():
                print('  ⚠️ 弃答后未回选关页 → 中止', flush=True)
                return False
            time.sleep(1.0)
        if not ok:
            print('❌ rec%d 连续 3 次未正解 → 中止' % rec, flush=True)
            return False
        print('  ✅ 正解!', flush=True)
        if not settle(tag):
            return False
        time.sleep(0.8)
    dshot('%s_all_done.png' % diff)
    print('=== %s 全部完成 ===' % diff, flush=True)
    return True


def main():
    sys.exit(0 if grind(DIFF, RECS) else 3)


if __name__ == '__main__':
    main()
