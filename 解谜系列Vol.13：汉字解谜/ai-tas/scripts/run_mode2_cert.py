#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模式2（ひりどりナンクロ）認定問題 runner——4 级 × 2 变体（rec252-259）速通 + 证据图。

机制（PITFALLS §S50/§S54，2026-10-16 实测标定）：
  * 認定题库 = rec252-259，4 级 × 2 变体（ブロンズ252/253、シルバー254/255、
    ゴールド256/257、プラチナ258/259）；同级每次进盘**随机**加载 2 变体之一（有放回）。
  * 全部单页盘（候选 ≤47 < 48，无翻页）；plans.json 已有 8 条 §S45 L/R 串。
  * 解锁：ブロンズ无门槛；シルバー以降 = 同会话模式2通常問題通关进度（存档不落盘，
    §S54.2）⇒ 银金白金需「大会话」（先连清通常問題不重启）。本 runner 只管
    「进盘→识别→填字→证据」，大会话由 run_mode2_cert_session.py 编排。
  * 识别（进盘后、填字前）：
      - シルバー/ゴールド/プラチナ：リスト 面板有字格数 = n_cand（42/47、35/41、
        39/37，同级两变体必不同）——复用 v7 count_inked_cells，37 rec 实证可靠；
      - ブロンズ（两变体 n_cand 同为 35）：与 ref_bronze252_list.png（rec252 实拍）
        的リスト区域做像素 diff——同 rec 渲染确定性、diff≈噪声；异 rec 字表不同、
        diff 大。阈值守在两者之间。
  * 退出重摇：オプション(40,166) → 問題選択(53,176)×2 → はい(86,114)×2
    （§S50 mode1 同款工具栏/对话框，mode2 盘内同布局；退出即弃答，不产生中断局，
    再进盘重摇变体）。
  * 导航坐标（2026-10-16 红网格/粉带实测，覆盖 §S54.3 旧目检值）：
      模式2主菜单 認定問題=(135,100)（二击）；级别菜单
      ブロンズ=(128,52) シルバー=(128,84) ゴールド=(128,116) プラチナ=(128,148)
      （粉带边界实测 y42-61/74-93/106-125/138-157；当前高亮项单击即进、
        非高亮项第一击只移高亮——先单击探测、仍菜单再补一击）。

用法：
  AI_TAS_CERT_LEVEL=bronze  AI_TAS_CERT_WANT=252,253 \
      AI_TAS_DISPLAY=:0 python3 run_mode2_cert.py
  # 证据图 → validation/mode2_4_certification/<level>_clear_r<rec>.png（§S37 量化）
