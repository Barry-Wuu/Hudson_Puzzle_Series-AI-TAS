#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seg4 剂量测试：limiter ON（录屏真实速度）下，对むずかしい的两种盘面尺寸
（24×14 / 36×20）实测剂量命中率，用 fill 阶段 topup（首涂漏格数）算真实命中率。

背景：
  - むずかしい 共 80 关：lvl1..40 = 24×14（~180-190 墙），lvl41..80 = 36×20（~390-400 墙）
  - fill_huge 内部 dose = TAP_MEGA if w>30 else TAP_HUGE（mode2_fast.py line 594）
    → 36×20 的注入必须写 M.TAP_MEGA，24×14 写 M.TAP_HUGE
  - TAP_HUGE 已被 seg3（ふつう 30 关 24×14 全 ok）间接验证；TAP_MEGA 仅 turbo 标定过
    （0.14s/格=98%、0.13s/格=88%），limiter ON 帧钟更宽裕 → 0.13s/格 有望 100%
  - 对照档必测：确认现役剂量在 limiter ON 下成立

用法: python3 seg4_dose_test.py
"""
import os
import sys
import re
import io
import contextlib
import time

os.environ.setdefault("V11_DIFF", "むずかしい")
HERE = "/workspace/Hudson_Puzzle_Series-AI-TAS/解谜系列Vol.11：数墙/ai-tas"
sys.path.insert(0, HERE)
import mode2_fast as M
import seg3_run as S          # 含 fill_huge/verify_huge/36宽 set_rect 的通用驱动

M.OUT = "/tmp/seg4_prep"
os.makedirs(M.OUT, exist_ok=True)


def test_dose(lvl, dose):
    """进关 -> 注入被测 dose -> fill（首涂+topup）-> 回选关。
    返回 (首涂命中率%, ok, topup, 总墙数, fill墙钟)。"""
    idx = lvl - 1
    p = M.PUZ[idx]
    if not S.enter_and_prepare(lvl):
        print(f"  FAIL enter lvl{lvl}", flush=True)
        return None
    S.set_rect(p)
    # 注入被测 dose（关键：36×20 → TAP_MEGA；24×14 → TAP_HUGE）
    if p["w"] > 30:
        M.TAP_MEGA = dict(dose)
    elif p["h"] > 10:
        M.TAP_HUGE = dict(dose)
    elif p["w"] > 10:
        M.TAP_WIDE = dict(dose)
    else:
        M.TAP = dict(dose)
    t0 = time.time()
    buf = io.StringIO()
    # fill_level（含 verify 兜底）：limiter ON 下 fill 的 wait_clear 常超时，
    # verify 兜底确认 clear（seg2/seg3 同机制 ok=True）。topup 反映首涂命中率。
    with contextlib.redirect_stdout(buf):
        ok = S.fill_level(lvl)
    log = buf.getvalue()
    topups = [int(x) for x in re.findall(r"topup=(\d+)", log)]
    nwalls = len(M.walls_of(idx))
    total_topup = sum(topups)
    el = time.time() - t0
    S.clear_to_select()
    rate = 100.0 * (nwalls - total_topup) / nwalls if nwalls else 0.0
    print(f"  lvl{lvl} {p['w']}x{p['h']} g{dose['gap']} h{dose['hold']} a{dose['after']} "
          f"({sum(dose.values()):.3f}s/格) | 墙={nwalls} 首涂漏={total_topup} "
          f"首涂命中={rate:.0f}% ok={bool(ok)} fill={el:.1f}s", flush=True)
    return rate, bool(ok), total_topup, nwalls, el


def main():
    # 24×14: hold≥0.07 底线；36×20: turbo 标定 0.14s/格=98%、0.13s/格=88%
    #   → limiter ON 更宽裕，探 0.13s（两条路）与 0.12s（激进）
    DOSES = {
        "24x14": [
            ("对照 TAP_HUGE",   dict(gap=0.02,  hold=0.07, after=0.02)),   # 0.110s/格
            ("after0.015(试探)", dict(gap=0.02,  hold=0.07, after=0.015)),  # 0.105s/格
            ("gap0.015(试探)",  dict(gap=0.015, hold=0.07, after=0.02)),   # 0.105s/格
        ],
        "36x20": [
            ("对照 TAP_MEGA",   dict(gap=0.04,  hold=0.07, after=0.03)),   # 0.140s/格
            ("gap0.03(0.13s)",  dict(gap=0.03,  hold=0.07, after=0.03)),   # 0.130s/格
            ("after0.02(0.13s)", dict(gap=0.04, hold=0.07, after=0.02)),   # 0.130s/格
            ("gap0.02(0.12s)",  dict(gap=0.02,  hold=0.07, after=0.03)),   # 0.120s/格
        ],
    }
    LVL_BY_SIZE = {"24x14": 2, "36x20": 41}   # むずかしい 实关（各尺寸首关+1）

    print("=== seg4 dose test (limiter ON; むずかしい 实关实测) ===", flush=True)
    if not M.ensure_select():
        print("FATAL ensure_select", flush=True)
        return 1
    for size, lvl in LVL_BY_SIZE.items():
        print(f"\n##### {size}  (lvl{lvl}) #####", flush=True)
        for name, dose in DOSES[size]:
            print(f"-- {name} --", flush=True)
            r = test_dose(lvl, dose)
            if r is None:
                print(f"  [abort] lvl{lvl} enter failed", flush=True)
                break
    print("\nDONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
