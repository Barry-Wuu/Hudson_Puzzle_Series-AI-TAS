#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seg4 剂量边界测试（第二轮）：36×20 的 0.13~0.14 夹缝。

第一轮结论（/tmp/dose_test.log）：
  36x20 0.140s/格(g.04 h.07 a.03) → 100%（398 墙零漏，fill 90.6s）
  36x20 0.130s/格 压 gap(g.03 h.07 a.03) → 91%（漏36） fill 250.5s
  36x20 0.130s/格 压 after(g.04 h.07 a.02) → 91%（漏35） fill 228.3s
  36x20 0.120s/格(g.02 h.07 a.03) → 62%（漏153） fill 302.9s
  → 0.13 两条路都掉到 91%，说明"总时长"而非某个参数是瓶颈；0.135 未测。

本轮目的：确认 0.14 是否已是物理极限（0.135 能否仍 100%）。
  desmume limiter ON = 60fps，1 帧 16.67ms：
    0.140s ≈ 8.4 帧 / 0.135s ≈ 8.1 帧 / 0.130s ≈ 7.8 帧
  → 边界很可能就是"8 帧"，0.135 是夹缝里的最后一格。

三档同为 0.135s，但参数分配不同，用于区分瓶颈是时长还是静默期：
  A 压 gap      g0.035 h0.07 a0.03   (静默期 0.100)
  B 压 gap+加静默 g0.03  h0.07 a0.035  (静默期 0.105)
  C 压 gap+加 hold g0.03  h0.075 a0.03 (静默期 0.105)

用法: python3 seg4_dose_test2.py
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

LVL = 41          # 36×20 首关（398 墙），与第一轮对照档同关，命中率可比


def test_dose(lvl, dose):
    idx = lvl - 1
    p = M.PUZ[idx]
    if not S.enter_and_prepare(lvl):
        print(f"  FAIL enter lvl{lvl}", flush=True)
        return None
    S.set_rect(p)
    M.TAP_MEGA = dict(dose)          # 36×20 → TAP_MEGA
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
    print(f"  lvl{lvl} {p['w']}x{p['h']} g{dose['gap']} h{dose['hold']} a{dose['after']} "
          f"({sum(dose.values()):.3f}s/格, {sum(dose.values())*60:.1f}帧) | 墙={nwalls} "
          f"首涂漏={total_topup} 首涂命中={rate:.0f}% ok={bool(ok)} fill={el:.1f}s", flush=True)
    return rate, bool(ok), total_topup, nwalls, el


def main():
    DOSES = [
        ("A 压gap(0.135s)",      dict(gap=0.035, hold=0.07,  after=0.03)),
        ("B 压gap+静默(0.135s)", dict(gap=0.03,  hold=0.07,  after=0.035)),
        ("C 压gap+hold(0.135s)", dict(gap=0.03,  hold=0.075, after=0.03)),
    ]
    print("=== seg4 dose test ROUND2: 36x20 边界 0.135s (limiter ON) ===", flush=True)
    if not M.ensure_select():
        print("FATAL ensure_select", flush=True)
        return 1
    for name, dose in DOSES:
        print(f"-- {name} --", flush=True)
        r = test_dose(LVL, dose)
        if r is None:
            print("  [abort] enter failed", flush=True)
            break
    # 复原现役剂量，避免影响后续任何调用
    M.TAP_MEGA = dict(gap=0.04, hold=0.07, after=0.03)
    print("\nDONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
