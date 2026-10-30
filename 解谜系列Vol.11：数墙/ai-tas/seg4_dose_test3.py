#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seg4 剂量测试 ROUND3：重复验证 0.135s 的稳定性 + 现役 0.14s 基线噪声。

ROUND2 结果（/tmp/dose_test2.log）：
  A g0.035 h0.07  a0.03 (0.135, 静默0.100) → 100% 但 fill 277.6s（异常慢，疑掉帧重试）
  B g0.03  h0.07  a0.035(0.135, 静默0.105) → 100% fill  96.0s
  C g0.03  h0.075 a0.03 (0.135, 静默0.105) → 100% fill  94.5s
  现役 g0.04 h0.07 a0.03 (0.140, 静默0.100) → 100% fill  90.6s（ROUND1）

问题：0.135 vs 0.14 理论只差 2s/关，单次噪声 ±5s，需重复取分布才能定性。
本轮：每档跑 REP 次，输出每次 fill 与均值，判断
  1) A 的 277s 是否偶发（若复现→gap0.035 有系统性问题）
  2) B 的 96s 是否稳定（若稳定且均值 < 0.14 基线 → 可采纳）

用法: python3 seg4_dose_test3.py
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
import seg3_run as S

M.OUT = "/tmp/seg4_prep"
os.makedirs(M.OUT, exist_ok=True)

LVL = 41
REP = 2


def test_dose(lvl, dose):
    idx = lvl - 1
    p = M.PUZ[idx]
    if not S.enter_and_prepare(lvl):
        print(f"  FAIL enter lvl{lvl}", flush=True)
        return None
    S.set_rect(p)
    M.TAP_MEGA = dict(dose)
    t0 = time.time()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = S.fill_level(lvl)
    log = buf.getvalue()
    topups = [int(x) for x in re.findall(r"topup=(\d+)", log)]
    nwalls = len(M.walls_of(idx))
    total_topup = sum(topups)
    el = time.time() - t0
    S.clear_to_select()
    rate = 100.0 * (nwalls - total_topup) / nwalls if nwalls else 0.0
    print(f"  lvl{lvl} g{dose['gap']} h{dose['hold']} a{dose['after']} ({sum(dose.values()):.3f}s) "
          f"| 墙={nwalls} 漏={total_topup} 命中={rate:.0f}% ok={bool(ok)} fill={el:.1f}s", flush=True)
    return rate, bool(ok), el


def main():
    DOSES = [
        ("现役 0.140 (g.04 h.07 a.03)", dict(gap=0.04,  hold=0.07,  after=0.03)),
        ("B    0.135 (g.03 h.07 a.035)", dict(gap=0.03,  hold=0.07,  after=0.035)),
        ("A    0.135 (g.035 h.07 a.03)", dict(gap=0.035, hold=0.07,  after=0.03)),
    ]
    print(f"=== ROUND3: 重复 {REP} 次/档 (limiter ON, lvl{LVL}) ===", flush=True)
    if not M.ensure_select():
        print("FATAL ensure_select", flush=True)
        return 1
    summary = {}
    for name, dose in DOSES:
        fills, rates = [], []
        for i in range(REP):
            print(f"-- {name}  [{i+1}/{REP}] --", flush=True)
            r = test_dose(LVL, dose)
            if r is None:
                print("  [abort] enter failed", flush=True)
                break
            rates.append(r[0])
            fills.append(r[2])
        if fills:
            summary[name] = (sum(fills) / len(fills), min(fills), max(fills),
                             sum(rates) / len(rates))
    print("\n===== SUMMARY =====", flush=True)
    for name, (avg, lo, hi, rate) in summary.items():
        print(f"{name}: 平均 fill={avg:.1f}s (min {lo:.1f} / max {hi:.1f}) 平均命中={rate:.0f}%",
              flush=True)
    M.TAP_MEGA = dict(gap=0.04, hold=0.07, after=0.03)
    print("\nDONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