"""
import os
import shutil
import subprocess
import sys
import time

os.environ.setdefault('DISPLAY', ':99')
sys.path.insert(0, '/workspace/Kanji/ai-tas/scripts')
import kanji_common as F                                  # noqa: E402
import numpy as np                                        # noqa: E402
from PIL import Image                                     # noqa: E402
import run_mode2_easy1_fast as V7                         # noqa: E402 (v7 管线复用)
import plan_store as PS                                   # noqa: E402
from plan_mode2_beam import load_plan as beam_load        # noqa: E402

SHOT = os.environ.get('AI_TAS_SHOT_DIR', '/tmp/m2cert')
EVDIR = os.environ.get('AI_TAS_EVDIR',
                       '/workspace/Kanji/validation/mode2_4_certification')
LEVEL = os.environ.get('AI_TAS_CERT_LEVEL', 'bronze').lower()
WANT = [int(x) for x in os.environ.get('AI_TAS_CERT_WANT', '').split(',') if x]
MAX_ROLLS = int(os.environ.get('AI_TAS_CERT_MAX_ROLLS', '14'))

CERT_VARIANTS = {'bronze': (252, 253), 'silver': (254, 255),
                 'gold': (256, 257), 'platinum': (258, 259)}
# 级别菜单按钮（粉带边界实测中心）
LEVEL_BTN = {'bronze': (128, 52), 'silver': (128, 84),
             'gold': (128, 116), 'platinum': (128, 148)}
# 退出三连（§S50 实测，mode2 同款工具栏）
OPT_WRENCH, OPT_PROBLEM, OPT_YES = (40, 166), (53, 176), (86, 114)

DIAG = os.path.join(SHOT, 'diag')


def dshot(name):
    os.makedirs(DIAG, exist_ok=True)
    p = os.path.join(DIAG, name)
    F.shot(p)
    return p


def cert_menu_visible(path):
    """認定级别菜单签名：下屏 4 条粉色按钮带（边界 y42-61/74-93/106-125/138-157）。"""
    a = np.array(Image.open(path).convert('RGB')).astype(int)[192:]
    pink = ((a[:, :, 0] > 225) & (a[:, :, 1] > 95) & (a[:, :, 1] < 175)
            & (a[:, :, 2] > 95) & (a[:, :, 2] < 175))[:, 40:215].sum(1)
    edges = [y for y in range(192) if pink[y] > 80]
    # 期望 8 条边界带（每按钮上下边各一），聚类到 ~4 组
    groups = []
    for y in edges:
        if not groups or y - groups[-1][-1] > 4:
            groups.append([y])
        else:
            groups[-1].append(y)
    return len(groups) >= 7   # 8 边界（高亮描边可能并组）⇒ ≥7 组宽松判定


def identify(path, level):
    """进盘识别 rec。返回 (rec, 依据描述)。"""
    n = V7.count_inked_cells(path)
    lo, hi = CERT_VARIANTS[level]
    plan_lo, (Rl, Cl), _, cands_lo = beam_load(lo)
    plan_hi, (Rh, Ch), _, cands_hi = beam_load(hi)
    nl, nh = len(cands_lo), len(cands_hi)
    if nl != nh:
        rec = lo if abs(n - nl) <= abs(n - nh) else hi
        return rec, 'リスト有字格=%d（%d→rec%d / %d→rec%d）' % (n, nl, lo, nh, hi)
    # bronze：与 rec252 实拍リスト面板做**墨迹掩码 XOR**（同 rec 渲染确定性：
    #   XOR/并 ≈ 0；异 rec 字表 25/35 格不同 → ≈0.5+，阈值守中间，分离度数量级）
    ref = np.array(Image.open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        'ref_bronze252_list.png')).convert('L')).astype(int)[192:]
    live = np.array(Image.open(path).convert('L')).astype(int)[192:]
    y0, y1, x0, x1 = 24, 162, 140, 250     # リスト 6×8 字格区（避开窗/光标/边框）
    ink_r, ink_l = ref[y0:y1, x0:x1] < 130, live[y0:y1, x0:x1] < 130
    union = int((ink_r | ink_l).sum())
    ratio = (int((ink_r ^ ink_l).sum()) / union) if union else 1.0
    rec = lo if ratio < 0.15 else hi
    return rec, ('リスト有字格=%d（同级同数）+ 墨迹XOR=%.3f vs rec252实拍 → rec%d'
                 % (n, ratio, rec))


def wait_state(timeout, pred, poll=0.3):
    t0 = time.time()
    while time.time() - t0 < timeout:
        p = dshot('_state.png')
        if pred(p):
            return p
        time.sleep(poll)
    return None


def enter_level(level):
    """从認定级别菜单进盘（高亮规则：单击探测，仍菜单再补一击）。"""
    x, y = LEVEL_BTN[level]
    F.tap(x, y, after=1.2)
    p = dshot('enter_1.png')
    if not cert_menu_visible(p):
        return True
    F.tap(x, y, after=1.5)
    p = dshot('enter_2.png')
    return not cert_menu_visible(p)


def exit_board():
    """盘内退出（弃答）：オプション → 問題選択×2 → はい×2 → 回级别菜单。"""
    F.tap(*OPT_WRENCH, after=1.0)
    dshot('exit_1_wrench.png')
    F.tap(*OPT_PROBLEM, after=0.8)
    F.tap(*OPT_PROBLEM, after=1.0)
    dshot('exit_2_problem.png')
    F.tap(*OPT_YES, after=0.6)
    F.tap(*OPT_YES, after=1.5)
    p = dshot('exit_3_yes.png')
    return cert_menu_visible(p)


def back_to_cert_menu():
    """从任意态回到認定级别菜单（戻る=(215,179) 连点 + 菜单签名轮询，上限 4 防过冲）。"""
    for i in range(4):
        if cert_menu_visible(dshot('_bk.png')):
            return True
        F.tap(215, 180, after=1.2)
    return cert_menu_visible(dshot('_bk.png'))


def fill_rec(rec):
    """填字 rec（v7 管线：重锚 → plans.json 串重建 → exec_seq）。"""
    plan_local, (R, C), slots_mat = V7.load_plan(rec)
    V7.BOARD[0], V7.BOARD[1] = R, C
    if not F.list_panel_open():
        V7.B.tap(*V7.ICON_LIST, after=F.TAP_AFTER)
        V7.B.sleep(1.2)
        V7.B.flush()
        time.sleep(0.5)
    cnt = [1]
    for _ in range(C - 1):                 # 重锚 (0,0)：方向键夹边必达
        V7.press(V7.LEFT); cnt[0] += 1
    for _ in range(R - 1):
        V7.press(V7.UP); cnt[0] += 1
    V7.B.flush()
    seq = PS.get(rec)
    assert seq, 'plans.json 无 rec%d 计划' % rec
    fixed, npress, endpage, nohop = V7.rebuild_pages_sim(seq, plan_local, R, C, 0, 1)
    t0 = time.time()
    V7.exec_seq(fixed, cnt)
    print('  rec%d 填字 %.2fs / %d 动作（重建 %d→%d 步）'
          % (rec, time.time() - t0, cnt[0], len(seq), len(fixed)), flush=True)
    poll = os.path.join(SHOT, '_seikai_poll.png')
    F.wait_seikai_shot(poll, timeout=10.0)
    if F.banner_visible(poll):
        return poll
    print('  ⚠️ 首轮未正解 → 重锚补填（无跳变体）', flush=True)
    cnt2 = [1]
    for _ in range(C - 1):
        V7.press(V7.LEFT); cnt2[0] += 1
    for _ in range(R - 1):
        V7.press(V7.UP); cnt2[0] += 1
    V7.exec_seq(nohop, cnt2, tag='（补填）')
    F.wait_seikai_shot(poll, timeout=10.0)
    return poll if F.banner_visible(poll) else None


def cert_like(path):
    """認定証画面签名：下屏中央大面白卡（实测 認定証 box≈0.61 vs 正解盘面≈0.27）。"""
    a = np.array(Image.open(path).convert('RGB')).astype(int)
    box = a[192:384, 30:226]
    return ((box.max(2) > 210) & (box.min(2) > 165)).mean() > 0.45


def save_evidence(poll, rec):
    """存正解证据 + 轮询認定証（★首次通关才出现，同级第二变体无）。

    2026-10-16 修：旧版 sleep(2.0) 单帧判断（阈值 0.22 太松，正解盘面 0.27 即误判），
    导致 platinum 首发认定証漏拍（被后续兜底连点推掉）。改「轮询 12s + 严阈值 0.45」。
    """
    out = os.path.join(EVDIR, '%s_clear_r%d.png' % (LEVEL, rec))
    im = Image.open(poll).convert('RGB').quantize(colors=256, dither=Image.NONE)
    im.save(out)
    print('  ✅ 正解! → 证据图 %s' % out, flush=True)
    for i in range(24):                     # 最多 ~12s（0.5s/次）
        time.sleep(0.5)
        cp = dshot('cert_poll_r%d_%02d.png' % (rec, i))
        if cert_like(cp):
            out2 = os.path.join(EVDIR, '%s_certificate_r%d.png' % (LEVEL, rec))
            Image.open(cp).convert('RGB').quantize(
                colors=256, dither=Image.NONE).save(out2)
            print('  📜 認定証 → %s' % out2, flush=True)
            time.sleep(1.0)
            F.tap(128, 150, after=1.5)      # 推进認定証
            dshot('cert_dismissed_r%d.png' % rec)
            return True
    print('  ℹ️ 未见認定証（非首次通关/已认定）', flush=True)
    return False


def nav_to_cert_menu():
    """冷启动 → 認定级别菜单（v7 公共导航 + 認定問題二击校验）。

    ★ AI_TAS_CERT_NO_NAV=1 时跳过冷启动：假定调用方已在同会话内把游戏停在
      認定级别菜单（大会话解锁路径——重启会丢通常問題进度，§S54.2）。
    """
    if os.environ.get('AI_TAS_CERT_NO_NAV') == '1':
        p = dshot('nonav_check.png')
        ok = cert_menu_visible(p)
        print('NO_NAV：已在認定级别菜单 = %s' % ('✅' if ok else '❌'), flush=True)
        return ok
    subprocess.run(['pkill', '-x', 'desmume-cli'], check=False)
    time.sleep(2)
    subprocess.run(['bash', '/workspace/Kanji/ai-tas/scripts/ensure_env.sh'],
                   check=False, capture_output=True)
    wt = F.wait_title()
    print('冷启动 → 标题页就绪 %.1fs' % wt, flush=True)
    F.tap(128, 100, after=F.NAV_TAP_AFTER)
    F.tap(95, 76, after=F.NAV_TAP_AFTER)
    time.sleep(3.0)
    F.tap(136, 96, after=F.NAV_TAP_AFTER)
    F.tap(136, 96, after=F.NAV_TAP_AFTER)
    time.sleep(2.0)
    F.tap(135, 100, after=1.2)             # 認定問題（二击规则）
    p = dshot('nav_cert_1.png')
    if not cert_menu_visible(p):
        F.tap(135, 100, after=1.5)
        p = dshot('nav_cert_2.png')
    ok = cert_menu_visible(p)
    print('認定级别菜单：%s' % ('✅' if ok else '❌ 未确认（看 diag）'), flush=True)
    return ok


def main():
    variants = CERT_VARIANTS[LEVEL]
    want = sorted(set(WANT) or set(variants))
    assert all(w in variants for w in want), 'want %s 超出 %s 变体' % (want, variants)
    os.makedirs(SHOT, exist_ok=True)
    os.makedirs(EVDIR, exist_ok=True)
    # 已有证据视为已捕获（幂等重跑）
    have = set()
    for r in want:
        if os.path.exists(os.path.join(EVDIR, '%s_clear_r%d.png' % (LEVEL, r))):
            have.add(r)
    print('模式2 認定 %s：目标 %s，已捕获 %s' % (LEVEL, want, sorted(have) or '无'), flush=True)
    if have >= set(want):
        print('全部已有证据，无事可做', flush=True)
        return
    if not nav_to_cert_menu():
        print('❌ 导航失败', flush=True)
        sys.exit(2)
    misses = 0
    for roll in range(1, MAX_ROLLS + 1):
        if have >= set(want):
            break
        print('--- 第 %d 轮进盘 ---' % roll, flush=True)
        if not enter_level(LEVEL):
            misses += 1
            print('  ⚠️ 未进盘（仍菜单），重试', flush=True)
            if misses >= 3:
                print('❌ 连续 3 轮未进盘——%s 认定级多半未解锁（同会话通常問題进度不足）'
                      % LEVEL, flush=True)
                sys.exit(6)
            continue
        misses = 0
        time.sleep(2.0)
        F.wait_banner_gone(timeout=7.0)     # 開始! 横幅吞点击（§S50.4）
        time.sleep(0.5)
        if not F.list_panel_open():
            V7.B.tap(*V7.ICON_LIST, after=F.TAP_AFTER)
            V7.B.sleep(1.2)
            V7.B.flush()
            time.sleep(0.6)
        p = dshot('roll%02d_board.png' % roll)
        rec, why = identify(p, LEVEL)
        print('  识别：%s' % why, flush=True)
        if rec in have:
            print('  rec%d 已捕获 → 退出重摇' % rec, flush=True)
            if not exit_board():
                print('  ⚠️ 退出未回到菜单 → back_to_cert_menu 兜底', flush=True)
                back_to_cert_menu()
            time.sleep(0.8)
            continue
        ev = fill_rec(rec)
        if ev:
            save_evidence(ev, rec)
            have.add(rec)
            if have >= set(want):
                break                       # ★集齐即停——勿再兜底连点（会推掉刚出的画面）
            # 正解后可能已回菜单/证书后回菜单——统一兜底
            if not cert_menu_visible(dshot('_after_clear.png')):
                back_to_cert_menu()
        else:
            print('  ❌ rec%d 填字未正解（识别疑错？）→ 退出重摇', flush=True)
            dshot('fail_%d.png' % rec)
            if not exit_board():
                back_to_cert_menu()
    print('=== 完成：捕获 %s / 目标 %s ===' % (sorted(have), want), flush=True)
    sys.exit(0 if have >= set(want) else 3)


if __name__ == '__main__':
    main()
